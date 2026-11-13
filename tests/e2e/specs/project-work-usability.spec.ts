import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
const labels = zh.page.projectWork
const project = "/labs/dev_lab/projects/quickstart"
test.use({ storageState: { cookies: [], origins: [] } })
test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(15000)
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
})

test("researcher starts from project overview, creates a minimal item and distinguishes filtered results", async ({ page }, testInfo) => {
  const title = `Synthetic UX ${Date.now()}`
  await page.goto(`${project}/overview`)
  await page.getByTestId("overview-new-work").click()
  const editor = page.getByTestId("work-editor")
  const input = editor.getByTestId("work-title").locator("input")
  await expect(input).toBeVisible()
  await expect(editor.getByTestId("work-editor-footer")).toContainText(labels.notCreated)
  await editor.getByTestId("work-save").click()
  await expect(editor.getByTestId("work-error")).toContainText(labels.titleRequired)
  await expect(input).toBeFocused()
  await input.fill(title)
  const request = page.waitForResponse(r => r.url().endsWith("/api/project-work") && r.request().method() === "POST")
  await editor.getByTestId("work-save").click()
  const created = await request
  expect(created.ok(), await created.text()).toBeTruthy()
  const item = await created.json()
  await expect(page).toHaveURL(new RegExp(`item=${item.id}`))
  await expect(input).toHaveValue(title)
  await expect(editor.getByTestId("work-editor-footer")).toContainText("版本 1")
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    const save = await editor.getByTestId("work-save").boundingBox()
    expect(save).not.toBeNull()
    expect(save!.y + save!.height).toBeLessThanOrEqual(900)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`work-editor-${width}.png`), animations: "disabled" })
  }
  await page.locator(".n-drawer-header__close").click()
  const workspace = page.getByTestId("project-work")
  await workspace.getByPlaceholder(labels.search).fill(`${title}-not-found`)
  await workspace.getByRole("button", { name: zh.common.search, exact: true }).click()
  await expect(workspace).toContainText(labels.noMatches)
  await expect(workspace).not.toContainText(labels.emptyHint)
  await workspace.getByTestId("work-clear-filters").click()
  await expect(workspace).toContainText(title)

  const token = (await created.request().allHeaders())["auth-token"]
  const blockedTitle = `${title} blocked`
  const blocked = await page.request.post("/api/project-work", {
    headers: { "Auth-Token": token },
    data: { id: crypto.randomUUID(), project_id: item.project_id, title: blockedTitle, state: "blocked", blocker: "Waiting for a synthetic fixture" },
  })
  expect(blocked.ok(), await blocked.text()).toBeTruthy()
  await workspace.getByTestId("work-state-filter").click()
  await page.locator(".n-base-select-option").filter({ hasText: labels.states.blocked }).click()
  await expect(workspace.getByRole("button", { name: new RegExp(blockedTitle) })).toBeVisible()
  await expect(workspace.locator(".work-row").filter({ hasText: title }).filter({ hasNotText: blockedTitle })).toHaveCount(0)
  await page.goto("/home")
  await page.locator(`[data-testid="home-project-card"][data-project-id="${item.project_id}"]`).getByTestId("home-project-work").click()
  await expect(page).toHaveURL(new RegExp(`${project}/work$`))
})

test("activity date and outcome survive reload before body text is entered", async ({ page }, testInfo) => {
  await page.goto(`${project}/work`)
  await page.getByTestId("work-new").click()
  const editor = page.getByTestId("work-editor")
  await editor.getByTestId("work-title").locator("input").fill(`Synthetic activity recovery ${Date.now()}`)
  const request = page.waitForResponse(r => r.url().endsWith("/api/project-work") && r.request().method() === "POST")
  await editor.getByTestId("work-save").click()
  const response = await request
  expect(response.ok()).toBeTruthy()
  const item = await response.json()
  await expect(page).toHaveURL(new RegExp(`item=${item.id}`))
  await editor.getByTestId("work-activity-tab").click()
  await editor.getByTestId("work-activity-kind").click()
  await page.locator(".n-base-select-option").filter({ hasText: labels.events.test }).click()
  await editor.locator("input[type=datetime-local]").fill("2026-11-13T10:00")
  await editor.getByTestId("work-activity-outcome").click()
  await page.locator(".n-base-select-option").getByText(labels.outcomes.passed, { exact: true }).click()
  await expect(editor.getByTestId("work-editor-footer")).toContainText(labels.unsaved)
  await expect(editor.getByTestId("work-activity-save")).toBeDisabled()
  page.once("dialog", dialog => dialog.accept())
  await page.reload()
  await editor.getByTestId("work-activity-tab").click()
  await expect(editor.locator("input[type=datetime-local]")).toHaveValue("2026-11-13T10:00")
  await expect(editor.getByTestId("work-activity-panel")).toContainText(labels.outcomes.passed)
  await expect(editor.getByTestId("work-activity-body").locator("textarea")).toHaveValue("")
  await expect(editor.getByTestId("work-activity-save")).toBeDisabled()
  // Switching panels must retain both kinds of unsaved input.
  await editor.getByTestId("work-details-tab").click()
  await editor.getByTestId("work-title").locator("input").fill("Synthetic detail edit retained")
  await editor.getByTestId("work-activity-tab").click()
  await expect(editor).toContainText(labels.saveFirst)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`work-activity-${width}.png`), animations: "disabled" })
  }
})

test("Home lets the researcher continue past the first six assigned items", async ({ page }) => {
  const response = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(response.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await response.json()).token }
  const projectResponse = await page.request.get("/api/projects/by_uid", { headers, params: { lab_uid: "dev_lab", project_uid: "quickstart" } })
  expect(projectResponse.ok()).toBeTruthy()
  const info = await projectResponse.json()
  const memberResponse = await page.request.get("/api/project-work/members", { headers, params: { project_id: info.id } })
  expect(memberResponse.ok()).toBeTruthy()
  const owner = (await memberResponse.json()).members.find((member: { username: string }) => member.username === "dev_owner")
  expect(owner).toBeTruthy()
  const prefix = `Synthetic assigned pagination ${Date.now()}`
  for (let index = 0; index < 7; index++) {
    const created = await page.request.post("/api/project-work", { headers, data: { id: crypto.randomUUID(), project_id: info.id, assignee_user_id: owner.id, title: `${prefix} ${index}` } })
    expect(created.ok(), await created.text()).toBeTruthy()
  }
  await page.goto("/home")
  const summary = page.getByTestId("work-summary")
  await expect(summary.locator("li")).toHaveCount(6)
  await summary.getByTestId("work-summary-more").click()
  await expect(summary.locator("li").filter({ hasText: prefix })).toHaveCount(7)
  await expect(summary.locator('[data-testid="work-summary-more"].n-button--loading')).toHaveCount(0)
})
