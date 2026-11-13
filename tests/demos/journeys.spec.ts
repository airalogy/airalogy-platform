import type { Browser, BrowserContext, Locator, Page } from "@playwright/test"
import { Buffer } from "node:buffer"
import { execFileSync } from "node:child_process"
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "../e2e/specs/fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../apps/web/package.json", import.meta.url))("fflate")
const root = process.cwd()
const api = process.env.DEMO_API_URL || "http://127.0.0.1:4100"
const web = process.env.DEMO_WEB_URL || "http://127.0.0.1:3100"
const recording = process.env.DEMO_RECORD === "1"
const output = `${root}/tests/e2e/.runtime/learning-demos/capture`
let state: Awaited<ReturnType<BrowserContext["storageState"]>>
let projectId: string
let projectPath: string
let protocolPath: string
let csvPath: string
let csvProtocolId: string
let headers: { "Auth-Token": string }
let projectName: string
const localTargets: Record<string, string> = {}
const welcomeScript = JSON.parse(await readFile(`${root}/docs/demos/narration.json`, "utf8")).lessons.welcome as { source_zh: string, en: string }[]

test.beforeAll(async ({ browser, request }) => {
  const fixtures = await loadFixtures()
  const context = await browser.newContext({ baseURL: web })
  const page = await context.newPage()
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill("dev.owner@airalogy.dev")
  await page.getByTestId("login-password").locator("input").fill("AiralogyDev123!")
  const login = page.waitForResponse(r => r.url().endsWith("/api/signin_by_email"))
  await page.getByTestId("login-submit").click()
  headers = { "Auth-Token": (await (await login).json()).token }
  await expect(page).not.toHaveURL(/\/login/)
  const uid = `demo_${Date.now().toString(36)}`
  projectName = "入门演示 · 虚构数据"
  const created = await request.post(`${api}/projects`, { headers, data: { lab_id: fixtures.lab.id, name: projectName, uid, type: 1, description: "仅供本地入门演示与验收，全部为虚构数据。" } })
  expect(created.ok(), await created.text()).toBeTruthy()
  const project = await created.json()
  expect(project.id).toBeTruthy()
  projectId = project.id
  projectPath = `/labs/${fixtures.lab.uid}/projects/${uid}`
  const aimd = await readFile(`${root}/docs/public/demos/examples/protocol.aimd`, "utf8")
  for (const [slug, name] of [["demo_first_record", "演示：样本观察（虚构数据）"], ["demo_csv", "演示：表格导入（虚构数据）"]]) {
    const archive = zipSync({ "protocol.aimd": strToU8(aimd), "protocol.toml": strToU8(`[airalogy_protocol]\nid="${slug}"\nname="${name}"\nversion="0.1.0"\n`) })
    const response = await request.post(`${api}/protocols`, { headers, multipart: { project_id: project.id, file: { name: "demo.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
    expect(response.ok(), await response.text()).toBeTruthy()
    const protocol = (await response.json()).data
    if (slug === "demo_csv") {
      csvPath = `${projectPath}/protocols/${slug}`
      csvProtocolId = protocol.id
    }
    else { protocolPath = `${projectPath}/protocols/${slug}` }
  }
  // Setup creates a dedicated synthetic workspace and example Protocols only.
  // The demonstrated documents, Protocol, Records, revisions and import are written through the UI below.
  const visited = page.waitForResponse(response => response.url().endsWith("/api/workspace/project-visits") && response.request().method() === "POST")
  await page.goto(`${projectPath}/protocols`)
  expect((await visited).ok()).toBeTruthy()
  await expect(page.getByRole("link", { name: "演示：样本观察（虚构数据）", exact: true })).toBeVisible()
  state = await context.storageState()
  await context.close()
  await mkdir(output, { recursive: true })
})

test.afterAll(async () => {
  await writeFile(`${output}/local-targets.json`, JSON.stringify({ project: `${web}${projectPath}/protocols`, ...localTargets }, null, 2))
})

type Cue = (zh: string, en: string, action?: () => Promise<void>, seconds?: number) => Promise<void>
async function scene(browser: Browser, id: string, body: (page: Page, cue: Cue, poster: () => Promise<void>) => Promise<void>) {
  const context = await browser.newContext({ baseURL: web, storageState: state, viewport: { width: 1440, height: 1000 }, ...(recording ? { recordVideo: { dir: `${output}/raw`, size: { width: 1440, height: 1000 } } } : {}) })
  await context.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
  if (recording && id === "welcome") {
    // Recording annotation only: follows real pointer events, never changes
    // application controls or data. Browser video otherwise omits the cursor.
    await context.addInitScript(() => {
      window.addEventListener("DOMContentLoaded", () => {
        const cursor = document.createElement("div")
        cursor.setAttribute("aria-hidden", "true")
        cursor.style.cssText = "position:fixed;display:none;width:18px;height:18px;border:2px solid #fff;border-radius:50%;background:#1677ffbb;box-shadow:0 0 0 2px #1677ff;pointer-events:none;z-index:2147483647"
        document.body.append(cursor)
        window.addEventListener("pointermove", (event) => {
          cursor.style.display = "block"
          cursor.style.left = `${event.clientX - 9}px`
          cursor.style.top = `${event.clientY - 9}px`
        })
        window.addEventListener("pointerdown", () => {
          cursor.animate([{ transform: "scale(1)" }, { transform: "scale(2.1)", opacity: 0.4 }, { transform: "scale(1)" }], { duration: 550 })
        })
      })
    })
  }
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  const start = Date.now()
  const cues: { at: number, zh: string, en: string }[] = []
  const cue: Cue = async (zh, en, action, seconds = 6) => {
    cues.push({ at: (Date.now() - start) / 1000, zh, en })
    if (action)
      await action()
    if (recording)
      await page.waitForTimeout(seconds * 1000)
  }
  const poster = async () => {
    await page.screenshot({ path: `${output}/${id}.png`, animations: "disabled",
    })
  }
  let succeeded = false
  try {
    await body(page, cue, poster)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    localTargets[id] = page.url()
    succeeded = true
  }
  finally {
    const duration = (Date.now() - start) / 1000
    if (!succeeded) {
      await page.screenshot({ path: test.info().outputPath(`${id}-failure.png`), fullPage: true })
      await writeFile(test.info().outputPath(`${id}-text.txt`), (await page.locator("body").textContent()) || "")
    }
    await context.close()
    if (recording && succeeded) {
      await copyFile(await page.video()!.path(), `${output}/${id}.webm`)
      await writeFile(`${output}/${id}.json`, JSON.stringify({ id, duration, cues, recorded_on: new Date().toISOString().slice(0, 10), source_revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim() }, null, 2))
    }
  }
}

// Recordings are optional; the same tasks run at normal test speed in demos:check.
test("first visit: use the real Platform to save a Record and find other work", async ({ browser }) => {
  await scene(browser, "welcome", async (page, cue, poster) => {
    const visited: string[] = []
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame())
        visited.push(new URL(frame.url()).pathname)
    })
    const click = async (target: Locator) => {
      await expect(target).toBeVisible()
      await target.scrollIntoViewIfNeeded()
      const box = await target.boundingBox()
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2, { steps: recording ? 14 : 1 })
      if (recording)
        await page.waitForTimeout(350)
      await target.click({ delay: recording ? 120 : 0 })
    }
    const tab = (name: string) => page.locator(".n-tabs-tab").getByText(name, { exact: true }).first()
    const projectCard = () => page.locator(`[data-testid="home-project-card"][data-project-id="${projectId}"]`)
    const home = () => click(page.locator("header a[href=\"/home\"]").first())
    const project = () => click(page.getByRole("link", { name: projectName, exact: true }).first())
    const step = async (index: number, action?: () => Promise<void>, seconds = 5) => {
      const line = welcomeScript[index]
      await cue(line.source_zh, line.en, action, seconds)
      expect(new URL(page.url()).pathname).not.toMatch(/^\/docs(?:\/|$)/)
    }
    await page.goto("/home")
    await expect(projectCard()).toBeVisible()
    await step(0, async () => {
      if (process.env.DEMO_AI_OVERVIEW === "1")
        await expect(page.getByRole("button", { name: "向 Aira 提问", exact: true })).toBeVisible()
    })
    await step(1, async () => {
      await click(projectCard().getByTestId("home-open-project"))
      await click(tab("协议"))
      await expect(page).toHaveURL(`${web}${projectPath}/protocols`)
    })
    await poster()
    await step(2, async () => {
      await click(page.getByRole("link", { name: "演示：样本观察（虚构数据）", exact: true }))
      await expect(page).toHaveURL(`${web}${protocolPath}/protocol`)
    })
    await step(3, async () => {
      await click(page.getByRole("button", { name: "新增记录", exact: true }).first())
    })
    const sample = page.locator("#form-research_variable-sample_label textarea, #form-research_variable-sample_label input")
    const count = page.locator("#form-research_variable-observation_count input")
    await step(4, async () => {
      await click(sample)
      await sample.pressSequentially("DEMO-START", { delay: recording ? 100 : 0 })
      await click(count)
      await count.fill("12")
      await page.locator("#form-research_variable-notes textarea, #form-research_variable-notes input").fill("首次使用演示：虚构数据")
      await count.blur()
    })
    await step(5, async () => {
      await click(page.getByRole("button", { name: "提交", exact: true }))
      await expect(page.getByRole("dialog")).toContainText(projectName)
    })
    await step(6, async () => {
      await click(page.getByRole("dialog").getByRole("button", { name: "提交 Record", exact: true }))
      await click(page.getByRole("dialog").getByRole("button", { name: "查看已保存记录", exact: true }))
      await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
      await expect(sample).toHaveValue("DEMO-START")
    })
    await step(7, async () => {
      await page.reload()
      await expect(sample).toHaveValue("DEMO-START")
      await expect(count).toHaveValue("12")
    })
    await step(8, async () => {
      await project()
      await click(tab("文档"))
      await expect(page.getByTestId("research-documents-list")).toBeVisible()
    })
    await step(9, async () => {
      await click(page.getByTestId("new-research-document"))
      await click(page.getByTestId("choose-template-builtin:meeting"))
      await expect(page.getByTestId("template-preview")).toBeVisible()
      await expect(page.getByRole("dialog")).toContainText(projectName)
    }, 7)
    await step(10, async () => {
      await click(page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }))
      await click(tab("协议"))
      await click(page.getByRole("link", { name: "演示：表格导入（虚构数据）", exact: true }))
      await click(tab("记录"))
      await click(page.getByRole("button", { name: "批量上传", exact: true }))
    })
    await step(11, async () => {
      const downloaded = page.waitForEvent("download")
      await click(page.getByRole("dialog").getByRole("button", { name: "下载 CSV 模板", exact: true }))
      expect((await downloaded).suggestedFilename()).toMatch(/\.csv$/)
      await click(page.getByRole("dialog").getByText("查看字段说明", { exact: true }))
    }, 7)
    await step(12, async () => {
      await click(page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }))
      await project()
      await click(tab("协议"))
      await click(page.getByRole("button", { name: "新建协议", exact: true }))
      await expect(page.getByTestId("protocol-create-template")).toBeVisible()
      if (process.env.DEMO_AI_OVERVIEW === "1")
        await expect(page.getByTestId("protocol-create-ai")).toBeVisible()
    })
    await step(13, async () => {
      await page.keyboard.press("Escape")
      await expect(page.getByRole("dialog")).toHaveCount(0)
      await home()
      await expect(projectCard()).toBeVisible()
      await click(projectCard().getByTestId("home-resume-project"))
      await expect(page).toHaveURL(new RegExp(`${projectPath}/`))
    })
    expect(visited.length).toBeGreaterThan(8)
    expect(visited.every(path => !path.startsWith("/docs/"))).toBe(true)
  })
})

