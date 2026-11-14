/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

// Load the actual pure archive parser without initializing browser stores or UI providers.
const source = readFileSync(new URL("../../../packages/components/src/monaco-editor/composables/useFileUpload.ts", import.meta.url), "utf8")
const constants = readFileSync(new URL("../../../packages/shared/src/constants/protocol.ts", import.meta.url), "utf8")
const pure = source.slice(0, source.indexOf("function buildFilePath")).replace(/^import .*\n/gm, "")
const dependencies = `${constants}\nlet sequence = 0; const nanoid = () => String(++sequence); const FILE_TYPES = { text: [".aimd", ".toml", ".py"] }; const arrayBufferToString = data => new TextDecoder().decode(data);`
const compiled = ts.transpileModule(`${dependencies}\n${pure}`, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { createFileStructure, getRootPath, DEFAULT_FILE_ID_MAP } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)
const text = value => new TextEncoder().encode(value)

test("root-level Protocol files retain contents and stable field-file IDs", () => {
  const result = createFileStructure({ "protocol.aimd": text("# Synthetic"), "protocol.toml": text("[airalogy_protocol]") })
  assert.equal(result.rootPath, "")
  assert.deepEqual(result.fileStructure.map(file => [file.name, file.id, file.content]), [
    ["protocol.aimd", DEFAULT_FILE_ID_MAP.protocol, "# Synthetic"],
    ["protocol.toml", DEFAULT_FILE_ID_MAP.toml_config, "[airalogy_protocol]"],
  ])
})

test("a wrapped Protocol archive retains the common directory and its files", () => {
  const result = createFileStructure({ "protocol/": new Uint8Array(), "protocol/protocol.aimd": text("# Wrapped"), "protocol/model.py": text("class VarModel: pass") })
  assert.equal(result.rootPath, "protocol")
  assert.equal(result.fileStructure.length, 1)
  assert.deepEqual(result.fileStructure[0].children.map(file => file.id), [DEFAULT_FILE_ID_MAP.protocol, DEFAULT_FILE_ID_MAP.model])
})

test("mixed root files and binary assets do not turn the asset folder into the protocol root", () => {
  const bytes = new Uint8Array([0, 255, 1])
  const result = createFileStructure({ "protocol.aimd": text("# Mixed"), "assets/image.png": bytes, "__MACOSX/ignored": bytes, ".DS_Store": bytes })
  assert.equal(result.rootPath, "")
  assert.deepEqual(result.fileStructure.map(item => item.name), ["protocol.aimd", "assets"])
  assert.equal(result.fileStructure[0].id, DEFAULT_FILE_ID_MAP.protocol)
  assert.deepEqual(result.fileStructure[1].children[0].content, bytes)
  assert.equal(getRootPath(["first/a.py", "second/b.py"]), "")
  assert.equal(getRootPath([]), "")
})
