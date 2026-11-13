/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import { useOffsetPagination } from "@vueuse/core"
import { useRouteQuery } from "@vueuse/router"
import ts from "typescript"
import { computed, effectScope, nextTick, reactive, ref, toRef, toValue, unref } from "vue"

const source = readFileSync(new URL("../../../packages/composables/src/usePagination.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText.replace(/^import .*?;\n/gm, "")
let serial = 0
async function harness(query = {}) {
  const route = reactive({ params: {}, query, hash: "" })
  const navigations = []
  const router = { replace: async (target) => { navigations.push(target); route.query = target.query } }
  const bindings = { ref, unref, toRef, computed, toValue, useOffsetPagination, useRouteQuery: (name, fallback, options) => useRouteQuery(name, fallback, { ...options, route, router }) }
  const key = `__pagination${++serial}`
  globalThis[key] = bindings
  const module = await import(`data:text/javascript;base64,${Buffer.from(`const { ${Object.keys(bindings).join(",")} } = globalThis.${key};\n${compiled}`).toString("base64")}`)
  delete globalThis[key]
  const scope = effectScope()
  const pagination = scope.run(() => module.usePagination({ options: { page: 1, pageSize: 10, total: ref(30) } }))
  await nextTick()
  return { pagination, navigations, scope }
}

test("initializing an absent or normalized page does not cancel another navigation", async () => {
  for (const query of [{}, { page: "1" }, { page: "2" }]) {
    const h = await harness(query)
    try {
      assert.equal(h.pagination.currentPage.value, Number(query.page || 1))
      assert.deepEqual(h.navigations, [])
    }
    finally { h.scope.stop() }
  }
})

test("an explicit page change still updates the URL and preserves unrelated filters", async () => {
  const h = await harness({ q: "sample" })
  try {
    h.pagination.handlePageChange(2)
    await nextTick()
    await nextTick()
    assert.equal(h.pagination.currentPage.value, 2)
    assert.equal(h.navigations.length, 1)
    assert.deepEqual(h.navigations[0].query, { q: "sample", page: 2 })
  }
  finally { h.scope.stop() }
})
