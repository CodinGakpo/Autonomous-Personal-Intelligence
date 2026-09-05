# Setup — Agent OS (mail console)

Get the full system running locally: three processes (a "brain" mail/chat service, a console
API, and a React frontend), each user's own Gmail connection, and their own private mail tree
and chat history.

If you're an AI agent (Claude Code or similar) setting this up on someone's behalf, follow this
document top to bottom in order — each numbered section has an explicit **Verify** step; don't
move on until it passes. Do not skip the Tesseract OCR install (§1.4) — it's a system binary,
not something `uv sync`/`npm install` can pull in, and its absence fails silently (image
attachments just come back unread) rather than with an error.

## Architecture, in one paragraph

`brain/viz_server.py` (port **8080**) does mail ingestion, classification, attachment reading,
and chat Q&A — one SQLite file per user under `brain/data/users/<id>/brain.db`. `console/backend`
(port **8000**) does login/accounts and stores chat session history (Postgres or SQLite via
`DATABASE_URL`). `console/frontend` (port **5173**, Vite dev server) is the React UI. The two
backends **must share one secret** (`OPS_SECRET_KEY`) because console/backend issues the login
JWT and brain verifies it — a mismatch 401s every request with no other symptom.

## 1. System prerequisites

Install these first; none of them come from `uv sync` or `npm install`.

### 1.1 Python 3.11+ and `uv`

```bash
# uv installs its own Python if needed, but you still need uv itself:
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
**Verify:** `uv --version` prints something (any recent version).

### 1.2 Node.js 20+ and npm

Get it from [nodejs.org](https://nodejs.org) or a version manager (`nvm`, `fnm`, etc).
**Verify:** `node --version` (v20 or newer) and `npm --version`.

### 1.3 Git

Whatever your OS ships, or `git-scm.com`. **Verify:** `git --version`.

### 1.4 Tesseract OCR (system binary — required for image attachments)

The mail pipeline reads text out of image attachments (photographed notices, poster-style
menus, screenshots) by shelling out to the `tesseract` binary directly — there's no Python
package to install for this, it must be on `PATH`.

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y tesseract-ocr

# macOS
brew install tesseract

# Windows — either:
choco install tesseract
# or download the installer from https://github.com/UB-Mannheim/tesseract/wiki and add its
# install directory to PATH
```
**Verify:** `tesseract --version` prints a version line (e.g. `tesseract 5.x.x`). If Tesseract
isn't installed, image attachments still get read — via a hosted vision-model fallback — but
only if `OPENROUTER_API_KEYS` is set (§3), and it's slower and less reliable than local OCR. Not
fatal, but don't skip this if you can help it.

### 1.5 (Optional) Postgres

Not required — the console backend works fine against a local SQLite file (`DATABASE_URL=sqlite:///./console-local.db`,
set in §3). Only set up Postgres if you specifically want it.

## 2. Clone & install

```bash
git clone <this-repo-url>
cd <repo-directory>

# Python deps (brain + console/backend)
uv sync

# Frontend deps
cd console/frontend
npm install
cd ../..
```
**Verify:** `uv run python -c "import fastapi, sqlalchemy, openpyxl, docx, pypdf"` exits with no
error; `ls console/frontend/node_modules` is non-empty.

## 3. Root `.env` — backend configuration

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```bash
# LLM calls (classification, chat Q&A, résumé/JD matching). Free-tier keys are fine.
# Sign up at openrouter.ai, generate one or more keys, comma-separate for rotation resilience.
OPENROUTER_API_KEYS=sk-or-v1-...

# Shared between console/backend and brain/viz_server — MUST be identical on both, or every
# request 401s with no other symptom. Any random string works for local dev.
OPS_SECRET_KEY=<pick any random string>

# Simplest path — no Postgres needed:
DATABASE_URL=sqlite:///./console-local.db

# Seeded automatically on first console/backend startup — this is your login.
OPS_ADMIN_EMAIL=admin@agent-os.local
OPS_ADMIN_PASSWORD=changeme
```

Everything else in `.env.example` (ClickUp, Slack, legacy IMAP app-password vars) is optional —
leave as placeholders unless you're specifically using those integrations. Gmail is connected
per-user from inside the console UI (§5), not via `.env`.

**Verify:** `uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); assert os.environ['OPENROUTER_API_KEYS']; assert os.environ['OPS_SECRET_KEY']"` exits with no error.

## 4. Frontend `.env.local` — the demo-mode trap

This file is git-ignored, so a fresh clone will **not** have it. Without it, the frontend
silently activates a built-in demo mode that blocks real login with no visible error message.

```bash
cd console/frontend
cat > .env.local <<'EOF'
VITE_API_BASE_URL=http://localhost:8000
VITE_BRAIN_API_BASE_URL=http://localhost:8080
EOF
cd ../..
```
**Verify:** `cat console/frontend/.env.local` shows both lines above.

## 5. Run all three services

Use three separate terminals (or background processes) — all three must stay running together.

```bash
# Terminal 1 — brain (mail ingestion, classification, attachments, chat Q&A)
uv run uvicorn brain.viz_server:app --port 8080

# Terminal 2 — console API (login, accounts, chat session history)
uv run uvicorn console.backend.main:app --port 8000

# Terminal 3 — frontend
cd console/frontend
npm run dev
```

