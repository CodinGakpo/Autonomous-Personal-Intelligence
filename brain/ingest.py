"""brain/ingest.py — the Plan B write path, wired end-to-end.

    input file ──▶ extractor (LLM, claude -p) ──▶ resolver ──▶ store (persist as a node)

Two paths today:
  • résumé  → a Person node (the 6-axis radar profile).
  • meeting → a Meeting node + one Task node per action item, each linked back to the meeting and
    (when the assignee matches a known person) to that Person — so the graph actually connects.

The heavy LLM work lives inside the extractors via `claude -p` (cheap, no Hermes tool-wall). This
module is pure orchestration: extract → resolve → upsert. Run standalone, or from a Hermes skill.

Usage:
    uv run python -m brain.ingest resume  <resume_file> [--role "Backend Engineer"]
    uv run python -m brain.ingest meeting <transcript>  [--summary summary.txt] [--date 2026-06-24]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain import store
from brain.resolver import normalize
from skills.meeting_to_task import extract_meeting
from tools.resume.parser import parse_resume


def ingest_resume(conn: Any, path: Path, role: str = "", kind: str = "person") -> dict[str, Any]:
    """Résumé file → Person node (create/update/review decided by the resolver).

    `kind` = "candidate" (a hiring applicant) or "person" (default). `role`, when given, both weights the
    radar scoring toward that role AND is stored as the target role for HR fit ranking.
    """
    profile = parse_resume(Path(path), role)
    name = profile.get("name")
    # email goes in the resolver's disambiguator slot: same-name people with different emails stay distinct.
    candidate = {**profile, "assignee": profile.get("email") or "", "kind": kind, "target_role": role or None}
    summary = profile.get("summary") or profile.get("headline")
    res, pid = store.upsert(conn, "person", candidate, title=name, summary=summary, source=str(path))
    return {"action": res.action, "id": pid, "name": name, "reason": res.reason}


def _match_person(conn: Any, assignee: str) -> dict[str, Any] | None:
    """Forgivingly link a meeting's free-text assignee ('Sai') to a known Person ('Sai Prakash')."""
    a = normalize(assignee)
    if not a:
        return None
    for p in store.all_of_type(conn, "person"):
        t = normalize(p.get("title"))
        if not t:
            continue
        if a == t or a in t.split() or t.split()[0] == a.split()[0]:
            return p
    return None


def ingest_meeting(
    conn: Any, path: Path, summary_path: Path | None = None, date: str = ""
) -> dict[str, Any]:
    """Meeting transcript → Meeting node + Task nodes, linked (from_meeting, assigned_to)."""
    transcript = Path(path).read_text(encoding="utf-8", errors="replace")
    summary_text = (
        Path(summary_path).read_text(encoding="utf-8", errors="replace") if summary_path else ""
    )
    result = extract_meeting(transcript, summary_text, date)

    # Meeting node — title + date form its natural key, so re-ingesting the same meeting updates it.
    m_title = result.get("meeting_title") or Path(path).stem
    m_date = result.get("meeting_date") or date or ""
    meeting_cand = {
        "name": m_title,
        "assignee": m_date,
        "meeting_date": m_date,
        "participants": result.get("participants", []),
    }
    m_res, mid = store.upsert(
        conn, "meeting", meeting_cand, title=m_title, summary=result.get("summary"), source=str(path)
    )

    tasks_out = []
    for task in result.get("tasks", []):
        assignee = task.get("assignee") or ""
        candidate = {**task, "assignee": assignee}
        t_res, tid = store.upsert(
            conn, "task", candidate, title=task.get("name"), summary=task.get("description"),
            source=str(path),
        )
        store.add_edge(conn, tid, mid, "from_meeting")
        person = _match_person(conn, assignee)
        if person:
            store.add_edge(conn, tid, person["id"], "assigned_to")
        tasks_out.append({
            "action": t_res.action,
            "id": tid,
            "name": task.get("name"),
            "assignee": assignee or None,
            "linked_person": bool(person),
        })

    return {"meeting": {"action": m_res.action, "id": mid, "title": m_title}, "tasks": tasks_out}


