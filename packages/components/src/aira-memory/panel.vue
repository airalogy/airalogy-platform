<template>
  <section class="min-w-0 space-y-4" aria-labelledby="aira-memory-title" data-testid="aira-memory-panel">
    <h3 id="aira-memory-title" class="text-lg font-semibold">
      {{ $t('airaMemory.title') }}
    </h3>
    <p class="text-sm text-gray-600">
      {{ $t('airaMemory.description') }}
    </p>
    <n-alert v-if="error" type="error" :title="error === 'conflict' ? $t('airaMemory.conflict') : $t('airaMemory.failed')">
      <n-button size="small" :loading="busy" @click="load">
        {{ $t('airaMemory.reload') }}
      </n-button>
    </n-alert>
    <n-spin :show="busy">
      <template v-if="state">
        <n-switch data-testid="memory-enabled" :aria-label="$t('airaMemory.enabled')" :value="enabled" :disabled="busy" @update:value="enabled = $event">
          <template #checked>
            {{ $t('airaMemory.enabled') }}
          </template>
          <template #unchecked>
            {{ $t('airaMemory.disabled') }}
          </template>
        </n-switch>
        <n-form label-placement="top" class="grid grid-cols-1 mt-4 gap-x-4 sm:grid-cols-2">
          <n-form-item v-for="key in keys" :key="key" :label="$t(`airaMemory.${key}`)">
            <div class="min-w-0 w-full">
              <n-select v-model:value="values[key]" :data-testid="`memory-${key}`" :aria-label="$t(`airaMemory.${key}`)" :options="options(key)" :placeholder="$t('airaMemory.notSet')" clearable :disabled="busy" />
              <p v-if="state.preferences[key]" class="mt-1 break-words text-xs text-gray-500">
                {{ $t(state.preferences[key]?.source === 'chat' ? 'airaMemory.fromChat' : 'airaMemory.fromSettings') }} · {{ date(state.preferences[key]?.updated_at) }}
              </p>
            </div>
          </n-form-item>
        </n-form>
        <div class="flex flex-wrap gap-2">
          <n-button type="primary" :disabled="busy || !dirty" @click="save">
            {{ $t('airaMemory.save') }}
          </n-button>
          <n-button v-if="undoState" :disabled="busy" @click="undo">
            {{ $t('airaMemory.undo') }}
          </n-button>
          <n-button :disabled="busy" @click="download">
            {{ $t('airaMemory.export') }}
          </n-button>
          <n-popconfirm @positive-click="clear">
            <template #trigger>
              <n-button :disabled="busy || !Object.keys(state.preferences).length" type="error" quaternary>
                {{ $t('airaMemory.clear') }}
              </n-button>
            </template>
            {{ $t('airaMemory.clearConfirm') }}
          </n-popconfirm>
        </div>
        <p v-if="saved" role="status" class="mt-2 text-sm text-green-700">
          {{ $t('airaMemory.saved') }}
        </p>
        <p class="mt-4 text-sm text-gray-600">
          {{ $t('airaMemory.examples') }}
        </p>
        <details class="mt-3 text-sm text-gray-500" @toggle="loadActivity">
          <summary class="cursor-pointer">
            {{ $t('airaMemory.activity') }}
          </summary>
          <p class="my-2">
            {{ $t('airaMemory.activityHint') }}
          </p>
          <ul class="space-y-1">
            <li v-for="event in activity" :key="event.revision">
              #{{ event.revision }} · {{ date(event.created_at) }} · {{ $t(event.action === 'clear' ? 'airaMemory.cleared' : 'airaMemory.updated') }}
            </li>
          </ul>
        </details>
      </template>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import type { MemoryEvent, MemoryState, PreferenceKey } from "./api"
import { $t } from "@airalogy/shared/locales"
import { computed, ref, watch } from "vue"
import { memoryRequest, preferenceOptions } from "./api"

const props = defineProps<{ endpoint: string, token: string }>()
const emit = defineEmits<{ updated: [] }>()
const keys = Object.keys(preferenceOptions) as PreferenceKey[]
const state = ref<MemoryState>()
const undoState = ref<MemoryState>()
const activity = ref<MemoryEvent[]>([])
const values = ref<Record<PreferenceKey, string | null>>({ language: null, detail: null, format: null, explanation: null })
const enabled = ref(true)
const busy = ref(false)
const error = ref("")
const saved = ref(false)
const identity = () => `${props.endpoint}|${props.token}`
const dirty = computed(() => !!state.value && (enabled.value !== state.value.enabled || keys.some(key => values.value[key] !== (state.value?.preferences[key]?.value ?? null))))
function options(key: PreferenceKey) {
  return preferenceOptions[key].map(value => ({ value, label: $t(`airaMemory.${value}` as "airaMemory.concise") }))
}
function date(value?: string) {
  return value ? new Date(value).toLocaleString() : ""
}
function apply(next: MemoryState) {
  state.value = next
  enabled.value = next.enabled
  for (const key of keys) values.value[key] = next.preferences[key]?.value ?? null
}
async function load() {
  const account = identity()
  busy.value = true
  error.value = ""
  undoState.value = undefined
  try {
    const next = await memoryRequest<MemoryState>(props.endpoint, props.token)
    if (account !== identity())
      return
    apply(next)
  }
  catch (e) {
    if (account === identity())
      error.value = (e as Error).message
  }
  finally {
    if (account === identity())
      busy.value = false
  }
}
async function change(body: Record<string, unknown>, allowUndo = true) {
  if (!state.value || busy.value)
    return
  busy.value = true
  saved.value = false
  error.value = ""
  const previous = state.value
  const account = identity()
  try {
    const next = await memoryRequest<MemoryState>(props.endpoint, props.token, "", { ...body, expected_revision: previous.revision, request_id: crypto.randomUUID() })
    if (account !== identity())
      return
    apply(next)
    undoState.value = allowUndo ? previous : undefined
    saved.value = true
    emit("updated")
  }
  catch (e) {
    if (account === identity())
      error.value = (e as Error).message
  }
  finally {
    if (account === identity())
      busy.value = false
  }
}
async function save() {
  const changes = Object.fromEntries(keys.filter(key => values.value[key] !== (state.value?.preferences[key]?.value ?? null)).map(key => [key, values.value[key]]))
  await change({ changes, enabled: enabled.value })
}
async function undo() {
  if (!undoState.value)
    return
  await change({ changes: Object.fromEntries(keys.map(key => [key, undoState.value?.preferences[key]?.value ?? null])), enabled: undoState.value.enabled }, false)
}
async function clear() {
  await change({ clear: true }, false)
}
async function download() {
  const account = identity()
  error.value = ""
  try {
    const data = await memoryRequest(props.endpoint, props.token, "/export")
    if (account !== identity())
      return
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }))
    const link = document.createElement("a")
    link.href = url
    link.download = "aira-preferences.json"
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  catch (e) {
    if (account === identity())
      error.value = (e as Error).message
  }
}
async function loadActivity(event: Event) {
  const account = identity()
  if (!(event.target as HTMLDetailsElement).open)
    return
  try {
    const next = await memoryRequest<MemoryEvent[]>(props.endpoint, props.token, "/activity")
    if (account !== identity())
      return
    activity.value = next
  }
  catch (e) {
    if (account === identity())
      error.value = (e as Error).message
  }
}
watch(() => [props.endpoint, props.token], () => {
  state.value = undefined
  undoState.value = undefined
  activity.value = []
  saved.value = false
  if (props.token)
    void load()
}, { immediate: true, flush: "sync" })
</script>
