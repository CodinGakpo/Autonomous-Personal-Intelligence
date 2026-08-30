# Agent OS — contributor & agent guide

Second brain for the company — an overlay on [Hermes Agent](https://github.com/nousresearch/hermes-agent).
Full design: [`docs/superpowers/specs/2026-06-07-agent-os-poc-design.md`](docs/superpowers/specs/2026-06-07-agent-os-poc-design.md).

This file is the single source of truth for **where files go**. Place every new file
(human- or agent-written) per the layout below. If a needed location isn't listed, add it
here first rather than placing files ad hoc.

## Repository layout

| Path | Holds |
|---|---|
| `pyproject.toml` | Project metadata, deps, tool config (ruff, mypy, import-linter) |
| `.python-version`, `uv.lock` | Pinned interpreter and locked deps (managed by `uv`) |
| `.pre-commit-config.yaml` | Local git-hook chain (the harness) |
| `.github/workflows/` | CI — runs the identical harness chain (`ci.yml`, job `harness`) |
| `package.json`, `.markdownlint.jsonc` | Dev-only Node tools + doc-lint config (jscpd, markdownlint) |
| `tools/` | Custom Hermes tools (e.g. `tools/fathom/`). MUST NOT write to ClickUp directly (ADR-0001) |
| `clickup/` | Typed ClickUp client. ALL ClickUp API access goes through here (ADR-0001) |
| `skills/` | Hermes skills (synthesis loop), agentskills.io-compatible |
| `console/` | Full-stack ops console: `console/backend` (FastAPI) + `console/frontend` (Vite/React/shadcn). Isolated from the overlay; reaches ClickUp only via `clickup/`; core packages MUST NOT import it (ADR-0002) |
| `scripts/` | Custom harness check scripts (`check_specs.py`, `check_inline_styles.py`) |
| `tests/` | `pytest` tests (e.g. architecture + spec-presence guards) |
| `features/` | BDD Gherkin `.feature` files + step defs. Drives the real interface only — never internals/DB |
| `docs/adr/` | Architecture Decision Records (enforced by `import-linter`) |
| `docs/prd/` | Product requirements (problem · goal · user journey) |
| `docs/design-system/` | UI rules (visual ADRs); scoped to any web UI |
| `docs/solutions/` | Documented solutions to past problems (bugs, best practices, workflow patterns), by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas |
| `docs/superpowers/` | Specs and implementation plans |
| `docs/team/` | Roster, assignments, kickoff runbook |
| `deploy/` | docker-compose for the Unraid server |
| `.claude/` | Committed team config (`settings.json`); `settings.local.json` is gitignored |

## Develop

Install `uv` first (one-time, per machine) — every command below depends on it:

```bash
# macOS
brew install uv
# or cross-platform
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version   # verify before continuing
```

Then:

```bash
uv sync                            # install deps
uv run pre-commit install          # enable the harness git hooks
uv run pre-commit run --all-files  # run the full harness locally
```

## Governance

Changes are gated locally (pre-commit) and on CI (`.github/workflows/ci.yml`) by the same
checks. Before writing code, read the relevant ADR (`docs/adr/`) and PRD (`docs/prd/`).
Architecture rules are encoded as `import-linter` contracts; a violation message points back
to the governing ADR. Workflow: one issue → one branch → one PR; no direct pushes to `main`.
