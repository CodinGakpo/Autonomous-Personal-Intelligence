import { execFileSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { type Page, expect } from "@playwright/test"

import { E2E, pythonEnv } from "../playwright.config"

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..")

/** Log in through the real /auth/login and return the bearer token + user id. */
export async function login(
  email = E2E.adminEmail,
  password = E2E.adminPassword,
): Promise<{ token: string; userId: number }> {
  const res = await fetch(`${E2E.consoleUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error(`login failed: ${res.status} ${await res.text()}`)
  const { token } = (await res.json()) as { token: string }

  const me = await fetch(`${E2E.consoleUrl}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const { id } = (await me.json()) as { id: number }
  return { token, userId: id }
}

/**
 * Write the mail tree that Gmail ingestion would have produced, for one user's own brain.
 * Runs the same seeding module a developer would run by hand, so the specs exercise real
 * store/graph code rather than a JS-side fake.
 */
export function seedBrain(userId: number): void {
  execFileSync("uv", ["run", "python", "-m", "e2e.support.seed", "--user-id", String(userId)], {
    cwd: REPO_ROOT,
    stdio: "pipe",
    // Must match the servers' env, or the seed writes the per-user brain DB and the Gmail
    // token placeholder somewhere the running services aren't looking.
    env: { ...process.env, ...pythonEnv },
  })
}

/**
 * Delete every chat session for a user.
 *
 * The suite's SQLite database is reused between runs, so without this a session titled by an
 * earlier run collides with this one's and assertions match two elements. Uses only the public
 * API, so it stays honest about what a client can do.
 */
export async function resetChats(token: string): Promise<void> {
  const res = await fetch(`${E2E.consoleUrl}/chat/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const sessions = (await res.json()) as { id: number }[]
  for (const session of sessions) {
    await fetch(`${E2E.consoleUrl}/chat/sessions/${session.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    })
  }
}

/** Sign in through the UI and land on the app shell. */
export async function signIn(page: Page): Promise<void> {
  await page.goto("/")
  await page.getByLabel("Email").fill(E2E.adminEmail)
  await page.getByLabel("Password").fill(E2E.adminPassword)
  await page.getByRole("button", { name: /sign in/i }).click()
  await expect(page.getByRole("button", { name: "Chat", exact: true })).toBeVisible()
}

/** Seed the signed-in user's mail tree, then open the Mail tab with the mindmap showing. */
export async function openMailMap(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Mail", exact: true }).click()
  await page.getByRole("button", { name: /view map/i }).click()
  await expect(page.locator(".mail-mindmap-root")).toBeVisible()
}

/**
 * Click a node in the D3 mindmap.
 *
 * The tree animates every expand/collapse over ~260ms and re-binds its selection as it goes,
 * so Playwright's stability check sees a moving (and sometimes detached) element. Waiting out
 * the transition and forcing the click is the reliable way to drive an animated SVG canvas.
 */
/**
 * Open a thread's detail panel, expanding only the levels that aren't already showing.
 *
 * The map renders some levels expanded already, and every node click is a *toggle* — so
 * unconditionally clicking the category would collapse the branch instead of opening it.
 */
export async function openThread(
  page: Page,
  { category, topic, thread }: { category: string; topic: string; thread: string },
): Promise<void> {
  if ((await page.locator(".node.mail_thread", { hasText: thread }).count()) === 0) {
    if ((await page.locator(".node.mail_topic", { hasText: topic }).count()) === 0) {
      await clickMapNode(page, "mail_category", category)
    }
    await clickMapNode(page, "mail_topic", topic)
  }
  await clickMapNode(page, "mail_thread", thread)
}

export async function clickMapNode(page: Page, type: string, label: string): Promise<void> {
  await expect(page.locator(`.node.${type}`, { hasText: label }).first()).toBeVisible()
  await page.waitForTimeout(500) // the D3 transition (DURATION = 260ms) plus headroom

  // Resolve and dispatch inside the page, atomically. A Node-side element handle goes stale
  // the moment D3 re-binds its selection mid-transition, which no amount of force or
  // actionability-skipping can survive; querying at dispatch time cannot race.
  await page.evaluate(
    ({ type, label }) => {
      const target = Array.from(document.querySelectorAll(`.node.${type}`)).find((n) =>
        (n.textContent || "").includes(label),
      )
      if (!target) throw new Error(`no .node.${type} containing "${label}"`)
      target.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    },
    { type, label },
  )
}
