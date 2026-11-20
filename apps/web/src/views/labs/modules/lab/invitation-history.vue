<script setup lang="ts">
import type { InvitationRecord } from "@/service/api/instance"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { listInvitations, revokeInvitation } from "@/service/api/instance"

const emit = defineEmits<{ revoked: [id: string] }>()
const { t } = useOrganizationTranslation()
const page = ref(1)
const total = ref(0)
const entries = ref<InvitationRecord[]>([])
const loading = ref(false)
const failed = ref(false)
const revoking = ref("")
let sequence = 0

async function load() {
  const ticket = ++sequence
  loading.value = true
  try {
    const { data } = await listInvitations(page.value)
    if (ticket !== sequence)
      return
    failed.value = !data
    entries.value = data?.items ?? []
    total.value = data?.total ?? 0
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}

async function revoke(id: string) {
  revoking.value = id
  try {
    const { data } = await revokeInvitation(id)
    if (data?.success)
      emit("revoked", id)
    await load()
  }
  finally {
    revoking.value = ""
  }
}
watch(page, load, { immediate: true })
</script>

<template>
  <n-spin :show="loading">
    <n-button v-if="failed" size="small" @click="load">
      {{ t('page.instance.reloadInvites') }}
    </n-button>
    <p v-else-if="!loading && !entries.length">
      {{ t('page.instance.noInvites') }}
    </p>
    <ul v-else class="m-0 max-h-72 overflow-auto p-0 divide-y">
      <li v-for="entry in entries" :key="entry.id" class="flex flex-wrap items-center justify-between gap-2 py-2">
        <div class="min-w-0 break-words">
          <strong>{{ entry.display_name || entry.email || t('page.instance.privateInvite') }}</strong>
          <div v-if="entry.display_name && entry.email" class="text-sm">
            {{ entry.email }}
          </div>
          <div v-if="entry.note" class="text-sm text-gray-600">
            {{ t('page.instance.invitationAdminNote', { note: entry.note }) }}
          </div>
          <div class="text-sm text-gray-600">
            {{ t(`page.instance.inviteStates.${entry.status}`) }}
            <span v-if="entry.claimed_by"> · {{ t('page.instance.invitationClaimant', { account: entry.claimed_by }) }}</span>
            <span v-if="entry.status === 'pending'"> · {{ t('page.instance.linkExpiresAt', { time: new Date(entry.expires_at).toLocaleString() }) }}</span>
          </div>
        </div>
        <n-popconfirm v-if="entry.can_revoke" @positive-click="revoke(entry.id)">
          <template #trigger>
            <n-button size="small" :loading="revoking === entry.id" :disabled="Boolean(revoking)">
              {{ t('page.instance.revokeInvite') }}
            </n-button>
          </template>
          {{ t('page.instance.confirmRevoke') }}
        </n-popconfirm>
      </li>
    </ul>
    <n-pagination v-if="total > 20" v-model:page="page" :item-count="total" :page-size="20" simple />
  </n-spin>
</template>
