import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

for (const [locale, width] of [["en-US", 390], ["zh-CN", 1440]] as const) {
  test(`Protocol rating: optional feedback, revision, privacy and layout (${locale})`, async ({ page, request }, testInfo) => {
    test.setTimeout(180_000)
    page.setDefaultTimeout(15_000)
    const fixtures = await loadFixtures()
    const language = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "zh-CN" ? "zh-cn" : "en-us"}.json`, import.meta.url), "utf8"))
    const t = language.page.protocol.rating
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(login.ok()).toBeTruthy()
    const headers = { "Auth-Token": (await login.json()).token }
    const uid = `rating_${randomUUID().replaceAll("-", "")}`
    const files = { "protocol.aimd": "# Synthetic rating test\n{{var|value: float}}", "protocol.toml": `[airalogy_protocol]\nid="${uid}"\nname="Synthetic Rating ${uid}"\nversion="0.1.0"\n` }
    const published = await request.post(`${api}/protocols`, { headers, multipart: { project_id: fixtures.project.id, file: { name: "synthetic-rating.zip", mimeType: "application/zip", buffer: Buffer.from(zipSync(Object.fromEntries(Object.entries(files).map(([k, v]) => [k, strToU8(v)])))) } } })
    expect(published.ok(), await published.text()).toBeTruthy()
    const protocol = (await published.json()).data
    const file = { name: "synthetic.csv", mimeType: "text/csv", buffer: Buffer.from("var.value\n2\n4\n") }
    const preview = await request.post(`${api}/protocols/${protocol.id}/records/import`, { headers, multipart: { file, preview: "true" } })
    expect(preview.ok(), await preview.text()).toBeTruthy()
    const imported = await request.post(`${api}/protocols/${protocol.id}/records/import`, { headers, multipart: { file, preview_token: (await preview.json()).preview_token } })
    expect(imported.ok(), await imported.text()).toBeTruthy()
    await page.addInitScript(lang => localStorage.setItem("lang", JSON.stringify({ data: lang, expire: null })), locale)
    await page.setViewportSize({ width, height: 1000 })
    const base = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${uid}`
    await page.goto(`${base}/protocol`)
    await page.locator(".n-tabs-tab").getByText(t.title, { exact: true }).click()
    const panel = page.getByTestId("protocol-rating-panel")
    await expect(panel.getByTestId("rating-recommendation")).toHaveText(t.insufficient)
    await panel.getByRole("button", { name: t.confirmUse, exact: true }).click()
    const useForm = panel.locator("form").filter({ hasText: t.groupHint })
    await useForm.locator(".n-select").first().click()
    await selectVisibleOption(page, /#1 /)
    await selectVisibleOption(page, /#2 /)
    await useForm.locator("h4").click()
    await useForm.locator(".n-select").last().click()
    await selectVisibleOption(page, t.outcome.as_planned)
    await useForm.getByRole("textbox").fill("Synthetic browser feedback only")
    // First save explicitly remains test/non-real, so it cannot increase use count.
    const saveUse = page.waitForResponse(r => r.url().includes(`/protocol-ratings/${protocol.id}/uses`) && r.request().method() === "POST")
    await useForm.getByRole("button", { name: t.saveUse, exact: true }).click()
    const saved = await saveUse
    expect(saved.ok(), await saved.text()).toBeTruthy()
    const use = await saved.json()
    try {
      const summaryURL = `${api}/protocol-ratings/${protocol.id}?version=0.1.0`
      expect((await (await request.get(summaryURL, { headers })).json()).use_count).toBe(0)
      await panel.getByText(t.myUses, { exact: true }).click()
      await panel.getByRole("button", { name: language.common.edit, exact: true }).click()
      const editForm = panel.locator("form").filter({ hasText: t.groupHint })
      await editForm.getByRole("checkbox", { name: t.realConfirmation, exact: true }).check()
      const edited = page.waitForResponse(r => r.url().includes(`/uses/${use.id}`) && r.request().method() === "PUT")
      await editForm.getByRole("button", { name: t.saveUse, exact: true }).click()
      expect((await edited).ok()).toBeTruthy()
      expect((await (await request.get(summaryURL, { headers })).json()).use_count).toBe(1)
      await panel.getByRole("button", { name: t.write, exact: true }).click()
      const review = panel.locator("form").filter({ hasText: t.evidenceHint })
      const fourth = review.getByRole("radio", { name: "4/5", exact: true })
      await fourth.focus()
      await fourth.press("Space")
      await fourth.press("ArrowLeft")
      await expect(review.getByRole("radio", { name: "3/5", exact: true })).toBeChecked()
      await page.keyboard.press("ArrowRight")
      await expect(fourth).toBeChecked()
      await review.locator(".n-select").click()
      await selectVisibleOption(page, use.id.slice(0, 8))
      await review.getByRole("textbox").last().fill("Synthetic reviewer comment")
      const rated = page.waitForResponse(r => r.url().includes(`/protocol-ratings/${protocol.id}/mine`) && r.request().method() === "PUT")
      await review.getByRole("button", { name: t.save, exact: true }).click()
      expect((await rated).ok()).toBeTruthy()
      await expect(panel).toContainText(t.kind.author)
      await panel.getByRole("button", { name: t.calculation }).click()
      await expect(panel.getByTestId("rating-calculation")).toContainText("protocol-rating-v1-trial")
      const download = page.waitForEvent("download")
      await panel.getByRole("button", { name: t.download }).click()
      expect((await download).suggestedFilename()).toBe("protocol-rating-0.1.0.json")
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await expect.poll(() => panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBeTruthy()
      if (width < 500)
        expect((await panel.boundingBox())!.width).toBeGreaterThan(width - 100)
      await panel.screenshot({ animations: "disabled", path: testInfo.outputPath(`rating-${locale}.png`) })
      // A public Protocol does not publish private feedback or even its use count.
      const anonymous = await (await request.get(summaryURL)).json()
      expect(anonymous.use_count).toBe(0)
      expect(anonymous.reviews).toEqual([])
      await panel.getByRole("button", { name: t.write, exact: true }).click()
      const revise = panel.locator("form").filter({ hasText: t.evidenceHint })
      await revise.getByRole("textbox").last().fill("Revised synthetic feedback")
      await revise.getByRole("button", { name: t.save, exact: true }).click()
      await expect(panel).toContainText("Revised synthetic feedback")
      await panel.getByText(t.history, { exact: true }).click()
      await expect(panel).toContainText("Synthetic reviewer comment")
      await panel.getByRole("button", { name: t.write, exact: true }).click()
      await panel.getByRole("button", { name: t.withdraw, exact: true }).click()
      await expect(panel).toContainText(t.noReviews)
      // Return the synthetic execution to non-real; preserve audit/review history.
      const correction = await request.put(`${api}/protocol-ratings/${protocol.id}/uses/${use.id}?version=0.1.0`, { headers, data: { expected_revision: 2, outcome: "as_planned", is_real: false } })
      expect(correction.ok()).toBeTruthy()
      const mine = await (await request.get(`${api}/protocol-ratings/${protocol.id}/mine?version=0.1.0`, { headers })).json()
      const recordId = mine.uses[0].record_ids[0]
      await page.goto(`${base}/v0.1.0/record/${recordId}/v1`)
      await expect(page.getByRole("button", { name: t.open, exact: true })).toContainText(t.optionalFeedback)
      await page.getByRole("button", { name: t.open, exact: true }).click()
      await expect(page.getByTestId("protocol-rating-panel")).toBeVisible()
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await expect(page.getByTestId("protocol-rating-panel")).toHaveAttribute("aria-busy", "false")
      const existingUseForm = page.getByTestId("protocol-rating-panel").locator("form").filter({ hasText: t.groupHint })
      await expect(existingUseForm).toContainText(t.linkedRecords.replace("{count}", "2"))
      await expect(existingUseForm.locator(".n-select")).toHaveCount(1)
      await expect(existingUseForm.getByRole("checkbox", { name: t.realConfirmation, exact: true })).not.toBeChecked()
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`rating-record-${locale}.png`) })
      await page.goto(`${base}/records`)
      await expect(page.getByTestId("protocol-rating-panel")).toHaveCount(0)
      await testInfo.attach("synthetic-local-protocol", { body: `${base}/protocol`, contentType: "text/plain" })
    }
    finally {
      const current = await request.get(`${api}/protocol-ratings/${protocol.id}/mine?version=0.1.0`, { headers })
      if (current.ok()) {
        const entry = (await current.json()).uses.find((item: { id: string }) => item.id === use.id)
        if (entry) {
          const correction = await request.put(`${api}/protocol-ratings/${protocol.id}/uses/${use.id}?version=0.1.0`, { headers, data: { expected_revision: entry.revision, outcome: "as_planned", is_real: false } })
          expect(correction.ok(), await correction.text()).toBeTruthy()
        }
      }
    }
  })
}