test("first Record: submit, reload, correct, preserve original", async ({ browser }) => {
  await scene(browser, "first-record", async (page, cue, poster) => {
    await page.goto(`${protocolPath}/protocol`)
    await cue("已有 Protocol 时，从项目中打开它。先阅读说明并确认版本。", "Open the existing Protocol in your project. Read its instructions and version.")
    await cue("选择‘新增记录’，进入可填写的表单。", "Choose Add Record to open the form.", async () => {
      await page.getByRole("button", { name: "新增记录", exact: true,
      }).first().click()
    })
    const sample = page.locator("#form-research_variable-sample_label textarea, #form-research_variable-sample_label input")
    const count = page.locator("#form-research_variable-observation_count input")
    await cue("填写样本 DEMO-001、数量 12。这些值仅用于演示。", "Enter sample DEMO-001 and count 12. These are synthetic values.", async () => {
      await sample.fill("DEMO-001")
      await count.fill("12")
      await page.locator("#form-research_variable-notes textarea, #form-research_variable-notes input").fill("虚构演示数据")
      await count.blur()
    })
    await poster()
    await cue("必填项应完成。草稿保存在当前设备；提交才会创建正式 Record。", "Complete required fields. A draft is on this device; submission creates the Record.")
    await cue("点击提交，核对项目和 Protocol 版本，再确认。", "Submit, check the project and Protocol version, then confirm.", async () => {
      await page.getByRole("button", { name: "提交", exact: true }).click()
      await expect(page.getByRole("dialog")).toContainText(projectName)
    })
    await cue("提交成功后，打开‘查看已保存记录’确认结果。", "After success, open View saved Record to check the result.", async () => {
      await page.getByRole("dialog").getByRole("button", { name: "提交 Record", exact: true }).click()
      await page.getByRole("dialog").getByRole("button", { name: "查看已保存记录", exact: true }).click()
      await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
    })
    const original = page.url()
    await cue("刷新页面，刚才的值仍在，确认已保存到平台。", "Reload: the values remain, confirming platform persistence.", async () => {
      await page.reload()
      await expect(count).toHaveValue("12")
    })
    await cue("发现录入错误时使用‘修订’，填写更正原因。", "Use Revise for a correction and provide its reason.", async () => {
      await page.getByRole("button", { name: "修订", exact: true }).click()
      await count.fill("13")
      await page.getByPlaceholder("填写本次修订原因（必填）").fill("修正演示中的录入错误；仍为虚构数据。")
    })
    await cue("提交修订，新的记录版本保留更正值。", "Submit the revision. The new revision contains the corrected value.", async () => {
      await page.getByRole("button", { name: "提交", exact: true }).click()
      await page.getByRole("dialog").getByRole("button", { name: "提交修订", exact: true }).click()
      await page.getByRole("dialog").getByRole("button", { name: "查看已保存记录", exact: true }).click()
      await expect(count).toHaveValue("13")
    })
    await cue("原修订仍保留 12。数据更正有历史，可以追溯。", "The original still contains 12. Corrections preserve history.", async () => {
      await page.goto(original)
      await expect(count).toHaveValue("12")
    })
  })
})

