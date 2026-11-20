import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { changeAccountLanguage, loadFixtures, mockAIEnabled } from "./fixtures"

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
})

for (const width of [1440, 876, 390]) {
  test(`Home Aira keeps the workbench and draft at ${width}px`, async ({ page }, testInfo) => {
    const question = "合成验收：怎样整理本周进展？"
    const answer = "可以先整理已完成的事项。"
    const id = randomUUID()
    await mockAIEnabled(page, () => true, { 2: "qwen3.5-plus" })
    await page.route("**/chats/qa/message", async (route) => {
      const payload = route.request().postDataJSON()
      expect(JSON.stringify(payload.message)).toContain(question)
      expect(payload.protocol_id).toBeUndefined()
      expect(payload.model.model_type).toBe(2)
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          JSON.stringify({ type: "meta", data: { chat_id: id } }),
          JSON.stringify({ type: "message", data: { index: 0, message: { role: "assistant", content: answer } } }),
          "[DONE]",
        ].map(data => `data: ${data}\n\n`).join(""),
      })
    })
    await page.setViewportSize({ width, height: 850 })
    await page.goto("/home")
    const url = page.url()
    const trigger = page.getByTestId("home-aira")
    const panel = page.getByRole(width >= 900 ? "complementary" : "dialog", { name: "Aira", exact: true })
    const input = panel.getByTestId("chat-input").locator("[contenteditable=true]")
    await trigger.click()
    await expect(input).toBeVisible()
    await expect(panel.getByTestId("chat-model")).toHaveText("qwen3.5-plus")
    await expect(panel.getByRole("button", { name: "qwen3.5-plus" })).toHaveCount(0)
    const bounds = await panel.boundingBox()
    const expectedWidth = width >= 900 ? 380 : Math.min(width, 460)
    expect(Math.round(bounds!.width)).toBe(expectedWidth)
    await expect.poll(async () => Math.round((await panel.boundingBox())!.x)).toBe(width - expectedWidth)
    if (width >= 900) {
      const main = await page.getByTestId("app-shell-content").boundingBox()
      expect(main!.x + main!.width).toBeLessThanOrEqual(bounds!.x + 1)
      const resources = page.getByTestId("home-resources").locator("details")
      await resources.locator("summary").click()
      await expect(resources).toHaveAttribute("open", "")
      const history = panel.getByTestId("open-aira-history")
      await expect(history).toBeInViewport({ ratio: 1 })
      await expect(panel.getByTestId("chat-submit")).toBeInViewport({ ratio: 1 })
      await expect(page.locator(".n-drawer-mask:visible")).toHaveCount(0)
    }
    await input.fill(question)
    await page.keyboard.press("Escape")
    await expect(panel).toBeHidden()
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(input).toHaveText(question)
    await panel.getByTestId("chat-submit").click()
    await expect(panel.getByText(answer, { exact: true })).toBeVisible()
    await expect(page).toHaveURL(url)
    expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`home-aira-${width}.png`) })
    await panel.getByRole("button", { name: "关闭" }).click()
    await trigger.click()
    await expect(panel.getByText(answer, { exact: true })).toBeVisible()
    await panel.getByRole("button", { name: "关闭" }).click()
    await expect(page).toHaveURL(url)
    if (width === 1440) {
      await page.getByTestId("header-aira").click()
      await expect(input).toBeVisible()
      await expect(panel.getByTestId("open-aira-history")).toHaveAttribute("href", `/chat?chat=${id}`)
      // The synthetic model response is stored on this device only.
      await page.goto("/chat")
      await expect(page).toHaveURL(/\/chat(?:\?|$)/)
      await expect(page.getByTestId("account-chat-history")).toBeVisible()
      await expect(page.getByRole("tab", { name: "此设备" })).toHaveCount(0)
      await expect(page.getByTestId("account-chat-history").locator(`[data-chat-id="${id}"]`)).toHaveCount(0)
    }
  })
}

