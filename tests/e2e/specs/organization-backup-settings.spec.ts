import { expect, test } from "@playwright/test"

test.skip(process.env.E2E_DEPLOYMENT_MODE !== "single_organization", "Single-organization operator surface")

test("backup policy and recovery status fit the desktop and phone without exposing host paths", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  const status = {
    catalog: [{ id: "local", name: "验收备份盘", code: "ready", free: 2 ** 30, total: 4 * 2 ** 30 }],
    policy: { frequency: "daily", hour: 2, days: 7, weeks: 4, targets: ["local"] },
    revision: 1,
    pending: null as null | string[],
    running: false,
    last_result: { local: { time: 100, success: 100, code: "ok", points: [{ id: "a".repeat(64), time: "2026-01-01T02:00:00Z" }] } },
    last_drill: null,
    timezone: "UTC",
    heartbeat: Math.floor(Date.now() / 1000),
  }
  await page.route("**/api/instance/backups**", async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith("/policy")) {
      const { revision, ...policy } = route.request().postDataJSON()
      expect(revision).toBe(status.revision)
      status.policy = policy
      status.revision += 1
    }
    if (path.endsWith("/requests"))
      status.pending = ["local"]
    await route.fulfill({ json: status })
  })
  await page.goto("/organization/settings")
  const heading = page.getByRole("heading", { name: "存储与备份" })
  const card = heading.locator("../..")
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(heading).toBeVisible()
    await expect(card.getByLabel("验收备份盘")).toBeChecked()
    await expect.poll(() => card.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
  }
  await card.getByText("可恢复的时间点", { exact: false }).click()
  await expect(card.getByText("a".repeat(12))).toBeVisible()
  await card.getByLabel("备份频率").selectOption("off")
  await card.getByRole("button", { name: "保存", exact: true }).click()
  await expect(card.getByText("备份策略已保存。")).toBeVisible()
  await card.getByRole("button", { name: "立即备份" }).click()
  await expect(card.getByRole("button", { name: "立即备份" })).toBeDisabled()
})
