"""brain/ask.py — ask the brain a natural-language question (Navigate -> Think -> show the path).

This is the piece that turns the store from a catalogue into a *brain*. The write path put typed
nodes + edges into `brain.db`; this reads them back the way the plan calls for:

    Navigate  — build a compact, id-labelled catalogue of every node + relation (the "table of
                contents"). No embeddings: the model reasons over titles + one-line summaries to
                decide what's relevant. (Flat catalogue today; the same contract scales to a
                walk-the-tree-by-summary descent when the graph outgrows one prompt.)
    Think     — hand the catalogue + the question to the engine (`claude -p` / Hermes, via the seam)
                and get back a concise answer.
    Provenance — the model must cite the node ids it used, so every answer carries the path it walked.
                That path is the only thing we surface: explainability, per the plan's "show the path".

Pure contract in / out, engine-agnostic (rides `brain.engine.run_llm`). No network beyond the engine.

Usage:
    uv run python -m brain.ask "who is the best fit for the backend role, and why?"
    uv run python -m brain.ask "what still needs review?" --json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from brain import engine, store

SYSTEM = """You are the Agent OS brain. You answer questions by reasoning over a catalogue of known
nodes (people, tasks, meetings) and the typed relations between them. Use ONLY the information in the
catalogue — never invent people, tasks, dates, or facts. If the catalogue cannot answer the question,
say so plainly. Cite the exact node ids (the [bracketed] handles) you relied on.

Respond with ONLY a JSON object — no prose before or after, no markdown code fences:
{"answer": "<concise, direct answer>",
 "used_nodes": ["<id>", "..."],
 "reasoning": "<one or two sentences on how you reached it from those nodes>"}
"""


def _person_line(p: dict[str, Any]) -> str:
    d = p["data"]
    bits = [d.get("headline") or d.get("seniority") or ""]
    if d.get("target_role"):
        bits.append(f"target role: {d['target_role']}")
    radar = d.get("radar") or {}
    scored = [(k, (v or {}).get("score")) for k, v in radar.items() if isinstance(v, dict)]
    scored = [(k, s) for k, s in scored if isinstance(s, (int, float))]
    if scored:
        fit = round(sum(s for _, s in scored) / len(scored))
        top = ", ".join(f"{k.replace('_', ' ')} {s}" for k, s in sorted(scored, key=lambda kv: kv[1], reverse=True)[:3])
        bits.append(f"fit {fit}; strengths: {top}")
    if d.get("skills"):
        bits.append("skills: " + ", ".join(d["skills"][:8]))
    if p.get("needs_review"):
        bits.append("(!) needs review")
    return " | ".join(b for b in bits if b)


def _task_line(t: dict[str, Any]) -> str:
    d = t["data"]
    bits = [f"assignee: {d.get('assignee') or 'unassigned'}"]
    if d.get("due_date"):
        bits.append(f"due {d['due_date']}")
    if d.get("priority"):
        bits.append(f"priority {d['priority']}")
    if t.get("needs_review"):
        bits.append("(!) needs review")
    return " | ".join(bits)


def _meeting_line(m: dict[str, Any]) -> str:
    d = m["data"]
    bits = []
    if d.get("meeting_date"):
        bits.append(f"date {d['meeting_date']}")
    if m.get("summary"):
        bits.append(m["summary"])
    return " | ".join(bits)


def catalogue(conn: Any) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build the id-labelled catalogue text + an id->node index (for provenance lookups)."""
    index: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    renderers = {"person": _person_line, "task": _task_line, "meeting": _meeting_line}

    for type_ in ("person", "task", "meeting"):
        nodes = store.all_of_type(conn, type_)
        if not nodes:
            continue
        lines.append(f"{type_.upper()}S:")
        for n in nodes:
            index[n["id"]] = n
            detail = renderers[type_](n)
            lines.append(f"  [{n['id']}] {n['title']}" + (f" — {detail}" if detail else ""))
        lines.append("")

    # Relations, rendered legibly as  src --relation--> dst  (the cross-edges the walk follows).
    rels = conn.execute("SELECT src_id, dst_id, relation FROM edges").fetchall()
    if rels:
        lines.append("RELATIONS:")
        for r in rels:
            s, dst = index.get(r["src_id"]), index.get(r["dst_id"])
            if s and dst:
                lines.append(f"  {s['title']} --{r['relation']}--> {dst['title']}")
        lines.append("")

    return "\n".join(lines).strip(), index


def _parse_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the engine's reply, tolerating fences or stray prose."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start : end + 1])
        raise


def ask(conn: Any, question: str) -> dict[str, Any]:
    """Answer `question` over the brain, returning {answer, path, reasoning}.

    `path` is the provenance: the actual nodes the model cited (id + type + title), so the caller can
    show where the answer came from. Ids the model names but the store doesn't have are surfaced as
    unknown rather than hidden — an honesty signal, not a silent drop.
    """
    cat, index = catalogue(conn)
    if not index:
        return {"answer": "The brain is empty — ingest a résumé or a meeting first.", "path": [], "reasoning": ""}

    prompt = f"{SYSTEM}\n\n=== CATALOGUE ===\n{cat}\n\n=== QUESTION ===\n{question}\n"
    reply = engine.run_llm(prompt)
    parsed = _parse_json(reply)

    path = []
    for nid in parsed.get("used_nodes", []):
        node = index.get(nid)
        if node:
            path.append({"id": nid, "type": node["type"], "title": node["title"]})
        else:
            path.append({"id": nid, "type": "unknown", "title": "(id not in brain)"})

    return {
        "answer": parsed.get("answer", "").strip(),
        "path": path,
        "reasoning": (parsed.get("reasoning") or "").strip(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask the brain a natural-language question.")
    ap.add_argument("question", help="what you want to know")
    ap.add_argument("--json", action="store_true", help="emit the raw result as JSON")
    args = ap.parse_args()

    conn = store.connect()
    result = ask(conn, args.question)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(result["answer"])
    if result["path"]:
        print("\nSources (the path I walked):")
        for node in result["path"]:
            print(f"  - {node['type']}: {node['title']}")
    if result["reasoning"]:
        print(f"\nHow: {result['reasoning']}")


if __name__ == "__main__":
    sys.exit(main())
