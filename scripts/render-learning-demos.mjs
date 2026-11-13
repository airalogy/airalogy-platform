import { Buffer } from "node:buffer"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import { captions, frameRate, planNarration, sampleRate, trackDurations, videoParts } from "./lib/learning-narration.mjs"

const root = new URL("../", import.meta.url)
const capture = new URL("tests/e2e/.runtime/learning-demos/capture/", root)
const voiceCache = new URL("tests/e2e/.runtime/learning-demos/narration/", root)
const staging = new URL("tests/e2e/.runtime/learning-demos/voiced-media/", root)
const output = new URL("docs/public/demos/", root)
const scenarios = JSON.parse(await readFile(new URL("docs/demos/scenarios.json", root), "utf8"))
const scriptBytes = await readFile(new URL("docs/demos/narration.json", root))
const script = JSON.parse(scriptBytes)
const sha = bytes => createHash("sha256").update(bytes).digest("hex")
const edits = JSON.parse(await readFile(new URL("docs/demos/edits.json", root), "utf8"))
const voiceManifest = JSON.parse(await readFile(new URL("manifest.json", voiceCache), "utf8").catch(() => {
  throw new Error("Generate the reviewed Chinese narration first: pnpm demos:voice")
}))
if (voiceManifest.script_sha256 !== sha(scriptBytes))
  throw new Error("Narration script changed: run pnpm demos:voice before rendering")
const ffmpeg = process.env.DEMO_FFMPEG || "ffmpeg"
const selected = process.env.DEMO_LESSONS?.split(",") || Object.keys(scenarios)
if (!selected.length || selected.some(id => !(id in scenarios)) || new Set(selected).size !== selected.length)
  throw new Error("DEMO_LESSONS must list unique known lesson IDs")
