import type { Page } from "@playwright/test"
import { expect, test } from "@playwright/test"

const valid = "# Synthetic protocol\n\n{{var|sample_id: str}}\n{{ref_var|sample_id}}\n"
const invalid = valid.replace("ref_var|sample_id", "ref_var|missing")

async function generatedDraft(page: Page, content = invalid) {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.route("**/api/editor/protocol_generate_draft", route => route.fulfill({ json: {
    content,
    original_content: content,
    repair_status: "needs_review",
    validation: { status: "invalid", diagnostics: [], source_hash: "synthetic", level: "static" },
  } }))
  await page.goto(`/editor?package_id=syntax-${Date.now()}`)
  await page.getByTestId("ai-protocol-create").click()
  await page.getByTestId("ai-protocol-requirements").locator("textarea").fill("Create a synthetic sample form")
  await page.getByTestId("ai-protocol-generate").click()
  await expect(page.getByTestId("protocol-validation")).toContainText("Changes required")
}

test("invalid generated draft is retained, save is blocked, repair requires review and can be undone", async ({ page }) => {
  await generatedDraft(page)
  const panel = page.getByTestId("protocol-validation")
  await expect(panel).toContainText("protocol.aimd:4:1")
  await expect(panel).toContainText("Reference to undefined variable: missing")
  await page.getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByText("Fix the reported issues or retry the check before saving. Your local draft is retained.")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Save Protocol", exact: true })).toHaveCount(0)
  await page.reload()
  await expect(panel).toContainText("Reference to undefined variable: missing")
  let repairs = 0
  await page.route("**/api/editor/code_edit", async (route) => {
    const body = route.request().postDataJSON()
    expect(body.syntax_repair).toBe(true)
    expect(body.files.find((file: { path: string }) => file.path === "protocol.aimd").content).toBe(invalid)
    repairs++
    await route.fulfill({ json: {
      runtime: "opencode",
      contract_version: "1",
      outcome: "changed",
      edit_status: "changed",
      change_set_id: `sha256:${"a".repeat(64)}`,
      message: "Correct the reference to the existing field.",
      changed_files: [{ path: "protocol.aimd", name: "protocol.aimd", type: "aimd", status: "modified", content: valid, diff: "-{{ref_var|missing}}\n+{{ref_var|sample_id}}" }],
      warnings: [],
      execution_log: [],
      risk: { level: "safe", reasons: [], recommended_action: "review" },
    } })
  })
  await page.getByTestId("protocol-repair").click()
  const review = page.getByTestId("editor-ai-review")
  await expect(review).toBeVisible()
  await expect(panel).toContainText("Changes required")
  await review.getByTestId("editor-ai-apply-all").click()
  await expect(panel).toContainText("Static checks passed")
  await page.getByTestId("editor-ai-change-status").getByRole("button", { name: "Undo", exact: true }).click()
  await expect(panel).toContainText("Changes required")
  expect(repairs).toBe(1)
})

test("checker outage is distinct from invalid source and does not discard the draft", async ({ page }) => {
  await generatedDraft(page)
  await page.route("**/api/editor/validate_sources", route => route.fulfill({ status: 503, json: { detail: "Synthetic checker outage" } }))
  await page.getByTestId("protocol-validation").getByRole("button", { name: "Check Protocol" }).click()
  await expect(page.getByTestId("protocol-validation")).toContainText("Checker unavailable")
  await expect(page.getByTestId("protocol-repair")).toHaveCount(0)
  await page.unroute("**/api/editor/validate_sources")
  await page.getByTestId("protocol-validation").getByRole("button", { name: "Check Protocol" }).click()
  await expect(page.getByTestId("protocol-validation")).toContainText("Reference to undefined variable: missing")
})

test("manual checks work without AI and accept protocols longer than 1000 characters", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...await response.json(), ai_enabled: false, enabled_chat_models: [] } })
  })
  await page.goto(`/editor?package_id=syntax-no-ai-${Date.now()}`)
  await page.getByTestId("template-protocol-create").click()
  await page.getByTestId("template-create-confirm").click()
  await expect(page.getByTestId("protocol-validation")).toContainText("Static checks passed")
  await expect(page.getByTestId("protocol-repair")).toHaveCount(0)
  await page.getByTestId("protocol-visual-editor").getByRole("button", { name: /Source/i }).click()
  const source = page.getByTestId("protocol-source-editor").locator(".monaco-editor").first()
  await source.click()
  await page.keyboard.press("ControlOrMeta+A")
  await page.keyboard.insertText(`${valid}\n${"Synthetic notes. ".repeat(100)}`)
  await page.getByTestId("protocol-validation").getByRole("button", { name: "Check Protocol" }).click()
  await expect(page.getByTestId("protocol-validation")).toContainText("Static checks passed")
})
