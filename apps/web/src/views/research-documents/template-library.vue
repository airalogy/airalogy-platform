<script setup lang="ts">
import type { DocumentTemplate } from "@/service/api/document-templates"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { archiveDocumentTemplate, listDocumentTemplates, scopeKey, templateError } from "@/service/api/document-templates"
import { useI18n } from "vue-i18n"
import TemplateEditorDialog from "./template-editor-dialog.vue"

const props = defineProps<{ scope: ResearchLogScopeParams }>()
const { t } = useI18n()
const router = useRouter()
const items = ref<DocumentTemplate[]>([])
const total = ref(0)
const page = ref(1)
const q = ref("")
const archived = ref(false)
const canWrite = ref(false)
const loading = ref(false)
const error = ref("")
const notice = ref("")
const editing = ref<DocumentTemplate | null>()
const copying = ref<DocumentTemplate>()
let sequence = 0
async function load(reset = false) {
  if (reset)
    page.value = 1
  const ticket = ++sequence
  loading.value = true
  error.value = ""
  try {
    const result = await listDocumentTemplates(props.scope, { q: q.value, page: page.value, archived: archived.value })
    if (ticket !== sequence)
      return
    items.value = result.items
    total.value = result.total_count
    canWrite.value = result.can_write
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
async function archive(item: DocumentTemplate) {
  try {
    await archiveDocumentTemplate(item, !item.archived)
    await load()
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
}
function saved(item: DocumentTemplate) {
  editing.value = undefined
  copying.value = undefined
  notice.value = t("page.documentTemplates.saved")
  if ((item.project_id ? `project:${item.project_id}` : item.lab_id ? `lab:${item.lab_id}` : "personal") !== scopeKey(props.scope)) {
    void router.push({ name: "research-documents", query: { tab: "templates", ...(item.project_id ? { project_id: item.project_id } : item.lab_id ? { lab_id: item.lab_id } : {}) } })
  }
  else {
    void load()
  }
}
watch(() => JSON.stringify(props.scope), () => {
  editing.value = undefined
  void load(true)
}, { immediate: true })
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="template-library">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="aira-type-section-title">
        {{ t('page.documentTemplates.library') }}
      </h2>
      <n-button v-if="canWrite" type="primary" data-testid="new-document-template" @click="editing = null">
        {{ t('page.documentTemplates.create') }}
      </n-button>
    </div>
    <p class="aira-type-meta">
      {{ t('page.documentTemplates.libraryHint') }}
    </p>
    <div class="flex flex-wrap items-center gap-3">
      <n-input v-model:value="q" class="max-w-sm" :placeholder="t('common.search')" @keyup.enter="load(true)" />
      <n-button @click="load(true)">
        {{ t('common.search') }}
      </n-button>
      <n-checkbox v-model:checked="archived" @update:checked="load(true)">
        {{ t('page.documentTemplates.archived') }}
      </n-checkbox>
    </div>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }} <n-button @click="load()">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <n-alert v-if="notice" type="success" role="status">
      {{ notice }}
    </n-alert>
    <n-spin :show="loading">
      <n-empty v-if="!loading && !items.length" :description="t('page.documentTemplates.empty')" />
      <div class="space-y-3">
        <article v-for="item in items" :key="item.id" class="flex flex-wrap items-start gap-3 border border-gray-200 rounded-xl p-4" :data-testid="`template-${item.id}`">
          <div class="min-w-0 flex-1">
            <h3 class="aira-type-card-title break-words">
              {{ item.title }}
            </h3>
            <p class="aira-type-meta whitespace-pre-wrap break-words">
              {{ item.description }}
            </p>
            <span class="aira-type-meta">{{ t('page.documentTemplates.version', { version: item.revision }) }}</span>
          </div>
          <n-button @click="editing = item">
            {{ t(item.can_edit && !item.archived ? 'page.documentTemplates.edit' : 'page.documentTemplates.view') }}
          </n-button>
          <n-button v-if="!item.archived" @click="copying = item">
            {{ t('page.documentTemplates.copyToScope') }}
          </n-button>
          <n-popconfirm v-if="item.can_edit" @positive-click="archive(item)">
            <template #trigger>
              <n-button>{{ t(item.archived ? 'page.documentTemplates.restore' : 'page.documentTemplates.archive') }}</n-button>
            </template>
            {{ t(item.archived ? 'page.documentTemplates.restoreHint' : 'page.documentTemplates.archiveHint') }}
          </n-popconfirm>
        </article>
      </div>
    </n-spin>
    <n-pagination v-if="total > 20" v-model:page="page" :item-count="total" :page-size="20" @update:page="load()" />
    <template-editor-dialog v-if="copying" :scope="scope" :copy-template="copying" @close="copying = undefined" @saved="saved" />
    <template-editor-dialog v-if="editing !== undefined" :scope="scope" :template="editing || undefined" @close="editing = undefined" @saved="saved" />
  </section>
</template>
