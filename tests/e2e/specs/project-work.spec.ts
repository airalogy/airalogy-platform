import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const messages = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/en-us.json", import.meta.url), "utf8"))
const labels = messages.page.projectWork
const projectPath = "/labs/dev_lab/projects/quickstart/work"
test.use({ storageState: { cookies: [], origins: [] } })

test("researcher coordinates a prototype without a Protocol or AI and retains conflicting edits", async ({ page }, testInfo) => {
  page.setDefaultTimeout(15000)
  page.on("pageerror", error => console.error("R&D page error:", error.message))
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  const loginResponse = page.waitForResponse(r => r.url().endsWith("/api/signin_by_email"))
  await page.getByTestId("login-submit").click()
  const login = await loginResponse
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  await expect(page).not.toHaveURL(/\/login/)
  // This test owns its project: other meeting tests may associate the owner's
  // account with a named contact in the shared quickstart project.
  const source = await page.request.get("/api/projects/by_uid", { headers, params: { lab_uid: "dev_lab", project_uid: "quickstart" } })
  expect(source.ok()).toBeTruthy()
  const uid = `work_${Date.now()}`
  const project = await page.request.post("/api/projects", { headers, data: { lab_id: (await source.json()).lab_id, uid, name: "Synthetic work journey", type: 1 } })
  expect(project.ok(), await project.text()).toBeTruthy()
  await page.goto(`/labs/dev_lab/projects/${uid}/work`)
  await page.getByTestId("work-new").click()
  const title = `Synthetic prototype ${Date.now()}`
  const editor = page.getByTestId("work-editor")
  await editor.getByTestId("work-title").locator("input").fill(title)
  await editor.getByTestId("work-acceptance").locator("textarea").fill("Link the measured comparison and review the design")
  await editor.getByTestId("work-assignee").locator(".n-select").click()
  await page.locator(".n-base-select-option").filter({ hasText: "dev_owner" }).click()
  await editor.locator("input[type=date]").nth(0).fill("2026-11-12")
  await editor.locator("input[type=date]").nth(1).fill("2026-11-20")
  const createdResponse = page.waitForResponse(r => r.url().endsWith("/api/project-work") && r.request().method() === "POST")
  await editor.getByTestId("work-save").click()
  const created = await createdResponse
  expect(created.ok(), await created.text()).toBeTruthy()
  const item = await created.json()
  await expect(page).toHaveURL(new RegExp(`item=${item.id}`))
  await expect(editor.getByTestId("work-title").locator("input")).toHaveValue(title)
  await expect(editor.locator("[role=status]")).toHaveCount(0) // saved item reopens with its persisted version

  await editor.getByRole("button", { name: labels.createDocument, exact: true }).click()
  const docDialog = page.getByRole("dialog", { name: labels.createDocument })
  await docDialog.locator("input").fill("Synthetic optical design")
  await docDialog.getByRole("button", { name: labels.createDocument, exact: true }).click()
  await expect(editor).toContainText("Synthetic optical design")
  await editor.getByTestId("work-change-reason").locator("input").fill("Link design evidence")
  const updateResponse = page.waitForResponse(r => r.url().endsWith(`/api/project-work/${item.id}`) && r.request().method() === "PUT")
  await editor.getByTestId("work-save").click()
  const updated = await updateResponse
  expect(updated.ok(), await updated.text()).toBeTruthy()
  const updatedItem = await updated.json()
  await editor.getByRole("button", { name: /Synthetic optical design/ }).first().click()
  await expect(page.getByRole("dialog", { name: labels.exactSnapshot })).toContainText(title)
  await page.keyboard.press("Escape")
  await editor.getByTestId("work-activity-tab").click()
  await editor.getByTestId("work-activity-body").locator("textarea").fill("Discussed the synthetic optical holder; measurements still pending.")
  await editor.getByTestId("work-activity-save").click()
  await expect(editor.getByTestId("work-event").first()).toContainText("measurements still pending")

  await editor.getByTestId("work-details-tab").click()

  // A real competing API write must not overwrite the user's unsaved title.
  const auth = (await updated.request().allHeaders())["auth-token"]
  const url = updated.url()
  const current = await (await page.request.get(url, { headers: { "Auth-Token": auth } })).json()
  const payload = updated.request().postDataJSON()
  const concurrent = await page.request.put(url, { headers: { "Auth-Token": auth }, data: { ...payload, title: "Concurrent synthetic change", expected_revision: current.revision, request_id: crypto.randomUUID(), change_reason: "Another colleague updated the plan" } })
  expect(concurrent.ok(), await concurrent.text()).toBeTruthy()
  await editor.getByTestId("work-title").locator("input").fill(`${title} retained`)
  await editor.getByTestId("work-change-reason").locator("input").fill("Keep local wording after review")
  await editor.getByTestId("work-save").click()
  await expect(editor.getByTestId("work-error")).toBeVisible()
  await expect(editor.getByTestId("work-title").locator("input")).toHaveValue(`${title} retained`)
  await editor.getByRole("button", { name: labels.compare, exact: true }).click()
  const comparison = page.getByRole("dialog", { name: labels.compare })
  await expect(comparison).toContainText("Concurrent synthetic change")
  await comparison.getByRole("button", { name: labels.keepMine, exact: true }).click()
  await editor.getByTestId("work-save").click()
  await expect(editor.getByTestId("work-error")).toHaveCount(0)
  await expect(editor.locator("[role=status]")).toContainText("saved", { ignoreCase: true })

  // Local input recovery is explicit; it is never mistaken for a saved revision.
  await editor.getByTestId("work-title").locator("input").fill(`${title} unfinished`)
  page.once("dialog", dialog => dialog.accept())
  await page.reload()
  await editor.getByRole("button", { name: labels.restore, exact: true }).click()
  await expect(editor.getByTestId("work-title").locator("input")).toHaveValue(`${title} unfinished`)
  await editor.getByTestId("work-change-reason").locator("input").fill("Recovered local draft")
  await editor.getByTestId("work-save").click()
  await expect(editor.getByTestId("work-error")).toHaveCount(0)
  await expect(editor.locator("[role=status]")).toContainText("saved", { ignoreCase: true })
  await expect(editor.getByTestId("work-save")).not.toHaveClass(/n-button--loading/)
  await page.locator(".n-drawer-header__close").click()
  await expect(editor).toHaveCount(0)

  for (const mode of ["list", "board", "plan"]) {
    await page.locator(".n-radio-group").getByText(labels.views[mode], { exact: true }).click()
    await expect(page.getByTestId("project-work")).toContainText(`${title} unfinished`)
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 980 })
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
      await page.screenshot({ path: testInfo.outputPath(`work-${mode}-${width}.png`), fullPage: true, animations: "disabled" })
    }
  }
  await page.goto("/home")
  const summary = page.getByTestId("work-summary")
  await expect(summary).toContainText(`${title} unfinished`)
  await summary.getByRole("link", { name: new RegExp(title) }).click()
  await expect(editor).toBeVisible()
  expect(updatedItem.evidence).toHaveLength(1)
})