test("Aira resizes its drawer and dock and shows the selected server model", async ({ page }, testInfo) => {
  await mockAIEnabled(page, () => true, { 1: "qwen3.5-flash", 4: "gpt-4.1" })
  await page.setViewportSize({ width: 878, height: 985 })
  await page.goto("/home")
  const open = page.getByTestId("home-aira")
  await open.click()
  const handle = page.getByRole("separator", { name: "调整 Aira 面板宽度" })
  const panel = page.getByTestId("home-aira-panel")
  const composer = panel.getByTestId("chat-input").locator("[contenteditable=true]")
  const model = panel.getByTestId("chat-model")
  await expect(model).toHaveText("qwen3.5-flash")
  await model.click()
  await page.locator(".n-dropdown-menu").getByText("gpt-4.1", { exact: true }).click()
  await expect(model).toHaveText("gpt-4.1")
  await composer.fill("合成草稿")
  await expect(handle).toHaveAttribute("aria-valuenow", "460")
  await handle.hover()
  const box = (await handle.boundingBox())!
  const x = box.x + box.width / 2
  const y = box.y + box.height / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x - 80, y, { steps: 6 })
  await page.mouse.up()
  await expect(handle).toHaveAttribute("aria-valuenow", "540")
  await expect.poll(async () => Math.round((await panel.boundingBox())!.width)).toBe(540)
  await page.screenshot({ path: testInfo.outputPath("aira-resized-878.png") })
  await handle.press("ArrowRight")
  await expect(handle).toHaveAttribute("aria-valuenow", "524")
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(handle).toHaveCount(0)
  await expect.poll(async () => Math.round((await panel.boundingBox())!.width)).toBe(390)
  await expect(composer).toHaveText("合成草稿")
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(handle).toHaveAttribute("aria-valuenow", "524")
  await expect(composer).toHaveText("合成草稿")
  await handle.press("End")
  await expect(handle).toHaveAttribute("aria-valuenow", "720")
  const main = await page.getByTestId("app-shell-content").boundingBox()
  expect(main!.x + main!.width).toBeLessThanOrEqual((await handle.boundingBox())!.x + 1)
  await page.reload()
  await open.click()
  await expect(handle).toHaveAttribute("aria-valuenow", "720")
  await handle.press("Home")
  await expect(handle).toHaveAttribute("aria-valuenow", "320")
  await expect(panel.getByTestId("chat-submit")).toBeInViewport({ ratio: 1 })
  await handle.dblclick()
  await expect(handle).toHaveAttribute("aria-valuenow", "380")
  await page.goto("/chat")
  await expect(page.getByTestId("chat-model")).toHaveText("qwen3.5-flash")
})

