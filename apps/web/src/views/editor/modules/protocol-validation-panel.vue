<template>
  <section data-testid="protocol-validation" class="shrink-0 border-b px-4 py-2" aria-live="polite">
    <div class="flex flex-wrap items-center gap-2">
      <n-tag :type="status === 'valid' ? 'success' : status === 'invalid' ? 'error' : 'warning'" size="small">
        {{ $t(`editor.validation.${status}`) }}
      </n-tag>
      <n-button size="small" :loading="checking" @click="check">
        {{ $t("editor.validation.check") }}
      </n-button>
      <n-button v-if="aiEnabled && status === 'invalid'" size="small" data-testid="protocol-repair" @click="$emit('repair')">
        {{ $t("editor.validation.repair") }}
      </n-button>
    </div>
    <p class="my-1 text-xs text-gray-500">
      {{ $t("editor.validation.scope") }}
    </p>
    <ul v-if="report?.diagnostics.length" class="my-1 max-h-32 overflow-auto pl-5 text-sm">
      <li v-for="(diagnostic, index) in report.diagnostics" :key="index" class="break-words">
        <strong>{{ diagnostic.path }}{{ diagnostic.line ? `:${diagnostic.line}:${diagnostic.column}` : '' }}</strong> — {{ diagnostic.message }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { ProtocolSourceFile, ProtocolSourceValidation } from "@/service/api/protocol-generate"
import { $t } from "@/locales"
import { validateProtocolSources } from "@/service/api/protocol-generate"

const props = defineProps<{ files: ProtocolSourceFile[], aiEnabled: boolean }>()
defineEmits<{ repair: [] }>()
const report = ref<ProtocolSourceValidation | null>(null)
const checking = ref(false)
const unavailable = ref(false)
const status = computed(() => checking.value ? "checking" : report.value?.status || (unavailable.value ? "unavailable" : "unchecked"))
let revision = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function check(): Promise<boolean> {
  clearTimeout(timer)
  const current = ++revision
  const snapshot = JSON.stringify(props.files)
  checking.value = true
  unavailable.value = false
  report.value = null
  try {
    const { data, error } = await validateProtocolSources(JSON.parse(snapshot))
    if (current !== revision || snapshot !== JSON.stringify(props.files))
      return false
    if (error || !data) {
      unavailable.value = true
      return false
    }
    report.value = data
    return data.status === "valid"
  }
  catch {
    if (current === revision)
      unavailable.value = true
    return false
  }
  finally {
    if (current === revision)
      checking.value = false
  }
}

watch(() => props.files, () => {
  revision++
  report.value = null
  checking.value = false
  unavailable.value = false
  clearTimeout(timer)
  timer = setTimeout(check, 900)
}, { deep: true, immediate: true })
onBeforeUnmount(() => {
  clearTimeout(timer)
  revision++
})
defineExpose({ check })
</script>
