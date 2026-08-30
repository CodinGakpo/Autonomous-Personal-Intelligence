# Deploy — Ops Console

Two targets are kept until we commit to one (Track C decision pending).

## Environment variables (backend)

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (e.g. `postgresql+psycopg://ops:ops@db:5432/ops_console`) |
| `OPS_SECRET_KEY` | JWT signing key — use 32+ random bytes in production |
| `OPS_ADMIN_EMAIL` / `OPS_ADMIN_PASSWORD` | Seed admin login, created on first startup if absent |
| `CLICKUP_TOKEN` | ClickUp API token (onboarding writes; health "configured") |
| `CLICKUP_EMPLOYEES_LIST_ID` | List that onboarded people are written to |
| `SLACK_BOT_TOKEN` / `FATHOM_API_KEY` | Health "configured" status (not used by v1 logic) |
| `OPS_CORS_ORIGINS` | Comma-separated origins allowed to call the API |

The compose stack runs Postgres (`db` service, volume `ops_db`); the backend waits for it to be
healthy and creates tables + seeds the admin on startup. Add more logins via
`POST /auth/users` (admin only).

Frontend bakes `VITE_API_BASE_URL` at build time — point it at the deployed backend.

## Unraid / self-hosted (docker-compose)

```bash
cd console/deploy
docker compose up --build      # backend :8000, frontend :8080
```

## Railway

- Backend: deploy this repo with `console/deploy/railway.json` (Dockerfile builder). Set the
  env vars above in the Railway service.
- Frontend: deploy `console/frontend` as a separate static service (build `npm run build`,
  serve `dist/`), with `VITE_API_BASE_URL` set to the backend URL.

> These are starting stubs — not yet smoke-tested against a live target. Harden when the
> deploy target is chosen.
