import type { APIRequestContext, Page } from "@playwright/test"
import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
const password = "AiralogyDev123!"
const ownerEmail = process.env.E2E_OWNER_EMAIL || "dev.owner@airalogy.dev"
const ownerPassword = process.env.E2E_OWNER_PASSWORD || password
test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Single-organization collaboration")
test.use({ storageState: { cookies: [], origins: [] } })

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")
async function publish(api: APIRequestContext, projectId: string, tag: string, token: string) {
  const files = {
    "protocol.aimd": "# Partner worksheet\n{{var|observations: str}}",
    "protocol.toml": `[airalogy_protocol]\nid="${tag}"\nname="Worksheet ${tag}"\nversion="0.1.0"\n`,
  }
  const buffer = Buffer.from(zipSync(Object.fromEntries(Object.entries(files).map(([key, text]) => [key, strToU8(text)]))))
  const res = await api.post("/api/protocols", { headers: { "Auth-Token": token }, multipart: {
    project_id: projectId,
    file: { name: "worksheet.zip", mimeType: "application/zip", buffer },
  } })
  expect(res.ok(), await res.text()).toBeTruthy()
  return (await res.json()).data
}

async function post(api: APIRequestContext, path: string, data: object, auth = "") {
  const response = await api.post(`/api${path}`, { data, headers: { "Auth-Token": auth } })
  expect(response.status(), `POST ${path.split("?")[0]}`).toBe(200)
  return response.json()
}
async function login(page: Page, email: string, loginPassword = password) {
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(email)
  await page.getByTestId("login-password").locator("input").fill(loginPassword)
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
}
function locale(page: Page) {
  return page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
}
for (const width of [1440, 390]) {
  test(`project invite, account reuse, membership conversion and isolation at ${width}px`, async ({ page, browser, request }) => {
    test.setTimeout(180000)
    const suffix = randomUUID().slice(0, 8)
    const owner = await post(request, "/signin_by_email", { email: ownerEmail, password: ownerPassword })
    const { lab } = await (await request.get("/api/instance")).json()
    const makeProject = (uid: string) => post(request, "/projects", { lab_id: lab.id, uid, name: uid }, owner.token)
    const shared = await makeProject(`partner_${suffix}`)
    const internal = await makeProject(`internal_${suffix}`)
    const worksheet = await publish(request, shared.id, `worksheet_${suffix}`, owner.token)
    const privateSheet = await publish(request, internal.id, `private_${suffix}`, owner.token)
    await page.setViewportSize({ width, height: 900 })
    await locale(page)
    await login(page, ownerEmail, ownerPassword)
    await page.goto(`/projects/${shared.uid}/members`)
    await page.getByRole("button", { name: zh.page.guests.invite }).click()
    const email = `partner.${suffix}@example.org`
    await page.getByLabel(zh.page.guests.email).fill(email)
    const response = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/invitations"))
    await page.getByRole("button", { name: zh.page.guests.create }).click()
    const { url } = await (await response).json()
    const guestContext = await browser.newContext({ viewport: { width, height: 900 }, baseURL: new URL(page.url()).origin })
    const guest = await guestContext.newPage()
    try {
      await locale(guest)
      await guest.goto(new URL(url).pathname + new URL(url).search)
      await expect(guest.getByText(zh.page.guests.invited.replace("{name}", shared.name))).toBeVisible()
      await guest.getByRole("button", { name: zh.page.login.register.confirm }).click()
      await guest.getByPlaceholder(zh.page.login.common.displayNamePlaceholder).fill("Partner")
      await guest.getByPlaceholder(zh.page.login.common.usernamePlaceholder).fill(`partner_${suffix}`)
      await guest.locator("input[type=\"password\"]").nth(0).fill(password)
      await guest.locator("input[type=\"password\"]").nth(1).fill(password)
      await guest.getByRole("button", { name: zh.page.login.register.confirm }).click()
      await expect(guest).toHaveURL(/\/collaboration/)
      await guest.getByRole("link", { name: shared.name }).click()
      await expect(guest.getByRole("heading", { name: shared.name })).toBeVisible()
      expect(await guest.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await guest.getByRole("link", { name: worksheet.name }).click()
      await expect(guest.getByRole("heading", { name: "Partner worksheet" })).toBeVisible()
      await guest.goto(`/projects/${shared.uid}/protocols/${worksheet.uid}/protocol`)
      await expect(guest.getByRole("heading", { name: "Partner worksheet" })).toBeVisible()
      const account = await post(request, "/signin_by_email", { email, password })
      const headers = { "Auth-Token": account.token }
      for (const path of [`/project-guests/mine/${internal.id}`, `/projects/${internal.id}`, `/labs/${lab.id}/users`, "/project-guests/directory", "/users/api_key", `/project-guests/protocols/${privateSheet.id}`, "/knowledge/items", `/project-operations/projects/${shared.id}`, `/project-operations/projects/${internal.id}`]) {
        expect([403, 404]).toContain((await request.get(`/api${path}`, { headers })).status())
      }
      expect((await request.post(`/api/protocols/${worksheet.id}/records`, {
        headers,
        data: { var: { observations: "Synthetic" }, check: {}, step: {}, report: "" },
      })).status()).toBe(403)
      expect((await request.post(`/api/project-guests/conversion/${owner.user.id}`, {
        headers: { "Auth-Token": owner.token },
        data: { projects: [shared.id], confirm: true },
      })).status()).toBe(403)
      const invite = (project: string, address: string) => post(request, `/project-guests/projects/${project}/invitations`, { email: address }, owner.token)
      const withdrawn = await invite(internal.id, email)
      const adminHeaders = { "Auth-Token": owner.token }
      expect((await request.delete(`/api/project-guests/projects/${internal.id}/invitations/${withdrawn.id}`, { headers: adminHeaders })).ok()).toBeTruthy()
      expect((await request.get(`/api/instance/invitations/${new URL(withdrawn.url).searchParams.get("token")}`)).status()).toBe(404)
      const second = await invite(internal.id, email)
      const token = new URL(second.url).searchParams.get("token")
      expect((await (await request.get(`/api/instance/invitations/${token}`)).json()).existing_account).toBe(true)
      expect((await request.post(`/api/instance/invitations/${token}/accept`, { headers: adminHeaders })).status()).toBe(403)
      await guest.goto(new URL(second.url).pathname + new URL(second.url).search)
      await guest.getByRole("button", { name: new RegExp(account.user.username) }).click()
      await expect(guest.getByRole("heading", { name: internal.name })).toBeVisible()
      expect((await request.post(`/api/instance/invitations/${token}/accept`, { headers })).status()).toBe(404)
      expect((await request.delete(`/api/project-guests/projects/${internal.id}/people/${account.user.id}`, { headers: { "Auth-Token": owner.token } })).ok()).toBeTruthy()
      expect((await request.get(`/api/project-guests/mine/${internal.id}`, { headers })).status()).toBe(404)

      const staffEmail = `staff.${suffix}@example.org`
      const invitation = await post(request, "/instance/invitations", { email: staffEmail, display_name: `Employee ${suffix}` }, owner.token)
      const staff = await post(request, "/signup", { email: staffEmail, name: `Employee ${suffix}`, username: `staff_${suffix}`, password, confirm_password: password, invite_token: new URL(invitation.url).searchParams.get("token") })
      await post(request, `/projects/${shared.id}/organization-members`, [{ user_id: staff.user.id, role: 40 }], owner.token)
      const record = await post(request, `/protocols/${worksheet.id}/records`, {
        var: { observations: "Staff observation" },
        step: {},
        check: {},
        report: "",
      }, staff.token)
      await page.goto("/organization/members")
      const row = page.locator(".member-list__item").filter({ hasText: `Employee ${suffix}` })
      if (width < 600)
        await row.getByRole("button", { name: zh.common.actions }).click()
      if (width < 600)
        await page.getByText(zh.page.guests.convert, { exact: true }).last().click()
      else await row.getByRole("button", { name: zh.page.guests.convert }).click()
      await page.getByRole("checkbox", { name: shared.name }).click()
      await page.getByRole("button", { name: zh.page.guests.confirm }).click()
      await expect(row).toHaveCount(0)
      await page.getByText(zh.page.guests.external, { exact: true }).click()
      await expect(page.getByText(staffEmail, { exact: true })).toBeVisible()
      await expect(page.getByText(email, { exact: true })).toBeVisible()
      expect((await request.get("/api/project-guests/mine", { headers: { "Auth-Token": staff.token } })).status()).toBe(401)
      const after = await post(request, "/signin_by_email", { email: staffEmail, password })
      expect(after.user.id).toBe(staff.user.id)
      const historical = await request.get(`/api/protocols/${worksheet.id}/records/${record.id}?version=1`, { headers: adminHeaders })
      expect(historical.ok()).toBeTruthy()
      expect((await historical.json()).metadata.record_initial_version_submission_user_id).toBe(after.user.username)
      const permitted = await (await request.get("/api/project-guests/mine", { headers: { "Auth-Token": after.token } })).json()
      expect(permitted.map((p: { id: string }) => p.id)).toEqual([shared.id])
      expect(after.user.project_guest).toBe(true)
      const upgrade = await post(request, `/project-guests/projects/${shared.id}/invitations`, { email, role: "recorder" }, owner.token)
      await post(request, `/instance/invitations/${new URL(upgrade.url).searchParams.get("token")}/accept`, {}, account.token)
      const submitted = await post(request, `/protocols/${worksheet.id}/records`, {
        var: { observations: "Partner observation" },
        step: {},
        check: {},
        report: "",
      }, account.token)
      expect(submitted.user_id).toBe(account.user.id)
      for (const path of ["/knowledge/items", `/project-guests/mine/${internal.id}`, `/project-operations/projects/${shared.id}`]) {
        expect([403, 404]).toContain((await request.get(`/api${path}`, { headers: { "Auth-Token": after.token } })).status())
      }
    }
    finally { await guestContext.close() }
  })
}

test("a project owner can invite independently and must transfer ownership before conversion", async ({ request }) => {
  const id = randomUUID().slice(0, 8)
  const admin = await post(request, "/signin_by_email", { email: ownerEmail, password: ownerPassword })
  const { lab } = await (await request.get("/api/instance")).json()
  const makeStaff = async (username: string) => {
    const email = `${username}@example.org`
    const invite = await post(request, "/instance/invitations", { email, display_name: username }, admin.token)
    return post(request, "/signup", { username, email, name: username, password, confirm_password: password, invite_token: new URL(invite.url).searchParams.get("token") })
  }
  const owner = await makeStaff(`owner_${id}`)
  const colleague = await makeStaff(`member_${id}`)
  const project = await post(request, "/projects", { lab_id: lab.id, uid: `pilot_${id}`, name: `Pilot ${id}` }, owner.token)
  const headers = { "Auth-Token": admin.token }
  const ownPath = `/project-guests/conversion/${owner.user.id}`
  expect((await (await request.get(`/api${ownPath}`, { headers })).json()).transfer_first).toContain(project.name)
  expect((await request.post(`/api${ownPath}`, { headers, data: { projects: [], confirm: true, keep_none: true } })).status()).toBe(409)
  expect((await request.get("/api/project-guests/directory", { headers: { "Auth-Token": owner.token } })).status()).toBe(403)
  const path = `/project-guests/projects/${project.id}/invitations`
  const email = `visitor.${id}@example.org`
  expect((await request.post(`/api${path}`, { headers: { "Auth-Token": colleague.token }, data: { email } })).status()).toBe(403)
  const issued = await post(request, path, { email }, owner.token)
  expect(["sent", "link"]).toContain(issued.delivery)
  await post(request, `/project-guests/conversion/${colleague.user.id}`, { projects: [], confirm: true, keep_none: true }, admin.token)
  const guest = await post(request, "/signin_by_email", { email: colleague.user.email, password })
  expect((await (await request.get("/api/project-guests/mine", { headers: { "Auth-Token": guest.token } })).json())).toEqual([])
})
