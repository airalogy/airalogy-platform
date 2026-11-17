import type { APIRequestContext } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { localDate } from "./meetings-test-date"

// Each writable journey owns its project so saved meetings, activity pages and
// named-person associations from another run cannot change its expectations.
async function meetingProject(api: APIRequestContext) {
  const login = await api.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const source = await api.get("/api/projects/by_uid", { headers, params: { lab_uid: "dev_lab", project_uid: "quickstart" } })
  expect(source.ok()).toBeTruthy()
  const uid = `meeting_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`
  const created = await api.post("/api/projects", { headers, data: { lab_id: (await source.json()).lab_id, uid, name: "Synthetic meeting journey", description: "Isolated meeting and activity acceptance", type: 1 } })
  expect(created.ok(), await created.text()).toBeTruthy()
  return `/labs/dev_lab/projects/${uid}`
}

test("project meeting, participants, comments, shared action and activity day survive reload", async ({
  page,
}, testInfo) => {
  const failures: string[] = []
  page.on("pageerror", error => failures.push(error.message))
  await page.addInitScript(() =>
    localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })),
  )
  await page.goto(`${await meetingProject(page.request)}/meetings`)
  await page.getByTestId("meeting-new").click()
  const title = `Synthetic meeting ${Date.now()}`
  await page.getByTestId("meeting-title").locator("input").fill(title)
  const day = new Date()
  day.setDate(day.getDate() - 2)
  const date = localDate(day)
  await page.getByTestId("meeting-date").fill(date)
  await page.getByTestId("meeting-people").locator(".n-select").first().click()
  await page.locator(".n-base-select-option").filter({ hasText: "dev_owner" }).click()
  await page.getByRole("button", { name: "添加参会人", exact: true }).click()
  await page.getByPlaceholder("姓名（无需账号）").fill("Synthetic partner")
  await page.getByPlaceholder("单位（可选）").fill("Synthetic organization")
  await page.getByRole("button", { name: "仅在本次会议按姓名添加", exact: true }).click()
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
  await expect(page.getByTestId("meeting-reading")).toContainText(title)
  await expect(page.getByTestId("meeting-reading")).toContainText("Decision remains pending")
  await page
    .getByTestId("meeting-comment")
    .locator("textarea")
    .fill("Synthetic participant follow-up")
  await page.getByTestId("meeting-comment-send").click()
  await expect(page.getByTestId("meeting-comments")).toContainText(
    "Synthetic participant follow-up",
  )
  await page.getByTestId("meeting-add-action-row").click()
  await page
    .getByTestId("meeting-action-title")
    .locator("input")
    .fill("Synthetic prototype comparison")
  const workSaved = page.waitForResponse(r =>
    r.url().endsWith(`/api/meetings/${meeting.id}/actions/batch`),
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
  const activityTime = activity.locator(".n-timeline-item-content__meta")
  await expect(activityTime).toBeVisible()
  await expect(activityTime).not.toContainText(/\d{2}:\d{2}/)
  await activity.getByRole("link").filter({ hasText: "打开" }).click()
  await expect(page).toHaveURL(new RegExp(`meeting=${meeting.id}`))
  await expect(page.getByTestId("meeting-work")).toContainText("Synthetic prototype comparison")
  const item = await page.request.get(`/api/project-work/${workId}`, { headers })
  expect(item.ok()).toBeTruthy()
  expect((await item.json()).evidence[0].id).toBe(meeting.id)
  await expect(page.getByTestId("meeting-edit")).toBeVisible()
  await expect(page.getByTestId("meeting-save")).toHaveCount(0)
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
    await page.getByTestId("meeting-edit").click()
    await page.getByTestId("meeting-people").locator("summary").click()
    await page.getByTestId("meeting-access-select").click()
    await page.locator(".n-base-select-option").filter({ hasText: "dev_viewer" }).click()
    await page.getByRole("button", { name: "添加授权", exact: true }).click()
    await page.getByTestId("meeting-save").click()
    await expect(page.getByTestId("meeting-save-state")).toContainText("已保存")
    await other.reload()
    await expect(other.getByTestId("meeting-reading")).toContainText(title)
    await expect(other.getByTestId("meeting-save")).toHaveCount(0)
    await expect(other.getByTestId("meeting-comment-send")).toHaveCount(0)
  }
  finally {
    await viewer.close()
  }
})

