---
name: brain
description: The company's second-brain knowledge graph. Use it to answer questions about team members and their skills/experience, and about action items/tasks — or to ingest a résumé or meeting transcript. Trigger when the user asks things like "who do we know / who can do X / what is <person> good at / what is <person> working on / what are the open tasks / what does <person> know", or asks to add/ingest a résumé or a meeting.
metadata:
  hermes:
    tags: [brain, people, tasks, knowledge-graph, agent-os]
---

# Agent OS Brain

A local knowledge graph (SQLite) of **people** (from résumés — each with a 6-axis capability radar) and
**tasks** (from meeting transcripts — deduped, and linked to the person they're assigned to). It is
driven by small Python commands in the `agent-os` project. The heavy reading is done by an LLM *inside*
those commands, so you simply run the command with the `terminal` tool and relay the result — you do not
read the documents yourself.

> **Install (per machine — do this once):**
> 1. Copy this file to `~/.hermes/skills/brain/SKILL.md`.
> 2. Replace `<AGENT_OS_DIR>` below with the absolute path to your `agent-os` checkout.
> 3. Make sure the `skills` toolset is enabled for the surface you use (e.g. `hermes -t terminal,file,todo,skills`).
> 4. Make sure `brain/engine.py`'s `BRAIN_ENGINE` points at an engine your box has (`hermes` or `claude`).

## How to use it

Every command runs in the project directory: **`<AGENT_OS_DIR>`**.
`cd` there first, then run the command via the `terminal` tool. Use `uv run` (it has the dependencies).

### Answer questions (read — safe, fast)
- Everyone we know: `uv run python -m brain.query people`
- One person + their assigned tasks: `uv run python -m brain.query person "Sai Prakash"`
- Who knows a skill/topic: `uv run python -m brain.query who python`
- Tasks (optionally for one person): `uv run python -m brain.query tasks --assignee Pruthvik`

### Add to the brain (write — adds to the local database)
- Ingest a résumé (pdf/docx/txt/image): `uv run python -m brain.ingest resume <path> [--role "Backend Engineer"]`
- Ingest a meeting transcript: `uv run python -m brain.ingest meeting <path> [--date YYYY-MM-DD]`

## Rules
- Run the command, then relay its output as a clear, friendly summary. The output is already
  human-readable — **do not invent data beyond it**.
- If the brain doesn't cover what was asked, say so plainly and suggest ingesting the relevant résumé or
  meeting first. Never guess a person's skills or a task's owner.
- The read commands are safe. The write commands only add to the local brain database.
