import { Buffer } from "node:buffer"
import { createServer } from "node:http"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

test("one Aira conversation explains, fills, reviews individual replacements, undoes fields and isolates examples", async ({ page, request }) => {
  test.skip(process.env.AI_ENABLED === "false", "The AI-disabled case verifies the manual entry.")
  test.setTimeout(120000)
  page.setDefaultTimeout(15000)
  const fileLookups: string[] = []
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (url.pathname.endsWith("/package_files"))
      fileLookups.push(url.searchParams.get("filename") || "")
  })
  let releaseModel: (() => void) | undefined
  const calls: Array<{ references: string[], last_applied: string[], current_message: string, conversation: unknown[] }> = []
  const server = createServer(async (req, res) => {
    if (req.url !== "/api/endpoints/chat/field_input/turn") {
      res.writeHead(404).end()
      return
    }
    const parts = []
    for await (const part of req) parts.push(part)
    const data = JSON.parse(Buffer.concat(parts).toString())
    if (data.current_message === "unavailable") {
      res.writeHead(503, { "Content-Type": "application/json" }).end(JSON.stringify({ detail: "Synthetic model unavailable" }))
      return
    }
    calls.push(data)
    if (data.current_message.includes("hold"))
      await new Promise<void>((resolve) => { releaseModel = resolve })
    const op = (rf_name: string, rf_value: string | number) => ({ operation: "update", rf_name, rf_value, source: String(rf_value) })
    const intent = data.current_message.includes("simulate") ? "simulate" : data.current_message.startsWith("Explain") ? "answer" : "fill"
    const operations = data.current_message.includes("ALT-002")
      ? [op("label", "ALT-002"), op("minutes", 25), op("note", "mixed-note")]
      : data.current_message.includes("25") ? [op("minutes", 25)] : [op("label", "001"), op("minutes", 20)]
    res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({
      intent,
      answer: intent === "answer" ? "Label is an identifier; minutes is duration." : "Recorder suggestion",
      references: ["label", "minutes"],
      operations: intent === "fill" ? operations : [],
    }))
  })
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject).listen(41999, "127.0.0.1", resolve)
  })
  try {
    const fx = await loadFixtures()
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const uid = `recorder_${Date.now()}`
    const archive = zipSync({ "protocol.aimd": strToU8("# Recorder\nLabel: {{var|label: str, examples=[\"EX-100\"]}}\nMinutes: {{var|minutes: int}}\nNote: {{var|note: str}}"), "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Recorder test"\nversion="0.1.0"\n`) })
    const published = await request.post(`${api}/protocols`, { headers: { "Auth-Token": (await login.json()).token }, multipart: { project_id: fx.project.id, file: { name: "recorder.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
    expect(published.ok(), await published.text()).toBeTruthy()
    await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`, { waitUntil: "domcontentloaded" })
    await page.locator("[data-tab=ai-assistant]").click()
    const editor = page.getByTestId("chat-input").locator("[contenteditable=true]")
    const say = async (message: string, status = 200) => {
      await editor.fill(message)
      const result = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
      await editor.press("Enter")
      const response = await result
      expect(response.status()).toBe(status)
    }
    const field = (id: string) => page.locator(`.record-inline-content .aimd-protocol-recorder__content [data-rec-focus-key="var:${id}"]`)
    const inline = (id: string) => page.locator(`.record-inline-content [data-recorder-field="${id}"]`)
    const action = (id: string, name: string) => inline(id).getByRole("button", { name, exact: true })
    const suggestion = (id: string) => inline(id).locator(".recorder-suggestion")
    await say("Explain label and minutes, is 37 a recommended value?")
    await expect(page.getByText("Label is an identifier; minutes is duration.").first()).toBeVisible()
    await expect(field("minutes")).toHaveValue("")
    await say("Fill those two with 001 and 20")
    await expect(page.getByTestId("recorder-receipt")).toContainText("minutes")
    await expect(field("label")).toHaveValue("001")
    await expect(field("minutes")).toHaveValue("20")
    await say("Change label to ALT-002 and minutes to 25, and fill note with mixed-note")
    await expect(suggestion("label")).toHaveText("001 → ALT-002")
    await expect(suggestion("minutes")).toHaveText("20 → 25")
    await expect(field("minutes")).toHaveValue("20")
    await expect(field("note")).toHaveValue("mixed-note")
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(page.getByRole("button", { name: "Submit", exact: true })).toBeDisabled()
    await say("Please simulate the remaining fields")
    await expect(page.getByTestId("open-example-preview")).toBeVisible()
    await expect(suggestion("minutes")).toHaveText("20 → 25")
    await expect(field("minutes")).toHaveValue("20")
    await action("label", "Keep original").click()
    await action("minutes", "Replace").click()
    await expect(field("label")).toHaveValue("001")
    await expect(field("minutes")).toHaveValue("25")
    await action("minutes", "Undo this field").click()
    await expect(field("minutes")).toHaveValue("20")
    await expect(field("note")).toHaveValue("mixed-note")
    await action("note", "Undo this field").click()
    await expect(field("note")).toHaveValue("")
    const noteInput = await field("note").elementHandle()
    await say("Please simulate the remaining fields")
    await expect(page.getByTestId("recorder-receipt")).toContainText("Protocol editor preview")
    await expect(page.getByTestId("accept-remaining")).toHaveCount(0)
    await expect(suggestion("note")).toHaveCount(0)
    await expect(field("note")).toHaveValue("")
    expect(await field("note").evaluate((element, original) => element === original, noteInput!)).toBe(true)
    const opening = page.waitForEvent("popup")
    await page.getByTestId("open-example-preview").click()
    const preview = await opening
    await expect(preview).toHaveURL(new RegExp(`/${uid}/editor/v0\.1\.0`))
    await preview.getByTestId("test-example-data").click()
    const exampleForm = preview.getByTestId("editor-example-form")
    await expect(exampleForm).toContainText("Filled 3 fields")
    const sample = exampleForm.locator('[data-rec-focus-key="var:label"]')
    await expect(sample).toHaveValue("EX-100")
    await expect(sample).toBeEditable()
    await sample.fill("Edited example")
    await preview.getByRole("button", { name: "Validate test form" }).click()
    await expect(exampleForm.getByRole("status")).toBeVisible()
    await preview.getByTestId("exit-example-preview").click()
    await expect(exampleForm).toHaveCount(0)
    await preview.getByTestId("test-example-data").click()
    await expect(sample).not.toHaveValue("Edited example")
    await preview.close()
    await expect(field("label")).toHaveValue("001")
    await expect(field("minutes")).toHaveValue("20")
    await expect(field("note")).toHaveValue("")
    const pending = say("Change the second to 25; hold for a moment")
    await expect.poll(() => Boolean(releaseModel)).toBe(true)
    await field("minutes").fill("31")
    await field("minutes").blur()
    releaseModel!()
    await pending
    await expect(page.getByTestId("recorder-receipt")).toContainText("Skipped")
    await expect(field("minutes")).toHaveValue("31")
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await say("unavailable", 503)
    await expect(field("minutes")).toHaveValue("31")
    await page.getByTestId("record-save-draft").click()
    const draft = await page.evaluate(() => localStorage.getItem("unitRecordDraft"))
    expect(draft).toContain("001")
    expect(draft).toContain("31")
    expect(draft).not.toContain("Example")
    const records = await request.get(`${api}/protocols/${(await published.json()).data.id}/records`, { headers: { "Auth-Token": (await login.json()).token } })
    expect((await records.json()).total_count).toBe(0)
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.getByTestId("recorder-receipt")).toBeVisible()
    const viewerLogin = await request.post(`${api}/signin_by_email`, { data: { email: "dev.viewer@airalogy.dev", password: "AiralogyDev123!" } })
    const denied = await request.post(`${api}/chats/qa/message`, { headers: { "Auth-Token": (await viewerLogin.json()).token }, data: {
      protocol_id: (await published.json()).data.id,
      context: {},
      model: { model_type: 1 },
      message: { role: "user", content: "fill" },
      recorder_target: { form_id: "viewer-form-01234", request_id: "viewer-turn-01234", version: "0.1.0" },
    } })
    expect([400, 403]).toContain(denied.status())
    expect(calls).toHaveLength(6)
    expect(calls[1].references).toEqual(["label", "minutes"])
    expect(calls[2].last_applied).toEqual(["label", "minutes"])
    expect(calls[1].conversation.length).toBeGreaterThanOrEqual(2)
    await page.setViewportSize({ width: 1280, height: 844 })
    if (!await editor.isVisible())
      await page.locator("[data-tab=ai-assistant]").click()
    await say("Change minutes to 25")
    await expect(suggestion("minutes")).toHaveText("31 → 25")
    await field("minutes").fill("32")
    await field("minutes").fill("31")
    await field("minutes").blur()
    await expect(suggestion("minutes")).toHaveCount(0)
    await expect(action("minutes", "Undo this field")).toHaveCount(0)
    await field("note").fill("Recorded note")
    await field("note").blur()
    await page.getByTestId("record-save-draft").click()
    const firstDraft = page.url()
    await page.reload({ waitUntil: "domcontentloaded" })
    await expect(field("note")).toHaveValue("Recorded note")
    await expect(page.getByTestId("simulated-fields")).toHaveCount(0)
    await page.goto(`${firstDraft.split("?")[0]}?newRecord=true`, { waitUntil: "domcontentloaded" })
    await expect(field("note")).toHaveValue("")
    await field("label").fill("SECOND")
    await field("label").blur()
    await page.getByTestId("record-save-draft").click()
    await page.goto(firstDraft, { waitUntil: "domcontentloaded" })
    await expect(field("label")).toHaveValue("001")
    await expect(field("minutes")).toHaveValue("31")
    await expect(field("note")).toHaveValue("Recorded note")
    // Subsequent edits do not affect the other draft.
    await field("note").fill("Synthetic browser observation")
    await field("note").blur()
    await expect(page.getByTestId("simulated-fields")).toHaveCount(0)
    await page.getByRole("button", { name: "Submit", exact: true }).click()
    await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
    await expect(page.getByRole("button", { name: "View saved Record", exact: true })).toBeVisible()
    const committed = await request.get(`${api}/protocols/${(await published.json()).data.id}/records`, { headers: { "Auth-Token": (await login.json()).token } })
    const saved = await committed.json()
    expect(saved.total_count).toBe(1)
    expect(saved.records[0].data.var).toMatchObject({ label: "001", minutes: 31, note: "Synthetic browser observation" })
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`, { waitUntil: "domcontentloaded" })
    await page.locator("[data-tab=ai-assistant]").click()
    // An ordinary entry resumes the other draft after the first was submitted.
    await expect(field("label")).toHaveValue("SECOND")
    await say("simulate")
    await expect(page.getByTestId("recorder-receipt")).toContainText("当前记录保持原样")
    await expect(page.getByTestId("open-example-preview")).toBeVisible()
    await expect(field("minutes")).toHaveValue("")
    await expect(field("note")).toHaveValue("")
    const quick = await request.post(`${api}/chats/field_input/message`, {
      headers: { "Auth-Token": (await login.json()).token },
      data: { protocol_id: (await published.json()).data.id, model: { model_type: 1 }, message: { role: "user", content: "simulate" }, recorder_target: { form_id: "quick-form-01234", request_id: "quick-turn-01234", version: "0.1.0", locale: "zh-CN" } },
    })
    expect(quick.ok(), await quick.text()).toBeTruthy()
    expect((await quick.json()).recorder_proposal).toMatchObject({ intent: "simulate", values: {} })
    expect(fileLookups).not.toEqual(expect.arrayContaining(["001"]))
    expect(fileLookups).not.toEqual(expect.arrayContaining(["mixed-note"]))
  }
  finally {
    releaseModel?.()
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
})

test("manual Record entry remains usable with Aira disabled", async ({ page }) => {
  test.skip(process.env.AI_ENABLED !== "false", "Only for the AI-disabled deployment")
  const fx = await loadFixtures()
  await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${fx.analysis.protocol_uid}/add`)
  await expect(page.getByTestId("record-save-draft")).toBeVisible()
  await expect(page.locator("[data-tab=ai-assistant]")).toHaveCount(0)
  await expect(page.locator(".record-inline-content input").first()).toBeVisible()
})

