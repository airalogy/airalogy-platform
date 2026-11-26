<script setup lang="ts">
import { type Task, workspaceGet, workspaceSave } from "@/service/api/meeting-workspace"
import { useI18n } from "vue-i18n"

const props = defineProps<{ id?: string }>()
const { t } = useI18n()
const rows = ref<Task[]>([])
const error = ref("")
const busy = ref(false)
async function load() {
  rows.value = props.id
    ? [await workspaceGet<Task>(`/meeting-workspace/tasks/${props.id}`)]
    : await workspaceGet<Task[]>("/meeting-workspace/tasks")
}
onMounted(() =>
  load().catch((e) => {
    error.value = e.message
  }),
)
async function update(task: Task, value: string) {
  if (busy.value)
    return
  busy.value = true
  try {
    await workspaceSave(`/meeting-workspace/tasks/${task.id}`, "PATCH", {
      state: value,
      expected_revision: task.revision,
    })
    await load()
  }
  catch (e) {
    error.value = (e as Error).message
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="space-y-3">
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <article v-for="task in rows" :key="task.id" class="border rounded p-3">
      <h3>{{ task.title }}</h3><p>{{ task.description }}</p><time>{{ task.due }}</time>
      <select
        v-if="task.can_update"
        :value="task.state"
        :aria-label="t('page.meetingSpace.status')"
        :disabled="busy"
        @change="update(task, ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="s in ['pending', 'in_progress', 'done']" :key="s" :value="s">
          {{
            t(`page.meetingSpace.${s}`)
          }}
        </option>
      </select><span v-else>{{ t(`page.meetingSpace.${task.state}`) }}</span>
    </article>
  </section>
</template>
