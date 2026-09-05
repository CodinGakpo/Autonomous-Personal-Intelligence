import { expect, test } from "@playwright/test"

import { E2E } from "../playwright.config"
import { login, openMailMap, openThread, seedBrain, signIn } from "./helpers"

/** Read the mail tree straight from the brain API, to assert on stored state not just pixels. */
async function fetchTree(token: string) {
  const res = await fetch(`${E2E.brainUrl}/api/mail_tree`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return (await res.json()) as {
    children?: { name: string; children?: { name: string }[] }[]
  }
}

test.describe("reclassifying a misfiled thread", () => {
  let token: string

  test.beforeEach(async () => {
    const session = await login()
    token = session.token
    // Reset to the known-bad starting state: the yoga competition filed under Placements.
    seedBrain(session.userId)
  })

  test("the seeded yoga thread starts misfiled under Placements and is flagged", async () => {
    const tree = await fetchTree(token)
    const placements = tree.children?.find((c) => c.name === "Placements")
    expect(placements?.children?.map((t) => t.name)).toContain("Yoga Competition")
  })

  test("moving the thread to General College updates the tree and clears the flag", async ({
    page,
  }) => {
    await signIn(page)
    await openMailMap(page)

    // Drill into Placements -> Yoga Competition -> the thread itself.
    await openThread(page, {
      category: "Placements",
      topic: "Yoga Competition",
      thread: "Yoga Competition 2026",
    })

    const panel = page.locator(".mail-mindmap-detail.open")
    await expect(panel).toBeVisible()
    // It was flagged as a low-confidence guess, which is how a user would notice it at all.
    await expect(panel.getByText(/low confidence/i)).toBeVisible()

    await panel.getByLabel("Move to category").fill("General College")
    await panel.getByRole("button", { name: "Move" }).click()

    // The panel closes (its node belongs to the now-stale tree) and the map refreshes.
    await expect(panel).toBeHidden()

    await expect
      .poll(async () => {
        const tree = await fetchTree(token)
        const general = tree.children?.find((c) => c.name === "General College")
        return general?.children?.map((t) => t.name) ?? []
      })
      .toContain("Yoga Competition")

    const tree = await fetchTree(token)
    // Placements had only this one topic left, so pruning should have removed the whole branch
    // rather than leaving an empty ghost category behind.
    const placements = tree.children?.find((c) => c.name === "Placements")
    expect(placements?.children?.map((t) => t.name) ?? []).not.toContain("Yoga Competition")

    // And the correction cleared the review flag.
    await expect(page.locator(".node circle.review-flag")).toHaveCount(0)
  })

  test("a correction teaches the classifier for next time", async () => {
    const res = await fetch(`${E2E.brainUrl}/api/mail/reclassify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ thread_id: "mail:thread:102", category: "General College" }),
    })
    expect(res.ok).toBe(true)
    const result = (await res.json()) as { learned_keywords: string[] }

    // The distinctive words of the corrected subject become General College vocabulary, so a
    // later "yoga" mail isn't misfiled the same way. Noise is filtered out.
    expect(result.learned_keywords).toContain("yoga")
    expect(result.learned_keywords).toContain("competition")
    expect(result.learned_keywords).not.toContain("2026")
  })
})

test.describe("asking about a mail thread", () => {
  test.beforeEach(async () => {
    const session = await login()
    seedBrain(session.userId)
  })

  test("carries the thread into a fresh chat with the question pre-filled", async ({ page }) => {
    await signIn(page)
    await openMailMap(page)
    await openThread(page, {
      category: "Placements",
      topic: "Accenture",
      thread: "Accenture Off-Campus Drive 2026",
    })

    await page.locator(".mail-mindmap-detail.open").getByRole("button", { name: /ask about this/i }).click()

    // Lands on the Chat tab with the question ready to edit, not already sent.
    const composer = page.getByPlaceholder("Ask a question…")
    await expect(composer).toHaveValue(/Accenture Off-Campus Drive 2026/)
    await expect(page.getByTestId("chat-thread").getByText(/STUBBED ANSWER:/)).toHaveCount(0)

    // Sending it works from there.
    await composer.press("Enter")
    await expect(page.getByTestId("chat-thread").getByText(/STUBBED ANSWER:/)).toBeVisible({
      timeout: 30_000,
    })
  })
})

test.describe("review queue", () => {
  let token: string

  test.beforeEach(async () => {
    const session = await login()
    token = session.token
    seedBrain(session.userId)
  })

  test("surfaces a low-confidence thread and fixes it in place", async ({ page }) => {
    await signIn(page)
    await page.getByRole("button", { name: "Mail", exact: true }).click()

    // The whole point: the misfiled thread is visible without hunting through the mail map.
    const queue = page.getByTestId("review-queue")
    await expect(queue).toBeVisible()
    await expect(queue.getByText("Yoga Competition 2026")).toBeVisible()
    await expect(queue.getByText(/needs review/i)).toBeVisible()

    // The suggested fix is offered even though General College doesn't exist in the tree yet.
    const picker = queue.getByLabel("Category for Yoga Competition 2026")
    await picker.selectOption("General College")
    await queue.getByRole("button", { name: /confirm/i }).click()

    await expect(queue.getByText(/all caught up/i)).toBeVisible()
    await expect(queue.getByText("Yoga Competition 2026")).toHaveCount(0)

    // ...and it really moved, not just disappeared from the list.
    const res = await fetch(`${E2E.brainUrl}/api/mail_tree`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const tree = (await res.json()) as { children?: { name: string; children?: { name: string }[] }[] }
    const general = tree.children?.find((c) => c.name === "General College")
    expect(general?.children?.map((t) => t.name)).toContain("Yoga Competition")
  })

  test("stays hidden when nothing needs review", async ({ page }) => {
    // Clear the only flagged thread first.
    await fetch(`${E2E.brainUrl}/api/mail/reclassify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ thread_id: "mail:thread:102", category: "General College" }),
    })

    await signIn(page)
    await page.getByRole("button", { name: "Mail", exact: true }).click()
    await expect(page.getByRole("button", { name: /view map/i })).toBeVisible()
    await expect(page.getByTestId("review-queue")).toHaveCount(0)
  })
})
