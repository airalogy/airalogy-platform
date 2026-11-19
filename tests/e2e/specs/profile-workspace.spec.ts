import type { Page } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { changeAccountLanguage, loadFixtures } from "./fixtures"

// Use real local profile data and permissions. Override only the instance's
// presentation capabilities to exercise both deployment modes in one run.
async function presentInstance(page: Page, mode: "single_organization" | "single_lab" | "community") {
  const single = mode !== "community"
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.route("**/api/instance", async (route) => {
    const response = await route.fetch()
    const status = await response.json()
    const organization = { ...(await loadFixtures()).lab, name: "Synthetic organization", organization_type: mode === "single_lab" ? "laboratory" : "company" }
    await route.fulfill({ response, json: {
      ...status,
      deployment_mode: mode,
      single_lab: single,
      single_organization: single,
      lab_structure_mode: single ? "structured" : "flat",
      organization_structure_mode: single ? "structured" : "flat",
      organization: single ? organization : null,
      lab: single ? organization : null,
      default_organization_uid: single ? "dev_lab" : "",
    } })
  })
}

for (const mode of ["single_organization", "single_lab", "community"] as const) {
  test(`${mode}: profile shows the right workspace context and switches languages without reloading`, async ({ page }, testInfo) => {
    await presentInstance(page, mode)
    const single = mode !== "community"
    const failures: string[] = []
    const educationQueries: string[] = []
    page.on("pageerror", error => failures.push(error.message))
    page.on("request", (request) => {
      const url = new URL(request.url())
      if (url.searchParams.get("lab_uid") === "edu")
        educationQueries.push(url.pathname)
    })
    await page.goto("/users/dev_owner")
    const summary = page.getByTestId("profile-summary")
    const statistics = page.getByTestId("profile-statistics")
    await expect(page.getByTestId("profile-projects").getByRole("link", { name: "Quickstart Protocol Testing", exact: true })).toBeVisible()
    await expect(statistics.getByText("项目", { exact: true })).toBeVisible()
    await expect(statistics.getByText("协议", { exact: true })).toBeVisible()
    await expect(page.locator(".profile__contacts")).toContainText("邮箱:")
    await expect(statistics).not.toContainText(/\b(Overview|Labs|Projects|Protocols|Groups)\b/)
    const membership = page.getByTestId("profile-organization")
    if (single) {
      await expect(statistics.getByText("组织", { exact: true })).toHaveCount(0)
      await expect(statistics.getByText("小组", { exact: true })).toHaveCount(0)
      await expect(membership).toContainText(mode === "single_lab" ? "所属实验室" : "所属组织")
      await expect(membership).toContainText("Dev Demo Lab")
      await expect(membership).toContainText("所有者")
      // Display actual profile membership, not the instance's name for everyone.
      await expect(membership).not.toContainText("Synthetic organization")
      await expect(page.getByTestId("profile-organizations").getByRole("link", { name: "Dev Demo Lab", exact: true })).toHaveCount(0)
    }
    else {
      await expect(membership).toHaveCount(0)
      await expect(statistics.getByText("组织", { exact: true })).toBeVisible()
      await expect(statistics.getByText("小组", { exact: true })).toBeVisible()
      await expect(page.getByTestId("profile-organizations").getByRole("link", { name: "Dev Demo Lab", exact: true })).toBeVisible()
    }

    await changeAccountLanguage(page, "中文", "English")
    await expect(statistics.getByText("Projects", { exact: true })).toBeVisible()
    await expect(statistics.getByText("Protocols", { exact: true })).toBeVisible()
    await expect(page.locator(".n-tabs-tab[data-name='user-profile']")).toHaveText("Summary")
    await expect(page.locator(".n-tabs-tab[data-name='profile-settings']")).toHaveText("Settings")
    await expect(page.locator(".profile__contacts")).toContainText("Email:")
    if (!single)
      await expect(statistics.getByText("Organizations", { exact: true })).toBeVisible()
    await changeAccountLanguage(page, "English", "中文")
    await expect(statistics.getByText("项目", { exact: true })).toBeVisible()
    await expect(page.locator(".n-tabs-tab[data-name='profile-settings']")).toHaveText("设置")

    await page.setViewportSize({ width: 390, height: 900 })
    await expect(summary).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`${mode}-profile-mobile.png`), fullPage: true, animations: "disabled" })
    await page.setViewportSize({ width: 1440, height: 980 })
    await page.getByTestId("profile-projects").getByRole("link", { name: "Quickstart Protocol Testing", exact: true }).click()
    await expect(page).toHaveURL(single ? /\/projects\/quickstart\/overview$/ : /\/orgs\/dev_lab\/projects\/quickstart\/overview$/)
    await expect(page.getByRole("heading", { name: "Quickstart Protocol Testing", exact: true })).toBeVisible()
    await page.goto("/users/dev_owner/protocols")
    await expect(page.getByText("全部协议", { exact: true })).toBeVisible()
    if (single)
      expect(educationQueries).toEqual([])
    expect(failures).toEqual([])
  })
}

for (const visibility of ["missing", "private"] as const) {
  test(`${visibility} membership is not exposed on another user's profile`, async ({ page }) => {
    await presentInstance(page, "single_organization")
    // Explicit visibility/empty-state simulation; do not change persisted members.
    await page.route(/\/api\/users\/[^/]+\/labs(?:\?|$)/, async (route) => {
      const response = await route.fetch()
      const data = await response.json()
      await route.fulfill({ response, json: visibility === "missing"
        ? { labs: [], total_count: 0 }
        : { ...data, labs: data.labs.map((lab: { type: number }) => ({ ...lab, type: 1 })) } })
    })
    await page.route(/\/api\/users\/[^/]+\/protocols(?:\?|$)/, route => route.fulfill({ json: { protocols: [], total_count: 0 } }))
    await page.goto("/users/dev_viewer")
    await expect(page.getByTestId("profile-summary")).toBeVisible()
    await expect(page.getByTestId("profile-organization")).toHaveCount(0)
    await expect(page.locator(".n-tabs-tab[data-name='profile-settings']")).toHaveCount(0)
    await page.locator(".n-tabs-tab[data-name='profile-protocols']").click()
    await expect(page.getByText("暂无协议", { exact: true })).toBeVisible()
    await changeAccountLanguage(page, "中文", "English")
    await expect(page.getByText("All protocols", { exact: true })).toBeVisible()
    await expect(page.getByText("No protocols found", { exact: true })).toBeVisible()
  })
}
