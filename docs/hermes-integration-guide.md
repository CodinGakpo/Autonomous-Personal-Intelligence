# Deploying the Agent OS brain into Hermes

How to put what we've built so far — the two extractors and the resolver — onto a Hermes box and
wire them in. Written for **fenil's box (macOS, reachable over Tailscale)**.

## What we're deploying

| Piece | File (branch `planb-implementation`) | Needs an LLM? |
|---|---|---|
| Résumé extractor | `tools/resume/parser.py` | yes (the parse step) |
| Meeting extractor | `skills/meeting_to_task.py` | yes (the extract step) |
| Resolver (dedup) | `brain/resolver.py` (+ tests) | **no** — pure code |

All three are self-contained and tested. The extractors are contained "text in → JSON out" calls; the
resolver is deterministic.

---

## The one change that matters: the LLM engine

Our extractors currently shell out to **`claude -p`**. On fenil's box that's the wrong engine:

- Anthropic blocked third-party tools from Pro/Max subscriptions (2026-04-04), and the team runs
  **OpenRouter free models through Hermes** (`hermes -z`) to stay at $0.
- The box may not even have Claude Code installed.

So before anything runs on the box, swap the engine to Hermes's one-shot mode:

```
claude -p   (reads prompt on stdin)   →   hermes -z "<prompt>"   (prompt as arg, final text out)
```

This is the engine-agnostic seam we designed for. Concretely, `run_claude()` in both extractors becomes
a `run_llm()` that picks the engine from an env var, e.g.:

```python
ENGINE = os.environ.get("BRAIN_ENGINE", "claude")   # "claude" | "hermes"
# claude:  subprocess.run(["claude", "-p"], input=prompt, ...)
# hermes:  subprocess.run(["hermes", "-z", prompt], ...)
```

Then on the box you set `BRAIN_ENGINE=hermes` and nothing else changes. **Done** — implemented in
`brain/engine.py`; both extractors call `run_llm()`, which routes to `claude -p` or `hermes -z`.

> Note: `hermes -z` (one-shot) works on the box even though interactive `hermes chat` is currently broken
> by a streaming bug in the `:8899` proxy. Our pipeline only uses `-z`, so it's unaffected.

> Heads-up from the handover doc: OpenRouter free model names churn (several 404'd). Confirm the box's
> `~/.hermes/config.yaml` `model.default` is a live one (e.g. `meta-llama/llama-3.3-70b-instruct:free`)
> before relying on it.

---

## Path 1 — Quick deploy (scripts the box runs)

Get it running first, integrate deeper later.

1. **Get the code on the box** (over your Tailscale SSH):
   ```bash
   git clone <this-repo-url>
   cd agent-os && git checkout planb-implementation
   ```
2. **Python env + deps:**
   ```bash
   uv sync            # or: pip install pypdf python-docx
   ```
   (Images need nothing extra — Claude/Hermes vision handles them; if using `hermes -z`, confirm the
   configured model accepts images, else fall back to a vision-capable model for image résumés.)
3. **Set the engine:** `export BRAIN_ENGINE=hermes` (after the run_llm refactor).
4. **Run them standalone to prove it works:**
   ```bash
   python -m skills.meeting_to_task transcript.txt --date 2026-06-24
   python -m tools.resume.parser resume.pdf --role "Backend Engineer"
   python -m pytest tests/test_resolver.py -q
   ```
   If you get JSON out, the brain runs on the box.

---

## Path 2 — Native Hermes integration (the real goal)

Map our pieces onto how Hermes actually works (skills + scripts + MCP), so Hermes *orchestrates* them.

### a) Extractor prompts → a Hermes **skill**
Hermes is itself the LLM, so the cleanest form is: the extractor **prompt lives in `SKILL.md`** and Hermes
does the extraction directly (no nested LLM call). Create:
```
~/.hermes/skills/agent-os/meeting-to-task/
├── SKILL.md            ← the "transcript + summary → summary + task list JSON" contract
└── scripts/
    └── resolver.py     ← brain/resolver.py (the deterministic dedup step)
```
`SKILL.md` instructs Hermes: when a transcript arrives, produce the task JSON, then call
`scripts/resolver.py` to decide new/update/review for each task. Mirror this for a `resume-parser` skill
(its `scripts/` holds the pdf/docx text-extraction helper; Hermes does the parse).

### b) Deterministic code → scripts (or an MCP tool)
The resolver (and the future ClickUp-create step) are pure tools. Two ways Hermes uses them:
- **As scripts** the skill calls via the `terminal` tool (simplest, matches `placement-email-processor`).
- **As an MCP server** added to `~/.hermes/config.yaml` (`mcp_servers:`), so they're first-class Hermes
  tools. Better long-term; more setup. (Hermes supports remote HTTP MCP servers over Tailscale too.)

### c) Secrets → `~/.hermes/.env`
ClickUp token (when we add the create step) and any keys go here — **never** a shell session var.

### d) Triggers
A new meeting can drive the skill via Hermes's built-in listeners or a `~/.hermes/cron/` job. (Note the
handover warning: the `messaging` toolset name maps to **no tools** in cron context — use specific
toolset names like `terminal`, `file`, `skills`.)

---

## Gotchas (from the team's own notes)

- **macOS box** → normal shell. The `cmd /c` convention in the handover was for the *Windows* install; ignore it here.
- **Model churn** → verify `model.default` against `GET /api/v1/models` before trusting a free model name.
- **Don't** put an Ollama model as default on a small-VRAM box (it crashed deterministically on the Windows rig).
- **Secrets hygiene** → tokens live in `.env`, not committed, not echoed.

---

## What's NOT ready yet (so the guide doesn't oversell)

- **The ClickUp create step** — the resolver decides new/update, but nothing writes to ClickUp yet
  (the action seam, still pending the create-endpoint answer). Until then the pipeline stops at "decided."
- **The store** — the resolver resolves against a provided set of existing tasks; there's no persistent
  task store on the box yet.
- ~~The engine refactor~~ — **done** (`brain/engine.py` + `BRAIN_ENGINE=hermes`).

## Suggested order

1. Refactor the engine seam (`run_llm`, `BRAIN_ENGINE`).
2. Path 1 quick-deploy → prove the scripts run on the box with `hermes -z`.
3. Path 2a → wrap the meeting extractor as a Hermes skill.
4. Add the ClickUp-create step + token, then the store.
