<script setup lang="ts">
import type { ProjectWork } from "@/service/api/project-work"
import { listProjectWork } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId?: string }>()
const { t } = useI18n()
const items = ref<ProjectWork[]>([])
const failed = ref(false)
let sequence = 0
async function load() {
  const ticket = ++sequence
  failed.value = false
  items.value = []
  try {
    const result = await listProjectWork({
      project_id: props.projectId,
      page_size: 6,
      active_only: true,
      mine: !props.projectId,
    })
    if (ticket === sequence) {
      items.value = result.items
        .filter(item => !["done", "cancelled"].includes(item.state))
        .slice(0, 6)
    }
  }
  catch {
    if (ticket === sequence)
      failed.value = true
  }
}
watch(() => props.projectId, load, { immediate: true })
</script>

<template>
  <section class="rounded-xl border border-gray-200 p-4 sm:p-5" data-testid="work-summary">
    <div class="flex flex-wrap items-center justify-between gap-2"
    ><h2 class="aira-type-card-title m-0">{{
      t(projectId ? "page.projectWork.title" : "page.projectWork.myWork")
    }}</h2
    ><router-link v-if="projectId" :to="{ name: 'project-work' }" class="text-primary"
    >{{ t("page.projectWork.open") }} →</router-link
    ></div
    >
    <p v-if="failed" role="alert"
    >{{ t("page.projectWork.failed") }}
      <n-button size="small" @click="load">{{ t("page.projectWork.reload") }}</n-button></p
    >
    <p v-else-if="!items.length" class="mb-0 text-sm text-gray-500">{{
      t("page.projectWork.noAssigned")
    }}</p>
    <ul v-else class="m-0 mt-3 list-none p-0 divide-y divide-gray-100">
      <li v-for="item in items" :key="item.id" class="flex items-center justify-between gap-3 py-3">
        <router-link
          :to="{
            name: 'project-work',
            params: { labUid: item.lab_uid, projectUid: item.project_uid },
            query: { item: item.id },
          }"
          class="min-w-0 break-words text-primary"
        ><span v-if="!projectId" class="mr-2 text-gray-500">{{ item.project_name }}</span
        >{{ item.title }}</router-link
        >
        <span class="shrink-0 text-xs text-gray-500">{{
          t(`page.projectWork.states.${item.state}`)
        }}</span>
      </li>
    </ul>
  </section>
</template>
