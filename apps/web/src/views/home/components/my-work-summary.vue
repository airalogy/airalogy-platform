<script setup lang="ts">
import { loadWorkSummary } from "@/service/api/my-work"
import { useAuthStore } from "@/store/modules/auth"

const auth = useAuthStore()
const summary = ref<Awaited<ReturnType<typeof loadWorkSummary>>>()
const failed = ref(false)
const retry = ref(0)
watch([() => auth.userInfo.id, retry], async ([id], _, onCleanup) => {
  let active = true
  onCleanup(() => {
    active = false
  })
  summary.value = undefined
  failed.value = false
  if (!id)
    return
  try {
    const data = await loadWorkSummary()
    if (active)
      summary.value = data
  }
  catch {
    if (active)
      failed.value = true
  }
}, { immediate: true })
</script>

<template>
  <section class="min-w-0 border border-gray-200 rounded-xl p-4" data-testid="my-work-summary">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="aira-type-card-title m-0">
        {{ $t("page.myWork.title") }}
      </h2>
      <router-link to="/my-work" class="text-primary hover:underline">
        {{ $t("common.viewAll") }} →
      </router-link>
    </div>
    <div v-if="summary" class="grid mt-3 gap-3 sm:grid-cols-2">
      <div>
        <div class="aira-type-meta">
          {{ $t(summary.meeting?.status === 'held' ? 'page.myWork.last' : 'page.myWork.next') }}
        </div>
        <router-link v-if="summary.meeting" :to="summary.meeting.href" class="break-words hover:underline">
          {{ summary.meeting.title }} · {{ summary.meeting.day }}
        </router-link>
        <span v-else>{{ $t("page.myWork.noneNext") }}</span>
      </div>
      <div>
        <div class="aira-type-meta">
          {{ $t("page.myWork.urgent") }}
        </div>
        <router-link v-if="summary.todo" :to="summary.todo.href" class="break-words hover:underline">
          {{ summary.todo.title }}
        </router-link>
        <span v-else>{{ $t("page.myWork.noneTodo") }}</span>
      </div>
    </div>
    <div v-else-if="failed" role="status">
      {{ $t("page.myWork.error") }} <n-button text @click="retry++">
        {{ $t("common.retry") }}
      </n-button>
    </div>
    <n-skeleton v-else text :repeat="1" class="mt-3" />
  </section>
</template>