> **Don't use `--reload` on either backend.** It has repeatedly failed to pick up code changes
> to `brain/viz_server.py` in practice (new routes kept 404ing after edits, even with the
> watcher supposedly active). If you need to pick up a change, stop the process and restart it
> plainly, as above.

**Verify:**
- `curl http://localhost:8080/` responds (the legacy mail-tree debug page), not connection-refused.
- `curl http://localhost:8000/health` responds with a JSON integrations status.
- Opening `http://localhost:5173` in a browser shows a real login screen, not a demo-mode banner.

## 6. First login and connecting Gmail

1. Open `http://localhost:5173`, log in with `OPS_ADMIN_EMAIL` / `OPS_ADMIN_PASSWORD` from §3.
2. Go to the **Integrations** (Applications) tab → **Connect** next to Gmail.
3. This triggers a one-time Google OAuth consent — a browser window opens on **the machine
   running the brain process** (not a redirect inside the web app) because the flow runs a local
   OAuth callback server server-side. Approve it with the Google account you want to ingest mail
   from.
4. On first-ever use of Gmail OAuth in this repo, you also need an OAuth **client** registered
   with Google (a one-time project-level setup, not per-user):
   - [Google Cloud Console](https://console.cloud.google.com) → **New Project** → any name.
   - **APIs & Services → OAuth consent screen** → User Type **External** → fill in app name,
     support email, developer email.
   - **Scopes** → add `https://mail.google.com/` (not `gmail.readonly` — this pipeline needs
     full-mailbox IMAP-equivalent access and needs write access to mark messages read).
   - **Test users** → add the Gmail account(s) you'll actually connect — skipping this gives
     `access_denied` at consent with no useful explanation.
   - **Credentials → Create Credentials → OAuth client ID → Desktop app** → download the JSON.
   - Save it at `~/.hermes/mail/credentials.json` (or set `GMAIL_CREDENTIALS_PATH` in `.env` to
     wherever you saved it).
5. Each teammate/account gets their **own** OAuth token and their own private mail tree — this
   step is per-user, done once per Google account you connect.

**Verify:** the Integrations tab shows Gmail as connected, and/or
`curl http://localhost:8080/api/mail/status -H "Authorization: Bearer <token from login>"`
returns `{"connected": true, "email": "..."}`.

## 7. Try it end to end

1. **Mail tab** → **Sync Mail** — watch the progress bar move through real per-email stages
   (connecting → fetched → filing each one → done); this streams from the server, it isn't a
   fake timer.
2. **View Map** — see the ingested mail organized into categories/topics.
3. **Chat tab** — ask a question about your ingested mail; answers come from an LLM call over
   your mail tree via OpenRouter.
4. **Profile tab** — add identifiers (your name, roll/registration number, etc.) used to match
   you inside spreadsheet/PDF attachments (shortlists, JD matching). This replaced an older
   static-config-file approach — identifiers now live per-account in the database, entered here.

## 8. Running the tests

```bash
# Python: classification, store, ingestion, attachments, console API — 189+ tests
uv run pytest -q

# Frontend typecheck + production build
cd console/frontend
npm run build

# Playwright end-to-end (one-time browser install, then run)
npx playwright install --with-deps chromium
npm run test:e2e
```

The E2E suite boots the real frontend and both real backends on isolated ports, faking only the
two things that would otherwise leave the machine: OpenRouter (a local stub via
`OPENROUTER_BASE_URL`) and Gmail (not exercised — a fixture seeds the per-user mail tree
directly). It uses a throwaway SQLite DB under `e2e/.tmp/` — no Postgres, no real credentials,
and it never touches your real `brain/data/users/` mail.

**Expected result:** all Python tests pass except one known pre-existing, unrelated failure —
`test_onboarding_creates_clickup_task_and_appears_in_roster` (a ClickUp-integration test broken
independently of this setup; confirmed present on a clean checkout). Anything else failing is a
real problem with your setup.

## 9. Troubleshooting

- **Login just spins / fails with no error** → you skipped §4 (`.env.local`); the frontend is in
  demo mode.
- **Every API call 401s** → `OPS_SECRET_KEY` differs between the two backend `.env`
  loads/processes, or one of them was started before you edited `.env`. Restart both.
- **A new route/edit to `brain/viz_server.py` 404s** → you're running with `--reload`; kill the
  process and restart plainly (§5).
- **Image attachments always say "not parsed" or come back empty** → Tesseract isn't on `PATH`
  (§1.4) *and* no `OPENROUTER_API_KEYS` is set for the vision fallback. Fix either.
- **`access_denied` during Gmail consent** → the Google account isn't added under **Test users**
  on the OAuth consent screen (§6, step 4).
- **Never run a one-off script against a real numeric `user_id`** (e.g. `brain/data/users/1/`)
  to "just test something" — that's a teammate's actual mail data. Use the E2E harness's
  isolated fixtures (`BRAIN_DATA_DIR`) or a disposable test account instead.

## 10. Known limitations

- Classification is a deterministic weighted-keyword scorer (`brain/mail_ingest.py`) arbitrating
  against the LLM's guess — it catches the common cases via `category_keywords` in
  `DEFAULT_CONFIG`/`brain/mail_config.json`, but isn't exhaustive for genuinely ambiguous mail.
  Low-confidence classifications are flagged for manual review in the Mail tab rather than
  silently guessed.
- Each user's mail tree (`brain/data/users/<id>/brain.db`) is local and git-ignored — nothing
  about mail content is shared via this repo.
