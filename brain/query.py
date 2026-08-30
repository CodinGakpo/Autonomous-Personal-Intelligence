"""brain/query.py - read the brain (the retrieval side; plain code, no LLM).

Answers the questions a person - or Hermes - asks of the graph:
    people                      everyone we know (name + one-line + top strengths)
    person <name>               one person's profile + the tasks assigned to them (via edges)
    who <term>                  people whose profile mentions a skill / word
    tasks [--assignee <name>]   action items, optionally for one person

Output is plain human-readable text, so a Hermes skill can run it and relay the result verbatim.

Usage:
    uv run python -m brain.query people
    uv run python -m brain.query person "Sai Prakash"
    uv run python -m brain.query who python
    uv run python -m brain.query tasks --assignee Pruthvik
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from brain import store
from brain.resolver import normalize


def _radar_top(data: dict[str, Any], n: int = 3) -> str:
    radar = data.get("radar") or {}
    scored = [(k, (v or {}).get("score", 0)) for k, v in radar.items() if isinstance(v, dict)]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{k.replace('_', ' ')} {s}" for k, s in scored[:n])


def cmd_people(conn: Any) -> str:
    people = store.all_of_type(conn, "person")
    if not people:
        return "The brain doesn't know any people yet. Ingest a résumé first."
    lines = [f"People the brain knows ({len(people)}):", ""]
    for p in people:
        d = p["data"]
        strengths = ", ".join((d.get("strengths") or [])[:4]) or "-"
        flag = "  (!) needs review" if p.get("needs_review") else ""
        lines.append(f"- {p['title']} - {d.get('headline') or d.get('seniority') or ''}{flag}")
        lines.append(f"    strengths: {strengths}")
        if _radar_top(d):
            lines.append(f"    radar: {_radar_top(d)}")
    return "\n".join(lines)


def cmd_person(conn: Any, name: str) -> str:
    target = normalize(name)
    match = None
    for p in store.all_of_type(conn, "person"):
        t = normalize(p.get("title"))
        if t and (t == target or target in t.split() or t.split()[0] == target.split()[0]):
            match = p
            break
    if not match:
        return f"No person matching '{name}'. Try: brain.query people"

    d = match["data"]
    lines = [f"{match['title']}", "=" * len(match["title"])]
    if match.get("summary"):
        lines.append(match["summary"])
    if d.get("seniority") or d.get("total_years_experience"):
        lines.append(f"seniority: {d.get('seniority') or '-'} | exp: {d.get('total_years_experience') or '-'} yrs")
    if d.get("skills"):
        lines.append("skills: " + ", ".join(d["skills"][:12]))
    if _radar_top(d, 6):
        lines.append("radar: " + _radar_top(d, 6))

    tasks = store.neighbors(conn, match["id"], "assigned_to", incoming=True)
    lines.append("")
    if tasks:
        lines.append(f"assigned tasks ({len(tasks)}):")
        for t in tasks:
            due = t["data"].get("due_date")
            lines.append(f"  - {t['title']}" + (f"  (due {due})" if due else ""))
    else:
        lines.append("assigned tasks: none")
    return "\n".join(lines)


def cmd_who(conn: Any, term: str) -> str:
    t = normalize(term)
    if not t:
        return "Give a term, e.g. brain.query who python"
    hits = []
    for p in store.all_of_type(conn, "person"):
        d = p["data"]
        haystack = " ".join(
            normalize(str(x))
            for x in [
                p.get("title"), d.get("summary"), d.get("headline"),
                " ".join(d.get("skills") or []), " ".join(d.get("strengths") or []),
                " ".join(d.get("domains") or []),
            ]
        )
        if t in haystack:
            skills = ", ".join(d.get("skills") or [])[:80]
            hits.append(f"- {p['title']} - {skills or d.get('headline') or ''}")
    if not hits:
        return f"No one in the brain mentions '{term}'."
    return f"People who mention '{term}' ({len(hits)}):\n" + "\n".join(hits)


def cmd_tasks(conn: Any, assignee: str | None) -> str:
    tasks = store.all_of_type(conn, "task")
    if assignee:
        a = normalize(assignee)
        tasks = [t for t in tasks if a in normalize(t["data"].get("assignee"))]
    if not tasks:
        who = f" for '{assignee}'" if assignee else ""
        return f"No tasks{who} in the brain yet."
    lines = [f"Tasks ({len(tasks)}):"]
    for t in tasks:
        d = t["data"]
        who = d.get("assignee") or "unassigned"
        due = f"  due {d['due_date']}" if d.get("due_date") else ""
        pri = f"  [{d['priority']}]" if d.get("priority") else ""
        flag = "  (!) review" if t.get("needs_review") else ""
        lines.append(f"  - {t['title']} - {who}{due}{pri}{flag}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask the brain about people and tasks.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("people", help="list everyone the brain knows")
    p_person = sub.add_parser("person", help="one person's profile + their tasks")
    p_person.add_argument("name")
    p_who = sub.add_parser("who", help="people whose profile mentions a term")
    p_who.add_argument("term")
    p_tasks = sub.add_parser("tasks", help="list action items")
    p_tasks.add_argument("--assignee", default=None)

    args = ap.parse_args()
    conn = store.connect()
    if args.cmd == "people":
        print(cmd_people(conn))
    elif args.cmd == "person":
        print(cmd_person(conn, args.name))
    elif args.cmd == "who":
        print(cmd_who(conn, args.term))
    elif args.cmd == "tasks":
        print(cmd_tasks(conn, args.assignee))


if __name__ == "__main__":
    sys.exit(main())