def _clickup_task_to_candidate(task: dict[str, Any]) -> dict[str, Any]:
    """Map a ClickUp task (v2 API shape) to the brain's task-node candidate."""
    assignees = task.get("assignees") or []
    who = ""
    if assignees:
        first = assignees[0]
        who = first.get("username") or first.get("email") or ""
    due_date = None
    due_ms = task.get("due_date")
    if due_ms:
        try:
            due_date = datetime.fromtimestamp(int(due_ms) / 1000, tz=timezone.utc).date().isoformat()
        except (ValueError, TypeError):
            due_date = None
    priority = None
    pri = task.get("priority")
    if isinstance(pri, dict):
        priority = pri.get("priority")
    return {
        "name": task.get("name"),
        "assignee": who,
        "clickup_id": str(task.get("id")),
        "clickup_url": task.get("url"),
        "description": task.get("text_content") or task.get("description") or "",
        "due_date": due_date,
        "priority": priority,
        "status": (task.get("status") or {}).get("status"),
    }


def ingest_clickup(conn: Any, list_id: str, client: Any = None) -> list[dict[str, Any]]:
    """Pull every task in a ClickUp list into the brain as Task nodes (idempotent via clickup_id)."""
    from clickup.client import ClickUpClient

    client = client or ClickUpClient()
    out = []
    for task in client.list_tasks(list_id):
        cand = _clickup_task_to_candidate(task)
        res, tid = store.upsert(
            conn, "task", cand, title=cand["name"], summary=cand["description"],
            source=f"clickup:{cand['clickup_id']}",
        )
        out.append({"action": res.action, "id": tid, "name": cand["name"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingest a résumé or meeting into the brain (extract → resolve → store)."
    )
    sub = ap.add_subparsers(dest="kind", required=True)

    pr = sub.add_parser("resume", help="ingest a résumé file as a Person node")
    pr.add_argument("file", type=Path)
    pr.add_argument("--role", default="", help="target role: weights scoring + stored for HR fit ranking")
    pr.add_argument("--candidate", action="store_true", help="mark this person as a hiring candidate")

    pm = sub.add_parser("meeting", help="ingest a meeting transcript as Meeting + Task nodes")
    pm.add_argument("file", type=Path)
    pm.add_argument("--summary", type=Path, help="optional meeting-summary file")
    pm.add_argument("--date", default="", help="meeting date (YYYY-MM-DD) for relative due dates")

    pc = sub.add_parser("clickup", help="pull tasks from a ClickUp list into the brain")
    pc.add_argument("--list-id", default=None, help="ClickUp list id (or set CLICKUP_LIST_ID)")

    args = ap.parse_args()
    conn = store.connect()

    if args.kind == "clickup":
        list_id = args.list_id or os.environ.get("CLICKUP_LIST_ID")
        if not list_id:
            raise SystemExit("Give --list-id or set CLICKUP_LIST_ID (with CLICKUP_TOKEN).")
        if not os.environ.get("CLICKUP_TOKEN"):
            raise SystemExit("Set CLICKUP_TOKEN in .env to pull from ClickUp (see INTEGRATIONS.md).")
        rows = ingest_clickup(conn, list_id)
        print(f"Pulled {len(rows)} task(s) from ClickUp list {list_id}:")
        for r in rows:
            print(f"  [{r['action']}] {r['name']}")
        return

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")
    if args.kind == "resume":
        out = ingest_resume(conn, args.file, args.role, "candidate" if args.candidate else "person")
        print(f"[{out['action']}] person: {out['name']}  (id {out['id']})")
        print(f"  {out['reason']}")
    else:
        out = ingest_meeting(conn, args.file, args.summary, args.date)
        m = out["meeting"]
        print(f"[{m['action']}] meeting: {m['title']}  (id {m['id']})")
        for t in out["tasks"]:
            who = f" -> {t['assignee']}" if t["assignee"] else " (unassigned)"
            link = " [linked to person]" if t["linked_person"] else ""
            print(f"  [{t['action']}] task: {t['name']}{who}{link}")


if __name__ == "__main__":
    sys.exit(main())
