<template>
  <n-dropdown
    v-if="authStore.isLogin"
    v-model:show="isDropdownShow"
    placement="bottom-end"
    trigger="click"
    :options="options"
    @select="handleDropdown"
  >
    <button type="button" data-testid="account-menu" class="flex-center cursor-pointer border-0 bg-transparent p-0" :aria-label="$t('common.profile')" :aria-expanded="isDropdownShow">
      <n-avatar
        round
        :size="34"
        :src="authStore.userInfo.avatar_url || '/images/avatar_default.svg'"
        color="white"
      />
      <dropdown-icon class="mx-2 max-sm:hidden" :style="{ color: props.buttonThemeOverrides.textColor }" :expended="isDropdownShow" />
    </button>
  </n-dropdown>
  <template v-else>
    <n-button
      style="
        --n-text-color-hover: rgba(255, 255, 255, 0.8);
        --n-text-color-pressed: rgba(255, 255, 255, 0.4);
      "
      class="mr-4 text-white"
      quaternary
      @click="routerPushByKey('login')"
    >
      {{ $t("common.login") }}
    </n-button>
    <n-button type="primary" @click="routerPushByKey('sign-up')">
      {{ $t("common.signup") }}
    </n-button>
  </template>
</template>

<script setup lang="ts">
import type { ButtonProps } from "naive-ui"
import type { DropdownMixedOption } from "naive-ui/es/dropdown/src/interface"
import { useRouterPush } from "@/composables/useRouterPush"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { NAvatar, NText } from "naive-ui"
import { computed } from "vue"
import { buttonThemeOverrides } from "../constants"
/** Button theme overrides */

defineOptions({
  name: "UserAvatar",
})

const props = withDefaults(defineProps<IProps>(), {
  buttonThemeOverrides: () => ({ ...buttonThemeOverrides }),
})

const emit = defineEmits<{ selectExtra: [key: string | number] }>()

interface IProps {
  extraOptions?: DropdownMixedOption[]
  buttonThemeOverrides?: ButtonProps["themeOverrides"]
}
const authStore = useAuthStore()
const { routerPushByKey } = useRouterPush()
const isDropdownShow = ref(false)

type DropdownOption = DropdownMixedOption

function renderCustomHeader() {
  const { avatar_url, username, name } = authStore.userInfo
  return h(
    "div",
    {
      style: "display: flex; align-items: center; padding: 8px 12px;",
    },
    [
      h(NAvatar, {
        round: true,
        style: "margin-right: 12px;",
        src: avatar_url || "/images/avatar_default.svg",
        color: "transparent",
      }),
      h("div", null, [
        h("div", null, [h(NText, { depth: 2 }, { default: () => name || username })]),
      ]),
    ],
  )
}

const userOptions: DropdownOption[] = [
  {
    type: "render",
    key: "header",
    render: renderCustomHeader,
  },
  {
    type: "divider",
    key: "divider",
  },
]
const baseOptions = computed<DropdownOption[]>(() => ([
  {
    label: $t("common.profile"),
    key: "user-profile",
  },
  {
    label: $t("common.logout"),
    key: "logout",
  },
]))
const options = computed(() => {
  const { roles } = authStore.userInfo

  const opts = [...userOptions]

  if (roles?.includes("R_ADMIN") || roles?.includes("R_SUPER")) {
    opts.push({
      label: $t("common.adminDashboard"),
      key: "admin-dashboard",
    })
  }

  opts.push(...(props.extraOptions ?? []), ...baseOptions.value)

  return opts
})

function logout() {
  window.$dialog?.info({
    title: $t("common.tip"),
    content: $t("common.logoutConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await authStore.resetStore()
    },
  })
}

async function handleDropdown(key: string | number) {
  if (key === "logout") {
    logout()
  }
  else if (key === "user-profile") {
    await routerPushByKey(key, {
      params: { username: authStore.userInfo.username, tab: "summary" },
    })
  }
  else if (key === "admin-dashboard") {
    await routerPushByKey("admin-dashboard")
  }
  else if (key !== "header" && key !== "divider") {
    emit("selectExtra", key)
  }
}
</script>

<style scoped>
button { min-width: 44px; min-height: 44px; }
</style>
