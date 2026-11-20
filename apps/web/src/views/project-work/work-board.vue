<script setup lang="ts">
import type { ProjectWork, WorkState } from "@/service/api/project-work"
import { templateError } from "@/service/api/document-templates"
import { moveProjectWork, workStates } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"
import WorkBoardColumn from "./work-board-column.vue"

const props = defineProps<{ items: ProjectWork[], canWrite: boolean, loading: boolean, projectId: string, owner: (item: ProjectWork) => string }>()
const emit = defineEmits<{ open: [id: string], saved: [] }>()
const { t } = useI18n()
const busy = ref(false)
const enabled = computed(() => props.canWrite && !props.loading && !busy.value)
const message = ref("")
const error = ref("")
const input = ref("")
const show = ref(false)
const pending = ref<{ item: ProjectWork, target: WorkState, field?: "blocker" | "acceptance" }>()
const canSubmit = computed(() => {
  const change = pending.value
  if (!change || !enabled.value || (change.field && !input.value.trim()))
    return false
  return props.items.find(item => item.id === change.item.id)?.revision === change.item.revision
})
let request: { signature: string, id: string } | undefined

function move(id: string, target: WorkState) {
  const item = props.items.find(entry => entry.id === id)
  if (!enabled.value || !item || item.state === target)
    return
  const field = target === "blocked" ? "blocker" : target === "done" && !item.acceptance.trim() ? "acceptance" : undefined
  input.value = field ? item[field] : ""
  error.value = ""
  message.value = ""
  request = undefined
  pending.value = { item, target, field }
  if (field)
    show.value = true
  else
    void submit()
}

async function submit() {
  const change = pending.value
  if (!change || !canSubmit.value)
    return
  const { item, target, field } = change
  const signature = JSON.stringify([item.id, item.revision, target, input.value])
  if (request?.signature !== signature)
    request = { signature, id: crypto.randomUUID() }
  busy.value = true
  error.value = ""
  try {
    await moveProjectWork(item.id, {
      state: target,
      expected_revision: item.revision,
      request_id: request.id,
      change_reason: t("page.projectWork.boardTransition", { from: t(`page.projectWork.states.${item.state}`), to: t(`page.projectWork.states.${target}`) }),
      ...(field ? { [field]: input.value.trim() } : {}),
    })
    message.value = t("page.projectWork.moved", { title: item.title, to: t(`page.projectWork.states.${target}`) })
    show.value = false
    pending.value = undefined
    emit("saved")
  }
  catch (err) {
    const detail = templateError(err, t("page.projectWork.failed"))
    const errors: Record<string, string> = {
      "Complete dependencies before completing this work item": t("page.projectWork.finishDependencies"),
      "Reopen completed dependent work before reopening this prerequisite": t("page.projectWork.reopenDependents"),
      "Work changed in another window. Reload before moving it.": t("page.projectWork.staleMove"),
    }
    error.value = errors[detail] || detail
    show.value = true
    emit("saved")
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <p v-if="message" class="my-1 text-sm" role="status">
      {{ message }}
    </p>
    <div class="max-w-full overflow-x-auto pb-4" tabindex="0" :aria-label="t('page.projectWork.views.board')">
      <div class="grid grid-cols-6 min-w-300 gap-3">
        <work-board-column
          v-for="state in workStates" :key="state" :state="state" :items="items.filter(item => item.state === state)"
          :group="`project-work-${projectId}`" :enabled="enabled" :owner="owner"
          @open="id => emit('open', id)" @move="move"
        />
      </div>
    </div>
    <n-modal v-model:show="show" preset="card" :title="t('page.projectWork.moveTo')" style="width: min(28rem, calc(100vw - 1.5rem))" :closable="!busy" :mask-closable="!busy" :close-on-esc="!busy">
      <template v-if="pending">
        <p class="mt-0">
          {{ pending.item.title }} → {{ t(`page.projectWork.states.${pending.target}`) }}
        </p>
        <n-alert v-if="error" type="error" class="mb-2" role="alert">
          {{ error }}
        </n-alert>
        <label v-if="pending.field" class="block">{{ t(`page.projectWork.${pending.field}`) }}
          <n-input v-model:value="input" type="textarea" :maxlength="pending.field === 'blocker' ? 4000 : 10000" :disabled="busy" />
        </label>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button :disabled="busy" @click="show = false">
            {{ t("common.cancel") }}
          </n-button>
          <n-button type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">
            {{ t("common.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
