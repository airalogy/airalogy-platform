<script setup lang="ts">
import type { DocumentTemplate, TemplateContent, TemplateScope } from "@/service/api/document-templates"
import type { DocumentPreview, ResearchDocument } from "@/service/api/research-documents"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { createDocumentTemplate, scopeKey, scopeParams, templateError, templateHistory, templateScopes, updateDocumentTemplate } from "@/service/api/document-templates"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import DocumentSelect from "./document-select.vue"
import SnapshotPreview from "./snapshot-preview.vue"

const props = defineProps<{ scope: ResearchLogScopeParams, template?: DocumentTemplate, copyTemplate?: DocumentTemplate, sourceDocument?: ResearchDocument }>()
const emit = defineEmits<{ close: [], saved: [DocumentTemplate] }>()
const { t, locale } = useI18n()
const dialog = useDialog()
const original = props.template || props.copyTemplate || props.sourceDocument
const form = reactive<TemplateContent>({ title: original?.title || "", description: props.template?.description || props.copyTemplate?.description || "", kind: original?.kind || "document", body: original?.body || "" })
const scopes = ref<TemplateScope[]>([])
const destination = ref(scopeKey(props.scope))
const key = createResearchDocumentId()
const mode = ref<"source" | "wysiwyg">("wysiwyg")
const error = ref("")
const busy = ref(false)
const preview = ref<DocumentPreview>()
const history = ref<Awaited<ReturnType<typeof templateHistory>>["items"]>()
const editable = computed(() => !props.template || (props.template.can_edit && !props.template.archived && !props.template.builtin))
const chosen = computed(() => scopes.value.find(s => scopeKey(s) === destination.value))
const scopeLabel = (s: TemplateScope) => `${t(`page.documentTemplates.${s.scope_type}`)}${s.name ? ` · ${s.name}` : ""}`
const options = computed(() => scopes.value.filter(s => s.can_write).map(s => ({ value: scopeKey(s), label: scopeLabel(s) })))
const initial = JSON.stringify(form)
function close() {
  if (busy.value)
    return
  if (editable.value && JSON.stringify(form) !== initial) {
    dialog.warning({ title: t("page.documentTemplates.unsaved"), content: t("page.documentTemplates.discardHint"), positiveText: t("common.confirm"), negativeText: t("common.cancel"), onPositiveClick: () => emit("close") })
    return
  }
  emit("close")
}
watch([form, destination], () => {
  preview.value = undefined
}, { deep: true })
async function save(confirm = false) {
  if (!editable.value || busy.value || (!props.template && !chosen.value?.can_write))
    return
  busy.value = true
  error.value = ""
  try {
    const result = props.template
      ? await updateDocumentTemplate(props.template.id, { ...form, expected_revision: props.template.revision, preview_digest: confirm ? preview.value?.preview_digest : undefined })
      : await createDocumentTemplate({ ...form, ...scopeParams(chosen.value!), id: key, source_template_id: props.copyTemplate?.id, source_template_revision: props.copyTemplate?.revision, source_document_id: props.sourceDocument?.id, source_revision: props.sourceDocument?.revision, preview_digest: confirm ? preview.value?.preview_digest : undefined })
    if ("id" in result)
      emit("saved", result)
    else
      preview.value = result
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
  finally { busy.value = false }
}
async function loadHistory() {
  if (!props.template)
    return
  try {
    history.value = (await templateHistory(props.template.id)).items
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
}
onMounted(async () => {
  try {
    scopes.value = (await templateScopes()).items
    if (!props.template && !chosen.value?.can_write)
      destination.value = "personal"
  }
  catch (err) { error.value = templateError(err, t("page.researchDocuments.failed")) }
})
</script>

<template>
  <n-modal :show="true" preset="card" class="aira-dialog template-editor-dialog" :title="t(template ? 'page.documentTemplates.edit' : 'page.documentTemplates.create')" :mask-closable="false" data-testid="template-editor-dialog" @update:show="close">
    <n-alert v-if="error" type="error" role="alert" class="mb-4">
      {{ error }}
    </n-alert>
    <p class="aira-type-meta mb-4">
      {{ t('page.documentTemplates.safetyHint') }}
    </p>
    <n-form label-placement="top" :disabled="!editable || busy">
      <n-form-item :label="t('page.documentTemplates.name')" required>
        <n-input v-model:value="form.title" maxlength="512" data-testid="template-title" />
      </n-form-item>
      <n-form-item :label="t('page.documentTemplates.description')">
        <n-input v-model:value="form.description" maxlength="2000" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
      </n-form-item>
      <n-form-item v-if="!template" :label="t('page.documentTemplates.shareScope')" required>
        <document-select v-model:value="destination" :options="options" :label="t('page.documentTemplates.shareScope')" :disabled="busy" data-testid="template-scope" />
      </n-form-item>
      <p v-else class="aira-type-meta mb-3">
        {{ t(`page.documentTemplates.${template.scope_type}`) }} · {{ t('page.documentTemplates.version', { version: template.revision }) }}
      </p>
      <p class="aira-type-meta mb-3">
        {{ t('page.documentTemplates.sharingHint') }}
      </p>
      <n-form-item :label="t('page.documentTemplates.body')">
        <div class="template-body min-w-0 w-full" data-testid="template-body">
          <div v-if="!editable" class="mb-2 flex gap-2">
            <n-button size="small" :type="mode === 'wysiwyg' ? 'primary' : 'default'" @click="mode = 'wysiwyg'">
              {{ t('page.researchDocuments.visual') }}
            </n-button>
            <n-button size="small" :type="mode === 'source' ? 'primary' : 'default'" data-testid="template-source-mode" @click="mode = 'source'">
              {{ t('page.researchDocuments.source') }}
            </n-button>
          </div>
          <aimd-editor v-model="form.body" v-model:mode="mode" :readonly="!editable || busy" :show-toolbar="editable" :locale="locale" :min-height="280" :keep-inactive-editors-mounted="false" />
        </div>
      </n-form-item>
    </n-form>
    <template v-if="preview">
      <p class="mb-2 font-medium">
        {{ t('page.documentTemplates.confirmHint', { scope: chosen ? scopeLabel(chosen) : t(`page.documentTemplates.${template?.scope_type || 'personal'}`) }) }}
      </p>
      <snapshot-preview :snapshot="preview.snapshot" />
    </template>
    <div class="mt-4 flex flex-wrap justify-end gap-2">
      <n-button v-if="template && !template.builtin" @click="loadHistory">
        {{ t('page.researchDocuments.history') }}
      </n-button>
      <n-button :disabled="busy" @click="close">
        {{ t('common.cancel') }}
      </n-button>
      <n-button v-if="editable" type="primary" :disabled="!form.title.trim() || (!template && !chosen?.can_write)" :loading="busy" data-testid="template-save" @click="save(Boolean(preview))">
        {{ t(preview ? 'page.documentTemplates.confirmSave' : 'page.documentTemplates.previewSave') }}
      </n-button>
    </div>
    <section v-if="history" class="mt-5 max-h-64 overflow-y-auto" :aria-label="t('page.researchDocuments.history')">
      <details v-for="item in history" :key="item.revision" class="border-b p-3">
        <summary>{{ t('page.documentTemplates.version', { version: item.revision }) }} · {{ new Date(item.created_at).toLocaleString() }}</summary>
        <snapshot-preview :snapshot="{ ...item.snapshot }" />
      </details>
    </section>
  </n-modal>
</template>

<style scoped>
.template-editor-dialog { width: min(1000px, calc(100vw - 32px)); }
.template-body { overflow: hidden; border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px; }
</style>
