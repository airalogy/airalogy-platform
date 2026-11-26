<template>
  <settings-card v-if="status" class="my-6" :title="t('page.organization.backups.title')">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <p role="status">
        {{ t(`page.organization.backups.${workerState}`) }}
      </p>
      <n-button size="small" @click="load(false)">
        {{ t('page.organization.backups.refresh') }}
      </n-button>
    </div>
    <form v-if="status.catalog.length && draft" class="grid gap-3" @submit.prevent="save">
      <fieldset>
        <legend>{{ t('page.organization.backups.targets') }}</legend>
        <label v-for="target in status.catalog" :key="target.id" class="mr-4 inline-flex items-center gap-2">
          <input v-model="draft.targets" type="checkbox" :value="target.id">
          {{ target.name }}
        </label>
      </fieldset>
      <div class="backup-fields">
        <label>{{ t('page.organization.backups.frequency') }}
          <select v-model="draft.frequency">
            <option v-for="mode in modes" :key="mode" :value="mode">{{ t(`page.organization.backups.${mode}`) }}</option>
          </select>
        </label>
        <label v-if="draft.frequency === 'daily'">{{ t('page.organization.backups.hour') }} ({{ status.timezone }})
          <select v-model.number="draft.hour">
            <option v-for="h in 24" :key="h" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
          </select>
        </label>
        <label>{{ t('page.organization.backups.days') }}<input v-model.number="draft.days" required type="number" min="1" max="90"></label>
        <label>{{ t('page.organization.backups.weeks') }}<input v-model.number="draft.weeks" required type="number" min="0" max="52"></label>
      </div>
      <p>{{ t(`page.organization.backups.${draft.frequency}Hint`) }}</p>
      <div class="flex flex-wrap gap-2">
        <n-button attr-type="submit" type="primary" :disabled="!dirty || !draft.targets.length || busy">
          {{ t('common.save') }}
        </n-button>
        <n-button :disabled="workerState !== 'online' || dirty || busy" @click="backup()">
          {{ t('page.organization.backups.run') }}
        </n-button>
      </div>
    </form>
    <p role="status" aria-live="polite" class="my-2">
      {{ feedback }}
    </p>
    <article v-for="target in status.catalog" :key="target.id" class="border-t py-3">
      <h4 class="mb-2 font-semibold">
        {{ target.name }}
      </h4>
      <p>{{ messageFor(target.code) }} <span v-if="target.free !== null && target.total !== null">· {{ capacity(target.total - target.free) }} {{ t('page.organization.backups.used') }} / {{ capacity(target.free) }} {{ t('page.organization.backups.free') }}</span></p>
      <p>{{ t('page.organization.backups.lastSuccess') }} · {{ date(status.last_result[target.id]?.success) }}</p>
      <template v-if="status.last_result[target.id]">
        <p>{{ t('page.organization.backups.lastAttempt') }} · {{ date(status.last_result[target.id].time) }} · {{ messageFor(status.last_result[target.id].code) }}</p>
        <n-button v-if="status.last_result[target.id].code !== 'ok'" size="small" :disabled="workerState !== 'online' || busy" @click="backup(target.id)">
          {{ t('page.organization.backups.retry') }}
        </n-button>
      </template>
      <details v-if="status.last_result[target.id]?.points?.length" class="mt-2">
        <summary>{{ t('page.organization.backups.points') }} ({{ status.last_result[target.id].points.length }})</summary>
        <ul class="pl-5">
          <li v-for="point in status.last_result[target.id].points" :key="point.id">
            {{ new Date(point.time).toLocaleString() }} · <code :title="point.id">{{ point.id.slice(0, 12) }}</code>
          </li>
        </ul>
      </details>
    </article>
    <p>{{ t('page.organization.backups.drill') }} · {{ date(status.last_drill?.time) }}</p>
  </settings-card>
</template>

<script setup lang="ts">
import { SettingsCard } from "@/components/common/settings"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { request } from "@/service/request"

const modes = ["daily", "hourly", "off"] as const
type Frequency = typeof modes[number]
interface Policy { targets: string[], frequency: Frequency, hour: number, days: number, weeks: number }
interface Target { id: string, name: string, code: string, free: number | null, total: number | null }
interface Result { code: string, time: number, success?: number, points: { time: string, id: string }[] }
interface Status { catalog: Target[], policy: Policy, revision: number, pending: string[] | null, running: string[] | false, last_result: Record<string, Result>, last_drill: { time: number } | null, timezone: string, heartbeat: number }
const codes = ["ready", "disk_missing", "read_only", "key_unavailable", "low_space", "low_staging_space", "ok", "interrupted", "capture_failed", "backup_failed", "retention_failed", "unknown_target"] as const
const { t } = useOrganizationTranslation()
const url = "/instance/backups"
const status = ref<Status>()
const draft = ref<Policy>()
const baseRevision = ref(0)
const baseline = ref("")
const dirty = computed(() => Boolean(draft.value) && JSON.stringify(draft.value) !== baseline.value)
const feedback = ref("")
const busy = ref(false)
const now = ref(Date.now())
const workerState = computed(() => {
  const s = status.value
  if (!s?.heartbeat)
    return "unconfigured"
  if (now.value / 1000 - s.heartbeat > 180)
    return "offline"
  if (s.running)
    return "running"
  return s.pending ? "queued" : "online"
})
function messageFor(code: string) {
  const key = codes.find(item => item === code) ?? "backup_failed"
  return t(`page.organization.backups.${key}`)
}
function capacity(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GiB`
}
function date(seconds?: number) {
  return seconds ? new Date(seconds * 1000).toLocaleString() : t("page.organization.backups.none")
}
async function load(reset: boolean) {
  const { data } = await request<Status>({ url, metadata: { showError: false } })
  now.value = Date.now()
  if (!data)
    return
  status.value = data
  if (reset || !dirty.value) {
    baseline.value = JSON.stringify(data.policy)
    const registered = new Set(data.catalog.map(item => item.id))
    draft.value = { ...data.policy, targets: data.policy.targets.filter(id => registered.has(id)) }
    baseRevision.value = data.revision
  }
}
async function save() {
  if (!draft.value || busy.value)
    return
  busy.value = true
  try {
    const { error } = await request({ url: `${url}/policy`, method: "PUT", data: { ...draft.value, revision: baseRevision.value }, metadata: { showError: false } })
    feedback.value = t(error ? "page.organization.backups.saveError" : "page.organization.backups.saved")
    await load(true)
  }
  finally { busy.value = false }
}
async function backup(target?: string) {
  busy.value = true
  try {
    const { error } = await request({ url: `${url}/requests`, method: "POST", data: { target }, metadata: { showError: false } })
    feedback.value = t(error ? "page.organization.backups.requestError" : "page.organization.backups.queued")
    await load(false)
  }
  finally { busy.value = false }
}
let timer: ReturnType<typeof setInterval>
onMounted(() => {
  load(true)
  timer = setInterval(() => {
    if (status.value && !document.hidden && !busy.value)
      load(false)
  }, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.backup-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr)); gap: .75rem; }
.backup-fields label { display: grid; align-content: start; gap: .3rem; }
.backup-fields select, .backup-fields input { min-width: 0; padding: .4rem .6rem; border: 1px solid #cbd5e1; border-radius: .35rem; background: inherit; }
</style>
