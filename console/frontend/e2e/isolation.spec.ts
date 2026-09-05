import { expect, test } from "@playwright/test"

import { E2E } from "../playwright.config"
import { login, seedBrain } from "./helpers"

// Each account gets its own Gmail connection, its own slice of the brain, and its own chat
// history. This spec is the guard on that boundary: it drives the real APIs as two different
// users and asserts neither can observe the other's data.

const SECOND_USER = { email: "second@e2e.local", password: "second-password" }

async function ensureSecondUser(adminToken: string): Promise<void> {
  const res = await fetch(`${E2E.consoleUrl}/auth/users`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`,
    },
    body: JSON.stringify({ ...SECOND_USER, role: "developer" }),
  })
  // 409 just means a previous run already created them.
  if (!res.ok && res.status !== 409) {
    throw new Error(`could not create second user: ${res.status} ${await res.text()}`)
  }
}

test.describe("per-user isolation", () => {
  test("one user's mail is invisible to another", async () => {
    const admin = await login()
    seedBrain(admin.userId)
    await ensureSecondUser(admin.token)
    const other = await login(SECOND_USER.email, SECOND_USER.password)

    const read = async (token: string) => {
      const res = await fetch(`${E2E.brainUrl}/api/mail_tree`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      return (await res.json()) as { children?: { name: string }[] }
    }

    const mine = await read(admin.token)
    expect(mine.children?.map((c) => c.name)).toContain("Placements")

    // The second user never had mail ingested, so their tree must be empty — not the admin's.
    const theirs = await read(other.token)
    expect(theirs.children ?? []).toHaveLength(0)
  })

  test("one user's chat sessions are invisible to another", async () => {
    const admin = await login()
    await ensureSecondUser(admin.token)
    const other = await login(SECOND_USER.email, SECOND_USER.password)

    const created = await fetch(`${E2E.consoleUrl}/chat/sessions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${admin.token}` },
    })
    const session = (await created.json()) as { id: number }

    const theirList = await fetch(`${E2E.consoleUrl}/chat/sessions`, {
      headers: { Authorization: `Bearer ${other.token}` },
    })
    const sessions = (await theirList.json()) as { id: number }[]
    expect(sessions.map((s) => s.id)).not.toContain(session.id)

    // Fetching it directly must 404 — not 403, which would confirm the id exists.
    const direct = await fetch(`${E2E.consoleUrl}/chat/sessions/${session.id}`, {
      headers: { Authorization: `Bearer ${other.token}` },
    })
    expect(direct.status).toBe(404)
  })

  test("the brain rejects unauthenticated and forged tokens", async () => {
    const anonymous = await fetch(`${E2E.brainUrl}/api/mail_tree`)
    expect(anonymous.status).toBe(401)

    const forged = await fetch(`${E2E.brainUrl}/api/mail_tree`, {
      headers: { Authorization: "Bearer not-a-real-token" },
    })
    expect(forged.status).toBe(401)
  })
})
