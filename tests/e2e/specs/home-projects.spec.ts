import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
})

test("project document work resumes directly and pins share the existing project list", async ({ page }, testInfo) => {
  test.setTimeout(120000)
  const f = await loadFixtures()
  const login = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  const created = await page.request.post("/api/projects", { headers, data: { lab_id: f.lab.id, uid: `home_${randomUUID().replaceAll("-", "").slice(0, 10)}`, name: "合成演示：材料稳定性研究", type: 1 } })
  expect(created.ok(), await created.text()).toBeTruthy()
  const project = await created.json()
  await page.goto(`/labs/${f.lab.uid}/projects/${project.uid}/overview`)
  await expect(page.getByText(project.name, { exact: true }).first()).toBeVisible()
  const id = randomUUID()
  const doc = await page.request.post("/api/research-documents", { headers, data: { id, scope_type: "project", project_id: f.project.id, title: "合成演示：继续观察文档", body: "这是用于界面验收的虚构文档。" } })
  expect(doc.ok(), await doc.text()).toBeTruthy()
  const captured = page.waitForResponse(response => response.url().endsWith("/api/workspace/project-visits") && response.request().postDataJSON()?.resource_id === id)
  await page.goto(`/research-documents/${id}`)
  await expect(page.getByTestId("document-save-state")).toHaveText("已保存")
  expect((await captured).ok()).toBeTruthy()
  await page.getByRole("banner").getByRole("link").first().click()
  await expect(page).toHaveURL(/\/home$/)
  const card = page.getByTestId("home-project-card").filter({ hasText: "Quickstart Protocol Testing" })
  await expect(card).toContainText("合成演示：继续观察文档")
  await expect(page.getByTestId("home-recent-documents")).not.toContainText("合成演示：继续观察文档")
  await expect(card.getByTestId("home-open-project")).toHaveAttribute("href", /\/overview$/)
  await expect(card.getByTestId("home-resume-project")).toHaveAttribute("href", `/research-documents/${id}`)
  const pin = card.locator("button[aria-pressed]")
  if (await pin.getAttribute("aria-pressed") === "true")
    await pin.click()
  await expect(pin).toHaveAttribute("aria-pressed", "false")
  await pin.click()
  await expect(pin).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("home-project-card").first()).toContainText("Quickstart Protocol Testing")
  for (const width of [390, 820, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(card.getByTestId("home-resume-project")).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    const heading = await page.getByTestId("home-project-workspaces").boundingBox()
    const attention = await page.getByTestId("home-attention-panel").boundingBox()
    expect(heading!.y).toBeLessThan(attention!.y)
    await page.screenshot({ path: testInfo.outputPath(`home-projects-${width}.png`), fullPage: true })
  }
  await card.getByTestId("home-resume-project").click()
  await expect(page.getByTestId("document-title").locator("textarea")).toHaveValue("合成演示：继续观察文档")
})

test("a saved Record draft survives reload and resumes from its project card", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto("/labs/dev_lab/projects/quickstart/protocols/drug_response_ic50_en/add?newRecord=true")
  const field = page.locator("#form-research_variable-study_id [data-rec-focus-key=\"var:study_id\"]")
  await field.fill("SYNTHETIC-HOME-DRAFT")
  await page.getByTestId("record-save-draft").click()
  await expect(page.getByText("Draft saved on this device.", { exact: true })).toBeVisible()
  await page.reload()
  await expect(field).toHaveValue("SYNTHETIC-HOME-DRAFT")
  await page.getByRole("banner").getByRole("link").first().click()
  const card = page.getByTestId("home-project-card").filter({ hasText: "Quickstart Protocol Testing" })
  await expect(card.getByTestId("home-resume-project")).toContainText("Continue Record")
  await expect(card).toContainText("Saved on this device")
  await card.getByTestId("home-resume-project").click()
  await expect(field).toHaveValue("SYNTHETIC-HOME-DRAFT")
})

test("project service failure keeps personal writing usable and can recover", async ({ page }) => {
  await page.route("**/api/workspace/recent-projects", route => route.fulfill({ status: 503, contentType: "application/json", body: "{\"detail\":\"Synthetic unavailable\"}" }))
  await page.goto("/home")
  await expect(page.getByTestId("home-project-error")).toBeVisible()
  await expect(page.getByTestId("home-recent-documents").getByRole("link", { name: "进入个人空间" })).toBeVisible()
  const instance = await (await page.request.get("/api/instance")).json()
  await expect(page.getByTestId("home-aira")).toHaveCount(instance.ai_enabled ? 1 : 0)
  await page.unroute("**/api/workspace/recent-projects")
  await page.getByTestId("home-project-error").getByRole("button").click()
  await expect(page.getByTestId("home-project-error")).toHaveCount(0)
  await expect(page.getByTestId("home-project-card").first()).toBeVisible()
})

test("first visit offers available projects without pretending they are recent work", async ({ browser }) => {
  const context = await browser.newContext({ storageState: "tests/e2e/.auth/viewer.json" })
  const viewer = await context.newPage()
  try {
    await viewer.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await viewer.goto("/home")
    await expect(viewer.getByTestId("home-project-history-hint")).toContainText("选择一个项目开始工作")
    await expect(viewer.getByTestId("home-resume-project")).toHaveCount(0)
    await expect(viewer.getByTestId("home-project-card").first()).toBeVisible()
    await expect(viewer.getByTestId("home-recent-documents")).not.toContainText("合成演示：继续观察文档")
  }
  finally {
    await context.close()
  }
})
