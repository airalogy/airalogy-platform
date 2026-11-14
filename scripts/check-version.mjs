import { readdir, readFile } from "node:fs/promises"
import { parsePlatformVersion } from "./release-version.mjs"

const repositoryRoot = new URL("../", import.meta.url)
const readText = async path => readFile(new URL(path, repositoryRoot), "utf8")
const readJson = async path => JSON.parse(await readText(path))

const version = (await readText("VERSION")).trim()
const { pythonVersion } = parsePlatformVersion(version)

for (const packageFile of ["package.json", "apps/web/package.json", "apps/instrument-interface/package.json"]) {
  const packageJson = await readJson(packageFile)
  if (packageJson.version !== version) {
    throw new Error(`${packageFile} has version ${packageJson.version}; expected ${version}`)
  }
}

for (const projectFile of [
  "apps/api/pyproject.toml",
  "apps/compute-runner/pyproject.toml",
  "apps/instrument-gateway/pyproject.toml",
]) {
  const project = await readText(projectFile)
  const projectVersion = /^version\s*=\s*"([^"]+)"$/mu.exec(project)?.[1]
  if (projectVersion !== pythonVersion) {
    throw new Error(
      `${projectFile} has version ${projectVersion ?? "missing"}; expected ${pythonVersion} (Platform ${version})`,
    )
  }
}

const deploymentEnvironment = await readText("deploy/single-lab/.env.example")
for (const entry of await readdir(new URL("apps/instrument-gateway/examples/", repositoryRoot), { withFileTypes: true })) {
  if (!entry.isDirectory())
    continue
  const files = await readdir(new URL(`apps/instrument-gateway/examples/${entry.name}/`, repositoryRoot))
  if (!files.includes("manifest.json"))
    continue
  const manifest = await readJson(`apps/instrument-gateway/examples/${entry.name}/manifest.json`)
  if (manifest.schema === "airalogy.adapter-package.v1" && !manifest.compatibility.gateway_versions.includes(pythonVersion))
    throw new Error(`${entry.name}: bundled adapter must declare tested compatibility with Gateway ${pythonVersion}`)
}
const deploymentVersion = /^PLATFORM_VERSION=(.+)$/mu.exec(deploymentEnvironment)?.[1]?.trim()
if (deploymentVersion !== version) {
  throw new Error(
    `deploy/single-lab/.env.example has PLATFORM_VERSION ${deploymentVersion ?? "missing"}; expected ${version}`,
  )
}

const escapedVersion = version.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
for (const imageKey of [
  "AIRALOGY_API_IMAGE",
  "AIRALOGY_WEB_IMAGE",
  "AIRALOGY_PROTOCOL_EXECUTOR_IMAGE",
  "AIRALOGY_POSTGRES_IMAGE",
  "MINIO_IMAGE",
  "MINIO_MC_IMAGE",
]) {
  const image = new RegExp(`^${imageKey}=(.+)$`, "mu").exec(deploymentEnvironment)?.[1]?.trim()
  if (!image || !new RegExp(`:${escapedVersion}(?:@|$)`).test(image)) {
    throw new Error(
      `deploy/single-lab/.env.example ${imageKey} must use product version ${version}`,
    )
  }
}

console.log(`Airalogy Platform version ${version} is consistent`)
