import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { mockAIEnabled } from "./fixtures"

test.use({ actionTimeout: 10000, storageState: { cookies: [], origins: [] } })

// Exercises the actual API; no AI provider is needed for explicit memory commands.
for (const [locale, width] of [["zh-CN", 1440], ["en-US", 390]] as const) {
  test(`personal memory management persists and can be cleared (${locale})`, async ({ page, request }, testInfo) => {
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signin = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const { token, user } = await signin.json()
    const headers = { "Auth-Token": token }
    const initial = await (await request.get(`${api}/aira-memory`, { headers })).json()
    await request.patch(`${api}/aira-memory`, { headers, data: { clear: true, enabled: true, expected_revision: initial.revision, request_id: randomUUID() } })
    const zh = locale === "zh-CN"
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    await page.setViewportSize({ width, height: 900 })
    try {
      await page.goto("/login")
      await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
      await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
      await page.getByTestId("login-submit").click()
      await expect(page).not.toHaveURL(/\/login/)
      await page.goto(`/users/${user.username}/settings#aira-memory`)
      const panel = page.getByTestId("aira-memory-panel")
      await expect(panel).toBeVisible()
      await panel.getByTestId("memory-language").click()
      await page.locator(".n-base-select-option").getByText("中文", { exact: true }).click()
      await panel.getByRole("button", { name: zh ? "保存偏好" : "Save preferences", exact: true }).click()
      await expect(panel.getByRole("status")).toContainText(zh ? "已保存" : "Saved")
      await page.reload()
      await expect(panel.getByTestId("memory-language")).toContainText("中文")
      await expect(panel.locator(".n-spin-body")).toHaveCount(0)
      await panel.scrollIntoViewIfNeeded()
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await panel.screenshot({ path: testInfo.outputPath(`memory-${locale}.png`) })
      const download = page.waitForEvent("download")
      await panel.getByRole("button", { name: zh ? "导出" : "Export", exact: true }).click()
      expect((await download).suggestedFilename()).toBe("aira-preferences.json")
      await panel.getByRole("button", { name: zh ? "清除全部" : "Clear all", exact: true }).click()
      await page.getByRole("button", { name: zh ? "确认" : "Confirm", exact: true }).last().click()
      await expect.poll(async () => (await (await request.get(`${api}/aira-memory`, { headers })).json()).preferences).toEqual({})
    }
    finally {
      const current = await (await request.get(`${api}/aira-memory`, { headers })).json()
      const changes = Object.fromEntries(["language", "detail", "format", "explanation"].map(key => [key, initial.preferences[key]?.value ?? null]))
      await request.patch(`${api}/aira-memory`, { headers, data: { changes, enabled: initial.enabled, expected_revision: current.revision, request_id: randomUUID() } })
    }
  })
}

test("explicit chat memory and temporary conversations use the real persistence boundary", async ({ page, request }) => {
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const signin = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await signin.json()).token }
  const initial = await (await request.get(`${api}/aira-memory`, { headers })).json()
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  try {
    await page.goto("/login")
    await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
    await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
    await page.getByTestId("login-submit").click()
    await expect(page).not.toHaveURL(/\/login/)
    await page.goto("/chat")
    const input = page.getByTestId("chat-input").locator("[contenteditable=true]")
    await input.fill("记住：用中文回答，简洁回答")
    await page.getByTestId("chat-submit").click()
    await expect(page.getByText("已记住你的表达偏好", { exact: false })).toBeVisible()
    await expect.poll(async () => (await (await request.get(`${api}/aira-memory`, { headers })).json()).preferences.detail?.value).toBe("concise")
    await page.getByTestId("aira-memory-menu").click()
    await page.getByText("本次对话不使用记忆", { exact: true }).click()
    await input.fill("记住：用英文回答")
    await page.getByTestId("chat-submit").click()
    await expect(page.getByText("这次对话不读取或保存个人记忆", { exact: false })).toBeVisible()
    await expect.poll(async () => (await (await request.get(`${api}/aira-memory`, { headers })).json()).preferences.language?.value).toBe("zh-CN")
    await page.reload()
    await expect(page.getByText("本次记忆已停用", { exact: true })).toBeVisible()
    await page.goto("/chat")
    await expect(page.getByText("本次记忆已停用", { exact: true })).toHaveCount(0)
    await page.getByTestId("aira-memory-menu").click()
    await page.getByText("本次对话不使用记忆", { exact: true }).click()
    await page.getByTestId("chat-input").locator("[contenteditable=true]").fill("记住：用英文回答")
    await page.getByTestId("chat-submit").click()
    await expect(page.getByText("这次对话不读取或保存个人记忆", { exact: false })).toBeVisible()
    await expect.poll(async () => (await (await request.get(`${api}/aira-memory`, { headers })).json()).preferences.language?.value).toBe("zh-CN")
  }
  finally {
    const current = await (await request.get(`${api}/aira-memory`, { headers })).json()
    await request.patch(`${api}/aira-memory`, { headers, data: { changes: Object.fromEntries(["language", "detail", "format", "explanation"].map(key => [key, initial.preferences[key]?.value ?? null])), enabled: initial.enabled, expected_revision: current.revision, request_id: randomUUID() } })
  }
})

