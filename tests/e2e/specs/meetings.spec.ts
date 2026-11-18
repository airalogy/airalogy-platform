import type { APIRequestContext } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { localDate } from "./meetings-test-date"

// Each writable journey owns its project so saved meetings, activity pages and
// named-person associations from another run cannot change its expectations.
async function createMeetingProject(api: APIRequestContext) {
  const login = await api.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const source = await api.get("/api/projects/by_uid", { headers, params: { lab_uid: "dev_lab", project_uid: "quickstart" } })
  expect(source.ok()).toBeTruthy()
  const uid = `meeting_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`
  const created = await api.post("/api/projects", { headers, data: { lab_id: (await source.json()).lab_id, uid, name: "Synthetic meeting journey", description: "Isolated meeting and activity acceptance", type: 1 } })
  expect(created.ok(), await created.text()).toBeTruthy()
  return { path: `/labs/dev_lab/projects/${uid}`, projectId: (await created.json()).id, headers }
}

async function meetingProject(api: APIRequestContext) {
  return (await createMeetingProject(api)).path
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
  await page.goto(`${canonical}documents`)
  const docs = page.getByTestId("research-documents-list")
  await expect(docs.getByTestId("document-list-empty")).toBeVisible()
  const search = docs.getByRole("textbox", { name: "搜索" })
  await search.fill("Decision remains pending")
  await search.press("Enter")
  const minutes = docs.getByTestId("research-document-link").filter({ hasText: title })
  await expect(minutes).toHaveAttribute("href", `${canonical}meetings?meeting=${meeting.id}`)
  await minutes.click()
  await expect(page.getByTestId("meeting-reading")).toContainText(title)
  const noteTitle = `Handwritten notes ${meeting.id}`
  const note = await page.request.post("/api/research-documents", { headers, data: { scope_type: "project", project_id: meeting.project_id, kind: "meeting", title: noteTitle } })
  expect(note.ok(), await note.text()).toBeTruthy()
  await page.goto(`${canonical}documents`)
  const rows = docs.getByTestId("research-document-link")
  await expect(rows).toHaveCount(1)
  await rows.filter({ hasText: noteTitle }).click()
  await expect(page).toHaveURL(/read=/)
  await page.goto(`${canonical}meetings`)
  const toggle = page.getByTestId("meeting-filters-toggle")
  for (const width of [876, 390]) {
    await page.setViewportSize({ width, height: 983 })
    await expect(toggle).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByLabel("开始日期")).toBeHidden()
    await toggle.click()
    await page.getByLabel("开始日期").fill("2099-01-01")
    await expect(page.getByTestId("meeting-list-item")).toHaveCount(0)
    await toggle.click()
    await expect(page.getByTestId("meeting-filter-summary")).toContainText("2099-01-01")
    await page.getByRole("button", { name: "清除筛选" }).click()
    await expect(page.getByTestId("meeting-list-item")).toContainText(title)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`meeting-search-${width}.png`) })
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByTestId("meeting-list-item").getByRole("link").click()
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
  const activityTime = activity.locator("time")
  await expect(activityTime).toBeVisible()
  await expect(activityTime).not.toContainText(/\d{2}:\d{2}/)
  await activity.getByRole("link", { name: title, exact: true }).click()
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
  const overview = page.getByTestId("overview-events")
  await expect(overview).toContainText("从会议创建了 2 项待办")
  await expect(overview.locator("li")).toHaveCount(2)
  const headers = { "Auth-Token": (await response.request().allHeaders())["auth-token"] }
  for (let n = 0; n < 3; n++) {
    const created = await page.request.post("/api/project-work", { headers, data: { id: crypto.randomUUID(), project_id: meeting.project_id, title: `Synthetic separate action ${n}` } })
    expect(created.ok(), await created.text()).toBeTruthy()
  }
  await page.reload()
  await expect(overview.locator("li")).toHaveCount(3)
  const workSummary = page.getByTestId("work-summary")
  await expect(workSummary.locator("li")).toHaveCount(3)
  const cell = page.getByTestId("activity-heatmap").locator("[data-count]:not([data-count=\"0\"])").last()
  await cell.click()
  await page.getByTestId("view-day").click()
  await expect(page.getByTestId("activity-list-title")).toContainText("当天活动")
  await expect(page.getByTestId("research-activity")).toContainText("从会议创建了 2 项待办")
  await page.goBack()
  await expect(overview.locator("li")).toHaveCount(3)
  for (const width of [755, 390, 1440]) {
    await page.setViewportSize({ width, height: 983 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    const header = await page.getByTestId("project-header").boundingBox()
    expect(header!.height).toBeLessThan(145)
    await page.screenshot({ path: testInfo.outputPath(`compact-project-${width}.png`), fullPage: true })
  }
})

