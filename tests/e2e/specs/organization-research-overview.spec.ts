import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

for (const width of [1440, 390]) {
  test(`organization research overview follows original work and daily activity at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    const { lab } = await loadFixtures()
    const auth = await page.request.post("/api/signin_by_email", { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(auth.ok()).toBeTruthy()
    const headers = { "Auth-Token": (await auth.json()).token }
    const uid = `overview_${randomUUID().slice(0, 8)}`
    const project = await page.request.post("/api/projects", { headers, data: { uid, name: `Synthetic ${uid}`, type: 1, lab_id: lab.id } })
    expect(project.ok()).toBeTruthy()
    const { id } = await project.json()
    const blockerId = randomUUID()
    for (const work of [
      { id: blockerId, title: "Fixture delivery", state: "blocked", blocker: "Waiting for fixture", next_step: "Check connector" },
      { id: randomUUID(), title: "Bench review", kind: "milestone", planned_end: "2027-03-01" },
    ]) {
      const response = await page.request.post("/api/project-work", { headers, data: { ...work, project_id: id } })
      expect(response.ok()).toBeTruthy()
    }
    const when = new Date()
    when.setDate(when.getDate() - 2)
    when.setHours(12, 0, 0, 0)
    const day = await page.evaluate(value => new Intl.DateTimeFormat("sv-SE").format(new Date(value)), when.toISOString())
    const title = `Research note ${uid}`
    const log = await page.request.post("/api/research-log/entries", {
      headers,
      data: { scope_type: "project", project_id: id, kind: "progress", title, occurred_at: when.toISOString() },
    })
    expect(log.ok()).toBeTruthy()
    await page.goto(`/orgs/${lab.uid}/members`)
    await page.getByText("研发总览", { exact: true }).click()
    const overview = page.getByTestId("org-research-overview")
    const card = overview.getByTestId("org-project").filter({ hasText: uid })
    await expect(card).toContainText("Waiting for fixture")
    await expect(card).toContainText("Check connector")
    await expect(card).toContainText("Bench review")
    await expect(card).toContainText("2027-03-01")
    await overview.getByRole("button", { name: new RegExp(`^${day}:`) }).click()
    await expect(overview.getByTestId("activity-list-title")).toContainText(day)
    const event = overview.getByTestId("overview-events").getByRole("listitem").filter({ hasText: title })
    await expect(event).toContainText(`Synthetic ${uid}`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
    await card.getByRole("link", { name: "Waiting for fixture" }).click()
    await expect(page).toHaveURL(new RegExp(`/projects/${uid}/work\\?item=${blockerId}`))
    await expect(page.getByTestId("work-title").locator("input")).toHaveValue("Fixture delivery")
  })
}
