<script setup lang="ts">
import type { ResearchDocument } from "@/service/api/research-documents"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { fetchResearchFile } from "@/service/api/knowledge"
import { getResearchDocument } from "@/service/api/research-documents"
import { documentBrowseQuery, localDocumentDate } from "@/utils/documentBrowse"
import { AimdRecorderWysiwygSurface } from "@airalogy/aimd-recorder"
import { useI18n } from "vue-i18n"
import DocumentAudience from "./document-audience.vue"

const props = defineProps<{ id: string, previous: boolean, next: boolean, pending?: boolean }>()
const emit = defineEmits<{ previous: [], next: [], close: [] }>()
const { locale } = useI18n()
const { t } = useOrganizationTranslation()
const route = useRoute()
const doc = ref<ResearchDocument>()
const loading = ref(false)
const error = ref("")
const heading = ref<HTMLElement>()
const readerRoot = ref<HTMLElement>()
const denyCollector = () => false
let sequence = 0
async function load() {
  const ticket = ++sequence
  loading.value = true
  doc.value = undefined
  error.value = ""
  try {
    const result = await getResearchDocument(props.id)
    if (ticket === sequence) {
      doc.value = result
      await nextTick()
      if (ticket !== sequence)
        return
      if (readerRoot.value) {
        readerRoot.value.scrollTop = 0
        readerRoot.value.scrollIntoView({ block: "start" })
      }
      heading.value?.focus({ preventScroll: true })
    }
  }
  catch {
    if (ticket === sequence)
      error.value = t("page.researchDocuments.failed")
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
async function attachment(id: string) {
  try {
    // Read authorization is rechecked by the normal file API.
    const blob = await fetchResearchFile(id, "download")
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = doc.value?.files.find(file => file.id === id)?.filename || "material"
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  catch { error.value = t("page.researchDocuments.failed") }
}
watch(() => props.id, load, { immediate: true })
onBeforeUnmount(() => sequence++)
</script>

<template>
  <section ref="readerRoot" class="document-reader min-w-0 border rounded-xl bg-white p-3 sm:p-5" data-testid="document-reader" :aria-label="t('page.documentBrowse.reading')">
    <div class="reader-navigation mb-4 flex flex-wrap items-center gap-2 bg-white">
      <n-button size="small" @click="emit('close')">
        {{ t('page.documentBrowse.backList') }}
      </n-button>
      <n-button size="small" :disabled="!previous || pending || loading" data-testid="document-previous" @click="emit('previous')">
        {{ t('page.documentBrowse.previous') }}
      </n-button>
      <n-button size="small" :disabled="!next || pending || loading" data-testid="document-next" @click="emit('next')">
        {{ t('page.documentBrowse.next') }}
      </n-button>
      <router-link v-if="doc" :to="{ name: 'research-document-detail', params: { documentId: doc.id }, query: { ...documentBrowseQuery(route.query), browse: '1' } }" class="ml-auto text-primary" data-testid="document-open-editor">
        {{ t(doc.can_edit ? 'page.documentBrowse.edit' : 'page.documentBrowse.details') }}
      </router-link>
    </div>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }} <n-button @click="load">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <n-spin :show="loading">
      <template v-if="doc">
        <h2 ref="heading" tabindex="-1" class="aira-type-page-title break-words" data-testid="document-reader-title">
          {{ doc.title }}
        </h2>
        <p class="aira-type-meta">
          {{ t('page.documentBrowse.recordedDate') }}：{{ localDocumentDate(doc.occurred_at || doc.created_at) }} · {{ t('page.documentBrowse.updated') }}：{{ new Date(doc.updated_at).toLocaleString() }}
        </p>
        <document-audience compact :scope="doc" :name="doc.scope_name" />
        <div class="mt-4 min-w-0 overflow-x-auto">
          <aimd-recorder-wysiwyg-surface :key="doc.id" :content="doc.body" :model-value="doc.record_data" readonly :show-mode-switch="false" :locale="locale" :min-height="200" :request-collector-permission="denyCollector" />
        </div>
        <ul v-if="doc.files.length" class="mt-4 pl-5">
          <li v-for="file in doc.files" :key="file.id" class="break-words">
            <span v-if="file.unavailable">{{ t('page.researchDocuments.unavailable') }}</span>
            <n-button v-else text @click="attachment(file.id)">
              {{ file.filename }}
            </n-button>
          </li>
        </ul>
      </template>
    </n-spin>
  </section>
</template>

<style scoped>
/* The SDK enforces readonly state; this reading surface has no authoring toolbar. */
.document-reader :deep(.aimd-editor-toolbar) { display: none; }
.document-reader { scroll-margin-top: 90px; }
@media (min-width: 1024px) {
  .document-reader { max-height: calc(100dvh - 120px); overflow-y: auto; }
  .reader-navigation { position: sticky; top: 0; z-index: 5; padding-bottom: 8px; }
}
</style>
