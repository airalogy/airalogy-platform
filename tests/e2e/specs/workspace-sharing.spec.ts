import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")
const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
test.skip(!["single_lab", "single_organization"].includes(process.env.E2E_DEPLOYMENT_MODE || ""), "Single organization workspace sharing")

test("project audience, selected version and materials, organization policy and withdrawal", async ({ request, page, browser }) => {
  test.setTimeout(150000)
  page.setDefaultTimeout(18000)
  const fixtures = await loadFixtures()
  async function signIn(email: string) {
    const session = await request.post(`${api}/signin_by_email`, { data: { email, password: "AiralogyDev123!" } })
    expect(session.status()).toBe(200)
    return { "Auth-Token": (await session.json()).token as string }
  }
  const headers = await signIn("dev.owner@airalogy.dev")
  const viewer = await signIn("dev.viewer@airalogy.dev")
  const uid = `optics_${randomUUID().replaceAll("-", "").slice(0, 14)}`
  const created = await request.post(`${api}/projects`, { headers, data: { lab_id: fixtures.lab.id, uid, name: "Synthetic optics project", description: "Optics summary" } })
  expect(created.status()).toBe(200)
  const project = await created.json()
  const pid = project.id
  const policy = `${api}/sharing/policy/${fixtures.lab.id}`
  const reader = `${api}/sharing/project/${pid}/organization-reading`
  const manage = `${api}/sharing/manage/${pid}`
  const base = `/projects/${uid}`
  const ordinary = await browser.newContext({ storageState: "tests/e2e/.auth/viewer.json", viewport: { width: 390, height: 844 } })
  const guest = await browser.newContext({ storageState: { cookies: [], origins: [] }, viewport: { width: 390, height: 844 } })
  const mobile = await ordinary.newPage()
  const visitor = await guest.newPage()
  const origin = new URL(page.url() === "about:blank" ? (process.env.E2E_WEB_URL || "http://127.0.0.1:3100") : page.url()).origin
  const fixtureOptions = await request.get(policy, { headers })
  expect(fixtureOptions.ok()).toBeTruthy()
  const wasEnabled = (await fixtureOptions.json()).enabled
  const setPolicy = async (enabled: boolean) => expect((await request.put(policy, { headers, data: { enabled } })).ok()).toBeTruthy()
  try {
    expect(project.organization_readable).toBe(false)
    expect((await request.get(`${api}/projects/${pid}`, { headers: viewer })).status()).toBe(404)
    expect((await request.put(policy, { headers: viewer, data: { enabled: true } })).status()).toBe(403)
    expect((await request.put(reader, { headers: viewer, data: { enabled: true } })).ok()).toBeFalsy()
    const archive = (version: string, body: string) => Buffer.from(zipSync({
      "protocol.aimd": strToU8(`# Optics\n${body}\n\n{{step|inspect, title="Inspect the lens"}}\n\n{{var|label: str}}`),
      "protocol.toml": strToU8(`[airalogy_protocol]\nid="inspection"\nname="Optics inspection"\nversion="${version}"\n`),
      "handout.txt": strToU8("Selected handout"),
      "worksheet.csv": strToU8("Unshared worksheet"),
    }))
    const upload = async (version: string, content: string, protocol_id?: string) => {
      const res = await request.post(`${api}/protocols`, { headers, multipart: {
        project_id: pid,
        ...(protocol_id ? { protocol_id } : {}),
        file: { name: "inspection.zip", mimeType: "application/zip", buffer: archive(version, content) },
      } })
      expect(res.ok(), await res.text()).toBeTruthy()
      return (await res.json()).data.id
    }
    const proto = await upload("1.0.0", "First optical inspection")
    const record = await request.post(`${api}/protocols/${proto}/records`, { headers, data: { var: { label: "Private raw reading" }, step: {}, check: {}, report: "" } })
    expect(record.ok()).toBeTruthy()
    const recordId = (await record.json()).id
    const recordUrl = `${api}/protocols/${proto}/records/${recordId}?version=1`
    const params = { protocol_id: proto, version: "1.0.0" }
    const plan = await (await request.get(manage, { headers, params })).json()
    const outdated = await request.post(manage, { headers, params, data: { audience: "organization", preview: "obsolete" } })
    expect(outdated.status()).toBe(409)
    const pub = (audience: string, materials: string[] = []) => request.post(manage, { headers, params, data: { audience, preview: plan.preview, materials } })
    await setPolicy(false)
    expect((await pub("public")).status()).toBe(403)
    const orgLink = await (await pub("organization")).json()
    expect((await request.get(`${api}/sharing/read/${orgLink.id}`, { headers: viewer })).ok()).toBeTruthy()
    expect((await request.get(`${api}/sharing/read/${orgLink.id}`)).status()).toBe(404)
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await page.goto(`${base}/settings`)
    await page.getByRole("radio", { name: "组织内可见 · 需登录", exact: true }).check()
    await page.getByRole("button", { name: "保存", exact: true }).last().click()
    await page.locator(".n-popconfirm").getByRole("button").last().click()
    await expect.poll(async () => (await (await request.get(`${api}/projects/${pid}`, { headers })).json()).organization_readable).toBe(true)
    await mobile.goto(`${origin + base}/overview`)
    await expect(mobile.getByRole("link", { name: "Optics inspection" })).toBeVisible()
    await mobile.getByRole("link", { name: "Optics inspection" }).click()
    await expect(mobile.getByText("First optical inspection", { exact: false }).first()).toBeVisible()
    const directory = await request.get(`${api}/projects`, { headers: viewer, params: { lab_uid: fixtures.lab.uid, uid } })
    expect((await directory.json()).projects).toMatchObject([{ uid, organization_reader: true }])
    expect((await request.get(manage, { headers: viewer, params })).ok()).toBeFalsy()
    expect((await request.get(recordUrl, { headers: viewer })).status()).toBe(404)
    await mobile.goto(`${origin + base}/operations`)
    await expect(mobile.getByTestId("resource-access-state")).toBeVisible()
    await mobile.goto(`${origin + base}/protocols/inspection/records`)
    await expect(mobile.getByTestId("resource-access-state")).toBeVisible()
    expect((await request.put(`${api}/projects/${pid}`, { headers, data: { permission_type: 2 } })).ok()).toBeTruthy()
    expect((await (await request.get(`${api}/projects/${pid}`, { headers: viewer })).json()).reader_protocols).toEqual([])
    expect((await request.get(`${api}/protocols/${proto}`, { headers: viewer })).status()).toBe(404)
    expect((await request.put(`${api}/projects/${pid}`, { headers, data: { permission_type: 1 } })).ok()).toBeTruthy()
    expect((await request.get(`${api}/projects/${pid}`)).status()).toBe(404)
    await page.goto("/organization/settings")
    await page.getByRole("checkbox", { name: "允许发布项目介绍和协议版本", exact: true }).check()
    await page.locator("section").filter({ has: page.getByRole("heading", { name: "对外分享", exact: true }) }).getByRole("button", { name: "保存", exact: true }).click()
    await page.locator(".n-popconfirm").getByRole("button").last().click()
    await expect.poll(async () => (await (await request.get(policy, { headers })).json()).enabled).toBe(true)
    await page.goto(`${base}/protocols/inspection/protocol`)
    await page.getByRole("button", { name: "分享", exact: true }).click()
    await page.getByRole("radio", { name: "对外公开 · 无需登录", exact: true }).check()
    await page.getByRole("button", { name: "预览分享内容" }).click()
    await page.getByRole("button", { name: "选择协议包中的随附材料" }).click()
    await page.getByRole("checkbox", { name: "handout.txt", exact: true }).check()
    await page.getByRole("button", { name: "确认发布" }).click()
    const publishedLink = page.getByRole("link", { name: "打开分享页" })
    await expect(publishedLink).toBeVisible()
    const href = (await publishedLink.getAttribute("href"))!
    const link = await (await pub("public", ["handout.txt"])).json()
    expect(link.path).toBe(href)
    const read = `${api}/sharing/read/${link.id}`
    await visitor.goto(origin + href)
    await expect(visitor.getByRole("heading", { name: "Optics inspection" })).toBeVisible()
    await expect(visitor.getByText("handout.txt")).toBeVisible()
    await expect(visitor.getByText("Inspect the lens", { exact: false }).first()).toBeVisible()
    await expect(visitor.locator("main")).not.toContainText("{{step|")
    await expect(visitor.getByText("worksheet.csv")).toHaveCount(0)
    expect(await (await request.get(`${read}/material`, { params: { name: "handout.txt" } })).text()).toBe("Selected handout")
    expect((await request.get(`${read}/material`, { params: { name: "worksheet.csv" } })).status()).toBe(404)
    expect((await request.get(recordUrl)).status()).toBe(404)
    await upload("1.1.0", "Revised optical inspection", proto)
    expect((await (await request.get(read)).json()).body).toContain("First optical inspection")
    const cover = await (await request.get(manage, { headers })).json()
    const catalog = await (await request.post(manage, { headers, data: { preview: cover.preview, audience: "public" } })).json()
    const getCatalog = async () => (await (await request.get(`${api}/sharing/read/${catalog.id}`)).json()).protocols
    expect((await getCatalog()).map((p: { version: string }) => p.version)).toEqual(["1.0.0"])
    expect((await request.delete(`${manage}/${link.id}`, { headers, params })).status()).toBe(204)
    expect((await request.get(read)).status()).toBe(404)
    expect(await getCatalog()).toEqual([])
    expect((await request.get(`${read}/material`, { params: { name: "handout.txt" } })).status()).toBe(404)
    const fresh = await (await pub("public")).json()
    expect(fresh.id).not.toBe(link.id)
    await setPolicy(false)
    await setPolicy(true)
    for (const id of [catalog.id, fresh.id, link.id])
      expect((await request.get(`${api}/sharing/read/${id}`)).status()).toBe(404)
    expect((await request.get(`${api}/sharing/read/${orgLink.id}`, { headers: viewer })).ok()).toBeTruthy()
    await request.put(reader, { headers, data: { enabled: false } })
    expect((await request.get(`${api}/projects/${pid}`, { headers: viewer })).status()).toBe(404)
  }
  finally {
    await setPolicy(wasEnabled)
    await guest.close()
    await ordinary.close()
  }
})
