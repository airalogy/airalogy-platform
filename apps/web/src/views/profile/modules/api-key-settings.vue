<template>
  <n-card>
    <template #header>
      <span class="list__title ml-3.5 capitalize !text-2xl">{{ $t("accountSettings.sdkTitle") }}</span>
    </template>
    <p class="mb-3 text-sm color-text-secondary">
      {{ $t("accountSettings.sdkHint") }}
    </p>
    <n-form ref="formRef" :show-label="false" :model="model" :show-require-mark="false">
      <n-list show-divider>
        <n-list-item>
          <template #prefix>
            <h4 class="w-40 text-4 color-text-secondary">
              {{ $t("accountSettings.sdkKey") }}
            </h4>
          </template>
          <n-form-item path="apiKey" :show-feedback="false" :class="!isKeyVisible && 'w-fit'">
            <n-input
              :value="isKeyVisible ? model.apiKey : maskedApiKey"
              type="textarea"
              disabled
              autosize
              required
            />
          </n-form-item>
          <template #suffix>
            <div class="flex items-center gap-2">
              <n-button v-if="model.apiKey && isKeyVisible" quaternary @click="copyToClipboard">
                {{ $t("accountSettings.copy") }}
              </n-button>
              <n-button quaternary @click="toggleKeyVisibility">
                {{ $t(isKeyVisible ? "accountSettings.hide" : "accountSettings.show") }}
              </n-button>
              <n-popconfirm @positive-click="handleSubmit">
                {{ $t("accountSettings.sdkConfirm") }}
                <template #trigger>
                  <n-button type="error" class="mr-2" :loading="loading">
                    {{ $t("accountSettings.regenerate") }}
                  </n-button>
                </template>
              </n-popconfirm>
            </div>
          </template>
        </n-list-item>
      </n-list>
    </n-form>
  </n-card>
</template>

<script setup lang="ts">
import { useLoading, useNaiveForm } from "@/composables"
import { getUserAPIKey, putGenerateAPIKey } from "@/service/api/auth"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { copyToClip } from "@airalogy/shared/utils"

defineOptions({ name: "ApiKeySettings" })

interface FormModel {
  apiKey: string
}

const model: FormModel = reactive({
  apiKey: "",
})

const isKeyVisible = ref(false)
const maskedApiKey = computed(() => {
  if (!model.apiKey)
    return ""
  return "•".repeat(Math.min(20, model.apiKey.length))
})

function toggleKeyVisibility() {
  isKeyVisible.value = !isKeyVisible.value
}

const message = useClosableMessage()

const { formRef, validate } = useNaiveForm()
const { loading, startLoading, endLoading } = useLoading()

async function handleSubmit() {
  await validate()
  startLoading()
  try {
    const { data } = await putGenerateAPIKey()
    if (data) {
      model.apiKey = data.api_key
      message.success($t("accountSettings.sdkDone"))
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}

async function copyToClipboard() {
  await copyToClip(model.apiKey)
  message.success($t("externalAccess.copied"))
}

onMounted(async () => {
  const { data } = await getUserAPIKey()
  if (data)
    model.apiKey = data.api_key
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
