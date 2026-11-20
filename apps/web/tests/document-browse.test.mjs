/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/documentBrowse.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { localDocumentDate, documentDateInstant, documentBrowseQuery } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)

test("record dates follow the viewer's calendar and preserve the local time when changed", () => {
  const previous = process.env.TZ
  try {
    process.env.TZ = "Asia/Shanghai"
    assert.equal(localDocumentDate("2026-11-06T16:00:00Z"), "2026-11-07")
    assert.equal(documentDateInstant("2026-10-31", "2026-11-06T16:01:02Z"), "2026-10-30T16:01:02.000Z")
    assert.equal(documentDateInstant("2026-02-30"), undefined)
    assert.equal(documentDateInstant(""), undefined)
    process.env.TZ = "America/New_York"
    assert.equal(documentDateInstant("2026-03-09", "2026-03-07T17:00:00Z"), "2026-03-09T16:00:00.000Z")
  }
  finally {
    if (previous === undefined) {
      delete process.env.TZ
    }
    else {
      process.env.TZ = previous
    }
  }
})

test("returning from editing preserves browsing filters but never forwards arbitrary redirects", () => {
  assert.deepEqual(documentBrowseQuery({ q: "Synthetic", from: "2026-11-07", page: "2", read: "doc", redirect: "https://invalid.test", project_id: "untrusted" }), { q: "Synthetic", from: "2026-11-07", page: "2", read: "doc" })
})

async function loadUtility(name) {
  const input = readFileSync(new URL(`../src/utils/${name}.ts`, import.meta.url), "utf8")
  const output = ts.transpileModule(input, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`)
}

test("document routes retain their workspace location instead of matching research tasks", async () => {
  const { workspaceDestination } = await loadUtility("workspaceNavigation")
  for (const name of ["research-documents", "research-document-detail"])
    assert.equal(workspaceDestination(name), "research-documents")
  assert.equal(workspaceDestination("research-tasks"), "research-tasks")
  assert.equal(workspaceDestination("project-documents"), "project-dashboard")
  assert.equal(workspaceDestination("projects-research-overview"), "project-dashboard")
  assert.equal(workspaceDestination("lab-research-overview"), "labs-my")
  assert.equal(workspaceDestination("project-records"), "profile-records")
  assert.equal(workspaceDestination("unrecognized"), null)
})

test("recent templates retain bounded identifiers without cached content or duplicate references", async () => {
  const { recentTemplateIds } = await loadUtility("documentTemplateRecents")
  const id = "10000000-0000-4000-8000-000000000001"
  assert.deepEqual(recentTemplateIds(JSON.stringify([id, id, { title: "Private content" }, "not-an-id", null])), [id])
  assert.deepEqual(recentTemplateIds("broken"), [])
  assert.deepEqual(recentTemplateIds("{\"title\":\"not an array\"}"), [])
  assert.equal(recentTemplateIds(JSON.stringify(Array.from({ length: 8 }, (_, i) => `10000000-0000-4000-8000-00000000000${i}`))).length, 4)
})
