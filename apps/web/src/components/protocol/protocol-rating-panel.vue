<script setup lang="ts">
import type { ProtocolUseFeedback, RatingMine, RatingSummary, UseOutcome } from "@/service/api/protocol-rating"
import { ratingApi } from "@/service/api/protocol-rating"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ protocolId: string, version: string, recordId?: string, initialScope?: "accessible" | "public", embedded?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const selectedVersion = ref(props.version)
const scope = ref(props.initialScope || "accessible")
const summary = ref<RatingSummary | null>(null)
const mine = ref<RatingMine | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const saved = ref(false)
const showReview = ref(false)
const showUse = ref(Boolean(props.recordId))
const details = ref(false)
const score = ref(0)
const comment = ref("")
const conditions = ref("")
const useId = ref<string | null>(null)
const share = ref(false)
const selectedRecords = ref<string[]>(props.recordId ? [props.recordId] : [])
const records = ref<{ id: string, version: number, number: number, use_id: string | null }[]>([])
const recordPage = ref(1)
const moreRecords = ref(false)
const outcome = ref<UseOutcome>("unknown")
const isReal = ref(false)
const usePublic = ref(false)
const useComment = ref("")
const editingUse = ref<ProtocolUseFeedback | null>(null)
const requestKey = ref(crypto.randomUUID())
let sequence = 0
const outcomes = computed(() => (["as_planned", "adjusted", "stopped", "unknown"] as const).map(value => ({ value, label: $t(`page.protocol.rating.outcome.${value}`) })))
const useOptions = computed(() => (mine.value?.uses || []).filter(u => u.active).map(u => ({ value: u.id, label: `${$t(`page.protocol.rating.outcome.${u.outcome}`)} · ${u.id.slice(0, 8)}${u.eligible ? "" : ` · ${$t("page.protocol.rating.excluded")}`}` })))
const recordOptions = computed(() => records.value.map(r => ({ value: r.id, label: `#${r.number} · ${r.id.slice(0, 8)} · r${r.version}${r.use_id ? ` · ${$t("page.protocol.rating.linked")}` : ""}`, disabled: Boolean(r.use_id) })))
const publicOptions = computed(() => [{ value: "accessible", label: $t("page.protocol.rating.accessible") }, { value: "public", label: $t("page.protocol.rating.publicOnly") }])

