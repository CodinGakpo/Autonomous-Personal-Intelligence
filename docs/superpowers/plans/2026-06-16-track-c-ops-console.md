# Track C — Ops Console (full-stack) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-06-16
**Owner:** Tech lead · built by the dev team
**Status:** v1 scaffold implemented 2026-06-16 (Tasks 0–9 landed; frontend uses shadcn/ui). Later screens (WBR/scoring) build on these rails.
**Depends on:** [`docs/superpowers/specs/2026-06-07-agent-os-poc-design.md`](../specs/2026-06-07-agent-os-poc-design.md) (this front-runs the spec's Phase 2 web UI, by product decision)

---
       
## Goal

Stand up a **full-stack ops console** — a web app the team uses to **onboard people** and see
**integration health** — as the first dogfood UI on top of the Agent OS backend. v1 is
deliberately small (onboarding + health), but the scaffold is real full-stack so the dev team
has rails to build the later WBR / reporting / scoring screens on.

This is the kickoff that lets multiple developers work in parallel without stepping on the
existing Hermes-overlay code.

---

## Where it lives — one dedicated folder (the key rule)

**All ops-console code lives under `console/`.** Nothing outside `console/` is edited except
four wiring touch-points (Task 0). The existing overlay packages (`tools/`, `clickup/`,
`skills/`) are **not moved or modified** — the console *consumes* `clickup/`, it does not
change it.

```
console/                     ← the entire full-stack app; devs work here, old code untouched
├── backend/                 # FastAPI (Python). Package: console.backend
│   ├── __init__.py
│   ├── main.py              # app factory (create_app) + router wiring + CORS
│   ├── config.py            # env-driven Settings (no secret required at import time)
│   ├── auth.py              # v1 email/password login + require_auth dependency
│   ├── health.py            # GET /health — integration configuration status
│   ├── onboarding.py        # POST /onboarding, GET /roster (through clickup/ client)
│   └── tests/               # pytest (TestClient; ClickUp faked — no network)
├── frontend/                # Vite + React + TypeScript SPA
│   ├── package.json         # own node deps; never imports an integration SDK (ADR-0002)
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx, App.tsx
│       ├── api.ts           # the ONLY place that calls the backend
│       ├── auth.ts          # token storage
│       └── pages/           # Login, Health, Onboard, Roster
├── deploy/                  # Dockerfile.backend, Dockerfile.frontend, docker-compose.yml, railway.json
└── README.md               # what it is + how to run both halves locally
```

**Why one cross-import is allowed:** the backend reaches ClickUp **only** through the root
`clickup/client.py` (`from clickup.client import ClickUpClient`). That is the single allowed
boundary crossing and is exactly what ADR-0001 requires (one typed, observable ClickUp path).
ADR-0002 (Task 0) encodes the rest: core packages never import `console/`, and the frontend
never calls a third-party API directly.

> Naming: `console/` is the recommendation. If you prefer `dashboard/` or `ops-console/`,
> rename once here before Task 1 — everything keys off this folder.

---

## Architecture & boundaries

```
browser ── frontend/ (SPA) ──HTTP──▶ backend/ (FastAPI) ──▶ clickup/ client ──▶ ClickUp API
                                          │
                                          └── reads env for Slack/Fathom config (health only, v1)
```

Dependency direction is one-way: `frontend → backend → clickup/`+`tools/`. The agent loop
(Hermes) and the console are independent consumers of the same typed clients; neither imports
the other.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **FastAPI** (Python 3.11), runs in the repo's existing `uv` env | Reuses `clickup/` client → honors ADR-0001; stays under the existing ruff/mypy/import-linter harness |
| Frontend | **Vite + React + TypeScript** | Rich dashboard; the design-system inline-style linter already targets `.tsx`; team's React skills |
| Auth (v1) | **email/password** (single admin cred from env, stateless bearer) | Agreed minimal; replaced by Slack OAuth before external users |
| Deploy | **Containerized for both** Railway *and* Unraid compose | Target not yet fixed — keep both, decide later |
| Tests | pytest + FastAPI `TestClient` (ClickUp faked) | No network in CI |

---

## v1 scope

**In:** login (email/password) · integration-health dashboard (ClickUp/Slack/Fathom config
status) · onboarding form (name, email, role, Slack handle, **multi-select products**) that
writes a ClickUp record · read-only roster.

**Out (later tracks):** WBR / reporting screens, performance scoring, the email analyzer,
Slack OAuth, real liveness probes, product→competitor mapping logic, Google Workspace.

---

## File-structure / wiring touch-points outside `console/` (Task 0 only)

| Path | Change |
|---|---|
| `docs/adr/0002-web-api-boundaries.md` | New ADR (console ↔ backend ↔ clickup boundaries) |
| `AGENTS.md` | Add `console/` row to the layout table |
| `pyproject.toml` | Add `fastapi`+`uvicorn` deps, `httpx` dev dep; add `console` to mypy `files` and import-linter `root_packages`; add the ADR-0002 contract; add `[tool.pytest.ini_options] pythonpath = ["."]` |
| `.pre-commit-config.yaml` + `.github/workflows/ci.yml` | Append `lint-imports` and `pytest -q` steps so ADR-0002 + console tests are enforced |

Everything else is created **inside `console/`**.

---

## Task 0 — Boundaries & harness wiring (do first; unblocks everyone)

**Files:** `docs/adr/0002-web-api-boundaries.md`, `AGENTS.md`, `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `console/__init__.py`, `console/backend/__init__.py`

- [ ] Write **ADR-0002**: frontend never calls third-party APIs directly; backend reaches ClickUp only via `clickup/`; core packages (`clickup/`, `tools/`, `skills/`) MUST NOT import `console`.
- [ ] Add the import-linter contract (`source_modules = ["clickup","tools","skills"]`, `forbidden_modules = ["console"]`) and add `"console"` to `root_packages`; add `"console"` to mypy `files`.
- [ ] Add deps: `fastapi>=0.115`, `uvicorn[standard]>=0.30` (runtime), `httpx>=0.27` (dev). Add `[tool.pytest.ini_options] pythonpath = ["."]`.
- [ ] Append `lint-imports` + `pytest -q` to pre-commit and CI.
- [ ] Add `console/` row to `AGENTS.md`.
- [ ] **Verify:** `uv sync && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest -q` all pass on the empty scaffold.

## Task 1 — Backend skeleton + health
`console/backend/{main.py,config.py,health.py}` — app factory with CORS, env-driven `Settings`, `GET /health` returning per-integration `configured | not_configured`. Verify with `uv run uvicorn console.backend.main:app` and a curl.

## Task 2 — Auth (email/password)
`console/backend/auth.py` — `POST /auth/login` validates a single admin cred from env, returns a stateless bearer token; `require_auth` dependency guards protected routes.

## Task 3 — Onboarding + roster
`console/backend/onboarding.py` — `OnboardRequest` (name, email, role enum, slack_handle, `products: list[Product]`), `POST /onboarding` creates a ClickUp task via `clickup/client.py` in the employees list, `GET /roster` lists onboarded people. Auth-guarded.

## Task 4 — Backend tests
`console/backend/tests/test_*.py` — `TestClient`, ClickUp client overridden with a fake (no network): health status, login success/failure, onboarding-requires-auth, onboarding creates task + appears in roster.

## Task 5 — Frontend skeleton
`console/frontend/` — `npm create vite@latest . -- --template react-ts`, trim to a minimal app, add `src/api.ts` (single backend-call module) + `src/auth.ts`. Verify `npm install && npm run build`.

## Task 6 — Frontend pages
`src/pages/` — Login, Health (status cards), Onboard (form with multi-select products), Roster (table). No inline styles (design-system rule) — use a CSS module / stylesheet.

## Task 7 — Wire frontend ↔ backend
`.env` for `VITE_API_BASE_URL`; dev proxy or CORS origin; auth header injection in `api.ts`. Manual smoke: log in → see health → onboard a person → see them in roster.

## Task 8 — Deploy (both targets)
`console/deploy/` — `Dockerfile.backend` (uv + uvicorn), `Dockerfile.frontend` (node build → static serve), `docker-compose.yml` (Unraid), `railway.json` (Railway). Document env vars.

## Task 9 — Docs
`console/README.md` (run both halves locally) + a PRD `docs/prd/ops-console.md` (problem · goal · user journey) so the spec-presence check passes and devs have grounding.

---

## Parallelization (so the team can split work)

- **Task 0 is the gate** — the tech lead lands it first; it unblocks the rest.
- Then split: **Backend dev** → Tasks 1–4 · **Frontend dev** → Tasks 5–6 against the agreed
  API shape · **Integration/DevOps** → Tasks 7–8. Task 9 is shared.
- API contract (the request/response models in Tasks 1–3) is the interface the frontend codes
  against — freeze it early so both halves move independently.

## Open questions (need product owner)

- Real **product names** + the product→competitor mapping (placeholders `product_one/two/three` for now).
- ClickUp **employees list id** (and whether onboarding writes a task vs. a list custom field).
- Confirm **deploy target** when we're ready (Railway vs Unraid) — until then we ship both.
