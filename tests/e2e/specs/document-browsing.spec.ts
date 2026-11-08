import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"

test.use({ timezoneId: "Asia/Shanghai" })

test("date browsing reads across pages, retains context, and uses one date shared with editing", async ({ page }) => {
  test.setTimeout(120000)
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  const login = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  const prefix = `Synthetic browser ${randomUUID().slice(0, 8)}`
  for (let index = 0; index < 22; index++) {
    const response = await page.request.post("/api/research-documents", { headers, data: {
      id: randomUUID(),
      scope_type: "personal",
      title: `${prefix} ${index}`,
      body: "## Synthetic observations\n\n{{var|reading: int}}",
      record_data: { var: { reading: index } },
      occurred_at: `2026-11-07T12:${String(index).padStart(2, "0")}:00+08:00`,
    } })
    expect(response.ok(), await response.text()).toBeTruthy()
  }
  await page.goto(`/research-documents?${new URLSearchParams({ q: prefix, order: "recorded", from: "2026-11-07", to: "2026-11-07" })}`)
  await expect(page.getByTestId("document-audience")).toContainText("Only you can view")
  await expect(page.getByTestId("research-document-link")).toHaveCount(20)
  await expect(page.getByTestId("document-day-heading")).toHaveText("2026-11-07")
  await page.getByTestId("research-document-link").last().click()
  await expect(page.getByTestId("document-reader-title")).toHaveText(`${prefix} 2`)
  await expect(page.getByTestId("document-reader-title")).toBeInViewport()
  await expect(page.getByTestId("document-reader").locator("[contenteditable=true]")).toHaveCount(0)
  await page.getByTestId("document-next").click()
  await expect(page.getByTestId("document-reader-title")).toHaveText(`${prefix} 1`)
  await expect(page).toHaveURL(/page=2/)
  await page.getByTestId("document-next").click()
  await expect(page.getByTestId("document-reader-title")).toHaveText(`${prefix} 0`)
  await expect(page.getByTestId("document-next")).toBeDisabled()
  await page.getByTestId("document-previous").click()
  await page.getByTestId("document-previous").click()
  await expect(page.getByTestId("document-reader-title")).toHaveText(`${prefix} 2`)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  await expect(page.getByTestId("research-document-link").first()).toBeHidden()
  await page.getByTestId("document-open-editor").click()
  await expect(page.getByTestId("document-recorded-date")).toHaveValue("2026-11-07")
  await page.getByTestId("document-recorded-date").fill("2026-10-31")
  await page.getByTestId("document-recorded-date").press("Tab")
  await expect(page.getByTestId("document-save-state")).toHaveText("Saved")
  await page.getByTestId("document-back").click()
  await expect(page.getByText("This document is no longer in the current results.", { exact: false })).toBeVisible()
  await page.getByTestId("document-filters-toggle").click()
  await expect(page.getByTestId("document-date-from")).toHaveValue("2026-11-07")
  await page.getByRole("button", { name: "Back to list", exact: true }).click()
  await page.getByText("Browse calendar", { exact: true }).click()
  await expect(page.getByRole("button", { name: "2026-11-07, 21 documents", exact: true })).toBeVisible()
  await page.getByTestId("document-calendar-month").fill("2026-10")
  await page.getByRole("button", { name: "2026-10-31, 1 documents", exact: true }).click()
  await expect(page.getByTestId("research-document-link")).toHaveCount(1)
  await page.reload()
  await page.getByTestId("document-filters-toggle").click()
  await expect(page.getByTestId("document-date-from")).toHaveValue("2026-10-31")
  await expect(page.getByTestId("research-document-link")).toContainText(`${prefix} 2`)
})

test("new historical Project documents disclose their draft audience before creation", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto("/research-documents")
  const scope = page.getByTestId("documents-scope")
  const project = await scope.locator("option").filter({ hasText: "Project ·" }).first().getAttribute("value")
  await scope.selectOption(project!)
  await expect(page.getByTestId("document-audience")).toContainText("Lab Owners/Managers")
  await page.getByTestId("new-research-document").click()
  await expect(page.getByRole("dialog").getByTestId("document-audience")).toContainText("Working drafts share this audience")
  await page.getByTestId("new-document-options").locator("summary").click()
  await page.getByTestId("new-document-date").fill("2025-01-01")
  await page.getByTestId("new-document-title").locator("input").fill("Synthetic historical Project note")
  await page.getByTestId("create-document-confirm").click()
  await expect(page.getByTestId("document-recorded-date")).toHaveValue("2025-01-01")
  await expect(page.getByTestId("document-audience")).toContainText("Lab Owners/Managers")
  await page.reload()
  await expect(page.getByTestId("document-recorded-date")).toHaveValue("2025-01-01")
})
