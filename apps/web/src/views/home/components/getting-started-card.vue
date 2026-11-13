<script setup lang="ts">
import LearningLink from "@/components/learning/learning-link.vue"
import { useAuthStore } from "@/store/modules/auth"

const auth = useAuthStore()
const dismissed = ref(false)
const storageKey = computed(() => `learning-intro:v1:${auth.userInfo.id}`)
watch(storageKey, () => {
  try {
    dismissed.value = localStorage.getItem(storageKey.value) === "dismissed"
  }
  catch { dismissed.value = false }
}, { immediate: true })
function dismiss() {
  dismissed.value = true
  try {
    localStorage.setItem(storageKey.value, "dismissed")
  }
  catch { /* Optional preference; the guide remains available in Help. */ }
}
</script>

<template>
  <aside v-if="!dismissed" class="flex flex-wrap items-center justify-between gap-3 border border-blue-100 rounded-xl bg-blue-50 p-4" data-testid="learning-intro">
    <div class="min-w-0">
      <p class="m-0 font-semibold">
        {{ $t("page.learning.firstVisit") }}
      </p>
      <p class="mb-0 mt-1 text-sm text-gray-600">
        {{ $t("page.learning.intro") }}
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-4">
      <learning-link />
      <n-button quaternary size="small" @click="dismiss">
        {{ $t("page.learning.dismiss") }}
      </n-button>
    </div>
  </aside>
</template>
