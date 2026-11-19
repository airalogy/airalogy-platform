<template>
  <Teleport defer :to="headerTarget">
    <div class="ml-auto flex shrink-0 items-center justify-end gap-1" data-testid="aira-memory-actions">
      <span v-if="disabled" role="status" class="text-xs text-gray-500">{{ $t('airaMemory.paused') }}</span>
      <n-dropdown trigger="click" placement="bottom-end" :options="options" @select="selectOption">
        <n-button quaternary circle size="small" :disabled="busy || saving" :aria-label="$t('airaMemory.options')" data-testid="aira-memory-menu">
          <template #icon>
            <n-icon><icon-tabler-dots /></n-icon>
          </template>
        </n-button>
      </n-dropdown>
    </div>
  </Teleport>
  <div v-if="!disabled && feedback?.kind" class="my-2 flex flex-wrap items-center gap-2 text-sm" role="status" data-testid="aira-memory-feedback">
    <template v-if="feedback.kind === 'suggest'">
      <span>{{ $t('airaMemory.suggest', { style: $t(`airaMemory.${feedback.value}`) }) }}</span>
      <n-button size="tiny" secondary type="primary" :disabled="saving || busy" @click="act('accept')">
        {{ $t('airaMemory.accept') }}
      </n-button>
      <n-button size="tiny" quaternary :disabled="saving || busy" @click="act('dismiss')">
        {{ $t('airaMemory.dismiss') }}
      </n-button>
    </template>
    <template v-else>
      <span>{{ $t('airaMemory.savedShort') }}</span>
      <n-button size="tiny" text type="primary" :disabled="saving || busy" @click="act('undo')">
        {{ $t('airaMemory.undoShort') }}
      </n-button>
    </template>
  </div>
  <span v-if="notice" role="status" class="text-xs text-gray-500">{{ notice }}</span>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"
import { computed, ref, watch } from "vue"
import { memoryRequest, type preferenceOptions } from "../../aira-memory/api"

type Style = (typeof preferenceOptions)[keyof typeof preferenceOptions][number]
type Feedback = { kind?: undefined } | { kind: "saved", id: string } | { kind: "suggest", id: string, value: Style }
interface Controls { disabled: boolean, feedback: Feedback }
const props = defineProps<{ endpoint: string, token: string, chatId?: string, headerTarget: string, disabled: boolean, busy: boolean, changedAt?: number }>()
const emit = defineEmits<{ "update:disabled": [value: boolean] }>()
const feedback = ref<Feedback>({})
const saving = ref(false)
const notice = ref("")
let version = 0
const options = computed(() => [{ key: "disable", label: $t("airaMemory.temporary"), disabled: props.disabled }])
const path = computed(() => `/conversations/${props.chatId}`)

function update(data: Controls) {
  if (data.disabled)
    emit("update:disabled", true)
  feedback.value = data.feedback
}

watch(() => [props.token, props.chatId, props.changedAt, props.disabled] as const, async () => {
  const current = ++version
  feedback.value = {}
  notice.value = ""
  if (!props.token || !props.chatId || props.disabled)
    return
  try {
    const result = await memoryRequest<Controls>(props.endpoint, props.token, path.value)
    if (current === version)
      update(result)
  }
  catch { /* A delayed or unavailable preference service must not interrupt chat. */ }
}, { immediate: true })

function selectOption(key: string) {
  if (key === "disable")
    void act("disable")
}

async function act(action: "disable" | "accept" | "dismiss" | "undo") {
  if (props.disabled || saving.value)
    return
  if (!props.chatId) {
    if (action === "disable")
      emit("update:disabled", true)
    return
  }
  saving.value = true
  const current = ++version
  const id = feedback.value.kind ? feedback.value.id : undefined
  try {
    const result = await memoryRequest<Controls>(props.endpoint, props.token, path.value, { action, offer_id: id })
    if (current === version) {
      update(result)
      notice.value = action === "undo" ? $t("airaMemory.undone") : ""
    }
  }
  catch (error) {
    if (current === version) {
      if (error instanceof Error && error.message === "conflict") {
        feedback.value = {}
        notice.value = $t("airaMemory.stale")
      }
      else {
        notice.value = $t("airaMemory.failed")
      }
    }
  }
  finally {
    saving.value = false
  }
}
</script>
