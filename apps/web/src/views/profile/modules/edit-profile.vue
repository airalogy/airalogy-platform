<template>
  <n-card>
    <template #header>
      <span class="list__title ml-3.5 capitalize !text-2xl">{{ $t("page.profile.info") }}</span>
    </template>
    <template #header-extra>
      <n-button type="primary" :loading="loading" :disabled="!hasChanges" @click="handleSubmit">
        {{ $t("common.save") }}
      </n-button>
    </template>
    <n-list show-divider>
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("common.avatar") }}
          </h4>
        </template>
        <div class="avatar-container">
          <n-upload
            abstract
            accept="image/jpeg,image/png"
            :action="`${baseURL}/attachments`"
            :headers="{ 'auth-token': authStore.token }"
            :show-file-list="false"
            :default-upload="false"
            :file-list="fileListRef"
            @change="handleAvatarChange"
          >
            <div class="avatar-wrapper">
              <n-avatar
                :size="120"
                round
                :src="
                  previewImageUrlRef || authStore.userInfo.avatar_url || '/images/avatar_default.svg'
                "
                color="transparent"
                class="avatar-image"
              />
              <n-upload-trigger>
                <div class="avatar-overlay">
                  <n-button size="small" type="primary">
                    {{ $t("common.edit") }}
                  </n-button>
                </div>
              </n-upload-trigger>
            </div>
          </n-upload>
          <n-button v-if="avatarRef" size="small" text class="delete-btn" @click="handleDeleteAvatar">
            {{ $t("accountSettings.reset") }}
          </n-button>
        </div>
      </n-list-item>
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("page.instance.username") }}
          </h4>
        </template>
        <n-input
          ref="usernameInput"
          v-model:value="userInfo.username.value"
          :disabled="!userInfo.username.editing"
          type="text"
          :maxlength="16"
          class="!w-80"
        />
      </n-list-item>
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("page.instance.displayName") }}
          </h4>
        </template>
        <n-input
          ref="displayNameInput"
          v-model:value="userInfo.name.value"
          :disabled="!userInfo.name.editing"
          type="text"
          :maxlength="16"
          class="!w-80"
        />
        <template #suffix>
          <div class="min-w-40 text-right">
            <template v-if="userInfo.name.editing">
              <n-button ghost :bordered="false" @click="cancelEdit('name')">
                {{ $t("common.cancel") }}
              </n-button>
              <n-button ghost type="primary" @click="confirmEdit('name')">
                {{ $t("common.confirm") }}
              </n-button>
            </template>
            <n-button v-else ghost :bordered="false" @click="toggleEdit('name')">
              {{ $t("common.edit") }}
            </n-button>
          </div>
        </template>
      </n-list-item>
      <!-- <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("accountSettings.phone") }}
          </h4>
        </template>
        <country-phone-input
          ref="phoneInput"
          :model-value="fullPhone"
          class="!w-80"
          :default-country="userInfo.country_code.value"
          :disabled="!userInfo.phone.editing"
          :mask="!userInfo.phone.editing"
          @update:model-value="handleUpdatePhone"
          @update:country="handleUpdateCountry"
        />
        <template #suffix>
          <div class="min-w-40 text-right">
            <template v-if="userInfo.phone.editing">
              <n-button ghost :bordered="false" @click="cancelEdit('phone')">
                {{ $t("common.cancel") }}
              </n-button>
              <n-button ghost type="primary" @click="confirmEdit('phone')">
                {{ $t("common.edit") }}
              </n-button>
            </template>
            <n-button v-else ghost :bordered="false" @click="toggleEdit('phone')">
              {{ $t("common.edit") }}
            </n-button>
          </div>
        </template>
      </n-list-item> -->
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("common.email") }}
          </h4>
        </template>
        <n-input
          ref="emailInput"
          v-model:value="userInfo.email.value"
          type="text"
          class="!w-80"
          :disabled="!userInfo.email.editing"
        />
        <template #suffix>
          <div class="min-w-40 text-right">
            <template v-if="userInfo.email.editing">
              <n-button ghost :bordered="false" @click="cancelEdit('email')">
                {{ $t("common.cancel") }}
              </n-button>
              <n-button ghost type="primary" @click="confirmEdit('email')">
                {{ $t("common.edit") }}
              </n-button>
            </template>
            <n-button v-else ghost :bordered="false" @click="toggleEdit('email')">
              {{ $t("common.edit") }}
            </n-button>
          </div>
        </template>
      </n-list-item>
      <n-list-item>
        <template #prefix>
          <h4 class="w-40 text-4 color-text-secondary">
            {{ $t("accountSettings.bio") }}
          </h4>
        </template>
        <n-input
          ref="bioInput"
          v-model:value="userInfo.bio.value"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          :minlength="1"
          :maxlength="500"
          show-count
          :placeholder="$t('accountSettings.bioPlaceholder')"
          class="!w-80"
          :disabled="!userInfo.bio.editing"
        />
        <template #suffix>
          <div class="min-w-40 text-right">
            <template v-if="userInfo.bio.editing">
              <n-button ghost :bordered="false" @click="cancelEdit('bio')">
                {{ $t("common.cancel") }}
              </n-button>
              <n-button ghost type="primary" @click="confirmEdit('bio')">
                {{ $t("common.confirm") }}
              </n-button>
            </template>
            <n-button v-else ghost :bordered="false" @click="toggleEdit('bio')">
              {{ $t("common.edit") }}
            </n-button>
          </div>
        </template>
      </n-list-item>
    </n-list>
  </n-card>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from "naive-ui"
