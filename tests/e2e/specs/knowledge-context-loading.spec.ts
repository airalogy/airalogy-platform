import { expect, test } from "@playwright/test"

const project = "/labs/dev_lab/projects/quickstart"

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto(`${project}/overview`)
  await expect(page.getByTestId("research-activity")).toBeVisible()
})

test("project knowledge never paints a personal title or opens personal actions while context is pending", async ({ page }, testInfo) => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  const requests: string[] = []
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/knowledge/"))
      requests.push(request.url())
  })
  await page.route("**/api/projects/by_uid?*", async (route) => {
    const response = await route.fetch()
    await gate
    await route.fulfill({ response })
  })
  await page.evaluate(() => {
    const state = window as typeof window & { knowledgeTitles?: string[] }
    state.knowledgeTitles = []
    new MutationObserver(() => {
      const title = document.querySelector(".knowledge-page h1")?.textContent?.trim()
      if (title && state.knowledgeTitles?.at(-1) !== title)
        state.knowledgeTitles?.push(title)
    }).observe(document.body, { subtree: true, childList: true, characterData: true })
  })
  try {
    await page.locator(".n-tabs-tab").filter({ hasText: /^知识$/ }).click()
    const knowledge = page.locator(".knowledge-page")
    await expect(knowledge.getByRole("heading", { level: 1 })).toHaveText("项目知识")
    await expect(knowledge).not.toContainText("我的知识")
    await expect(knowledge.getByRole("button", { name: "新建知识条目", exact: true })).toBeDisabled()
    await expect(knowledge.getByRole("button", { name: "导入文献", exact: true })).toBeDisabled()
    expect(requests).toEqual([])
    await page.screenshot({ path: testInfo.outputPath("knowledge-context-loading.png"), fullPage: true })
    release()
    await expect(knowledge.getByRole("button", { name: "新建知识条目", exact: true })).toBeEnabled()
    await expect(knowledge.locator(".n-spin-body")).toHaveCount(0)
    expect(requests.length).toBeGreaterThan(0)
    expect(requests.every(url => new URL(url).searchParams.get("scope_type") === "project")).toBeTruthy()
    const titles = await page.evaluate(() => (window as typeof window & { knowledgeTitles: string[] }).knowledgeTitles)
    expect(titles.length).toBeGreaterThan(0)
    expect(titles.every(title => title === "项目知识")).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath("knowledge-desktop.png"), fullPage: true })
    await page.setViewportSize({ width: 390, height: 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath("knowledge-mobile.png"), fullPage: true })
  }
  finally { release() }
})

test("a failed project context can be retried without requesting or creating personal knowledge", async ({ page }) => {
  let fail = true
  const scopes: string[] = []
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith("/api/knowledge/"))
      scopes.push(url.searchParams.get("scope_type") || "")
  })
  await page.route("**/api/projects/by_uid?*", route => fail
    ? route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic context failure" }) })
    : route.continue())
  await page.locator(".n-tabs-tab").filter({ hasText: /^知识$/ }).click()
  const knowledge = page.locator(".knowledge-page")
  await expect(knowledge).toContainText("知识加载失败")
  await expect(knowledge.getByRole("heading", { level: 1 })).toHaveText("项目知识")
  await expect(knowledge.getByRole("button", { name: "新建知识条目", exact: true })).toBeDisabled()
  expect(scopes).toEqual([])
  fail = false
  await knowledge.getByRole("button", { name: "重试", exact: true }).click()
  await expect(knowledge.getByRole("button", { name: "新建知识条目", exact: true })).toBeEnabled()
  await expect(knowledge.locator(".n-spin-body")).toHaveCount(0)
  expect(scopes.length).toBeGreaterThan(0)
  expect(scopes.every(scope => scope === "project")).toBeTruthy()
})
