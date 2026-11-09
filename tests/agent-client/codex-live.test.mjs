/* eslint-disable test/no-import-node-test -- Standalone Node runner, no Vitest runtime. */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import process from "node:process"
import { it } from "node:test"
import { fileURLToPath } from "node:url"
import { loopback } from "./codex-live.mjs"

it("live acceptance refuses remote targets and credential-bearing URLs", () => {
  for (const address of ["https://example.test", "http://localhost:3108", "http://127.0.0.1.example.test", "http://user:secret@127.0.0.1", "http://127.0.0.1/api", "http://127.0.0.1?token=secret", "file:///tmp/test"])
    assert.throws(() => loopback(address))
  assert.equal(loopback("http://127.0.0.1:3108"), "http://127.0.0.1:3108")
  assert.equal(loopback("http://[::1]:3108"), "http://[::1]:3108")
})

it("real Codex test is opt-in and refuses before starting clients", () => {
  const env = { ...process.env, AIRALOGY_CODEX_LIVE: "", CODEX_BIN: "/does-not-exist" }
  const result = spawnSync(process.execPath, [fileURLToPath(new URL("./codex-live.mjs", import.meta.url))], { env, encoding: "utf8" })
  assert.equal(result.status, 1)
  assert.match(result.stderr, /Set AIRALOGY_CODEX_LIVE=1/)
  assert.doesNotMatch(result.stderr, /ENOENT/)
})
