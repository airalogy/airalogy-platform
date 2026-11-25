import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("a Record report fits the window and keeps each step heading once", async ({ page }, testInfo) => {
  const fixtures = await loadFixtures()
  const stepId = `inspect_${"optical_frame_".repeat(7)}alignment`
  const untitledId = `verify_${"alignment_".repeat(12)}result`
  const end = "End of fixture report"
  const aimd = [
    "# 检查记录",
    `{{step|${stepId}, title="外观核对"}}`,
    "{{step|align, 2, title='对齐标记'}}",
    `{{step|${untitledId}}}`,
    "{{check|verified}}",
    ...Array.from({ length: 32 }, (_, index) => `检查点 ${index + 1}。`),
    end,
  ].join("\n\n")
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.route("**/api/protocols/by_uid?**", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    const protocol = body.data || body
    protocol.aimd = aimd
    await route.fulfill({ response, json: body })
  })
  await page.route("**/api/protocols/*/records?**", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    // Older Records without a version open in the list's report drawer.
    for (const record of (body.data || body).records) {
      delete record.metadata.protocol_version
      record.data.check = { verified: { checked: true } }
    }
    await route.fulfill({ response, json: body })
  })
  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${fixtures.schema_governance.protocol_uid}/records`)
  const open = page.locator(".aimd-record-table-view__record-link").first()
  await open.click()
  const drawer = page.locator(".record-report-drawer")
  const pane = drawer.locator(".n-drawer-body-content-wrapper")
  const close = drawer.locator(".n-drawer-header__close")
  await expect(drawer.locator(`#step-${stepId} [role="heading"]`)).toHaveAttribute("title", stepId)
  await expect(drawer.getByRole("heading", { name: /外观核对|对齐标记/ })).toHaveText(["1外观核对", "1.1对齐标记"])
  await expect(drawer.locator("#step-align [role=heading]")).toHaveAccessibleName(/步骤 1\.1.*对齐标记/)
  await expect(drawer.locator(`#step-${untitledId} [role="heading"]`)).toContainText(untitledId)
  await expect(drawer.locator(".aimd-record-check input")).toBeChecked()
  for (const viewport of [{ width: 1280, height: 900 }, { width: 619, height: 985 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await expect(close).toBeInViewport()
    await expect.poll(() => pane.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    const bounds = (await drawer.boundingBox())!
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    if (viewport.width > 640)
      expect(bounds.x).toBeGreaterThan(0)
    else
      expect(bounds.width).toBeCloseTo(viewport.width, 0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width + 1)
    await drawer.screenshot({ path: testInfo.outputPath(`report-${viewport.width}.png`) })
    await pane.getByText(end).scrollIntoViewIfNeeded()
    await expect(pane.getByText(end)).toBeInViewport()
    await pane.evaluate(el => el.scrollTo(0, 0))
  }
  await close.click()
  await expect(drawer).toHaveCount(0)
})
