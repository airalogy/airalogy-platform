import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

for (const screen of [{ width: 1280, height: 900, touch: false }, { width: 702, height: 985, touch: false }, { width: 390, height: 844, touch: true }]) {
  test.describe(`saved Record at ${screen.width}px`, () => {
    test.use({ viewport: { width: screen.width, height: screen.height }, hasTouch: screen.touch })

    test("scrolls from the record heading to the last paragraph and back", async ({ page }) => {
      const { lab, project, schema_governance: record } = await loadFixtures()
      const first = "Alignment review"
      const last = "End of saved report"
      await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
      await page.route("**/api/protocols/by_uid?**", async (route) => {
        const response = await route.fetch()
        const body = await response.json()
        const protocol = body.data || body
        protocol.aimd = ["# Frame inspection", `{{step|review_frame, title=\"${first}\"}}`, ...Array.from({ length: 60 }, (_, i) => `Inspection note ${i + 1}`), last].join("\n\n")
        await route.fulfill({ response, json: body })
      })
      await page.goto(`/labs/${lab.uid}/projects/${project.uid}/protocols/${record.protocol_uid}/v${record.source_version}/record/${record.record_id}/v${record.record_version}`)
      const content = page.getByTestId("record-main-content")
      const heading = content.getByText(first, { exact: true })
      const ending = content.getByText(last, { exact: true })
      await expect(heading).toBeInViewport()
      await expect(ending).not.toBeInViewport()
      const step = content.getByRole("heading", { name: /Alignment review/ })
      await expect(step).toHaveAttribute("title", "review_frame")
      await expect(step).toHaveText("Step 1 : Alignment review")
      const stepRoot = step.locator("..")
      await expect(stepRoot).toHaveCSS("border-top-width", "0px")
      await expect(stepRoot).toHaveCSS("background-color", "rgba(0, 0, 0, 0)")
      if (screen.width === 390) {
        await page.getByTestId("record-open-fields").tap()
        const drawer = page.getByTestId("record-fields-drawer")
        await expect(drawer).toBeVisible()
        await drawer.locator(".n-drawer-header__close").tap()
        await expect(drawer).toBeHidden()
      }
      const touch = screen.touch ? await page.context().newCDPSession(page) : undefined
      async function scroll(down: boolean) {
        const x = Math.floor(screen.width / 2)
        if (touch) {
          const start = screen.height * (down ? 0.8 : 0.35)
          const distance = screen.height * (down ? -0.45 : 0.45)
          await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: start }] })
          for (let i = 1; i <= 6; i++) {
            await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: start + distance * i / 6 }] })
          }
          await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })
        }
        else {
          await page.mouse.move(x, Math.floor(screen.height * 0.7))
          await page.mouse.wheel(0, down ? 3000 : -3000)
        }
      }
      for (const down of [true, false]) {
        await expect(async () => {
          await scroll(down)
          await expect(down ? ending : heading).toBeInViewport({ timeout: 500 })
        }).toPass({ timeout: 8000 })
      }
      await expect.poll(() => page.locator("main").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    })
  })
}
