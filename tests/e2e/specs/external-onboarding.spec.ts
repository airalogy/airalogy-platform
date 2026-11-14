import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

for (const [locale, width] of [["en-US", 390], ["zh-CN", 1440]] as const) {
  test(`project external AI onboarding and connection management (${locale})`, async ({ page, request }, testInfo) => {
    const fixtures = await loadFixtures()
    const language = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "zh-CN" ? "zh-cn" : "en-us"}.json`, import.meta.url), "utf8"))
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signIn.ok()).toBeTruthy()
    const headers = { "Auth-Token": (await signIn.json()).token }
    const policy = await request.get(`${api}/external-access/labs/${fixtures.lab.id}/policy`, { headers })
    const previousPolicy = await policy.json()
    expect((await request.put(`${api}/external-access/labs/${fixtures.lab.id}/policy`, { headers, data: { enabled: true, blocked_fields: [], expected_revision: previousPolicy.revision } })).ok()).toBeTruthy()
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    await page.setViewportSize({ width, height: 900 })
    const project = `/orgs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.goto(`${project}/protocols`)
    await page.locator(".n-tabs-tab").getByText(language.page.analysis.title, { exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${project}/analysis$`))
    await page.getByTestId("analysis-external-view").click()
    await expect(page).toHaveURL(new RegExp(`${project}/analysis\\?view=external`))
    await page.getByTestId("external-connect-project").click()
    const setup = page.getByTestId("external-connection-setup")
    await expect(setup.getByTestId("external-fixed-project")).toContainText("Quickstart Protocol Testing")
    await expect(setup.getByTestId("external-grant-project")).toHaveCount(0)
    await expect(setup.getByTestId("external-selected-scopes")).not.toContainText(language.externalResearch.exportRecords)
    await setup.getByTestId("external-preset-analyze").click()
    await expect(setup.getByTestId("external-preset-analyze")).toHaveAttribute("aria-pressed", "true")
    await expect(setup.getByTestId("external-preset-read")).toHaveAttribute("aria-pressed", "false")
    await expect(setup.getByTestId("external-selected-scopes")).toContainText(language.externalResearch.exportRecords)
    await expect(setup.getByTestId("external-selected-scopes")).not.toContainText(language.externalResearch.publish)
    await setup.getByTestId("external-grant-name").locator("input").fill(`Synthetic onboarding ${randomUUID()}`)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`onboarding-${locale}.png`) })
    const created = page.waitForResponse(r => r.url().endsWith("/external-access/grants") && r.request().method() === "POST")
    await setup.getByTestId("external-grant-create").click()
    const response = await created
    expect(response.ok()).toBeTruthy()
    const { token, grant } = await response.json()
    try {
      expect(grant.project_id).toBe(fixtures.project.id)
      expect(grant.scopes.sort()).toEqual(["protocols:read", "records:read", "records:export", "analysis:read", "analysis:write"].sort())
      await expect(setup.getByTestId("external-grant-token").locator("input")).toHaveValue(token)
      await setup.getByTestId("external-test-connection").click()
      await expect(setup.getByTestId("external-connection-result")).toContainText(language.externalOnboarding.tokenVerified)
      expect(await page.evaluate(value => JSON.stringify(localStorage).includes(value) || JSON.stringify(sessionStorage).includes(value), token)).toBeFalsy()
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`connected-${locale}.png`), mask: [setup.getByTestId("external-grant-token")] })
      await setup.getByRole("button", { name: language.externalAccess.dismissToken, exact: true }).click()
      await expect(page.getByTestId("external-grant-token")).toHaveCount(0)
      await page.goto(`${project}/analysis?view=external`)
      await page.getByTestId("external-manage-connections").click()
      await page.getByTestId(`external-grant-${grant.id}`).getByRole("button", { name: language.externalAccess.revoke, exact: true }).click()
      const revoked = page.waitForResponse(r => r.url().endsWith(`/external-access/grants/${grant.id}`) && r.request().method() === "DELETE")
      await page.locator(".n-popconfirm__action").getByRole("button").last().click()
      expect((await revoked).ok()).toBeTruthy()
      expect((await request.post(`${api}/external-access/tools/access_context`, { headers: { Authorization: `Bearer ${token}` }, data: {} })).status()).toBe(401)
    }
    finally {
      await request.delete(`${api}/external-access/grants/${grant.id}`, { headers })
    }
  })
}
