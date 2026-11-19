import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_lab", "Uses the isolated single-Lab API profile")
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
})

test("single Lab keeps the project-led home and shared resources with AI disabled", async ({ page }, testInfo) => {
  const status = await (await page.request.get("/api/instance")).json()
  expect(status.single_lab).toBe(true)
  expect(status.ai_enabled).toBe(false)
  await page.goto("/home")
  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByTestId("home-project-card").first()).toBeVisible()
  await expect(page.getByTestId("single-lab-identity")).toHaveText("Dev Demo Lab")
  await expect(page.getByTestId("home-project-card")).not.toContainText(["Dev Demo Lab"])
  const resources = page.getByTestId("home-resources")
  await expect(resources.getByRole("link", { name: "共享知识", exact: true })).toHaveAttribute("href", "/organization/knowledge")
  await expect(resources.getByRole("link", { name: "实验室日志", exact: true })).toHaveAttribute("href", "/organization/records")
  await expect(resources.locator("a[href=\"/labs/my\"]")).toHaveCount(0)
  await expect(page.getByTestId("app-shell-header").getByRole("button", { name: "全部对话", exact: true })).toHaveCount(0)
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: 980 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    const overlaps = await page.getByTestId("app-shell-header").evaluate((el) => {
      const boxes = Array.from(el.querySelectorAll("button, a"))
        .map(item => item.getBoundingClientRect())
        .filter(box => box.width > 0 && box.height > 0)
        .sort((a, b) => a.left - b.left)
      return boxes.some((box, index) => index > 0 && box.left < boxes[index - 1].right - 1)
    })
    expect(overlaps, `single-Lab header controls overlap at ${width}px`).toBe(false)
    await page.screenshot({ path: testInfo.outputPath(`single-lab-home-${width}.png`), fullPage: true, animations: "disabled" })
  }
})

test("legacy Lab entry opens projects and project breadcrumbs omit the fixed Lab", async ({ page }) => {
  await page.goto("/labs/my")
  await expect(page).toHaveURL(/\/projects(?:\/my)?$/)
  await page.goto("/labs/dev_lab/projects/quickstart/protocols")
  await expect(page.getByRole("heading", { name: "Quickstart Protocol Testing", exact: true })).toBeVisible()
  await expect(page.locator(".global-breadcrumb")).not.toContainText("dev_lab")
  await expect(page.locator(".global-breadcrumb")).toContainText("项目")
  await page.goto("/labs/not_this_workspace/projects")
  await expect(page).toHaveURL(/\/404\/lab$/)
  await page.goto("/home")
  await page.getByTestId("home-project-card").filter({ hasText: "Quickstart Protocol Testing" }).getByTestId("home-resume-project").click()
  await expect(page).toHaveURL(/quickstart\/protocols$/)
})

test("management stays separate from shared resources and member API permissions remain enforced", async ({ page, browser }) => {
  await page.goto("/home")
  await page.getByTestId("app-shell-header").getByRole("button", { name: "更多", exact: true }).click()
  await expect(page.getByText("实验室管理", { exact: true })).toBeVisible()
  await page.getByText("实验室管理", { exact: true }).hover()
  await page.getByText("设置", { exact: true }).last().click()
  await expect(page).toHaveURL(/\/organization\/settings$/)
  await expect(page.getByRole("heading", { name: "实验室管理", exact: true })).toBeVisible()
  await page.goto("/labs/dev_lab/knowledge")
  await expect(page.getByRole("heading", { name: "实验室共享", exact: true })).toBeVisible()
  const context = await browser.newContext({ storageState: "tests/e2e/.auth/viewer.json" })
  try {
    const viewer = await context.newPage()
    await viewer.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await viewer.goto("/home")
    await viewer.getByTestId("app-shell-header").getByRole("button", { name: "更多", exact: true }).click()
    await expect(viewer.getByText("成员与权限", { exact: true })).toBeVisible()
    await expect(viewer.getByText("实验室管理", { exact: true })).toHaveCount(0)
    const f = await loadFixtures()
    const login = await viewer.request.post("/api/signin_by_email", { data: { email: "dev.viewer@airalogy.dev", password: "AiralogyDev123!" } })
    const headers = { "Auth-Token": (await login.json()).token }
    const denied = await viewer.request.put(`/api/labs/${f.lab.id}`, { headers, data: { name: "Denied change", description: "Synthetic unauthorized request" } })
    expect(denied.status()).toBe(403)
  }
  finally { await context.close() }
})

test("new Project and Record choices inherit the Lab without a Lab selector", async ({ page }, testInfo) => {
  await page.goto("/projects")
  await page.getByRole("button", { name: /新建项目|创建项目/ }).first().click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("保存位置：Dev Demo Lab")
  await expect(dialog.getByText("实验室", { exact: true })).toHaveCount(0)
  await dialog.getByRole("button", { name: "取消", exact: true }).click()
  await page.goto("/labs/dev_lab/projects/quickstart/protocols")
  await page.getByTestId("app-shell-header").getByRole("button", { name: "新建", exact: true }).click()
  await page.getByText("新建记录", { exact: true }).click()
  await expect(page.getByRole("dialog")).toContainText("选择项目")
  await expect(page.getByText("新建记录", { exact: true })).not.toBeVisible()
  await expect(page.getByRole("dialog")).toContainText("Quickstart Protocol Testing")
  await expect(page.getByRole("dialog").locator(".n-data-table-tr").first()).toBeVisible()
  await expect(page.getByRole("dialog")).not.toContainText("Select lab and project")
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath("single-lab-new-record-mobile.png"), fullPage: true, animations: "disabled" })
})

test("personal writing remains private in a single Lab", async ({ page }) => {
  const login = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  const id = randomUUID()
  const created = await page.request.post("/api/research-documents", { headers, data: { id, scope_type: "personal", title: "合成私有文档", body: "仅用于权限回归。" } })
  expect(created.ok(), await created.text()).toBeTruthy()
  const viewer = await page.request.post("/api/signin_by_email", { data: { email: "dev.viewer@airalogy.dev", password: "AiralogyDev123!" } })
  const denied = await page.request.get(`/api/research-documents/${id}`, { headers: { "Auth-Token": (await viewer.json()).token } })
  expect([403, 404]).toContain(denied.status())
  await page.goto("/home")
  await expect(page.getByTestId("home-recent-documents")).toContainText("合成私有文档")
})
