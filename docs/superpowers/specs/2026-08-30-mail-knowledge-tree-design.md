# Mail knowledge-tree — design

## Context

The brain currently has a live implementation ("Plan B"): a flat entity graph in
`brain/store.py` (SQLite `entities` + `edges`), built for résumés, meeting transcripts, and
ClickUp tasks. Separately, `docs/proposals/brain-architecture/plan-a-knowledge-tree/` (and the
nested `05-agent-os/brain/*.md` copies) describe a different, unimplemented design — "Plan A": a
hierarchical tree of nodes, each with an LLM-written `summary` (a routing digest) and a `body`
(full content), where an AI navigates by reading sibling summaries instead of doing vector search.

This project applies Plan A's node shape (summary/body, parent→child, LLM-driven placement) to
email, and persists it inside the existing Plan B storage (`brain/store.py`'s `entities`/`edges`
tables) rather than standing up a separate store — reusing the store, resolver, and upsert
machinery already built and tested, while modeling mail as a small tree via typed edges.

The trigger: verified Hermes can already read mail via a proven IMAP helper
(`~/.hermes/skills/automation/placement-email-processor/scripts/emailtool.py`). The ask is to turn
that raw unread-mail feed into a standing, browsable knowledge structure — so a student in their
final year, or later, other users, can build up sensemaking around ongoing email threads (e.g.
placement rounds: interview → PPT → OA → result) rather than re-reading a scattered inbox. A later
phase (not part of this spec) will add asking questions against this tree.

## Node model (within `brain/store.py`)

Three new `entities.type` values, connected by two new `edges.relation` values:

```
mail_category ──contains──▶ mail_topic ──contains──▶ mail_thread
```

- **`mail_category`** — top-level branch. Seeded set (e.g. Placements, Banking, Academics, Job
  Hunt), configurable in `brain/mail_config.json`. The LLM may create a new category when an email
  doesn't fit any existing one well enough.
- **`mail_topic`** — sub-branch under a category (e.g. one company during placement season, one
  bank account, one course).
- **`mail_thread`** — the node holding actual content: one email, or several emails merged
  together by the LLM into one coherent picture (e.g. a company's interview mail + PPT mail + OA
  mail folded into one thread node instead of three disconnected ones).

Every node uses the existing `entities` columns:
- `id` — deterministic, source-keyed: `mail:cat:<slug>`, `mail:topic:<category-slug>:<topic-slug>`,
  `mail:thread:<uuid>`. Stable ids make re-runs idempotent (same lookup-and-upsert pattern the
  brain already uses elsewhere).
- `summary` — LLM-written routing digest (what's here, what questions it answers).
- `data` (JSON) — for a thread node: accumulated structured `body` (e.g. "Interview: ...\nPPT:
  ...\nOA: ..."), plus the list of source email UIDs/Message-IDs it was built from, plus any
  attachment findings (see below).
- `source` — `mail:<uid>` (or the list of uids once merged).

## Pipeline

```
emailtool.py list ─→ attachment handling ─→ LLM classify ─→ LLM merge/place ─→ store upsert ─→ mark-read
   (existing,           (local, mostly         (category +      (existing thread     (entities +
    proven working)       no-LLM)                topic)           vs new thread)       edges)
```

1. **Fetch** — `emailtool.py list` (IMAP) returns unread emails: from/subject/body + attachments
   already saved to disk as files.

2. **Attachment handling** — local, mostly no LLM cost, and pluggable per category via
   `mail_config.json` (built out now for the placement use case; other categories can add their
   own strategy later without touching the core pipeline):
   - **Excel** (`.xlsx`/`.xls`): parsed with `openpyxl`/`pandas`, entirely locally. Find the column
     that looks like a student-ID column, locate the row matching the student's own ID (from
     `mail_config.json`), extract just that row + the header row. If the ID isn't found, note "no
     matching row" — nothing further sent to the LLM for that sheet.
   - **PDF**: text extracted locally with `pypdf`, hard-capped at ~4000 characters. If it reads
     like a job description, a second small LLM call compares it against the student's parsed
     resume profile (reusing `tools/resume/parser.py`'s existing résumé→JSON) for a match/gap
     note.
   - Anything else: recorded as "attachment not parsed", no extraction attempted.
   - This local pre-filter + hard char cap is the guard against a single large attachment burning
     through a free-tier API key on one email.

3. **Classify** (LLM call) — given the email content (+ any extracted attachment slice) and the
   existing category summaries, decide: which category (existing, or new if nothing fits), and
   within it, which topic (existing, or new).

4. **Merge/place** (LLM call) — given the topic's existing thread summaries, decide: merge into an
   existing thread (regenerate that thread's `body` and `summary` from old body + new email,
   producing a coherent combined picture — not a raw concatenation) or create a new thread node.

5. **Write** — `store.upsert` for any new/changed category, topic, and thread entities;
   `store.add_edge` for the two `contains` relations.

6. **Mark read** — only after a successful write, `emailtool.py mark-read <uid>`, so a crash
   mid-run never silently drops an email.

## LLM provider

OpenRouter, via `.env`:
```
OPENROUTER_API_KEYS=key1,key2,key3,...   # comma-separated free-tier keys
OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct:free
```
An 8B free-tier model is deliberately chosen over a larger one — classify/merge/summarize is a
bounded, structured-JSON-output task, and the free-tier keys need to last across many small calls
over a long period, not get drained by an oversized model. A thin call wrapper tries the current
key; on a 401/429/quota-style error it rotates to the next key in the list and retries — logged,
not silent.

## Running it

Plain Python script (no Hermes involvement, per explicit preference for "solid code" over an
LLM-driven skill): `brain/mail_ingest.py` (or `brain/ingest.py mail`, following the existing
`brain/ingest.py resume|meeting|clickup` subcommand pattern). Runs two ways:
- **Cron** — 3–4x/day, scheduled via Windows Task Scheduler (matches the box this runs on).
- **On-demand** — the same script run manually now; a UI trigger button is a later-phase concern.

## Config

`brain/mail_config.json` (new, git-ignored if it ever holds anything personal — the placement use
case's student ID isn't secret, but keep the file itself out of the "shareable soul" if it later
gains anything personal):
```json
{
  "student_id": "<the student's own ID, matched against Excel selection sheets>",
  "resume_path": "path/to/resume.pdf",
  "seeded_categories": ["Placements", "Banking", "Academics", "Job Hunt"]
}
```

## Explicitly out of scope for this spec

- **Retrieval / asking questions against the tree** — later phase, per the user.
- **The separate Gmail-OAuth mail subsystem** (`~/.hermes/mail/`) — no source code for it exists
  in this checkout; IMAP via `emailtool.py` is the only mail source this pipeline uses.
- **Plan B's own retrieval/resolver semantics are unaffected** — this only adds new entity types
  and edge relations; existing résumé/meeting/task ingestion is untouched.
- **Multi-user / other categories' attachment strategies** — only the placement (student ID +
  resume-vs-JD) strategy is built now; the config is shaped to add more later.
