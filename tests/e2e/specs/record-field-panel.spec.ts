import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { type APIRequestContext, expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

async function publishFieldProtocol(request: APIRequestContext, content: string[]) {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const uid = `panel_${randomUUID().replaceAll("-", "")}`
  const files = {
    "protocol.toml": `[airalogy_protocol]\nid="${uid}"\nname="Synthetic field panel"\nversion="0.1.0"`,
    "protocol.aimd": content.join("\n\n"),
  }
  const published = await request.post(`${api}/protocols`, {
    headers,
    multipart: { project_id: fixtures.project.id, file: {
      name: "panel.zip",
      mimeType: "application/zip",
      buffer: Buffer.from(zipSync(Object.fromEntries(Object.entries(files).map(([name, content]) => [name, strToU8(content)])))),
    } },
  })
  expect(published.ok(), await published.text()).toBeTruthy()
  return { api, headers, protocolId: (await published.json()).data.id, protocolUrl: `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${uid}` }
}

for (const width of [1440, 663, 390]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width === 390, isMobile: width === 390 })

    test("shared field panel for entry, saved photos and navigation", async ({ page, request }, testInfo) => {
      test.setTimeout(150_000)
      page.setDefaultTimeout(30_000)
      const { api, headers, protocolId, protocolUrl } = await publishFieldProtocol(request, [
        '{{var|short_label: str, title="标签编号", examples=["EX-100"]}}',
        '{{var|location: str, title="位置", placeholder="例如 A-01"}}',
        '{{var|photo: FileIdJPG | None = None, title="标签照片"}}',
        '{{step|prepare, title="准备标签", check=True}}',
        '{{check|review, title="核对标签"}}',
        '{{check|legacy}}',
      ])
      await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
      const entryUrl = `${protocolUrl}/add`
      const fields = page.getByRole("radiogroup", { name: "字段显示" })
      await page.goto(entryUrl, { waitUntil: "domcontentloaded" })
      if (width < 768)
        await page.getByTestId("record-open-fields").click()
      const sidebar = page.locator(".record-fields-form .aimd-fields-list")
      const body = page.locator(".record-inline-content.aimd-protocol-recorder")
      await expect(sidebar).toHaveAttribute("data-field-display", "detailed")
      await expect(body).not.toHaveClass(/aimd-protocol-recorder--compact/)
      await expect(sidebar.locator('[data-panel-key="var:short_label"] .aimd-panel-label code')).toHaveText("short_label")
      if (width < 768)
        await page.getByTestId("record-fields-drawer").locator(".n-drawer-header__close").click()
      await fields.getByText("简洁", { exact: true }).click()
      await expect(body).toHaveClass(/aimd-protocol-recorder--compact/)
      await page.reload()
      if (width < 768)
        await page.getByTestId("record-open-fields").click()
      await expect(sidebar).toHaveAttribute("data-field-display", "compact")
      const compactLabel = sidebar.locator('[data-panel-key="var:short_label"]')
      await expect(compactLabel.locator("code")).not.toBeVisible()
      await page.screenshot({ path: testInfo.outputPath("compact.png") })
      await compactLabel.locator("summary").click()
      await expect(compactLabel.locator("code")).toBeVisible()
      const definition = compactLabel.locator("dl")
      await expect(definition).toContainText("示例数据")
      await expect(definition.getByText("EX-100", { exact: true })).toBeVisible()
      await expect(definition.getByText("str", { exact: true })).toBeVisible()
      for (const value of await sidebar.locator(':is([data-panel-key="var:short_label"], [data-panel-key="var:location"]) .aimd-panel-value').all()) {
        expect(await value.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
      }
      await page.screenshot({ path: testInfo.outputPath("expanded-definition.png") })
      if (width < 768)
        await page.getByTestId("record-fields-drawer").locator(".n-drawer-header__close").click()
      await fields.getByText("详细", { exact: true }).click()
      if (width < 768)
        await page.getByTestId("record-open-fields").click()
      const field = page.locator("#form-research_variable-short_label")
      const text = field.locator("textarea, input").first()
      await expect(text).toBeVisible()
      await expect(text).not.toHaveAttribute("placeholder", "标签编号")
      await expect(page.getByPlaceholder("例如 A-01").first()).toBeVisible()
      const inputBox = (await text.boundingBox())!
      const fieldBox = (await field.boundingBox())!
      expect(inputBox.width).toBeGreaterThan(fieldBox.width * 0.87)
      const panel = field.locator("xpath=ancestor::div[contains(@class,'record-fields-form')][1]")
      const groups = await panel.locator(".aimd-panel-group > summary").allTextContents()
      expect(groups).toEqual(["变量", "步骤", "检查点"])
      await expect(panel.locator('[data-navigate-field="step:prepare"]')).toBeVisible()
      await expect(panel.locator('[data-navigate-field="check:legacy"]')).toBeVisible()
      await text.fill("LABEL-01")
      await text.press("Tab")
      const photo = panel.locator('[data-panel-field="var:photo"]')
      await expect(photo).toContainText("选填")
      await expect(body.locator('[data-recorder-field="photo"] .aimd-field__label')).toContainText("选填")
      await expect(photo.locator(".aimd-field__name")).toHaveCount(0)
      const trigger = photo.getByRole("button", { name: /上传照片.*JPG/i })
      await expect(trigger).toBeVisible()
      // The empty required field reports an error on blur. The first tap must
      // still reach the upload button even if the validation message moves it.
      await panel.getByPlaceholder("例如 A-01").focus()
      const jpeg = await page.evaluate(() => {
        const canvas = document.createElement("canvas")
        canvas.width = 192
        canvas.height = 64
        const ctx = canvas.getContext("2d")!
        ctx.fillStyle = "#eaf3fa"
        ctx.fillRect(0, 0, 192, 64)
        ctx.fillStyle = "#25364a"
        ctx.font = "20px sans-serif"
        ctx.fillText("LABEL-01", 16, 39)
        return canvas.toDataURL("image/jpeg").split(",")[1]
      })
      const [chooser] = await Promise.all([page.waitForEvent("filechooser"), width === 390 ? trigger.tap() : trigger.click()])
      const uploaded = page.waitForResponse(r => r.url().endsWith("/airalogy_files") && r.request().method() === "POST")
      await chooser.setFiles({ name: "label.jpg", mimeType: "image/jpeg", buffer: Buffer.from(jpeg, "base64") })
      const response = await uploaded
      expect(response.ok(), await response.text()).toBeTruthy()
      const photoId = (await response.json()).airalogy_file_id
      expect(photoId).toMatch(/^airalogy\.id\.file\..+\.jpg$/i)
      await expect.poll(() => photo.locator("img").evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(192)
      await page.screenshot({ path: testInfo.outputPath("recording.png") })
      await photo.getByRole("button", { name: /清除|移除|清空|删除/ }).click()
      await expect(trigger).toBeVisible()
      await panel.locator('[data-navigate-field="check:review"]').click()
      await expect(page.locator('[data-rec-focus-key="check:review:checked"]')).toBeFocused()
      await expect(page.locator('.record-inline-content [data-rec-focus-key="var:short_label"]')).toHaveValue("LABEL-01")
      await fields.getByText("简洁", { exact: true }).click()
      const recorded = await request.post(`${api}/protocols/${protocolId}/records`, {
        headers,
        data: {
          var: { short_label: "LABEL-01", location: "A-01", photo: photoId },
          step: { prepare: { checked: true, annotation: "" } },
          check: { review: { checked: false, annotation: "复核备注" } },
          report: "",
        },
      })
      expect(recorded.ok(), await recorded.text()).toBeTruthy()
      const recordId = (await recorded.json()).id
      const reportUrl = `${protocolUrl}/v0.1.0/record/${recordId}/v1`
      await page.goto(reportUrl)
      const report = page.locator(".record-inline-content .rendered-aimd-document")
      const style = page.getByRole("radiogroup", { name: "报告样式" })
      await expect(style.getByRole("radio", { name: "高亮" })).toBeChecked()
      await expect(report).toHaveAttribute("data-record-presentation", "detailed")
      if (width < 768)
        await expect(page.getByTestId("record-fields-drawer")).toBeHidden()
      await page.screenshot({ path: testInfo.outputPath("report-highlighted.png"), animations: "disabled" })
      if (width < 768)
        await page.getByTestId("record-open-fields").click()
      const saved = page.locator(".record-fields-form .aimd-fields-list")
      await expect(saved.locator(".aimd-panel-group > summary")).toHaveText(groups)
      const variableGroup = saved.locator('[data-panel-group="var"]')
      await variableGroup.locator(":scope > summary").click()
      await expect(variableGroup).not.toHaveAttribute("open")
      await variableGroup.locator(":scope > summary").click()
      const label = saved.locator('[data-panel-key="var:short_label"]')
      await expect(label.locator(".aimd-panel-value")).toHaveText("LABEL-01")
      await expect(label.locator(".aimd-panel-label code")).toBeVisible()
      await label.locator("summary").click()
      await expect(label.locator("dl")).toContainText("示例数据")
      await expect(label.locator("dl")).toContainText("EX-100")
      await expect(label.locator("dl")).not.toContainText("LABEL-01")
      await expect(label.locator(".aimd-panel-value")).toHaveText("LABEL-01")
      await label.locator("summary").click()
      await expect.poll(() => saved.locator('[data-panel-key="var:photo"] img').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(192)
      await expect(saved.locator('[data-panel-key="check:review"]')).toContainText("复核备注")
      await expect(saved.locator('[data-panel-key="check:review"] .aimd-record-check__status')).toHaveText("未勾选")
      await expect(saved.locator("input, textarea, select, [contenteditable=true]")).toHaveCount(0)
      await page.screenshot({ path: testInfo.outputPath("saved-record.png") })
      await saved.locator('[data-navigate-field="check:review"]').click()
      const target = page.getByTestId("record-main-content").locator('[data-aimd-type="check"][data-aimd-id="review"]')
      await expect(target).toBeFocused()
      await expect(target).toBeInViewport()
      if (width < 768)
        await expect(page.getByTestId("record-fields-drawer")).toBeHidden()
      await expect(target).toBeFocused()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)

      await style.getByText("简洁", { exact: true }).click()
      await page.reload()
      await expect(report).toHaveAttribute("data-record-presentation", "compact")
      await page.goto(entryUrl)
      await expect(fields.getByRole("radio", { name: "简洁" })).toBeChecked()
      await fields.getByText("详细", { exact: true }).click()
      await page.goto(reportUrl)
      await expect(style.getByRole("radio", { name: "简洁" })).toBeChecked()
      await expect(report).toHaveAttribute("data-record-presentation", "compact")
    })
  })
}

