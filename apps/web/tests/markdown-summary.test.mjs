/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

const source = readFileSync(new URL("../src/utils/markdown-summary.ts", import.meta.url), "utf8")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText.replace(/(["'])mdast-util-from-markdown\1/, JSON.stringify(import.meta.resolve("mdast-util-from-markdown")))
const { markdownSummary } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)

test("activity previews preserve readable content without Markdown syntax or HTML blocks", () => {
  assert.equal(markdownSummary("# Decisions\n\n**Compare** [results](https://example.test) and ![sample](asset.png).\n\n- First\n- Second\n\n<script>alert('x')</script>"), "Decisions Compare results and sample. First Second")
  assert.equal(markdownSummary("a <em>readable</em> result and `sample_id`"), "a readable result and sample_id")
})
test("long previews are bounded without exposing link targets", () => {
  assert.equal(markdownSummary("[abcdef](https://example.test/private)", 3), "abc…")
  assert.equal(markdownSummary(""), "")
})