test("Home Aira account history opens the same conversation on a fresh phone", async ({ page, browser }) => {
  await mockAIEnabled(page.context(), () => true)
  await page.goto("/home")
  await page.getByTestId("home-aira").click()
  const panel = page.getByTestId("home-aira-panel")
  // A deterministic personal-memory command persists a real conversation without a model call.
  const send = panel.getByTestId("chat-input").locator("[contenteditable=true]")
  await send.fill("记住：合成验收未支持偏好")
  const completed = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
  await panel.getByTestId("chat-submit").click()
  expect((await completed).ok()).toBeTruthy()
  const link = panel.getByTestId("open-aira-history")
  await expect(link).toHaveAttribute("href", /\/chat\?chat=[a-f0-9-]{36}/)
  const href = (await link.getAttribute("href"))!
  const id = new URL(href, page.url()).searchParams.get("chat")
  const legacy = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(name => name.startsWith("chatStorage:"))!
    return localStorage.getItem(key)!
  })
  const viewer = await browser.newContext({ storageState: "tests/e2e/.auth/viewer.json" })
  try {
    await viewer.addInitScript(cache => localStorage.setItem("chatStorage", cache), legacy)
    const own = await viewer.newPage()
    await mockAIEnabled(own, () => true)
    await own.goto("/chat")
    const list = own.getByTestId("account-chat-history")
    await expect(list).toBeVisible()
    await expect(list.locator(".n-spin")).toHaveCount(0)
    await expect(list.locator(`[data-chat-id="${id}"]`)).toHaveCount(0)
  }
  finally { await viewer.close() }
  const popupPromise = page.waitForEvent("popup")
  await link.click()
  const popup = await popupPromise
  await expect(popup.getByTestId("account-chat-history")).toBeVisible()
  await expect(popup.getByText("个人记忆请求", { exact: true }).last()).toBeVisible()
  const desktopTitle = popup.getByTestId("account-chat-history").locator(`[data-chat-id="${id}"]`)
  await expect(desktopTitle).toHaveText("个人记忆请求")
  await expect(popup.getByText("平台已处理这次个人记忆请求，科研数据未变更。", { exact: true })).toBeVisible()
  await changeAccountLanguage(popup, "English")
  await expect(desktopTitle).toHaveText("Personal memory request")
  await expect(popup.getByText("Platform handled this personal memory request. Research data was unchanged.", { exact: true })).toBeVisible()
  await popup.close()

  const phone = await browser.newContext({ storageState: "tests/e2e/.auth/owner.json", viewport: { width: 390, height: 844 } })
  try {
    const fresh = await phone.newPage()
    await mockAIEnabled(fresh, () => true)
    await fresh.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    // An older device retains an unscoped cache. Import only sessions whose owner
    // is confirmed by the API; a new device can open the same history without it.
    await fresh.goto("/chat")
    await fresh.getByRole("button", { name: "对话历史", exact: true }).click()
    const history = fresh.getByTestId("account-chat-history")
    const mobileTitle = history.locator(`[data-chat-id="${id}"]`)
    await expect(mobileTitle).toHaveText("个人记忆请求")
    await mobileTitle.click()
    await expect(fresh).toHaveURL(new RegExp(String(id)))
    await expect(fresh.getByText("平台已处理这次个人记忆请求，科研数据未变更。", { exact: true })).toBeVisible()
    const input = fresh.getByTestId("chat-input").locator("[contenteditable=true]")
    await input.fill("记住：合成验收其他未支持偏好")
    const request = fresh.waitForRequest(r => r.url().endsWith("/chats/qa/message"))
    const persisted = fresh.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
    await fresh.getByTestId("chat-submit").click()
    expect((await request).postDataJSON().chat_id).toBe(id)
    expect((await persisted).ok()).toBeTruthy()
    await fresh.evaluate(cache => localStorage.setItem("chatStorage", cache), legacy)
    await fresh.reload()
    await expect.poll(async () => fresh.evaluate(() => {
      const key = Object.keys(localStorage).find(name => name.startsWith("chatStorage:"))
      return !!key && JSON.parse(localStorage.getItem(key)!).data.legacyOwnershipChecked
    })).toBe(true)
    await expect(fresh.getByText("平台已处理这次个人记忆请求，科研数据未变更。", { exact: true })).toHaveCount(2)
    await changeAccountLanguage(fresh, "English")
    await expect(fresh.getByText("Platform handled this personal memory request. Research data was unchanged.", { exact: true })).toHaveCount(2)
    await expect(fresh.getByText("Personal memory request", { exact: true }).first()).toBeVisible()
    expect(await fresh.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  }
  finally { await phone.close() }
})

test("Home Aira respects the organization AI switch", async ({ page }) => {
  await mockAIEnabled(page, () => false)
  await page.goto("/home")
  await expect(page.getByTestId("task-workbench")).toBeVisible()
  await expect(page.getByTestId("home-aira")).toHaveCount(0)
  await expect(page.getByTestId("header-aira")).toHaveCount(0)
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
