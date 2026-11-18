import { execFileSync, spawnSync } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from "node:fs"
import { delimiter, join, resolve } from "node:path"

const MAX_AGE_MS = 24 * 60 * 60 * 1000
const digest = value => createHash("sha256").update(value).digest("hex")
const volatileEnvironment = new Set(["_", "SHLVL", "PWD", "OLDPWD", "GIT_PREFIX"])

// Local feedback only: live services, image availability, installed artifacts,
// recovery and browser acceptance always execute. CI never trusts this cache.
export const reusableChecks = new Set([
  "version",
  "lint",
  "types",
  "api-compile",
  "api-lock",
  "gateway-lock",
  "compute-lock",
  "api-tests",
  "masterbrain",
  "ci-config",
  "release-metadata",
  "deployment-identity",
  "instrument-contract",
  "gateway-cli",
  "gateway-tests",
  "interface-tests",
  "compute-runner-tests",
  "docs",
])

function git(root, args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim()
}

function runtimeInputs(root, env) {
  const inputs = {}
  for (const tool of ["node", "corepack", "uv", "python3"]) {
    const binary = (env.PATH || "").split(delimiter).map(path => join(path, tool)).find(path => existsSync(path) && statSync(path).isFile())
    if (binary) {
      const real = realpathSync(binary)
      const info = statSync(real)
      inputs[`tool:${tool}`] = [real, info.size, info.mtimeMs]
    }
  }
  const add = (path) => {
    const absolute = join(root, path)
    inputs[path] = existsSync(absolute) ? digest(readFileSync(absolute)) : null
  }
  for (const path of ["node_modules/.modules.yaml", "node_modules/.pnpm/lock.yaml", ".npmrc"])
    add(path)
  for (const directory of [".", "apps/web", "apps/api", "apps/instrument-gateway", "apps/compute-runner"]) {
    const absolute = join(root, directory)
    if (!existsSync(absolute))
      continue
    for (const entry of readdirSync(absolute, { withFileTypes: true })) {
      if (entry.isFile() && (entry.name === ".env" || entry.name.startsWith(".env.")))
        add(join(directory, entry.name))
    }
    add(join(directory, ".venv/pyvenv.cfg"))
    const python = join(absolute, ".venv/bin/python")
    if (existsSync(python)) {
      const binary = realpathSync(python)
      const info = statSync(binary)
      inputs[join(directory, "python-runtime")] = [binary, info.size, info.mtimeMs]
    }
    const lib = join(absolute, ".venv/lib")
    if (!existsSync(lib))
      continue
    for (const version of readdirSync(lib)) {
      const site = join(lib, version, "site-packages")
      if (!existsSync(site))
        continue
      for (const entry of readdirSync(site).sort()) {
        if (entry.endsWith(".dist-info")) {
          for (const name of ["METADATA", "RECORD", "direct_url.json"])
            add(join(directory, ".venv/lib", version, "site-packages", entry, name))
        }
      }
    }
  }
  return inputs
}

export function checkIdentity(root, check, env) {
  if (env.CI || env.GITHUB_ACTIONS || env.RESOURCE_TEST_DATABASE_URL)
    return null
  try {
    // Untracked source files matter too; ignored caches/private operations do not.
    if (git(root, ["status", "--porcelain", "--untracked-files=normal"]))
      return null
    const commit = git(root, ["rev-parse", "HEAD"])
    const environment = Object.fromEntries(Object.entries(env).filter(([key]) => !volatileEnvironment.has(key)).sort(([a], [b]) => a.localeCompare(b)))
    const context = { root: realpathSync(root), commit, platform: process.platform, arch: process.arch, node: process.version, executable: process.execPath, command: check.command, args: check.args, environment, runtime: runtimeInputs(root, env) }
    // Never persist credentials or environment values in a receipt.
    return { commit, key: digest(JSON.stringify(context)) }
  }
  catch {
    return null
  }
}

export function validReceipt(receipt, identity, log, now = Date.now()) {
  return Boolean(identity && receipt?.schema === 1 && receipt.status === "passed"
    && receipt.exit_code === 0 && receipt.commit === identity.commit && receipt.key === identity.key
    && Number.isFinite(receipt.finished_at) && receipt.finished_at <= now
    && now - receipt.finished_at < MAX_AGE_MS && existsSync(log)
    && digest(readFileSync(log)) === receipt.log_sha256)
}

export function executeLocalCheck(check, { root = process.cwd(), env = process.env, fresh = false, cacheable = reusableChecks.has(check.id) } = {}) {
  const directory = resolve(root, ".cache/local-checks")
  const receiptPath = join(directory, `${check.id}.json`)
  const attempt = randomUUID()
  const log = join(directory, `${check.id}-${attempt}.log`)
  const identity = cacheable ? checkIdentity(root, check, env) : null
  const save = (value) => {
    const temporary = `${receiptPath}.${process.pid}.tmp`
    writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 })
    renameSync(temporary, receiptPath)
  }
  if (cacheable) {
    mkdirSync(directory, { recursive: true, mode: 0o700 })
    try {
      const receipt = JSON.parse(readFileSync(receiptPath, "utf8"))
      const previousLog = /^[a-f\d-]{36}$/.test(receipt.attempt) ? join(directory, `${check.id}-${receipt.attempt}.log`) : ""
      if (!fresh && validReceipt(receipt, identity, previousLog)
        && JSON.parse(readFileSync(receiptPath, "utf8")).attempt === receipt.attempt) {
        console.log(`[pre-push] ${check.id}: reused verified local result for ${identity.commit.slice(0, 12)}`)
        return { status: 0, reused: true }
      }
    }
    catch { /* Missing or malformed evidence requires a real run. */ }
    // Invalidate previous success BEFORE any retry, even in a dirty checkout.
    save({ schema: 1, attempt, status: "running", ...identity, started_at: Date.now() })
  }
  const fd = identity ? openSync(log, "w", 0o600) : null
  let result
  try {
    result = spawnSync(check.command, check.args, { cwd: root, env, stdio: fd === null ? "inherit" : ["inherit", fd, fd] })
  }
  finally {
    if (fd !== null)
      closeSync(fd)
  }
  const after = identity ? checkIdentity(root, check, env) : null
  if (cacheable && JSON.parse(readFileSync(receiptPath, "utf8")).attempt === attempt) {
    // A later attempt (including a failure) wins over an older finishing run.
    save({ schema: 1, attempt, ...identity, status: result.status === 0 && identity?.key === after?.key && identity ? "passed" : "failed", exit_code: result.status, finished_at: Date.now(), log_sha256: fd === null ? null : digest(readFileSync(log)) })
  }
  if (fd !== null) {
    console.log(`[pre-push] ${check.id}: log ${log}`)
    if (result.status !== 0)
      process.stderr.write(readFileSync(log, "utf8"))
  }
  return result
}
