import { mkdir, readFile, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

const root = new URL("../", import.meta.url)
const { zipSync, strToU8 } = createRequire(new URL("apps/web/package.json", root))("fflate")
const out = new URL("docs/public/demos/examples/", root)
await mkdir(out, { recursive: true })
const aimd = await readFile(new URL("packages/components/src/monaco-editor/templates/first-record-zh.aimd", root), "utf8")
const toml = "[airalogy_protocol]\nid = \"demo_first_record\"\nname = \"演示：样本观察（虚构数据）\"\nversion = \"0.1.0\"\n"
const files = {
  "protocol.aimd": aimd,
  "protocol.toml": toml,
  "records-template.csv": "\uFEFFvar.sample_label,var.observation_count,var.notes\r\n",
  "records-invalid.csv": "\uFEFFvar.sample_label,var.observation_count,var.notes\r\nDEMO-101,#REF!,故意错误的虚构示例\r\nDEMO-102,12,虚构演示数据\r\n",
  "records-corrected.csv": "\uFEFFvar.sample_label,var.observation_count,var.notes\r\nDEMO-101,0,虚构演示数据\r\nDEMO-102,12,虚构演示数据\r\n",
  "meeting-note.aimd": "# 演示：样品观察讨论\n\n> 虚构数据，仅供入门演示。\n\n## 观察\nDEMO-001 的观察数量为 12。\n\n## 决定及依据\n先核对录入值，再开始下一轮观察。\n\n## 下一步\n整理观察表，准备下一次讨论。\n",
}
await Promise.all(Object.entries(files).map(([name, text]) => writeFile(new URL(name, out), text)))
const archive = zipSync({ "protocol.aimd": strToU8(aimd), "protocol.toml": strToU8(toml) }, { level: 9, mtime: new Date("2020-01-01T00:00:00Z") })
await writeFile(new URL("first-record-protocol.zip", out), archive)
console.log(`Learning examples: ${fileURLToPath(out)}`)

const analysisAimd = "# 虚构样本读数\n\n仅供软件教学，不构成科研结论。\n\n样本编号：{{var|sample_id: str}}\n\n分组：{{var|group: str}}\n\n读数：{{var|measurement: float, ge=0}}\n"
const analysisToml = "[airalogy_protocol]\nid=\"aira_analysis\"\nname=\"Aira 分析演示\"\nversion=\"0.1.0\"\n"
await writeFile(new URL("analysis-protocol.zip", out), zipSync({ "protocol.aimd": strToU8(analysisAimd), "protocol.toml": strToU8(analysisToml) }, { level: 9, mtime: new Date("2020-01-01T00:00:00Z") }))
await writeFile(new URL("analysis-records.csv", out), `\uFEFFvar.sample_id,var.group,var.measurement\r\n${[10, 12, 14, 16, 18, 20].map((value, index) => `DEMO-${index + 1},${index < 3 ? "A" : "B"},${value}\r\n`).join("")}`)
