<script setup lang="ts">
import type { ProjectWork } from "@/service/api/project-work"
import { listProjectWork } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId?: string }>()
const { t } = useI18n()
const router = useRouter()
const items = ref<ProjectWork[]>([])
const failed = ref(false)
const loading = ref(true)
const canWrite = ref(false)
const total = ref(0)
const page = ref(0)
let sequence = 0
async function load(append = false) {
  const ticket = ++sequence
  failed.value = false
  loading.value = true
  if (!append) {
    canWrite.value = false
    items.value = []
  }
  const nextPage = append ? page.value + 1 : 1
  try {
    const result = await listProjectWork({
      project_id: props.projectId,
      page: nextPage,
      page_size: props.projectId ? 3 : 6,
      overview_order: Boolean(props.projectId),
      active_only: true,
      mine: !props.projectId,
    })
    if (ticket === sequence) {
      canWrite.value = result.can_write
      total.value = result.total
      page.value = nextPage
      const next = result.items.filter(item => !["done", "cancelled"].includes(item.state))
      items.value = append ? [...new Map([...items.value, ...next].map(item => [item.id, item])).values()] : next
    }
  }
  catch {
    if (ticket === sequence)
      failed.value = true
  }
  finally {
    if (ticket === sequence)
      loading.value = false
  }
}
onBeforeUnmount(() => sequence++)
watch(() => props.projectId, () => load(), { immediate: true })
</script>

<template>
  <section class="rounded-xl border border-gray-200 p-4 sm:p-5" data-testid="work-summary">
    <div class="flex flex-wrap items-center justify-between gap-2"
    ><h2 class="aira-type-card-title m-0">{{
      t(projectId ? "page.projectWork.title" : "page.projectWork.myWork")
    }}</h2
    ><div v-if="projectId" class="flex flex-wrap items-center gap-3">
      <router-link :to="{ name: 'project-work' }" class="text-primary">{{ t("page.projectWork.open") }}<span v-if="total"> ({{ total }})</span> →</router-link>
      <n-button v-if="canWrite" type="primary" size="small" data-testid="overview-new-work" @click="router.push({ name: 'project-work', query: { create: '1' } })">{{ t("page.projectWork.new") }}</n-button>
    </div>
    </div>
    <div v-if="loading && !items.length" role="status" :aria-label="t('common.loading')" class="mt-3 space-y-2">
      <n-skeleton text :repeat="2" />
    </div>
    <p v-if="failed" role="alert"
    >{{ t("page.projectWork.failed") }}
      <n-button size="small" @click="load(Boolean(items.length))">{{ t("page.projectWork.reload") }}</n-button></p
    >
    <p v-else-if="!loading && !items.length" class="mb-0 text-sm text-gray-500">{{
      t(projectId ? "page.projectWork.noActive" : "page.projectWork.noAssigned")
    }}</p>
    <ul v-if="items.length" class="m-0 mt-3 list-none p-0 divide-y divide-gray-100">
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
    <n-button v-if="!projectId && items.length > 0 && total > items.length" class="mt-3" :loading="loading" :disabled="loading" data-testid="work-summary-more" @click="load(true)">{{ t("page.projectWork.moreItems") }}</n-button>
    <p v-if="!projectId && !loading && !failed && total > items.length" class="mb-0 text-sm text-gray-500">{{ t("page.projectWork.summaryCount", { shown: items.length, total }) }}</p>
  </section>
</template>
