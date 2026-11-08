/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/projectWorkspace.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { projectVisitForRoute, mergeProjectWorkspaces } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)
const params = { labUid: "synthetic_lab", projectUid: "synthetic_project", protocolUid: "test_protocol" }
const route = (name, query = {}, extra = {}) => ({ name, params: { ...params, ...extra }, query })

test("history includes only known destinations and never copies form values or arbitrary redirects", () => {
  assert.deepEqual(projectVisitForRoute(route("project-protocols", { secret: "private search" })), { kind: "project", lab_uid: params.labUid, project_uid: params.projectUid, section: "protocols" })
  assert.deepEqual(projectVisitForRoute(route("add-protocol-record", { draft: "private-content", redirect: "https://invalid.test" })), { kind: "recording", lab_uid: params.labUid, project_uid: params.projectUid, protocol_uid: params.protocolUid })
  assert.equal(projectVisitForRoute(route("home")), null)
  assert.equal(projectVisitForRoute({ name: "research-documents", params: {}, query: {} }), null)
  assert.equal(projectVisitForRoute(route("protocol-record-report", {}, { recordVersion: "NaN" })), null)
})

test("document, versioned Record and editor navigation preserve exact authorized identifiers", () => {
  assert.equal(projectVisitForRoute(route("protocol-record-report", {}, { recordId: "record-id", recordVersion: "2" })).record_version, 2)
  assert.equal(projectVisitForRoute(route("protocol-editor", {}, { protocolVersion: "1.1.0" })).protocol_version, "1.1.0")
  assert.equal(projectVisitForRoute(route("project-documents", { read: "doc-id" })).resource_id, "doc-id")
  assert.deepEqual(projectVisitForRoute({ name: "research-documents", params: {}, query: { project_id: "p", tab: "materials" } }), { kind: "project", project_id: "p", section: "materials" })
})

const project = (id, time, target, pinned_id = null) => ({ id, visited_at: time ? new Date(time).toISOString() : null, pinned_id, target })
const draft = (protocolId, timestamp, version = "1.0.0") => ({ protocolId, draftId: `draft-${protocolId}`, timestamp, scope: { version }, data: { var: { synthetic: true } } })
const target = protocol_id => ({ protocol_id, protocol_version: "1.0.0", kind: "recording" })

test("pins retain their order and visits use actor time rather than project modification dates", () => {
  const result = mergeProjectWorkspaces([project("pin", 1, null, 7), project("old", 10), project("new", 20)], [], [])
  assert.deepEqual(result.map(x => x.id), ["pin", "new", "old"])
})

test("only authorized matching device drafts replace older visits; latest project document wins over old draft", () => {
  const recent = [project("a", 50, { kind: "document", title: "Synthetic note" }), project("b", 10, null, 9)]
  const destinations = [project("a", null, target("one")), project("b", null, target("two"))]
  const result = mergeProjectWorkspaces(recent, destinations, [draft("one", 40), draft("two", 60), draft("revoked", 100)])
  assert.equal(result.length, 2)
  assert.equal(result[0].id, "b")
  assert.equal(result[0].pinned_id, 9)
  assert.equal(result[0].draft.draftId, "draft-two")
  assert.equal(result[1].target.kind, "document")
  assert.equal(result[1].draft, undefined)
})

test("multiple local drafts in one project collapse to its newest compatible draft", () => {
  const result = mergeProjectWorkspaces([], [project("a", null, target("one")), project("a", null, target("two"))], [draft("one", 50), draft("two", 60)])
  assert.equal(result.length, 1)
  assert.equal(result[0].draft.protocolId, "two")
  assert.deepEqual(mergeProjectWorkspaces([], [project("a", null, target("one"))], [draft("one", 100, "old-version")]), [])
})

test("reloading the same recording page still offers its existing device draft", () => {
  const result = mergeProjectWorkspaces([project("a", 100, target("one"))], [project("a", null, target("one"))], [draft("one", 50)])
  assert.equal(result[0].draft.draftId, "draft-one")
  assert.equal(result[0].lastUsed, 100)
})
