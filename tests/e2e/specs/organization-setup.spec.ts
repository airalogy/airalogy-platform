import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8"))
const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))

// Mock only an uninitialized instance; never reset or bootstrap the running instance.
test.use({ storageState: { cookies: [], origins: [] } })

for (const [locale, messages] of [["zh-CN", zh], ["en-US", en]] as const) {
  test(`setup confirms deployment identity without allowing a rename (${locale})`, async ({ page }, testInfo) => {
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    await page.route("**/api/instance", route => route.fulfill({
      json: {
        deployment_mode: "single_organization",
        single_lab: true,
        single_organization: true,
        initialized: false,
        signup_mode: "invite_only",
        bootstrap_token_required: false,
        site_url: "http://localhost",
        lab_structure_mode: "flat",
        organization_structure_mode: "flat",
        documentation_profile: "customer_managed",
        documentation_url: "/docs/",
        support_url: "",
        ai_enabled: false,
        sms_login_enabled: false,
        sms_signup_required: false,
        enabled_chat_models: [],
        lab: null,
        organization: null,
        default_organization_uid: "synthetic_company",
        default_organization_name: "Synthetic Company",
        default_organization_type: "company",
      },
    }))
    await page.route("**/api/instance/bootstrap", route => route.fulfill({
      status: 409,
      json: { detail: "The configured organization identifier has changed. Reload setup and confirm it before continuing." },
    }))
    await page.goto("/setup")
    const labels = messages.page.instance
    const organization = page.getByRole("group", { name: messages.page.organization.setupSection, exact: true })
    const administrator = page.getByRole("group", { name: labels.administratorAccount, exact: true })
    await expect(organization.getByTestId("setup-organization-name")).toBeVisible()
    await expect(administrator).toContainText(labels.administratorAccountHint)
    await expect(administrator).toContainText(labels.personalUsername)
    await expect(administrator.getByTestId("setup-organization-name")).toHaveCount(0)
    const identifier = page.getByTestId("setup-organization-uid").locator("input")
    await expect(identifier).toHaveValue("synthetic_company")
    await expect(identifier).toHaveAttribute("readonly")
    await expect(page.locator("#setup-organization-uid-hint")).toHaveText(messages.page.organization.setupUidHint)
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 980 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.screenshot({ path: testInfo.outputPath(`setup-${locale}-${width}.png`), fullPage: true })
    }
    await page.getByTestId("setup-organization-name").locator("input").fill("Synthetic Renamed Company")
    await page.getByPlaceholder(labels.administratorNamePlaceholder, { exact: true }).fill("Synthetic Owner")
    const username = page.getByPlaceholder(labels.personalUsernamePlaceholder, { exact: true })
    await username.fill("synthetic_company")
    await username.press("Tab")
    await expect(administrator.getByText(labels.personalUsernameDistinct, { exact: true })).toBeVisible()
    await username.fill("synthetic_owner")
    await page.getByPlaceholder(labels.email, { exact: true }).fill("owner@example.org")
    await page.getByPlaceholder(labels.password, { exact: true }).fill("Synthetic123!")
    await page.getByPlaceholder(labels.confirmPassword, { exact: true }).fill("Synthetic123!")
    const submission = page.waitForRequest(r => r.url().endsWith("/api/instance/bootstrap"))
    await page.getByRole("button", { name: labels.completeSetup, exact: true }).click()
    const request = await submission
    expect(request.postDataJSON()).toMatchObject({
      organization_uid: "synthetic_company",
      organization_name: "Synthetic Renamed Company",
      organization_type: "company",
      name: "Synthetic Owner",
      username: "synthetic_owner",
    })
    await expect(page).toHaveURL(/\/setup$/)
    await expect(identifier).toHaveValue("synthetic_company")
    await expect(page.getByTestId("setup-organization-name").locator("input")).toHaveValue("Synthetic Renamed Company")
  })
}
