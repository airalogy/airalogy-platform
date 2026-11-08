import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("Project documents keep creation, templates and import together and distinguish empty searches", async ({ page }, testInfo) => {
  test.setTimeout(120000)
  const fixtures = await loadFixtures()
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  const login = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const uid = `documents_${randomUUID().slice(0, 8)}`
  const response = await page.request.post("/api/projects", { headers, data: { lab_id: fixtures.lab.id, uid, name: "Synthetic document workspace", type: 1 } })
  expect(response.ok(), await response.text()).toBeTruthy()
  const project = await response.json()
  const path = `/labs/${fixtures.lab.uid}/projects/${uid}/documents`
  await page.setViewportSize({ width: 942, height: 984 })
  await page.goto(path)
  const list = page.getByTestId("research-documents-list")
  await expect(list.getByTestId("document-list-empty")).toContainText("还没有文档")
  await expect(list.getByTestId("document-list-tools")).toBeHidden()
  await expect(list.getByTestId("new-research-document")).toHaveCount(1)
  await expect(page.getByTestId("project-research-workspace").getByRole("heading", { name: "文档", exact: true })).toHaveCount(0)
  await expect(list.getByTestId("document-audience")).toContainText("项目授权成员及实验室所有者、管理员可见")
  await expect(page.locator(".n-spin-body:visible")).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath("project-documents-empty.png"), fullPage: true })

  await list.getByTestId("document-list-more").click()
  await expect(page.locator(".n-dropdown-option").filter({ hasText: "文档模板" })).toBeVisible()
  await page.keyboard.press("ArrowDown")
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(new RegExp(`project_id=${project.id}`))
  await expect(page.getByRole("tab", { name: "文档模板", exact: true })).toHaveAttribute("aria-selected", "true")
  await page.goto(path)
  await expect(list.getByTestId("new-research-document")).toBeVisible()
  await list.getByTestId("document-list-more").click()
  const chooser = page.waitForEvent("filechooser")
  await page.locator(".n-dropdown-option").filter({ hasText: "导入归档包" }).click()
  expect(await (await chooser).element().getAttribute("accept")).toBe(".zip")
  await list.getByTestId("new-research-document").click()
  await expect(page.getByRole("dialog").getByTestId("document-audience")).toContainText("项目授权成员及实验室所有者、管理员可见")
  await page.getByTestId("new-document-title").locator("input").fill("合成示例：实验观察计划")
  await page.getByTestId("create-document-confirm").click()
  await expect(page.getByTestId("research-document-editor")).toBeVisible()
  await page.goto(path)
  await expect(list.getByTestId("research-document-link")).toHaveCount(1)
  await expect(list.getByTestId("document-list-tools")).toBeVisible()

  await list.getByRole("textbox", { name: "搜索", exact: true }).fill("missing-synthetic-title")
  await list.getByRole("button", { name: "搜索", exact: true }).click()
  await expect(list.getByTestId("document-list-empty")).toContainText("没有符合条件的文档")
  await expect(list.getByTestId("document-list-tools")).toBeVisible()
  await list.getByRole("button", { name: "清除搜索和筛选", exact: true }).click()
  await expect(list.getByTestId("research-document-link")).toHaveCount(1)
  await list.getByTestId("document-filters-toggle").click()
  await list.getByTestId("document-date-to").fill("2000-01-01")
  await list.getByTestId("document-date-to").press("Tab")
  await expect(list.getByTestId("document-list-empty")).toContainText("没有符合条件的文档")
  await list.getByRole("button", { name: "清除搜索和筛选", exact: true }).click()
  await expect(list.getByTestId("research-document-link")).toHaveCount(1)
  await expect(list.getByTestId("document-date-to")).toHaveValue("")
  await list.getByTestId("document-filters-toggle").click()
  await list.getByTestId("document-order").selectOption("recorded")
  await expect(list.getByTestId("document-day-heading")).toHaveCount(1)
  for (const width of [942, 390, 1440]) {
    await page.setViewportSize({ width, height: 984 })
    await expect(list.getByTestId("new-research-document")).toBeVisible()
    for (const control of [list.locator(".document-list-search .n-input"), list.getByTestId("document-order"), list.getByTestId("document-filters-toggle")]) {
      expect((await control.boundingBox())!.height).toBe(40)
    }
    expect(await list.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBeTruthy()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await expect(page.locator(".n-spin-body:visible")).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath(`project-documents-${width}.png`), fullPage: true })
  }
})

test("read-only empty document spaces do not suggest unavailable creation or import", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  // Exercise the list's server capability response without changing account permissions.
  await page.route(/\/api\/research-documents\?/, route => route.fulfill({ json: { items: [], total_count: 0, can_write: false } }))
  await page.goto("/research-documents")
  await expect(page.getByTestId("document-list-empty")).toContainText("Documents in this space will appear here.")
  await expect(page.getByTestId("new-research-document")).toHaveCount(0)
  await page.getByTestId("document-list-more").click()
  await expect(page.locator(".n-dropdown-option").filter({ hasText: "Document templates" })).toBeVisible()
  await expect(page.locator(".n-dropdown-option").filter({ hasText: "Import archive" })).toHaveCount(0)
})
