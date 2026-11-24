<script setup lang="ts">
import { sharing } from "@/service/api/sharing"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ id: string, organization?: boolean, readable?: boolean }>()
const emit = defineEmits<{ changed: [boolean] }>()
const current = ref<boolean | null>(null)
const draft = ref(false)
const busy = ref(false)
const failed = ref(false)
let sequence = 0
async function load() {
  const call = ++sequence
  current.value = null
  failed.value = false
  const value = props.organization ? (await sharing.policy(props.id)).data?.enabled : Boolean(props.readable)
  if (call !== sequence)
    return
  if (value === undefined) {
    failed.value = true
    return
  }
  current.value = draft.value = value
}
watch(() => [props.id, props.readable], load, { immediate: true })
async function save() {
  const id = props.id
  busy.value = true
  try {
    const response = props.organization ? await sharing.policy(id, draft.value) : await sharing.reading(id, draft.value)
    if (id === props.id && response.data) {
      current.value = draft.value = response.data.enabled
      emit("changed", current.value)
      window.$message?.success($t("sharing.saved"))
    }
  }
  finally { busy.value = false }
}
</script>

<template>
  <section class="my-5 border rounded-lg p-4">
    <h3 class="m-0 text-base">
      {{ $t(organization ? 'sharing.policy' : 'sharing.audience') }}
    </h3>
    <n-button v-if="failed" @click="load">
      {{ $t('resourceAccess.retry') }}
    </n-button>
    <n-spin v-else-if="current === null" />
    <div v-else class="mt-2 space-y-2">
      <n-checkbox v-if="organization" v-model:checked="draft">
        {{ $t('sharing.enable') }}
      </n-checkbox>
      <n-radio-group v-else :value="draft ? 'organization' : 'members'" @update:value="draft = $event === 'organization'">
        <n-radio value="members">
          {{ $t('sharing.members') }}
        </n-radio>
        <n-radio value="organization">
          {{ $t('sharing.organization') }}
        </n-radio>
      </n-radio-group>
      <p class="text-sm color-text-secondary">
        {{ $t(organization ? 'sharing.policyHint' : 'sharing.projectReadingHint') }}
      </p>
      <n-popconfirm v-if="draft !== current" @positive-click="save">
        <template #trigger>
          <n-button :loading="busy" size="small" type="primary">
            {{ $t('common.save') }}
          </n-button>
        </template>
        {{ $t(organization ? (draft ? 'sharing.enableHint' : 'sharing.disableHint') : 'sharing.changeReading') }}
      </n-popconfirm>
    </div>
  </section>
</template>