test("Chinese read-only member can inspect R&D work without write controls", async ({ page }, testInfo) => {
  page.setDefaultTimeout(15000)
  const zh = JSON.parse(readFileSync(new URL("../../../packages/shared/src/locales/langs/zh-cn.json", import.meta.url), "utf8")).page.projectWork
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.viewer@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  await page.getByTestId("login-submit").click()
  await expect(page).not.toHaveURL(/\/login/)
  await page.goto("/labs/dev_lab/projects/quickstart/overview")
  await expect(page.getByTestId("work-summary").locator("[role=status]")).toHaveCount(0)
  await expect(page.getByTestId("overview-new-work")).toHaveCount(0)
  await page.goto(`${projectPath}?create=1`)
  await expect(page.getByTestId("project-work").locator(".n-spin-body")).toBeHidden()
  await expect(page.getByTestId("work-editor")).toHaveCount(0)
  // Seed through ordinary authorized endpoints so this test can run alone.
  const authResponse = await page.request.post("/api/signin_by_email", {
    data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" },
  })
  expect(authResponse.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await authResponse.json()).token }
  const projectResponse = await page.request.get("/api/projects/by_uid", {
    headers,
    params: { lab_uid: "dev_lab", project_uid: "quickstart" },
  })
  expect(projectResponse.ok()).toBeTruthy()
  const project = await projectResponse.json()
  const created = await page.request.post("/api/project-work", {
    headers,
    data: { id: crypto.randomUUID(), project_id: project.id, title: `Synthetic prototype reader ${Date.now()}` },
  })
  expect(created.ok(), await created.text()).toBeTruthy()
  const item = await created.json()
  await page.goto(`${projectPath}?item=${item.id}`)
  await expect(page.getByRole("heading", { name: zh.title, exact: true })).toBeVisible()
  await expect(page.getByTestId("work-new")).toHaveCount(0)
  const editor = page.getByTestId("work-editor")
  await expect(editor.getByTestId("work-title")).toHaveCount(0)
  await expect(editor).toContainText("Synthetic prototype")
  await expect(editor.getByTestId("work-save")).toHaveCount(0)
  await expect(editor.getByTestId("work-activity-save")).toHaveCount(0)
  await expect(page.locator(".n-drawer .n-spin-body")).toBeHidden()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 980 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`work-reader-zh-${width}.png`), fullPage: true, animations: "disabled" })
  }
})
