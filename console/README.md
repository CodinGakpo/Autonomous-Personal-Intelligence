# Ops Console (full-stack)

The team-facing web app for Agent OS. **All ops-console code lives in this folder** — it is
kept separate from the Hermes-overlay packages (`tools/`, `clickup/`, `skills/`) on purpose, so
contributors can work here without touching the agent runtime. The console *consumes* the
`clickup/` client; it never modifies it.

> **Status:** scaffolding. Build it task-by-task following
> [`docs/superpowers/plans/2026-06-16-track-c-ops-console.md`](../docs/superpowers/plans/2026-06-16-track-c-ops-console.md).
> Boundaries are governed by ADR-0002.

## What it does (v1)

- **Login** — email/password (single admin cred for now; Slack OAuth later).
- **Integration health** — is ClickUp / Slack / Fathom configured?
- **Onboarding** — add a person (name, role, Slack handle, the products they work on) → recorded in ClickUp.
- **Roster** — read-only list of onboarded people.

## Layout

```
console/
├── backend/    # FastAPI (Python). Runs in the repo's uv env. Reaches ClickUp only via the root clickup/ client.
├── frontend/   # Vite + React + TypeScript SPA. Talks only to backend/ — never a third-party API directly.
└── deploy/     # Dockerfiles + docker-compose (Unraid) + railway.json (Railway).
```

## Run locally

There are two ways to start the full stack. Both end with the seeded admin login
`admin@agent-os.local` / `changeme` (override via `OPS_ADMIN_EMAIL` / `OPS_ADMIN_PASSWORD`).
Add more logins via `POST /auth/users` (admin only).

### Option A — With Docker (recommended)

Runs everything (frontend + backend + Postgres) with one command. Needs only Docker.

```bash
cd console/deploy
docker compose up --build            # add -d to run in the background
```

| Service | URL |
|---|---|
| Frontend | http://localhost:8080 |
| Backend API + docs | http://localhost:8000 · http://localhost:8000/docs |
| Postgres | internal `db:5432` (data persists in the `ops_db` volume) |

```bash
docker compose logs -f backend       # tail logs
docker compose down                  # stop (keeps the database)
docker compose down -v               # stop + wipe the database
```

### Option B — Without Docker (manual)

Run each piece yourself. The backend still needs a Postgres; the quickest is a one-off
container on port **5433** (matches the backend's default `DATABASE_URL`, and avoids clashing
with any Postgres already on 5432):

```bash
# 1. Postgres (one-time container; or use a locally installed Postgres)
docker run --name ops-db -p 5433:5432 \
  -e POSTGRES_USER=ops -e POSTGRES_PASSWORD=ops -e POSTGRES_DB=ops_console \
  -d postgres:16-alpine

# 2. Backend — from the repo root, uses the shared uv env (creates tables + seeds admin)
uv sync
uv run uvicorn console.backend.main:app --reload       # http://localhost:8000

# 3. Frontend — from console/frontend
npm install
npm run dev                                            # http://localhost:5173
```

Point the backend at a different database any time by setting `DATABASE_URL`, e.g.
`DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname uv run uvicorn ...`.
The dev frontend (`:5173`) is already an allowed CORS origin; for other origins set
`OPS_CORS_ORIGINS` (comma-separated) on the backend.

## Boundaries (ADR-0002)

- `frontend/` → calls `backend/` only. No ClickUp/Slack/Fathom SDKs or tokens in the browser.
- `backend/` → reaches ClickUp only through `clickup/client.py` (ADR-0001).
- Core packages (`clickup/`, `tools/`, `skills/`) MUST NOT import `console/`.
