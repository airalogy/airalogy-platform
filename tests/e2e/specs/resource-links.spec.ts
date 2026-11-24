import type { Page } from "@playwright/test"
import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")
const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
let path: string
let projectPath: string
let publicTitle: string
let publicPath: string
let recordPath: string
let projectId: string
let protocolId: string
let recordId: string
let query: Record<string, string>
let viewer: Record<string, string>
const singleOrg = ["single_lab", "single_organization"].includes(process.env.E2E_DEPLOYMENT_MODE || "")
const privateTitle = "Shared inspection checklist"
test.use({ storageState: { cookies: [], origins: [] } })

test.beforeAll(async ({ request }) => {
  const fixtures = await loadFixtures()
  async function session(email: string) {
    const res = await request.post(`${api}/signin_by_email`, { data: { email, password: "AiralogyDev123!" } })
    expect(res.status()).toBe(200)
    return { "Auth-Token": (await res.json()).token as string }
  }
  const headers = await session("dev.owner@airalogy.dev")
  viewer = await session("dev.viewer@airalogy.dev")
  const uid = `link_${randomUUID().replaceAll("-", "")}`
  const project = await request.post(`${api}/projects`, {
    headers,
    data: { uid, name: "Private inspection project", lab_id: fixtures.lab.id, type: 1, copy_members: false },
  })
  expect(project.ok(), await project.text()).toBeTruthy()
  projectId = (await project.json()).id
  const archive = zipSync({
    "protocol.aimd": strToU8("# Inspection\n{{var|label: str}}"),
    "protocol.toml": strToU8(`[airalogy_protocol]\nid = "inspection"\nname = "${privateTitle}"\nversion = "1.0.0"\n`),
  })
  const uploaded = await request.post(`${api}/protocols`, { headers, multipart: {
    project_id: projectId,
    file: { name: "inspection.zip", mimeType: "application/zip", buffer: Buffer.from(archive) },
  } })
  expect(uploaded.ok(), await uploaded.text()).toBeTruthy()
  protocolId = (await uploaded.json()).data.id
  const recorded = await request.post(`${api}/protocols/${protocolId}/records`, { headers, data: {
    var: { label: "Synthetic inspection" },
    step: {},
    check: {},
    report: "",
  } })
  expect(recorded.ok(), await recorded.text()).toBeTruthy()
  recordId = (await recorded.json()).id
  const org = singleOrg ? "" : `/orgs/${fixtures.lab.uid}`
  projectPath = `${org}/projects/${uid}`
  path = `${projectPath}/protocols/inspection/protocol`
  recordPath = `${projectPath}/protocols/inspection/v1.0.0/record/${recordId}/v1`
  publicPath = `${org}/projects/${fixtures.project.uid}/protocols/${fixtures.schema_governance.protocol_uid}/protocol`
  const visible = await request.get(`${api}/protocols/by_uid`, { headers: singleOrg ? headers : {}, params: { lab_uid: fixtures.lab.uid, project_uid: fixtures.project.uid, protocol_uid: fixtures.schema_governance.protocol_uid } })
  expect(visible.ok(), await visible.text()).toBeTruthy()
  publicTitle = (await visible.json()).name
  query = { lab_uid: fixtures.lab.uid, project_uid: uid, protocol_uid: "inspection" }
})

async function login(page: Page, email: string) {
  await page.getByTestId("login-email").locator("input").fill(email)
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
}

test("private and missing links have indistinguishable read responses", async ({ request }) => {
  for (const headers of [{}, viewer]) {
    for (const [url, missing, params, missingParams] of [
      [`/projects/${projectId}`, `/projects/${randomUUID()}`, {}, {}],
      [`/protocols/${protocolId}`, `/protocols/${randomUUID()}`, {}, {}],
      ["/protocols/by_uid", "/protocols/by_uid", query, { ...query, protocol_uid: "missing" }],
      ["/projects/by_uid", "/projects/by_uid", { lab_uid: query.lab_uid, project_uid: query.project_uid }, { lab_uid: query.lab_uid, project_uid: "missing" }],
      [`/protocols/${protocolId}/records/${recordId}`, `/protocols/${protocolId}/records/${randomUUID()}`, { version: "1" }, { version: "1" }],
    ] as const) {
      const denied = await request.get(api + url, { headers, params })
      const absent = await request.get(api + missing, { headers, params: missingParams })
      expect(denied.status()).toBe(404)
      expect(absent.status()).toBe(404)
      expect(await denied.json()).toEqual(await absent.json())
    }
  }
})

for (const [locale, width] of [["zh-CN", 1280], ["en-US", 390]] as const) {
  test(`shared protocol opens after sign-in on ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 820 })
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    const destination = `${path}?view=shared#inspection`
    await page.goto(destination)
    const panel = page.getByTestId("resource-access-state")
    await expect(panel.getByRole("heading")).toHaveText(locale === "zh-CN" ? "登录后查看" : "Sign in to view this page")
    await expect(page.getByText(privateTitle, { exact: true })).toHaveCount(0)
    await panel.getByRole("link", { name: /登录并继续|Sign in and continue/ }).click()
    await expect(page.getByTestId("login-email")).toBeVisible()
    expect(new URL(page.url()).searchParams.get("redirect")).toBe(destination)
    await login(page, "dev.owner@airalogy.dev")
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === destination)
    await expect(page.getByText(privateTitle, { exact: true }).first()).toBeVisible()
    await expect(panel).toHaveCount(0)
    if (width === 1280) {
      await page.goto(`${projectPath}/overview`)
      await expect(page.getByTestId("project-header")).toContainText("Private inspection project")
      await page.goto(recordPath)
      await expect(page.getByRole("button", { name: /导出.*PDF|Export.*PDF/i })).toBeVisible()
      await expect(panel).toHaveCount(0)
    }
  })
}

test("member without access sees recovery advice across direct links", async ({ page }) => {
  await page.goto("/login")
  await login(page, "dev.viewer@airalogy.dev")
  await expect(page).not.toHaveURL(/\/login/)
  for (const target of [path, `${projectPath}/overview`, recordPath, path.replace("/inspection/", "/missing/")]) {
    await page.goto(target)
    const panel = page.getByTestId("resource-access-state")
    await expect(panel).toContainText(/联系分享者|person who shared/)
    await expect(panel.getByRole("link", { name: /登录并继续|Sign in and continue/ })).toHaveCount(0)
    await expect(page.getByText(privateTitle, { exact: true })).toHaveCount(0)
  }
})

test("a readable protocol recovers after a temporary failure", async ({ page }) => {
  if (singleOrg) {
    await page.goto("/login")
    await login(page, "dev.owner@airalogy.dev")
    await expect(page).not.toHaveURL(/\/login/)
  }
  await page.route("**/protocols/by_uid?**", route => route.fulfill({ status: 503, json: {} }))
  await page.goto(publicPath)
  const panel = page.getByTestId("resource-access-state")
  await expect(panel.getByRole("button", { name: /重新加载|Try again/ })).toBeVisible()
  await page.unroute("**/protocols/by_uid?**")
  await panel.getByRole("button").click()
  await expect(panel).toHaveCount(0)
  await expect(page.getByText(publicTitle, { exact: true }).first()).toBeVisible()
  expect(new URL(page.url()).pathname).toBe(publicPath)
})
