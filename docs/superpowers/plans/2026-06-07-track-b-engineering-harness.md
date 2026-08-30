# Track B — Engineering Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the repo's enforcement harness so every later PR (human- or agent-written) is automatically checked against ADRs, PRDs, BDD specs, and code-quality rules, locally (git hooks) and on CI.

**Architecture:** Overlay repo, Python-primary (matching Hermes). A `pre-commit` hook chain runs formatter, type-check, architecture check, duplication, doc-lint, and BDD; GitHub Actions re-runs the identical chain so skipping local hooks is caught. Architecture rules (ADRs) are encoded as `import-linter` contracts; a violation message points back to the ADR. Source packages (`tools/`, `clickup/`, `skills/`) are scaffolded as stubs so the contracts have something to enforce.

**Tech Stack:** Python 3.11, `uv` (env + deps), `ruff` (format+lint), `mypy` (types), `import-linter` (architecture), `behave` (BDD/Gherkin), `pre-commit` (git hooks), `jscpd` + `markdownlint-cli2` (via `npx`), GitHub Actions (CI).

**Prerequisite tools on the machine:** `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`), Node.js (for `npx`), `git`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, deps, config for ruff/mypy/import-linter |
| `package.json` | Dev-only Node tools (`jscpd`, `markdownlint-cli2`) pinned for `npx` |
| `.pre-commit-config.yaml` | Local git-hook chain |
| `.github/workflows/ci.yml` | CI running the identical chain |
| `.markdownlint.jsonc` | Doc-lint rules |
| `scripts/check_specs.py` | Custom check: ADR/PRD presence + required-section lint |
| `scripts/check_inline_styles.py` | Design-system rule: forbid inline styles in UI files |
| `tools/__init__.py`, `tools/fathom/__init__.py`, `tools/fathom/client.py` | Stub Fathom tool package (correct import direction) |
| `clickup/__init__.py`, `clickup/client.py` | Stub typed ClickUp client |
| `skills/__init__.py`, `skills/meeting_to_task.py` | Stub synthesis skill (imports clickup client, not raw HTTP) |
| `docs/adr/0000-template.md`, `docs/adr/0001-module-boundaries.md` | ADR template + first architecture decision |
| `docs/prd/0000-template.md`, `docs/prd/poc-meeting-to-task.md` | PRD template + the POC PRD |
| `docs/design-system/README.md` | Design-system rules (visual ADRs) |
| `features/meeting_to_task.feature`, `features/environment.py`, `features/steps/meeting_to_task_steps.py` | Sample BDD spec + DB-access guard |
| `tests/test_architecture.py` | Asserts `lint-imports` passes on a clean tree |
| `tests/test_specs.py` | Asserts `check_specs.py` passes |

---

## Task 1: Initialize the Python project

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`

- [ ] **Step 1: Create `.python-version`**

```
3.11
```

- [ ] **Step 2: Create `pyproject.toml`**

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

- [ ] **Step 3: Create the environment and verify**

Run: `uv sync` then `uv run python -c "import sys; print(sys.version)"`
Expected: prints a `3.11.x` version, no errors.

- [ ] **Step 4: Commit**

```bash
git add .python-version pyproject.toml uv.lock
git commit -m "chore: initialize python project with uv and tool config"
```

---

## Task 2: Scaffold source packages as stubs

**Files:**
- Create: `tools/__init__.py`, `tools/fathom/__init__.py`, `tools/fathom/client.py`
- Create: `clickup/__init__.py`, `clickup/client.py`
- Create: `skills/__init__.py`, `skills/meeting_to_task.py`

- [ ] **Step 1: Create the ClickUp client stub** (`clickup/client.py`)

```python
"""Typed ClickUp client. All ClickUp API access MUST go through this module (ADR-0001)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRef:
    id: str
    url: str


class ClickUpClient:
    """Stub. Real HTTP wiring lands in Track A (Plan 2)."""

    def create_task(self, list_id: str, name: str, description: str) -> TaskRef:
        raise NotImplementedError("Implemented in Track A")

    def add_comment(self, task_id: str, text: str) -> None:
        raise NotImplementedError("Implemented in Track A")
```

- [ ] **Step 2: Create the Fathom tool stub** (`tools/fathom/client.py`)

```python
"""Fathom tool. MUST NOT import clickup or write to ClickUp directly (ADR-0001).

