import type { Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Uses an isolated single-organization deployment")
test.use({ storageState: { cookies: [], origins: [] } })
test.beforeEach(({ page }) => page.setDefaultTimeout(15000))

async function login(page: Page, account: "owner" | "viewer") {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(`dev.${account}@airalogy.dev`)
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
}

test("owner can reach management directly and save a one-character name without changing its UID", async ({ page }, testInfo) => {
  await login(page, "owner")
  const status = await (await page.request.get("/api/instance")).json()
  const original = status.organization
  await page.setViewportSize({ width: 1440, height: 980 })
  await page.getByTestId("organization-management-entry").click()
  await expect(page).toHaveURL(/\/organization\/members$/)
  await page.locator('.n-tabs-tab[data-name="lab-settings"]').click()
  const input = page.getByTestId("organization-settings-name").locator("input")
  const uid = page.getByTestId("organization-settings-uid").locator("input")
  await expect(uid).toHaveValue(original.uid)
  await expect(uid).toHaveAttribute("readonly")
  const originalDescription = await page.locator("textarea").first().inputValue()
  let auth: string | undefined
  let updates = 0
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().endsWith(`/organizations/${original.id}`))
      updates++
  })
  try {
    await input.fill(" \t ")
    await page.getByRole("button", { name: zh.page.labs.settingsPage.saveAction, exact: true }).click()
    await expect(page.locator(".n-form-item-feedback__line").first()).toBeVisible()
    expect(updates).toBe(0)
    await input.fill("  研  ")
    const saved = page.waitForResponse(response => response.request().method() === "PUT" && response.url().endsWith(`/organizations/${original.id}`))
    await page.getByRole("button", { name: zh.page.labs.settingsPage.saveAction, exact: true }).click()
    const response = await saved
    auth = (await response.request().allHeaders())["auth-token"]
    expect(response.ok(), await response.text()).toBeTruthy()
    expect(response.request().postDataJSON().name).toBe("研")
    await expect(page.getByTestId("single-lab-identity")).toHaveText("研")
    await page.reload()
    await expect(input).toHaveValue("研")
    await expect(uid).toHaveValue(original.uid)
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({ width, height: 980 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.screenshot({ path: testInfo.outputPath(`organization-settings-${width}.png`), fullPage: true })
    }
    const header = page.getByTestId("app-shell-header")
    await header.getByRole("button", { name: zh.common.more, exact: true }).click()
    await page.locator(".n-dropdown-menu").getByText("组织管理", { exact: true }).click()
    await expect(page).toHaveURL(/\/organization\/members$/)
  }
  finally {
    if (auth) {
      const restored = await page.request.put(`/api/organizations/${original.id}`, { headers: { "Auth-Token": auth }, data: { name: original.name, description: originalDescription } })
      expect(restored.ok(), await restored.text()).toBeTruthy()
    }
  }
})

test("ordinary members see their member directory instead of administrator controls", async ({ page }) => {
  await login(page, "viewer")
  const status = await (await page.request.get("/api/instance")).json()
  await page.setViewportSize({ width: 1440, height: 980 })
  // Wait for the authenticated membership request, not just the initial header render.
  await page.goto(`/labs/${status.lab.uid}/members`)
  await expect(page.locator('.n-tabs-tab[data-name="lab-members"]')).toBeVisible()
  await expect(page.getByTestId("organization-management-entry")).toHaveCount(0)
  await expect(page.locator('.n-tabs-tab[data-name="lab-settings"]')).toHaveCount(0)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 980 })
    await page.getByTestId("app-shell-header").getByRole("button", { name: zh.common.more, exact: true }).click()
    await expect(page.locator(".n-dropdown-menu").getByText("组织管理", { exact: true })).toHaveCount(0)
    await expect(page.getByText(zh.page.singleLabWorkspace.membersAccess, { exact: true }).last()).toBeVisible()
    await page.keyboard.press("Escape")
  }
})

test("organization owner configures an AI model and can remove the saved key", async ({ page }) => {
  await login(page, "owner")
  await page.goto("/organization/settings")
  const card = page.getByTestId("organization-ai-settings")
  const toggle = card.getByRole("switch")
  const field = card.locator('input[type="password"]')
  const save = card.getByRole("button", { name: zh.page.organization.ai.save })
  const testKey = card.getByRole("button", { name: zh.page.organization.ai.test })
  await expect(toggle).toBeVisible()
  if (await toggle.isDisabled()) {
    await expect(card.getByText(zh.page.organization.ai.blocked)).toBeVisible()
    await expect(testKey).toBeDisabled()
    return
  }
  // The provider directory alone is simulated. Saving and read-back use the real API.
  await page.route("**/ai-settings/test", route => route.fulfill({ json: { status: "ok" } }))
  await field.fill("synthetic-browser-config-only")
  await testKey.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.ok)
  await toggle.click()
  await save.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.saved)
  await page.reload()
  await expect(toggle).toBeChecked()
  await expect(field).toHaveValue("")
  await expect(field).toHaveAttribute("placeholder", zh.page.organization.ai.keepKey)
  await toggle.click()
  await card.getByRole("checkbox").click()
  await save.click()
  await expect(card.getByRole("status")).toHaveText(zh.page.organization.ai.saved)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(toggle).not.toBeChecked()
  await expect(field).toHaveAttribute("placeholder", zh.page.organization.ai.enterKey)
})