test("first document: choose a template, write and find the saved document", async ({ browser }) => {
  await scene(browser, "first-document", async (page, cue, poster) => {
    await page.goto("/research-documents")
    await cue("想记下会议或观察时，进入‘我的文档’，不需要先建立 Protocol。", "For a meeting or observation, open My documents. No Protocol is required.")
    await cue("新建文档，选择‘会议记录’模板，查看它的结构。", "Create a document, select Meeting notes and preview its structure.", async () => {
      await page.getByTestId("new-research-document").click()
      await page.getByTestId("choose-template-builtin:meeting").click()
      await expect(page.getByTestId("template-preview")).toBeVisible()
      await page.getByTestId("new-document-title").locator("input").fill("演示：样品观察讨论")
    })
    await cue("确认保存到个人空间，仅自己可见，再创建。", "Confirm the personal destination, visible only to you, then create.", async () => {
      await page.getByTestId("create-document-confirm").click()
      await expect(page.getByTestId("research-document-editor")).toBeVisible()
    })
    const prose = page.locator(".ProseMirror[contenteditable=true]")
    await cue("在可视化编辑器直接写下观察、决定和下一步。", "Write observations, decisions and next steps directly in the visual editor.", async () => {
      for (const [heading, text] of [
        ["会议主题与参与者", "样品观察讨论；参与者：演示研究员（虚构）。"],
        ["议题与讨论", "虚构样本 DEMO-001 的观察数量为 12。"],
        ["决策及依据", "先核对录入值，再准备下一轮观察。"],
        ["下一步与负责人", "演示研究员整理观察表，供下次讨论。"],
      ]) {
        const headingNode = prose.getByRole("heading", { name: heading, exact: true })
        const bounds = await headingNode.boundingBox()
        await headingNode.click({ position: { x: bounds!.width - 4, y: bounds!.height / 2 } })
        await page.keyboard.press("Enter")
        await page.keyboard.insertText(text)
        await expect(headingNode).toBeVisible()
      }
      await expect(prose).toContainText("DEMO-001")
      await expect(page.getByTestId("document-save-state")).toHaveText("已保存")
    }, 8)
    await poster()
    await cue("等待‘已保存’。如需查看归属与共享范围，可展开保存位置。", "Wait for Saved. Expand the destination to check ownership and visibility.", async () => {
      await page.getByTestId("document-details-toggle").click()
      await expect(page.getByTestId("document-details")).toBeVisible()
    })
    const document = page.url()
    await cue("返回列表，用标题搜索，就能找回这份文档。", "Return to the list and search by title to find the document.", async () => {
      await page.getByTestId("document-back").click()
      const search = page.getByTestId("document-list-tools").getByRole("search")
      await search.getByRole("textbox").fill("演示：样品观察讨论")
      await search.getByRole("button", { name: "搜索", exact: true }).click()
      await expect(page.getByTestId("research-document-link").filter({ hasText: "演示：样品观察讨论" }).first()).toBeVisible()
    })
    await cue("重新打开，文字还在。团队共享内容请从项目或实验室入口新建。", "Reopen and verify persistence. Create shared work from its project or Lab entry.", async () => {
      await page.goto(document)
      await expect(prose).toContainText("DEMO-001")
    })
  })
})