It returns transcript data; the agent acts on it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    meeting_id: str
    text: str


def fetch_transcript(meeting_id: str) -> Transcript:
    """Stub. Real Fathom API wiring lands in Track A (Plan 2)."""
    raise NotImplementedError("Implemented in Track A")
```

- [ ] **Step 3: Create the synthesis skill stub** (`skills/meeting_to_task.py`)

```python
"""Synthesis skill: transcript -> structured minutes + task payload.

Persists via the typed clickup client, never raw HTTP (ADR-0001).
"""
from __future__ import annotations

from clickup.client import ClickUpClient, TaskRef


def meeting_to_task(client: ClickUpClient, list_id: str, minutes: str) -> TaskRef:
    """Stub. Real synthesis lands in Track A (Plan 2)."""
    raise NotImplementedError("Implemented in Track A")
```

- [ ] **Step 4: Create the empty `__init__.py` files**

Each of `tools/__init__.py`, `tools/fathom/__init__.py`, `clickup/__init__.py`, `skills/__init__.py` contains a single line:

```python
"""Agent OS package."""
```

- [ ] **Step 5: Verify everything imports**

Run: `uv run python -c "import tools.fathom.client, clickup.client, skills.meeting_to_task; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add tools clickup skills
git commit -m "feat: scaffold tools/clickup/skills stub packages"
```

---

## Task 3: Wire ruff (format + lint)

**Files:**
- Modify: `pyproject.toml` (config already added in Task 1)

- [ ] **Step 1: Run the formatter and linter to confirm a clean tree**

Run: `uv run ruff format --check . && uv run ruff check .`
Expected: PASS ("All checks passed!"). If format reports changes, run `uv run ruff format .` then re-run.

- [ ] **Step 2: Prove the linter catches a violation (RED)**

Append an unused import to `clickup/client.py`:

```python
import os  # deliberately unused
```

Run: `uv run ruff check clickup/client.py`
Expected: FAIL with `F401` unused-import.

- [ ] **Step 3: Remove the violation (GREEN)**

Delete the `import os` line. Run: `uv run ruff check clickup/client.py`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: confirm ruff format+lint gate"
```

---

## Task 4: Wire mypy (types)

**Files:**
- Modify: `pyproject.toml` (config already added in Task 1)

- [ ] **Step 1: Run mypy to confirm a clean tree**

Run: `uv run mypy`
Expected: PASS ("Success: no issues found").

- [ ] **Step 2: Prove mypy catches a type error (RED)**

In `clickup/client.py`, change `add_comment`'s body to `return "oops"`.

Run: `uv run mypy`
Expected: FAIL with an error about returning `str` from a function declared `-> None`.

- [ ] **Step 3: Revert (GREEN)**

Restore the original `raise NotImplementedError(...)` body. Run: `uv run mypy`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: confirm mypy strict gate"
```

---

## Task 5: Encode ADR-0001 as import-linter contracts

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_architecture.py`

- [ ] **Step 1: Add the architecture contracts to `pyproject.toml`**

Append below the existing `[tool.importlinter]` block:

```toml
[[tool.importlinter.contracts]]
name = "Fathom tool must not import ClickUp (ADR-0001)"
type = "forbidden"
source_modules = ["tools.fathom"]
forbidden_modules = ["clickup"]

[[tool.importlinter.contracts]]
name = "Tools must not import skills (ADR-0001)"
type = "forbidden"
source_modules = ["tools"]
forbidden_modules = ["skills"]
```

