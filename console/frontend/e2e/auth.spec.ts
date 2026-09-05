import { expect, test } from "@playwright/test"

import { E2E } from "../playwright.config"
import { signIn } from "./helpers"

test.describe("authentication", () => {
  test("an unauthenticated visitor gets the login gate, not the app", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByText(/ops console/i)).toBeVisible()
    await expect(page.getByLabel("Password")).toBeVisible()
    // The app shell must not be reachable without signing in.
    await expect(page.getByRole("button", { name: "Chat", exact: true })).toHaveCount(0)
  })

  test("bad credentials are rejected", async ({ page }) => {
    await page.goto("/")
    await page.getByLabel("Email").fill(E2E.adminEmail)
    await page.getByLabel("Password").fill("definitely-wrong")
    await page.getByRole("button", { name: /sign in/i }).click()
    await expect(page.getByText(/invalid credentials/i)).toBeVisible()
  })

  test("signing in reveals the app and the session survives a reload", async ({ page }) => {
    await signIn(page)
    await page.reload()
    await expect(page.getByRole("button", { name: "Chat", exact: true })).toBeVisible()
    await expect(page.getByLabel("Password")).toHaveCount(0)
  })

  test("a corrupted token bounces back to the login gate", async ({ page }) => {
    await signIn(page)
    await page.evaluate(() => localStorage.setItem("ops_token", "not-a-real-token"))
    await page.reload()
    await expect(page.getByLabel("Password")).toBeVisible()
  })

  test("logging out returns to the login gate", async ({ page }) => {
    await signIn(page)
    await page.getByRole("button", { name: /log out/i }).click()
    await expect(page.getByLabel("Password")).toBeVisible()
  })
})
