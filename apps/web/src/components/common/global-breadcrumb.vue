<template>
  <n-breadcrumb class="global-breadcrumb">
    <!-- define component: BreadcrumbContent -->
    <define-breadcrumb-content v-slot="{ breadcrumb }">
      <div class="size-full">
        <n-ellipsis class="align-middle">
          {{ breadcrumb.breadcrumbLabel || breadcrumb.label }}
        </n-ellipsis>
      </div>
    </define-breadcrumb-content>
    <!-- define component: BreadcrumbContent -->

    <n-breadcrumb-item v-for="item in currentBreadcrumb" :key="item.key" class="flex-shrink-1 ellipsis-text overflow-hidden">
      <template #separator>
        <icon-local-breadcrumb-separator />
      </template>
      <router-link v-if="item.to" :to="item.to">
        <breadcrumb-content :breadcrumb="item" />
      </router-link>
      <n-dropdown
        v-else-if="item.options?.length"
        trigger="click"
        :options="item.options"
        placement="bottom-start"
        @select="handleClickMenu"
      >
        <button type="button" class="max-w-full rounded text-left focus-visible:outline-2 focus-visible:outline-primary" aria-haspopup="menu">
          <breadcrumb-content :breadcrumb="item" />
        </button>
      </n-dropdown>
      <breadcrumb-content v-else :breadcrumb="item" />
    </n-breadcrumb-item>
  </n-breadcrumb>
</template>

<script setup lang="ts">
import type { RouteNameKey } from "@/types/page-route"
import { useRouterPush } from "@/composables/useRouterPush"
import { useInstanceStore } from "@/store/modules/instance"
import { useRouteStore } from "@/store/modules/route"
import { $t } from "@airalogy/shared/locales"
import { createReusableTemplate } from "@vueuse/core"

defineOptions({ name: "GlobalBreadcrumb" })

const routeStore = useRouteStore()
const instance = useInstanceStore()
const route = useRoute()
const { routerPushByKey } = useRouterPush()

interface BreadcrumbContentProps {
  breadcrumb: App.Global.Breadcrumb
}

const [DefineBreadcrumbContent, BreadcrumbContent]
  = createReusableTemplate<BreadcrumbContentProps>()

async function handleClickMenu(key: RouteNameKey) {
  if (key.startsWith("project-") && route.params.projectUid && route.params.labUid) {
    const { projectUid, labUid } = route.params
    if (projectUid && labUid) {
      await routerPushByKey(key, {
        params: { projectUid: projectUid as string, labUid: labUid as string },
      })
    }
  }
  else {
    await routerPushByKey(key)
    routeStore.clearDynamicBreadcrumbs()
  }
}

function localizeBreadcrumb(item: App.Global.Breadcrumb): App.Global.Breadcrumb {
  const label = item.i18nKey ? $t(item.i18nKey) : item.label
  return {
    ...item,
    label,
    breadcrumbLabel: item.breadcrumbI18nKey
      ? $t(item.breadcrumbI18nKey)
      : item.i18nKey ? label : item.breadcrumbLabel,
    options: item.options?.map(localizeBreadcrumb),
  }
}

const currentBreadcrumb = computed((): App.Global.Breadcrumb[] => {
  const { breadcrumbs, dynamicBreadcrumbs } = routeStore

  const items = [...breadcrumbs, ...dynamicBreadcrumbs].map(localizeBreadcrumb)
  if (!instance.isSingleLab)
    return items
  return items.flatMap((item) => {
    if (String(item.routeKey) !== "lab" && item.routeKey !== "lab-projects")
      return [item]
    if (!route.params.projectUid)
      return []
    return [{ ...item, key: "workspace-projects", label: $t("common.projectsLabel"), breadcrumbLabel: $t("common.projectsLabel"), routeKey: "project-dashboard" as const, to: { name: "project-dashboard" } }]
  })
})
</script>

<style scoped lang="sass">
:deep(.n-breadcrumb-item__separator)
  margin: 0 6px!important
:deep(.n-breadcrumb-item__link)
  max-width: 100%
</style>

<style lang="sass">
.global-breadcrumb > ul
  display: flex!important
</style>
