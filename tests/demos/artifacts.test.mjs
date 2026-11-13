/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import test from "node:test"
import { captions, planNarration, trackDurations, videoParts } from "../../scripts/lib/learning-narration.mjs"

const root = new URL("../../", import.meta.url)
const { unzipSync, strFromU8 } = createRequire(new URL("apps/web/package.json", root))("fflate")
const read = path => readFile(new URL(path, root))
const scenarios = JSON.parse(await read("docs/demos/scenarios.json"))
const manifest = JSON.parse(await read("docs/demos/manifest.json"))
const narrationBytes = await read("docs/demos/narration.json")
const narration = JSON.parse(narrationBytes)
const edits = JSON.parse(await read("docs/demos/edits.json"))
const seconds = time => time.split(":").reduce((sum, part) => sum * 60 + Number(part), 0)

test("each task has real downloadable media, bilingual captions and complete instructions", async () => {
  assert.deepEqual(Object.keys(scenarios).sort(), ["welcome", "first-record", "first-document", "first-protocol", "first-import", "aira-protocol", "aira-record", "aira-analysis"].sort())
  assert.deepEqual(Object.keys(manifest).sort(), Object.keys(scenarios).sort())
  for (const [id, scenario] of Object.entries(scenarios)) {
    const media = manifest[id]
    assert.ok(media.duration > 20 && media.duration < 240, `${id}: short, complete recording`)
    assert.equal(media.synthetic, true)
    if (scenario.ai_required) {
      assert.equal(media.ai_workflow, true)
      assert.equal(media.ai_verification, "real-model-responses")
    }
    assert.match(media.recorded_on, /^\d{4}-\d{2}-\d{2}$/)
    assert.match(media.source_revision, /^[a-f0-9]{40}$/)
    assert.equal(media.narration.locale, "zh-CN")
    assert.equal(media.narration.ai_generated, true)
    assert.equal(media.narration.script_sha256, createHash("sha256").update(narrationBytes).digest("hex"))
    if (edits[id]) {
      assert.deepEqual(media.editing.cuts, edits[id].cuts)
      assert.equal(media.editing.capture_sha256, edits[id].capture_sha256)
      assert.match(media.editing.capture_sha256, /^[a-f0-9]{64}$/)
      assert.ok(Math.abs(media.editing.removed_seconds - edits[id].cuts.reduce((sum, cut) => sum + cut.end - cut.start, 0)) < 0.00001)
    }
    let previousEnd = 0
    for (const [index, step] of media.narration.timeline.entries()) {
      assert.equal(step.start, previousEnd)
      assert.ok(step.audio_start >= step.start && step.audio_end < step.end, `${id}: speech fits its visible step`)
      assert.ok(step.hold >= 0, `${id}: retained actions must not be accelerated`)
      const cutSeconds = step.cut_seconds || 0
      assert.ok(Math.abs(step.end - step.start - (step.source_end - step.source_start - cutSeconds + step.hold)) < 0.00001)
      const expectedCuts = edits[id]?.cuts.filter(cut => cut.step === index) || []
      assert.ok(Math.abs(cutSeconds - expectedCuts.reduce((sum, cut) => sum + cut.end - cut.start, 0)) < 0.00001)
      if (step.source_ranges) {
        const ranges = step.source_ranges
        assert.equal(ranges[0].start, step.source_start)
        assert.equal(ranges.at(-1).end, step.source_end)
        assert.equal(ranges.length, expectedCuts.length + 1)
        for (const [cutIndex, cut] of expectedCuts.entries()) {
          assert.equal(ranges[cutIndex].end, cut.start)
          assert.equal(ranges[cutIndex + 1].start, cut.end)
        }
      }
      if (index > 0)
        assert.equal(step.source_start, media.narration.timeline[index - 1].source_end)
      previousEnd = step.end
    }
    assert.equal(previousEnd, media.duration)
    for (const [filename, expected] of Object.entries(media.files)) {
      const bytes = await read(`docs/public/demos/${filename}`)
      assert.equal(bytes.length, expected.bytes, filename)
      assert.equal(createHash("sha256").update(bytes).digest("hex"), expected.sha256, filename)
      if (filename.endsWith(".mp4")) {
        assert.equal(bytes.toString("ascii", 4, 8), "ftyp")
        assert.ok(bytes.length > 100_000, "real screen recording")
        const movie = boxes(bytes).find(box => box.type === "moov")
        const handlers = boxes(movie.data).filter(box => box.type === "trak").map((track) => {
          const mdia = boxes(track.data).find(box => box.type === "mdia")
          const handler = boxes(mdia.data).find(box => box.type === "hdlr")
          return handler.data.toString("ascii", 8, 12)
        })
        assert.equal(handlers.filter(type => type === "soun").length, 1, "MP4 contains one real audio track")
        assert.equal(handlers.filter(type => type === "vide").length, 1)
        assert.equal(handlers.filter(type => type === "sbtl").length, 2, "download retains both subtitle tracks")
        const tracks = trackDurations(bytes)
        for (const kind of ["vide", "soun"]) {
          const duration = tracks.find(track => track.type === kind).duration
          assert.ok(Math.abs(duration - media.duration) < 0.05, `${id}: ${kind} really spans the whole timeline`)
        }
      }
    }
    for (const locale of ["zh", "en"]) {
      assert.ok(scenario[locale].steps.length >= 5)
      assert.ok(scenario[locale].requirements.length && scenario[locale].success)
      const text = String(await read(`docs/public/demos/${id}.${locale}.vtt`))
      assert.ok(text.startsWith("WEBVTT\n"))
      const aligned = media.narration.timeline.map((step, index) => ({ ...step, ...narration.lessons[id][index] }))
      assert.equal(text, captions(aligned, locale), `${id}: captions follow the final voiced timeline`)
      const cues = [...text.matchAll(/(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\n[^\n]+/g)]
      assert.ok(cues.length >= 5)
      let end = 0
      for (const cue of cues) {
        const from = seconds(cue[1])
        const to = seconds(cue[2])
        assert.ok(from >= end && to > from && to <= media.duration + 0.002, `${id}: valid caption timeline`)
        end = to
      }
      assert.ok(media.duration - end < 0.1)
      assert.ok(String(await read(`docs/${locale}/learn/${id}.md`)).includes(`lesson="${id}"`))
    }
    for (const filename of scenario.downloads)
      assert.ok((await read(`docs/public/demos/examples/${filename}`)).length)
  }
})

test("reviewed waits are removed while clicks, results, speech and transition tails survive", () => {
  const take = { duration: 33, cues: [{ at: 1, zh: "generate" }, { at: 28, zh: "review" }] }
  const lines = [{ source_zh: "generate", zh: "生成", en: "Generate" }, { source_zh: "review", zh: "确认", en: "Review" }]
  const cuts = [{ step: 0, start: 3, end: 26, reason: "ai_wait" }]
  const plan = planNarration(take, lines, [7, 2], cuts)
  assert.equal(plan[0].cut_seconds, 23)
  assert.deepEqual(plan[0].source_ranges.map(({ start, end }) => [start, end]), [[1, 3], [26, 28]])
  assert.ok(plan[0].end < 9, "long loading sequence becomes a short narrated action")
  assert.equal(plan[1].start, plan[0].end)
  assert.ok(plan[0].audio_end < plan[0].end)
  const parts = videoParts(plan[0])
  assert.equal(parts.reduce((sum, part) => sum + part.frames, 0), plan[0].frames)
  assert.equal(parts.reduce((sum, part) => sum + part.sourceFrames, 0), plan[0].source_frames)
  assert.ok(parts.every(part => part.sourceFrames > 0 && part.frames >= part.sourceFrames))
  assert.ok(parts.find(part => part.frames > part.sourceFrames).start >= 26, "hold the visible result, not the spinner")
  assert.equal(parts.at(-1).frames, parts.at(-1).sourceFrames, "transition is never frozen")
})

test("cuts cannot silently cross steps, overlap, reorder or remove a whole step", () => {
  const take = { duration: 30, cues: [{ at: 1, zh: "one" }, { at: 20, zh: "two" }] }
  const lines = [{ source_zh: "one" }, { source_zh: "two" }]
  const base = { step: 0, start: 3, end: 15, reason: "ai_wait" }
  for (const cuts of [
    [{ ...base, start: 1 }],
    [{ ...base, end: 21 }],
    [{ ...base, step: 2 }],
    [{ ...base, step: -1 }],
    [{ ...base, step: 0.5 }],
    [{ ...base, end: 2 }],
    [{ ...base, end: Number.NaN }],
    [{ ...base, reason: "action" }],
    [base, { ...base, start: 14, end: 17 }],
    [{ ...base, start: 16, end: 18 }, base],
  ]) assert.throws(() => planNarration(take, lines, [2, 2], cuts), /Invalid wait cut/)
})

function boxes(bytes) {
  const result = []
  for (let offset = 0; offset < bytes.length;) {
    const size = bytes.readUInt32BE(offset)
    assert.ok(size >= 8 && offset + size <= bytes.length, "valid MP4 box")
    result.push({ type: bytes.toString("ascii", offset + 4, offset + 8), data: bytes.subarray(offset + 8, offset + size) })
    offset += size
  }
  return result
}

test("long speech holds the current step, never overlaps or shortens actions", () => {
  const take = { duration: 14, cues: [{ at: 2, zh: "first" }, { at: 8, zh: "second" }] }
  const lines = [{ source_zh: "first", zh: "一", en: "one" }, { source_zh: "second", zh: "二", en: "two" }]
  const plan = planNarration(take, lines, [9, 2])
  assert.equal(plan[0].start, 0, "remove uncaptioned startup")
  assert.ok(plan[0].end >= 9.8, "leave breathing room around speech")
  assert.equal(plan[1].start, plan[0].end)
  assert.ok(plan[1].frames >= 6 * 25, "keep even the longer silent action window, measured in whole frames")
  assert.ok(plan[0].audio_end < plan[1].audio_start)
  assert.ok(plan[0].end - plan[0].audio_end >= 1.1, "finish speech before the preserved transition tail")
  assert.ok(plan[0].hold_after_frame < plan[0].source_frames, "hold before a possible reload frame")
  assert.equal(plan[0].source_end, plan[1].source_start, "no captured actions omitted")
})

test("stale narration and incomplete or invalid audio cannot overwrite demos", () => {
  const take = { duration: 8, cues: [{ at: 2, zh: "current" }] }
  assert.throws(() => planNarration(take, [{ source_zh: "old" }], [4]), /changed/)
  assert.throws(() => planNarration(take, [], []), /every captured step/)
  for (const duration of [0, -1, Number.NaN, Infinity])
    assert.throws(() => planNarration(take, [{ source_zh: "current" }], [duration]), /Invalid duration/)
})

test("the example package and CSV match the official starter and preserve zero", async () => {
  const base = "docs/public/demos/examples/"
  const archive = unzipSync(await read(`${base}first-record-protocol.zip`))
  assert.deepEqual(Object.keys(archive).sort(), ["protocol.aimd", "protocol.toml"])
  assert.equal(strFromU8(archive["protocol.aimd"]), String(await read("packages/components/src/monaco-editor/templates/first-record-zh.aimd")))
  assert.equal(strFromU8(archive["protocol.toml"]), String(await read(`${base}protocol.toml`)))
  const fields = [...strFromU8(archive["protocol.aimd"]).matchAll(/\{\{var\|([a-z_]+)/g)].map(m => `var.${m[1]}`)
  const header = String(await read(`${base}records-template.csv`)).replace(/^\uFEFF/, "").trim()
  assert.deepEqual(header.split(","), fields)
  const valid = String(await read(`${base}records-corrected.csv`)).replace(/^\uFEFF/, "").trim().split("\r\n")
  assert.equal(valid[0], header)
  assert.equal(valid.length, 3)
  assert.deepEqual(valid.slice(1).map(row => row.split(",")[1]), ["0", "12"])
  assert.ok(String(await read(`${base}records-invalid.csv`)).includes("#REF!"))
})

test("analysis example has six synthetic Records matching its Protocol and demo statistics", async () => {
  const archive = unzipSync(await read("docs/public/demos/examples/analysis-protocol.zip"))
  const fields = [...strFromU8(archive["protocol.aimd"]).matchAll(/\{\{var\|([a-z_]+)/g)].map(m => `var.${m[1]}`)
  const rows = String(await read("docs/public/demos/examples/analysis-records.csv")).replace(/^\uFEFF/, "").trim().split("\r\n").map(row => row.split(","))
  assert.deepEqual(rows[0], fields)
  assert.equal(rows.length, 7)
  for (const [group, mean] of [["A", 12], ["B", 18]]) {
    const samples = rows.slice(1).filter(row => row[1] === group)
    assert.equal(samples.length, 3)
    assert.equal(samples.reduce((sum, row) => sum + Number(row[2]), 0) / samples.length, mean)
    assert.ok(samples.every(row => row[0].startsWith("DEMO-")))
  }
})
