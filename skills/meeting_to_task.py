r"""Meeting extractor — transcript (+ summary) in, structured JSON out.

This is the Plan B write-path EXTRACTOR: a contained LLM step that turns one meeting into a clean
summary plus a flat list of action items (each tagged with its assignee). It produces task
*candidates* — it does NOT create ClickUp tasks. Creation + idempotency is a separate downstream
step (the resolver + clickup client), per ADR-0001 and the Plan B split:
    extractor = fuzzy LLM (this file)   |   resolver = deterministic code (later)

Engine: `claude -p` for now. The same prompt drops into Hermes later — only run_claude swaps.

Usage:
    python -m skills.meeting_to_task <transcript.txt> [--summary summary.txt] \
        [--date 2026-06-23] [--out out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brain.engine import run_llm

# Engine-agnostic extraction contract. {{MEETING_DATE}} / {{MEETING_SUMMARY}} / {{RAW_TRANSCRIPT}}
# are filled by str.replace (NOT .format — the prompt is full of literal JSON braces).
PROMPT = r'''You are a meeting-extraction engine for a team operations system. You receive ONE meeting's
SUMMARY and RAW TRANSCRIPT and return a single, strictly-valid JSON object: a clean summary of the
meeting plus a FLAT list of concrete action items (tasks), each tagged with who it is for. Your
output is consumed by software, not a human — output JSON only.

==================== HARD RULES ====================
1. Output ONE JSON object and NOTHING else — no markdown, no code fences, no text before/after.
2. Use ONLY information present in the summary/transcript. Never invent tasks, people, dates, or details.
3. If a field is absent, set it to null (or [] for lists) AND add its name to "missing_fields". Do not guess.
4. A "task" is a CONCRETE action item someone committed to or was asked to do — a real next step with an
   owner or clear outcome. Do NOT turn general discussion, opinions, or status updates into tasks.
5. Every task MUST have a "name" (a short imperative action, e.g. "Fix the login bug"). If you cannot
   state a concrete action, do not emit a task.
6. "assignee" = the person responsible, exactly as named in the meeting (free text). null if the task was
   raised with no clear owner.
7. "priority": only "low" | "medium" | "high" | "urgent", and ONLY if the discussion clearly implies it
   ("this is urgent", "blocker", "ASAP", "low priority"). Otherwise null.
8. "due_date": ISO "YYYY-MM-DD" ONLY when a concrete date is stated, OR a relative date ("by Friday",
   "tomorrow") that you can resolve using MEETING DATE below. If it is relative and MEETING DATE is
   blank, leave due_date null and note the phrase in "flags". Never invent a deadline.
9. "required_skills": list a skill ONLY if the meeting explicitly says the task needs it. Usually [].
10. Lower "parse_confidence" (0–1) when the transcript is messy, partial, or you had to infer a lot. Put
    anything ambiguous (unclear owner, vague action, conflicting statements) in "flags".

==================== OUTPUT SCHEMA (fill every key; null/[] when unknown) ====================
{
  "schema_version": "1.0",
  "parse_confidence": 0.0,
  "meeting_title": null,
  "meeting_date": null,
  "participants": [],
  "summary": null,
  "tasks": [
    {
      "name": null,
      "description": null,
      "assignee": null,
      "priority": null,
      "due_date": null,
      "required_skills": []
    }
  ],
  "missing_fields": [],
  "flags": []
}

Field notes:
- "summary": a clean 3–6 sentence recap of what the meeting was about and what was decided. Neutral, factual.
- "meeting_title" / "meeting_date" / "participants": fill from the summary/transcript if present, else null/[].
- "tasks": a FLAT list across the whole meeting; each task carries its own assignee. Most-important first.
- "description": one line of extra context for the task if the transcript gives it; else null.

==================== INPUT ====================
MEETING DATE (optional, may be blank): {{MEETING_DATE}}
Use it to resolve relative due dates. If blank, do not resolve relative dates.

MEETING SUMMARY (may be blank):
"""
{{MEETING_SUMMARY}}
"""

RAW TRANSCRIPT:
"""
{{RAW_TRANSCRIPT}}
"""

Return the JSON object now.'''


def _strip_fences(text: str) -> str:
    """Defensively remove ```json ... ``` fences if the model adds them."""
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def extract_meeting(transcript: str, summary: str = "", meeting_date: str = "") -> dict:
    """Run the extractor: meeting text in, {summary, tasks[]} JSON out. Does NOT persist anything."""
    if not transcript.strip() and not summary.strip():
        raise SystemExit("Need a transcript or a summary to extract from (both were empty).")
    prompt = (
        PROMPT.replace("{{MEETING_DATE}}", meeting_date)
        .replace("{{MEETING_SUMMARY}}", summary)
        .replace("{{RAW_TRANSCRIPT}}", transcript)
    )
    raw = _strip_fences(run_llm(prompt))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Engine did not return valid JSON: {exc}\n--- raw output ---\n{raw}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract a clean summary + task list from a meeting via claude -p.")
    ap.add_argument("transcript", type=Path, help="raw transcript file (.txt/.md)")
    ap.add_argument("--summary", type=Path, help="optional meeting-summary file")
    ap.add_argument("--date", default="", help="meeting date (YYYY-MM-DD) to resolve relative due dates")
    ap.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = ap.parse_args()

    if not args.transcript.exists():
        raise SystemExit(f"File not found: {args.transcript}")
    transcript = args.transcript.read_text(encoding="utf-8", errors="replace")
    summary = args.summary.read_text(encoding="utf-8", errors="replace") if args.summary else ""

    result = extract_meeting(transcript, summary, args.date)
    payload = json.dumps(result, indent=2, ensure_ascii=False)

    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    sys.exit(main())
