<template>
  <section
    data-testid="app-shell-header"
    class="platform-header mx-auto h-full min-w-0 w-full flex items-center px-2 sm:px-4"
    :class="isContainer ? 'container' : ''"
    :style="containerStyle"
  >
    <global-logo
      class="platform-brand shrink-0" data-testid="platform-brand" aria-label="Airalogy"
      :to="{ name: authStore.isLogin ? 'home' : 'root' }" :compact="isMobile && showOrganizationIdentity"
    />
    <router-link
      v-if="showOrganizationIdentity"
      :to="{ name: 'home' }"
      class="organization-identity min-w-0 flex items-center gap-1.5"
      :title="organizationName"
      data-testid="single-lab-identity"
    >
      <n-avatar v-if="workspaceInfo?.logo_url" :src="workspaceInfo.logo_url" :size="24" object-fit="contain" color="transparent" class="shrink-0" />
      <span class="truncate text-sm">{{ organizationName }}</span>
    </router-link>
    <template v-if="authStore.isLogin">
      <global-menu :label="currentSectionLabel">
        <template v-if="isMobile" #extra>
          <n-dropdown trigger="click" :options="discoveryOptions" @select="handleSelect">
            <n-button quaternary>{{ $t('common.more') }}</n-button>
          </n-dropdown>
        </template>
      </global-menu>
      <n-dropdown v-if="!isMobile" trigger="click" :options="moreOptions" @select="handleSelect">
        <n-button :theme-overrides="buttonThemeOverrides" :aria-current="inMore ? 'page' : undefined" data-testid="workspace-more">
          {{ $t('common.more') }}
        </n-button>
      </n-dropdown>
      <div class="header-actions" data-testid="workspace-actions">
        <global-add-new />
        <n-button
          v-if="!isMobile && instanceStore.aiEnabled" :theme-overrides="buttonThemeOverrides"
          :aria-current="inChat ? 'page' : undefined" data-testid="header-aira"
          @click="openAira($event.currentTarget as HTMLElement)"
        >
          Aira
        </n-button>
        <n-button
          v-if="!isMobile && showOrganizationManagement" :theme-overrides="buttonThemeOverrides"
          :aria-current="inManagement ? 'page' : undefined" data-testid="organization-management-entry"
          @click="handleSelect('organization-management')"
        >
          {{ $t('page.singleLabWorkspace.management') }}
        </n-button>
        <user-avatar :extra-options="accountOptions" @select-extra="handleSelect" />
      </div>
    </template>
    <div v-else class="header-actions">
      <n-dropdown trigger="click" :options="appStore.localeOptions" @select="handleLocaleSelect">
        <n-button :theme-overrides="buttonThemeOverrides" :aria-label="currentLocaleLabel">
          <template #icon><n-icon><icon-ion-language /></n-icon></template>
        </n-button>
      </n-dropdown>
      <n-button :theme-overrides="buttonThemeOverrides" @click="routerPushByKey('login')">{{ $t('common.login') }}</n-button>
      <n-button v-if="instanceStore.signupMode === 'open'" type="primary" @click="routerPushByKey('sign-up')">{{ $t('common.signup') }}</n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import { useBasicLayout } from "@/composables"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"

import { useRouterPush } from "@/composables/useRouterPush"
import { useSingleLabWorkspace } from "@/composables/useSingleLabWorkspace"
import { useWorkspaceAira } from "@/composables/useWorkspaceAira"
import GlobalAddNew from "@/layouts/modules/global-add-new/index.vue"
import GlobalMenu from "@/layouts/modules/global-menu/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { singleLabManagementEntries, singleLabManagementRoutes, singleLabSharedEntries } from "@/utils/singleLabWorkspace"
import { workspaceDestination } from "@/utils/workspaceNavigation"
import { useMediaQuery } from "@vueuse/core"
import UserAvatar from "./components/user-avatar.vue"
import { buttonThemeOverrides } from "./constants"

defineOptions({ name: "GlobalHeader" })

const props = withDefaults(defineProps<IProps>(), {
  showLogo: true,
  showMenu: false,
  showMenuToggler: false,
})

const { t: $t } = useOrganizationTranslation()

const { isMobile } = useBasicLayout()
const wide = useMediaQuery("(min-width: 1280px)")
const aira = useWorkspaceAira()
interface IProps {
  showLogo?: boolean
  showMenu?: boolean
  showMenuToggler?: boolean
  isContainer?: boolean
  maxWidth?: number
}

const containerStyle = computed(() =>
  props.isContainer && props.maxWidth
    ? { maxWidth: `${props.maxWidth}px` }
    : undefined,
)

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const { info: workspaceInfo, canManageLab } = useSingleLabWorkspace()
const organizationName = computed(() => workspaceInfo.value?.name || instanceStore.lab?.name || "")
const showOrganizationIdentity = computed(() =>
  Boolean(authStore.isLogin && instanceStore.isSingleLab && instanceStore.lab && (
    workspaceInfo.value?.logo_url || instanceStore.lab.uid !== "airalogy" || organizationName.value.trim().toLowerCase() !== "airalogy"
  )),
)
const showOrganizationManagement = computed(() => authStore.isLogin && instanceStore.isSingleLab && Boolean(instanceStore.lab) && canManageLab.value)
const appStore = useAppStore()
const { routerPushByKey } = useRouterPush()

