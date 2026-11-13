/** Opt-in real-model acceptance. No intercepted responses or canned AI output. */
import type { Browser, BrowserContext, Page } from "@playwright/test"
import { Buffer } from "node:buffer"
import { execFileSync } from "node:child_process"
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "../e2e/specs/fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../apps/web/package.json", import.meta.url))("fflate")
const api = process.env.DEMO_API_URL || "http://127.0.0.1:4100"
const web = process.env.DEMO_WEB_URL || "http://127.0.0.1:3100"
const output = "tests/e2e/.runtime/learning-demos/capture"
const recording = process.env.DEMO_RECORD === "1"
const scripts = JSON.parse(await readFile("docs/demos/narration.json", "utf8")).lessons
let state: Awaited<ReturnType<BrowserContext["storageState"]>>
let projectPath: string
let projectName: string
let formPath: string
let analysisPath: string
let headers: { "Auth-Token": string }
const targets: Record<string, string> = {}

test.beforeAll(async ({ browser, request }) => {
  test.setTimeout(120_000)
  expect(process.env.DEMO_LIVE_AI, "Real models require explicit opt-in").toBe("1")
  const instance = await (await request.get(`${api}/instance`)).json()
  expect(instance.ai_enabled).toBe(true)
  expect(instance.enabled_chat_models.length).toBeGreaterThan(0)
  const context = await browser.newContext({ baseURL: web })
  const page = await context.newPage()
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  const login = page.waitForResponse(r => r.url().endsWith("/api/signin_by_email"))
  await page.getByTestId("login-submit").click()
  headers = { "Auth-Token": (await (await login).json()).token }
  await expect(page).not.toHaveURL(/\/login/)
  const fx = await loadFixtures()
  const uid = `ai_demo_${Date.now().toString(36)}`
  projectName = "Aira 教学演示 · 虚构数据"
  const created = await request.post(`${api}/projects`, { headers, data: { lab_id: fx.lab.id, name: projectName, uid, type: 1, description: "独立的本地 AI 演示空间，所有样本和数值均为虚构。" } })
  expect(created.ok(), await created.text()).toBe(true)
  const project = await created.json()
  expect(project.type).toBe(1)
  projectPath = `/labs/${fx.lab.uid}/projects/${uid}`
  const definitions = [
    { uid: "aira_form", name: "Aira 填表演示", aimd: "# 样本观察\n\n本项目全部数据为虚构教学数据。根据用户明确提供的观察值填写，不推测缺失值。\n\n样本编号：{{var|sample_label: str}}\n\n观察数量：{{var|observation_count: int, ge=0}}\n\n备注：{{var|notes: str, default=\"\"}}\n" },
    { uid: "aira_analysis", name: "Aira 分析演示", aimd: "# 虚构样本读数\n\n仅供软件教学，不构成科研结论。\n\n样本编号：{{var|sample_id: str}}\n\n分组：{{var|group: str}}\n\n读数：{{var|measurement: float, ge=0}}\n" },
  ]
  for (const definition of definitions) {
    const archive = zipSync({ "protocol.aimd": strToU8(definition.aimd), "protocol.toml": strToU8(`[airalogy_protocol]\nid="${definition.uid}"\nname="${definition.name}"\nversion="0.1.0"\n`) })
    const response = await request.post(`${api}/protocols`, { headers, multipart: { project_id: project.id, file: { name: "synthetic.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
    expect(response.ok(), await response.text()).toBe(true)
    const protocol = (await response.json()).data
    if (definition.uid === "aira_form") {
      formPath = `${projectPath}/protocols/${definition.uid}`
    }
    else {
      analysisPath = `${projectPath}/protocols/${definition.uid}`
      for (const [i, measurement] of [10, 12, 14, 16, 18, 20].entries()) {
        const record = await request.post(`${api}/protocols/${protocol.id}/records`, { headers, data: { step: {}, check: {}, report: "虚构教学数据", var: { sample_id: `DEMO-${i + 1}`, group: i < 3 ? "A" : "B", measurement } } })
        expect(record.ok(), await record.text()).toBe(true)
      }
    }
  }
  state = await context.storageState()
  await context.close()
  await mkdir(output, { recursive: true })
})

test.afterAll(async () => {
  await writeFile(`${output}/ai-local-targets.json`, JSON.stringify({ project: `${web}${projectPath}/protocols`, ...targets }, null, 2))
})

async function scene(browser: Browser, id: string, body: (page: Page, step: (index: number, action?: () => Promise<void>) => Promise<void>, poster: () => Promise<void>) => Promise<void>) {
  test.setTimeout(600_000)
  const context = await browser.newContext({ baseURL: web, storageState: state, viewport: { width: 1440, height: 1000 }, ...(recording ? { recordVideo: { dir: `${output}/raw`, size: { width: 1440, height: 1000 } } } : {}) })
  await context.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  const page = await context.newPage()
  page.setDefaultTimeout(20_000)
  const requests: { path: string, status: number }[] = []
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname
    if (response.request().method() === "POST" && /protocol_generate_draft|editor\/code_edit|chats\/qa\/message|aira-drafts$|aira-interpretations$/.test(path))
      requests.push({ path, status: response.status() })
  })
  const start = Date.now()
  const cues: { at: number, zh: string, en: string }[] = []
  const step = async (index: number, action?: () => Promise<void>) => {
    const line = scripts[id][index]
    cues.push({ at: (Date.now() - start) / 1000, zh: line.source_zh, en: line.en })
    if (action)
      await action()
    if (recording)
      await page.waitForTimeout(3500)
  }
  let succeeded = false
  try {
    await body(page, step, () => page.screenshot({ path: `${output}/${id}.png`, animations: "disabled" }).then(() => {}))
    expect(requests.length).toBeGreaterThan(0)
    expect(requests.every(r => r.status === 200 || r.status === 201)).toBe(true)
    expect(cues.length).toBe(scripts[id].length)
    targets[id] = page.url()
    succeeded = true
  }
  finally {
    const duration = (Date.now() - start) / 1000
    await writeFile(test.info().outputPath(`${id}-requests.json`), JSON.stringify(requests, null, 2))
    if (!succeeded) {
      await page.screenshot({ path: test.info().outputPath(`${id}-failure.png`), fullPage: true })
      await writeFile(test.info().outputPath(`${id}-text.txt`), (await page.locator("body").textContent()) || "")
    }
    await context.close()
    if (recording && succeeded) {
      await copyFile(await page.video()!.path(), `${output}/${id}.webm`)
      await writeFile(`${output}/${id}.json`, JSON.stringify({ id, duration, cues, ai_workflow: true, ai_verification: "real-model-responses", recorded_on: new Date().toISOString().slice(0, 10), source_revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim() }, null, 2))
    }
  }
}

test("live Aira: create, refine, preview and publish a Protocol", async ({ browser }) => {
  await scene(browser, "aira-protocol", async (page, step, poster) => {
    await page.goto(`${projectPath}/protocols`)
    await step(0, async () => {
      await page.getByRole("button", { name: "新建协议", exact: true }).click()
      await page.getByTestId("protocol-create-ai").click()
    })
    await step(1, async () => {
      await page.getByTestId("ai-protocol-name").locator("input").fill("Aira 生成：样本观察教学")
      await page.getByTestId("ai-protocol-requirements").locator("textarea").fill("创建中文样本观察教学协议，所有样本为虚构。包含目的、记录方法、提交前核对。仅设三个字段：必填字符串 sample_label（样本编号）；必填非负整数 observation_count（观察数量）；可选字符串 notes（备注，默认空字符串）。必填字段不能设置默认值，observation_count 必须加 ge=0。不要其他字段、步骤、检查点、计算或文件；直接使用 AIMD 内联类型。")
    })
    await step(2, async () => {
      const response = page.waitForResponse(r => r.url().endsWith("/editor/protocol_generate_draft"), { timeout: 300_000 })
      await page.getByTestId("ai-protocol-generate").click()
      const generated = await response
      expect(generated.ok(), await generated.text()).toBe(true)
      expect((await generated.json()).validation.status).toBe("valid")
      await expect(page.getByTestId("protocol-visual-editor")).toBeVisible({ timeout: 30_000 })
    })
    const assistant = page.getByTestId("editor-ai-edit-panel")
    await step(3, async () => {
      await expect(assistant).toBeVisible()
      await assistant.getByTestId("chat-input").locator("[contenteditable=true]").fill("请在协议末尾增加一句：提交前核对样本编号，避免重复录入。只修改说明文字，保持所有字段和类型不变。")
      const response = page.waitForResponse(r => r.url().endsWith("/editor/code_edit"), { timeout: 300_000 })
      await assistant.getByTestId("chat-submit").click()
      const edited = await response
      expect(edited.ok(), await edited.text()).toBe(true)
      expect((await edited.json()).changed_files.length).toBeGreaterThan(0)
    })
    await step(4, async () => {
      const review = page.getByTestId("editor-ai-review")
      if (await review.isVisible())
        await review.getByTestId("editor-ai-apply-all").click()
      await expect(page.getByTestId("protocol-validation")).toContainText("静态检查通过", { timeout: 30_000 })
      await expect(page.getByTestId("protocol-visual-editor")).toContainText("避免重复录入")
    })
    await step(5, async () => {
      await page.locator(".n-tabs-tab").getByText("填写预览", { exact: true }).click()
      await page.getByTestId("test-example-data").click()
      await expect(page.getByTestId("editor-example-form")).toBeVisible()
    })
    await poster()
    await step(6, async () => {
      await page.getByRole("button", { name: /^(Save|保存)$/ }).first().click()
      await expect(page.getByRole("dialog")).toContainText(projectName)
    })
    await step(7, async () => {
      const saved = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && r.request().method() === "POST", { timeout: 60_000 })
      await page.getByRole("dialog").getByRole("button", { name: "保存", exact: true }).click()
      expect((await saved).ok()).toBe(true)
      await page.getByRole("button", { name: "打开 Protocol", exact: true }).click()
      await expect(page).toHaveURL(/\/protocols\/protocol_/)
      await page.reload()
      await expect(page.getByRole("button", { name: "新增记录", exact: true }).first()).toBeVisible()
    })
  })
})

test("live Aira: explain, fill, review each field and persist a Record", async ({ browser }) => {
  await scene(browser, "aira-record", async (page, step, poster) => {
    await page.goto(`${formPath}/add`)
    const input = page.getByTestId("chat-input").locator("[contenteditable=true]")
    const field = (name: string) => page.locator(`.record-inline-content .aimd-protocol-recorder__content [data-rec-focus-key="var:${name}"]`)
    const inline = (name: string) => page.locator(`.record-inline-content [data-recorder-field="${name}"]`)
    const say = async (text: string) => {
      await input.fill(text)
      const response = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"), { timeout: 120_000 })
      await input.press("Enter")
      const reply = await response
      expect(reply.ok(), await reply.text()).toBe(true)
    }
    await step(0, async () => {
      await page.locator("[data-tab=ai-assistant]").click()
      await expect(input).toBeVisible()
    })
    await step(1, async () => {
      await say("样本编号和观察数量这两项分别应该填什么？请先解释，不要填写。")
      await expect(field("sample_label")).toHaveValue("")
      await expect(field("observation_count")).toHaveValue("")
    })
    await step(2, async () => {
      await say("把刚才那两项分别填为 DEMO-AI-001 和 12。")
      await expect(field("sample_label")).toHaveValue("DEMO-AI-001")
      await expect(field("observation_count")).toHaveValue("12")
    })
    await step(3, async () => {
      await say("把样本编号改为 DEMO-AI-002，观察数量改为 15。")
      await expect(inline("sample_label").locator(".recorder-suggestion")).toContainText("DEMO-AI-002")
      await expect(inline("observation_count").locator(".recorder-suggestion")).toContainText("15")
      await expect(field("observation_count")).toHaveValue("12")
    })
    await poster()
    await step(4, async () => {
      await inline("sample_label").getByRole("button", { name: "保留原值", exact: true }).click()
      await inline("observation_count").getByRole("button", { name: "替换", exact: true }).click()
      await expect(field("sample_label")).toHaveValue("DEMO-AI-001")
      await expect(field("observation_count")).toHaveValue("15")
    })
    await step(5, async () => {
      await field("observation_count").fill("14")
      await field("observation_count").blur()
      await field("notes").fill("虚构教学数据；展示人工核对与修改。")
      await page.getByTestId("record-save-draft").click()
      await page.reload()
      await expect(field("sample_label")).toHaveValue("DEMO-AI-001")
      await expect(field("observation_count")).toHaveValue("14")
    })
    await step(6, async () => {
      await page.getByRole("button", { name: "提交", exact: true }).click()
      await expect(page.getByRole("dialog")).toContainText(projectName)
    })
    await step(7, async () => {
      await page.getByRole("dialog").getByRole("button", { name: "提交 Record", exact: true }).click()
      await page.getByRole("dialog").getByRole("button", { name: "查看已保存记录", exact: true }).click()
      await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
      await page.reload()
      await expect(page.locator("#form-research_variable-observation_count input")).toHaveValue("14")
      await expect(page.locator("#form-research_variable-sample_label input, #form-research_variable-sample_label textarea")).toHaveValue("DEMO-AI-001")
    })
  })
})

test("live Aira: propose analysis, compute, interpret sources and save method", async ({ browser }) => {
  await scene(browser, "aira-analysis", async (page, step, poster) => {
    await page.goto(`${analysisPath}/records`)
    await step(0, async () => {
      await page.getByTestId("analysis-filtered-trigger").click()
    })
    await step(1, async () => {
      await page.getByTestId("analysis-question").locator("textarea").fill("请按 group 分组，比较 measurement 的平均值、数量和范围，用柱状图展示。只做描述性统计，不做显著性检验或因果推断。")
      await page.getByTestId("analysis-ai-draft-consent").click()
    })
    await step(2, async () => {
      await page.getByTestId("analysis-ai-draft-generate").click()
      await expect(page.getByTestId("analysis-ai-adopt")).toBeVisible({ timeout: 100_000 })
    })
    await step(3, async () => {
      await page.getByTestId("analysis-ai-adopt").click()
      await expect(page.getByTestId("analysis-ai-adopted")).toBeVisible()
      await page.getByTestId("analysis-preview").click()
      await expect(page.getByTestId("analysis-preview-dialog")).toBeVisible()
    })
    let runId = ""
    await step(4, async () => {
      const done = page.waitForResponse(async r => r.request().method() === "GET" && /\/analyses\/[0-9a-f-]+$/.test(new URL(r.url()).pathname) && r.ok() && (await r.json()).status === "succeeded", { timeout: 45_000 })
      await page.getByTestId("analysis-confirm").click()
      const run = await (await done).json()
      runId = run.id
      expect(run.result.groups.map((g: any) => g.fields.measurement.mean).sort()).toEqual([12, 18])
      expect(run.result.counts.included).toBe(6)
      expect(run.ai_provenance).not.toEqual({})
      await expect(page.getByTestId("analysis-result-charts")).toBeVisible()
      await page.getByTestId("analysis-result-table").scrollIntoViewIfNeeded()
      await expect(page.getByTestId("analysis-result-table")).toBeInViewport()
    })
    await step(5, async () => {
      await page.getByTestId("analysis-ai-interpretation-consent").click()
      await page.getByTestId("analysis-ai-interpretation-generate").click()
      await expect(page.getByTestId("analysis-ai-metric").first()).toBeVisible({ timeout: 100_000 })
      await expect(page.getByTestId("analysis-ai-grounding-rejected")).toHaveCount(0)
    })
    await poster()
    await step(6, async () => {
      await page.getByTestId("analysis-save-pipeline").click()
      await page.getByTestId("analysis-method-title").locator("input").fill("演示：分组读数比较")
      await page.getByTestId("analysis-confirm-save-method").click()
      await expect(page.getByTestId("analysis-pipeline-item").filter({ hasText: "演示：分组读数比较" })).toBeVisible()
    })
    await step(7, async () => {
      await page.reload()
      await page.getByTestId("analysis-result-table").scrollIntoViewIfNeeded()
      await expect(page.getByTestId("analysis-result-table")).toBeInViewport()
      await expect(page.getByTestId("analysis-ai-metric").first()).toBeVisible()
      expect(page.url()).toContain(runId)
    })
  })
})
