<script setup lang="ts">
import type { Audience, ShareOptions } from "@/service/api/sharing"
import { sharing } from "@/service/api/sharing"
import { $t } from "@airalogy/shared/locales"
import { useClipboard } from "@vueuse/core"
import SharedProtocolText from "./shared-protocol-text"

const props = defineProps<{ project: string, protocol?: string, version?: string, organizationReadable?: boolean, manage?: boolean }>()
const opened = ref(false)
const busy = ref(false)
const options = ref<ShareOptions | null>(null)
const failed = ref(false)
const version = ref(props.version)
const audience = ref<Audience>(props.protocol ? "organization" : "public")
const chosen = ref<string[]>([])
const files = ref<string[] | null>(null)
const showPreview = ref(false)
const { copy } = useClipboard({ legacy: true })
const route = useRoute()
const router = useRouter()
const workspacePath = computed(() => {
  const { labUid, projectUid, protocolUid } = route.params
  return router.resolve(protocolUid
    ? { name: "protocol-detail", params: { labUid, projectUid, protocolUid } }
    : { name: "project-overview", params: { labUid, projectUid } }).href
})
const audienceLabel = computed(() => {
  if (props.organizationReadable)
    return $t("sharing.organization")
  return $t(props.protocol ? "sharing.protocolMembers" : "sharing.members")
})
const published = computed(() => options.value?.links.find(item => item.audience === audience.value))
let generation = 0
watch(() => [props.project, props.protocol, props.version], () => {
  generation++
  opened.value = false
  version.value = props.version
})
async function reload() {
  const current = ++generation
  options.value = null
  files.value = null
  chosen.value = []
  showPreview.value = false
  failed.value = false
  if (!opened.value || !props.manage)
    return
  const { data } = await sharing.options(props.project, props.protocol, version.value)
  if (current !== generation)
    return
  options.value = data || null
  failed.value = !data
}
watch([opened, version], reload)
watch(audience, () => {
  showPreview.value = false
  chosen.value = []
})
async function loadFiles() {
  if (!props.protocol || !version.value)
    return
  const current = generation
  const { data } = await sharing.materials(props.project, props.protocol, version.value)
  if (current === generation && data)
    files.value = data
}
async function copyPath(path: string) {
  try {
    await copy(new URL(path, location.origin).href)
    window.$message?.success($t("sharing.copied"))
  }
  catch { window.$message?.error($t("sharing.copyFailed")) }
}
async function save() {
  if (!options.value || busy.value)
    return
  busy.value = true
  try {
    const result = await sharing.publish(props.project, { audience: audience.value, preview: options.value.preview, materials: chosen.value }, props.protocol, version.value)
    if (result.data) {
      await reload()
      window.$message?.success($t("sharing.published"))
    }
  }
  finally { busy.value = false }
}
async function withdraw() {
  if (!published.value || busy.value)
    return
  busy.value = true
  try {
    const { error } = await sharing.withdraw(props.project, published.value.id, props.protocol, version.value)
    if (!error)
      await reload()
  }
  finally { busy.value = false }
}
</script>

<template>
  <n-button size="small" @click="opened = true">
    {{ $t('sharing.share') }}
  </n-button>
  <n-modal v-model:show="opened" preset="card" :title="$t('sharing.share')" :mask-closable="!busy" :closable="!busy" class="w-[min(37rem,94vw)]" style="max-height:90dvh;overflow:auto">
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div><strong>{{ $t('sharing.workspaceLink') }}</strong><p>{{ audienceLabel }}</p></div>
        <n-button @click="copyPath(workspacePath)">
          {{ $t('sharing.copy') }}
        </n-button>
      </div>
      <template v-if="manage">
        <n-divider />
        <n-button v-if="failed" @click="reload">
          {{ $t('resourceAccess.retry') }}
        </n-button>
        <n-spin v-else-if="!options" />
        <template v-else>
          <label v-if="protocol" class="block">{{ $t('sharing.version') }}
            <select v-model="version" :disabled="busy" class="ml-2 border rounded p-1">
              <option v-for="v in options.versions" :key="v" :value="v">v{{ v }}</option>
            </select>
          </label>
          <n-radio-group v-if="protocol" v-model:value="audience" :disabled="busy">
            <n-radio value="organization">
              {{ $t('sharing.organization') }}
            </n-radio>
            <n-radio value="public" :disabled="!options.public_enabled">
              {{ $t('sharing.public') }}
            </n-radio>
          </n-radio-group>
          <p v-if="!options.public_enabled" class="text-sm color-text-secondary">
            {{ $t('sharing.disabled') }}
          </p>
          <template v-if="audience === 'organization' || options.public_enabled">
            <p>{{ $t(protocol ? 'sharing.versionScope' : 'sharing.projectScope') }}</p>
            <div v-if="published" class="space-y-2">
              <a :href="published.path" target="_blank" rel="noopener" class="text-primary">{{ $t('sharing.open') }}</a>
              <p v-for="file in published.materials" :key="file">
                {{ file }}
              </p>
              <div class="flex flex-wrap gap-2">
                <n-button @click="copyPath(published.path)">
                  {{ $t('sharing.copy') }}
                </n-button>
                <n-popconfirm @positive-click="withdraw">
                  <template #trigger>
                    <n-button :disabled="busy">
                      {{ $t('sharing.withdraw') }}
                    </n-button>
                  </template>
                  {{ $t('sharing.withdrawHint') }}
                </n-popconfirm>
              </div>
            </div>
            <template v-else>
              <n-button v-if="!showPreview" @click="showPreview = true">
                {{ $t('sharing.preview') }}
              </n-button>
              <div v-else class="border rounded p-3 space-y-3">
                <strong>{{ options.title }}</strong>
                <div class="max-h-64 overflow-auto">
                  <shared-protocol-text :body="options.body" />
                </div>
                <details v-if="protocol">
                  <summary class="cursor-pointer">
                    {{ $t('sharing.source') }}
                  </summary>
                  <pre class="max-h-56 overflow-auto whitespace-pre-wrap">{{ options.body }}</pre>
                </details>
                <template v-if="protocol">
                  <n-button v-if="files === null" size="small" @click="loadFiles">
                    {{ $t('sharing.chooseFiles') }}
                  </n-button>
                  <p v-else-if="!files.length">
                    {{ $t('sharing.noFiles') }}
                  </p>
                  <n-checkbox-group v-else v-model:value="chosen">
                    <n-checkbox v-for="file in files" :key="file" :value="file" class="mr-3">
                      {{ file }}
                    </n-checkbox>
                  </n-checkbox-group>
                </template>
                <p class="text-sm">
                  {{ $t(audience === 'public' ? 'sharing.public' : 'sharing.organization') }}
                </p>
                <n-button type="primary" :loading="busy" @click="save">
                  {{ $t('sharing.confirm') }}
                </n-button>
              </div>
            </template>
          </template>
        </template>
      </template>
    </div>
  </n-modal>
</template>
