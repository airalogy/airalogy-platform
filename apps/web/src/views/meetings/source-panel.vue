<script setup lang="ts">
import {
  type Cue,
  type Person,
  type Source,
  sourceFile,
  spaceUrl,
  workspaceGet,
  workspaceSave,
} from "@/service/api/meeting-workspace"
import { downloadBlob } from "@/utils/downloadBlob"
import { useI18n } from "vue-i18n"

const props = defineProps<{ id: string, manage: boolean }>()
const emit = defineEmits<{
  draft: [body: string, actions: string[]]
  cite: [milliseconds: number]
}>()
const { t } = useI18n()
const tr = (key: string) => t(`page.meetingSpace.${key}`)
const source = ref<Source>()
const player = ref<HTMLAudioElement>()
const url = ref("")
const active = ref<number>()
const busy = ref(false)
const problem = ref("")
const editing = ref(false)
const imported = ref(false)
const page = ref(1)
const pageSize = 40
const offset = computed(() => (page.value - 1) * pageSize)
const working = ref<Cue[]>([])
const speakers = ref<Person[]>([])
const matches = ref<Record<string, string[]>>(Object.create(null))
const choices = ref<Record<string, string>>(Object.create(null))
const names = computed(() => [...new Set(working.value.map(c => c.speaker).filter(Boolean))])
let disposed = false
onUnmounted(() => {
  disposed = true
  if (url.value)
    URL.revokeObjectURL(url.value)
})
async function run(action: () => Promise<void>) {
  if (busy.value)
    return
  problem.value = ""
  busy.value = true
  try {
    await action()
  }
  catch (e) {
    problem.value = (e as Error).message || tr("failed")
  }
  finally {
    busy.value = false
  }
}
async function refresh() {
  source.value = await workspaceGet<Source>(`${spaceUrl(props.id)}/sources`)
}
let ready: Promise<void> | undefined
onMounted(() => {
  ready = run(refresh)
})
async function edit(fresh = false) {
  page.value = 1
  imported.value = fresh
  const transcript = source.value?.transcript
  if (!transcript)
    return
  const result = await workspaceGet<{ people: Person[], matches: Record<string, string[]> }>(
    `${spaceUrl(props.id)}/speakers`,
  )
  speakers.value = result.people
  matches.value = Object.assign(Object.create(null), result.matches)
  working.value = transcript.cues.map(c => ({ ...c }))
  choices.value = Object.create(null)
  for (const name of names.value) {
    const accounts = new Set(working.value.filter(c => c.speaker === name).map(c => c.account_id))
    if (accounts.size === 1) {
      const account = [...accounts][0]
      if (account)
        choices.value[name] = account
    }
  }
  editing.value = true
}
function apply(name: string, id: string | null) {
  for (const cue of working.value) {
    if (cue.speaker === name)
      cue.account_id = id
  }
}
async function save() {
  await workspaceSave(`${spaceUrl(props.id)}/transcript`, "PUT", {
    expected_revision: source.value?.transcript?.revision,
    cues: working.value.map(({ start, end, speaker, text, account_id }) => ({
      start,
      end,
      speaker,
      text,
      account_id,
    })),
  })
  await refresh()
  editing.value = false
}
async function upload(event: Event, kind: "audio" | "transcript") {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file)
    return
  input.value = ""
  const data = new FormData()
  data.set("file", file)
  await run(async () => {
    await workspaceSave(`${spaceUrl(props.id)}/${kind}`, "POST", data)
    await refresh()
    if (kind === "transcript")
      await edit(true)
  })
}
async function play(ms = 0) {
  if (!url.value) {
    const blob = await sourceFile(props.id, "audio")
    if (disposed)
      return
    url.value = URL.createObjectURL(blob)
    await nextTick()
  }
  if (player.value) {
    const audio = player.value
    if (audio.readyState < HTMLMediaElement.HAVE_METADATA) {
      await new Promise<void>((resolve, reject) => {
        function cleanup() {
          audio.removeEventListener("loadedmetadata", loaded)
          audio.removeEventListener("error", failed)
        }
        function loaded() {
          cleanup()
          resolve()
        }
        function failed() {
          cleanup()
          reject(new Error(tr("failed")))
        }
        audio.addEventListener("loadedmetadata", loaded)
        audio.addEventListener("error", failed)
      })
    }
    if (disposed)
      return
    audio.currentTime = ms / 1000
    await audio.play()
  }
}
function clock(ms: number) {
  const sec = Math.floor(ms / 1000)
  return [Math.floor(sec / 3600), Math.floor(sec / 60) % 60, sec % 60]
    .map(v => String(v).padStart(2, "0"))
    .join(":")
}
async function download(fmt: string) {
  downloadBlob(
    await sourceFile(props.id, `transcript/${fmt}`),
    fmt === "original" ? source.value!.transcript!.filename : `transcript.${fmt}`,
  )
}
async function draft() {
  const result = await workspaceSave<{ body: string, actions: string[] }>(
    `${spaceUrl(props.id)}/draft`,
    "POST",
    {},
  )
  emit("draft", result.body, result.actions)
}
async function seek(ms: number) {
  await ready
  if (source.value?.audio)
    await run(() => play(ms))
}
function matchAll() {
  const linked = new Set(working.value.filter(c => c.account_id).map(c => c.speaker))
  for (const name of names.value) {
    const ids = matches.value[name]
    if (choices.value[name] === undefined && ids?.length === 1 && !linked.has(name)) {
      choices.value[name] = ids[0]!
      apply(name, ids[0]!)
    }
  }
}
defineExpose({ seek })
</script>

