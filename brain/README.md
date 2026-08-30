# The Agent OS Brain (Plan B — the write path)

A small, engine-agnostic **entity graph**: typed nodes (people, tasks, meetings) and typed edges,
persisted in SQLite. It turns raw inputs (résumés, meeting transcripts) into structured, deduplicated,
linked memory.

```
input file ──▶ extractor (LLM) ──▶ resolver (deterministic) ──▶ store (idempotent upsert)
   résumé          contained            create / update /            SQLite: entities + edges
   transcript      prompt, JSON out     review decision
```

The **only** non-deterministic step is the extractor (a contained "document in → JSON out" LLM call).
Everything after it — dedup, keys, persistence — is plain, testable code. Idempotency comes from a
stable natural key + a lookup, never from the model returning identical text.

## Pieces

| File | Role | LLM? |
|---|---|---|
| `brain/store.py` | the entity graph — `entities` + `edges` tables, `upsert` / `add_edge` / query helpers | no |
| `brain/resolver.py` | deterministic dedup: candidate + existing → create / update / review | no |
| `brain/ingest.py` | the write path wired end-to-end (résumé→Person, meeting→Meeting+Tasks) | via extractors |
| `brain/query.py` | the read side: `people` / `person` / `who` / `tasks` (plain code, no LLM) | no |
| `brain/ask.py` | ask in natural language → answer **+ the node path it walked** (provenance) | yes |
| `brain/act.py` | the Act seam: push Tasks to ClickUp (dry-run by default), records `clickup_id` back | no |
| `brain/viz_server.py` + `viz.html` | a visual board (capability radars, fit ranking) with an "Ask the brain" box + résumé upload | no |
| `slack/client.py` + `brain/notify.py` | post brain events to Slack (dry-run until a bot token) | no |
| `slack/bot.py` | interactive `/brain` bot — ask the brain from Slack (Socket Mode) | via `ask` |
| `brain/ingest.py clickup` | pull ClickUp tasks into the brain (read); `clickup/client.py` gained `list_tasks` | no |
| `brain/engine.py` | **the one LLM seam** — routes a prompt to the configured engine | — |
| `tools/resume/parser.py` | résumé → profile JSON (6-axis radar) | yes |
| `skills/meeting_to_task.py` | transcript → clean summary + task list | yes |

## Run it

```bash
uv sync                                             # deps (pypdf, python-docx; sqlite3 is stdlib)
uv run python -m brain.ingest resume  brain/samples/resume_sai.txt
uv run python -m brain.ingest meeting brain/samples/meeting_standup.txt --date 2026-06-30
uv run python -m brain.query people
uv run python -m brain.query person "Sai Prakash"
uv run python -m brain.query who python
uv run python -m brain.query tasks --assignee Pruthvik

uv run python -m brain.ask "who is the best fit for the backend role, and why?"
uv run python -m brain.act                          # dry-run: the ClickUp tasks it would create
uv run python -m brain.ingest clickup               # pull ClickUp tasks in (needs .env — see INTEGRATIONS.md)
uv run python -m slack.bot                           # interactive /brain Slack bot (needs .env)
uv run uvicorn brain.viz_server:app --port 8080     # visual board + "Ask the brain" box at :8080
```

**Connecting ClickUp & Slack:** see [`../INTEGRATIONS.md`](../INTEGRATIONS.md). Everything is **dry-run
(no network) until you add tokens to `.env`** — push/pull ClickUp, Slack notifications, and the `/brain` bot.

The store lands at `brain/brain.db` (git-ignored — it's data, regenerate by ingesting).

## Engine-agnostic — run it on whatever you have

The brain never talks to a model directly; it calls `brain/engine.py::run_llm`, switched by one env var:

```
BRAIN_ENGINE=claude   (default)  ->  claude -p     (prompt on stdin)
BRAIN_ENGINE=hermes              ->  hermes -z     (prompt as arg, final text out)
```

So there is **nothing machine-specific to inherit**. Point `BRAIN_ENGINE` at whatever your box runs
(`hermes -z` on the team box, `claude -p` locally, or add another branch for a raw API key). Adding an
engine is a few lines in `engine.py`.

## Extend it (the natural next steps)

- **Live ClickUp push:** `brain/act.py` *is* the write-back seam — it builds each Task's ClickUp payload
  and, with `--push --list-id <id>` (+ `CLICKUP_TOKEN`), creates them and stores the `clickup_id` back so
  it never double-creates. It's dry-run by default; a real list id + token is all that's left to go live.
- **A review queue:** near-duplicate candidates are stored with `needs_review = 1`. Surface them (Slack /
  console) for a human to confirm-or-merge instead of leaving them flagged.
- **More node types / edges:** the store is generic (`type` + JSON `data`). Add `decision`, `skill`,
  `product` nodes and cross-links (Task↔commit, Decision↔code) — no schema change needed for new types.
- **Connectors (read):** wire Fathom (meeting ingest) and ClickUp (task read) as `tools/<source>/`
  adapters that feed `ingest.py`, replacing the manual file path.

## Design provenance

Plan B entity-graph, chosen for Agent OS. See `../system-overview.md` (the two-view PM/Dev doc) and the
ADRs under `../docs/`. This directory is the write path; the read/chatbot path is a separate phase.

---

## What's shareable vs. local (read before sending this anywhere)

**Everything in this repo is the shareable "soul" — safe to send.** It is engine-agnostic and holds no
secrets or machine paths:

- `brain/` (store, ingest, query, ask, act, notify, resolver, engine, viz_server + viz.html), `slack/`
  (client + `/brain` bot), `tools/resume/parser.py`, `skills/meeting_to_task.py`,
  `brain/hermes-skill/SKILL.md` (portable template), `brain/samples/`, `INTEGRATIONS.md`, `.env.example`
  (empty template), this README. (`act.py`/`ingest.py` use the in-repo `clickup/` client.)

**These are local / personal — do NOT send them (machine-specific or secret):**

| Item | Why it stays put |
|---|---|
| `brain/brain.db` | ingested data, not code — already git-ignored; regenerate by ingesting |
| `.env` (your real tokens) | ClickUp/Slack secrets — git-ignored; ship `.env.example` (empty template) instead |
| `~/.hermes/**` (e.g. `config.yaml`) | a contributor's Hermes config — **contains secrets** (bot tokens, provider wiring); lives outside this repo, never commit it |
| Meridian install + `~/.hermes/meridian-start.*` + the "Start Claude-Hermes" shortcut + `meridian.log` | one contributor's local Claude-Max bridge — **not part of the brain**; the engine seam means no one else needs it |
| the *installed* `~/.hermes/skills/brain/SKILL.md` | that copy has an absolute local path — ship `brain/hermes-skill/SKILL.md` (the placeholder template) instead |

Rule of thumb: **if it's committed to this repo, it's shareable. If it lives in `~/.hermes` or is a
`.db`, it's local.** The brain's design guarantees this — the only thing that ever varies per machine is
`BRAIN_ENGINE`.
