<template>
  <global-layout>
    <content-layout :title="$t('breadcrumb.projects')" :tabs="tabs" :title-icon="ProjectIcon">
      <template v-if="route.name === 'projects-research-overview' && !canManageLab" #default>
        <n-spin v-if="loading" size="small" :aria-label="$t('common.loading')" />
        <n-alert v-else type="warning" role="alert">
          {{ $t(info ? 'route.403' : 'page.orgResearch.error') }}
          <router-link :to="{ name: 'project-dashboard' }" class="ml-2 text-primary hover:underline">
            {{ $t('page.project.tab.list') }}
          </router-link>
        </n-alert>
      </template>
      <template #suffix>
        <create-project-modal v-if="route.name === 'project-dashboard'" @modal:new-project="handleAddProject" />
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/es/tabs"
import ProjectIcon from "@/components/icon/project-icon.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSingleLabWorkspace } from "@/composables/useSingleLabWorkspace"

import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import CreateProjectModal from "./modules/create-project-modal.vue"

defineOptions({
  name: "ProjectLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const instance = useInstanceStore()
const { info, loading, canManageLab } = useSingleLabWorkspace()
const tabs = computed<TabPaneProps[]>(() => [
  { name: "project-dashboard", tab: $t(instance.isSingleLab ? "page.project.tab.list" : "page.project.tab.my") },
  ...(canManageLab.value ? [{ name: "projects-research-overview", tab: $t("page.orgResearch.title") }] : []),
  { name: "project-starred", tab: $t("page.project.tab.star") },
])

const route = useRoute()
const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { lab_uid, uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-overview", { params: { labUid: lab_uid, projectUid: uid } })
}
</script>

<style></style>