test("unpublished Protocol can test examples without AI or writing a Record", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  await page.goto(`/editor?package_id=example-preview-${Date.now()}`)
  await page.getByTestId("template-protocol-create").click()
  await page.getByTestId("template-create-confirm").click()
  const writes: string[] = []
  page.on("request", (req) => {
    if (["POST", "PATCH", "PUT", "DELETE"].includes(req.method()) && /\/api\/(?:protocols|records|chats)(?:[/?]|$)/.test(req.url()))
      writes.push(req.url())
  })
  const visual = page.getByTestId("protocol-visual-editor")
  const document = visual.locator(".ProseMirror[contenteditable=true]")
  await expect(document).toBeVisible()
  await document.press("End")
  await document.press("ControlOrMeta+End")
  await document.press("Enter")
  await page.keyboard.insertText("Synthetic visual authoring check")
  await expect(document).toContainText("Synthetic visual authoring check")
  await visual.getByRole("button", { name: /源码|源代码|Source/i }).click()
  const sourceEditor = page.getByTestId("protocol-source-editor")
  await expect(sourceEditor).toBeVisible()
  await sourceEditor.getByRole("button", { name: /所见即所得|可视化|WYSIWYG/i }).click()
  await expect(visual.locator(".ProseMirror")).toContainText("Synthetic visual authoring check")
  await page.getByTestId("test-example-data").click()
  const form = page.getByTestId("editor-example-form")
  const count = form.locator('[data-rec-focus-key="var:observation_count"]')
  await expect(count).toHaveValue("0")
  const name = form.locator('[data-rec-focus-key="var:sample_label"]')
  await expect(name).not.toHaveValue("")
  await name.fill("")
  await page.getByRole("button", { name: "校验测试表单" }).click()
  await expect(form.getByRole("status")).toContainText("需要检查")
  await name.fill("临时示例")
  await page.getByRole("button", { name: "校验测试表单" }).click()
  await expect(form.getByRole("status")).toContainText("通过")
  await page.getByTestId("exit-example-preview").click()
  await page.getByTestId("test-example-data").click()
  await expect(name).not.toHaveValue("临时示例")
  expect(writes).toEqual([])
})

