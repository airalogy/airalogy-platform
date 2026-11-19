import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Uses the isolated company workspace profile")
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
})

test("company home, navigation and management remain usable at mobile and desktop widths", async ({ page }, testInfo) => {
  const status = await (await page.request.get("/api/instance")).json()
  expect(status.organization).toEqual(status.lab)
  expect(status.organization.organization_type).toBe("company")
  expect(status.single_organization).toBe(true)
  expect(status.ai_enabled).toBe(false)
  await page.goto("/home")
  await expect(page.getByTestId("single-lab-identity")).toHaveText("Dev R&D Company")
  await expect(page.getByTestId("home-project-card").first()).toBeVisible()
  await expect(page.getByTestId("home-resources")).toContainText("组织日志")
  await expect(page.getByTestId("home-resources")).not.toContainText("实验室")
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: 980 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth), { message: `Page fits at ${width}px` }).toBeLessThanOrEqual(1)
    await page.screenshot({ path: testInfo.outputPath(`company-home-${width}.png`), fullPage: true, animations: "disabled" })
  }
  await page.setViewportSize({ width: 1440, height: 980 })
  await page.getByTestId("organization-management-entry").click()
  await expect(page).toHaveURL(/\/members$/)
  await page.locator(".n-tabs-tab[data-name=lab-settings]").click()
  await expect(page.getByRole("heading", { name: "组织管理", exact: true })).toBeVisible()
  await expect(page.getByText("组织类型", { exact: true })).toBeVisible()
  await expect(page.getByText("组织名称", { exact: true })).toBeVisible()
  await page.goto("/labs/dev_lab/members")
  await page.getByRole("button", { name: "邀请成员", exact: true }).click()
  await expect(page.getByRole("dialog")).toContainText("组织角色")
  await expect(page.getByRole("dialog")).toContainText("协作者")
  await expect(page.getByRole("dialog")).not.toContainText("实验室")
})

test("the Airalogy product wordmark and a configured organization logo have separate identities", async ({ page }, testInfo) => {
  const original = (await (await page.request.get("/api/instance")).json()).organization
  const company = { ...original, uid: "airalogy", name: "Airalogy" }
  let logo: string | null = null
  await page.route("**/api/instance", async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), organization: company, lab: company } })
  })
  await page.route("**/api/labs/uid/airalogy", async (route) => {
    const url = new URL(route.request().url())
    url.pathname = `/api/labs/uid/${original.uid}`
    const response = await route.fetch({ url: url.href })
    const { data } = await response.json()
    await route.fulfill({ response, json: { data: { ...data, ...company, logo_url: logo } } })
  })
  await page.goto("/home")
  const header = page.getByTestId("app-shell-header")
  const brand = header.getByTestId("platform-brand")
  const organization = header.getByTestId("single-lab-identity")
  await expect(header.getByTestId("organization-management-entry")).toBeVisible()
  for (const width of [1440, 876, 390, 320]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(header.locator("..")).toHaveCSS("height", "56px")
    await expect(header.locator("..")).toHaveCSS("background-color", "rgb(246, 249, 255)")
    await expect(brand.locator("svg")).toHaveAttribute("viewBox", "0 0 684 184")
    await expect(organization).toHaveCount(0)
    await expect(header.getByTestId("global-create-trigger")).toBeInViewport()
    if (width < 1280) {
      const menu = header.getByTestId("workspace-menu-trigger")
      await menu.click()
      await expect(page.getByRole("link", { name: "项目", exact: true })).toBeVisible()
      await menu.click()
    }
    if (width === 876 || width === 390) {
      await header.evaluate(el => (el.ownerDocument.activeElement as HTMLElement)?.blur())
      await header.screenshot({ path: testInfo.outputPath(`airalogy-header-${width}.png`) })
    }
  }
  logo = "/images/avatar_default.svg"
  await page.reload()
  await expect(organization).toHaveText("Airalogy")
  await expect(organization.locator("img")).toHaveAttribute("src", logo)
  await expect(brand.locator("svg")).toHaveAttribute("viewBox", "0 0 184 184")
  company.name = "独立验收机构"
  await page.setViewportSize({ width: 1440, height: 980 })
  await page.reload()
  await expect(organization).toHaveText(company.name)
  await expect(organization.locator("img")).toBeVisible()
  await expect(brand.locator("svg")).toHaveAttribute("viewBox", "0 0 684 184")
})

