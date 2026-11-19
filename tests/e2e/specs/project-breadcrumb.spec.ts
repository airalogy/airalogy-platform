import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { changeAccountLanguage } from "./fixtures"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8"))
const projectPath = "/orgs/dev_lab/projects/quickstart"
const projectName = "合成研发项目"

test.use({ storageState: { cookies: [], origins: [] } })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
  // A display-only override proves that names are not inferred from URL slugs
  // or translated as interface text. No project data is changed.
  await page.route("**/api/projects/by_uid?**", async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), name: projectName } })
  })
})

test("project menu translates immediately and keeps custom names and project context", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 755, height: 989 })
  await page.goto(`${projectPath}/overview`)
  const breadcrumb = page.locator(".global-breadcrumb")
  const trigger = breadcrumb.getByRole("button", { name: projectName, exact: true })
  await expect(trigger).toBeVisible()
  await expect(breadcrumb).not.toContainText("quickstart")
  await trigger.focus()
  await page.keyboard.press("Enter")
  const menu = page.locator(".n-dropdown-menu:visible").last()
  await expect(menu).toContainText(zh.page.project.protocols)
  await expect(menu).toContainText(zh.page.research.title)
  await expect(menu).toContainText(zh.page.workflowDefinitions.title)
  await expect(menu).toContainText(zh.page.analysis.title)
  await expect(menu).toContainText(zh.page.recordDiary.tab)
  await expect(menu).toContainText(zh.page.project.members)
  await expect(menu).not.toContainText("Project protocols")
  await page.screenshot({ path: testInfo.outputPath("project-menu-zh-755.png"), fullPage: true })
  await page.locator("h2").filter({ hasText: projectName }).click()
  await changeAccountLanguage(page, "English")
  await trigger.click()
  await expect(menu).toContainText(en.page.project.protocols)
  await expect(menu).toContainText(en.page.workflowDefinitions.title)
  await expect(menu).toContainText(en.page.analysis.title)
  await expect(menu).not.toContainText(zh.page.project.protocols)
  await expect(trigger).toHaveText(projectName)
  await menu.getByText(en.page.analysis.title, { exact: true }).click()
  await expect(page).toHaveURL(`${projectPath}/analysis`)
  await expect(trigger).toBeVisible()
})

test("every project menu destination keeps the same project and remains usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  await page.goto(`${projectPath}/overview`)
  const destinations = [
    [zh.page.workflowDefinitions.title, "workflows"],
    [zh.page.research.title, "research"],
    [zh.page.recordDiary.tab, "records"],
    [zh.page.project.members, "members"],
    [zh.page.project.protocols, "protocols"],
  ]
  for (const [label, section] of destinations) {
    await page.locator(".global-breadcrumb").getByRole("button", { name: projectName, exact: true }).click()
    await page.locator(".n-dropdown-menu:visible").last().getByText(label, { exact: true }).click()
    await expect(page).toHaveURL(`${projectPath}/${section}`)
    await expect(page.locator(".global-breadcrumb").getByRole("button", { name: projectName, exact: true })).toBeVisible()
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
})
