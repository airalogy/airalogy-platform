import { Buffer } from "node:buffer"
import { expect, test } from "@playwright/test"

for (const width of [390, 1440]) {
  test(`official editor and Recorder run locally at ${width}px`, async ({ page }, testInfo) => {
    const failures: string[] = []
    const outbound: string[] = []
    page.on("pageerror", error => failures.push(error.message))
    page.on("request", (request) => {
      if (!request.url().startsWith("http://127.0.0.1:3109/") && !request.url().startsWith("blob:"))
        outbound.push(request.url())
    })
    await page.setViewportSize({ width, height: 950 })
    await page.goto("/agent-preview.html")
    await expect(page.getByRole("heading", { name: /Local Protocol|本地 Protocol/ })).toBeVisible()
    await page.locator("input[type=\"file\"]").setInputFiles({ name: "protocol.aimd", mimeType: "text/plain", buffer: Buffer.from("# Synthetic preview\n{{var|value: float, ge=1, le=10}}\n{{var|group: str}}") })
    await page.getByRole("button", { name: /Test with example|用示例数据/ }).click()
    await expect(page.getByRole("status")).toContainText(/Preview only|仅用于预览/)
    const recorder = page.getByRole("region", { name: "Recorder preview" })
    await expect(recorder.locator("input").first()).not.toHaveValue("")
    const download = page.waitForEvent("download")
    await page.getByRole("button", { name: /Download edited|下载修改/ }).click()
    expect((await download).suggestedFilename()).toBe("protocol.aimd")
    await page.getByRole("button", { name: /Check form|检查填写/ }).click()
    await expect(page.getByRole("status")).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    expect(failures).toEqual([])
    expect(outbound).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`preview-${width}.png`), fullPage: true })
  })
}
