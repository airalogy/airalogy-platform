<template>
  <n-card>
    <template #header>
      <span class="list__title ml-3.5 capitalize !text-2xl">{{ $t("accountSettings.security") }}</span>
    </template>
    <n-list show-divider>
      <n-list-item v-if="!instanceStore.isSingleLab">
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("accountSettings.phone") }}
          </h4>
        </template>
        <span class="mr-4">********</span>

        <template #suffix>
          <n-button @click="showChangePhoneModal = true">
            {{ $t("common.edit") }}
          </n-button>
        </template>
      </n-list-item>
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("accountSettings.loginPassword") }}
          </h4>
        </template>
        <span class="mr-4">********</span>

        <template #suffix>
          <n-button @click="showChangePasswordModal = true">
            {{ $t("common.edit") }}
          </n-button>
        </template>
      </n-list-item>
      <n-list-item v-if="!instanceStore.isSingleLab">
        <template #prefix>
          <h4 class="w-40 text-4 color-[#d03050]">
            {{ $t("accountSettings.deleteAccount") }}
          </h4>
        </template>
        <span class="color-text-secondary">
          {{ $t("accountSettings.deleteHint") }}
        </span>
        <template #suffix>
          <div class="min-w-40 text-right">
            <n-button type="error" disabled @click="handleDelete">
              {{ $t("common.delete") }}
            </n-button>
          </div>
        </template>
      </n-list-item>
    </n-list>
  </n-card>

  <single-lab-change-password-modal v-if="instanceStore.isSingleLab" v-model:show="showChangePasswordModal" />
  <change-password-modal v-else v-model:show="showChangePasswordModal" />

  <change-phone-modal v-if="!instanceStore.isSingleLab" v-model:show="showChangePhoneModal" />
  <!-- Delete Confirmation Modal -->
  <delete-confirmation-modal
    :show="showDeleteModal"
    :entity-name="$t('accountSettings.account')"
    :item-name="authStore.userInfo.email || authStore.userInfo.username"
    :delete-confirmation-text="deleteConfirmationText"
    :is-delete-confirmation-valid="isDeleteConfirmationValid"
    :deleting="deleting"
    @update:delete-confirmation-text="deleteConfirmationText = $event"
    @confirm="confirmDelete"
    @cancel="cancelDelete"
  />
</template>

<script setup lang="ts">
import DeleteConfirmationModal from "@/components/common/settings/DeleteConfirmationModal.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { computed, ref } from "vue"
import ChangePasswordModal from "./change-password-modal.vue"
import ChangePhoneModal from "./change-phone-modal.vue"
import SingleLabChangePasswordModal from "./single-lab-change-password-modal.vue"

defineOptions({ name: "EditProfile" })

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const showChangePhoneModal = ref(false)
const showChangePasswordModal = ref(false)

// Delete Account Modal
const showDeleteModal = ref(false)
const deleting = ref(false)
const deleteConfirmationText = ref("")
const isDeleteConfirmationValid = computed(() => deleteConfirmationText.value === "DELETE")

const message = useClosableMessage()

const routerPush = useRouterPush()

function handleDelete() {
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (!isDeleteConfirmationValid.value)
    return
  deleting.value = true
  try {
    // TODO: Call the actual delete account API
    await new Promise(resolve => setTimeout(resolve, 1500))
    message.success($t("accountSettings.deleted"))
    await authStore.resetStore()
    routerPush.toLogin()
  }
  finally {
    deleting.value = false
    cancelDelete()
  }
}

function cancelDelete() {
  showDeleteModal.value = false
  deleteConfirmationText.value = ""
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