<template>
  <section class="source-panel space-y-3" :aria-label="tr('sources')">
    <p v-if="problem" role="alert">
      {{ problem }} <button @click="run(refresh)">
        {{ t("common.retry") }}
      </button>
    </p>
    <template v-if="source">
      <div class="flex flex-wrap gap-3">
        <label v-if="manage && !source.audio">{{ tr("addAudio") }}
          <input
            type="file"
            accept=".mp3,.m4a,.mp4,.wav,.ogg,.webm,.flac,.aac"
            :disabled="busy"
            @change="upload($event, 'audio')"
          ></label>
        <label v-if="manage && !source.transcript">{{ tr("importTranscript") }}
          <input
            type="file"
            accept=".srt,.vtt,.txt"
            :disabled="busy"
            @change="upload($event, 'transcript')"
          ></label>
        <n-button v-if="source.audio && !url" :disabled="busy" @click="run(() => play())">
          {{
            tr("play")
          }}
        </n-button>
        <audio
          v-if="url"
          ref="player"
          :src="url"
          controls
          class="w-full"
          @timeupdate="active = player?.currentTime"
        />
      </div>
      <template v-if="source.transcript">
        <div class="flex flex-wrap items-center gap-2">
          <span>{{ source.transcript.filename }}</span>
          <n-button
            v-for="format in ['original', 'vtt', 'srt', 'txt']"
            :key="format"
            size="small"
            :disabled="
              busy
                || (['vtt', 'srt'].includes(format)
                  && source.transcript.cues.some(c => c.start === null))
            "
            @click="run(() => download(format))"
          >
            {{ format === "original" ? tr("original") : format.toUpperCase() }}
          </n-button>
          <n-button v-if="manage && !editing" :disabled="busy" @click="run(() => edit())">
            {{
              tr("correct")
            }}
          </n-button>
          <n-button v-if="manage && !editing" :loading="busy" @click="run(draft)">
            {{
              tr("draft")
            }}
          </n-button>
        </div>
        <template v-if="editing">
          <fieldset class="border rounded p-3 space-y-2">
            <legend>{{ tr("speakers") }}</legend>
            <p>{{ tr("matchHint") }}</p>
            <label v-for="name in names" :key="name" class="block">{{ name }}
              <select v-model="choices[name]" @change="apply(name, choices[name] || null)">
                <option disabled :value="undefined">{{ tr("choose") }}</option>
                <option value="">{{ tr("unlink") }}</option>
                <optgroup v-if="matches[name]?.length" :label="tr('suggested')"><option
                  v-for="p in speakers.filter(p => matches[name]?.includes(p.id))"
                  :key="p.id"
                  :value="p.id"
                >{{ p.name }} @{{ p.username }}</option></optgroup>
                <option
                  v-for="p in speakers.filter(p => !matches[name]?.includes(p.id))"
                  :key="p.id"
                  :value="p.id"
                >{{ p.name }} @{{ p.username }}</option>
              </select>
            </label>
            <n-button size="small" @click="matchAll">
              {{ tr("unique") }}
            </n-button>
          </fieldset>
          <div v-for="(cue, i) in working.slice(offset, offset + pageSize)" :key="i" class="cue">
            <input v-model="cue.speaker" :aria-label="tr('speaker')">
            <select v-model="cue.account_id" :aria-label="tr('account')">
              <option :value="null">
                {{ tr("unlink") }}
              </option><option v-for="p in speakers" :key="p.id" :value="p.id">
                {{ p.name }} @{{ p.username }}
              </option>
            </select>
            <textarea v-model="cue.text" :aria-label="tr('words')" />
          </div>
          <n-button :disabled="busy" type="primary" @click="run(save)">
            {{
              t("common.save")
            }}
          </n-button>
          <n-button :disabled="busy" @click="editing = false">
            {{
              imported ? tr("skipLinks") : t("common.cancel")
            }}
          </n-button>
        </template>
        <ol v-else class="list-none p-0 space-y-2">
          <li
            v-for="(cue, i) in source.transcript.cues.slice(offset, offset + pageSize)"
            :key="i"
            class="cue"
            :class="{
              playing:
                active !== undefined
                && cue.start !== null
                && active * 1000 >= cue.start
                && active * 1000 < cue.end!,
            }"
          >
            <button
              v-if="cue.start !== null"
              :disabled="!source.audio || busy"
              @click="run(() => play(cue.start!))"
            >
              {{ clock(cue.start) }}
            </button>
            <strong>{{ cue.account_name || cue.speaker || tr("unknown") }}</strong>
            <span
              v-if="cue.account_name && cue.speaker && cue.account_name !== cue.speaker"
              class="text-sm text-gray-500"
            >{{ cue.speaker }}</span>
            <button v-if="manage && cue.start !== null" @click="emit('cite', cue.start)">
              {{
                tr("cite")
              }}
            </button>
            <p>{{ cue.text }}</p>
          </li>
        </ol>
        <n-pagination
          v-if="source.transcript.cues.length > pageSize"
          v-model:page="page"
          :page-size="pageSize"
          :item-count="source.transcript.cues.length"
          :page-slot="3"
        />
      </template>
    </template>
  </section>
</template>

<style scoped>
.cue {
  padding: 0.65rem;
  border-inline-start: 2px solid #cbd5e1;
  overflow-wrap: anywhere;
}
.cue.playing {
  background: #edf5ff;
  border-color: #2671b9;
}
.cue > * {
  margin-inline-end: 0.5rem;
}
.cue p {
  white-space: pre-wrap;
  margin-block: 0.2rem;
}
textarea,
select,
input {
  max-width: 100%;
  border: 1px solid #aab6c4;
  border-radius: 0.3rem;
  padding: 0.3rem;
}
.cue textarea {
  width: 100%;
}
button {
  color: #215d97;
}
</style>
