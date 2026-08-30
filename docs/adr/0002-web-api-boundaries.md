# ADR-0002: Ops-console boundaries

- **Status:** accepted
- **Date:** 2026-06-16

## Rule

1. All ops-console code lives under `console/` (`console/backend` = FastAPI, `console/frontend`
   = SPA). The existing overlay packages (`tools/`, `clickup/`, `skills/`) are not modified.
2. The frontend (`console/frontend`) MUST NOT call ClickUp, Slack, Fathom, or any third-party
   API directly. It talks only to `console/backend` over HTTP.
3. The backend (`console/backend`) MUST reach ClickUp only through `clickup/client.py` — never
   raw HTTP. Other integrations go through their typed client under `tools/`.
4. Core packages (`clickup/`, `tools/`, `skills/`) MUST NOT import `console`. The dependency
   direction is one-way: `frontend` → `backend` → `clickup/`+`tools/`. The agent loop and the
   console are independent consumers of the same typed clients.

## Why

Keeps a single, observable, rate-limited path to each integration (extends ADR-0001 to the web
layer), keeps secrets out of browser code, and stops the agent runtime and the web app from
coupling — either can change or deploy independently. Confining the console to one folder lets
the team build it without touching the Hermes overlay.

## Scope

`console/` and its relationship to `clickup/`, `tools/`, `skills/`.

## Enforcement

`import-linter` contract in `pyproject.toml` ("Core packages must not import the console")
covers rule 4. Rule 3 reuses the ADR-0001 contracts (all ClickUp access via `clickup/`). Rules
1–2 are reviewed in code review until a custom check exists; the frontend ships with no
integration SDKs or tokens in its dependencies.