for (const width of [1280, 759, 390]) {
  test.describe(`Recording layout at ${width}px`, () => {
    const touch = width === 390
    test.use({ viewport: { width, height: 985 }, hasTouch: touch, isMobile: touch })

    test("long draft scrolls in both directions and shows complete optional labels", async ({ page, request }, testInfo) => {
      const { protocolUrl } = await publishFieldProtocol(request, [
        "# Inspection worksheet",
        '{{step|inspection, title="Inspection"}}',
        '读数 {{var|reading: float | None = None, title="测量读数（mm）"}}',
        '比例 {{var|reading_ratio: float | None = None, title="A260/A280"}}',
        '{{var|q: float | None = None}}',
        '{{var|optional_field_with_a_very_long_identifier_for_small_displays: str | None = None, title="Additional observations for the instrument under review"}}',
        '{{var|label: str}}',
        '{{var|location: str}}',
        '{{var|instrument: str}}',
        '{{var|operator: str}}',
        ...Array.from({ length: 52 }, (_, i) => `Inspection point ${i + 1}`),
        '{{var|final_observation: str, title="Final observation"}}',
      ])
      await page.addInitScript(locale => localStorage.setItem("lang", JSON.stringify({ data: locale, expire: null })), touch ? "en-US" : "zh-CN")
      await page.goto(`${protocolUrl}/add`)
      await expect(page).toHaveURL(/draft=[^&]+/)
      await page.reload()
      const content = page.getByTestId("record-main-content")
      const heading = content.getByRole("heading", { name: "Inspection worksheet" })
      const last = content.locator('[data-rec-focus-key="var:final_observation"]')
      await expect(heading).toBeInViewport()
      await expect(last).not.toBeInViewport()
      const mode = content.getByRole("radiogroup", { name: touch ? "Field display" : "字段显示" })

      if (width < 768) {
        await page.getByTestId("record-open-fields").click()
        const drawer = page.getByTestId("record-fields-drawer")
        await expect(drawer).toBeVisible()
        await drawer.locator(".n-drawer-header__close").click()
        await expect(drawer).toBeHidden()
      }
      const viewport = page.viewportSize()!
      const rect = (await content.boundingBox())!
      const x = Math.min(viewport.width - 24, rect.x + rect.width * 0.75)
      const session = touch ? await page.context().newCDPSession(page) : undefined
      for (const compact of [false, true]) {
        if (compact)
          await mode.getByText(touch ? "Compact" : "简洁", { exact: true }).click()
        const markers = content.locator(".aimd-rec-inline--var-stacked .aimd-field__optional-marker")
        await expect(markers).toHaveCount(4)
        const labelTokens = content.locator(".aimd-rec-inline--var-stacked :is(.aimd-field__optional-marker, .aimd-field__title, .aimd-field__key)")
        const clipped = await labelTokens.evaluateAll(elements => elements.flatMap((element) => {
          const wrapper = element.closest(".aimd-rec-inline--var-stacked")!
          const field = wrapper.getBoundingClientRect()
          const range = document.createRange()
          range.selectNodeContents(element)
          const bounds = range.getBoundingClientRect()
          return bounds.width > 0 && bounds.left >= field.left - 1 && bounds.right <= field.right + 1
            && bounds.top >= field.top - 1 && bounds.bottom <= field.bottom + 1
            ? []
            : [wrapper.textContent?.trim()]
        }))
        expect.soft(clipped, `clipped labels in ${compact ? "compact" : "detailed"} mode`).toEqual([])
        if (!compact)
          await page.screenshot({ path: testInfo.outputPath("optional-fields.png"), animations: "disabled" })
        for (const down of [true, false]) {
          await expect(async () => {
            if (session) {
              const y = viewport.height * (down ? 0.82 : 0.4)
              const dy = viewport.height * (down ? -0.5 : 0.5)
              await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] })
              for (let i = 1; i <= 6; i++)
                await session.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y + dy * i / 6 }] })
              await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })
            }
            else {
              await page.mouse.move(x, viewport.height * 0.75)
              await page.mouse.wheel(0, down ? 1600 : -1600)
            }
            await expect(down ? last : heading).toBeInViewport({ timeout: 350 })
          }).toPass({ timeout: 9000 })
          if (down) {
            await last.fill("Verified at end of draft")
            await last.press("Tab")
          }
        }
      }
      await expect(last).toHaveValue("Verified at end of draft")
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1)
    })
  })
}
