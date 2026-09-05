import { type Page, expect, test } from "@playwright/test"

import { login, resetChats, seedBrain, signIn } from "./helpers"

// "STUBBED ANSWER:" comes from e2e/support/fake_openrouter.py — seeing it in the transcript
// proves the whole chain ran: browser -> console/backend -> brain -> (fake) LLM -> DB.
const STUB = /STUBBED ANSWER:/

/**
 * The conversation pane only. Scoping matters: the sidebar lists each session by its first
 * question, so an unscoped getByText would match history entries as well as messages.
 */
const thread = (page: Page) => page.getByTestId("chat-thread")

/**
 * The user's own bubble. `exact` matters because the stub echoes the question back, so a
 * substring match would also hit the assistant's reply.
 */
const userMessage = (page: Page, text: string) => thread(page).getByText(text, { exact: true })

async function ask(page: Page, question: string): Promise<void> {
  const composer = page.getByPlaceholder("Ask a question…")
  await composer.fill(question)
  await composer.press("Enter")
  await expect(thread(page).getByText(STUB)).toBeVisible({ timeout: 30_000 })
}

test.describe("persistent chat", () => {
  test.beforeEach(async () => {
    const { token, userId } = await login()
    seedBrain(userId)
    await resetChats(token)
  })

  test("a conversation persists across a page reload", async ({ page }) => {
    await signIn(page)
    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await ask(page, "What did Accenture say?")
    await expect(userMessage(page, "What did Accenture say?")).toBeVisible()

    // The whole point of the feature: it is still there after a refresh.
    await page.reload()
    await expect(userMessage(page, "What did Accenture say?")).toBeVisible()
    await expect(thread(page).getByText(STUB)).toBeVisible()
  })

  test("messages do not bleed between sessions", async ({ page }) => {
    await signIn(page)

    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await ask(page, "First conversation question")

    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await expect(userMessage(page, "First conversation question")).toHaveCount(0)

    await ask(page, "Second conversation question")
    await expect(userMessage(page, "First conversation question")).toHaveCount(0)
    await expect(userMessage(page, "Second conversation question")).toBeVisible()
  })

  test("a past conversation can be reopened from the sidebar", async ({ page }) => {
    await signIn(page)
    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await ask(page, "Reopen me later")

    // Start a different chat, then click back into the first from the history list.
    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await expect(userMessage(page, "Reopen me later")).toHaveCount(0)

    await page.getByRole("button", { name: /^Reopen me later/ }).first().click()
    await expect(userMessage(page, "Reopen me later")).toBeVisible()
    await expect(thread(page).getByText(STUB)).toBeVisible()
  })
})

test.describe("chat history search", () => {
  test.beforeEach(async () => {
    const { token } = await login()
    await resetChats(token)
  })

  test("filters the sidebar by conversation title", async ({ page }) => {
    await signIn(page)

    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await ask(page, "Question about placements")
    await page.getByRole("button", { name: "New chat", exact: true }).click()
    await ask(page, "Question about lectures")

    const search = page.getByLabel("Search chats")
    await search.fill("placements")
    await expect(page.getByRole("button", { name: /^Question about placements/ })).toBeVisible()
    await expect(page.getByRole("button", { name: /^Question about lectures/ })).toHaveCount(0)

    await search.fill("zzz-no-such-chat")
    await expect(page.getByText(/no chats match/i)).toBeVisible()

    await search.clear()
    await expect(page.getByRole("button", { name: /^Question about lectures/ })).toBeVisible()
  })
})
