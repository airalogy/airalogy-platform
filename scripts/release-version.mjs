import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

// Keep product tags unambiguous; Python packages use the equivalent PEP 440
// spelling, while product versions, browser builds and image tags use SemVer.
export function parsePlatformVersion(version) {
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.([1-9]\d*))?$/.exec(version)
  if (!match || match[0] !== version)
    throw new Error("Expected MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-{alpha,beta,rc}.N (N >= 1)")
  const base = match.slice(1, 4).join(".")
  const channel = match[4] || "stable"
  return {
    version,
    tag: `v${version}`,
    channel,
    prerelease: channel !== "stable",
    pythonVersion: match[4] ? `${base}${{ alpha: "a", beta: "b", rc: "rc" }[channel]}${match[5]}` : base,
  }
}

export function parsePlatformTag(tag) {
  if (typeof tag !== "string" || !tag.startsWith("v"))
    throw new Error("Expected an exact Platform release tag")
  return parsePlatformVersion(tag.slice(1))
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const info = parsePlatformVersion(process.argv[2])
  console.log(`version=${info.version}\npython_version=${info.pythonVersion}\nchannel=${info.channel}\nprerelease=${info.prerelease}`)
}
