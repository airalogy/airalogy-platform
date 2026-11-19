<template>
  <n-card :bordered="false" class="m-auto h-fit min-w-320px w-full md:w-500px" size="huge">
    <n-result
      :status="status"
      :title="title"
      :description="description"
    >
      <template v-if="actionLabel" #footer>
        <n-button type="primary" :loading="loading" @click="handleAction">
          {{ actionLabel }}
        </n-button>
        <n-button v-if="!authStore.isLogin && invitation && !invitation.email" class="ml-2" @click="signIn">
          {{ $t("page.instance.signInToJoin") }}
        </n-button>
      </template>
    </n-result>
  </n-card>
</template>

<script setup lang="ts">
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { acceptInvitation, fetchInvitation, type InvitationInfo } from "@/service/api/instance"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"

const { t: $t } = useOrganizationTranslation()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const token = computed(() => typeof route.query.token === "string" ? route.query.token : "")
const invitation = ref<InvitationInfo | null>(null)
const loading = ref(true)
const failed = ref(false)

const status = computed(() => failed.value ? "error" : "info")
const title = computed(() => {
  if (failed.value)
    return $t("page.instance.invitationInvalid")
  if (invitation.value)
    return $t("page.instance.invitedTo", { lab: invitation.value.lab.name })
  return $t("page.instance.invitationLoading")
})
const description = computed(() => invitation.value?.existing_account && !authStore.isLogin
  ? $t("page.instance.existingAccount")
  : "")
const actionLabel = computed(() => {
  if (!invitation.value || failed.value)
    return ""
  if (!authStore.isLogin) {
    return invitation.value.existing_account
      ? $t("page.instance.signInToJoin")
      : $t("page.login.register.confirm")
  }
  return $t("page.instance.confirmJoin", { account: authStore.userInfo.username })
})

async function loadInvitation() {
  const requested = token.value
  invitation.value = null
  loading.value = true
  if (!token.value) {
    failed.value = true
    loading.value = false
    return
  }
  const { data } = await fetchInvitation(token.value)
  if (requested !== token.value)
    return
  invitation.value = data || null
  failed.value = !data
  loading.value = false
}

async function acceptCurrentInvitation() {
  if (loading.value)
    return
  loading.value = true
  try {
    const { data } = await acceptInvitation(token.value)
    if (!data) {
      await loadInvitation()
      return
    }
    await instanceStore.load()
    window.$message?.success($t("page.instance.joinSuccess"))
    await router.replace({
      name: "home",
    })
  }
  finally {
    loading.value = false
  }
}

async function handleAction() {
  if (!invitation.value)
    return
  if (authStore.isLogin) {
    await acceptCurrentInvitation()
    return
  }
  if (invitation.value.existing_account) {
    await signIn()
  }
  else {
    await router.push({
      name: "sign-up",
      query: { inviteToken: token.value },
    })
  }
}

function signIn() {
  return router.push({ name: "login", query: { redirect: route.fullPath } })
}
watch(token, loadInvitation, { immediate: true })
</script>
