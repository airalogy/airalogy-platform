<script setup lang="ts">
import type { WorkEvidence } from "@/service/api/project-work"
import { projectWorkSources, workDocumentSnapshot, workProtocolSnapshot } from "@/service/api/project-work"
import SnapshotPreview from "@/views/research-documents/snapshot-preview.vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, modelValue: WorkEvidence[], editable?: boolean }>()
const emit = defineEmits<{ "update:modelValue": [value: WorkEvidence[]] }>()
const { t } = useI18n()
const choosing = ref(false)
const kind = ref("document")
const q = ref("")
const options = ref<WorkEvidence[]>([])
const loading = ref(false)
const error = ref("")
const external = ref("")
const label = ref("")
const snapshot = ref<Record<string, unknown>>()
const types = [
  "document",
  "protocol",
  "record",
  "file",
  "analysis",
  "research_task",
  "external",
] as const
let sequence = 0
async function search() {
  const ticket = ++sequence
  options.value = []
  if (kind.value === "external")
    return
  loading.value = true
  error.value = ""
  try {
    const result = await projectWorkSources(props.projectId, kind.value, q.value)
    if (ticket === sequence)
      options.value = result.items
  }
  catch {
    error.value = t("page.projectWork.failed")
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
function choose() {
  choosing.value = true
  void search()
}
function add(item: WorkEvidence) {
  if (
    !props.modelValue.some(
      link => link.kind === item.kind && link.id === item.id && link.version === item.version,
    )
  ) {
    emit("update:modelValue", [...props.modelValue, item])
  }
  choosing.value = false
}
function addExternal() {
  try {
    const url = new URL(external.value)
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password)
      throw new Error("URL")
    add({
      kind: "external",
      id: url.href,
      href: url.href,
      label: label.value || url.hostname,
      version: "",
      available: true,
    })
  }
  catch {
    error.value = t("page.projectWork.invalidUrl")
  }
}
async function openDocument(item: WorkEvidence) {
  try {
    const fetchSnapshot = item.kind === "protocol" ? workProtocolSnapshot : workDocumentSnapshot
    snapshot.value = (await fetchSnapshot(props.projectId, item.id!, item.version!)).snapshot
  }
  catch {
    error.value = t("page.projectWork.sourceUnavailable")
  }
}
watch(kind, search)
</script>

<template>
  <div class="min-w-0 space-y-2">
    <div
      v-for="(item, index) in modelValue"
      :key="`${item.kind}:${item.id}:${item.version}:${index}`"
      class="flex items-start gap-2 rounded bg-gray-50 p-2 text-sm"
    >
      <span v-if="item.available === false" class="text-gray-500">{{
        t("page.projectWork.sourceUnavailable")
      }}</span>
      <button
        v-else-if="['document', 'protocol'].includes(item.kind)"
        type="button"
        class="min-w-0 break-words text-left text-primary"
        @click="openDocument(item)"
      >
        {{ item.label || item.id }} · v{{ item.version }}
      </button>
      <a
        v-else
        :href="item.href || (item.kind === 'external' ? item.id : undefined)"
        target="_blank"
        rel="noopener noreferrer"
        class="min-w-0 break-words text-primary"
      >
        {{ item.label || item.id }}<span v-if="item.version"> · v{{ item.version }}</span>
      </a>
      <n-button
        v-if="editable"
        size="tiny"
        quaternary
        class="ml-auto shrink-0"
        :aria-label="t('common.delete')"
        @click="
          emit(
            'update:modelValue',
            modelValue.filter((_, i) => i !== index),
          )
        "
      >
        {{ t("common.delete") }}
      </n-button>
    </div>
    <n-button
      v-if="editable"
      size="small"
      @click="choose"
    >
      + {{ t("page.projectWork.linkEvidence") }}
    </n-button>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <n-modal
      v-model:show="choosing"
      preset="card"
      class="aira-dialog max-w-2xl"
      :title="t('page.projectWork.linkEvidence')"
      :aria-label="t('page.projectWork.linkEvidence')"
    >
      <p class="text-gray-500">{{ t("page.projectWork.evidenceHint") }}</p>
      <n-select
        v-model:value="kind"
        :options="types.map(value => ({ value, label: t(`page.projectWork.sources.${value}`) }))"
      />
      <form v-if="kind === 'external'" class="mt-3 space-y-3" @submit.prevent="addExternal">
        <n-input
          v-model:value="external"
          :placeholder="t('page.projectWork.url')"
          aria-label="URL"
        />
        <n-input v-model:value="label" :placeholder="t('page.projectWork.linkLabel')" />
        <n-button attr-type="submit" type="primary">{{ t("common.add") }}</n-button>
      </form>
      <template v-else>
        <form class="my-3 flex gap-2" @submit.prevent="search">
          <n-input v-model:value="q" :placeholder="t('common.search')" />
          <n-button attr-type="submit" :loading="loading">{{ t("common.search") }}</n-button>
        </form>
        <div class="max-h-60vh overflow-y-auto space-y-2">
          <button
            v-for="item in options"
            :key="`${item.id}:${item.version}`"
            type="button"
            class="w-full border border-gray-200 rounded p-3 text-left hover:bg-blue-50"
            @click="add(item)"
          >
            {{ item.label || item.id }}<span v-if="item.version"> · v{{ item.version }}</span>
          </button>
          <p v-if="!loading && !options.length">{{ t("page.projectWork.noSources") }}</p>
        </div>
      </template>
    </n-modal>
    <n-modal
      :show="Boolean(snapshot)"
      preset="card"
      class="aira-dialog max-w-3xl"
      :title="t('page.projectWork.exactSnapshot')"
      :aria-label="t('page.projectWork.exactSnapshot')"
      @update:show="snapshot = undefined"
    >
      <snapshot-preview :snapshot="snapshot" />
    </n-modal>
  </div>
</template>
