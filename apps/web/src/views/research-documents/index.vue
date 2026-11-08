<script setup lang="ts">
import type { TemplateScope } from "@/service/api/document-templates"
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { scopeKey, templateScopes } from "@/service/api/document-templates"
import { useI18n } from "vue-i18n"
import DocumentList from "./document-list.vue"
import DocumentSelect from "./document-select.vue"
import MaterialLibrary from "./material-library.vue"
import TemplateLibrary from "./template-library.vue"

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const tabs = ["documents", "materials", "templates"] as const
const tab = computed(() => tabs.includes(String(route.query.tab) as typeof tabs[number]) ? String(route.query.tab) : "documents")
const scopes = ref<TemplateScope[]>([])
const contextError = ref(false)
const labels = { documents: "page.documentUx.documents", materials: "page.researchDocuments.materials", templates: "page.documentTemplates.library" } as const
async function selectTab(value: string) {
  await router.replace({ name: "research-documents", query: { ...route.query, tab: value } })
  void nextTick(() => document.getElementById(`research-${value}-tab`)?.focus())
}
function moveTab(delta: number) {
  const index = tabs.indexOf(tab.value as typeof tabs[number])
  void selectTab(tabs[(index + delta + tabs.length) % tabs.length])
}
const scope = computed<ResearchLogScopeParams>(() => {
  if (route.query.project_id)
    return { scope_type: "project", project_id: String(route.query.project_id) }
  if (route.query.lab_id)
    return { scope_type: "lab", lab_id: String(route.query.lab_id) }
  return { scope_type: "personal" }
})
const scopeOptions = computed(() => scopes.value.map(s => ({ value: scopeKey(s), label: `${t(`page.documentTemplates.${s.scope_type}`)}${s.name ? ` · ${s.name}` : ""}` })))
async function selectScope(key: string) {
  const s = scopes.value.find(s => scopeKey(s) === key)
  if (s)
    await router.replace({ name: "research-documents", query: { tab: tab.value, ...(s.project_id ? { project_id: s.project_id } : s.lab_id ? { lab_id: s.lab_id } : {}) } })
}
async function loadScopes() {
  try {
    scopes.value = (await templateScopes()).items
    contextError.value = false
  }
  catch { contextError.value = true }
}
onMounted(loadScopes)
</script>

<template>
  <main class="mx-auto max-w-7xl w-full !px-0 !py-4 sm:!p-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="aira-type-page-title">
        {{ t(`page.researchDocuments.scope${scope.scope_type[0].toUpperCase()}${scope.scope_type.slice(1)}`) }}
      </h1>
      <document-select :value="scopeKey(scope)" class="w-full sm:max-w-96" :options="scopeOptions" :label="t('page.documentTemplates.shareScope')" data-testid="documents-scope" @update:value="selectScope" />
    </div>
    <n-alert v-if="contextError" type="warning" class="mt-3">
      {{ t('page.researchDocuments.failed') }} <n-button @click="loadScopes">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <div role="tablist" :aria-label="t('page.researchDocuments.title')" class="my-5 flex flex-wrap gap-2 border-b border-gray-200 pb-3">
      <button v-for="item in tabs" :id="`research-${item}-tab`" :key="item" type="button" role="tab" :aria-controls="`research-${item}-panel`" :aria-selected="tab === item" :tabindex="tab === item ? 0 : -1" class="rounded-lg px-4 py-2 focus-visible:outline-primary" :class="tab === item ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700'" @click="selectTab(item)" @keydown.right.prevent="moveTab(1)" @keydown.left.prevent="moveTab(-1)">
        {{ t(labels[item]) }}
      </button>
    </div>
    <section :id="`research-${tab}-panel`" role="tabpanel" :aria-labelledby="`research-${tab}-tab`" tabindex="0">
      <document-list v-if="tab === 'documents'" :scope="scope" :scope-name="scopes.find(s => scopeKey(s) === scopeKey(scope))?.name" />
      <material-library v-else-if="tab === 'materials'" :scope="scope" />
      <template-library v-else :scope="scope" />
    </section>
  </main>
</template>
