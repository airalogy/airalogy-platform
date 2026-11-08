<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <n-button v-if="!example" size="small" :disabled="!content.trim()" data-testid="test-example-data" @click="start">
      {{ $t("editor.examplePreview.start") }}
    </n-button>
    <template v-else>
      <n-tag type="info">{{ $t("editor.examplePreview.title") }}</n-tag>
      <n-button size="small" @click="check">{{ $t("editor.examplePreview.check") }}</n-button>
      <n-button size="small" data-testid="exit-example-preview" @click="close">{{ $t("editor.examplePreview.exit") }}</n-button>
    </template>
  </div>
  <n-alert v-if="error" type="error">{{ error }}</n-alert>
  <div v-if="example" v-protocol-preview-assets="resolveAsset" data-testid="editor-example-form">
    <p>{{ $t("editor.examplePreview.hint", { count: filledCount }) }}</p>
    <p v-if="skipped.length" class="break-words">{{ $t("editor.examplePreview.skipped", { fields: skipped.join(", ") }) }}</p>
    <p v-if="validation" role="status">{{ validation }}</p>
    <aimd-recorder
      ref="recorder" v-model="example" :content="content" :validation-schema="schema"
      :locale="locale" :show-search="false" :request-collector-permission="denyCollector"
      @update:model-value="validation = ''"
    />
  </div>
  <aimd-recorder v-else-if="active && content.trim()" v-protocol-preview-assets="resolveAsset" :key="content" :content="content" :locale="locale"
                 :validation-schema="schema" :show-search="false" :request-collector-permission="denyCollector" />
</template>

<script setup lang="ts">
import type { AimdProtocolRecordData, AimdRecordValidationSchema } from "@airalogy/aimd-recorder"
import { vProtocolPreviewAssets } from "@/utils/protocolPreviewAssets"
import { AimdRecorder } from "@airalogy/aimd-recorder"
import { createExampleRecord } from "@airalogy/aimd-recorder/record"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { useI18n } from "vue-i18n"

const props = defineProps<{ resolveAsset: (path: string) => Promise<{ url: string } | null>, active: boolean, content: string, schema?: AimdRecordValidationSchema, assigned: string[], modelSource: string, assignerSource: string }>()
const { t, locale } = useI18n()
const recorder = ref<InstanceType<typeof AimdRecorder>>()
const example = ref<AimdProtocolRecordData>()
const skipped = ref<string[]>([])
const filledCount = ref(0)
const validation = ref("")
const error = ref("")
const denyCollector = () => false
function close() {
  example.value = undefined
  validation.value = ""
  error.value = ""
}
function start() {
  close()
  try {
    const result = createExampleRecord(parseAndExtract(props.content), {
      schema: props.schema,
      assignedFields: props.assigned,
      locale: locale.value,
    })
    filledCount.value = Object.keys(result.record.var).length
    skipped.value = result.skipped
    example.value = result.record
  }
  catch {
    error.value = t("editor.examplePreview.invalid")
  }
}
async function check() {
  const view = recorder.value
  const result = await view?.validate()
  if (view === recorder.value && result) {
    validation.value = result.valid ? t("editor.examplePreview.valid") : t("editor.examplePreview.issues", { count: result.issues.length })
  }
}
watch(() => [props.active, props.content, props.schema, props.assigned, props.modelSource, props.assignerSource], close)
</script>
