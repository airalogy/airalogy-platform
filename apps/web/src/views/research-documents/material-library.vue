<script setup lang="ts">
import type { Material } from "@/service/api/research-documents"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { fetchResearchFile } from "@/service/api/knowledge"
import {
  createResearchDocument,
  extractResearchMaterial,
  listResearchMaterials,
  uploadResearchMaterial,
} from "@/service/api/research-documents"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { useI18n } from "vue-i18n"

const props = defineProps<{ scope: ResearchLogScopeParams, attach?: boolean }>()
const emit = defineEmits<{ attach: [file: Material] }>()
const { t } = useI18n()
const router = useRouter()
const items = ref<Material[]>([])
const total = ref(0)
const page = ref(1)
const q = ref("")
const canUpload = ref(false)
const busy = ref(false)
const error = ref("")
const sourceNote = ref("")
const occurredAt = ref<number | null>(null)
const fileInput = ref<HTMLInputElement>()
const selected = ref<File>()
const uploadKey = ref("")
const preview = ref<{ url: string, type: string, name: string }>()
const extracted = ref<{ file: Material, text: string, truncated: boolean, id: string }>()
let generation = 0
function failure(err: unknown) {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  error.value = typeof detail === "string" ? detail : t("page.researchDocuments.failed")
}
function search() {
  page.value = 1
  void load()
}
async function load() {
  const ticket = ++generation
  error.value = ""
  try {
    const data = await listResearchMaterials(props.scope, q.value, page.value)
    if (ticket !== generation)
      return
    items.value = data.items
    total.value = data.total_count
    canUpload.value = data.can_upload
  }
  catch (err) {
    if (ticket === generation)
      failure(err)
  }
}
async function upload() {
  if (!selected.value || busy.value)
    return
  const scopeKey = JSON.stringify(props.scope)
  busy.value = true
  error.value = ""
  try {
    const item = await uploadResearchMaterial(
      props.scope,
      selected.value,
      uploadKey.value,
      sourceNote.value,
      occurredAt.value ? new Date(occurredAt.value).toISOString() : undefined,
    )
    if (scopeKey !== JSON.stringify(props.scope))
      return
    selected.value = undefined
    sourceNote.value = ""
    occurredAt.value = null
    if (fileInput.value)
      fileInput.value.value = ""
    await load()
    if (props.attach)
      emit("attach", item)
  }
  catch (err) {
    failure(err)
  }
  finally {
    busy.value = false
  }
}
function selectFile(event: Event) {
  selected.value = (event.target as HTMLInputElement).files?.[0]
  uploadKey.value = createResearchDocumentId()
}
function closePreview() {
  if (preview.value)
    URL.revokeObjectURL(preview.value.url)
  preview.value = undefined
}
async function openFile(item: Material, mode: "preview" | "download") {
  const scopeKey = JSON.stringify(props.scope)
  busy.value = true
  error.value = ""
  try {
    const blob = await fetchResearchFile(item.id, mode)
    if (scopeKey !== JSON.stringify(props.scope))
      return
    const url = URL.createObjectURL(blob)
    if (mode === "preview" && item.previewable) {
      closePreview()
      preview.value = { url, type: item.content_type, name: item.filename }
    }
    else {
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = item.filename
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  }
  catch (err) {
    failure(err)
  }
  finally {
    busy.value = false
  }
}
async function extract(item: Material) {
  const scopeKey = JSON.stringify(props.scope)
  busy.value = true
  error.value = ""
  try {
    const result = await extractResearchMaterial(item.id)
    if (scopeKey !== JSON.stringify(props.scope))
      return
    extracted.value = {
      file: item,
      text: result.text,
      truncated: result.truncated,
      id: createResearchDocumentId(),
    }
  }
  catch (err) {
    failure(err)
  }
  finally {
    busy.value = false
  }
}
async function createFromText() {
  if (!extracted.value)
    return
  busy.value = true
  try {
    const result = await createResearchDocument({
      ...props.scope,
      id: extracted.value.id,
      title: extracted.value.file.filename,
      body: extracted.value.text,
      file_ids: [extracted.value.file.id],
    })
    extracted.value = undefined
    await router.push({ name: "research-document-detail", params: { documentId: result.id } })
  }
  catch (err) {
    failure(err)
  }
  finally {
    busy.value = false
  }
}
watch(
  () => JSON.stringify(props.scope),
  () => {
    items.value = []
    page.value = 1
    selected.value = undefined
    extracted.value = undefined
    closePreview()
    void load()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  generation++
  closePreview()
})
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="research-materials">
    <p class="aira-type-body aira-text-secondary">
      {{ t("page.researchDocuments.materialHint") }}
    </p>
    <n-alert v-if="error" type="error" role="alert">
      {{ error }}
      <n-button text @click="load">
        {{ t("page.researchDocuments.retry") }}
      </n-button>
    </n-alert>
    <div class="flex flex-wrap gap-2">
      <n-input
        v-model:value="q"
        :placeholder="t('common.search')"
        :input-props="{ 'aria-label': t('common.search') }"
        class="max-w-sm"
        @keyup.enter="search"
      />
      <n-button
        @click="search"
      >
        {{ t("common.search") }}
      </n-button>
    </div>
    <n-card v-if="canUpload" size="small" :title="t('page.researchDocuments.upload')">
      <div class="space-y-3">
        <input
          ref="fileInput"
          type="file"
          :aria-label="t('page.researchDocuments.upload')"
          :disabled="busy"
          class="max-w-full"
          data-testid="material-upload-input"
          @change="selectFile"
        >
        <n-input
          v-model:value="sourceNote"
          :placeholder="t('page.researchDocuments.sourceNote')"
          :input-props="{ 'aria-label': t('page.researchDocuments.sourceNote') }"
        />
        <n-date-picker
          v-model:value="occurredAt"
          type="datetime"
          clearable
          :placeholder="t('page.researchDocuments.occurredAt')"
        />
        <n-button
          type="primary"
          :disabled="!selected"
          :loading="busy"
          data-testid="material-upload-confirm"
          @click="upload"
        >
          {{ t("page.researchDocuments.upload") }}
        </n-button>
      </div>
    </n-card>
    <n-empty
      v-if="!items.length && !error"
      :description="t('page.researchDocuments.materialEmpty')"
    />
    <article v-for="item in items" :key="item.id" class="material-row">
      <div class="min-w-0 flex-1">
        <h3 class="aira-type-card-title m-0 break-all">
          {{ item.filename }}
        </h3>
        <p class="aira-type-meta mt-1">
          {{ Math.ceil(item.size_bytes / 1024) }} KB · {{ t("page.researchDocuments.uploadedAt") }}
          {{ item.created_at ? new Date(item.created_at).toLocaleString() : "" }}
        </p>
        <p v-if="item.occurred_at" class="aira-type-meta">
          {{ t("page.researchDocuments.occurredAt") }}
          {{ new Date(item.occurred_at).toLocaleString() }}
        </p>
        <p v-if="item.source_note" class="whitespace-pre-wrap break-words">
          {{ item.source_note }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button v-if="attach" size="small" :disabled="busy" @click="emit('attach', item)">
          {{ t("page.researchDocuments.attach") }}
        </n-button>
        <n-button
          v-if="item.previewable"
          size="small"
          :disabled="busy"
          @click="openFile(item, 'preview')"
        >
          {{ t("page.researchDocuments.preview") }}
        </n-button>
        <n-button size="small" :disabled="busy" @click="openFile(item, 'download')">
          {{ t("page.researchDocuments.download") }}
        </n-button>
        <n-button v-if="canUpload" size="small" :disabled="busy" @click="extract(item)">
          {{ t("page.researchDocuments.extract") }}
        </n-button>
      </div>
    </article>
    <n-pagination
      v-if="total > 50"
      v-model:page="page"
      :item-count="total"
      :page-size="50"
      @update:page="load"
    />
    <n-modal
      :show="Boolean(preview)"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 64rem"
      :title="preview?.name"
      @update:show="closePreview"
    >
      <template v-if="preview">
        <img
          v-if="preview.type.startsWith('image/')"
          :src="preview.url"
          :alt="preview.name"
          class="max-h-70vh max-w-full object-contain"
        >
        <iframe
          v-else
          :src="preview.url"
          :title="preview.name"
          sandbox=""
          class="h-70vh w-full border-0"
        />
      </template>
    </n-modal>
    <n-modal
      :show="Boolean(extracted)"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 56rem"
      :title="t('page.researchDocuments.extract')"
      :mask-closable="false"
      @update:show="extracted = undefined"
    >
      <template v-if="extracted">
        <n-alert type="info" class="mb-4">
          {{ t("page.researchDocuments.extractionHint") }}
        </n-alert>
        <p v-if="extracted.truncated">
          {{ t("page.researchDocuments.truncated") }}
        </p>
        <n-input
          v-model:value="extracted.text"
          type="textarea"
          :autosize="{ minRows: 10, maxRows: 22 }"
          :placeholder="t('page.researchDocuments.extractionEmpty')"
        />
        <n-button
          type="primary"
          :disabled="!extracted.text.trim()"
          :loading="busy"
          class="mt-4"
          @click="createFromText"
        >
          {{ t("page.researchDocuments.useText") }}
        </n-button>
      </template>
    </n-modal>
  </section>
</template>

<style scoped>
.material-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--n-border-color, #e5e7eb);
  border-radius: 12px;
}
</style>