test("choosing an organization logo uploads it once and saves its attachment ID", async ({ page }) => {
  const organization = (await (await page.request.get("/api/instance")).json()).organization
  await page.goto("/organization/members")
  await page.locator(".n-tabs-tab[data-name=lab-settings]").click()
  const attachmentId = randomUUID()
  let uploads = 0
  await page.route("**/api/attachments/", async (route) => {
    uploads++
    await route.fulfill({ json: { id: attachmentId, filename: "test-logo.png", url: "/images/avatar_default.svg" } })
  })
  // Exercise the save form without changing the shared test organization's identity.
  await page.route(`**/api/organizations/${organization.id}`, async (route) => {
    if (route.request().method() === "PUT")
      await route.fulfill({ json: { ...organization, logo: attachmentId } })
    else
      await route.fallback()
  })
  const upload = page.waitForResponse(r => r.url().endsWith("/api/attachments/"))
  await page.locator("input[type=file]").first().setInputFiles({
    name: "test-logo.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMQjz8GAAHNAT1PNjFiAAAAAElFTkSuQmCC", "base64"),
  })
  await upload
  const save = page.waitForRequest(r => r.method() === "PUT" && r.url().endsWith(`/organizations/${organization.id}`))
  await page.getByRole("button", { name: "保存更改", exact: true }).click()
  expect((await save).postDataJSON().logo).toBe(attachmentId)
  expect(uploads).toBe(1)
})

test("a company member writes a private document and resumes the same project from a legacy link", async ({ page }) => {
  const f = await loadFixtures()
  await page.goto(`/labs/${f.lab.uid}/projects/${f.project.uid}/protocols`)
  await expect(page.locator(".global-breadcrumb")).not.toContainText("dev_lab")
  await expect(page.getByRole("heading", { name: "Quickstart Protocol Testing", exact: true })).toBeVisible()
  await page.goto(`/labs/${f.lab.uid}/projects/${f.project.uid}/documents`)
  await expect(page.getByTestId("document-audience").first()).toContainText("组织所有者")
  await expect(page.getByTestId("document-audience").first()).not.toContainText("实验室")
  await page.goto("/home")
  await page.getByTestId("home-project-card").filter({ hasText: "Quickstart Protocol Testing" }).getByTestId("home-resume-project").click()
  await expect(page).toHaveURL(/quickstart\/documents$/)
  await page.goto("/home")
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "新建文档", exact: true }).click()
  const dialog = page.getByTestId("new-document-dialog")
  await expect(dialog.getByTestId("document-audience")).toContainText("仅自己可见")
  await dialog.getByTestId("new-document-title").locator("input").fill(`合成眼镜研发想法 ${randomUUID()}`)
  const response = page.waitForResponse(r => r.url().endsWith("/api/research-documents") && r.request().method() === "POST")
  await dialog.getByTestId("create-document-confirm").click()
  const created = await response
  expect(created.ok(), await created.text()).toBeTruthy()
  const document = await created.json()
  expect(document.scope_type).toBe("personal")
  await expect(page.getByTestId("research-document-editor")).toBeVisible()
  const viewer = await page.request.post("/api/signin_by_email", { data: { email: "dev.viewer@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await viewer.json()).token }
  const denied = await page.request.get(`/api/research-documents/${document.id}`, { headers })
  expect([403, 404]).toContain(denied.status())
  const update = await page.request.put(`/api/organizations/${f.lab.id}`, { headers, data: { description: "Denied", organization_type: "institution" } })
  expect(update.status()).toBe(403)
})