import type { InputInst, InputWrappedRef } from "naive-ui/es/input/src/interface"

import type { Component } from "vue"
import type { CountryData } from "../../../constants/country-code"
import { useLoading } from "@/composables"

import { putUserProfile } from "@/service/api/profile"
import { baseURL } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { localStg } from "@/utils/storage"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"

defineOptions({ name: "EditProfile" })

const authStore = useAuthStore()

type IFieldKey = Extract<keyof Api.Auth.UserInfo, "username" | "phone" | "email" | "name" | "country_code" | "bio">

const usernameInput = ref<InputInst | null>(null)
const displayNameInput = ref<InputInst | null>(null)
const phoneInput = ref<InputInst | null>(null)
const emailInput = ref<InputInst | null>(null)
const bioInput = ref<InputInst | null>(null)

const userInfo = ref<
  Record<IFieldKey, { value: string, editing: boolean, ref: Ref<Component | null>, changed: boolean }>
>({
  username: {
    value: authStore.userInfo.username || "",
    editing: false,
    ref: usernameInput,
    changed: false,
  },
  phone: {
    value: authStore.userInfo.phone || "",
    editing: false,
    ref: phoneInput,
    changed: false,
  },
  country_code: {
    value: authStore.userInfo.country_code || "",
    editing: false,
    ref: phoneInput,
    changed: false,
  },
  email: {
    value: authStore.userInfo.email || "",
    editing: false,
    ref: emailInput,
    changed: false,
  },
  name: {
    value: authStore.userInfo.name || "",
    editing: false,
    ref: displayNameInput,
    changed: false,
  },
  bio: {
    value: authStore.userInfo.bio || "",
    editing: false,
    ref: bioInput,
    changed: false,
  },
})

function handleUpdateCountry(country?: CountryData | null) {
  userInfo.value.country_code.value = country?.dialCode || ""
}
function handleUpdatePhone(phone: string) {
  userInfo.value.phone.value = phone
}
const fullPhone = computed(() => {
  const { phone, country_code } = authStore.userInfo

  return `+${country_code}${phone}`
})

const fileListRef = ref<UploadFileInfo[]>([])
const previewImageUrlRef = ref("")
const avatarRef = ref<UploadFileInfo | null>(null)

// Check if any field has been changed or if avatar has changed
const hasChanges = computed(() => {
  const fieldChanged = Object.values(userInfo.value).some(field => field.changed)
  const avatarChanged = avatarRef.value !== null || previewImageUrlRef.value !== ""
  return fieldChanged || avatarChanged
})

// Watch for changes in field values to update the changed status
watch(
  () => [userInfo.value.name.value, userInfo.value.email.value, userInfo.value.phone.value, userInfo.value.bio.value],
  ([newName, newEmail, newPhone, newBio]) => {
    userInfo.value.name.changed = newName !== (authStore.userInfo.name || "")
    userInfo.value.email.changed = newEmail !== (authStore.userInfo.email || "")
    userInfo.value.phone.changed = newPhone !== (authStore.userInfo.phone || "")
    userInfo.value.bio.changed = newBio !== (authStore.userInfo.bio || "")
  },
  { immediate: true },
)

