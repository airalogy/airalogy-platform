import type { APIRequestContext, Locator, Page } from "@playwright/test"
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
async function findPerson(page: Page, row: Locator) {
  const list = page.locator(".member-list")
  await expect(list.locator(".member-list__item").first()).toBeVisible()
  const next = page.locator(".n-pagination-item--button").last()
  while (!await row.count() && !await next.evaluate(el => el.classList.contains("n-pagination-item--disabled"))) {
    const loaded = page.waitForResponse(r => r.url().includes("/project-guests/people?"))
    await next.click()
    await (await loaded).finished()
    await expect(page.locator(".n-spin-content--spinning")).toHaveCount(0)
  }
  await expect(row).toBeVisible()
}

for (const width of [1440, 759, 390]) {
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
    const alias = `Partner directory ${suffix}`
    await page.getByLabel(zh.common.labAliasLabel).fill(alias)
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
      for (const path of [`/project-guests/mine/${internal.id}`, `/projects/${internal.id}`, `/labs/${lab.id}/users`, "/project-guests/directory", "/project-guests/people", "/users/api_key", `/project-guests/protocols/${privateSheet.id}`, "/knowledge/items", `/project-operations/projects/${shared.id}`, `/project-operations/projects/${internal.id}`]) {
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
      const directory = await (await request.get("/api/project-guests/people?kind=guest&page_size=100", { headers: adminHeaders })).json()
      const matches = directory.list.filter((person: { id: string }) => person.id === account.user.id)
      expect(matches).toHaveLength(1)
      expect(matches[0].name).toBe(alias)
      expect(matches[0].projects.sort()).toEqual([shared.name, internal.name].sort())
      expect((await request.delete(`/api/project-guests/projects/${internal.id}/people/${account.user.id}`, { headers: { "Auth-Token": owner.token } })).ok()).toBeTruthy()
      expect((await request.get(`/api/project-guests/mine/${internal.id}`, { headers })).status()).toBe(404)

      const staffEmail = `staff.${suffix}@example.org`
      const invitation = await post(request, "/instance/invitations", { email: staffEmail, display_name: `Employee ${suffix}` }, owner.token)
      const staff = await post(request, "/signup", { email: staffEmail, name: `Staff profile ${suffix}`, username: `staff_${suffix}`, password, confirm_password: password, invite_token: new URL(invitation.url).searchParams.get("token") })
      await post(request, `/projects/${shared.id}/organization-members`, [{ user_id: staff.user.id, role: 40 }], owner.token)
      const record = await post(request, `/protocols/${worksheet.id}/records`, {
        var: { observations: "Staff observation" },
        step: {},
        check: {},
        report: "",
      }, staff.token)
      await page.goto("/organization/members")
      const filters = page.getByRole("radiogroup")
      await expect(filters.getByRole("radio", { name: zh.common.all, exact: true })).toBeChecked()
      const guestRow = page.getByTestId("guest-row").filter({ hasText: account.user.username })
      await findPerson(page, guestRow)
      await expect(guestRow.getByText(alias, { exact: true })).toBeVisible()
      const pageBeforeRename = await page.locator(".n-pagination-item--active").textContent()
      await expect(guestRow.locator("img[src=\"/images/role_member.png\"]")).toBeVisible()
      const guestActions = guestRow.getByRole("button", { name: zh.common.actions, exact: true })
      await guestActions.click()
      await page.getByText(zh.page.guests.collaborationDetails, { exact: true }).click()
      await expect(page.getByRole("dialog")).toContainText(email)
      await expect(page.getByRole("dialog")).toContainText(shared.name)
      await page.keyboard.press("Escape")
      await guestActions.click()
      await page.getByText(zh.page.instance.createResetLink, { exact: true }).click()
      await expect(page.getByRole("dialog").locator("textarea")).toHaveValue(/reset/)
      await page.getByRole("dialog").getByRole("button", { name: zh.common.close }).click()
      await guestActions.click()
      await page.getByText(zh.common.setAlias, { exact: true }).click()
      await page.getByLabel(zh.common.labAliasLabel).fill(`Updated ${suffix}`)
      await page.getByRole("button", { name: zh.common.save, exact: true }).click()
      await expect(guestRow.getByText(`Updated ${suffix}`, { exact: true })).toBeVisible()
      await expect(page.locator(".n-pagination-item--active")).toHaveText(pageBeforeRename!)
      await filters.getByText(zh.page.guests.members, { exact: true }).click()
      await expect(guestRow).toHaveCount(0)
      const row = page.locator(".member-list__item").filter({ hasText: `Employee ${suffix}` })
      await findPerson(page, row)
      const actions = row.getByRole("button", { name: zh.common.actions, exact: true })
      await expect(row.locator(".n-list-item__suffix button")).toHaveCount(1)
      const rowHeight = Math.ceil((await row.boundingBox())!.height)
      expect(rowHeight).toBeLessThanOrEqual(width < 600 ? 85 : 72)
      console.log(`Organization member row: ${width}px viewport, ${rowHeight}px height`)
      await actions.click()
      const menu = page.locator(".n-dropdown-menu:visible")
      for (const label of [zh.common.setAlias, zh.page.instance.createResetLink, zh.common.changeRole, zh.common.remove])
        await expect(menu.getByText(label, { exact: true })).toBeVisible()
      await menu.getByText(zh.page.guests.collaborationDetails, { exact: true }).click()
      await page.getByRole("dialog").getByRole("listitem").filter({ hasText: shared.name }).getByRole("link").click()
      const selectedStaff = page.locator(".member-list__item").filter({ hasText: staff.user.username })
      await expect(selectedStaff).toHaveCount(1)
      await selectedStaff.getByRole("button", { name: zh.common.actions }).click()
      await expect(menu.getByText(zh.common.changeRole, { exact: true })).toBeVisible()
      await page.goto("/organization/members")
      await filters.getByText(zh.page.guests.members, { exact: true }).click()
      await findPerson(page, row)
      await actions.click()
      await menu.getByText(zh.page.guests.convert, { exact: true }).click()
      await page.getByRole("checkbox", { name: shared.name }).click()
      await page.getByRole("button", { name: zh.page.guests.confirm }).click()
      await expect(row).toHaveCount(0)
      await filters.getByText(zh.page.guests.external, { exact: true }).click()
      await findPerson(page, page.getByTestId("guest-row").filter({ hasText: staff.user.username }))
      expect((await request.get("/api/project-guests/mine", { headers: { "Auth-Token": staff.token } })).status()).toBe(401)
      const after = await post(request, "/signin_by_email", { email: staffEmail, password })
      expect(after.user.id).toBe(staff.user.id)
      await expect(page.getByTestId("guest-row").filter({ hasText: staff.user.username })).toContainText(`Employee ${suffix}`)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.goto(`/projects/${shared.uid}/members`)
      await expect(page.getByTestId("external-team").filter({ hasText: account.user.username })).toContainText(`Updated ${suffix}`)
      await page.getByRole("button", { name: zh.page.guests.invite }).click()
      await page.getByLabel(zh.page.guests.email).fill(email)
      await page.getByLabel(zh.page.guests.email).press("Tab")
      await expect(page.getByText(zh.page.guests.reuseName, { exact: true })).toBeVisible()
      await expect(page.getByRole("button", { name: zh.page.guests.create })).toBeEnabled()
      expect(account.user.name).toBe("Partner")
      const historical = await request.get(`/api/protocols/${worksheet.id}/records/${record.id}?version=1`, { headers: adminHeaders })
      expect(historical.ok()).toBeTruthy()
      expect((await historical.json()).metadata.record_initial_version_submission_user_id).toBe(after.user.username)
      const permitted = await (await request.get("/api/project-guests/mine", { headers: { "Auth-Token": after.token } })).json()
      expect(permitted.map((p: { id: string }) => p.id)).toEqual([shared.id])
      expect(after.user.project_guest).toBe(true)
      const endpoint = `/api/project-guests/projects/${shared.id}/people/${account.user.id}`
      const duplicate = await request.post(`/api/project-guests/projects/${shared.id}/invitations`, { headers: adminHeaders, data: { email, role: "recorder" } })
      expect(duplicate.status()).toBe(409)
      await page.goto("/organization/members")
      await filters.getByText(zh.page.guests.external, { exact: true }).click()
      await findPerson(page, guestRow)
      await guestActions.click()
      await page.getByText(zh.page.guests.collaborationDetails, { exact: true }).click()
      await page.getByRole("dialog").getByRole("listitem").filter({ hasText: shared.name }).getByRole("link").click()
      await expect(page).toHaveURL(new RegExp(`/members\\?person=${account.user.id}`))
      const teamRow = page.getByTestId("external-team")
      await expect(teamRow).toContainText(account.user.username)
      await teamRow.getByRole("button", { name: zh.common.actions }).click()
      await page.getByText(zh.page.guests.manageAccess, { exact: true }).click()
      const grant = page.getByRole("dialog")
      await grant.locator(".n-select").click()
      await page.getByText(zh.page.guests.editor, { exact: true }).click()
      await grant.getByRole("button", { name: zh.common.save }).click()
      await expect(teamRow).toContainText(zh.page.guests.editor)
      const stale = await request.patch(endpoint, { headers: adminHeaders, data: { role: "reader", access_until: null, previous: { role: "reader", access_until: null } } })
      expect(stale.status()).toBe(409)
      const guestHeaders = { "Auth-Token": account.token }
      const revisionPath = `/api/project-guests/protocols/${worksheet.id}/revisions`
      const revision = { aimd: "# Reviewed worksheet\n{{var|observations: str}}", version: "0.1.1", base_version: "0.1.0" }
      const cannotEditOther = await request.post(`/api/project-guests/protocols/${privateSheet.id}/revisions`, { headers: guestHeaders, data: revision })
      expect(cannotEditOther.status()).toBe(404)
      await guest.goto(`/collaboration?project=${shared.id}&protocol=${worksheet.id}`)
      await guest.getByRole("button", { name: zh.page.guests.revise }).click()
      await guest.getByRole("textbox", { name: zh.page.guests.revise }).fill(revision.aimd)
      const savingRevision = guest.waitForResponse(r => r.url().endsWith("/revisions") && r.request().method() === "POST")
      await guest.getByRole("button", { name: zh.common.save, exact: true }).click()
      const publishResult = await savingRevision
      expect(publishResult.status(), await publishResult.text()).toBe(200)
      await expect(guest.getByRole("heading", { name: "Reviewed worksheet" })).toBeVisible()
      const reread = await (await request.get(`/api/project-guests/protocols/${worksheet.id}`, { headers: guestHeaders })).json()
      expect(reread).toMatchObject({ version: "0.1.1", aimd: revision.aimd })
      expect((await request.post(revisionPath, { headers: guestHeaders, data: revision })).status()).toBe(409)
      expect((await request.patch(endpoint, { headers: guestHeaders, data: { role: "editor", access_until: null } })).status()).toBe(403)
      expect((await request.patch(endpoint, { headers: adminHeaders, data: { role: "recorder", access_until: null } })).status()).toBe(200)
      expect((await request.post(revisionPath, { headers: guestHeaders, data: revision })).status()).toBe(403)
      const until = new Date(Date.now() + 1800).toISOString()
      expect((await request.patch(endpoint, { headers: adminHeaders, data: { role: "editor", access_until: until } })).status()).toBe(200)
      await expect.poll(async () => (await request.get(`/api/project-guests/protocols/${worksheet.id}`, { headers: guestHeaders })).status()).toBe(404)
      expect((await request.post(revisionPath, { headers: guestHeaders, data: revision })).status()).toBe(404)
      expect((await request.patch(endpoint, { headers: adminHeaders, data: { role: "recorder", access_until: null } })).status()).toBe(200)
      const updatedTeam = await (await request.get(`/api/project-guests/projects/${shared.id}/team`, { headers: adminHeaders })).json()
      expect(updatedTeam.people.find((person: { id: string }) => person.id === account.user.id).name).toBe(`Updated ${suffix}`)
      const submitted = await post(request, `/protocols/${worksheet.id}/records`, {
        var: { observations: "Partner observation" },
        step: {},
        check: {},
        report: "",
      }, account.token)
      expect(submitted.user_id).toBe(account.user.id)
      const reset = await post(request, "/instance/password-reset-links", { user_id: account.user.id }, owner.token)
      const resetPath = `/instance/password-resets/${new URL(reset.url).searchParams.get("token")}`
      const newPassword = "ChangedDev123!"
      await post(request, resetPath, { password: newPassword, confirm_password: newPassword })
      expect((await request.post(`/api${resetPath}`, { data: { password, confirm_password: password } })).status()).toBe(404)
      expect((await request.get("/api/project-guests/mine", { headers })).status()).toBe(401)
      const reauthed = await post(request, "/signin_by_email", { email, password: newPassword })
      expect(reauthed.user.project_guest).toBe(true)
      const promotion = `/project-guests/promotion/${account.user.id}`
      expect((await request.post(`/api${promotion}`, { headers: adminHeaders, data: { projects: [internal.id], confirm: true } })).status()).toBe(422)
      expect((await request.get(`/api${promotion}`, { headers: { "Auth-Token": reauthed.token } })).status()).toBe(403)
      const previous = await invite(internal.id, email)
      await post(request, `/instance/invitations/${new URL(previous.url).searchParams.get("token")}/accept`, {}, reauthed.token)
      await page.goto("/organization/members")
      await filters.getByText(zh.page.guests.external, { exact: true }).click()
      await findPerson(page, guestRow)
      await guestActions.click()
      await page.getByText(zh.page.guests.promote, { exact: true }).click()
      await expect(page.getByRole("button", { name: zh.page.guests.confirm })).toBeDisabled()
      await expect(page.getByRole("checkbox", { name: new RegExp(internal.name) })).not.toBeChecked()
      await page.getByRole("checkbox", { name: new RegExp(shared.name) }).check()
      await page.getByRole("button", { name: zh.page.guests.confirm }).click()
      await expect(page.getByRole("dialog")).toHaveCount(0)
      await expect(guestRow).toHaveCount(0)
      expect((await request.get("/api/project-guests/mine", { headers: { "Auth-Token": reauthed.token } })).status()).toBe(401)
      const promoted = await post(request, "/signin_by_email", { email, password: newPassword })
      expect(promoted.user.id).toBe(account.user.id)
      expect(promoted.user.project_guest).toBe(false)
      const promotedHeaders = { "Auth-Token": promoted.token }
      expect((await request.get(`/api/projects/${shared.id}`, { headers: promotedHeaders })).ok()).toBeTruthy()
      expect([403, 404]).toContain((await request.get(`/api/projects/${internal.id}`, { headers: promotedHeaders })).status())
      await filters.getByText(zh.page.guests.members, { exact: true }).click()
      await findPerson(page, page.locator(".member-list__item").filter({ hasText: `Updated ${suffix}` }))
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
  expect((await request.post(`/api${path}`, { headers: { "Auth-Token": owner.token }, data: { email } })).status()).toBe(422)
  for (const member of [owner, colleague]) {
    const privateHeaders = { "Auth-Token": member.token }
    expect((await request.get("/api/project-guests/people", { headers: privateHeaders })).status()).toBe(403)
    expect((await request.patch(`/api/project-guests/directory/${colleague.user.id}`, { headers: privateHeaders, data: { display_name: "Other" } })).status()).toBe(403)
  }
  const issued = await post(request, path, { email, display_name: "Project visitor" }, owner.token)
  expect(["sent", "link"]).toContain(issued.delivery)
  await post(request, `/project-guests/conversion/${colleague.user.id}`, { projects: [], confirm: true, keep_none: true }, admin.token)
  const projectOwnerHeaders = { "Auth-Token": owner.token }
  expect((await request.post("/api/instance/password-reset-links", { headers: projectOwnerHeaders, data: { user_id: colleague.user.id } })).status()).toBe(403)
  expect((await request.get(`/api/project-guests/promotion/${colleague.user.id}`, { headers: projectOwnerHeaders })).status()).toBe(403)
  const guest = await post(request, "/signin_by_email", { email: colleague.user.email, password })
  expect((await (await request.get("/api/project-guests/mine", { headers: { "Auth-Token": guest.token } })).json())).toEqual([])
})
