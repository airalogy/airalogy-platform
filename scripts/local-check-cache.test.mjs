/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFileSync, spawnSync } from "node:child_process"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { checkEnvironment, checkIdentity, executeLocalCheck, reusableChecks } from "./local-check-cache.mjs"

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "platform-check-cache-"))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const gitEnv = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("GIT_")))
  gitEnv.GIT_CONFIG_GLOBAL = "/dev/null"
  gitEnv.GIT_CONFIG_NOSYSTEM = "1"
  const git = (...args) => execFileSync("git", args, { cwd: root, env: gitEnv, stdio: "pipe" })
  git("init", "-q")
  git("config", "user.name", "Synthetic check")
  git("config", "user.email", "check@example.invalid")
  writeFileSync(join(root, ".gitignore"), ".cache/\nnode_modules/\n.env\n")
  writeFileSync(join(root, "source.txt"), "committed source")
  git("add", ".")
  git("commit", "-qm", "synthetic fixture")
  const env = { PATH: process.env.PATH, MODE: "synthetic" }
  const check = { id: "fixture", command: process.execPath, args: ["-e", `
    const fs = require('node:fs');
    fs.mkdirSync('.cache', { recursive: true });
    let n = 0; try { n = Number(fs.readFileSync('.cache/count')); } catch {}
    fs.writeFileSync('.cache/count', String(n + 1));
    console.log('synthetic run', n + 1);
    if (fs.existsSync('.cache/fail')) process.exit(7);
  `] }
  const options = { root, env, cacheable: true }
  const run = extra => executeLocalCheck(check, { ...options, ...extra })
  const receipt = join(root, ".cache/local-checks/fixture.json")
  const count = () => Number(readFileSync(join(root, ".cache/count")))
  return { root, git, env, check, run, receipt, count }
}

test("same clean commit and runtime reuse a real successful command; fresh reruns", (t) => {
  const f = fixture(t)
  assert.equal(f.run().status, 0)
  assert.equal(f.run().reused, true)
  assert.equal(f.count(), 1)
  assert.equal(f.run({ fresh: true }).status, 0)
  assert.equal(f.count(), 2)
})

test("hook repository variables never reach temporary repositories or invalidate direct-check reuse", (t) => {
  const f = fixture(t)
  const before = f.git("rev-parse", "HEAD").toString()
  const config = readFileSync(join(f.root, ".git/config"), "utf8")
  const hookEnv = { ...f.env, GIT_DIR: join(f.root, ".git"), GIT_WORK_TREE: f.root, GIT_INDEX_FILE: join(f.root, ".git/index"), PATH: `node_modules/.bin:${f.env.PATH}` }
  assert.deepEqual(checkEnvironment(f.env, f.root), checkEnvironment(hookEnv, f.root))
  f.run()
  assert.equal(f.run({ env: hookEnv }).reused, true)
  const child = spawnSync(process.execPath, ["--test", "--test-name-pattern=same clean commit", fileURLToPath(import.meta.url)], { env: { ...process.env, ...hookEnv }, encoding: "utf8", timeout: 10000 })
  assert.equal(child.status, 0, child.stderr + child.stdout)
  assert.equal(f.git("rev-parse", "HEAD").toString(), before)
  assert.equal(readFileSync(join(f.root, ".git/config"), "utf8"), config)
})

test("failed retry invalidates earlier success instead of falling back", (t) => {
  const f = fixture(t)
  f.run()
  writeFileSync(join(f.root, ".cache/fail"), "synthetic failure")
  assert.equal(f.run({ fresh: true }).status, 7)
  assert.equal(f.run().status, 7)
  assert.equal(f.count(), 3)
})

test("changed commit, dirty or untracked source, environment and dependency metadata invalidate", (t) => {
  const f = fixture(t)
  f.run()
  writeFileSync(join(f.root, "source.txt"), "modified")
  assert.equal(checkIdentity(f.root, f.check, f.env), null)
  f.run()
  f.git("add", ".")
  f.git("commit", "-qm", "source change")
  assert.equal(f.run().reused, undefined)
  writeFileSync(join(f.root, "untracked.py"), "# source")
  assert.equal(checkIdentity(f.root, f.check, f.env), null)
  rmSync(join(f.root, "untracked.py"))
  assert.equal(f.run({ env: { ...f.env, MODE: "different" } }).reused, undefined)
  mkdirSync(join(f.root, "node_modules"))
  writeFileSync(join(f.root, "node_modules/.modules.yaml"), "changed installation")
  assert.equal(f.run().reused, undefined)
  writeFileSync(join(f.root, ".env"), "SECRET=synthetic-only")
  assert.equal(f.run().reused, undefined)
  assert.ok(!readFileSync(f.receipt, "utf8").includes("SECRET"))
})

test("missing, corrupt, future or stale evidence and changed command cannot be reused", (t) => {
  const f = fixture(t)
  for (const finishedAt of [Date.now() - 86400_001, Date.now() + 60_000]) {
    f.run({ fresh: true })
    const r = JSON.parse(readFileSync(f.receipt))
    writeFileSync(f.receipt, JSON.stringify({ ...r, finished_at: finishedAt }))
    assert.equal(f.run().reused, undefined)
  }
  const r = JSON.parse(readFileSync(f.receipt))
  writeFileSync(join(f.root, `.cache/local-checks/fixture-${r.attempt}.log`), "tampered log")
  assert.equal(f.run().reused, undefined)
  const missing = JSON.parse(readFileSync(f.receipt))
  rmSync(join(f.root, `.cache/local-checks/fixture-${missing.attempt}.log`))
  assert.equal(f.run().reused, undefined)
  writeFileSync(f.receipt, "invalid JSON")
  assert.equal(f.run().reused, undefined)
  const before = checkIdentity(f.root, f.check, f.env)
  assert.notEqual(checkIdentity(f.root, { ...f.check, args: ["--version"] }, f.env).key, before.key)
})

test("source edits during a command and later failed attempts cannot become reusable success", (t) => {
  const f = fixture(t)
  f.check.args = ["-e", "require('node:fs').writeFileSync('source.txt', 'changed during check')"]
  assert.equal(f.run().status, 0)
  assert.equal(JSON.parse(readFileSync(f.receipt)).status, "failed")
  f.git("checkout", "--", "source.txt")
  f.check.args = ["-e", `
    const fs = require('node:fs');
    const path = '.cache/local-checks/fixture.json';
    const receipt = JSON.parse(fs.readFileSync(path));
    fs.writeFileSync(path, JSON.stringify({ ...receipt, attempt: 'newer-attempt', status: 'failed', exit_code: 7 }));
  `]
  assert.equal(f.run().status, 0)
  assert.equal(JSON.parse(readFileSync(f.receipt)).exit_code, 7)
})

test("CI and database integrations never reuse local feedback; live checks are excluded", (t) => {
  const f = fixture(t)
  f.run()
  for (const key of ["CI", "GITHUB_ACTIONS", "RESOURCE_TEST_DATABASE_URL"]) {
    const env = { ...f.env, [key]: "synthetic" }
    assert.equal(checkIdentity(f.root, f.check, env), null)
    assert.equal(f.run({ env }).reused, undefined)
  }
  for (const id of ["image-availability", "object-storage", "research-integration", "full-e2e", "ai-e2e", "build", "compute-engine", "gateway-sandbox", "native-build-tests", "interface-demo"])
    assert.equal(reusableChecks.has(id), false, id)
})
