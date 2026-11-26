import type { APIRequestContext } from "@playwright/test"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"

test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Single-organization fixtures")
test.use({ storageState: { cookies: [], origins: [] } })

async function post(api: APIRequestContext, path: string, data: unknown, token = "") {
  const response = await api.post(`/api${path}`, { headers: { "Auth-Token": token }, data })
  expect(response.ok(), `POST ${path} (${response.status()})`).toBeTruthy()
  return response.json()
}

test("personal timeline and work queue follow project and meeting permissions", async ({ page, request }) => {
  const id = randomUUID().slice(0, 8)
  const password = "AiralogyDev123!"
  const owner = await post(request, "/signin_by_email", { email: process.env.E2E_OWNER_EMAIL || "dev.owner@airalogy.dev", password: process.env.E2E_OWNER_PASSWORD || password })
  const { lab } = await (await request.get("/api/instance")).json()
  const makeProject = (uid: string) => post(request, "/projects", { lab_id: lab.id, uid, name: uid }, owner.token)
  const first = await makeProject(`agenda_a_${id}`)
  const second = await makeProject(`agenda_b_${id}`)
  const privateProject = await makeProject(`other_${id}`)
  const email = `agenda.${id}@example.org`
  const inv = await post(request, "/instance/invitations", { email, display_name: `Reader ${id}` }, owner.token)
  const member = await post(request, "/signup", { email, password, confirm_password: password, name: "Reader", username: `reader_${id}`, invite_token: new URL(inv.url).searchParams.get("token") })
  for (const p of [first, second])
    await post(request, `/projects/${p.id}/organization-members`, [{ user_id: member.user.id, role: 30 }], owner.token)
  const day = "2021-01-18T12:00:00Z"
  const newMeeting = (pid: string, name: string, options: object) => post(request, "/meetings", {
    id: randomUUID(),
    project_id: pid,
    title: `${name} ${id}`,
    occurred_at: day,
    ...options,
  }, owner.token)
  const participant = { user_id: member.user.id, attendance: "attended" }
  const meeting = await newMeeting(first.id, "Design review", { participants: [participant] })
  const other = await newMeeting(second.id, "Partner discussion", { participants: [participant] })
  const secret = await newMeeting(first.id, "Private audience", { visibility: "selected", participants: [participant] })
  const absent = await newMeeting(first.id, "Absent", { participants: [{ ...participant, attendance: "absent" }] })
  const unscheduled = await newMeeting(second.id, "Unscheduled", { status: "planned", occurred_at: null, participants: [participant] })
  const hidden = await newMeeting(privateProject.id, "Private project meeting", {})
  const task = { id: randomUUID(), title: `Deliver prototype ${id}`, assignee_user_id: member.user.id, planned_end: "2021-01-20" }
  await post(request, `/meetings/${meeting.id}/actions`, { ...task, expected_revision: 1 }, owner.token)
  await post(request, `/meetings/${secret.id}/work`, { task_id: task.id, expected_revision: 1 }, owner.token)
  const get = async (path: string) => {
    const response = await request.get(`/api${path}`, { headers: { "Auth-Token": member.token } })
    expect(response.ok(), `GET ${path} (${response.status()})`).toBeTruthy()
    return response.json()
  }
  const mine = await get("/my-work?view=meetings&period=past")
  expect(mine.items.map((m: { id: string }) => m.id).sort()).toEqual([meeting.id, other.id].sort())
  const visible = await get("/my-work?view=meetings&period=past&scope=visible")
  expect(visible.items.map((m: { id: string }) => m.id)).toContain(absent.id)
  for (const m of [secret, hidden])
    expect(JSON.stringify(visible)).not.toContain(m.id)
  expect((await get("/my-work?view=meetings&period=undated")).items[0].id).toBe(unscheduled.id)
  expect((await get("/my-work?view=meetings&period=past&scope=managed")).items).toHaveLength(0)
  expect((await get("/my-work?view=projects")).projects.map((p: { id: string }) => p.id)).not.toContain(privateProject.id)
  const queue = await get("/my-work?view=todos")
  expect(queue.items).toHaveLength(1)
  expect(queue.items[0].meetings.map((m: { id: string }) => m.id)).toEqual([meeting.id])
  expect((await get(`/project-work/${task.id}`)).meetings).toHaveLength(1)
  expect(mine.items.find((m: { id: string }) => m.id === meeting.id).open_count).toBe(1)
  const next = await get("/my-work?view=meetings&period=past&page_size=1")
  expect(next.has_more).toBe(true)
  expect((await get("/my-work?view=meetings&period=past&page_size=1&page=2")).items[0].id).not.toBe(next.items[0].id)
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(email)
  await page.getByTestId("login-password").locator("input").fill(password)
  await page.getByTestId("login-submit").click()
  await expect(page.getByTestId("my-work-summary")).toContainText(task.title)
  await page.getByTestId("my-work-summary").getByRole("link", { name: /查看全部/ }).click()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 850 })
    await page.goto("/my-work?period=past")
    await expect(page.getByRole("link", { name: meeting.title, exact: true })).toBeVisible()
    await expect(page.getByText(secret.title)).toHaveCount(0)
    await page.getByRole("link", { name: "待办", exact: true }).click()
    await expect(page.getByText("已逾期", { exact: false })).toBeVisible()
    await expect(page.getByRole("link", { name: task.title })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.getByRole("link", { name: task.title }).click()
    await expect(page.getByRole("link", { name: new RegExp(meeting.title) }).first()).toBeVisible()
    await page.getByRole("link", { name: new RegExp(meeting.title) }).first().click()
    await expect(page.getByTestId("meeting-work")).toContainText(task.title)
  }
  const move = await request.patch(`/api/project-work/${task.id}/state`, { headers: { "Auth-Token": owner.token }, data: {
    state: "cancelled",
    expected_revision: 1,
    request_id: randomUUID(),
    change_reason: "Synthetic meeting follow-up closed",
  } })
  expect(move.ok(), `Change state (${move.status()})`).toBeTruthy()
  expect((await get("/my-work?view=todos")).items).toHaveLength(0)
  const updated = await get(`/my-work?period=past&project_id=${first.id}`)
  expect(updated.items.find((m: { id: string }) => m.id === meeting.id).open_count).toBe(0)
})
