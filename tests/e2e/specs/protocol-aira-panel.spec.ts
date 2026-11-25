import { expect, test } from "@playwright/test"
import { loadFixtures, mockAIEnabled } from "./fixtures"

test("a Protocol selection opens the same Aira panel and follows the reader into revision", async ({ page }) => {
  const fx = await loadFixtures()
  await mockAIEnabled(page, () => true)
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.route("**/chats/qa/message", route => route.fulfill({
    contentType: "text/event-stream",
    body: `data: ${JSON.stringify({ type: "message", data: { index: 0, message: { role: "assistant", content: "Synthetic reading reply." } } })}\n\ndata: [DONE]\n\n`,
  }))
  await page.goto(`/orgs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${fx.analysis.protocol_uid}/protocol`)
  await page.getByTestId("protocol-ask-aira").click()
  await expect(page.getByTestId("context-aira").getByTestId("chat-input")).toBeVisible()
  await page.getByTestId("context-aira-close").click()
  const heading = page.locator(".markdown-body h1").first()
  await heading.click({ clickCount: 3 })
  await page.getByRole("button", { name: "Add to chat", exact: true }).click()
  const panel = page.getByTestId("context-aira")
  const input = panel.getByTestId("chat-input").locator("[contenteditable=true]")
  await expect(input).toContainText((await heading.textContent())!.trim())
  await expect(page.getByTestId("header-aira")).toHaveAttribute("aria-expanded", "true")
  await input.fill("Explain this protocol title")
  await input.press("Enter")
  await expect(panel).toContainText("Synthetic reading reply.")
  await page.getByRole("button", { name: "Edit", exact: true }).first().click()
  await expect(page).toHaveURL(/\/editor\/v/)
  await expect(page.getByTestId("editor-ai-edit-panel")).toContainText("Synthetic reading reply.")
  await expect(page.getByTestId("editor-side-menu-airalogy")).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(input).toBeInViewport()
  await page.getByTestId("context-aira-close").click()
  await page.getByTestId("editor-open-aira").click()
  await expect(panel).toContainText("Synthetic reading reply.")
})

test("a saved Record has one right-hand Aira and a separate field index on narrow screens", async ({ page }) => {
  const { lab, project, schema_governance: record } = await loadFixtures()
  await mockAIEnabled(page, () => true)
  await page.goto(`/labs/${lab.uid}/projects/${project.uid}/protocols/${record.protocol_uid}/v${record.source_version}/record/${record.record_id}/v${record.record_version}`)
  await expect(page.getByTestId("record-main-content")).toBeVisible()
  const panel = page.getByTestId("context-aira")
  const trigger = page.getByTestId("header-aira")
  await trigger.click()
  await expect(panel).toBeVisible()
  await expect(page.locator(".aira-rail[data-aira-docked=true]")).toHaveCount(1)
  await expect(page.locator("[data-tab=ai-assistant]")).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(panel.getByTestId("chat-input")).toBeInViewport()
  await panel.getByTestId("context-aira-close").click()
  await page.getByTestId("record-open-fields").click()
  const fields = page.getByTestId("record-fields-drawer")
  await expect(fields).toBeVisible()
  await expect(fields.getByTestId("chat-input")).toHaveCount(0)
})

test("report analysis uses the displayed revision once across desktop and mobile", async ({ page }) => {
  const { lab, project, schema_governance: record } = await loadFixtures()
  await mockAIEnabled(page, () => true)
  const calls: Record<string, any>[] = []
  await page.route("**/chats/qa/message", (route) => {
    calls.push(route.request().postDataJSON())
    return route.fulfill({
      contentType: "text/event-stream",
      body: `data: ${JSON.stringify({ type: "message", data: { index: 0, message: { role: "assistant", content: "Synthetic analysis of this revision." } } })}\n\ndata: [DONE]\n\n`,
    })
  })
  await page.goto(`/labs/${lab.uid}/projects/${project.uid}/protocols/${record.protocol_uid}/v${record.source_version}/record/${record.record_id}/v${record.record_version}`)
  await page.getByTestId("record-analyze").click()
  const panel = page.getByTestId("context-aira")
  await expect(panel).toContainText("Synthetic analysis of this revision.")
  expect(calls[0].context.ephemeral_context.current_recorder_record).toMatchObject({
    record_id: record.record_id,
    record_revision: record.record_version,
    protocol_version: record.source_version,
    readonly: true,
  })
  expect(calls[0].recorder_target).toBeUndefined()
  await page.getByTestId("context-aira-close").click()
  await page.reload()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByTestId("record-analyze").click()
  await expect(panel.getByTestId("chat-input")).toBeInViewport()
  await expect(panel).toContainText("Synthetic analysis of this revision.")
  expect(calls).toHaveLength(1)
})
