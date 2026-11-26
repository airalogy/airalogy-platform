<script setup lang="ts">
import { type GuestRole, type GuestTeam, inviteGuest, inviteNameStatus, removeGuest } from "@/service/api/project-guests"
import { copyToClip } from "@airalogy/shared"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, team?: GuestTeam }>()
const emit = defineEmits<{ updated: [] }>()
const { t, locale } = useI18n()

const show = ref(false)
const email = ref("")
const displayName = ref("")
const reuse = ref(false)
let lookup = 0
watch(email, (_, __, onCleanup) => {
  lookup++
  reuse.value = false
  const timer = setTimeout(checkName, 300)
  onCleanup(() => clearTimeout(timer))
}, { flush: "sync" })
async function checkName() {
  const address = email.value.trim()
  if (!/^[^@\s]+@[^\s@][^\s.@]*\.[^\s@]+$/.test(address))
    return
  const ticket = ++lookup
  const project = props.projectId
  const { data } = await inviteNameStatus(project, address)
  if (ticket === lookup && project === props.projectId)
    reuse.value = !!data?.reuse
}
const role = ref<GuestRole>("reader")
const until = ref<number | null>(null)
const busy = ref(false)
const result = ref<{ url: string, delivery: "sent" | "link" | "failed" }>()
const roles = computed(() => (["reader", "recorder", "editor"] as const).map(value => ({ value, label: t(`page.guests.${value}`) })))
function open() {
  email.value = ""
  displayName.value = ""
  reuse.value = false
  until.value = null
  role.value = "reader"
  result.value = undefined
  show.value = true
}
async function submit() {
  if (busy.value || !email.value.trim() || (!reuse.value && !displayName.value.trim()))
    return
  busy.value = true
  try {
    const { data } = await inviteGuest(props.projectId, { email: email.value.trim(), display_name: reuse.value ? undefined : displayName.value.trim(), role: role.value, access_until: until.value ? new Date(until.value).toISOString() : null, locale: locale.value })
    if (data) {
      result.value = data
      emit("updated")
    }
  }
  finally { busy.value = false }
}
async function remove(kind: "people" | "invitations", id: string) {
  const { error } = await removeGuest(props.projectId, kind, id)
  if (!error)
    emit("updated")
}
defineExpose({ open })
</script>

<template>
  <div v-if="show || team?.pending.length" class="grid gap-2">
    <div v-for="row in team?.pending" :key="row.id" class="flex flex-wrap items-center gap-2 py-1">
      <strong v-if="row.name">{{ row.name }}</strong><span class="break-all">{{ row.email }}</span><n-tag size="small">
        {{ t("page.guests.pending") }}
      </n-tag>
      <n-popconfirm @positive-click="remove('invitations', row.id)">
        <template #trigger>
          <n-button text>
            {{ t("page.guests.cancelInvite") }}
          </n-button>
        </template>{{ t("page.guests.cancelPrompt") }}
      </n-popconfirm>
    </div>
    <n-modal v-model:show="show" preset="card" :title="t('page.guests.invite')" style="width: min(30rem, calc(100vw - 2rem))">
      <form v-if="!result" class="grid gap-4" @submit.prevent="submit">
        <label>{{ t("page.guests.email") }}<n-input v-model:value="email" type="text" autocomplete="off" :input-props="{ type: 'email', required: true }" /></label>
        <p v-if="reuse" role="status" class="aira-type-meta m-0">
          {{ t("page.guests.reuseName") }}
        </p>
        <label v-else>{{ t("common.labAliasLabel") }}<n-input v-model:value="displayName" :maxlength="255" :input-props="{ required: true }" /></label>
        <label>{{ t("page.guests.access") }}<n-select v-model:value="role" :options="roles" /></label>
        <label>{{ t("page.guests.until") }}<n-date-picker v-model:value="until" type="datetime" clearable /></label>
        <p class="aira-type-meta">
          {{ t("page.guests.inviteHint") }}
        </p>
        <n-button type="primary" attr-type="submit" :loading="busy" :disabled="!email.trim() || (!reuse && !displayName.trim())">
          {{ t("page.guests.create") }}
        </n-button>
      </form>
      <div v-else class="grid gap-3">
        <p role="status">
          {{ t(`page.guests.${result.delivery}`, { email }) }}
        </p>
        <n-input :value="result.url" readonly aria-label="URL" />
        <n-button @click="copyToClip(result.url)">
          {{ t("page.guests.copy") }}
        </n-button>
      </div>
    </n-modal>
  </div>
</template>
