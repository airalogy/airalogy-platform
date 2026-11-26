<script setup lang="ts">
import type { AimdProtocolRecordData } from "@airalogy/aimd-recorder"
import { type GuestProject, guestProjects, guestProtocol, type GuestProtocol, guestProtocols, reviseGuestProtocol } from "@/service/api/project-guests"
import { request } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { AimdRecorder, createEmptyProtocolRecordData } from "@airalogy/aimd-recorder"
import { useI18n } from "vue-i18n"

const { t, locale } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const projects = ref<GuestProject[]>([])
const protocols = ref<{ id: string, name: string }[]>([])
const project = computed(() => projects.value.find(x => x.id === route.query.project || x.uid === route.query.projectUid))
const protocol = ref<GuestProtocol>()
const record = ref<AimdProtocolRecordData>(createEmptyProtocolRecordData())
const busy = ref(false)
const saved = ref(false)
const editing = ref(false)
const text = ref("")
const nextVersion = ref("")
function openRevision() {
  if (!protocol.value)
    return
  text.value = protocol.value.aimd
  const parts = protocol.value.version.split(".").map(Number)
  nextVersion.value = parts[2] < 999 ? [parts[0], parts[1], parts[2] + 1].join(".") : ""
  editing.value = true
}
async function publish() {
  const id = route.query.protocol
  const original = protocol.value
  if (typeof id !== "string" || !original || busy.value)
    return
  busy.value = true
  try {
    const { data } = await reviseGuestProtocol(id, original.version, nextVersion.value, text.value)
    if (data && original === protocol.value) {
      protocol.value = { ...original, version: data.version, aimd: text.value }
      editing.value = false
    }
  }
  finally { busy.value = false }
}
const loading = ref(true)
const recorder = ref<InstanceType<typeof AimdRecorder>>()
onMounted(async () => {
  const { data } = await guestProjects()
  projects.value = data || []
  loading.value = false
})
watch([project, () => route.query.protocol, () => route.query.protocolUid], async ([p, recordProtocol, uid], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  editing.value = false
  protocols.value = []
  protocol.value = undefined
  saved.value = false
  record.value = createEmptyProtocolRecordData()
  if (!p)
    return
  const { data } = await guestProtocols(p.id)
  if (!active || !data)
    return
  protocols.value = data.protocols
  const item = data.protocols.find(item => item.id === recordProtocol || item.uid === uid)
  if (!item)
    return
  if (!recordProtocol) {
    await router.replace({ name: "guest-workspace", query: { project: p.id, protocol: item.id } })
    return
  }
  const detail = await guestProtocol(item.id)
  if (active && detail.data)
    protocol.value = detail.data
}, { immediate: true })
async function save() {
  const id = route.query.protocol
  if (typeof id !== "string" || busy.value || saved.value)
    return
  busy.value = true
  try {
    const validation = await recorder.value?.validate()
    if (validation && !validation.valid)
      return
    const { data } = await request({ url: `/protocols/${id}/records`, method: "POST", data: { ...record.value, report: "" } })
    if (data && id === route.query.protocol)
      saved.value = true
  }
  finally { busy.value = false }
}
function logout() {
  auth.clearSession()
  void router.replace({ name: "login" })
}
</script>

<template>
  <main class="guest-workspace">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <h1>{{ t("page.guests.workspace") }}</h1>
      <n-button @click="logout">
        {{ t("page.guests.logout") }}
      </n-button>
    </header>
    <p class="aira-type-meta">
      {{ auth.userInfo.email }}
    </p>
    <template v-if="project">
      <router-link :to="{ name: 'guest-workspace' }">
        ← {{ t("page.guests.projects") }}
      </router-link>
      <h2>{{ project.name }}</h2>
      <p v-if="project.description">
        {{ project.description }}
      </p>
      <ul class="pl-5">
        <li v-for="p in protocols" :key="p.id">
          <router-link :to="{ name: 'guest-workspace', query: { project: project.id, protocol: p.id } }">
            {{ p.name }}
          </router-link>
        </li>
      </ul>
      <p v-if="!protocols.length">
        {{ t("page.guests.noProtocols") }}
      </p>
      <section v-if="protocol" :key="String(route.query.protocol)">
        <h3>{{ protocol.name }} · v{{ protocol.version }}</h3>
        <n-button v-if="protocol.role === 'editor' && !editing" @click="openRevision">
          {{ t("page.guests.revise") }}
        </n-button>
        <form v-if="editing" class="grid my-3 gap-3" @submit.prevent="publish">
          <label>{{ t("page.guests.revise") }}<n-input v-model:value="text" type="textarea" :autosize="{ minRows: 5, maxRows: 16 }" /></label>
          <label>{{ t("page.guests.newVersion") }}<n-input v-model:value="nextVersion" /></label>
          <div class="flex gap-2">
            <n-button :disabled="busy" @click="editing = false">
              {{ t("common.cancel") }}
            </n-button><n-button type="primary" attr-type="submit" :loading="busy" :disabled="text === protocol.aimd || !nextVersion">
              {{ t("common.save") }}
            </n-button>
          </div>
        </form>
        <aimd-recorder ref="recorder" v-model="record" :content="protocol.aimd" :locale="locale" :readonly="protocol.role === 'reader' || saved" :show-search="false" />
        <n-button v-if="protocol.role !== 'reader' && !saved && !editing" type="primary" :loading="busy" @click="save">
          {{ t("page.guests.save") }}
        </n-button>
        <p v-if="saved" role="status">
          {{ t("page.guests.saved") }}
        </p>
      </section>
    </template>
    <template v-else>
      <h2>{{ t("page.guests.projects") }}</h2>
      <p v-if="!loading && !projects.length">
        {{ t("page.guests.noProjects") }}
      </p>
      <ul class="pl-5">
        <li v-for="p in projects" :key="p.id">
          <router-link :to="{ name: 'guest-workspace', query: { project: p.id } }">
            {{ p.name }}
          </router-link> · {{ t(`page.guests.${p.role}`) }}
        </li>
      </ul>
    </template>
  </main>
</template>

<style scoped>
.guest-workspace { margin-inline: auto; padding: clamp(1rem, 4vw, 3rem); max-width: 68rem; width: 100%; min-width: 0; overflow-wrap: anywhere; }
.guest-workspace a { color: var(--primary-color, #165bbf); text-decoration: underline; }
.guest-workspace li { margin-block: .75rem; }
</style>
