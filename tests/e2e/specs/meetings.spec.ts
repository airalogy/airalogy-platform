import { expect, test } from "@playwright/test"
import { localDate } from "./meetings-test-date"

test("project meeting, participants, comments, shared action and activity day survive reload", async ({
  page,
}, testInfo) => {
  const failures: string[] = []
  page.on("pageerror", error => failures.push(error.message))
  await page.addInitScript(() =>
    localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })),
  )
  await page.goto("/labs/dev_lab/projects/quickstart/meetings")
  await page.getByTestId("meeting-new").click()
  const title = `Synthetic meeting ${Date.now()}`
  await page.getByTestId("meeting-title").locator("input").fill(title)
  const day = new Date()
  day.setDate(day.getDate() - 2)
  const date = localDate(day)
  await page.getByTestId("meeting-date").fill(date)
  await page.getByTestId("meeting-participant-select").click()
  await page.locator(".n-base-select-option").filter({ hasText: "dev_owner" }).click()
  await page.getByRole("button", { name: "添加参会人", exact: true }).click()
  await page.getByPlaceholder("外部人员姓名").fill("Synthetic partner")
  await page.getByPlaceholder("单位（可选）").fill("Synthetic organization")
  await page.getByRole("button", { name: "记录外部参会人", exact: true }).click()
  const editor = page.getByTestId("meeting-minutes").locator("[contenteditable=\"true\"]").first()
  await expect(editor).toBeVisible()
  await editor.fill("Synthetic discussion: compare the prototype. Decision remains pending.")
  const saving = page.waitForResponse(
    r => r.url().endsWith("/api/meetings") && r.request().method() === "POST",
  )
  await page.getByTestId("meeting-save").click()
  const response = await saving
  expect(response.ok(), await response.text()).toBeTruthy()
  const meeting = await response.json()
  const headers = { "Auth-Token": (await response.request().allHeaders())["auth-token"] }
  await expect(page).toHaveURL(new RegExp(`meeting=${meeting.id}`))
  await page.reload()
  await expect(page.getByTestId("meeting-title").locator("input")).toHaveValue(title)
  await expect(page.getByTestId("meeting-minutes")).toContainText("Decision remains pending")
  await page
    .getByTestId("meeting-comment")
    .locator("textarea")
    .fill("Synthetic participant follow-up")
  await page.getByTestId("meeting-comment-send").click()
  await expect(page.getByTestId("meeting-comments")).toContainText(
    "Synthetic participant follow-up",
  )
  await page
    .getByTestId("meeting-action-title")
    .locator("input")
    .fill("Synthetic prototype comparison")
  const workSaved = page.waitForResponse(r =>
    r.url().endsWith(`/api/meetings/${meeting.id}/actions`),
  )
  await page.getByTestId("meeting-create-action").click()
  const workResponse = await workSaved
  expect(workResponse.ok(), await workResponse.text()).toBeTruthy()
  const updated = await workResponse.json()
  expect(updated.work).toHaveLength(1)
  const workId = updated.work[0].item.id
  const canonical = new URL(page.url()).pathname.replace(/meetings$/, "")
  await page.getByRole("button", { name: "修改历史", exact: true }).click()
  await expect(page.getByRole("dialog")).toContainText("Decision remains pending")
  await page.keyboard.press("Escape")
  await page.goto(`${canonical}overview`)
  const activity = page.getByTestId("research-activity")
  await activity.getByTestId("activity-type").click()
  await page
    .locator(".n-base-select-option")
    .filter({ hasText: /^会议$/ })
    .click()
  await expect(activity.locator(`[data-date="${date}"]`)).toHaveAttribute("data-count", "1")
  await activity.locator(`[data-date="${date}"]`).click()
  await expect(activity.getByTestId("activity-list-title")).toContainText(date)
  await expect(activity).toContainText(title)
  await activity.getByRole("link").filter({ hasText: "打开" }).click()
  await expect(page).toHaveURL(new RegExp(`meeting=${meeting.id}`))
  await expect(page.getByTestId("meeting-work")).toContainText("Synthetic prototype comparison")
  const item = await page.request.get(`/api/project-work/${workId}`, { headers })
  expect(item.ok()).toBeTruthy()
  expect((await item.json()).evidence[0].id).toBe(meeting.id)
  await expect(page.getByTestId("meeting-save")).toBeDisabled()
  await page.setViewportSize({ width: 390, height: 900 })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath("meeting-mobile.png"), fullPage: true })
  await page.goto(`${canonical}overview`)
  await expect(page.getByTestId("research-activity")).toContainText(title)
  await expect(page.locator(".n-spin-body")).toHaveCount(0)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath("activity-mobile.png"), fullPage: true })
  expect(failures).toEqual([])
})

test("selected meeting remains hidden from other project members until explicitly shared", async ({
  page,
  browser,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })),
  )
  await page.goto("/labs/dev_lab/projects/quickstart/meetings")
  await page.getByTestId("meeting-new").click()
  const title = `Synthetic restricted ${Date.now()}`
  await page.getByTestId("meeting-title").locator("input").fill(title)
  await page.getByTestId("meeting-visibility").click()
  await page.locator(".n-base-select-option").filter({ hasText: "仅指定成员可见" }).click()
  const create = page.waitForResponse(
    r => r.url().endsWith("/api/meetings") && r.request().method() === "POST",
  )
  await page.getByTestId("meeting-save").click()
  const response = await create
  expect(response.ok(), await response.text()).toBeTruthy()
  const m = await response.json()
  await expect(page).toHaveURL(new RegExp(`meeting=${m.id}`))
  const viewer = await browser.newContext({ storageState: "tests/e2e/.auth/viewer.json" })
  try {
    const other = await viewer.newPage()
    await other.addInitScript(() =>
      localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })),
    )
    await other.goto(page.url())
    await expect(other.getByTestId("meeting-error")).toBeVisible()
    await expect(other.getByTestId("meeting-title")).toHaveCount(0)
    await page.getByTestId("meeting-people").locator("summary").click()
    await page.getByTestId("meeting-access-select").click()
    await page.locator(".n-base-select-option").filter({ hasText: "dev_viewer" }).click()
    await page.getByRole("button", { name: "添加授权", exact: true }).click()
    await page.getByTestId("meeting-save").click()
    await expect(page.getByTestId("meeting-save-state")).toContainText("已保存")
    await other.reload()
    await expect(other.getByTestId("meeting-title").locator("input")).toHaveValue(title)
    await expect(other.getByTestId("meeting-save")).toHaveCount(0)
    await expect(other.getByTestId("meeting-comment-send")).toHaveCount(0)
  }
  finally {
    await viewer.close()
  }
})
