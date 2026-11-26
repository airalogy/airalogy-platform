<script setup lang="ts">
import {
  type Options,
  roomOptions,
  spaceUrl,
  type Task,
  workspaceGet,
  workspaceSave,
} from "@/service/api/meeting-workspace"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  id: string
  lab: string
  projects: string[]
  revision: number
  manage: boolean
  suggestions?: string[]
}>()
const { t } = useI18n()
const tr = (key: string) => t(`page.meetingSpace.${key}`)
const tasks = ref<Task[]>([])
const options = ref<Options>({ people: [], projects: [] })
const project = ref("")
const audience = ref("personal")
const assignee = ref<string | null>(null)
const readers = ref<string[]>([])
const title = ref("")
const description = ref("")
const due = ref("")
const busy = ref(false)
const error = ref("")
const expanded = ref(false)
let key = createResearchDocumentId()
async function load() {
  tasks.value = await workspaceGet<Task[]>(`${spaceUrl(props.id)}/actions`)
}
onMounted(() =>
  load().catch((e) => {
    error.value = e.message
  }),
)
watch(
  [() => props.lab, project],
  async (_, __, cleanup) => {
    let current = true
    cleanup(() => {
      current = false
    })
    readers.value = []
    assignee.value = null
    if (!props.manage || !props.lab)
      return
    try {
      const result = await roomOptions(props.lab, project.value)
      if (current)
        options.value = result
    }
    catch (e) {
      if (current)
        error.value = (e as Error).message
    }
  },
  { immediate: true },
)
async function save() {
  if (busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    await workspaceSave(`${spaceUrl(props.id)}/actions`, "POST", {
      id: key,
      expected_revision: props.revision,
      title: title.value,
      description: description.value,
      due: due.value || null,
      audience: audience.value,
      project_id: project.value || null,
      assignee_id: audience.value === "personal" ? null : assignee.value,
      readers: audience.value === "selected" ? readers.value : [],
    })
    key = createResearchDocumentId()
    title.value = description.value = due.value = ""
    expanded.value = false
    await load()
  }
  catch (e) {
    error.value = (e as Error).message
  }
  finally {
    busy.value = false
  }
}
function fromSelection(value: string) {
  title.value = value.slice(0, 255)
  expanded.value = true
}
defineExpose({ fromSelection })
</script>

<template>
  <section class="space-y-3">
    <h3>{{ tr("actions") }}</h3>
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <ul v-if="tasks.length" class="pl-4">
      <li v-for="item in tasks" :key="item.id">
        <router-link :to="item.href || { name: 'my-work', query: { task: item.id } }">
          {{
            item.title
          }}
        </router-link>
        ·
        {{
          item.audience === "project" ? t(`page.projectWork.states.${item.state}`) : tr(item.state)
        }}
        <time>{{ item.due }}</time>
      </li>
    </ul>
    <div v-if="manage && suggestions?.length" class="flex flex-wrap items-center gap-2">
      {{ tr("draftTasks") }}
      <n-button
        v-for="suggestion in suggestions"
        :key="suggestion"
        size="small"
        @click="fromSelection(suggestion)"
      >
        {{ suggestion }}
      </n-button>
    </div>
    <n-button v-if="manage && !expanded" @click="expanded = true">
      {{ tr("addTask") }}
    </n-button>
    <form v-if="expanded && manage" class="grid gap-2" @submit.prevent="save">
      <label>{{ tr("taskTitle") }}<n-input v-model:value="title" required maxlength="255" /></label>
      <label>{{ tr("taskDescription") }}<n-input v-model:value="description" type="textarea" /></label>
      <label>{{ tr("audience") }}
        <select v-model="audience"><option value="personal">{{ tr("personal") }}</option><option value="selected">{{ tr("selected") }}</option><option v-if="projects.length" value="project">{{ tr("project") }}</option></select></label>
      <label v-if="projects.length">{{ tr("projectLink") }}
        <select v-model="project" :required="audience === 'project'"><option value="">—</option><option
          v-for="p in options.projects.filter(p => projects.includes(p.id))"
          :key="p.id"
          :value="p.id"
        >{{ p.name }}</option></select></label>
      <label v-if="audience !== 'personal'">{{ tr("assignee")
      }}<n-select
        v-model:value="assignee"
        filterable
        clearable
        :options="options.people"
        value-field="id"
        label-field="name"
      /></label>
      <label v-if="audience === 'selected'">{{ tr("alsoRead")
      }}<n-select
        v-model:value="readers"
        multiple
        filterable
        :options="options.people"
        value-field="id"
        label-field="name"
      /></label>
      <label>{{ tr("due") }} <input v-model="due" type="date"></label>
      <p v-if="audience === 'project'">
        {{ tr("projectAudience") }}
      </p>
      <div>
        <n-button
          attr-type="submit"
          type="primary"
          :loading="busy"
          :disabled="!title.trim() || (audience === 'project' && !project)"
        >
          {{ tr("addTask") }}
        </n-button>
      </div>
    </form>
  </section>
</template>
