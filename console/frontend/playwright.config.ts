import path from "node:path"
import { fileURLToPath } from "node:url"

import { defineConfig, devices } from "@playwright/test"

// package.json sets "type": "module", so __dirname doesn't exist here.
const HERE = path.dirname(fileURLToPath(import.meta.url))

// The suite runs the REAL stack — this frontend, console/backend, and brain/viz_server — and
// fakes only the two boundaries that genuinely reach outside the machine:
//   * OpenRouter, via OPENROUTER_BASE_URL pointing at e2e/support/fake_openrouter.py
//   * Gmail/IMAP, which isn't exercised at all; e2e/support/seed.py writes the mail tree that
//     ingestion would have produced (global setup does this).
const REPO_ROOT = path.resolve(HERE, "../..")
// SQLAlchemy URLs and env paths want forward slashes, even on Windows.
const POSIX_ROOT = REPO_ROOT.split(path.sep).join("/")

const FRONTEND_PORT = 5199
const CONSOLE_PORT = 8111
const BRAIN_PORT = 8112
const OPENROUTER_PORT = 8113

// Both backends verify the same JWT, so they must share this. Tests sign in through the real
// /auth/login, so the seeded admin credentials matter too.
const SECRET = "e2e-secret-key-at-least-32-bytes-long!"
const ORIGIN = `http://127.0.0.1:${FRONTEND_PORT}`

export const E2E = {
  origin: ORIGIN,
  adminEmail: "admin@e2e.local",
  adminPassword: "e2e-password",
  consoleUrl: `http://127.0.0.1:${CONSOLE_PORT}`,
  brainUrl: `http://127.0.0.1:${BRAIN_PORT}`,
}

export const pythonEnv = {
  OPS_SECRET_KEY: SECRET,
  // Postgres isn't needed: console/backend's configure_engine has a sqlite branch and seeds the
  // admin itself on startup. The file lives under the repo's git-ignored e2e scratch dir.
  DATABASE_URL: `sqlite:///${POSIX_ROOT}/e2e/.tmp/e2e.db`,
  OPS_ADMIN_EMAIL: E2E.adminEmail,
  OPS_ADMIN_PASSWORD: E2E.adminPassword,
  BRAIN_API_BASE_URL: E2E.brainUrl,
  // localhost and 127.0.0.1 are distinct origins to the browser — this must match ORIGIN exactly.
  OPS_CORS_ORIGINS: ORIGIN,
  BRAIN_CORS_ORIGINS: ORIGIN,
  OPENROUTER_BASE_URL: `http://127.0.0.1:${OPENROUTER_PORT}`,
  OPENROUTER_API_KEYS: "e2e-fake-key",
  // Keeps the placeholder Gmail token out of the developer's real ~/.hermes directory.
  GMAIL_TOKEN_PATH: `${POSIX_ROOT}/e2e/.tmp/gmail-token.json`,
  // Keeps the suite's per-user mail databases out of brain/data, which a real dev account
  // also uses — user ids collide across the dev and test console databases.
  BRAIN_DATA_DIR: `${POSIX_ROOT}/e2e/.tmp/brain-data`,
  PYTHONUTF8: "1",
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // one shared backend + one SQLite file per run
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: process.env.CI ? "line" : [["list"]],
  use: {
    baseURL: ORIGIN,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run python -m e2e.support.fake_openrouter --port ${OPENROUTER_PORT}`,
      url: `http://127.0.0.1:${OPENROUTER_PORT}/docs`,
      cwd: REPO_ROOT,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `uv run uvicorn brain.viz_server:app --host 127.0.0.1 --port ${BRAIN_PORT}`,
      url: `http://127.0.0.1:${BRAIN_PORT}/docs`,
      cwd: REPO_ROOT,
      env: pythonEnv,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `uv run uvicorn console.backend.main:app --host 127.0.0.1 --port ${CONSOLE_PORT}`,
      url: `http://127.0.0.1:${CONSOLE_PORT}/health`,
      cwd: REPO_ROOT,
      env: pythonEnv,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // VITE_API_BASE_URL must be non-empty or api.ts's DEMO_MODE short-circuits login and the
      // app is unreachable. Vite inlines these at transform time, so they cannot be set later
      // from the test process.
      command: `npm run dev -- --port ${FRONTEND_PORT} --host 127.0.0.1 --strictPort`,
      url: ORIGIN,
      cwd: HERE,
      env: {
        VITE_API_BASE_URL: E2E.consoleUrl,
        VITE_BRAIN_API_BASE_URL: E2E.brainUrl,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
