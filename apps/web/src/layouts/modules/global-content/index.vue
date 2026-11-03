<template>
  <router-view v-slot="{ Component, route }">
    <Transition
      name="fade" mode="out-in" @before-leave="appStore.setContentXScrollable(true)"
      @after-enter="appStore.setContentXScrollable(false)"
    >
      <n-spin v-if="props.showSpin" :show="appStore.loading || !appStore.reloadFlag" class="max-w-full min-h-90 flex-1" :class="props.containerClass" :content-class="props.containerContentClass">
        <keep-alive
          v-if="route.meta.keepAlive"
          :include="routeStore.cacheRoutes.length === 0 ? undefined : routeStore.cacheRoutes"
        >
          <component
            :is="Component" v-if="appStore.reloadFlag" :key="pageKey(route)" :class="{ 'p-8': props.showPadding }"
            class="transition-300"
          />
        </keep-alive>
        <component
          :is="Component" v-else-if="appStore.reloadFlag" :key="pageKey(route)" :class="{ 'p-8': props.showPadding }"
          class="transition-300"
        />
      </n-spin>

      <template v-else>
        <keep-alive
          v-if="route.meta.keepAlive"
          :include="routeStore.cacheRoutes.length === 0 ? undefined : routeStore.cacheRoutes"
        >
          <component
            :is="Component" v-if="appStore.reloadFlag" :key="pageKey(route)" :class="{ 'p-8': props.showPadding }"
            class="transition-300"
          />
        </keep-alive>
        <component
          :is="Component" v-else-if="appStore.reloadFlag" :key="pageKey(route)" :class="{ 'p-8': props.showPadding }"
          class="transition-300"
        />
      </template>
    </Transition>
  </router-view>
</template>

<script setup lang="ts">
import type { RouteLocationNormalizedLoaded } from "vue-router"
import { memoizedGetLabInfo } from "@/service/api/labs"
import { useAppStore } from "@/store/modules/app/"
import { useRouteStore } from "@/store/modules/route"
import { recordDraftQuery } from "@/utils/recordDrafts"

defineOptions({
  name: "GlobalContent",
})

const props = withDefaults(defineProps<Props>(), {
  showPadding: false,
  containerContentClass: "w-full h-full",
  showSpin: false,
})

// Changing a revision or a work item needs fresh source data even on the same URL path.
function pageKey(route: RouteLocationNormalizedLoaded) {
  if (route.name === "add-protocol-record" || route.name === "add-protocol-record-from-workflow")
    return JSON.stringify([route.path, recordDraftQuery(route.query)])
  return route.path
}

interface Props {
  /** Show padding for content */
  showPadding?: boolean
  /** Container class */
  containerClass?: string
  /** Container content class */
  containerContentClass?: string
  /** Show spin */
  showSpin?: boolean
}

const appStore = useAppStore()
const routeStore = useRouteStore()

watch(() => appStore.reloadFlag, (val) => {
  if (!val) {
    memoizedGetLabInfo.clear()
  }
})
</script>

<style></style>