test("editor previews registered field types without inventing file references", async ({ page, request }) => {
  const fx = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const user = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await user.json()).token }
  const uid = `typed_preview_${Date.now()}`
  const archive = zipSync({
    "protocol.aimd": strToU8("# Typed preview\nGroup: {{var|group: BloodType}}\nSequence: {{var|seq: ATCG}}\nScan: {{var|scan: FileIdPNG}}"),
    "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Typed preview"\nversion="0.1.0"\n`),
  })
  const published = await request.post(`${api}/protocols`, { headers, multipart: { project_id: fx.project.id, file: { name: "preview.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
  expect(published.ok(), await published.text()).toBeTruthy()
  await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/${uid}/editor/v0.1.0`)
  await page.getByTestId("test-example-data").click()
  const preview = page.getByTestId("editor-example-form")
  await expect(preview).toContainText("Filled 2 fields")
  await expect(preview).toContainText("Fields to fill manually or calculate: scan")
  await expect(preview.locator('[data-rec-focus-key="var:seq"]')).toHaveValue("ATCG")
  await page.getByTestId("exit-example-preview").click()
  const records = await request.get(`${api}/protocols/${(await published.json()).data.id}/records`, { headers })
  expect((await records.json()).total_count).toBe(0)
})

test("native table cells and quiz answers survive a draft reload and Record submission", async ({ page, request }) => {
  const fx = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  const uid = `native_table_${Date.now()}`
  const aimd = [
    "# Synthetic readings",
    "{{var_table|readings, subvars=[var(label: str)]}}",
    "\n```quiz",
    "id: note",
    "type: open",
    "stem: Describe the synthetic sample.",
    "```",
  ].join("\n")
  const file = zipSync({
    "protocol.aimd": strToU8(aimd),
    "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Synthetic readings"\nversion="0.1.0"\n`),
  })
  const published = await request.post(`${api}/protocols`, { headers, multipart: { project_id: fx.project.id, file: { name: "table.zip", mimeType: "application/zip", buffer: Buffer.from(file) } } })
  expect(published.ok(), await published.text()).toBeTruthy()
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`)
  const form = page.locator(".record-inline-content.aimd-protocol-recorder")
  const cell = form.locator('[data-rec-focus-key="var_table:readings:0:label"]')
  const answer = form.locator('[data-rec-focus-key="quiz:note:open"]')
  await cell.fill("synthetic-A")
  await answer.fill("Observed in test fixture")
  await page.getByTestId("record-save-draft").click()
  await page.reload()
  await expect(cell).toHaveValue("synthetic-A")
  await expect(answer).toHaveValue("Observed in test fixture")
  await cell.fill("synthetic-B")
  await page.getByRole("button", { name: "Submit", exact: true }).click()
  const posted = page.waitForResponse(res => res.request().method() === "POST" && res.url().endsWith("/records"))
  await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
  const response = await posted
  expect(response.ok(), await response.text()).toBeTruthy()
  const saved = await response.json()
  const stored = await request.get(`${api}/protocols/${(await published.json()).data.id}/records/${saved.id}?version=1`, { headers })
  expect(stored.ok(), await stored.text()).toBeTruthy()
  expect((await stored.json()).data).toMatchObject({ var: { readings: [{ label: "synthetic-B" }] }, quiz: { note: "Observed in test fixture" } })
  await page.getByRole("dialog").getByRole("button", { name: "View saved Record", exact: true }).click()
  await page.getByRole("button", { name: "Revise", exact: true }).click()
  await expect(cell).toHaveValue("synthetic-B")
  await expect(answer).toHaveValue("Observed in test fixture")
})

test("visual edits preserve executable fence arguments and hosted forms do not schedule them twice", async ({ page }) => {
  await page.goto("/")
  const result = await page.evaluate(async () => {
    const modulePath = "/src/utils/recorderMarkdown.ts"
    const { preserveVisualFenceMetadata, hostedRecorderContent, recorderVariableList } = await import(/* @vite-ignore */ modulePath)
    const body = 'assigner({mode:"auto",dependent_fields:["a"],assigned_fields:["b"]},function calculate({a}){return {b:a*2}})'
    const before = ["Original", "```assigner runtime=client", body, "```"].join("\n")
    const after = before.replace("Original", "Edited").replace("a*2", "a*3")
    const example = ["````markdown", before, "````"].join("\n")
    return {
      drawer: recorderVariableList("Example: `{{var|n: str}}`\n\nEnter {{var|n: int}}", ["n"]),
      preserved: preserveVisualFenceMetadata(before, after.replace(" runtime=client", "")) === after,
      hosted: hostedRecorderContent(before).trim(),
      example: hostedRecorderContent(example) === example,
    }
  })
  expect(result).toEqual({ preserved: true, hosted: "Original", example: true, drawer: "{{var|n: int}}" })
})
