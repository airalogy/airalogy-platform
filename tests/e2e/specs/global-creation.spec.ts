import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
})

test("global New separates creation from navigation and opens private document templates at every width", async ({ page }, testInfo) => {
  for (const width of [390, 820, 1440]) {
    await page.setViewportSize({ width, height: 984 })
    await page.goto("/home")
    const trigger = page.getByTestId("global-create-trigger")
    await trigger.focus()
    await page.keyboard.press("Enter")
    await expect(trigger).toHaveAttribute("aria-expanded", "true")
    const item = page.getByRole("button", { name: "New document", exact: true })
    await expect(item).toBeVisible()
    await expect(page.getByRole("button", { name: "New protocol", exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: "New record", exact: true })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath(`global-new-${width}.png`), fullPage: false, animations: "disabled" })
    if (width === 820) {
      await page.keyboard.press("Escape")
      await expect(trigger).toHaveAttribute("aria-expanded", "false")
      await trigger.press("Enter")
      await item.focus()
      await item.press("Enter")
    }
    else { await item.click() }
    const dialog = page.getByTestId("new-document-dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog.getByTestId("document-audience")).toContainText("Only you")
    await expect(dialog.getByTestId("document-common-templates")).toBeVisible()
    await expect(dialog.getByTestId("document-browse-templates")).toBeVisible()
    await expect(page.getByTestId("global-create-trigger")).toHaveAttribute("aria-expanded", "false")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page).not.toHaveURL(/create=/)
    await page.reload()
    await expect(page.getByTestId("research-documents-list")).toBeVisible()
    await expect(dialog).toHaveCount(0)
  }
  await page.goto("/home")
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "New document", exact: true }).click()
  await page.getByTestId("new-document-title").locator("input").fill(`Synthetic global private ${randomUUID()}`)
  const response = page.waitForResponse(r => r.url().endsWith("/api/research-documents") && r.request().method() === "POST")
  await page.getByTestId("create-document-confirm").click()
  const created = await response
  expect(created.ok(), await created.text()).toBeTruthy()
  expect((await created.json()).scope_type).toBe("personal")
  await expect(page.getByTestId("research-document-editor")).toBeVisible()
})

test("global document creation inherits Project, document and Lab scope without changing the audience", async ({ page }) => {
  const f = await loadFixtures()
  await page.goto(`/labs/${f.lab.uid}/projects/${f.project.uid}/protocols`)
  await expect(page.getByRole("heading", { name: "Quickstart Protocol Testing", exact: true })).toBeVisible()
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "New document", exact: true }).click()
  const dialog = page.getByTestId("new-document-dialog")
  await expect(dialog.getByTestId("document-audience")).toContainText("Quickstart Protocol Testing")
  await expect(dialog.getByTestId("document-audience")).toContainText("Project")
  await dialog.getByTestId("new-document-title").locator("input").fill(`Synthetic project shortcut ${randomUUID()}`)
  const response = page.waitForResponse(r => r.url().endsWith("/api/research-documents") && r.request().method() === "POST")
  await dialog.getByTestId("create-document-confirm").click()
  const created = await response
  expect(created.ok(), await created.text()).toBeTruthy()
  const data = await created.json()
  expect(data.scope_type).toBe("project")
  expect(data.project_id).toBe(f.project.id)
  await expect(page.getByTestId("research-document-editor")).toBeVisible()
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "New document", exact: true }).click()
  await expect(dialog.getByTestId("document-audience")).toContainText("Quickstart Protocol Testing")
  await expect(page).toHaveURL(new RegExp(`project_id=${f.project.id}`))
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  await page.goto(`/labs/${f.lab.uid}/knowledge`)
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "New document", exact: true }).click()
  await expect(dialog.getByTestId("document-audience")).toContainText("Dev Demo Lab")
  await expect(page).toHaveURL(new RegExp(`lab_id=${f.lab.id}`))
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
})

test("global document shortcut honors server write restrictions and never falls back to another scope", async ({ page }) => {
  const f = await loadFixtures()
  let writes = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/research-documents") && request.method() === "POST")
      writes++
  })
  // Exercise the API capability contract without changing the test user's membership.
  await page.route(/\/api\/research-documents\?/, route => route.fulfill({ json: { items: [], total_count: 0, can_write: false } }))
  await page.goto(`/labs/${f.lab.uid}/projects/${f.project.uid}/protocols`)
  await page.getByTestId("global-create-trigger").click()
  await page.getByRole("button", { name: "New document", exact: true }).click()
  await expect(page.getByTestId("research-documents-list").getByRole("alert")).toContainText("cannot create documents in this space")
  await expect(page).toHaveURL(new RegExp(`/projects/${f.project.uid}/documents`))
  await expect(page.getByTestId("new-document-dialog")).toHaveCount(0)
  expect(writes).toBe(0)
})
