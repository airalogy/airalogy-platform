import { Buffer } from "node:buffer"
import { createServer } from "node:http"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures, mockAIEnabled } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

// Exercise MediaRecorder in Chromium with generated audio, independent of host hardware.
test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] } })

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
    const intent = data.current_message.includes("simulate") ? "simulate" : data.current_message.includes("Explain") ? "answer" : data.current_message.includes("somewhere") ? "clarify" : "fill"
    const operations = data.attachment_texts?.includes("note: ATTACH-456")
      ? [op("note", "ATTACH-456")]
      : data.current_message.includes("ALT-002")
        ? [op("label", "ALT-002"), op("minutes", 25), op("note", "mixed-note")]
        : data.current_message.includes("25") ? [op("minutes", 25)] : [op("label", "001"), op("minutes", 20)]
    res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({
      intent,
      answer: intent === "answer" ? "Label is an identifier; minutes is duration." : intent === "clarify" ? "Which field should contain 12?" : "Recorder suggestion",
      attachment_count: data.attachment_texts?.length || 0,
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
    const archive = zipSync({ "protocol.aimd": strToU8("# Recorder\nLabel: {{var|label: str, examples=[\"EX-100\"]}}\nMinutes: {{var|minutes: int, title=\"Duration in minutes\"}}\nNote: {{var|note: str}}"), "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Recorder test"\nversion="0.1.0"\n`) })
    const published = await request.post(`${api}/protocols`, { headers: { "Auth-Token": (await login.json()).token }, multipart: { project_id: fx.project.id, file: { name: "recorder.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
    expect(published.ok(), await published.text()).toBeTruthy()
    await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`, { waitUntil: "domcontentloaded" })
    const targetField = page.locator('.record-inline-content [data-recorder-field="minutes"]')
    await targetField.hover()
    await targetField.getByRole("button", { name: /Add to chat.*minutes/i }).click()
    const editor = page.getByTestId("chat-input").locator("[contenteditable=true]")
    const reference = editor.locator('[data-type="mention"][data-id="var.minutes"]')
    await expect(reference).toHaveText("@Duration in minutes")
    await expect(reference).toHaveAttribute("title", "var.minutes")
    const contrast = await reference.evaluate((element) => {
      const { color, backgroundColor } = getComputedStyle(element)
      function luminance(rgb: string) {
        const channels = (rgb.match(/\d+/g) || []).slice(0, 3).map(Number)
        const [r, g, b] = channels.map((channel) => {
          const value = channel / 255
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
        })
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
      }
      if (backgroundColor.startsWith("rgba"))
        return 0
      const lighter = Math.max(luminance(color), luminance(backgroundColor))
      const darker = Math.min(luminance(color), luminance(backgroundColor))
      return (lighter + 0.05) / (darker + 0.05)
    })
    expect(contrast).toBeGreaterThanOrEqual(4.5)
    const submit = async (status = 200) => {
      await expect(page.getByTestId("chat-submit")).toHaveAccessibleName(/Send message|发送消息/)
      const result = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
      await editor.press("Enter")
      const response = await result
      expect(response.status(), response.status() === status ? undefined : await response.text()).toBe(status)
    }
    const say = async (message: string, status = 200) => {
      await editor.fill(message)
      await submit(status)
    }
    const field = (id: string) => page.locator(`.record-inline-content .aimd-protocol-recorder__content [data-rec-focus-key="var:${id}"]`)
    const inline = (id: string) => page.locator(`.record-inline-content [data-recorder-field="${id}"]`)
    const action = (id: string, name: string) => inline(id).getByRole("button", { name, exact: true })
    const suggestion = (id: string) => inline(id).locator(".recorder-suggestion")
    await editor.press("End")
    await editor.pressSequentially("Explain label and minutes, is 37 a recommended value?")
    await submit()
    expect(calls[0].current_message).toContain("{{var|minutes,")
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
    await expect(page.getByTestId("context-aira")).toBeVisible()
    await expect(editor).toBeInViewport()
    await page.getByTestId("context-aira-close").click()
    await expect(page.getByTestId("recorder-receipt")).toBeVisible()
    await page.getByTestId("record-open-fields").click()
    const fieldsDrawer = page.getByTestId("record-fields-drawer")
    await fieldsDrawer.getByRole("button", { name: /Add to chat.*minutes/i }).click()
    await expect(fieldsDrawer).toBeHidden()
    await expect(reference).toHaveText("@Duration in minutes")
    await expect(reference).toBeInViewport()
    await expect(page.getByTestId("context-aira")).toContainText("Recorder suggestion")
    await page.getByTestId("context-aira-close").click()
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
    await page.getByTestId("header-aira").click()
    await say("Change minutes to 25")
    await page.getByTestId("context-aira-close").click()
    await expect(suggestion("minutes")).toHaveText("31 → 25")
    await expect(field("minutes")).toHaveValue("31")
    await page.setViewportSize({ width: 1280, height: 844 })
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
    await page.getByTestId("header-aira").click()
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
    await page.setViewportSize({ width: 390, height: 844 })
    await page.context().grantPermissions(["microphone"], { origin: new URL(page.url()).origin })
    await page.getByTestId("context-aira-close").click()
    await page.getByTestId("record-assist").click()
    const composer = page.getByTestId("context-aira").getByTestId("chat-input")
    await expect(page.getByTestId("context-aira").locator("[contenteditable=true]")).toHaveCount(1)
    await expect(page.getByTestId("context-aira").getByText("字段输入", { exact: true })).toHaveCount(0)
    await say("Put 12 somewhere")
    await expect(page.getByTestId("context-aira").getByText("Which field should contain 12?", { exact: true })).toBeVisible()
    await expect(field("minutes")).toHaveValue("")
    const attach = async () => {
      const uploaded = page.waitForResponse(r => r.request().method() === "POST" && /\/attachments\/?$/.test(new URL(r.url()).pathname))
      await composer.getByRole("button", { name: /添加.*(内容|附件|上下文)|Add context/ }).click()
      const [chooser] = await Promise.all([
        page.waitForEvent("filechooser"),
        page.getByText(/^(上传文件|上传附件|Upload file)$/i).filter({ visible: true }).click(),
      ])
      await chooser.setFiles({ name: "observation.txt", mimeType: "text/plain", buffer: Buffer.from("note: ATTACH-456") })
      expect((await uploaded).ok()).toBe(true)
    }
    await attach()
    await say("Explain the attachment")
    await expect(field("note")).toHaveValue("")
    await attach()
    await say("Fill the note from the attached observation")
    await expect(field("note")).toHaveValue("ATTACH-456")
    await page.route("**/chats/stt/message", async (route) => {
      expect(route.request().postDataBuffer()?.length).toBeGreaterThan(100)
      await route.fulfill({ json: { text: "Change minutes to 25" } })
    })
    await composer.getByRole("button", { name: /语音输入|Voice input/ }).click()
    await composer.getByRole("button", { name: /停止|Stop/ }).click()
    await expect(editor).toContainText("Change minutes to 25")
    const dictated = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
    await composer.getByTestId("chat-submit").click()
    const dictatedTurn = (await dictated).request().postDataJSON()
    expect(dictatedTurn.message.files || []).toHaveLength(0)
    expect(dictatedTurn.message.content).toBe("Change minutes to 25")
    await expect(field("minutes")).toHaveValue("25")
    await page.getByTestId("context-aira-close").click()
    await expect(field("label")).toHaveValue("SECOND")
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
  await mockAIEnabled(page, () => false)
  const fx = await loadFixtures()
  await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${fx.analysis.protocol_uid}/add`)
  await expect(page.getByTestId("record-save-draft")).toBeVisible()
  await expect(page.getByTestId("header-aira")).toHaveCount(0)
  await expect(page.getByTestId("record-assist")).toHaveCount(0)
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