test("meeting and two detailed actions save together, and an administrator links a named person", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto(`${await meetingProject(page.request)}/meetings`)
  await page.getByTestId("meeting-new").click()
  const title = `Synthetic batch ${Date.now()}`
  await page.getByTestId("meeting-title").locator("input").fill(title)
  await page.getByTestId("meeting-minutes").locator("[contenteditable=true]").first().fill("Synthetic **decision** remains pending.")
  await page.getByTestId("meeting-add-action-row").click()
  const first = page.getByTestId("meeting-action-row-0")
  await first.getByTestId("meeting-action-title").locator("input").fill(`${title} first`)
  await first.getByRole("button", { name: "添加姓名 / 关联账号", exact: true }).click()
  const personName = `Synthetic colleague ${Date.now()}`
  await page.getByTestId("project-person-name").locator("input").fill(personName)
  await page.getByTestId("project-person-add").click()
  await expect(first).toContainText(personName)
  await first.getByText("协作人、目标与验收条件", { exact: true }).click()
  await first.locator("textarea").first().fill("Synthetic explicit goal")
  await page.getByTestId("meeting-add-action-row").click()
  await page.getByTestId("meeting-action-row-1").getByTestId("meeting-action-title").locator("input").fill(`${title} second`)
  const saving = page.waitForResponse(r => r.url().endsWith("/api/meetings/with-actions") && r.request().method() === "POST")
  await page.getByTestId("meeting-save").click()
  const response = await saving
  expect(response.ok(), await response.text()).toBeTruthy()
  const meeting = await response.json()
  expect(meeting.work).toHaveLength(2)
  const action = meeting.work.find((w: any) => w.item.title.endsWith("first")).item
  expect(action.goal).toBe("Synthetic explicit goal")
  expect(action.assignee_person_id).toBeTruthy()
  expect(action.assignee_user_id).toBeNull()
  const canonical = new URL(page.url()).pathname.replace(/meetings$/, "")
  await expect(page.getByTestId("meeting-reading")).toContainText(title)
  await page.getByTestId("meeting-work").getByRole("link", { name: `${title} first`, exact: true }).click()
  const editor = page.getByTestId("work-editor")
  await editor.getByTestId("work-assignee").getByRole("button", { name: "添加姓名 / 关联账号", exact: true }).click()
  const personRow = page.locator(".n-modal").filter({ hasText: "人员名单在项目内共享" }).locator("div.mt-3.border-t").filter({ hasText: personName })
  await personRow.getByTestId("project-person-account").click()
  await page.locator(".n-base-select-option").filter({ hasText: "dev_owner" }).click()
  await expect(page.getByRole("dialog").last()).toContainText("1 项任务")
  await page.getByRole("button", { name: "确认", exact: true }).last().click()
  await expect(personRow.getByTestId("project-person-account")).toContainText("dev_owner")
  await page.locator(".n-modal").filter({ hasText: "人员名单在项目内共享" }).getByRole("button", { name: "close", exact: true }).click()
  await page.locator(".n-drawer-header__close").click()
  await page.getByText("只看我负责的", { exact: true }).click()
  await expect(page.getByTestId("project-work")).toContainText(`${title} first`)
  await page.goto(`${canonical}overview`)
  await expect(page.getByTestId("project-description")).toBeVisible()
  await expect(page.getByTestId("research-activity")).toContainText(title)
  await expect(page.locator(".n-spin-body")).toHaveCount(0)
  for (const width of [755, 390, 1440]) {
    await page.setViewportSize({ width, height: 983 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    const header = await page.getByTestId("project-header").boundingBox()
    expect(header!.height).toBeLessThan(145)
    await page.screenshot({ path: testInfo.outputPath(`compact-project-${width}.png`), fullPage: true })
  }
})
