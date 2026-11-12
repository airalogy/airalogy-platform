<script setup lang="ts">
import type { DocumentTemplate, TemplateScope } from "@/service/api/document-templates"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { builtinTemplates, getDocumentTemplate, listDocumentTemplates, scopeKey, scopeParams, templateError, templateScopes } from "@/service/api/document-templates"
import { createResearchDocument, researchProtocolSources } from "@/service/api/research-documents"
import { useAuthStore } from "@/store/modules/auth"
import { documentDateInstant, localDocumentDate } from "@/utils/documentBrowse"
import { recentTemplateIds } from "@/utils/documentTemplateRecents"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { useI18n } from "vue-i18n"
import DocumentAudience from "./document-audience.vue"
import DocumentSelect from "./document-select.vue"

const props = defineProps<{ scope: ResearchLogScopeParams }>()
const emit = defineEmits<{ close: [] }>()
const { locale } = useI18n()
const { t } = useOrganizationTranslation()
const router = useRouter()
const scopes = ref<TemplateScope[]>([])
const source = ref("builtin")
const browsingTemplates = ref(false)
const recent = ref<DocumentTemplate[]>([])
const auth = useAuthStore()
const recentKey = computed(() => `document-template-recents:${auth.userInfo.id}`)
const items = ref<DocumentTemplate[]>([])
const selected = ref<DocumentTemplate>()
const q = ref("")
const page = ref(1)
const total = ref(0)
const title = ref("")
const openedAt = new Date().toISOString()
const recordedDate = ref(localDocumentDate(openedAt))
const suggestedTitle = computed(() => selected.value?.id !== "builtin:blank" && selected.value?.title ? selected.value.title : t("page.researchDocuments.untitled"))
const busy = ref(false)
const loading = ref(false)
const error = ref("")
const protocol = ref<string>()
const protocols = ref<{ label: string, value: string }[]>([])
let sequence = 0
let pending: { key: string, id: string } | undefined
const label = (s: TemplateScope) => `${t(`page.documentTemplates.${s.scope_type}`)}${s.name ? ` · ${s.name}` : ""}`
const options = computed(() => [
  { value: "builtin", label: t("page.documentTemplates.builtin") },
  ...scopes.value.map(s => ({ value: scopeKey(s), label: label(s) })),
  ...(props.scope.project_id ? [{ value: "protocol", label: t("page.researchDocuments.fromProtocol") }] : []),
])
const destinationLabel = computed(() => {
  const s = scopes.value.find(s => scopeKey(s) === scopeKey(props.scope))
  return s ? label(s) : t(`page.documentTemplates.${props.scope.scope_type}`)
})
async function loadRecent() {
  let ids: string[] = []
  try {
    ids = recentTemplateIds(localStorage.getItem(recentKey.value))
  }
  catch { return }
  const results = await Promise.allSettled(ids.map(getDocumentTemplate))
  recent.value = results.flatMap(result => result.status === "fulfilled" && !result.value.archived ? [result.value] : [])
}
function rememberTemplate() {
  if (!selected.value || selected.value.builtin || source.value === "protocol")
    return
  try {
    const ids = recentTemplateIds(localStorage.getItem(recentKey.value))
    localStorage.setItem(recentKey.value, JSON.stringify([selected.value.id, ...ids.filter(id => id !== selected.value!.id)].slice(0, 4)))
  }
  catch { /* Browser storage is optional; creation still succeeds. */ }
}
async function chooseSource(library: boolean) {
  browsingTemplates.value = library
  source.value = library ? scopeKey(props.scope) : "builtin"
  q.value = ""
  await load(true)
}
async function load(reset = false) {
  if (reset)
    page.value = 1
  const ticket = ++sequence
  selected.value = undefined
  protocol.value = undefined
  error.value = ""
  loading.value = true
  try {
    if (source.value === "protocol") {
      const result = await researchProtocolSources(props.scope.project_id!, q.value)
      if (ticket !== sequence)
        return
      protocols.value = result.items.map(p => ({ value: p.id, label: `${p.name} · ${p.version}` }))
      protocol.value = undefined
    }
    else {
      const scope = scopes.value.find(s => scopeKey(s) === source.value)
      const result = source.value === "builtin" ? await builtinTemplates(locale.value) : await listDocumentTemplates(scopeParams(scope!), { q: q.value, page: page.value })
      if (ticket !== sequence)
        return
      items.value = result.items
      total.value = "total_count" in result ? Number(result.total_count) : result.items.length
      selected.value = result.items[0]
    }
  }
  catch (err) {
    if (ticket === sequence)
      error.value = templateError(err, t("page.researchDocuments.failed"))
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
async function create() {
  if (busy.value || loading.value || (!selected.value && !protocol.value))
    return
  if (!documentDateInstant(recordedDate.value, openedAt)) {
    error.value = t("page.documentBrowse.invalidDate")
    return
  }
  busy.value = true
  error.value = ""
  const data = {
    ...scopeParams(props.scope),
    occurred_at: documentDateInstant(recordedDate.value, openedAt),
    title: title.value.trim() || suggestedTitle.value,
    ...(source.value === "protocol"
      ? { source_protocol_version_id: protocol.value, kind: "experiment" as const }
      : { source_template_id: selected.value!.id, source_template_revision: selected.value!.revision, template_locale: locale.value }),
  }
  const signature = JSON.stringify(data)
  if (pending?.key !== signature)
    pending = { key: signature, id: createResearchDocumentId() }
  try {
    const result = await createResearchDocument({ ...data, id: pending.id })
    rememberTemplate()
    await router.push({ name: "research-document-detail", params: { documentId: result.id } })
    emit("close")
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
  finally { busy.value = false }
}
onMounted(async () => {
  try {
    scopes.value = (await templateScopes()).items
    await Promise.all([load(), loadRecent()])
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
})
onBeforeUnmount(() => sequence++)
</script>

<template>
  <n-modal :show="true" preset="card" class="aira-dialog new-document-dialog" :title="t('page.researchDocuments.new')" :mask-closable="!busy" data-testid="new-document-dialog" @update:show="!busy && emit('close')">
    <document-audience :scope="scope" :name="destinationLabel" class="mb-3" />
    <n-alert v-if="error" type="error" role="alert" class="mb-3">
      {{ error }} <n-button @click="load()">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <n-form label-placement="top" :disabled="busy">
      <div class="mb-4 flex flex-wrap gap-2">
        <n-button :type="!browsingTemplates ? 'primary' : 'default'" data-testid="document-common-templates" @click="chooseSource(false)">
          {{ t('page.documentUx.commonTemplates') }}
        </n-button>
        <n-button :type="browsingTemplates ? 'primary' : 'default'" data-testid="document-browse-templates" @click="chooseSource(true)">
          {{ t('page.documentUx.browseTemplates') }}
        </n-button>
      </div>
      <n-form-item v-if="browsingTemplates" :label="t('page.documentTemplates.source')">
        <document-select v-model:value="source" :options="options" :label="t('page.documentTemplates.source')" :disabled="busy" data-testid="document-template-source" @update:value="load(true)" />
      </n-form-item>
      <div v-if="source !== 'builtin' && source !== 'protocol'" class="mb-4 flex gap-2">
        <n-input v-model:value="q" :placeholder="t('common.search')" @keyup.enter="load(true)" />
        <n-button @click="load(true)">
          {{ t('common.search') }}
        </n-button>
      </div>
      <n-spin :show="loading">
        <template v-if="source === 'protocol'">
          <p class="aira-type-meta mb-3">
            {{ t('page.researchDocuments.protocolCopyHint') }}
          </p>
          <n-select v-model:value="protocol" :options="protocols" filterable :placeholder="t('common.search')" />
        </template>
        <template v-else>
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2" role="group" :aria-label="t('page.documentTemplates.choose')">
            <button v-for="item in items" :key="item.id" type="button" class="template-choice" :class="{ 'template-choice--selected': selected?.id === item.id }" :aria-pressed="selected?.id === item.id" :disabled="busy" :data-testid="`choose-template-${item.id}`" @click="selected = item">
              <strong class="block break-words">{{ item.title }}</strong>
              <span class="aira-type-meta block break-words">{{ item.description }}</span>
            </button>
          </div>
          <n-empty v-if="!loading && !items.length" :description="t('page.documentTemplates.empty')" />
          <n-pagination v-if="total > 20" v-model:page="page" :item-count="total" :page-size="20" class="mt-3" @update:page="load()" />
          <section v-if="!browsingTemplates && recent.length" class="mt-4" data-testid="recent-document-templates">
            <h3 class="aira-type-card-title mb-2">
              {{ t('page.documentUx.recentTemplates') }}
            </h3>
            <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <button v-for="item in recent" :key="item.id" type="button" class="template-choice" :class="{ 'template-choice--selected': selected?.id === item.id }" :aria-pressed="selected?.id === item.id" :disabled="busy" @click="selected = item">
                <strong class="block break-words">{{ item.title }}</strong><span class="aira-type-meta block break-words">{{ item.description }}</span>
              </button>
            </div>
          </section>
          <section v-if="selected?.body" class="mt-4 min-w-0 border rounded-lg p-3" data-testid="template-preview" :aria-label="t('page.documentTemplates.preview')">
            <h3 class="aira-type-card-title">
              {{ t('page.documentTemplates.preview') }} · {{ selected.title }}
            </h3>
            <aimd-editor v-if="selected.body" :key="selected.id" :model-value="selected.body" mode="wysiwyg" readonly :show-toolbar="false" :locale="locale" :min-height="160" />
            <p v-else class="aira-type-meta">
              {{ t('page.documentTemplates.blankHint') }}
            </p>
          </section>
        </template>
      </n-spin>
      <n-form-item class="mt-4" :label="t('page.researchDocuments.titleLabel')">
        <n-input v-model:value="title" :placeholder="suggestedTitle" maxlength="512" data-testid="new-document-title" />
      </n-form-item>
      <details class="mb-4" data-testid="new-document-options">
        <summary class="cursor-pointer text-gray-600">
          {{ t('page.documentUx.creationDetails') }} · {{ recordedDate }}
        </summary>
        <n-form-item class="mt-3" :label="t('page.documentBrowse.recordedDate')">
          <input v-model="recordedDate" type="date" required class="max-w-full min-h-10 border rounded px-3" data-testid="new-document-date">
        </n-form-item>
      </details>
    </n-form>
    <div class="flex flex-wrap justify-end gap-2">
      <n-button :disabled="busy" @click="emit('close')">
        {{ t('common.cancel') }}
      </n-button>
      <n-button type="primary" :loading="busy" :disabled="loading || (source === 'protocol' ? !protocol : !selected)" data-testid="create-document-confirm" @click="create">
        {{ t('page.documentTemplates.createDocument') }}
      </n-button>
    </div>
  </n-modal>
</template>

<style scoped>
.new-document-dialog { width: min(850px, calc(100vw - 32px)); }
.template-choice { border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: white; text-align: left; color: inherit; }
.template-choice:hover, .template-choice:focus-visible, .template-choice--selected { border-color: #1677ff; background: #eff6ff; }
.template-choice:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
</style>