test("first Protocol: edit a template, validate, preview, save", async ({ browser }) => {
  await scene(browser, "first-protocol", async (page, cue, poster) => {
    await page.goto(`${projectPath}/protocols`)
    await cue("准备新实验时，从项目的‘协议’进入‘新建协议’。", "For a new experiment, open New protocol in the project’s Protocols.", async () => {
      await page.getByRole("button", { name: "新建协议", exact: true,
      }).click()
    })
    await cue("选择‘从模板开始’，用入门模板建立可填写的结构。", "Start from a template to create a fillable structure.", async () => {
      await page.getByTestId("protocol-create-template").click()
      await page.getByTestId("template-name").locator("input").fill("演示：新实验观察方案")
    })
    await cue("名称清楚表达用途；模板创建后还可以编辑。", "Use a clear name. The template remains editable after creation.", async () => {
      await page.getByTestId("template-create-confirm").click()
      await expect(page.getByTestId("protocol-visual-editor")).toBeVisible()
    })
    const prose = page.getByTestId("protocol-visual-editor").locator(".ProseMirror[contenteditable=true]")
    await cue("在可视化界面补充步骤。字段的 ID、类型和约束决定后续表单。", "Edit the instructions visually. Field IDs, types and constraints define the form.", async () => {
      await prose.press("ControlOrMeta+End")
      await prose.press("Enter")
      await page.keyboard.insertText("演示补充步骤：提交前核对样本标识和观察数量。本方案仅使用虚构数据。")
    }, 8)
    await cue("等待语法检查通过；有错误应先修正。结构通过不代表实验方法已验证。", "Wait for syntax validation. Resolve errors first; valid structure is not scientific validation.", async () => {
      await expect(page.getByTestId("protocol-validation")).toContainText("静态检查通过")
    }, 7)
    await cue("右侧切到‘填写预览’，用示例数据测试。测试值不会创建 Record。", "Open Form preview and test example data. Preview values do not create Records.", async () => {
      await page.locator(".n-tabs-tab").getByText("填写预览", { exact: true }).click()
      await page.getByTestId("test-example-data").click()
      await expect(page.getByTestId("editor-example-form")).toBeVisible()
    })
    await poster()
    await cue("检查表单效果后保存，确认协议的归属位置和版本。", "After checking the form, save and verify the destination and version.", async () => {
      await page.getByRole("button", { name: /^(Save|保存)$/ }).first().click()
      await expect(page.getByRole("dialog")).toContainText(projectName)
    })
    await cue("确认保存。新方案进入项目，之后可反复填写 Record。", "Confirm the save. The Protocol is available in the project for future Records.", async () => {
      const saved = page.waitForResponse(r => new URL(r.url()).pathname === "/api/protocols" && r.request().method() === "POST")
      await page.getByRole("dialog").getByRole("button", { name: "保存", exact: true }).click()
      expect((await saved).ok()).toBeTruthy()
      await page.getByRole("button", { name: "打开 Protocol", exact: true }).click()
      await expect(page).toHaveURL(/\/protocols\/protocol_/)
    })
    await cue("完成后阅读刚保存的方案；真正采集数据时选择‘新增记录’。", "Read the saved Protocol. Choose Add Record when collecting observations.")
  })
})

