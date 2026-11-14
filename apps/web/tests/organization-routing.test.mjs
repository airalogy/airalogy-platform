/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"
import { createMemoryHistory, createRouter } from "vue-router"

async function sourceModule(path) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8")
  // Exercise production route definitions without loading page components in Node.
  const compiled = ts.transpileModule(source.replace(/\(\) => import\([^)]*\)/g, "{}"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)
}
const { organizationRoutes, installOrganizationRouting, canonicalOrganizationPath, configureOrganizationRouting } = await sourceModule("../src/router/organization-routing.ts")
const modules = await Promise.all(["lab-info", "labs", "groups", "project-info", "projects", "protocol-info", "protocol-record"].map(name => sourceModule(`../src/router/routes/modules/${name}.ts`)))
const routes = modules.flatMap(module => Object.values(module))
const single = { single: true, uid: "synthetic_org" }
const multi = { single: false }
function makeRouter(scope) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    ...organizationRoutes(routes, scope),
    { path: "/login", name: "login", component: {} },
    { path: "/404/lab", name: "lab-not-found", component: {}, meta: { constant: true } },
    { path: "/:pathMatch(.*)*", name: "fallback", component: {} },
  ] })
  const browserNavigate = router.push
  installOrganizationRouting(router, scope)
  return Object.assign(router, { browserNavigate })
}
const cases = [
  ["project-overview", "/projects/project/overview", {}],
  ["project-documents", "/projects/project/documents", {}],
  ["project-work", "/projects/project/work", {}],
  ["project-analysis", "/projects/project/analysis", {}],
  ["project-workflows", "/projects/project/workflows", {}],
  ["protocol-detail", "/projects/project/protocols/protocol/protocol", { protocolUid: "protocol" }],
  ["add-protocol-record", "/projects/project/protocols/protocol/add", { protocolUid: "protocol" }],
  ["add-protocol-record-from-workflow", "/projects/project/protocols/protocol/add/chain", { protocolUid: "protocol" }],
  ["protocol-record-report", "/projects/project/protocols/protocol/v1.2.3/record/record/v2", { protocolUid: "protocol", protocolVersion: "1.2.3", recordId: "record", recordVersion: "2" }],
  ["protocol-editor", "/projects/project/protocol/editor/v1.2.3", { protocolUid: "protocol", protocolVersion: "1.2.3" }],
  ["lab-members", "/organization/members", {}],
  ["lab-settings", "/organization/settings", {}],
  ["lab-knowledge", "/organization/knowledge", {}],
  ["lab-resources", "/organization/resources/gateways", { section: "gateways" }],
  ["lab-group-members", "/organization/groups/123/members", { groupId: "123" }],
]
for (const scope of [single, multi]) {
  test(`${scope.single ? "single" : "multi"}: named links, direct loads, legacy links and reloads preserve assets and navigation state`, async () => {
    const router = makeRouter(scope)
    for (const [name, short, extra] of cases) {
      const suffix = short.startsWith("/organization") ? short.slice("/organization".length) : short
      const long = `/orgs/synthetic_org${suffix}`
      const canonical = scope.single ? short : long
      const params = { labUid: single.uid, ...extra, ...(short.startsWith("/projects/") ? { projectUid: "project" } : {}) }
      const target = { name, params, query: { search: "中文", tag: ["a", "b"] }, hash: "#field" }
      const resolved = router.resolve(target)
      assert.equal(resolved.path, canonical)
      assert.match(resolved.href, /#field$/)
      await router.push(target)
      assert.equal(router.currentRoute.value.path, canonical)
      assert.equal(router.currentRoute.value.params.labUid, single.uid)
      await router.push({ path: long.replace("/orgs/", "/labs/"), query: target.query, hash: target.hash })
      assert.equal(router.currentRoute.value.fullPath, resolved.fullPath)
      await router.replace(canonical)
      assert.equal(router.currentRoute.value.name, name)
      assert.equal(router.currentRoute.value.params.labUid, single.uid)
      // Browser refresh and bookmarks enter the guard before any named navigation.
      const refreshed = makeRouter(scope)
      await refreshed.browserNavigate(`${long.replace("/orgs/", "/labs/")}?read=version#anchor`)
      assert.equal(refreshed.currentRoute.value.path, canonical)
      assert.deepEqual(refreshed.currentRoute.value.query, { read: "version" })
      assert.equal(refreshed.currentRoute.value.hash, "#anchor")
    }
  })
}

test("single instance never resolves a foreign organization to the local project", async () => {
  const router = makeRouter(single)
  for (const target of ["/labs/foreign/projects/project/overview", "/orgs/foreign/projects/project/overview", { name: "project-overview", params: { labUid: "foreign", projectUid: "project" } }]) {
    assert.equal(router.resolve(target).path, "/404/lab")
    await router.push(target)
    assert.equal(router.currentRoute.value.name, "lab-not-found")
    assert.equal(router.currentRoute.value.params.labUid, undefined)
  }
})

test("deployment mode, not visible organization count, selects short paths", () => {
  assert.equal(configureOrganizationRouting({ deployment_mode: "community", lab: { uid: single.uid } }).single, false)
  assert.equal(configureOrganizationRouting({ deployment_mode: "single_lab", lab: { uid: single.uid } }).single, true)
  assert.equal(configureOrganizationRouting({ deployment_mode: "single_organization", organization: { uid: single.uid } }).uid, single.uid)
  assert.equal(canonicalOrganizationPath("/api/labs/123", single), "/api/labs/123")
  assert.equal(canonicalOrganizationPath("https://external.example/labs/123", single), "https://external.example/labs/123")
  assert.equal(canonicalOrganizationPath("/labs/%ZZ/projects/a", single), "/404/lab")
  assert.equal(canonicalOrganizationPath("/labs/synthetic_org/projects/a", { single: true }), "/404/lab")
})

test("root redirects, list routes, browser history and query-only updates do not loop", async () => {
  const router = makeRouter(single)
  await router.push("/labs/synthetic_org/projects/project?sort=recent#top")
  assert.equal(router.currentRoute.value.path, "/projects/project/overview")
  await router.push("/labs/synthetic_org")
  assert.equal(router.currentRoute.value.path, "/organization/settings")
  assert.equal(router.resolve({ name: "lab-projects", params: { labUid: single.uid } }).href, "/projects/my")
  await router.browserNavigate("/labs/my")
  assert.equal(router.currentRoute.value.path, "/projects/my")
  await router.push({ name: "project-documents", params: { labUid: single.uid, projectUid: "project" } })
  await router.replace({ query: { read: "document" } })
  assert.equal(router.currentRoute.value.path, "/projects/project/documents")
  assert.equal(router.currentRoute.value.params.labUid, single.uid)
  const returned = new Promise(resolve => router.afterEach(resolve))
  router.back()
  await returned
  assert.equal(router.currentRoute.value.path, "/projects/my")
})

test("login return links use canonical destinations and preserve query and hash", async () => {
  const router = makeRouter(single)
  let signedIn = false
  router.beforeEach((to) => {
    if (!signedIn && to.name === "project-documents")
      return { name: "login", query: { redirect: to.fullPath } }
  })
  await router.browserNavigate("/labs/synthetic_org/projects/project/documents?read=revision#result")
  assert.equal(router.currentRoute.value.name, "login")
  assert.equal(router.currentRoute.value.query.redirect, "/projects/project/documents?read=revision#result")
  signedIn = true
  await router.push(router.currentRoute.value.query.redirect)
  assert.equal(router.currentRoute.value.name, "project-documents")
  assert.equal(router.currentRoute.value.params.labUid, single.uid)
})
