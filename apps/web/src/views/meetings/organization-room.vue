<script setup lang="ts">
import DocumentMarkdown from "@/components/common/document-markdown.vue"
import { useConfirmDocumentChange } from "@/composables/useConfirmDocumentChange"
import {
  type Options,
  type Room,
  roomOptions,
  spaceUrl,
  workspaceGet,
  workspaceSave,
} from "@/service/api/meeting-workspace"
import { downloadBlob } from "@/utils/downloadBlob"
import { createResearchDocumentId } from "@/utils/research-document-id"
import { useI18n } from "vue-i18n"
import FollowUps from "./follow-ups.vue"
import SourcePanel from "./source-panel.vue"

const props = defineProps<{ id: string }>()
const { t, locale } = useI18n()
const tr = (key: string) => t(`page.meetingSpace.${key}`)
const router = useRouter()
const confirmChange = useConfirmDocumentChange()
const identity = props.id === "new" ? createResearchDocumentId() : props.id
const room = ref<Room>()
const orgs = ref<{ id: string, name: string }[]>([])
const form = reactive({
  lab_id: "",
  title: "",
  body: "",
  body_format: "aimd" as "aimd" | "md",
  date: "",
  participants: [] as string[],
  project_ids: [] as string[],
})
const options = ref<Options>({ people: [], projects: [] })
const tab = ref<"minutes" | "sources">("minutes")
const editing = ref(props.id === "new")
const sharing = ref(false)
const recipients = ref<string[]>([])
const error = ref("")
const busy = ref(false)
const loading = ref(true)
const saved = ref("")
const sources = ref<InstanceType<typeof SourcePanel>>()
const actions = ref<InstanceType<typeof FollowUps>>()
const selection = ref("")
const suggestedTasks = ref<string[]>([])
const reading = ref<HTMLElement>()
function localTime(value: Date) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
function accept(value: Room) {
  room.value = value
  Object.assign(form, {
    lab_id: value.lab_id || "",
    title: value.title,
    body: value.body,
    body_format: value.body_format,
    date: value.occurred_at ? localTime(new Date(value.occurred_at)) : "",
    participants: [...value.participants],
    project_ids: [...value.project_ids],
  })
  recipients.value = [...value.shared_with]
  saved.value = JSON.stringify(form)
}
async function run(fn: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    await fn()
  }
  catch (e) {
    error.value = (e as Error).message || tr("failed")
  }
  finally {
    busy.value = false
  }
}
onMounted(() =>
  run(async () => {
    if (props.id === "new") {
      orgs.value = await workspaceGet("/meeting-workspace/organizations")
      form.lab_id = orgs.value[0]?.id || ""
      form.date = localTime(new Date())
      saved.value = JSON.stringify(form)
    }
    else {
      accept(await workspaceGet<Room>(spaceUrl(identity)))
    }
    loading.value = false
  }),
)
watch(
  () => form.lab_id,
  async (id, _, cleanup) => {
    let current = true
    cleanup(() => {
      current = false
    })
    options.value = { people: [], projects: [] }
    if (!id || (!editing.value && !room.value?.can_manage))
      return
    try {
      const result = await roomOptions(id)
      if (current)
        options.value = result
    }
    catch (e) {
      if (current)
        error.value = (e as Error).message
    }
  },
)
function resetScope() {
  form.participants = []
  form.project_ids = []
}
function cancelEditing() {
  if (room.value)
    accept(room.value)
  editing.value = false
}
function save() {
  return run(async () => {
    const { date, ...fields } = form
    accept(
      await workspaceSave<Room>(spaceUrl(identity), "PUT", {
        ...fields,
        id: identity,
        occurred_at: new Date(date).toISOString(),
        expected_revision: room.value?.revision || 0,
      }),
    )
    editing.value = false
    if (props.id === "new")
      await router.replace({ name: "my-work", query: { room: identity } })
  })
}
function share() {
  return run(async () => {
    await workspaceSave(`${spaceUrl(identity)}/share`, "PUT", {
      users: recipients.value,
      revision: room.value!.revision,
    })
    room.value!.shared_with = [...recipients.value]
    sharing.value = false
  })
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file)
    return
  if (file.size > 800000 || !/\.(?:md|aimd)$/i.test(file.name)) {
    error.value = tr("invalidFile")
    return
  }
  if (form.body && !(await confirmChange(tr("replace"))))
    return
  const body = await file.text()
  if (body.length > 200000) {
    error.value = tr("invalidFile")
    return
  }
  form.body = body
  form.body_format = file.name.toLowerCase().endsWith(".aimd") ? "aimd" : "md"
  input.value = ""
}
function exportFile(format: string) {
  downloadBlob(
    new Blob([form.body], { type: "text/plain;charset=utf-8" }),
    `${form.title}.${format}`,
  )
}
function capture() {
  const selected = window.getSelection()
  selection.value
    = selected
    && reading.value?.contains(selected.anchorNode)
    && reading.value.contains(selected.focusNode)
      ? selected.toString().trim()
      : ""
}
function cite(ms: number) {
  const secs = Math.floor(ms / 1000)
  form.body += ` [${tr("play")} ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}](#recording-${ms})`
  editing.value = true
  tab.value = "minutes"
}
async function playback(event: MouseEvent) {
  const href = (event.target as HTMLElement).closest("a")?.getAttribute("href")
  if (!href || !/^#recording-\d+$/.test(href))
    return
  event.preventDefault()
  if (!room.value?.can_read_sources)
    return
  tab.value = "sources"
  await nextTick()
  await sources.value?.seek(Number(href.slice(11)))
}
async function receiveDraft(body: string, tasks: string[]) {
  if (form.body && !(await confirmChange(tr("replace"))))
    return
  form.body = body
  suggestedTasks.value = tasks
  tab.value = "minutes"
  editing.value = true
}
function mayLeave() {
  return !editing.value || JSON.stringify(form) === saved.value || confirmChange(tr("discard"))
}
onBeforeRouteLeave(mayLeave)
onBeforeRouteUpdate((to, from) => to.query.room === from.query.room || mayLeave())
</script>

<template>
  <section class="room mx-auto max-w-4xl p-4 space-y-4 sm:p-6">
    <router-link :to="{ name: 'my-work' }">
      ← {{ t("page.myWork.title") }}
    </router-link>
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <template v-if="!loading">
      <h1>{{ editing ? tr("editRoom") : room?.title }}</h1>
      <dl v-if="room && !editing" class="meeting-meta">
        <template v-if="room.occurred_at">
          <dt>{{ tr("date") }}</dt><dd>
            <time :datetime="room.occurred_at">{{
              new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
                new Date(room.occurred_at),
              )
            }}</time>
          </dd>
        </template>
        <template v-if="room.attendees?.length">
          <dt>{{ tr("attendees") }}</dt><dd>{{ room.attendees.map(p => p.name).join("、") }}</dd>
        </template>
        <template v-if="room.projects?.length">
          <dt>{{ tr("projectLink") }}</dt><dd class="flex flex-wrap gap-2">
            <router-link v-for="project in room.projects" :key="project.id" :to="project.path">
              {{
                project.name
              }}
            </router-link>
          </dd>
        </template>
      </dl>
      <nav v-if="room" class="flex flex-wrap gap-2">
        <n-button :type="tab === 'minutes' ? 'primary' : 'default'" @click="tab = 'minutes'">
          {{
            tr("minutes")
          }}
        </n-button><n-button
          v-if="room.can_read_sources"
          :disabled="editing"
          :type="tab === 'sources' ? 'primary' : 'default'"
          @click="tab = 'sources'"
        >
          {{ tr("sources") }}
        </n-button>
      </nav>
      <template v-if="tab === 'minutes'">
        <form v-if="editing" class="grid gap-3" @submit.prevent="save">
          <label v-if="!room">{{ tr("organization") }}
            <select
              v-model="form.lab_id"
              required
              @change="resetScope"
            ><option v-for="o in orgs" :key="o.id" :value="o.id">{{ o.name }}</option></select></label>
          <label>{{ tr("subject")
          }}<n-input
            v-model:value="form.title"
            :input-props="{ 'aria-label': tr('subject') }"
            maxlength="512"
          /></label>
          <label>{{ tr("date") }} <input v-model="form.date" type="datetime-local" required></label>
          <label>{{ tr("attendees")
          }}<n-select
            v-model:value="form.participants"
            multiple
            filterable
            :options="options.people"
            value-field="id"
            label-field="name"
          /></label>
          <label>{{ tr("projects")
          }}<n-select
            v-model:value="form.project_ids"
            multiple
            filterable
            :options="options.projects"
            value-field="id"
            label-field="name"
          /></label>
          <p>{{ tr("privateHint") }}</p>
          <label>{{ tr("minutes")
          }}<n-input
            v-model:value="form.body"
            :input-props="{ 'aria-label': tr('minutes') }"
            type="textarea"
            :autosize="{ minRows: 8, maxRows: 28 }"
          /></label>
          <div class="flex flex-wrap items-center gap-3">
            <label>{{ tr("format") }}
              <select v-model="form.body_format"><option value="aimd">AIMD</option><option value="md">Markdown</option></select></label><label>{{ tr("importDoc") }}
              <input type="file" accept=".md,.aimd" @change="importFile"></label>
          </div>
          <div class="flex gap-2">
            <n-button
              type="primary"
              attr-type="submit"
              :loading="busy"
              :disabled="!form.title.trim() || !form.lab_id"
            >
              {{ t("common.save") }}
            </n-button><n-button
              v-if="room"
              @click="cancelEditing"
            >
              {{ t("common.cancel") }}
            </n-button>
          </div>
        </form>
        <template v-else-if="room">
          <div ref="reading" @mouseup="capture" @touchend="capture" @click="playback">
            <document-markdown :body="room.body" :format="room.body_format" />
          </div>
          <div class="flex flex-wrap gap-2">
            <n-button v-if="room.can_manage" @click="editing = true">
              {{
                t("common.edit")
              }}
            </n-button>
            <n-button v-if="room.can_manage" @click="sharing = !sharing">
              {{
                tr("share")
              }}
            </n-button>
            <n-button
              v-if="room.can_manage && selection"
              @click="actions?.fromSelection(selection)"
            >
              {{ tr("selectionTask") }}
            </n-button>
            <n-button v-for="fmt in ['md', 'aimd']" :key="fmt" @click="exportFile(fmt)">
              {{ tr("export") }} .{{ fmt }}
            </n-button>
          </div>
          <div v-if="sharing && room.can_manage" class="space-y-2">
            <p>{{ tr("shareHint") }}</p><n-select
              v-model:value="recipients"
              multiple
              filterable
              :options="options.people"
              value-field="id"
              label-field="name"
            /><n-button :loading="busy" @click="share">
              {{ tr("confirmShare") }}
            </n-button>
          </div>
          <follow-ups
            v-if="room.can_read_sources"
            :id="identity"
            ref="actions"
            :suggestions="suggestedTasks"
            :lab="form.lab_id"
            :projects="room.project_ids"
            :revision="room.revision"
            :manage="room.can_manage"
          />
        </template>
      </template>
      <source-panel
        v-if="room && tab === 'sources'"
        :id="identity"
        ref="sources"
        :manage="room.can_manage"
        @draft="receiveDraft"
        @cite="cite"
      />
    </template>
  </section>
</template>

<style scoped>
.room {
  overflow-wrap: anywhere;
}
.room select,
.room input[type="datetime-local"] {
  border: 1px solid #aab6c4;
  border-radius: 0.3rem;
  padding: 0.3rem;
  max-width: 100%;
}
.meeting-meta {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.25rem 1rem;
  font-size: 0.9rem;
}
.meeting-meta dt {
  color: #64748b;
}
.meeting-meta dd {
  margin: 0;
}
.room a {
  color: #215d97;
}
</style>