test.describe("conversation memory actions", () => {
  test.use({ storageState: "tests/e2e/.auth/owner.json" })
  for (const width of [1440, 390]) {
    test(`remember, confirm, undo and pause across both chat surfaces at ${width}px`, async ({ page, request }, testInfo) => {
      const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
      const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
      const headers = { "Auth-Token": (await login.json()).token }
      const preferences = async () => (await (await request.get(`${api}/aira-memory`, { headers })).json())
      const initial = await preferences()
      await request.patch(`${api}/aira-memory`, { headers, data: { expected_revision: initial.revision, request_id: randomUUID(), clear: true, enabled: true } })
      await page.setViewportSize({ width, height: 844 })
      await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
      await mockAIEnabled(page.context(), () => true)
      try {
        await page.goto("/home", { waitUntil: "domcontentloaded" })
        await page.getByTestId("home-aira").click()
        const drawer = page.getByTestId("home-aira-panel")
        await expect(drawer.locator("header").getByTestId("aira-memory-menu")).toBeVisible()
        await expect(drawer.getByRole("checkbox")).toHaveCount(0)
        const send = async (text: string) => {
          await drawer.getByTestId("chat-input").locator("[contenteditable=true]").fill(text)
          const ready = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
          await drawer.getByTestId("chat-submit").click()
          expect((await ready).ok()).toBeTruthy()
          await expect(drawer.getByTestId("aira-memory-menu")).toBeEnabled()
        }
        await send("这次分步骤写")
        await send("以后都这样")
        const feedback = drawer.getByTestId("aira-memory-feedback")
        await expect(feedback).toContainText("已记住偏好")
        await expect.poll(async () => (await preferences()).preferences.format?.value).toBe("steps")
        await feedback.getByRole("button", { name: "撤销" }).click()
        await expect.poll(async () => (await preferences()).preferences).toEqual({})
        await send("请简短回答")
        await expect(feedback).toHaveCount(0)
        await send("请简短回答")
        await expect(feedback).toContainText("以后都用")
        expect((await preferences()).preferences).toEqual({})
        await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`drawer-${width}.png`) })
        const href = await drawer.getByTestId("open-aira-history").getAttribute("href")
        await page.goto(href!, { waitUntil: "domcontentloaded" })
        const fullFeedback = page.getByTestId("aira-memory-feedback")
        await fullFeedback.getByRole("button", { name: "记住", exact: true }).click()
        await expect.poll(async () => (await preferences()).preferences.detail?.value).toBe("concise")
        await page.locator("#page-aira-memory-actions").getByTestId("aira-memory-menu").click()
        await page.getByText("本次对话不使用记忆", { exact: true }).click()
        await page.reload({ waitUntil: "domcontentloaded" })
        await expect(page.locator("#page-aira-memory-actions")).toContainText("本次记忆已停用")
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
        await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`all-chats-${width}.png`) })
      }
      finally {
        const current = await preferences()
        const changes = Object.fromEntries(["language", "detail", "format", "explanation"].map(key => [key, initial.preferences[key]?.value ?? null]))
        await request.patch(`${api}/aira-memory`, { headers, data: { changes, enabled: initial.enabled, expected_revision: current.revision, request_id: randomUUID() } })
      }
    })
  }
})
