export const frameRate = 25
export const sampleRate = 48000
export const voiceLead = 0.24
export const voiceTail = 0.56
export const transitionTail = 0.6

// Only explicitly reviewed wait intervals may be cut. Keep actions and speech
// at their recorded speed, and extend settled results when narration needs it.
export function planNarration(take, lines, audioDurations, cuts = []) {
  if (!take.cues?.length || take.cues.length !== lines.length || lines.length !== audioDurations.length)
    throw new Error("Narration must match every captured step")
  let previousCutEnd = -1
  for (const cut of cuts) {
    const cue = take.cues[cut.step]
    const end = take.cues[cut.step + 1]?.at ?? take.duration
    if (!Number.isInteger(cut.step) || !cue || cut.reason !== "ai_wait"
      || !Number.isFinite(cut.start) || !Number.isFinite(cut.end)
      || cut.start >= cut.end || cut.start < previousCutEnd
      || cut.start < cue.at + 0.5 || cut.end > end - 0.5) {
      throw new Error("Invalid wait cut: preserve step boundaries and ordered, non-overlapping ranges")
    }
    previousCutEnd = cut.end
  }
  let frame = 0
  return take.cues.map((cue, index) => {
    const sourceEnd = take.cues[index + 1]?.at ?? take.duration
    const sourceDuration = sourceEnd - cue.at
    const audioDuration = audioDurations[index]
    if (cue.zh !== lines[index].source_zh)
      throw new Error(`Step ${index + 1} changed: review its narration before rendering`)
    if (!Number.isFinite(sourceDuration) || sourceDuration <= 0 || cue.at < 0 || !Number.isFinite(audioDuration) || audioDuration <= 0)
      throw new Error(`Invalid duration at step ${index + 1}`)
    const stepCuts = cuts.filter(cut => cut.step === index)
    const ranges = []
    let cursor = cue.at
    for (const cut of stepCuts) {
      ranges.push({ start: cursor, end: cut.start })
      cursor = cut.end
    }
    ranges.push({ start: cursor, end: sourceEnd })
    const sourceRanges = ranges.map(range => ({ ...range, frames: Math.ceil((range.end - range.start) * frameRate) }))
    const cutSeconds = stepCuts.reduce((sum, cut) => sum + cut.end - cut.start, 0)
    const sourceFrames = sourceRanges.reduce((sum, range) => sum + range.frames, 0)
    const tailFrames = Math.min(Math.round(transitionTail * frameRate), Math.floor(sourceFrames / 2))
    const frames = Math.max(sourceFrames, Math.ceil((audioDuration + voiceLead + voiceTail + tailFrames / frameRate) * frameRate))
    const start = frame / frameRate
    frame += frames
    return {
      start,
      end: frame / frameRate,
      source_start: cue.at,
      source_end: sourceEnd,
      hold: frames / frameRate - (sourceDuration - cutSeconds),
      cut_seconds: cutSeconds,
      source_ranges: sourceRanges,
      audio_start: start + voiceLead,
      audio_end: start + voiceLead + audioDuration,
      frames,
      source_frames: sourceFrames,
      hold_after_frame: sourceFrames - tailFrames,
      zh: lines[index].zh,
      en: lines[index].en,
    }
  })
}

// Split retained footage at the hold point without extending a loading/reload
// transition. All part durations remain whole frames, even across jump cuts.
export function videoParts(step) {
  const extraFrames = step.frames - step.source_frames
  const parts = []
  let frame = 0
  for (const [index, range] of step.source_ranges.entries()) {
    const holdAt = step.hold_after_frame - frame
    if (extraFrames > 0 && holdAt > 0 && holdAt <= range.frames) {
      parts.push({ name: `${index}-held`, start: range.start, sourceFrames: holdAt, frames: holdAt + extraFrames })
      if (holdAt < range.frames)
        parts.push({ name: `${index}-tail`, start: range.start + holdAt / frameRate, sourceFrames: range.frames - holdAt, frames: range.frames - holdAt })
    }
    else {
      parts.push({ name: `${index}-full`, start: range.start, sourceFrames: range.frames, frames: range.frames })
    }
    frame += range.frames
  }
  return parts
}

export function timestamp(seconds) {
  const ms = Math.round(seconds * 1000)
  return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`
}

export function captions(timeline, locale) {
  return `WEBVTT\n\n${timeline.map((step, index) => `${index + 1}\n${timestamp(step.start)} --> ${timestamp(step.end)}\n${step[locale]}\n`).join("\n")}`
}

function boxes(bytes) {
  const result = []
  for (let offset = 0; offset < bytes.length;) {
    const size = bytes.readUInt32BE(offset)
    if (size < 8 || offset + size > bytes.length)
      throw new Error("Malformed generated MP4")
    result.push({ type: bytes.toString("ascii", offset + 4, offset + 8), data: bytes.subarray(offset + 8, offset + size) })
    offset += size
  }
  return result
}

// Container duration alone can hide a shorter video track behind longer audio.
export function trackDurations(bytes) {
  const movie = boxes(bytes).find(box => box.type === "moov")
  if (!movie)
    throw new Error("Generated MP4 has no movie metadata")
  return boxes(movie.data).filter(box => box.type === "trak").map((track) => {
    const mdia = boxes(track.data).find(box => box.type === "mdia")
    const children = boxes(mdia.data)
    const header = children.find(box => box.type === "mdhd").data
    const handler = children.find(box => box.type === "hdlr").data
    const version = header[0]
    if (version !== 0 && version !== 1)
      throw new Error("Unsupported MP4 track duration")
    const timescale = header.readUInt32BE(version === 1 ? 20 : 12)
    const ticks = version === 1 ? Number(header.readBigUInt64BE(24)) : header.readUInt32BE(16)
    return { type: handler.toString("ascii", 8, 12), duration: ticks / timescale }
  })
}
