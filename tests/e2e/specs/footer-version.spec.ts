import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
})

test("runtime version remains visible from sign-in to home and can be copied", async ({ page }, testInfo) => {
  const identity = {
    version: "9.8.7",
    tag: "v9.8.7",
    commit: "a".repeat(40),
    build_time: "2026-01-01T00:00:00Z",
    dirty: false,
    release_manifest_sha256: null,
    database_revision: "synthetic",
    deployment_id: null,
  }
  let reads = 0
  await page.route("**/api/system/version", (route) => {
    reads++
    return route.fulfill({ json: identity })
  })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", { value: {
      writeText: async (text: string) => sessionStorage.setItem("copied-version", text),
    } })
  })
  await page.goto("/login")
  const version = page.getByTestId("platform-version")
  await expect(version).toContainText(/Airalogy Platform\s*v9\.8\.7/)
  await expect(version).toContainText("本地开发版")
  await version.click()
  const details = page.getByTestId("platform-version-details")
  await expect(details).toContainText(identity.commit)
  await details.getByRole("button", { name: "复制诊断信息" }).click()
  await expect(details).not.toBeVisible()
  expect(JSON.parse(await page.evaluate(() => sessionStorage.getItem("copied-version")) || "{}")).toMatchObject({ ...identity, local_development: true })
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
  await expect(version).toContainText("v9.8.7")
  expect(reads).toBe(1)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 980 })
    await version.scrollIntoViewIfNeeded()
    await expect(version).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`footer-${width}.png`) })
  }
})

test("a missing version endpoint leaves sign-in usable without inventing a version", async ({ page }) => {
  await page.route("**/api/system/version", route => route.fulfill({ status: 404, json: { detail: "Not Found" } }))
  await page.goto("/login")
  const version = page.getByTestId("platform-version")
  await expect(version).toContainText("版本暂不可用")
  await expect(version).not.toContainText(/v\d+\.\d+/)
  await expect(version).toBeDisabled()
  const email = page.getByTestId("login-email").locator("input")
  await email.fill("synthetic@example.org")
  await expect(email).toHaveValue("synthetic@example.org")
  await expect(page.getByTestId("login-submit")).toBeEnabled()
})
