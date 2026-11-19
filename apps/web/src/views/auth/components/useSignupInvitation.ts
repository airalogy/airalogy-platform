import { fetchInvitation, type InvitationInfo } from "@/service/api/instance"

export function useSignupInvitation(setBoundEmail: (email: string) => void) {
  const route = useRoute()
  const router = useRouter()
  const inviteToken = computed(() => typeof route.query.inviteToken === "string" ? route.query.inviteToken : "")
  const invitation = ref<InvitationInfo | null>(null)
  const invitationLoading = ref(false)

  watch(inviteToken, async (token, previousToken, onCleanup) => {
    let active = true
    onCleanup(() => {
      active = false
    })
    if (previousToken && invitation.value?.email)
      setBoundEmail("")
    invitation.value = null
    invitationLoading.value = Boolean(token)
    if (token) {
      try {
        const { data } = await fetchInvitation(token)
        if (active && data) {
          invitation.value = data
          if (data.email)
            setBoundEmail(data.email)
        }
      }
      finally {
        if (active)
          invitationLoading.value = false
      }
    }
  }, { immediate: true })

  function signIn() {
    const redirect = inviteToken.value
      ? router.resolve({ name: "join-lab", query: { token: inviteToken.value } }).fullPath
      : undefined
    return router.push({ name: "login", query: { redirect } })
  }

  return { inviteToken, invitation, invitationLoading, signIn }
}