test("project Aira reviews a temporary meeting draft before saving minutes and actions together", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  const root = await meetingProject(page.request)
  await page.route("**/api/instance", async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), ai_enabled: true } })
  })
  await page.route("**/api/meetings/aira/availability?*", route => route.fulfill({ json: { available: true } }))
  const title = "Synthetic Aira meeting"
  const draft = { title, body: "Synthetic decision to review fit.", occurred_on: null, actions: ["Check fit", "Review notes"] }
  let draftCalls = 0
  await page.route("**/api/meetings/aira/draft", async (route) => {
    const input = route.request().postDataJSON()
    if (draftCalls++)
      expect(input.previous).toEqual(draft)
    await route.fulfill({ json: { message: "请核对纪要", draft } })
  })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`${root}/records`)
  const filters = page.getByTestId("activity-type")
  expect((await filters.boundingBox())!.height).toBeLessThanOrEqual(36)
  await page.getByTestId("project-aira").click()
  const panel = page.getByTestId("project-aira-panel")
  await expect(panel).toBeVisible()
  const avatar = panel.getByRole("heading", { name: "Aira", exact: true }).locator("svg")
  await expect(avatar).toHaveCSS("width", "24px")
  expect((await panel.boundingBox())!.x).toBeGreaterThan((await filters.boundingBox())!.x)
  await panel.locator("textarea").fill("Synthetic transcript for a new meeting")
  await panel.getByRole("button", { name: "发送" }).click()
  await expect(panel.getByTestId("aira-proposal")).toContainText(title)
  await expect(page.getByTestId("research-activity").locator(".n-spin-body")).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("aira-desktop.png") })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(panel).toBeVisible()
  await expect(avatar).toHaveCSS("height", "24px")
  expect((await panel.boundingBox())!.width).toBeGreaterThanOrEqual(385)
  await page.screenshot({ path: testInfo.outputPath("aira-phone.png") })
  await panel.locator("textarea").fill("Keep the two actions")
  await panel.getByRole("button", { name: "发送" }).click()
  await panel.getByRole("button", { name: "核对纪要与待办" }).click()
  await expect(page.getByTestId("meeting-title").locator("input")).toHaveValue(title)
  await expect(page.getByTestId("meeting-action-row-1")).toContainText("2")
  await expect(page.getByTestId("meeting-save")).toBeDisabled()
  await page.getByTestId("meeting-date").fill("2020-03-15")
  const saved = page.waitForResponse(r => r.url().endsWith("/api/meetings/with-actions") && r.request().method() === "POST")
  await page.getByTestId("meeting-save").click()
  const response = await saved
  expect(response.ok(), await response.text()).toBeTruthy()
  const meeting = await response.json()
  expect(meeting.work.map((link: { item: { title: string } }) => link.item.title).sort()).toEqual(draft.actions)
  await expect(page.getByTestId("meeting-reading")).toContainText(draft.body)
})

test("project team follows meetings and separates accounts from named participants", async ({ page }, testInfo) => {
  const { headers, projectId, path } = await createMeetingProject(page.request)
  const name = "Synthetic partner"
  const people = [crypto.randomUUID(), crypto.randomUUID()]
  for (const [index, id] of people.entries()) {
    const saved = await page.request.post("/api/project-people", { headers, data: {
      project_id: projectId,
      id,
      name,
      organization: `Synthetic organization ${index + 1}`,
    } })
    expect(saved.ok(), await saved.text()).toBeTruthy()
  }
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  const errors: string[] = []
  page.on("pageerror", e => errors.push(e.message))
  // Hold the first project lookup until the user switches tabs, as on a slow connection.
  let lookupStarted!: () => void
  const firstLookup = new Promise<void>((resolve) => {
    lookupStarted = resolve
  })
  let releaseLookup!: () => void
  const heldLookup = new Promise<void>((resolve) => {
    releaseLookup = resolve
  })
  await page.route("**/api/projects/by_uid?**", async (route) => {
    lookupStarted()
    await heldLookup
    await route.continue()
  }, { times: 1 })
  const accounts = page.getByTestId("team-accounts")
  const participants = page.getByTestId("team-participants")
  for (const width of [1440, 876, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 983 })
    await page.goto(`${path}/meetings`)
    const team = page.locator('.n-tabs-tab[data-name="project-members"]')
    await expect(team).toHaveText("团队")
    const tabs = await page.locator(".n-tabs-tab").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-name")))
    expect(tabs.slice(tabs.indexOf("project-meetings"), tabs.indexOf("project-meetings") + 3))
      .toEqual(["project-meetings", "project-members", "project-documents"])
    if (width === 1440)
      await firstLookup
    await team.click()
    releaseLookup()
    await expect(page).toHaveURL(/\/members$/)
    await expect(accounts).toContainText("Dev Owner")
    await expect(accounts).not.toContainText(name)
    await expect(participants.getByText(name, { exact: true })).toHaveCount(2)
    await expect(participants).toContainText("Synthetic organization 2")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`project-team-${width}.png`) })
  }
  const direct = await page.request.get(`/api/projects/${projectId}/users`, { headers })
  expect(direct.ok()).toBeTruthy()
  const userId = (await direct.json()).users.find((u: { username: string }) => u.username === "dev_owner").id
  const linked = await page.request.put(`/api/project-people/${people[0]}`, { headers, data: {
    name,
    user_id: userId,
    expected_revision: 1,
  } })
  expect(linked.ok(), await linked.text()).toBeTruthy()
  await page.reload()
  await expect(participants.getByText(name, { exact: true })).toHaveCount(1)
  await expect(participants).toContainText("Synthetic organization 2")
  await expect(accounts.getByText("Dev Owner", { exact: true })).toHaveCount(1)
  expect(errors).toEqual([])
})
