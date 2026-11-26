<script setup lang="ts">
import { convertMember, previewConversion } from "@/service/api/project-guests"

const props = defineProps<{ userId: string, name: string }>()
const emit = defineEmits<{ close: [], converted: [] }>()
const options = ref<{ id: string, name: string }[]>()
const owners = ref<string[]>([])
const keep = ref<string[]>([])
const busy = ref(false)
const keepNone = ref(false)
onMounted(async () => {
  const { data } = await previewConversion(props.userId)
  if (!data) {
    emit("close")
    return
  }
  options.value = data.projects
  owners.value = data.transfer_first
})
async function submit() {
  if (busy.value || (!keepNone.value && !keep.value.length))
    return
  busy.value = true
  try {
    const { error } = await convertMember(props.userId, keepNone.value ? [] : keep.value, keepNone.value)
    if (!error)
      emit("converted")
  }
  finally { busy.value = false }
}
</script>

<template>
  <n-modal show preset="card" :title="$t('page.guests.convert')" style="width: min(32rem, calc(100vw - 2rem))" @update:show="emit('close')">
    <n-spin v-if="!options" />
    <n-alert v-else-if="owners.length" type="warning">
      {{ $t("page.guests.transfer") }} {{ owners.join("、") }}
    </n-alert>
    <div v-else class="grid gap-3">
      <p>{{ $t("page.guests.loss", { name }) }}</p>
      <strong>{{ $t("page.guests.keep") }}</strong>
      <n-checkbox-group v-model:value="keep">
        <div v-for="project in options" :key="project.id" class="py-1">
          <n-checkbox :value="project.id" :disabled="keepNone">
            {{ project.name }}
          </n-checkbox>
        </div>
      </n-checkbox-group>
      <n-checkbox v-model:checked="keepNone" @update:checked="keep = []">
        {{ $t("page.guests.keepNone") }}
      </n-checkbox>
      <n-button type="primary" :disabled="!keep.length && !keepNone" :loading="busy" @click="submit">
        {{ $t("page.guests.confirm") }}
      </n-button>
    </div>
  </n-modal>
</template>