const manifest = JSON.parse(await readFile(new URL("docs/demos/manifest.json", root), "utf8"))
for (const [id, media] of Object.entries(manifest)) {
  if (!selected.includes(id) && media.narration.script_sha256 !== sha(scriptBytes))
    throw new Error("Narration changed: render all lessons instead of a subset")
}
function convert(args) {
  const result = spawnSync(ffmpeg, ["-hide_banner", "-loglevel", "error", "-y", ...args], { encoding: "utf8" })
  if (result.status !== 0)
    throw new Error(`Media conversion failed: ${result.error || result.stderr}`)
}
await mkdir(staging, { recursive: true })
await mkdir(output, { recursive: true })
for (const id of selected) {
  const take = JSON.parse(await readFile(new URL(`${id}.json`, capture), "utf8"))
  if (take.id !== id || !take.recorded_on || take.cues.length < 5 || take.duration <= 20)
    throw new Error(`Missing or incomplete successful capture: ${id}`)
  if (scenarios[id].ai_required && (!take.ai_workflow || take.ai_verification !== "real-model-responses"))
    throw new Error(`AI lesson requires successful real-model acceptance: ${id}`)
  const edit = edits[id]
  if (edit && (!take.ai_workflow || edit.capture_sha256 !== sha(await readFile(new URL(`${id}.webm`, capture)))))
    throw new Error(`Wait cuts need review for this capture: ${id}`)
  const lines = script.lessons[id]
  const voices = voiceManifest.lessons[id]
  if (voices?.length !== lines?.length)
    throw new Error(`Incomplete narration: ${id}`)
  const audio = []
  for (const [index, voice] of voices.entries()) {
    if (!/^[a-f0-9]{64}\.mp3$/.test(voice.file))
      throw new Error("Invalid cached narration filename")
    const source = new URL(voice.file, voiceCache)
    if (sha(await readFile(source)) !== voice.sha256)
      throw new Error(`Narration cache damaged: ${id} step ${index + 1}`)
    const pcm = new URL(`${id}-${index}.pcm`, staging)
    convert(["-i", fileURLToPath(source), "-af", "loudnorm=I=-16:TP=-1.5:LRA=7", "-ar", String(sampleRate), "-ac", "1", "-f", "s16le", fileURLToPath(pcm)])
    const samples = await readFile(pcm)
    let sum = 0
    for (let i = 0; i < samples.length; i += 2) sum += samples.readInt16LE(i) ** 2
    if (!samples.length || Math.sqrt(sum / (samples.length / 2)) < 50)
      throw new Error(`Empty or silent narration: ${id} step ${index + 1}`)
    audio.push(samples)
  }
  const timeline = planNarration(take, lines, audio.map(bytes => bytes.length / (sampleRate * 2)), edit?.cuts)
  const duration = timeline.at(-1).end
  const joinedAudio = Buffer.alloc(Math.round(duration * sampleRate) * 2)
  const segments = []
  for (const [index, step] of timeline.entries()) {
    audio[index].copy(joinedAudio, Math.round(step.audio_start * sampleRate) * 2)
    const parts = videoParts(step)
    // Encode held content separately from its transition tail. Some FFmpeg
    // versions drop tpad frames in a split/trim/concat filter graph.
    for (const part of parts) {
      const segment = `${id}-${index}-${part.name}.mp4`
      convert([
        "-ss",
        String(part.start),
        "-i",
        fileURLToPath(new URL(`${id}.webm`, capture)),
        "-vf",
        `trim=duration=${part.sourceFrames / frameRate},setpts=PTS-STARTPTS,fps=${frameRate},tpad=stop_mode=clone:stop=${part.frames - part.sourceFrames + 1}`,
        "-frames:v",
        String(part.frames),
        "-r",
        String(frameRate),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-video_track_timescale",
        "25000",
        fileURLToPath(new URL(segment, staging)),
      ])
      const videoDuration = trackDurations(await readFile(new URL(segment, staging))).find(track => track.type === "vide")?.duration
      if (Math.abs(videoDuration - part.frames / frameRate) > 0.002 || !Number.isFinite(videoDuration))
        throw new Error(`Video hold lost during encoding: ${segment}`)
      segments.push(`file '${segment}'`)
    }
  }
  await writeFile(new URL(`${id}.concat`, staging), `${segments.join("\n")}\n`)
  await writeFile(new URL(`${id}.pcm`, staging), joinedAudio)
  const files = [`${id}.mp4`, `${id}.png`, `${id}.zh.vtt`, `${id}.en.vtt`]
  for (const locale of ["zh", "en"])
    await writeFile(new URL(`${id}.${locale}.vtt`, staging), captions(timeline, locale))
  convert([
    "-f",
    "concat",
    "-safe",
    "1",
    "-i",
    fileURLToPath(new URL(`${id}.concat`, staging)),
    "-f",
    "s16le",
    "-ar",
    String(sampleRate),
    "-ac",
    "1",
    "-i",
    fileURLToPath(new URL(`${id}.pcm`, staging)),
    "-i",
    fileURLToPath(new URL(`${id}.zh.vtt`, staging)),
    "-i",
    fileURLToPath(new URL(`${id}.en.vtt`, staging)),
    "-map",
    "0:v:0",
    "-map",
    "1:a:0",
    "-map",
    "2:0",
    "-map",
    "3:0",
    "-c:v",
    "copy",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-c:s",
    "mov_text",
    "-map_metadata",
    "-1",
    "-metadata:s:a:0",
    "language=zho",
    "-metadata:s:a:0",
    "title=Chinese AI narration",
    "-metadata:s:s:0",
    "language=zho",
    "-metadata:s:s:1",
    "language=eng",
    "-metadata",
    `comment=${edit ? "AI waiting intervals shortened; actions and narration retain normal speed." : "Real UI demonstration with synchronized narration."}`,
    "-movflags",
    "+faststart",
    "-t",
    String(duration),
    fileURLToPath(new URL(`${id}.mp4`, staging)),
  ])
  const tracks = trackDurations(await readFile(new URL(`${id}.mp4`, staging)))
  for (const kind of ["vide", "soun"]) {
    const actual = tracks.find(track => track.type === kind)?.duration
    if (!Number.isFinite(actual) || Math.abs(actual - duration) > 0.05)
      throw new Error(`${id}: ${kind} track duration does not match the narrated timeline`)
  }
  // Decode both streams before replacing existing playable lessons.
  convert(["-i", fileURLToPath(new URL(`${id}.mp4`, staging)), "-map", "0:v", "-map", "0:a", "-f", "null", "-"])
  await copyFile(new URL(`${id}.png`, capture), new URL(`${id}.png`, staging))
  manifest[id] = {
    duration,
    recorded_on: take.recorded_on,
    source_revision: take.source_revision,
    source_state: "local-development",
    synthetic: true,
    ai_workflow: take.ai_workflow === true,
    ...(take.ai_workflow ? { ai_verification: take.ai_verification } : {}),
    ...(edit ? { editing: { ...edit, removed_seconds: timeline.reduce((sum, step) => sum + step.cut_seconds, 0) } } : {}),
    viewport: { width: 1440, height: 1000 },
    ui_locale: "zh-CN",
    captions: ["zh", "en"],
    narration: {
      locale: script.locale,
      ai_generated: true,
      engine: script.engine,
      engine_version: script.engine_version,
      voice: script.voice,
      rate: script.rate,
      script_sha256: sha(scriptBytes),
      generated_on: new Date().toISOString().slice(0, 10),
      timeline: timeline.map(({ frames: _frames, zh: _zh, en: _en, ...step }, index) => ({ ...step, audio_sha256: voices[index].sha256 })),
    },
    files: Object.fromEntries(await Promise.all(files.map(async (name) => {
      const bytes = await readFile(new URL(name, staging))
      return [name, { bytes: bytes.length, sha256: sha(bytes) }]
    }))),
  }
  console.log(`Rendered ${id}: ${duration.toFixed(2)}s; ${manifest[id].editing?.removed_seconds.toFixed(2) || 0}s of reviewed waiting removed`)
}
// Failed generation leaves the previous set intact. Promote only a complete set.
for (const id of selected) {
  const media = manifest[id]
  for (const name of Object.keys(media.files))
    await copyFile(new URL(name, staging), new URL(name, output))
}
await writeFile(new URL("docs/demos/manifest.json", root), `${JSON.stringify(manifest, null, 2)}\n`)