const message = useClosableMessage()

const { loading, startLoading, endLoading } = useLoading()

// 切换编辑状态的方法
async function toggleEdit(field: IFieldKey) {
  const target = userInfo.value[field]
  target.editing = !target.editing

  await nextTick(() => {
    if (!target.ref) {
      return
    }

    const { focus, inputElRef } = target.ref as InputWrappedRef
    if (focus) {
      focus()
    }
    // const elm = unref(inputElRef)
    // if (elm) {
    //   elm.selectionStart = 0
    //   elm.selectionEnd = 0
    // }
  })
}

async function cancelEdit(field: IFieldKey) {
  await toggleEdit(field)
  userInfo.value[field].value = authStore.userInfo[field] || ""
  userInfo.value[field].changed = false
}

async function confirmEdit(field: IFieldKey) {
  await toggleEdit(field)
  userInfo.value[field].changed = userInfo.value[field].value !== (authStore.userInfo[field] || "")
}

// function handleDelete() {
//   dialog.error({
//     title: "Delete account?",
//     content:
//       "Once the account is deleted, all data will be permanently erased and cannot be recovered. Please proceed with caution.",
//     positiveText: "DELETE",
//     onPositiveClick: async () => {
//       message.success($t("accountSettings.deleted"))
//       await authStore.resetStore()
//     },
//   })
// }

function handleAvatarChange(option: {
  file: UploadFileInfo
  fileList: UploadFileInfo[]
  event?: Event
}) {
  const { file, fileList } = option
  fileListRef.value = fileList

  if (file.status === "removed") {
    avatarRef.value = null

    return
  }

  if (file.file) {
    const reader = new FileReader()

    reader.readAsDataURL(file.file)
    reader.addEventListener(
      "load",
      () => {
        previewImageUrlRef.value = reader.result as string
      },
      { once: true },
    )
    avatarRef.value = file
  }
  else {
    avatarRef.value = null
  }
}

function handleDeleteAvatar() {
  fileListRef.value = []
  avatarRef.value = null
  previewImageUrlRef.value = ""
}

async function handleSubmit() {
  const { name, email, bio } = userInfo.value
  const avatar = avatarRef.value
  const avatarFile = avatar?.file instanceof File ? avatar.file : undefined

  if (!name) {
    message.warning($t("accountSettings.requireName"))
    return
  }

  // Validate bio if it has been changed
  if (bio.changed) {
    const trimmedBio = bio.value.trim()
    if (trimmedBio.length === 0) {
      message.warning($t("accountSettings.requireBio"))
      return
    }
  }

  startLoading()
  try {
    const payload: { avatar?: File, name?: string, email?: string, bio?: string } = {
      avatar: avatarFile,
      name: name.changed ? name.value : undefined,
      email: email.changed ? email.value : undefined,
    }

    // Only include bio if it was changed and has content
    if (bio.changed) {
      const trimmedBio = bio.value.trim()
      if (trimmedBio) {
        payload.bio = trimmedBio
      }
    }

    const newUserInfo = await putUserProfile(payload)

    if (newUserInfo) {
      localStg.set("userInfo", newUserInfo)
      message.success($t("accountSettings.saved"))
      // Force browser reload to ensure all components show the new avatar
      setTimeout(() => {
        window.location.reload()
      }, 500)
    }
    else {
      message.error($t("accountSettings.saveFailed"))
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

.avatar-wrapper
  position: relative
  width: 120px
  height: 120px
  border-radius: 50%
  cursor: pointer

  &:hover .avatar-overlay
    opacity: 1

.avatar-image
  width: 100%
  height: 100%

.avatar-overlay
  position: absolute
  top: 0
  left: 0
  width: 100%
  height: 100%
  border-radius: 50%
  background-color: rgba(0, 0, 0, 0.5)
  display: flex
  align-items: center
  justify-content: center
  opacity: 0
  transition: opacity 0.3s ease

  &:hover
    opacity: 1

.delete-btn
  margin-top: 8px
  width: 120px
  height: 32px
</style>
