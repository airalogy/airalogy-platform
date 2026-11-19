<template>
  <nav :aria-label="$t('common.workspaceNavigation')" :class="{ 'workspace-nav--wide': wide }" class="workspace-nav" data-testid="workspace-navigation">
    <div v-if="wide" class="workspace-nav__links">
      <router-link
        v-for="item in items" :key="item.name" :to="destination(item.name)"
        class="workspace-nav__link" :class="{ 'workspace-nav__link--active': activeName === item.name }"
        :aria-current="activeName === item.name ? 'page' : undefined"
      >
        {{ item.label }}
      </router-link>
    </div>
    <n-popover v-else v-model:show="expanded" trigger="click" placement="bottom-start" :show-arrow="false">
      <template #trigger>
        <n-button
          :theme-overrides="props.buttonThemeOverrides ?? buttonThemeOverrides"
          :class="{ 'workspace-nav__trigger--current': !props.compact && activeItem }"
          icon-placement="right"
          class="workspace-nav__trigger h-9 max-w-full w-full rounded-2 px-3"
          :aria-expanded="expanded" :aria-label="$t('common.workspaceNavigation')" data-testid="workspace-menu-trigger"
          :title="props.label || activeLabel"
        >
          <span class="min-w-0 truncate">{{ props.label || activeLabel }}</span>
          <template #icon>
            <dropdown-icon :expended="expanded" />
          </template>
        </n-button>
      </template>
      <div class="workspace-nav__menu">
        <router-link
          v-for="item in items" :key="item.name" :to="destination(item.name)"
          class="workspace-nav__menu-link" :aria-current="activeName === item.name ? 'page' : undefined"
          @click="expanded = false"
        >
          {{ item.label }}
        </router-link>
      </div>
    </n-popover>
  </nav>
</template>

<script setup lang="ts">
import type { ButtonProps } from "naive-ui"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { workspaceDestination } from "@/utils/workspaceNavigation"
import { $t } from "@airalogy/shared/locales"
import { useMediaQuery } from "@vueuse/core"
import { buttonThemeOverrides } from "../global-header/constants"

const props = defineProps<{ compact?: boolean, label?: string, buttonThemeOverrides?: ButtonProps["themeOverrides"] }>()
const route = useRoute()
const auth = useAuthStore()
const instance = useInstanceStore()
const desktop = useMediaQuery("(min-width: 1280px)")
const wide = computed(() => desktop.value && !props.compact)
const expanded = ref(false)
const items = computed<Array<{ name: App.Global.RouteNameKey, label: string }>>(() => [
  { name: "home", label: $t("route.home") },
  { name: "protocols-my", label: $t("common.protocolsLabel") },
  { name: "project-dashboard", label: $t("common.projectsLabel") },
  { name: "research-documents", label: $t("page.documentUx.documents") },
  { name: "knowledge-home", label: $t("page.knowledge.title") },
  { name: "research-tasks", label: $t("page.research.title") },
  { name: "profile-records", label: $t("page.recordDiary.tab") },
  ...(!instance.isSingleLab ? [{ name: "labs-my" as const, label: $t("common.labsLabel") }] : []),
])
const activeName = computed(() => workspaceDestination(String(route.name || "")))
const activeItem = computed(() => items.value.find(item => item.name === activeName.value))
const activeLabel = computed(() => activeItem.value?.label || $t("common.workspace"))

function destination(name: App.Global.RouteNameKey) {
  return name === "profile-records"
    ? { name, params: { username: auth.userInfo.username } }
    : { name }
}
watch(() => route.fullPath, () => {
  expanded.value = false
})
</script>

<style scoped>
.workspace-nav { min-width: 0; }
@media (min-width: 1280px) {
  .workspace-nav--wide { flex: none; }
}
.workspace-nav__trigger :deep(.n-button__content) { min-width: 0; overflow: hidden; }
.workspace-nav__links { display: flex; align-items: center; gap: 0.125rem; }
@media (max-width: 1279px) {
  .workspace-nav__links { display: none; }
}
.workspace-nav__link {
  border-radius: 0.5rem;
  padding: 0.625rem 0.75rem;
  color: #354962;
  white-space: nowrap;
  text-decoration: none;
}
@media (min-width: 1280px) and (max-width: 1439px) {
  .workspace-nav__link { padding-inline: 0.375rem; }
}
.workspace-nav__link:hover { color: #165bb7; background: #e6effc; }
.workspace-nav__link--active, .workspace-nav__trigger--current { color: #165bb7; box-shadow: inset 0 -2px #165bb7; border-radius: 0; font-weight: 600; }
.workspace-nav__menu { display: grid; min-width: 12rem; gap: 0.25rem; }
.workspace-nav__menu-link { padding: 0.625rem 0.75rem; border-radius: 0.375rem; color: inherit; text-decoration: none; }
.workspace-nav__menu-link:hover, .workspace-nav__menu-link[aria-current] { background: #edf5ff; color: #0067b3; }
.workspace-nav a:focus-visible { outline: 2px solid #165bb7; outline-offset: 2px; }
</style>