function fail(cause?: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  const keys = ["stale_revision", "record_already_linked", "evidence_unavailable", "public_source_required", "version_mismatch", "request_conflict", "duplicate_record", "different_runs", "run_not_completed"] as const
  const key = keys.find(k => detail === `rating.${k}`)
  error.value = key ? $t(`page.protocol.rating.errors.${key}`) : $t("page.protocol.rating.error")
}
function applyMine(value: RatingMine) {
  mine.value = value
  score.value = value.rating?.score || 0
  comment.value = value.rating?.comment || ""
  conditions.value = value.rating?.conditions || ""
  useId.value = value.rating?.use_id || null
  share.value = value.rating?.public || false
}
async function load() {
  const seq = ++sequence
  loading.value = true
  error.value = ""
  saved.value = false
  summary.value = null
  mine.value = null
  const [result, own] = await Promise.all([
    ratingApi.summary(props.protocolId, selectedVersion.value, scope.value),
    auth.isLogin ? ratingApi.mine(props.protocolId, selectedVersion.value) : Promise.resolve(null),
  ])
  if (seq !== sequence)
    return
  loading.value = false
  if (result.error || !result.data || own?.error) {
    fail(result.error)
    return
  }
  summary.value = result.data
  if (own?.data) {
    applyMine(own.data)
    if (showUse.value && props.recordId) {
      const existing = own.data.uses.find(use => use.record_ids.includes(props.recordId!))
      if (existing)
        editUse(existing)
    }
  }
}
async function loadRecords(reset = true) {
  if (reset) {
    records.value = []
    recordPage.value = 1
  }
  const version = selectedVersion.value
  const result = await ratingApi.records(props.protocolId, version, recordPage.value)
  if (version !== selectedVersion.value)
    return
  if (result.error || !result.data) {
    fail(result.error)
    return
  }
  records.value = [...records.value, ...result.data.items]
  moreRecords.value = result.data.has_more
  recordPage.value++
}
async function beginUse() {
  const existing = props.recordId && mine.value?.uses.find(use => use.record_ids.includes(props.recordId!))
  if (existing) {
    editUse(existing)
    return
  }
  editingUse.value = null
  selectedRecords.value = props.recordId ? [props.recordId] : []
  outcome.value = "unknown"
  isReal.value = false
  usePublic.value = false
  useComment.value = ""
  requestKey.value = crypto.randomUUID()
  showUse.value = true
  await loadRecords()
}
function editUse(use: ProtocolUseFeedback) {
  editingUse.value = use
  selectedRecords.value = use.record_ids
  outcome.value = use.outcome
  isReal.value = use.is_real
  usePublic.value = use.public
  useComment.value = use.comment
  showUse.value = true
}
async function finish() {
  await load()
  saved.value = true
  emit("changed")
}
async function saveReview(active = true) {
  if (!score.value || saving.value)
    return
  saving.value = true
  error.value = ""
  const result = await ratingApi.save(props.protocolId, selectedVersion.value, { score: score.value, comment: comment.value, conditions: conditions.value, use_id: useId.value, public: share.value, active, expected_revision: mine.value?.rating?.revision || 0 })
  saving.value = false
  if (result.error) {
    fail(result.error)
    return
  }
  showReview.value = false
  await finish()
}
async function saveUse(active = true) {
  if (saving.value)
    return
  saving.value = true
  error.value = ""
  const data = { outcome: outcome.value, is_real: isReal.value, public: usePublic.value, comment: useComment.value }
  const result = editingUse.value
    ? await ratingApi.updateUse(editingUse.value.source_protocol_id, editingUse.value.source_version, editingUse.value.id, { ...data, expected_revision: editingUse.value.revision, active })
    : await ratingApi.use(props.protocolId, selectedVersion.value, { ...data, request_key: requestKey.value, record_ids: selectedRecords.value })
  saving.value = false
  if (result.error) {
    fail(result.error)
    return
  }
  showUse.value = false
  await finish()
}
function downloadBasis() {
  if (!summary.value)
    return
  const { reviews: _reviews, feedback: _feedback, ...basis } = summary.value
  const url = URL.createObjectURL(new Blob([JSON.stringify(basis, null, 2)], { type: "application/json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `protocol-rating-${selectedVersion.value}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
watch(() => [props.protocolId, props.version, auth.userInfo.id], () => {
  selectedVersion.value = props.version
  showReview.value = false
  showUse.value = Boolean(props.recordId)
  void load()
  if (showUse.value && auth.isLogin)
    void loadRecords()
}, { immediate: true })
function changeVersion(value: string) {
  selectedVersion.value = value
  showUse.value = false
  showReview.value = false
  void load()
}
</script>

<template>
  <section class="protocol-rating min-w-0 space-y-4" data-testid="protocol-rating-panel" :aria-busy="loading">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 v-if="!embedded" class="m-0 text-lg font-semibold">
        {{ $t("page.protocol.rating.title") }}
      </h3>
      <div class="flex flex-wrap gap-2">
        <n-select :value="selectedVersion" :options="(summary?.versions || [selectedVersion]).map(v => ({ value: v, label: `v${v}` }))" class="w-36" :aria-label="$t('page.protocol.rating.version')" :disabled="saving" @update:value="changeVersion" />
        <n-select v-if="auth.isLogin" v-model:value="scope" class="w-44" :options="publicOptions" :aria-label="$t('page.protocol.rating.scope')" :disabled="saving" @update:value="load" />
      </div>
    </div>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }} <n-button text @click="load">
        {{ $t("page.protocol.rating.reload") }}
      </n-button>
    </n-alert>
    <n-alert v-if="saved" type="success" role="status">
      {{ $t("page.protocol.rating.saved", { version: selectedVersion }) }}
    </n-alert>
    <n-spin :show="loading">
      <template v-if="summary">
        <div class="border border-gray-200 rounded-lg p-4">
          <div class="flex flex-wrap items-baseline gap-x-4 gap-y-2">
            <strong class="text-xl" data-testid="rating-recommendation">{{ summary.score === null ? $t("page.protocol.rating.insufficient") : `${$t("page.protocol.rating.recommendation")} ${summary.score}/100` }}</strong>
            <span>{{ $t("page.protocol.rating.userScore") }} {{ summary.rating_average === null ? '—' : `${summary.rating_average}/5` }} · {{ $t("page.protocol.rating.reviewers", { count: summary.rating_count }) }}</span>
          </div>
          <div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
            <span>{{ $t("page.protocol.rating.uses") }} {{ summary.use_count }}</span>
            <span>{{ $t("page.protocol.rating.reuse") }} {{ summary.effective_reuse_count }}</span>
            <span>{{ $t("page.protocol.rating.copies") }} {{ summary.copies_count }}</span>
            <span>{{ $t("page.protocol.rating.labs") }} {{ summary.lab_count }}</span>
          </div>
          <p class="mb-2 text-sm text-gray-500">
            {{ $t("page.protocol.rating.unknownUses", { count: summary.unclassified_records }) }}
          </p>
          <p class="mb-2 text-sm text-gray-500">
            {{ $t("page.protocol.rating.disclaimer") }}
          </p>
          <n-button text type="primary" @click="details = !details">
            {{ $t("page.protocol.rating.calculation") }}
          </n-button>
          <div v-if="details" class="mt-3 break-words border-t pt-3 text-sm space-y-2" data-testid="rating-calculation">
            <p>{{ $t("page.protocol.rating.formula") }}</p>
            <p>{{ $t("page.protocol.rating.points", { rating: summary.components.rating_points, adoption: summary.components.adoption_points }) }}</p>
            <p>{{ $t("page.protocol.rating.distribution") }}: <span v-for="n in 5" :key="n" class="mr-3">{{ n }}★: {{ summary.distribution[String(n)] }}</span></p>
            <p>{{ summary.algorithm }} · {{ $t(`page.protocol.rating.${summary.scope === 'public' ? 'publicOnly' : 'accessible'}`) }} · {{ new Date(summary.generated_at).toLocaleString() }}</p>
            <p>{{ $t("page.protocol.rating.coverage") }}</p>
            <p>{{ $t("page.protocol.rating.notAssessed") }}</p>
            <n-button size="small" @click="downloadBasis">
              {{ $t("page.protocol.rating.download") }}
            </n-button>
          </div>
        </div>
        <div v-if="auth.isLogin" class="mt-4 flex flex-wrap gap-3">
          <n-button type="primary" :disabled="saving" @click="showReview = !showReview">
            {{ $t("page.protocol.rating.write") }}
          </n-button>
          <n-button :disabled="saving" @click="beginUse">
            {{ $t("page.protocol.rating.confirmUse") }}
          </n-button>
        </div>
        <p v-else class="mt-3 text-gray-500">
          {{ $t("page.protocol.rating.login") }}
        </p>
        <n-form v-if="showReview && mine" class="mt-4 border rounded-lg p-4" label-placement="top" @submit.prevent="saveReview()">
          <n-form-item :label="$t('page.protocol.rating.userScore')">
            <fieldset class="m-0 flex flex-wrap gap-2 border-0 p-0" :aria-label="$t('page.protocol.rating.userScore')">
              <label v-for="n in 5" :key="n" class="rating-choice relative cursor-pointer">
                <input v-model.number="score" type="radio" name="protocol-rating-score" :value="n" :aria-label="`${n}/5`" :disabled="saving" class="sr-only">
                <span class="inline-block border rounded px-3 py-2" :class="score === n ? 'border-primary bg-primary-50 text-primary' : 'border-gray-200'">{{ n }} ★</span>
              </label>
            </fieldset>
          </n-form-item>
          <n-form-item :label="$t('page.protocol.rating.evidence')">
            <n-select v-model:value="useId" :options="useOptions" clearable :placeholder="$t('page.protocol.rating.readingOnly')" />
          </n-form-item>
          <p class="mb-3 text-sm text-gray-500">
            {{ $t("page.protocol.rating.evidenceHint") }}
          </p>
          <n-form-item :label="$t('page.protocol.rating.conditions')">
            <n-input v-model:value="conditions" type="textarea" :maxlength="2000" :autosize="{ minRows: 2, maxRows: 5 }" />
          </n-form-item>
          <n-form-item :label="$t('page.protocol.rating.comment')">
            <n-input v-model:value="comment" type="textarea" :maxlength="4000" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
          <n-checkbox v-model:checked="share">
            {{ $t("page.protocol.rating.shareReview") }}
          </n-checkbox>
          <p class="my-2 text-sm text-gray-500">
            {{ $t("page.protocol.rating.shareHint") }}
          </p>
          <div class="flex flex-wrap gap-2">
            <n-button type="primary" attr-type="submit" :loading="saving" :disabled="!score">
              {{ $t("page.protocol.rating.save") }}
            </n-button>
            <n-button v-if="mine.rating?.active" :disabled="saving" @click="saveReview(false)">
              {{ $t("page.protocol.rating.withdraw") }}
            </n-button>
            <n-button :disabled="saving" @click="showReview = false">
              {{ $t("common.cancel") }}
            </n-button>
          </div>
        </n-form>
        <n-form v-if="showUse && auth.isLogin" class="mt-4 border rounded-lg p-4" label-placement="top" @submit.prevent="saveUse()">
          <h4>{{ $t("page.protocol.rating.confirmUse") }} · v{{ selectedVersion }}</h4>
          <p class="my-3 text-sm">
            {{ $t("page.protocol.rating.groupHint") }}
          </p>
          <p v-if="editingUse" class="mb-3 text-sm">
            {{ $t("page.protocol.rating.linkedRecords", { count: editingUse.record_ids.length }) }}
          </p>
          <n-form-item v-if="!editingUse" :label="$t('page.protocol.rating.records')">
            <n-select v-model:value="selectedRecords" multiple :options="recordOptions" />
          </n-form-item>
          <n-button v-if="!editingUse && moreRecords" text @click="loadRecords(false)">
            {{ $t("page.protocol.rating.loadMore") }}
          </n-button>
          <n-form-item :label="$t('page.protocol.rating.result')">
            <n-select v-model:value="outcome" :options="outcomes" />
          </n-form-item>
          <n-form-item :label="$t('page.protocol.rating.comment')">
            <n-input v-model:value="useComment" type="textarea" :maxlength="4000" :autosize="{ minRows: 2, maxRows: 6 }" />
          </n-form-item>
          <div class="space-y-3">
            <n-checkbox v-model:checked="isReal" class="!flex">
              {{ $t("page.protocol.rating.realConfirmation") }}
            </n-checkbox>
            <n-checkbox v-model:checked="usePublic" class="!flex">
              {{ $t("page.protocol.rating.shareUse") }}
            </n-checkbox>
          </div>
          <p class="my-2 text-sm text-gray-500">
            {{ $t("page.protocol.rating.shareHint") }}
          </p>
          <div class="flex flex-wrap gap-2">
            <n-button type="primary" attr-type="submit" :loading="saving" :disabled="!editingUse && !selectedRecords.length">
              {{ $t("page.protocol.rating.saveUse") }}
            </n-button>
            <n-button v-if="editingUse?.active" :disabled="saving" @click="saveUse(false)">
              {{ $t("page.protocol.rating.withdraw") }}
            </n-button>
            <n-button :disabled="saving" @click="showUse = false">
              {{ $t("common.cancel") }}
            </n-button>
          </div>
        </n-form>
        <details v-if="mine?.uses.length" class="mt-4">
          <summary class="cursor-pointer">
            {{ $t("page.protocol.rating.myUses") }}
          </summary>
          <div v-for="use in mine.uses" :key="use.id" class="flex flex-wrap items-center gap-2 border-b py-3">
            <span>{{ $t(`page.protocol.rating.outcome.${use.outcome}`) }} · {{ use.id.slice(0, 8) }} · r{{ use.revision }}</span>
            <span v-if="!use.eligible" class="text-gray-500">{{ $t("page.protocol.rating.excluded") }}</span>
            <n-button v-if="use.source_protocol_id === protocolId" size="small" :disabled="saving" @click="editUse(use)">
              {{ $t("common.edit") }}
            </n-button>
            <n-button v-else tag="a" :href="use.source_url" size="small">
              {{ $t("page.protocol.rating.source") }} · {{ use.source_name }}
            </n-button>
          </div>
        </details>
        <details v-if="mine?.history.length" class="mt-3">
          <summary class="cursor-pointer">
            {{ $t("page.protocol.rating.history") }}
          </summary>
          <div v-for="entry in mine.history" :key="entry.revision" class="border-b py-2">
            r{{ entry.revision }} · {{ entry.payload.score }}/5 · {{ entry.payload.active ? $t('page.protocol.rating.active') : $t('page.protocol.rating.withdrawn') }}
            <p class="whitespace-pre-wrap break-words">
              {{ entry.payload.comment }}
            </p>
          </div>
        </details>
        <h4 class="mb-2 mt-6">
          {{ $t("page.protocol.rating.reviews") }}
        </h4>
        <p v-if="!summary.reviews.length" class="text-gray-500">
          {{ $t("page.protocol.rating.noReviews") }}
        </p>
        <article v-for="entry in summary.reviews" :key="entry.id" class="border-b py-4">
          <div class="flex flex-wrap gap-2">
            <strong>{{ entry.author }}</strong><span>{{ entry.score }}/5</span><n-tag size="small">
              {{ $t(`page.protocol.rating.kind.${entry.kind}`) }}
            </n-tag><span class="text-gray-500">r{{ entry.revision }}</span>
          </div>
          <p class="mt-2 whitespace-pre-wrap break-words">
            {{ entry.comment }}
          </p>
          <p v-if="entry.conditions" class="mt-2 whitespace-pre-wrap break-words text-gray-500">
            {{ $t("page.protocol.rating.conditions") }}: {{ entry.conditions }}
          </p>
        </article>
        <details v-if="summary.feedback.length" class="mt-4">
          <summary class="cursor-pointer">
            {{ $t("page.protocol.rating.feedback") }}
          </summary>
          <article v-for="entry in summary.feedback" :key="entry.id" class="border-b py-3">
            {{ $t(`page.protocol.rating.outcome.${entry.outcome}`) }} <span v-if="!entry.is_real">· {{ $t("page.protocol.rating.excluded") }}</span>
            <p class="whitespace-pre-wrap break-words">
              {{ entry.comment }}
            </p>
          </article>
        </details>
      </template>
    </n-spin>
  </section>
</template>

<style scoped>
.protocol-rating :deep(.n-button) { max-width: 100%; min-height: 34px; height: auto; }
.protocol-rating :deep(.n-button__content) { white-space: normal; overflow-wrap: anywhere; padding-block: 6px; }
.protocol-rating :deep(.n-tag) { max-width: 100%; height: auto; }
.protocol-rating :deep(.n-tag__content) { white-space: normal; }
.rating-choice:focus-within { outline: 2px solid #1a79ff; outline-offset: 3px; border-radius: 4px; }
</style>