test("first CSV: download template, correct errors and explicitly import", async ({ browser }) => {
  await scene(browser, "first-import", async (page, cue, poster) => {
    await page.goto(`${csvPath}/records`)
    await cue("已有表格时，打开匹配 Protocol 的 Records，选择‘批量上传’。", "For existing data, open the matching Protocol’s Records and choose Bulk upload.", async () => {
      await page.getByRole("button", { name: "批量上传", exact: true,
      }).click()
    })
    const dialog = page.getByRole("dialog")
    const input = dialog.locator("input[type=file]")
    await cue("先下载该版本的 CSV 模板，保留标准表头，用 UTF-8 CSV 整理数据。", "Download this version’s CSV template. Keep its standard headers and prepare UTF-8 CSV.", async () => {
      const download = page.waitForEvent("download")
      await dialog.getByRole("button", { name: "下载 CSV 模板", exact: true }).click()
      const stream = await (await download).createReadStream()
      const chunks: Buffer[] = []
      for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
      expect(Buffer.concat(chunks).toString("utf8")).toBe(await readFile(`${root}/docs/public/demos/examples/records-template.csv`, "utf8"))
      await dialog.getByText("查看字段说明", { exact: true }).click()
    }, 8)
    await cue("先演示错误文件：数量包含 #REF!。选择文件并点击预检。", "First try the invalid example: its count contains #REF!. Select it and validate.", async () => {
      await input.setInputFiles(`${root}/docs/public/demos/examples/records-invalid.csv`)
      await dialog.getByRole("button", { name: "预检文件", exact: true }).click()
      await expect(dialog).toContainText("请修正后重新预检（尚未导入）")
      await expect(dialog).toContainText("存在表格错误值")
    })
    const count = async () => (await (await page.request.get(`${api}/protocols/${csvProtocolId}/records`, { headers })).json()).total_count
    expect(await count()).toBe(0)
    await cue("错误会指出字段和位置；校验失败时不会创建任何 Record。", "Errors identify the field and location. Invalid input creates no Records.")
    await cue("点击‘更换文件’，选择修正后的示例；修正源数据时不要猜测缺失值。", "Replace the file with the corrected example. Do not guess missing values in real data.", async () => {
      const chooser = page.waitForEvent("filechooser")
      await page.getByTestId("replace-import-file").click()
      await (await chooser).setFiles(`${root}/docs/public/demos/examples/records-corrected.csv`)
      await dialog.getByRole("button", { name: "预检文件", exact: true }).click()
      await expect(dialog).toContainText("预检通过（尚未导入）")
    })
    expect(await count()).toBe(0)
    if (!recording) {
      await dialog.getByRole("checkbox").check()
      const replacement = page.waitForEvent("filechooser")
      await page.getByTestId("replace-import-file").click()
      await (await replacement).setFiles([])
      await expect(dialog.getByRole("button", { name: "确认导入", exact: true })).toBeDisabled()
      await input.setInputFiles(`${root}/docs/public/demos/examples/records-corrected.csv`)
      await dialog.getByRole("button", { name: "预检文件", exact: true }).click()
      await expect(dialog).toContainText("预检通过（尚未导入）")
      await expect(dialog.getByRole("checkbox")).not.toBeChecked()
      expect(await count()).toBe(0)
    }
    await poster()
    await cue("预检通过仍未写入。核对条数、Protocol 和版本，再勾选确认。", "A successful preview has not written data. Check the count, Protocol and version, then acknowledge.", async () => {
      await dialog.getByRole("checkbox").check()
    })
    await cue("点击‘确认导入’，提交这两条虚构数据。", "Confirm the import to save these two synthetic rows.", async () => {
      await dialog.getByRole("button", { name: "确认导入", exact: true }).click()
      await expect(dialog).toHaveCount(0)
      await expect(page.locator(".protocol-stats-card .stat-item").filter({ hasText: "记录" })).toContainText("2")
      await expect(page.getByRole("button", { name: "新增记录", exact: true })).toBeVisible()
    })
    await cue("刷新列表核对结果：DEMO-101 为 0，DEMO-102 为 12。成功后不要重复上传。", "Reload and verify: DEMO-101 is 0; DEMO-102 is 12. Do not upload again after success.", async () => {
      await page.reload()
      await expect(page.getByText("DEMO-101", { exact: true })).toBeVisible()
      await expect(page.getByText("DEMO-102", { exact: true })).toBeVisible()
      expect(await count()).toBe(2)
    }, 8)
  })
})
