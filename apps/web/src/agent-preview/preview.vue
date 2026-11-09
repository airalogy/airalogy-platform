<script setup lang="ts">
import type { AimdProtocolRecordData } from "@airalogy/aimd-recorder"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { AimdRecorder } from "@airalogy/aimd-recorder"
import { createExampleRecord } from "@airalogy/aimd-recorder/record"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { computed, ref, watch } from "vue"

const zh = navigator.language.startsWith("zh")
const label = (cn: string, en: string) => zh ? cn : en
const source = ref("# Synthetic example\n\n{{var|measurement: float}}\n")
const mode = ref<"wysiwyg" | "source">("wysiwyg")
const values = ref<AimdProtocolRecordData>({ var: {}, step: {}, check: {}, quiz: {} })
const recorder = ref<InstanceType<typeof AimdRecorder>>()
const status = ref("")
const locale = computed(() => zh ? "zh-CN" : "en-US")
watch(source, () => {
  values.value = { var: {}, step: {}, check: {}, quiz: {} }
  status.value = ""
})
async function open(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || file.size > 1000000)
    return
  source.value = await file.text()
}
function example() {
  try {
    const result = createExampleRecord(parseAndExtract(source.value), { locale: locale.value })
    values.value = result.record
    status.value = `${label("仅用于预览；跳过字段", "Preview only; skipped fields")}: ${result.skipped.join(", ") || "—"}`
  }
  catch { status.value = label("请先修正 AIMD 语法", "Correct AIMD syntax first") }
}
async function validate() {
  const result = await recorder.value?.validate()
  status.value = JSON.stringify(result, null, 2)
}
function save() {
  const url = URL.createObjectURL(new Blob([source.value], { type: "text/plain;charset=utf-8" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "protocol.aimd"
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <main class="workspace">
    <h1>{{ label("本地 Protocol 编辑与预览", "Local Protocol editing and preview") }}</h1>
    <p>{{ label("文件只在此浏览器中处理，不上传，不创建实验记录。仅检查 AIMD 内联字段；Python 模型与服务端 Assigner 仍须通过平台隔离校验。", "Files stay in this browser. Nothing is uploaded and no Records are created. Preview covers inline AIMD fields; Python models and server assigners require Platform validation.") }}</p>
    <div class="actions">
      <label>{{ label("打开 AIMD", "Open AIMD") }} <input type="file" accept=".aimd" @change="open"></label>
      <button @click="save">
        {{ label("下载修改后的 AIMD", "Download edited AIMD") }}
      </button>
      <button @click="example">
        {{ label("用示例数据测试", "Test with example data") }}
      </button>
      <button @click="validate">
        {{ label("检查填写", "Check form") }}
      </button>
    </div>
    <pre v-if="status" role="status">{{ status }}</pre>
    <div class="columns">
      <section aria-label="Protocol editor">
        <aimd-editor v-model="source" v-model:mode="mode" :locale="locale" />
      </section>
      <section aria-label="Recorder preview">
        <aimd-recorder ref="recorder" v-model="values" :content="source" :locale="locale" :show-search="false" :request-collector-permission="() => false" />
      </section>
    </div>
  </main>
</template>

<style>
body { margin: 0; font-family: system-ui, sans-serif; color: #243044; background: #f7f9fc; }
h1 { font-size: 24px; line-height: 1.3; font-weight: 650; margin: 0 0 12px; }
.workspace > p { line-height: 1.6; color: #526077; }
.workspace { max-width: 1600px; margin: auto; padding: 24px; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0; align-items: center; }
button { background: white; border: 1px solid #b9c8d9; border-radius: 6px; padding: 10px 14px; cursor: pointer; }
.columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
section { min-width: 0; background: white; border: 1px solid #dde3ed; padding: 16px; border-radius: 10px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 220px; overflow: auto; }
@media (max-width: 800px) { .columns { grid-template-columns: minmax(0, 1fr); } .workspace { padding: 16px; } }
</style>
