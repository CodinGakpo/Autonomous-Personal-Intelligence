---
title: "`uv sync` fails with `command not found: uv` during project init"
date: 2026-06-08
category: build-errors
module: project-setup
problem_type: build_error
component: tooling
symptoms:
  - "`uv sync` fails with `command not found: uv` (exit code 127)"
  - "uv binary absent from ~/.local/bin, ~/.cargo/bin, and /opt/homebrew/bin"
  - "Project initialization (Plan 1, Task 1) halts before Python/deps are provisioned"
root_cause: missing_tooling
resolution_type: tooling_addition
severity: high
related_components:
  - development_workflow
tags:
  - uv
  - build-error
  - project-setup
  - prerequisites
  - homebrew
  - python
  - onboarding
  - dependency-management
---

# `uv sync` fails with `command not found: uv` during project init

## Problem

During Plan 1 Task 1 ("Initialize the Python project") in the Agent OS repo — a
Python-primary project managed with `uv`, on macOS (darwin/arm64) — the first command of
the standard workflow, `uv sync`, failed immediately with an exit-127 command-not-found
error. `uv` was never installed on the machine. Because the entire team's standard workflow
opens with `uv sync`, every developer onboarding to this repo will hit the same wall.

## Symptoms

```
$ uv sync
(eval):1: command not found: uv
```

- Exit code 127 (command not found).
- The failure occurs on a freshly cloned repo at the very first dependency step, before any
  Python environment is provisioned.
- The `uv` binary is absent from every common install location.

## What Didn't Work

Running `uv`-prefixed commands directly — `uv sync` (and `uv run ...`) — on the assumption
that `uv` was already on `PATH`. It was not: `uv` had never been installed, so every
invocation failed with `command not found`. There was no PATH or shell-config issue to fix;
the binary simply did not exist.

Diagnosis confirmed this by checking the common install locations, all absent:

```
~/.local/bin/uv      # not present (curl-installer default)
~/.cargo/bin/uv      # not present (cargo install default)
/opt/homebrew/bin/uv # not present (Homebrew default)
```

`python3` resolved to Homebrew Python 3.13.5 and `brew` was available at
`/opt/homebrew/bin/brew`, confirming the toolchain was otherwise healthy — only `uv` was
missing.

## Solution

Install `uv` once, then re-run the workflow. Two supported install paths:

Option A — Homebrew (used here, clean on macOS):

```
brew install uv
```

Option B — official cross-platform installer (the one the plan references; Linux and macOS):

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Note: the curl installer drops the `uv` binary in `~/.local/bin`. If that directory isn't
already on your `PATH`, open a new shell (or re-source your shell profile) so the binary
resolves before continuing.

With `uv` installed (here, uv 0.11.19), run the sync and verify:

```
uv sync
uv run python -c "import sys; print(sys.version)"
```

`uv sync` provisioned Python 3.11.15 (per `.python-version`) and installed all dev-group
tools (ruff, mypy, import-linter, behave, pre-commit, pytest). The verification printed
`3.11.15`, confirming the pinned interpreter was in use.

## Why This Works

`uv` is the tool that reads `.python-version` and `pyproject.toml`, provisions the correct
interpreter, and resolves/installs dependencies — so it must exist on `PATH` before any
`uv sync` or `uv run` can do anything. The exit-127 error was not a project or config
problem; it was a missing prerequisite binary. Installing `uv` via Homebrew (or the official
installer) puts the executable on `PATH`, after which the project's own pins
(`.python-version` → 3.11.15) and declared dependencies drive the rest of the setup
automatically. Homebrew places the binary in `/opt/homebrew/bin` (already on PATH on macOS),
which is why no shell reconfiguration was needed on this path.

## Prevention

`uv` is currently mentioned only as a prerequisite note in the Track B plan
("uv (curl -LsSf https://astral.sh/uv/install.sh | sh)"), not as a numbered setup step — so
it gets silently assumed even though the very first command everyone runs depends on it. Make
the install explicit and unmissable:

- Lead the README "Develop" section (and `docs/team/usman-kickoff.md`) with an explicit
  "Install uv first" step, placed before the first `uv sync` call:

  ```
  # macOS
  brew install uv
  # or cross-platform
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- Add a "step zero" verification so a missing install fails loudly with a clear cause rather
  than an opaque exit 127:

  ```
  uv --version
  ```

- Frame it as one-time, per-machine environment setup: this install happens once per
  developer machine, so the onboarding flow should treat it as a setup prerequisite the
  reader actively performs, not background knowledge. Promoting it from a parenthetical note
  to an ordered step is what prevents the next onboarding developer from hitting the same
  exit-127 wall.

## Related Issues

- First entry in `docs/solutions/` — no prior related docs.
- Source task: `docs/superpowers/plans/2026-06-07-track-b-engineering-harness.md` (Task 1).
- Onboarding workflow that assumes `uv`: `docs/team/usman-kickoff.md`.