const route = useRoute()
const inChat = computed(() => route.name === "global-chat")
const inManagement = computed(() => instanceStore.isSingleLab && singleLabManagementRoutes.has(String(route.name)))
const currentSectionLabel = computed(() => {
  if (inChat.value)
    return $t("common.allChats")
  if (inManagement.value) {
    if (!canManageLab.value)
      return $t("page.labs.members")
    return $t(instanceStore.usesOrganizationVocabulary ? "common.organizationNav" : "common.lab")
  }
  return undefined
})
function openAira(trigger?: HTMLElement) {
  if (inChat.value) {
    document.querySelector<HTMLElement>('[data-testid="chat-input"] [contenteditable="true"]')?.focus()
    return
  }
  aira?.open(trigger)
}
const discoveryOptions = computed<DropdownOption[]>(() => [
  ...(!instanceStore.isSingleLab ? [{ label: $t("common.hub"), key: "hub" }] : []),
  ...(instanceStore.isSingleLab && instanceStore.lab
    ? [
        ...singleLabSharedEntries.map(entry => ({ label: $t(entry.label), key: entry.name })),
        ...(!canManageLab.value
          ? [{
              label: $t("page.singleLabWorkspace.membersAccess"),
              key: "lab-management",
              children: singleLabManagementEntries(instanceStore.isStructuredLab, false).map(entry => ({ label: $t(entry.label), key: entry.name })),
            }]
          : []),
        { type: "divider" as const, key: "workspace-divider" },
      ]
    : []),
  { label: $t("page.help.title"), key: "help" },
])
const currentLocaleLabel = computed(() => {
  return appStore.localeOptions.find(option => option.key === appStore.locale)?.label || appStore.locale
})

const secondaryEntries = computed<DropdownOption[]>(() => [
  { key: "research-tasks", label: $t("page.research.title") },
  { key: "profile-records", label: $t("page.recordDiary.tab") },
  ...(!instanceStore.isSingleLab ? [{ key: "labs-my", label: $t("common.labsLabel") }] : []),
])
const moreOptions = computed(() => wide.value
  ? [...secondaryEntries.value, { type: "divider" as const, key: "secondary-divider" }, ...discoveryOptions.value]
  : discoveryOptions.value)
const inMore = computed(() => !inManagement.value && wide.value && secondaryEntries.value.some(item => item.key === workspaceDestination(String(route.name))))
const accountOptions = computed<DropdownOption[]>(() => [
  ...(isMobile.value && instanceStore.aiEnabled ? [{ label: "Aira", key: "aira" }] : []),
  ...(isMobile.value && showOrganizationManagement.value ? [{ label: $t("page.singleLabWorkspace.management"), key: "organization-management" }] : []),
  {
    type: "group",
    label: $t("common.language"),
    key: "language",
    children: appStore.localeOptions.map(option => ({
      label: option.label,
      key: `language:${option.key}`,
      disabled: option.key === appStore.locale,
    })),
  },
])
async function handleSelect(key: string | number) {
  const locale = appStore.localeOptions.find(option => key === `language:${option.key}`)
  if (locale) {
    handleLocaleSelect(locale.key)
    return
  }
  const workspaceEntries = [...singleLabSharedEntries, ...singleLabManagementEntries(instanceStore.isStructuredLab, canManageLab.value)]
  const entry = workspaceEntries.find(item => item.name === key)
  if (instanceStore.isSingleLab && instanceStore.lab && entry) {
    await routerPushByKey(entry.name, { params: { labUid: instanceStore.lab.uid } })
    return
  }
  switch (key) {
    case "organization-management":
      if (showOrganizationManagement.value && instanceStore.lab)
        await routerPushByKey("lab-members", { params: { labUid: instanceStore.lab.uid } })
      break
    case "research-tasks":
    case "labs-my":
    case "hub":
      await routerPushByKey(key)
      break
    case "profile-records":
      await routerPushByKey(key, { params: { username: authStore.userInfo.username } })
      break
    case "aira":
      openAira(document.querySelector<HTMLElement>('[data-testid="account-menu"]') || undefined)
      break
    case "help":
      await routerPushByKey("help-center")
      break
  }
}

function handleLocaleSelect(key: string | number) {
  appStore.changeLocale(key as I18n.LangType)
}
</script>

<style scoped>
.platform-header { gap: 0.25rem; color: #354962; }
.header-actions { display: flex; flex: none; align-items: center; gap: 0.5rem; margin-inline-start: auto; padding-inline-start: 0.75rem; }
.platform-brand { display: inline-flex; align-items: center; min-height: 44px; padding: 0; margin-right: 0.5rem; color: #183453; }
.platform-brand :deep(svg) { display: block; width: 106px; height: 29px; }
.organization-identity { max-width: 10rem; border-left: 1px solid #c7d5e4; padding-left: 0.75rem; margin-right: 0.5rem; color: inherit; }
.platform-header :deep(:focus-visible) { outline: 2px solid #165bb7; outline-offset: 2px; }
.platform-header :deep(.n-button[aria-current="page"]) { color: #165bb7; box-shadow: inset 0 -2px #165bb7; border-radius: 0; font-weight: 600; }
@media (max-width: 639px) {
  .platform-header :deep(.workspace-nav) { flex: 1 1 auto; }
  .platform-header :deep(.workspace-nav__trigger) { width: auto; padding-inline: 4px; }
  .header-actions { gap: 2px; padding-inline-start: 0; }
  .platform-header { gap: 2px; }
  .platform-brand { margin-right: 2px; }
  .platform-brand :deep(svg) { width: 88px; height: 24px; }
  .platform-brand:has(+ .organization-identity) :deep(svg) { width: 26px; height: 26px; }
  .organization-identity { max-width: clamp(3rem, calc(50vw - 6.5rem), 6rem); padding-left: 0.375rem; margin-right: 0.125rem; }
  .platform-header :deep(.n-button) { min-height: 44px; }
}
</style>
