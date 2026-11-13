import type { Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { selectVisibleOption } from "./fixtures"

const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8"))
const en = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8"))
const projectPath = "/labs/dev_lab/projects/quickstart/protocols"
const folderName = "Synthetic long folder / 合成方案资料与仪器测试结果归档"

test.use({ storageState: { cookies: [], origins: [] } })

async function signIn(page: Page, locale = "zh-CN") {
  await page.addInitScript(locale => localStorage.setItem("lang", JSON.stringify({ data: locale, expire: null })), locale)
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
}

async function folders(page: Page, empty = false) {
  await page.route("**/api/projects/*/protocol_folders?**", route => route.fulfill({ json: {
    folders: empty ? [] : [{ id: 990001, name: folderName, protocols_count: 0 }],
    total_count: empty ? 0 : 1,
  } }))
}

function waitForQuery(page: Page, matches: (params: URLSearchParams) => boolean) {
  return page.waitForRequest((request) => {
    const url = new URL(request.url())
    return request.method() === "GET" && url.pathname === "/api/protocols" && matches(url.searchParams)
  })
}

for (const [locale, labels] of [["zh-CN", zh], ["en-US", en]] as const) {
  test(`protocol toolbar is readable at narrow and wide widths (${locale})`, async ({ page }, testInfo) => {
    await signIn(page, locale)
    await folders(page)
    await page.goto(projectPath)
    const toolbar = page.getByTestId("project-protocol-toolbar")
    await expect(toolbar).toBeVisible()
    await expect(page.locator(".protocol-list-item").first()).toBeVisible()
    await expect(page.getByTestId("protocol-search-field")).toContainText(labels.page.protocol.protocolName)
    await expect(toolbar).not.toContainText(labels.page.project.protocolsFilter.name)
    for (const width of [320, 390, 755, 1280, 1440]) {
      await page.setViewportSize({ width, height: 989 })
      const input = await page.getByTestId("protocol-search-input").boundingBox()
      const toolbarBox = await toolbar.boundingBox()
      // Reserve most of the row for typing; font metrics differ slightly in compiled assets.
      expect(input!.width).toBeGreaterThan(toolbarBox!.width * 0.6)
      for (const id of ["protocol-search-input", "protocol-folder-filter", "protocol-search-field", "protocol-sort", "protocol-manage-folders"]) {
        const box = await page.getByTestId(id).boundingBox()
        expect(box!.x).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width).toBeLessThanOrEqual(width)
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      if ([390, 755, 1440].includes(width))
        await page.screenshot({ path: testInfo.outputPath(`protocol-toolbar-${locale}-${width}.png`), animations: "disabled" })
    }
    await page.setViewportSize({ width: 390, height: 900 })
    await page.getByTestId("protocol-manage-folders").click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toContainText(folderName)
    const box = await dialog.boundingBox()
    expect(box!.x).toBeGreaterThanOrEqual(15)
    expect(box!.x + box!.width).toBeLessThanOrEqual(375)
  })
}

test("search, search field, sorting and folder filters refresh the list and recover from no results", async ({ page }) => {
  await signIn(page)
  await folders(page)
  await page.route("**/api/protocols?**", async (route) => {
    const params = new URL(route.request().url()).searchParams
    if (params.get("folder_id"))
      await route.fulfill({ json: { protocols: [], total_count: 0 } })
    else
      await route.continue()
  })
  const initial = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols")
  await page.goto(projectPath)
  const sample = (await (await initial).json()).protocols[0]
  await expect(page.locator(".protocol-list-item").first()).toBeVisible()
  const toolbar = page.getByTestId("project-protocol-toolbar")
  await page.getByTestId("protocol-search-input").locator("input").fill("Synthetic unmatched")
  const response = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && new URL(r.url()).searchParams.get("search_str") === "Synthetic unmatched")
  const search = waitForQuery(page, p => p.get("search_str") === "Synthetic unmatched" && p.get("search_by") === "name")
  await toolbar.getByRole("button", { name: zh.common.search, exact: true }).click()
  await search
  expect((await response).ok()).toBeTruthy()
  await expect(page.getByText(/未找到.*Synthetic unmatched.*协议/)).toBeVisible()
  await expect(page.getByTestId("protocol-first-create")).toHaveCount(0)
  await page.getByTestId("protocol-search-field").click()
  const field = waitForQuery(page, p => p.get("search_by") === "uid")
  const idResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && new URL(r.url()).searchParams.get("search_by") === "uid")
  await selectVisibleOption(page, zh.page.protocol.protocolId)
  await field
  expect((await idResponse).ok()).toBeTruthy()
  await page.getByTestId("protocol-sort").click()
  const sort = waitForQuery(page, p => p.get("sorted_by") === "stars_count")
  const sortResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && new URL(r.url()).searchParams.get("sorted_by") === "stars_count")
  await selectVisibleOption(page, zh.page.project.protocolsSort.stars)
  await sort
  expect((await sortResponse).ok()).toBeTruthy()
  const clear = waitForQuery(page, p => !p.has("search_str") && !p.has("folder_id"))
  await toolbar.getByRole("button", { name: zh.page.project.protocolsEmpty.clearFilters, exact: true }).click()
  await clear
  await expect(page.locator(".protocol-list-item").first()).toBeVisible()
  await page.getByTestId("protocol-folder-filter").click()
  const folder = waitForQuery(page, p => p.get("folder_id") === "990001")
  await selectVisibleOption(page, folderName)
  await folder
  await expect(page.getByText(zh.page.project.protocolsEmpty.folderNoResult, { exact: true })).toBeVisible()
  await expect(page.getByTestId("protocol-first-create")).toHaveCount(0)
  await toolbar.getByRole("button", { name: zh.page.project.protocolsEmpty.clearFilters, exact: true }).click()
  await expect(page.locator(".protocol-list-item").first()).toBeVisible()
  await page.getByTestId("protocol-search-input").locator("input").fill(sample.uid)
  const byId = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && new URL(r.url()).searchParams.get("search_str") === sample.uid)
  await toolbar.getByRole("button", { name: zh.common.search, exact: true }).click()
  const matched = await byId
  expect(matched.ok()).toBeTruthy()
  expect((await matched.json()).protocols.some((item: { uid: string }) => item.uid === sample.uid)).toBeTruthy()
  await expect(page.locator(".protocol-list-item").filter({ hasText: sample.name })).toBeVisible()
})

test("an empty project shows creation rather than irrelevant filters; a direct search can still be cleared", async ({ page }, testInfo) => {
  await signIn(page)
  await folders(page, true)
  await page.route("**/api/protocols?**", route => route.fulfill({ json: { protocols: [], total_count: 0 } }))
  await page.setViewportSize({ width: 755, height: 989 })
  await page.goto(projectPath)
  await expect(page.getByTestId("protocol-first-create")).toBeVisible()
  await expect(page.getByTestId("project-protocol-toolbar")).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("protocol-empty-755.png"), animations: "disabled" })
  const query = waitForQuery(page, p => p.get("search_str") === "Synthetic unmatched")
  await page.goto(`${projectPath}?q=Synthetic%20unmatched`)
  await query
  await expect(page.getByTestId("protocol-search-input").locator("input")).toHaveValue("Synthetic unmatched")
  await expect(page.getByTestId("protocol-first-create")).toHaveCount(0)
  await page.getByTestId("project-protocol-toolbar").getByRole("button", { name: zh.page.project.protocolsEmpty.clearFilters, exact: true }).click()
  await expect(page.getByTestId("protocol-first-create")).toBeVisible()
  await expect(page.getByTestId("project-protocol-toolbar")).toHaveCount(0)
})