- [ ] **Step 2: Run the architecture check to confirm the clean tree passes**

Run: `uv run lint-imports`
Expected: PASS ("Contracts: 2 kept, 0 broken").

- [ ] **Step 3: Write the failing test** (`tests/test_architecture.py`)

```python
import subprocess


def test_architecture_contracts_pass():
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_architecture.py -v`
Expected: PASS.

- [ ] **Step 5: Prove a violation is caught (RED — this satisfies spec success criterion #2)**

Add to the top of `tools/fathom/client.py`:

```python
from clickup.client import ClickUpClient  # ADR-0001 violation
```

Run: `uv run lint-imports`
Expected: FAIL — "Fathom tool must not import ClickUp" listed as broken.

- [ ] **Step 6: Remove the violation (GREEN)**

Delete that import. Run: `uv run lint-imports`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/test_architecture.py
git commit -m "feat: enforce ADR-0001 module boundaries via import-linter"
```

---

## Task 6: ADR template + ADR-0001 document

**Files:**
- Create: `docs/adr/0000-template.md`
- Create: `docs/adr/0001-module-boundaries.md`

- [ ] **Step 1: Create the ADR template** (`docs/adr/0000-template.md`)

```markdown
# ADR-NNNN: <title>

- **Status:** proposed | accepted | superseded
- **Date:** YYYY-MM-DD

## Rule
<the rule, stated as an enforceable constraint>

## Why
<the rationale — what breaks if this rule is ignored>

## Scope
<which files/folders/modules this governs>

## Enforcement
<the linter/check that enforces it, e.g. import-linter contract name>
```

- [ ] **Step 2: Create ADR-0001** (`docs/adr/0001-module-boundaries.md`)

```markdown
# ADR-0001: Module boundaries

- **Status:** accepted
- **Date:** 2026-06-07

## Rule
1. `tools/fathom` MUST NOT import `clickup` (the Fathom tool returns data; the agent acts on it).
2. `tools` MUST NOT import `skills`.
3. All ClickUp API access MUST go through `clickup/client.py` — never raw HTTP elsewhere.

## Why
Keeps integration tools side-effect-free and composable, prevents hidden write paths that
make behavior hard to reason about, and centralizes ClickUp access for rate-limiting, auth,
and observability.

## Scope
`tools/`, `clickup/`, `skills/`.

## Enforcement
`import-linter` contracts in `pyproject.toml` ("Fathom tool must not import ClickUp",
"Tools must not import skills"). Rule 3 is reviewed in code review until a custom check exists.
```

- [ ] **Step 3: Verify markdown is well-formed**

Run: `npx -y markdownlint-cli2 "docs/adr/**/*.md"`
Expected: PASS (no errors). If it flags rules, fix the markdown.

- [ ] **Step 4: Commit**

```bash
git add docs/adr
git commit -m "docs: add ADR template and ADR-0001 module boundaries"
```

---

## Task 7: PRD template + POC PRD

**Files:**
- Create: `docs/prd/0000-template.md`
- Create: `docs/prd/poc-meeting-to-task.md`

- [ ] **Step 1: Create the PRD template** (`docs/prd/0000-template.md`)

```markdown
# PRD: <feature>

## Problem
<the core problem, one paragraph>

## Goal
<the outcome we want, measurable if possible>

## User Journey
<the critical path the user takes, step by step>
```

- [ ] **Step 2: Create the POC PRD** (`docs/prd/poc-meeting-to-task.md`)

```markdown
# PRD: Meeting-to-Task co-pilot (POC)

## Problem
Meeting decisions and action items live in Fathom transcripts and never reliably make it
into ClickUp, so work is forgotten and ClickUp is not a trustworthy source of truth.

## Goal
From Slack, a user points the co-pilot at one Fathom meeting and gets a ClickUp task created
with accurate minutes recorded — no manual correction needed on a real meeting.

## User Journey
1. The user messages the co-pilot in Slack with a Fathom meeting link.
2. The agent fetches the transcript (Fathom tool).
3. The agent synthesizes structured minutes and a task payload (synthesis skill).
4. The agent creates a ClickUp task with the minutes recorded (clickup client).
5. The agent confirms back in Slack with the task link.
```

- [ ] **Step 3: Lint**

Run: `npx -y markdownlint-cli2 "docs/prd/**/*.md"`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/prd
git commit -m "docs: add PRD template and POC meeting-to-task PRD"
```

---

## Task 8: Custom spec-presence check

**Files:**
- Create: `scripts/check_specs.py`
- Create: `tests/test_specs.py`

- [ ] **Step 1: Write the check** (`scripts/check_specs.py`)

```python
"""Fail if the spec harness is missing required docs or required sections.

Run: python scripts/check_specs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_REQUIRED = ["## Rule", "## Why", "## Scope", "## Enforcement"]
PRD_REQUIRED = ["## Problem", "## Goal", "## User Journey"]


def _check(dir_rel: str, required: list[str]) -> list[str]:
    errors: list[str] = []
    d = ROOT / dir_rel
    docs = [p for p in d.glob("*.md") if not p.name.startswith("0000")]
    if not docs:
        errors.append(f"{dir_rel}: no documents found (need at least one besides the template)")
    for p in docs:
        text = p.read_text(encoding="utf-8")
        for section in required:
            if section not in text:
                errors.append(f"{p.relative_to(ROOT)}: missing required section '{section}'")
    return errors


def main() -> int:
    errors = _check("docs/adr", ADR_REQUIRED) + _check("docs/prd", PRD_REQUIRED)
    for e in errors:
        print(f"SPEC-LINT: {e}")
    if errors:
        print(f"\n{len(errors)} spec problem(s). See docs/adr and docs/prd.")
        return 1
    print("Spec harness OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to confirm the current tree passes**

Run: `uv run python scripts/check_specs.py`
Expected: prints "Spec harness OK." and exits 0.

- [ ] **Step 3: Write the test** (`tests/test_specs.py`)

```python
import subprocess


def test_spec_harness_passes():
    result = subprocess.run(
        ["uv", "run", "python", "scripts/check_specs.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_specs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_specs.py tests/test_specs.py
git commit -m "feat: add spec-presence check for ADRs and PRDs"
```

---

## Task 9: BDD with behave (DB-access guard)

**Files:**
- Create: `features/meeting_to_task.feature`
- Create: `features/environment.py`
- Create: `features/steps/meeting_to_task_steps.py`

- [ ] **Step 1: Write the feature** (`features/meeting_to_task.feature`)

```gherkin
Feature: Meeting-to-task co-pilot
  As a user, I want a meeting turned into a ClickUp task
  so that decisions are not lost.

  Scenario: A transcript becomes minutes
    Given a meeting transcript with one action item
    When the co-pilot synthesizes minutes
    Then the minutes contain the action item
```

- [ ] **Step 2: Write the DB-access guard** (`features/environment.py`)

```python
"""behave environment. Enforces: the e2e suite must not touch internals/DB (ADR discipline).

For Phase 0 there is no DB; this guard makes the rule executable now by forbidding any
import of a database driver from within step execution.
"""
FORBIDDEN_MODULES = {"sqlite3", "psycopg2", "psycopg", "sqlalchemy", "asyncpg"}


def before_all(context):
    import sys

    leaked = FORBIDDEN_MODULES & set(sys.modules)
    if leaked:
        raise AssertionError(
            f"e2e/BDD suite imported forbidden internal/DB modules: {sorted(leaked)}"
        )
```

- [ ] **Step 3: Write the steps** (`features/steps/meeting_to_task_steps.py`)

```python
from behave import given, then, when


@given("a meeting transcript with one action item")
def step_transcript(context):
    context.transcript = "Decision: ship POC. Action item: set up Unraid."


@when("the co-pilot synthesizes minutes")
def step_synthesize(context):
    # Phase 0 placeholder synthesis; real skill arrives in Track A (Plan 2).
    context.minutes = f"Minutes:\n- {context.transcript.split('Action item: ')[1]}"


@then("the minutes contain the action item")
def step_assert(context):
    assert "set up Unraid" in context.minutes
```

- [ ] **Step 4: Run behave**

Run: `uv run behave`
Expected: PASS — "1 feature passed", "1 scenario passed".

- [ ] **Step 5: Commit**

```bash
git add features
git commit -m "test: add BDD feature with DB-access guard"
```

---

## Task 10: Duplication + markdown lint (Node tools)

**Files:**
- Create: `package.json`
- Create: `.markdownlint.jsonc`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "agent-os-devtools",
  "private": true,
  "devDependencies": {
    "jscpd": "4.0.5",
    "markdownlint-cli2": "0.14.0"
  },
  "scripts": {
    "dup": "jscpd --min-lines 12 --threshold 0 --pattern \"{tools,clickup,skills,scripts}/**/*.py\" --reporters consoleFull",
    "mdlint": "markdownlint-cli2 \"docs/**/*.md\""
  }
}
```

- [ ] **Step 2: Create `.markdownlint.jsonc`**

```jsonc
{
  "default": true,
  "MD013": false,   // line length handled elsewhere
  "MD033": false,   // allow inline HTML in design-system previews
  "MD041": false    // first line need not be a top-level heading
}
```

- [ ] **Step 3: Run duplication check**

Run: `npx -y jscpd --min-lines 12 --threshold 0 --pattern "{tools,clickup,skills,scripts}/**/*.py" --reporters consoleFull`
Expected: PASS — "Found 0 clones." (threshold 0 means any clone fails CI.)

- [ ] **Step 4: Run markdown lint**

Run: `npx -y markdownlint-cli2 "docs/**/*.md"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add package.json .markdownlint.jsonc
git commit -m "chore: add jscpd duplication and markdownlint config"
```

---

## Task 11: Design-system stub + inline-style guard

**Files:**
- Create: `docs/design-system/README.md`
- Create: `scripts/check_inline_styles.py`

- [ ] **Step 1: Create the design-system rules** (`docs/design-system/README.md`)

```markdown
# Design System (visual ADRs)

Applies to any web UI (first lands in Phase 2). Rules:
- One primary button visible per view.
- No inline styles anywhere — use component classes/tokens.
- Compose from documented components; do not write one-off custom UI.

Component previews and tokens are added when the first UI is built.
```

- [ ] **Step 2: Write the inline-style guard** (`scripts/check_inline_styles.py`)

```python
"""Forbid inline styles in UI files (design-system rule).

Passes when there are no UI files yet (Phase 0). Run: python scripts/check_inline_styles.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_GLOBS = ["**/*.html", "**/*.tsx", "**/*.jsx", "**/*.vue"]
INLINE_STYLE = re.compile(r"""\bstyle\s*=\s*["'{]""")
SKIP_DIRS = {"node_modules", ".venv", "venv", ".git"}


def _iter_ui_files():
    for pattern in UI_GLOBS:
        for p in ROOT.glob(pattern):
            if not any(part in SKIP_DIRS for part in p.parts):
                yield p


def main() -> int:
    errors = []
    for p in _iter_ui_files():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if INLINE_STYLE.search(line):
                errors.append(f"{p.relative_to(ROOT)}:{i}: inline style forbidden (design-system)")
    for e in errors:
        print(f"DESIGN-LINT: {e}")
    if errors:
        return 1
    print("Inline-style check OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it (passes — no UI yet)**

Run: `uv run python scripts/check_inline_styles.py`
Expected: prints "Inline-style check OK." and exits 0.

- [ ] **Step 4: Commit**

```bash
git add docs/design-system scripts/check_inline_styles.py
git commit -m "feat: add design-system rules and inline-style guard"
```

---

## Task 12: pre-commit git hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

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
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        pass_filenames: false
      - id: import-linter
        name: architecture (ADRs)
        entry: uv run lint-imports
        language: system
        pass_filenames: false
      - id: check-specs
        name: spec presence (ADR/PRD)
        entry: uv run python scripts/check_specs.py
        language: system
        pass_filenames: false
      - id: check-inline-styles
        name: design-system inline styles
        entry: uv run python scripts/check_inline_styles.py
        language: system
        pass_filenames: false
      - id: behave
        name: BDD (behave)
        entry: uv run behave
        language: system
        pass_filenames: false
```

- [ ] **Step 2: Install the hooks**

Run: `uv run pre-commit install`
Expected: "pre-commit installed at .git/hooks/pre-commit".

- [ ] **Step 3: Run the full chain against all files**

Run: `uv run pre-commit run --all-files`
Expected: every hook reports "Passed".

- [ ] **Step 4: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "feat: add pre-commit hook chain"
```

---

## Task 13: GitHub Actions CI (identical chain)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow** (`.github/workflows/ci.yml`)

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
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install deps
        run: uv sync
      - name: Ruff format
        run: uv run ruff format --check .
      - name: Ruff lint
        run: uv run ruff check .
      - name: Mypy
        run: uv run mypy
      - name: Architecture (ADRs)
        run: uv run lint-imports
      - name: Spec presence
        run: uv run python scripts/check_specs.py
      - name: Inline styles
        run: uv run python scripts/check_inline_styles.py
      - name: BDD
        run: uv run behave
      - name: Pytest
        run: uv run pytest -v
      - name: Duplication
        run: npx -y jscpd --min-lines 12 --threshold 0 --pattern "{tools,clickup,skills,scripts}/**/*.py" --reporters consoleFull
      - name: Markdown lint
        run: npx -y markdownlint-cli2 "docs/**/*.md"
```

- [ ] **Step 2: Validate YAML locally**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Expected: prints `yaml ok`. (If `yaml` is missing, run `uv add --dev pyyaml` first.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the full harness chain on push and PR"
```

---

## Task 14: README + final verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Agent OS

Second brain for the company — an overlay on [Hermes Agent](https://github.com/nousresearch/hermes-agent).
See `docs/superpowers/specs/2026-06-07-agent-os-poc-design.md` for the design.

## Develop
- `uv sync` — install deps
- `uv run pre-commit install` — enable git hooks
- `uv run pre-commit run --all-files` — run the full harness

## Governance
- ADRs: `docs/adr/` (enforced by `import-linter`)
- PRDs: `docs/prd/` (read before coding)
- BDD: `features/` (`uv run behave`)
- Design system: `docs/design-system/`
Violations are caught by git hooks and by CI (`.github/workflows/ci.yml`).
```

- [ ] **Step 2: Run the entire harness one final time**

Run: `uv run pre-commit run --all-files && uv run pytest -v`
Expected: all hooks "Passed", all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with develop + governance instructions"
```

---

## Self-Review Notes (verified against the spec)

- **§5 ADRs** → Tasks 5, 6 (template + ADR-0001 + import-linter enforcement + violation caught = spec success criterion #2).
- **§5 PRDs** → Tasks 7, 8 (template + POC PRD + presence check).
- **§5 BDD** → Task 9 (feature + steps + DB-access guard).
- **§5 design system** → Task 11 (rules + inline-style guard wired now, passes with no UI).
- **§5 enforcement loop (hooks + CI, same checks)** → Tasks 12, 13.
- **§11 success criterion #2** ("rejects a deliberately ADR-violating PR locally AND on CI") → Task 5 Step 5 proves local rejection; Task 13 runs the identical `lint-imports` on CI.
- **Out of scope here (Track A / Plan 2):** real Fathom/ClickUp/Hermes wiring — stubs only, by design.
```
