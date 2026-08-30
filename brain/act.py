"""brain/act.py — the Act stage: push brain Tasks out to ClickUp (the write-back seam).

The pipeline's last step. Ingest/resolve/store gave us Task nodes; this turns them into real ClickUp
tasks. It is **dry-run by default** — it prints exactly the create-task payload it *would* send and
touches no network. `--push` actually creates them (via `clickup.ClickUpClient`, the one sanctioned
ClickUp path per ADR-0001) and records the returned id back on the node, so a second run never
double-creates: idempotency by remembering the `clickup_id`, the same principle as the write path.

    brain Task node ──▶ payload (name + markdown body) ──▶ ClickUp create ──▶ clickup_id stored back

Usage:
    uv run python -m brain.act                              # dry-run: show what would be created
    uv run python -m brain.act --push --list-id 901234567   # for real (needs CLICKUP_TOKEN in env)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from brain import store
from brain.notify import notify
from clickup.client import ClickUpClient, TaskRef


def _payload(node: dict[str, Any]) -> dict[str, str]:
    """A Task node -> the {name, description} ClickUp's create_task wants (assignee/due/priority folded in)."""
    d = node["data"]
    meta = []
    if d.get("assignee"):
        meta.append(f"- Assignee: {d['assignee']}")
    if d.get("due_date"):
        meta.append(f"- Due: {d['due_date']}")
    if d.get("priority"):
        meta.append(f"- Priority: {d['priority']}")
    if node.get("source"):
        meta.append(f"- Source: {node['source']} (via the Agent OS brain)")
    body = (d.get("description") or "").strip()
    description = (body + "\n\n" + "\n".join(meta)).strip() if meta else (body or node["title"])
    return {"name": node["title"], "description": description}


def _link(conn: Any, node: dict[str, Any], ref: TaskRef) -> None:
    """Record the ClickUp id/url back on the node so we never create it twice."""
    data = {**node["data"], "clickup_id": ref.id, "clickup_url": ref.url}
    conn.execute(
        "UPDATE entities SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat(timespec="seconds"), node["id"]),
    )
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Push brain Tasks into ClickUp (dry-run unless --push).")
    ap.add_argument("--list-id", default=None, help="ClickUp list id (required with --push)")
    ap.add_argument("--push", action="store_true", help="actually create the tasks (default: dry-run)")
    ap.add_argument("--force", action="store_true", help="include tasks already linked to ClickUp")
    args = ap.parse_args()

    conn = store.connect()
    tasks = store.all_of_type(conn, "task")
    pending = [t for t in tasks if args.force or not t["data"].get("clickup_id")]
    linked = [t for t in tasks if not args.force and t["data"].get("clickup_id")]

    if args.push:
        list_id = args.list_id or os.environ.get("CLICKUP_LIST_ID")
        if not list_id:
            raise SystemExit("--push needs --list-id <id> or CLICKUP_LIST_ID (and CLICKUP_TOKEN).")
        client = ClickUpClient()  # token from CLICKUP_TOKEN
        for t in pending:
            p = _payload(t)
            ref = client.create_task(list_id, p["name"], p["description"])
            _link(conn, t, ref)
            print(f"[created] {t['title']} -> {ref.url}")
        if pending:
            notify("tasks_pushed", count=len(pending), list_id=list_id)
        else:
            print("Nothing to push — every task is already linked to ClickUp.")
        return

    list_id = args.list_id or "<LIST_ID>"
    print(f"DRY RUN - would create {len(pending)} task(s) in ClickUp list {list_id}:\n")
    for t in pending:
        p = _payload(t)
        print(f"- {p['name']}")
        for line in p["description"].splitlines():
            print(f"      {line}")
        print()
    if linked:
        print(f"({len(linked)} task(s) already linked to ClickUp - skipped; --force to include)")
    print("Re-run with:  --push --list-id <id>   (CLICKUP_TOKEN set)  to create them for real.")


if __name__ == "__main__":
    sys.exit(main())
