<div align="center">

# Agent OS

**An AI co-pilot overlay on [Hermes Agent](https://github.com/nousresearch/hermes-agent) — the operational second brain for your organisation.**

[![CI](https://img.shields.io/github/actions/workflow/status/your-org/agent-os/ci.yml?branch=main&label=harness&style=flat-square)](https://github.com/your-org/agent-os/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org/)
[![uv](https://img.shields.io/badge/pkg--manager-uv-purple?style=flat-square)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

*A meeting concludes → the transcript flows in → the agent synthesises → a ClickUp task is created. Automatically.*

</div>

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Development Workflow](#development-workflow)
- [Code Tour](#code-tour)
- [CI / Harness Reference](#ci--harness-reference)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Governance](#governance)
- [Roadmap](#roadmap)
- [Team](#team)

---

## Overview

Agent OS eliminates the gap between **conversation and action**. When a Fathom meeting ends, nothing happens automatically — someone must write it up, create tasks, and assign owners. Agent OS handles that entirely in the background.

**North-star metric:** team throughput per person at constant quality — velocity increases, rework remains flat.

| Track | Scope | Status |
|---|---|---|
| **Track A** — Co-pilot loop | Fathom transcript → Hermes synthesis → ClickUp task → Slack confirmation | Planning |
| **Track B** — Engineering harness | ADR / PRD / BDD / type / lint / architecture gates on every PR | Active |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                          TRACK A  LOOP                          │
│                                                                  │
│  Slack (Fenil)        Fathom API        Hermes        ClickUp   │
│       │                   │               │               │      │
│  "Summarise meeting" ─►   │               │               │      │
│       │            fetch_transcript()     │               │      │
│       │                   │──────────────►│               │      │
│       │                   │   Transcript  │               │      │
│       │                   │◄──────────────│               │      │
│       │                   │  meeting_to_task() skill      │      │
│       │                   │               │──────────────►│      │
│       │                   │               │  create_task()│      │
│       │                   │               │◄──────────────│      │
│       │                   │               │  TaskRef      │      │
│  "✅ Task #1234 created" ◄─────────────────│               │      │
└─────────────────────────────────────────────────────────────────┘
```

**Architectural rule:** `tools/fathom` is **read-only**. `clickup/client` is the sole **write path**. This boundary is enforced by `import-linter` — any violation fails CI. See [ADR-0001](docs/adr/0001-module-boundaries.md).

---

## Architecture

### Component Boundaries

```
Slack (Hermes gateway)   ──────────────────────────────────────┐
                                                                │
Fathom API               tools/fathom/client.py                │
     │                        │  fetch_transcript()            │
     └────────────────────────►  returns Transcript            │
                               │  (read-only; no ClickUp)      │
                               ▼                               │
                         Hermes agent loop ─────────────────── ►
                               │                               │
                         skills/meeting_to_task.py             │
                               │  meeting_to_task()            │
                               ▼                               │
                         clickup/client.py                     │
                               │  create_task()                │
                               │  add_comment()                │
                               ▼                               │
                         ClickUp API  ◄─────────────────────────┘
```

### Why an Overlay Repository (not a Hermes Fork)?

Hermes is MIT-licensed and under active development (~11k commits). Forking would mean absorbing every upstream update as a merge conflict. Instead, we contribute only what is ours:

```
overlay/
    ├── tools/      ← custom Hermes tools
    ├── skills/     ← synthesis skills (agentskills.io-compatible)
    ├── clickup/    ← typed ClickUp client
    ├── docs/adr/   ← architecture decisions
    └── deploy/     ← Unraid docker-compose
```

Hermes is pulled as a dependency. Its core is never modified.

---

## Project Structure

```
agent-os/
│
├── clickup/                        # Typed ClickUp client — all writes go here
│   ├── __init__.py
│   └── client.py                   # ClickUpClient + TaskRef dataclass
│
├── tools/
│   └── fathom/                     # Fathom tool — read-only (ADR-0001)
│       ├── __init__.py
│       └── client.py               # fetch_transcript() → Transcript
│
├── skills/                         # Hermes synthesis skills
│   ├── __init__.py
│   └── meeting_to_task.py          # transcript → structured minutes → ClickUp task
│
├── tests/                          # pytest suite
│   ├── test_architecture.py        # architecture contract guard
│   └── test_specs.py               # spec-presence guard
│
├── features/                       # BDD Gherkin specs
│   ├── meeting_to_task.feature     # user-facing behaviour
│   ├── environment.py
│   └── steps/
│       └── meeting_to_task_steps.py
│
├── scripts/                        # Custom harness check scripts
│   ├── check_specs.py              # ADR/PRD required-section linting
│   └── check_inline_styles.py      # Design-system: no inline styles in UI files
│
├── docs/
│   ├── adr/                        # Architecture Decision Records
│   │   ├── 0000-template.md
│   │   └── 0001-module-boundaries.md
│   ├── prd/                        # Product requirements
│   ├── design-system/              # UI rules (visual ADRs)
│   ├── solutions/                  # Documented fixes with YAML front-matter
│   ├── superpowers/
│   │   ├── plans/                  # Track A & Track B implementation plans
│   │   └── specs/                  # POC design spec
│   └── team/                       # Roster, assignments, kickoff runbook
│
├── deploy/                         # Docker Compose for Unraid server
│
├── pyproject.toml                  # Project config + ruff / mypy / import-linter
├── .pre-commit-config.yaml         # Local git-hook chain (mirrors CI)
├── .github/workflows/ci.yml        # CI harness
├── .python-version                 # Pinned interpreter (read by uv)
├── uv.lock                         # Locked dependency graph
├── AGENTS.md                       # File-placement contract for humans and agents
└── .claude/settings.json           # Committed team config for Claude Code
```

---

## Quick Start

### Prerequisites

**uv** (Python package manager) is required. Install it once:

```bash
# macOS
brew install uv

# Linux / Windows
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify the installation before proceeding
uv --version
```

> **Troubleshooting:** If `uv` is not found after installation, refer to
> [`docs/solutions/build-errors/uv-command-not-found-uv-sync-2026-06-08.md`](docs/solutions/build-errors/uv-command-not-found-uv-sync-2026-06-08.md)

**Node.js v18+** is also required for `npx jscpd` and `markdownlint-cli2` (Track B, tasks 10+):

```bash
node --version   # must be v18 or later
```

### Clone and Set Up

```bash
git clone https://github.com/<org>/agent-os.git
cd agent-os

# Install all Python dependencies (creates .venv automatically from uv.lock)
uv sync

# Enable the local git-hook harness
uv run pre-commit install
```

### Verify the Environment

```bash
uv run pre-commit run --all-files
```

Expected output — all hooks pass:

```
ruff format..............................................................Passed
ruff lint................................................................Passed
```

Resolve any failure before writing code. A green harness is the prerequisite for all development.

### Run the Ops Console (full-stack web app)

The team-facing web app lives in [`console/`](console/) (FastAPI + React/shadcn + Postgres).
Start it **with Docker** (one command, includes Postgres) or **without Docker** (run each piece
manually) — both paths are documented in [`console/README.md`](console/README.md):

```bash
# With Docker (recommended)
cd console/deploy && docker compose up --build     # frontend :8080 · backend :8000 · db
```

Login with the seeded admin `admin@agent-os.local` / `changeme`.

---

## Development Workflow

### The Golden Rule

```
one issue  →  one branch  →  one PR  →  Usman reviews & merges
```

Direct pushes to `main` are not permitted. Branch protection requires a passing `CI / harness` check before any merge is allowed.

### Step-by-Step

```bash
# 1. Pick up your task from docs/team/assignments.md
# 2. Create a branch using the convention: name/task-number-description
git checkout -b yogesh/task-14-readme-verification

# 3. Make your changes

# 4. Run the full harness locally before pushing — all checks must pass
uv run pre-commit run --all-files

# 5. Run the test suite
uv run pytest -v

# 6. Commit with a descriptive message
git add .
git commit -m "docs: add README and final verification (task 14)"

# 7. Push and open a pull request
git push -u origin HEAD
gh pr create --fill

# 8. CI must pass. Usman reviews. Merge.
```

### Daily Standup Format (Slack, ~10 minutes)

Post in the team channel using this format:

```
Task #14 — PR: https://github.com/…/pull/42
Done: Added README with all sections; quick-start verified on a clean machine
Blocker: None
```

---

## Code Tour

### `clickup/client.py` — Typed ClickUp Client

All ClickUp API access must go through this module. No direct HTTP calls are permitted elsewhere in the codebase.

```python
"""Typed ClickUp client. All ClickUp API access MUST go through this module (ADR-0001)."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRef:
    id: str
    url: str


class ClickUpClient:
    """Stub. Real HTTP wiring is implemented in Track A (Plan 2)."""

    def create_task(self, list_id: str, name: str, description: str) -> TaskRef:
        raise NotImplementedError("Implemented in Track A")

    def add_comment(self, task_id: str, text: str) -> None:
        raise NotImplementedError("Implemented in Track A")
```

### `tools/fathom/client.py` — Fathom Transcript Fetcher

Returns data only. Must not import `clickup` or write to ClickUp under any circumstances. This rule is enforced by `import-linter`.

```python
"""Fathom tool. MUST NOT import clickup or write to ClickUp directly (ADR-0001).

Returns transcript data; the agent is responsible for acting on it.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    meeting_id: str
    text: str


def fetch_transcript(meeting_id: str) -> Transcript:
    """Stub. Real Fathom API wiring is implemented in Track A (Plan 2)."""
    raise NotImplementedError("Implemented in Track A")
```

### `skills/meeting_to_task.py` — Synthesis Skill

The bridge between transcript and task. Uses the typed ClickUp client exclusively — never raw HTTP.

```python
"""Synthesis skill: transcript → structured minutes + task payload.

Persists via the typed ClickUp client, never raw HTTP (ADR-0001).
"""

from __future__ import annotations
from clickup.client import ClickUpClient, TaskRef


def meeting_to_task(client: ClickUpClient, list_id: str, minutes: str) -> TaskRef:
    """Stub. Real synthesis is implemented in Track A (Plan 2)."""
    raise NotImplementedError("Implemented in Track A")
```

### `pyproject.toml` — Centralised Tool Configuration

```toml
[project]
name = "agent-os"
version = "0.0.0"
description = "Agent OS — second brain for the company (overlay on Hermes Agent)"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = [
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "behave>=1.2.6",
    "pre-commit>=3.8",
    "pytest>=8.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["tools", "clickup", "skills", "scripts"]

[tool.importlinter]
root_packages = ["tools", "clickup", "skills"]
```

### `.pre-commit-config.yaml` — Git Hook Chain

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format --check .
        language: system
        pass_filenames: false
      - id: ruff-lint
        name: ruff lint
        entry: uv run ruff check .
        language: system
        pass_filenames: false
```

> Subsequent tasks append hooks for `mypy`, `lint-imports`, `behave`, `check_specs.py`, `jscpd`, and `markdownlint`.

### `.github/workflows/ci.yml` — CI Harness

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  harness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install deps
        run: uv sync
      - name: Ruff format
        run: uv run ruff format --check .
      - name: Ruff lint
        run: uv run ruff check .
      # Tasks 4–11 append further steps here (see plan comments)
```

The job is named `harness` so GitHub branch protection can require `CI / harness` to pass before any merge.

---

## CI / Harness Reference

Every check runs identically in local pre-commit hooks and in CI. Any check can be run in isolation:

```bash
# Formatting
uv run ruff format --check .

# Linting (E, F, I, UP, B rules)
uv run ruff check .

# Type checking (strict mypy — covers tools/, clickup/, skills/, scripts/)
uv run mypy

# Architecture contracts (ADR-0001 boundary enforcement)
uv run lint-imports

# Unit / integration tests
uv run pytest -v

# BDD acceptance tests
uv run behave

# Spec-presence and required-section linting
uv run python scripts/check_specs.py

# Design-system: forbid inline styles in UI files
uv run python scripts/check_inline_styles.py

# Markdown lint (requires Node.js)
npx markdownlint-cli2 "**/*.md"

# Code duplication check (requires Node.js)
npx jscpd .
```

### Harness Build-Up by Task

| Task | Check Added | Command |
|---|---|---|
| 3 | Ruff format + lint | `uv run ruff format --check . && uv run ruff check .` |
| 4 | Mypy strict | `uv run mypy` |
| 5 | Import-linter (ADR-0001) | `uv run lint-imports` |
| 8 | Spec presence + pytest | `uv run python scripts/check_specs.py && uv run pytest` |
| 9 | BDD | `uv run behave` |
| 10 | Duplication + markdown | `npx jscpd . && npx markdownlint-cli2 "**/*.md"` |
| 11 | Inline styles | `uv run python scripts/check_inline_styles.py` |
| 12 | Pre-commit hooks wired | `uv run pre-commit run --all-files` |
| 13 | CI workflow complete | Push to any PR branch |

**Definition of Done (Plan 1):**

```bash
# All three must be green on main before Plan 2 begins
uv run pre-commit run --all-files   # all hooks pass
uv run pytest -v                    # all tests pass

# Smoke test: a deliberately ADR-violating PR must be rejected
# (import-linter fires on a tools/ file that imports clickup directly)
```

---

## Configuration

### `.claude/settings.json` — Team-Shared Claude Code Config

Committed to the repository so every developer and agent inherits identical permissions:

```json
{
  "permissions": {
    "allow": [
      "Read(//Users/*/.claude/plugins/**)",
      "Bash(claude plugin *)",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:hermes-agent.nousresearch.com)",
      "Bash(*)",
      "Bash(git config *)"
    ]
  }
}
```

> Personal overrides belong in `.claude/settings.local.json`, which is gitignored.

### Environment Variables

```bash
cp .env.example .env
# Open .env and populate the values for your environment
```

```ini
# .env.example
CLICKUP_API_KEY=your_clickup_api_key_here
FATHOM_API_KEY=your_fathom_api_key_here
HERMES_SLACK_TOKEN=your_slack_bot_token_here
CLICKUP_LIST_ID=your_default_list_id_here
```

> **Never commit `.env`** — it is explicitly listed in `.gitignore`.

---

## Testing

### Run All Tests

```bash
uv run pytest -v
```

### Run BDD Acceptance Tests

```bash
uv run behave
```

```gherkin
# features/meeting_to_task.feature
Feature: Meeting to task
  As Fenil
  I want to point the co-pilot at a Fathom meeting
  So that action items are automatically created in ClickUp

  Scenario: Happy path
    Given a Fathom meeting transcript is available
    When I ask the agent to summarise the meeting in Slack
    Then a ClickUp task is created with the minutes in the description
    And the agent confirms the task URL in Slack
```

### Run Type Checks

```bash
# Strict mypy across all source packages
uv run mypy

# Check a single file
uv run mypy skills/meeting_to_task.py
```

### Run Architecture Checks

```bash
uv run lint-imports

# Output when ADR-0001 is respected:
# All contracts ok.

# Output when violated (e.g. tools/fathom imports clickup):
# ✗ tools-must-not-import-clickup
#   tools.fathom.client imports clickup.client
#   (See docs/adr/0001-module-boundaries.md)
```

---

## Deployment

The production target is an **Unraid server**. Deployment configuration lives in `deploy/` (Docker Compose).

```
deploy/
└── docker-compose.yml   # Hermes + agent-os overlay on Unraid
```

**Deployment is owned by Usman.** Do not deploy to production without his explicit sign-off.

```bash
# On the Unraid server (Usman only)
docker compose -f deploy/docker-compose.yml up -d

# View logs
docker compose -f deploy/docker-compose.yml logs -f hermes
```

---

## Governance

Before writing or modifying any code, verify two things:

1. **Is there an ADR that covers this area?** → `docs/adr/`
2. **Is there a PRD that motivates this work?** → `docs/prd/`

If neither exists, write them first. Code without supporting specifications is not eligible for merge.

```
docs/adr/
├── 0000-template.md              ← Copy for every new ADR
└── 0001-module-boundaries.md     ← The boundary rule (tools must not write to ClickUp directly)

docs/prd/
├── 0000-template.md              ← Copy for every new PRD
└── poc-meeting-to-task.md        ← The POC user journey
```

Architecture rules are encoded as `import-linter` contracts. Violation error messages reference the relevant ADR directly, making the governance self-documenting.

---

## Roadmap

> Phase 0 (this repository) is the proof of concept — one person, one loop, one list.

| Phase | Feature |
|---|---|
| **0** | Track A loop + Track B harness (current) |
| **1** | Multi-instance role agents, CEO orchestrator |
| **2** | Performance dashboards, gamification, career path metrics |
| **3** | Bootstrap / onboarding wizard, daily check-ins |
| **4** | Skill intelligence engine, Google Workspace integrations |

Full roadmap context: [`docs/superpowers/specs/2026-06-07-agent-os-poc-design.md`](docs/superpowers/specs/2026-06-07-agent-os-poc-design.md)

---

## Team

| Person | Role | Track B Responsibility |
|---|---|---|
| **Usman** | Team Lead & DevOps | Tasks 1, 2, 3, 12, 13 — owns the full harness chain |
| **Manikandan K.B** | Full-stack & Slack Workflows | Task 5 (import-linter), Task 7 (PRD template) |
| **Hirak Parekh** | ML & Research Integration | Task 9 (BDD) — intern until 6 Jul |
| **Sajal Mondal** | Java / Spring / Typed Systems | Task 4 (mypy) |
| **Pruthvik J.** | Systems Design & Implementation | Task 6 (ADR template), Task 11 (design-system stub) |
| **Ayush Kumar** | Developer | Tasks 8, 10 (paired with Pruthvik) |
| **Sudeep C N** | Developer (Google Meet Recorder) | Task 9 (BDD, paired with Hirak) |
| **Yogesh K K** | Documentation & Verification | **Task 14 — this README and final green-build verification** |

**Product Owner:** Fenil Parekh &nbsp;·&nbsp; **Tech Lead / DevOps:** Usman

---

## Quick Links

| Resource | Location |
|---|---|
| POC design spec | [`docs/superpowers/specs/2026-06-07-agent-os-poc-design.md`](docs/superpowers/specs/2026-06-07-agent-os-poc-design.md) |
| Track A plan | [`docs/superpowers/plans/2026-06-07-track-a-copilot-loop.md`](docs/superpowers/plans/2026-06-07-track-a-copilot-loop.md) |
| Track B plan | [`docs/superpowers/plans/2026-06-07-track-b-engineering-harness.md`](docs/superpowers/plans/2026-06-07-track-b-engineering-harness.md) |
| Team assignments | [`docs/team/assignments.md`](docs/team/assignments.md) |
| Kickoff runbook | [`docs/team/usman-kickoff.md`](docs/team/usman-kickoff.md) |
| Contributor guide | [`AGENTS.md`](AGENTS.md) |
| ADR-0001 | [`docs/adr/0001-module-boundaries.md`](docs/adr/0001-module-boundaries.md) |
| Known solutions | [`docs/solutions/`](docs/solutions/) |

---

<div align="center">

*Agent OS is under active development. Stubs in `tools/`, `skills/`, and `clickup/` are replaced with real implementations as Track A ships.*

**Built with [Hermes Agent](https://github.com/nousresearch/hermes-agent) · Powered by [uv](https://github.com/astral-sh/uv)**

</div>