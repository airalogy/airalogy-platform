import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

for (const width of [1440, 390]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width === 390, isMobile: width === 390 })

    test("field panel labels, photo upload and outline", async ({ page, request }) => {
      test.setTimeout(150_000)
      page.setDefaultTimeout(30_000)
      const fixtures = await loadFixtures()
      const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
      const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
      expect(login.ok()).toBeTruthy()
      const uid = `panel_${randomUUID().replaceAll("-", "")}`
      const files = {
        "protocol.toml": `[airalogy_protocol]\nid="${uid}"\nname="Synthetic field panel"\nversion="0.1.0"`,
        "protocol.aimd": [
          '{{var|short_label: str, title="标签编号"}}',
          '{{var|location: str, title="位置", placeholder="例如 A-01"}}',
          '{{var|photo: FileIdJPG | None = None, title="标签照片"}}',
          '{{step|prepare, title="准备标签", check=True}}',
          '{{check|review, title="核对标签"}}',
          '{{check|legacy}}',
        ].join("\n\n"),
      }
      const published = await request.post(`${api}/protocols`, {
        headers: { "Auth-Token": (await login.json()).token },
        multipart: { project_id: fixtures.project.id, file: {
          name: "panel.zip",
          mimeType: "application/zip",
          buffer: Buffer.from(zipSync(Object.fromEntries(Object.entries(files).map(([name, content]) => [name, strToU8(content)])))),
        } },
      })
      expect(published.ok(), await published.text()).toBeTruthy()
      await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
      await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${uid}/add`, { waitUntil: "domcontentloaded" })
      if (width === 390)
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
      await expect(panel.getByRole("button", { name: "准备标签", exact: true })).toBeVisible()
      await expect(panel.getByRole("button", { name: "legacy", exact: true })).toBeVisible()
      await text.fill("LABEL-01")
      await text.press("Tab")
      const photo = panel.locator('[data-panel-field="var:photo"]')
      await expect(photo).toContainText("选填")
      await expect(photo.locator(".aimd-field__name")).toHaveCount(0)
      const trigger = photo.getByRole("button", { name: /上传照片.*JPG/i })
      await expect(trigger).toBeVisible()
      // The empty required field reports an error on blur. The first tap must
      // still reach the upload button even if the validation message moves it.
      await panel.getByPlaceholder("例如 A-01").focus()
      const jpeg = await page.evaluate(() => document.createElement("canvas").toDataURL("image/jpeg").split(",")[1])
      const [chooser] = await Promise.all([page.waitForEvent("filechooser"), width === 390 ? trigger.tap() : trigger.click()])
      const uploaded = page.waitForResponse(r => r.url().endsWith("/airalogy_files") && r.request().method() === "POST")
      await chooser.setFiles({ name: "label.jpg", mimeType: "image/jpeg", buffer: Buffer.from(jpeg, "base64") })
      const response = await uploaded
      expect(response.ok(), await response.text()).toBeTruthy()
      expect((await response.json()).airalogy_file_id).toMatch(/^airalogy\.id\.file\..+\.jpg$/i)
      await expect(photo.getByRole("img", { name: "label.jpg" })).toBeVisible()
      await photo.getByRole("button", { name: /清除|移除|清空|删除/ }).click()
      await expect(trigger).toBeVisible()
      await panel.getByRole("button", { name: "核对标签", exact: true }).click()
      await expect(page.locator('[data-rec-focus-key="check:review:checked"]')).toBeFocused()
    })
  })
}
