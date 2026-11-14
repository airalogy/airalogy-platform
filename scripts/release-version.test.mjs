/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { load } from "js-yaml"
import { parsePlatformTag, parsePlatformVersion } from "./release-version.mjs"

const root = path.resolve(import.meta.dirname, "..")

test("product versions and Python package identities agree across release channels", () => {
  for (const [version, pythonVersion, channel] of [
    ["0.4.1", "0.4.1", "stable"],
    ["0.5.0-alpha.1", "0.5.0a1", "alpha"],
    ["0.5.0-beta.2", "0.5.0b2", "beta"],
    ["1.2.0-rc.3", "1.2.0rc3", "rc"],
  ]) {
    assert.deepEqual(parsePlatformTag(`v${version}`), { version, tag: `v${version}`, pythonVersion, channel, prerelease: channel !== "stable" })
    const bootstrap = spawnSync("python3", ["-I", "-S", "-c", "import runpy,sys; print(runpy.run_path(sys.argv[1])['release_tag_version'](sys.argv[2]))", path.join(root, "apps/instrument-gateway/bootstrap.py"), `v${version}`], { encoding: "utf8" })
    assert.equal(bootstrap.status, 0, bootstrap.stderr)
    assert.equal(bootstrap.stdout.trim(), pythonVersion)
  }
  for (const invalid of ["01.2.3", "1.2", "1.2.3-beta", "1.2.3-beta.0", "1.2.3-beta.01", "1.2.3-dev.1", "1.2.3-rc.1+dirty", "1.2.3\n", "v1.2.3"])
    assert.throws(() => parsePlatformVersion(invalid))
  for (const invalid of ["main", "latest", "1.2.3", "v1.2.3/../../x"])
    assert.throws(() => parsePlatformTag(invalid))
})

test("version consistency accepts canonical Python prereleases but rejects mismatched components", async (t) => {
  const fixture = await mkdtemp(path.join(os.tmpdir(), "platform-version-"))
  t.after(() => rm(fixture, { recursive: true, force: true }))
  const files = {
    "VERSION": "0.5.0-beta.1\n",
    "package.json": '{"version":"0.5.0-beta.1","type":"module"}',
    "apps/web/package.json": '{"version":"0.5.0-beta.1"}',
    "apps/instrument-interface/package.json": '{"version":"0.5.0-beta.1"}',
    "apps/api/pyproject.toml": 'version = "0.5.0b1"\n',
    "apps/compute-runner/pyproject.toml": 'version = "0.5.0b1"\n',
    "apps/instrument-gateway/pyproject.toml": 'version = "0.5.0b1"\n',
    "apps/instrument-gateway/examples/example/manifest.json": JSON.stringify({ schema: "airalogy.adapter-package.v1", compatibility: { gateway_versions: ["0.5.0b1"] } }),
    "deploy/single-lab/.env.example": `PLATFORM_VERSION=0.5.0-beta.1\n${["AIRALOGY_API_IMAGE", "AIRALOGY_WEB_IMAGE", "AIRALOGY_PROTOCOL_EXECUTOR_IMAGE", "AIRALOGY_POSTGRES_IMAGE", "MINIO_IMAGE", "MINIO_MC_IMAGE"].map(key => `${key}=example/image:0.5.0-beta.1`).join("\n")}\n`,
  }
  for (const [name, content] of Object.entries(files)) {
    await mkdir(path.dirname(path.join(fixture, name)), { recursive: true })
    await writeFile(path.join(fixture, name), content)
  }
  await mkdir(path.join(fixture, "scripts"))
  for (const file of ["check-version.mjs", "release-version.mjs"])
    await copyFile(path.join(root, "scripts", file), path.join(fixture, "scripts", file))
  const run = () => spawnSync(process.execPath, [path.join(fixture, "scripts/check-version.mjs")], { encoding: "utf8" })
  const valid = run()
  assert.equal(valid.status, 0, valid.stderr)
  await writeFile(path.join(fixture, "apps/api/pyproject.toml"), 'version = "0.5.0b2"\n')
  assert.match(run().stderr, /expected 0\.5\.0b1/)
})

test("prerelease publication never becomes latest and unknown channels fail closed", async (t) => {
  const fixture = await mkdtemp(path.join(os.tmpdir(), "platform-publication-"))
  t.after(() => rm(fixture, { recursive: true, force: true }))
  const workflow = load(await readFile(path.join(root, ".github/workflows/release.yml"), "utf8"))
  const step = workflow.jobs.release.steps.find(step => step.name === "Create GitHub release")
  await writeFile(path.join(fixture, "gh"), '#!/bin/sh\nprintf "%s\\n" "$@" > "$PUBLICATION_CALL"\n', { mode: 0o755 })
  const callFile = path.join(fixture, "calls")
  for (const [version, prerelease] of [["0.5.0", "false"], ["0.5.0-beta.1", "true"]]) {
    for (const locale of ["en", "zh"]) {
      const directory = path.join(fixture, "docs", locale, "releases")
      await mkdir(directory, { recursive: true })
      await writeFile(path.join(directory, `v${version}.md`), "Synthetic release notes\n")
    }
    const env = { ...process.env, PATH: `${fixture}:${process.env.PATH}`, RUNNER_TEMP: fixture, PUBLICATION_CALL: callFile, GITHUB_REF_NAME: `v${version}`, PRERELEASE: prerelease }
    const result = spawnSync("bash", ["-eu", "-o", "pipefail", "-c", step.run], { cwd: fixture, env, encoding: "utf8" })
    assert.equal(result.status, 0, result.stderr)
    const args = (await readFile(callFile, "utf8")).split("\n")
    assert.equal(args.includes("--prerelease"), prerelease === "true")
    assert.equal(args.includes("--latest=false"), prerelease === "true")
    assert.ok(args.includes("--verify-tag"))
    await rm(callFile)
    const invalid = spawnSync("bash", ["-eu", "-o", "pipefail", "-c", step.run], { cwd: fixture, env: { ...env, PRERELEASE: "" }, encoding: "utf8" })
    assert.notEqual(invalid.status, 0)
    await assert.rejects(readFile(callFile), /ENOENT/)
  }
  const metadata = workflow.jobs.images.steps.find(step => step.id === "metadata")
  assert.match(metadata.with.tags, /pattern=\{\{major\}\}\.\{\{minor\}\},enable=.*prerelease == 'false'/)
  assert.match(metadata.with.tags, /type=sha,prefix=sha-,format=long/)
})
