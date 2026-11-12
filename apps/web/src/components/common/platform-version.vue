<template>
  <n-popover v-model:show="showDetails" trigger="click" placement="top" :disabled="!systemInfo || error">
    <template #trigger>
      <button
        ref="triggerRef"
        type="button"
        data-testid="platform-version"
        class="max-w-full inline-flex flex-wrap items-center justify-center gap-x-1 rounded px-1 py-1 text-xs text-inherit focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline"
        :disabled="!systemInfo || error"
        :aria-label="`${versionLabel} · ${$t('common.footer.versionDetails')}`"
        @keydown.esc="closeDetails"
      >
        <span>Airalogy Platform</span>
        <span>{{ versionLabel }}</span>
        <span v-if="isLocalDevelopment">· {{ $t("common.footer.localDevelopment") }}</span>
        <span v-else-if="systemInfo?.dirty">· {{ $t("page.about.systemInfo.dirtyBuild") }}</span>
      </button>
    </template>
    <div v-if="systemInfo" data-testid="platform-version-details" class="max-w-[calc(100vw-48px)] w-72 space-y-3" @keydown.esc="closeDetails">
      <div class="font-semibold">
        {{ $t("common.footer.versionDetails") }}
      </div>
      <dl class="m-0 text-sm space-y-2">
        <div>
          <dt class="text-gray-500">
            {{ $t("page.about.systemInfo.productVersion") }}
          </dt>
          <dd class="m-0 break-all">
            {{ versionLabel }}
          </dd>
        </div>
        <div>
          <dt class="text-gray-500">
            {{ $t("page.about.systemInfo.sourceRevision") }}
          </dt>
          <dd class="m-0 break-all">
            {{ systemInfo.commit === 'unknown' ? $t('common.unknown') : systemInfo.commit }}
          </dd>
        </div>
        <div>
          <dt class="text-gray-500">
            {{ $t("page.about.systemInfo.buildTime") }}
          </dt>
          <dd class="m-0 break-all">
            {{ systemInfo.build_time || $t('common.unknown') }}
          </dd>
        </div>
      </dl>
      <n-button size="small" block @click="copyVersion">
        {{ $t("page.about.systemInfo.copyDiagnostics") }}
      </n-button>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { useSystemVersion } from "@/composables/useSystemVersion"
import { $t } from "@/locales"
import { useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared/utils"
import { computed, onMounted, ref } from "vue"

const { systemInfo, error, load } = useSystemVersion()
const isLocalDevelopment = import.meta.env.DEV
const showDetails = ref(false)
const triggerRef = ref<HTMLButtonElement | null>(null)
const message = useClosableMessage()
const versionLabel = computed(() => {
  if (error.value)
    return $t("common.footer.versionUnavailable")
  const version = systemInfo.value?.version
  if (!version)
    return $t("common.footer.versionLoading")
  return version === "development" ? $t("common.footer.developmentBuild") : `v${version.replace(/^v/, "")}`
})

function closeDetails() {
  showDetails.value = false
  triggerRef.value?.focus()
}

async function copyVersion() {
  if (!systemInfo.value)
    return
  try {
    await copyToClip(JSON.stringify({ ...systemInfo.value, local_development: import.meta.env.DEV }, null, 2))
    closeDetails()
    message.success($t("page.about.systemInfo.copied"))
  }
  catch {
    message.error($t("common.footer.copyVersionFailed"))
  }
}

onMounted(load)
</script>
