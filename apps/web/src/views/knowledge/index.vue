<template>
  <div class="knowledge-page py-4">
    <header class="knowledge-hero">
      <div class="min-w-0">
        <h1 class="aira-type-page-title m-0" data-testid="knowledge-title">
          {{ pageTitle }}
        </h1>
        <p class="aira-type-body aira-text-secondary mb-0 mt-2 max-w-3xl">
          {{ $t("page.knowledge.description") }}
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <n-button quaternary :loading="loading" :disabled="contextsLoading" @click="() => loadCurrentView()">
          <template #icon>
            <n-icon><icon-tabler-refresh /></n-icon>
          </template>
          {{ $t("page.knowledge.refresh") }}
        </n-button>
        <knowledge-editor-modal
          v-if="contextReady"
          ref="editorRef"
          :scope="scope"
          :scope-label="scopeLabel"
          @saved="handleKnowledgeSaved"
        />
        <import-paper-modal
          v-if="contextReady"
          :scope="scope"
          :scope-label="scopeLabel"
          @imported="handlePaperImported"
        />
        <template v-if="!contextReady">
          <n-button disabled>{{ $t("page.knowledge.newKnowledge") }}</n-button>
          <n-button type="primary" disabled>{{ $t("page.knowledge.importPaper") }}</n-button>
        </template>
      </div>
    </header>

    <n-alert class="mt-5" type="info" :title="$t('page.knowledge.privateByDesign')">
      {{ $t("page.knowledge.privateHint") }}
    </n-alert>

    <div class="knowledge-toolbar mt-5">
      <n-select
        v-if="!contextLocked"
        v-model:value="selectedScopeKey"
        class="min-w-56 flex-1 md:max-w-80"
        :options="scopeOptions"
        :loading="contextsLoading"
        :disabled="!contextReady"
        :placeholder="$t('page.knowledge.scope')"
        @update:value="handleScopeChange"
      />
      <div v-else class="knowledge-scope-label">
        <n-icon><icon-tabler-folders /></n-icon>
        <span v-if="contextReady">{{ scopeLabel }}</span>
        <n-skeleton v-else text width="8rem" :sharp="false" />
      </div>
      <n-input
        v-model:value="search"
        clearable
        :disabled="!contextReady"
        class="min-w-56 flex-[2]"
        :placeholder="$t('page.knowledge.searchPlaceholder')"
        @keyup.enter="() => loadCurrentView()"
        @clear="() => loadCurrentView()"
      >
        <template #prefix>
          <n-icon><icon-tabler-search /></n-icon>
        </template>
      </n-input>
    </div>

    <n-alert v-if="loadError" type="error" class="mt-5" :title="$t('page.knowledge.loadError')">
      <n-button size="small" class="mt-2" @click="() => loadCurrentView()">
        {{ $t("common.retry") }}
      </n-button>
    </n-alert>

    <n-tabs v-model:value="activeView" type="line" animated class="mt-6" @update:value="() => loadCurrentView()">
      <n-tab name="papers" :disabled="!contextReady">
        {{ $t("page.knowledge.papers") }}
      </n-tab>
      <n-tab name="items" :disabled="!contextReady">
        {{ $t("page.knowledge.items") }}
      </n-tab>
    </n-tabs>

    <div v-if="activeView === 'items'" class="mt-4 flex flex-wrap gap-3">
      <n-select
        v-model:value="kindFilter"
        clearable
        class="w-44"
        :options="kindOptions"
        :placeholder="$t('page.knowledge.kind')"
        @update:value="() => loadCurrentView()"
      />
      <n-select
        v-model:value="stateFilter"
        clearable
        class="w-44"
        :options="stateOptions"
        :placeholder="$t('page.knowledge.state')"
        @update:value="() => loadCurrentView()"
      />
    </div>

    <n-spin :show="loading" class="mt-5 min-h-70">
      <template v-if="activeView === 'papers'">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div v-if="collections.length" class="flex flex-wrap gap-2">
            <n-tag v-for="collection in collections" :key="collection.id" round>
              {{ collection.name }}
            </n-tag>
          </div>
          <n-button size="small" secondary :disabled="!contextReady" @click="collectionModalVisible = true">
            <template #icon>
              <n-icon><icon-tabler-folder-plus /></n-icon>
            </template>
            {{ $t("page.knowledge.newCollection") }}
          </n-button>
        </div>
        <div v-if="papers.length" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <button
            v-for="entry in papers"
            :key="entry.id"
            type="button"
            class="knowledge-card"
            @click="openPaper(entry.id)"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="aira-type-meta">
                  {{ [entry.paper.first_author, entry.paper.publication_year, entry.paper.venue].filter(Boolean).join(" · ") || entry.source_type }}
                </div>
                <h2 class="aira-type-card-title line-clamp-2 mb-0 mt-1">
                  {{ entry.paper.title }}
                </h2>
              </div>
              <n-tag :type="entry.visibility === 'restricted' ? 'warning' : 'info'" round size="small">
                {{ visibilityLabel(entry.visibility) }}
              </n-tag>
            </div>
            <p v-if="entry.paper.abstract" class="aira-type-body aira-text-secondary line-clamp-3 mb-0 mt-3">
              {{ entry.paper.abstract }}
            </p>
            <div class="mt-4 flex flex-wrap items-center gap-2">
              <n-tag v-if="entry.paper.doi" size="small" round>
                DOI
              </n-tag>
              <n-tag v-for="tag in entry.tags.slice(0, 4)" :key="tag" size="small" round>
                {{ tag }}
              </n-tag>
              <span class="aira-type-meta ml-auto"><n-time :time="new Date(entry.created_at)" type="relative" /></span>
            </div>
          </button>
        </div>
        <n-empty v-else-if="contextReady && !loading && !loadError" class="knowledge-empty" :description="$t('page.knowledge.noPapers')">
          <template #extra>
            <import-paper-modal :scope="scope" :scope-label="scopeLabel" @imported="handlePaperImported" />
          </template>
        </n-empty>
      </template>

      <template v-else>
        <div v-if="knowledgeItems.length" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <article v-for="item in knowledgeItems" :key="item.id" class="knowledge-card">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <n-tag size="small" round>
                    {{ kindLabel(item.kind) }}
                  </n-tag>
                  <n-tag :type="stateType(item.state)" size="small" round>
                    {{ stateLabel(item.state) }}
                  </n-tag>
                  <n-tag v-if="item.generated_by === 'aira_assisted'" type="info" size="small" round>
                    {{ $t("page.knowledge.airaSuggested") }}
                  </n-tag>
                  <span v-if="item.derived_from_id" class="aira-type-meta">{{ $t("page.knowledge.derived") }}</span>
                </div>
                <h2 class="aira-type-card-title mb-0 mt-2">
                  {{ item.title }}
                </h2>
              </div>
              <span class="aira-type-meta">{{ $t("page.knowledge.revision", { revision: item.revision }) }}</span>
            </div>
            <p class="aira-type-body aira-text-secondary line-clamp-5 mb-0 mt-3 whitespace-pre-wrap">
              {{ item.body }}
            </p>
            <n-collapse v-if="item.evidence_sources.length" class="mt-3">
              <n-collapse-item
                name="evidence-provenance"
                :title="$t('page.knowledge.evidenceProvenance', { count: item.evidence_sources.length })"
              >
                <p class="aira-type-meta aira-text-secondary mb-3 mt-0">
                  {{ $t("page.knowledge.evidenceProvenanceHint") }}
                </p>
                <div class="space-y-2">
                  <div v-for="source in item.evidence_sources" :key="source.evidence_id" class="knowledge-evidence-source">
                    <div class="flex flex-wrap items-center gap-2">
                      <n-tag size="small" type="success" round>
                        {{ $t("page.research.evidenceQuality.validated") }}
                      </n-tag>
                      <span class="aira-type-meta min-w-0 break-all" data-testid="knowledge-evidence-source-identity">
                        {{ $t(researchArtifactTypeKey(source.source_snapshot.artifact_type)) }}
                        <template v-if="source.source_snapshot.artifact_version">
                          · {{ researchArtifactVersionLabel(source.source_snapshot.artifact_type, source.source_snapshot.artifact_version) }}
                        </template>
                        · {{ $t("page.knowledge.revision", { revision: source.knowledge_revision }) }}
                      </span>
                    </div>
                    <p class="aira-type-body mb-0 mt-2 whitespace-pre-wrap">
                      {{ source.source_snapshot.summary || source.source_snapshot.artifact_id }}
                    </p>
                    <div class="aira-type-meta aira-text-secondary mt-1 break-all">
                      {{ source.source_snapshot.artifact_id }}
                    </div>
                  </div>
                </div>
              </n-collapse-item>
            </n-collapse>
            <div class="mt-4 flex flex-wrap items-center gap-2">
              <n-tag v-for="tag in item.tags" :key="tag" size="small" round>
                {{ tag }}
              </n-tag>
              <div class="ml-auto flex flex-wrap gap-2">
                <n-button
                  v-if="instanceStore.aiEnabled && !['archived', 'superseded'].includes(item.state)"
                  size="small"
                  type="primary"
                  secondary
                  @click="openProtocolDraft(item)"
                >
                  {{ $t("page.knowledge.createProtocolDraft") }}
                </n-button>
                <n-button size="small" secondary @click="editorRef?.open({ item })">
                  {{ $t("common.edit") }}
                </n-button>
                <n-button
                  v-if="item.scope_type !== 'personal' && ['draft', 'suggested'].includes(item.state)"
                  size="small"
                  type="primary"
                  ghost
                  @click="reviewItem(item)"
                >
                  {{ $t("page.knowledge.review") }}
                </n-button>
                <n-button
                  v-if="item.scope_type !== 'lab'"
                  size="small"
                  @click="openPublish(item)"
                >
                  {{ $t("page.knowledge.publish") }}
                </n-button>
              </div>
            </div>
          </article>
        </div>
        <n-empty v-else-if="contextReady && !loading && !loadError" class="knowledge-empty" :description="$t('page.knowledge.noItems')">
          <template #extra>
            <n-button type="primary" @click="editorRef?.open()">
              {{ $t("page.knowledge.newKnowledge") }}
            </n-button>
          </template>
        </n-empty>
      </template>
    </n-spin>

    <div v-if="hasNextPage" class="mt-6 flex justify-center">
      <n-button secondary :loading="loading" @click="loadMore">
        {{ $t("common.loadMore") }}
      </n-button>
    </div>

    <n-drawer v-model:show="paperDrawerVisible" :width="paperDrawerWidth" placement="right">
      <n-drawer-content :title="$t('page.knowledge.paperDetails')" closable>
        <n-spin :show="paperLoading">
          <template v-if="selectedPaper">
            <div class="flex flex-wrap items-center gap-2">
              <n-tag :type="selectedPaper.visibility === 'restricted' ? 'warning' : 'info'" round>
                {{ visibilityLabel(selectedPaper.visibility) }}
              </n-tag>
              <n-tag v-if="selectedPaper.files?.length" type="success" round>
                {{ $t("page.knowledge.fullTextAvailable") }}
              </n-tag>
            </div>
            <h2 class="aira-type-section-title mb-0 mt-4">
              {{ selectedPaper.paper.title }}
            </h2>
            <p class="aira-type-body aira-text-secondary mb-0 mt-2">
              {{ selectedPaper.paper.authors.join(", ") }}
            </p>
            <p class="aira-type-meta aira-text-muted mb-0 mt-1">
              {{ [selectedPaper.paper.venue, selectedPaper.paper.publication_year, selectedPaper.paper.doi].filter(Boolean).join(" · ") }}
            </p>
            <p v-if="selectedPaper.paper.abstract" class="aira-type-body aira-text-secondary mt-5 whitespace-pre-wrap">
              {{ selectedPaper.paper.abstract }}
            </p>

            <n-divider />
            <n-form label-placement="top">
              <n-form-item :label="$t('page.knowledge.notes')">
                <n-input
                  v-model:value="paperNotes"
                  type="textarea"
                  :autosize="{ minRows: 4, maxRows: 10 }"
                  :placeholder="$t('page.knowledge.notesPlaceholder')"
                />
              </n-form-item>
              <n-form-item :label="$t('page.knowledge.tags')">
                <n-dynamic-tags v-model:value="paperTags" />
              </n-form-item>
              <n-form-item :label="$t('page.knowledge.collections')">
                <n-select
                  v-model:value="paperCollectionIds"
                  multiple
                  clearable
                  :options="collectionOptions"
                  @update:value="updatePaperCollections"
                />
              </n-form-item>
              <n-button type="primary" :loading="paperSaving" @click="savePaperMetadata">
                {{ $t("page.knowledge.saveMetadata") }}
              </n-button>
            </n-form>

            <n-divider />
            <div class="flex flex-wrap gap-2">
              <n-button
                v-if="selectedPaper.files?.[0]"
                :loading="fileLoading"
                @click="openProtectedFile(selectedPaper.files[0], 'preview')"
              >
                {{ $t("page.knowledge.previewPdf") }}
              </n-button>
              <n-button
                v-if="selectedPaper.files?.[0]"
                :loading="fileLoading"
                @click="openProtectedFile(selectedPaper.files[0], 'download')"
              >
                {{ $t("page.knowledge.downloadPdf") }}
              </n-button>
              <n-button @click="downloadExport('bibtex')">
                {{ $t("page.knowledge.exportBibtex") }}
              </n-button>
              <n-button @click="downloadExport('ris')">
                {{ $t("page.knowledge.exportRis") }}
              </n-button>
              <n-button
                v-if="instanceStore.aiEnabled"
                type="primary"
                :loading="airaDraftLoading"
                data-testid="paper-aira-knowledge-draft"
                @click="createAiraKnowledgeFromPaper"
              >
                {{ $t("page.knowledge.airaDraftFromPaper") }}
              </n-button>
              <n-button ghost @click="createKnowledgeFromPaper">
                {{ $t("page.knowledge.createFromPaper") }}
              </n-button>
            </div>
            <n-alert v-if="instanceStore.aiEnabled" type="warning" class="mt-3" :show-icon="false">
              {{ $t("page.knowledge.airaProcessingNotice") }}
            </n-alert>
          </template>
        </n-spin>
      </n-drawer-content>
    </n-drawer>

    <n-modal
      v-model:show="collectionModalVisible" style="--aira-dialog-width: 32rem" preset="card" class="aira-dialog small-modal" :title="$t('page.knowledge.newCollection')"
    >
      <n-form label-placement="top">
        <n-form-item :label="$t('page.knowledge.collectionName')" required>
          <n-input v-model:value="collectionForm.name" />
        </n-form-item>
        <n-form-item :label="$t('page.knowledge.collectionDescription')">
          <n-input v-model:value="collectionForm.description" type="textarea" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="collectionModalVisible = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!collectionForm.name.trim()" :loading="collectionSaving" @click="saveCollection">
            {{ $t("common.create") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="publishModalVisible" style="--aira-dialog-width: 42rem" preset="card" class="aira-dialog knowledge-modal" :title="$t('page.knowledge.publish')"
    >
      <template v-if="publishingItem">
        <n-alert type="info" class="mb-4">
          {{ $t("page.knowledge.publishImpact") }}
        </n-alert>
        <n-form v-if="publishingItem.scope_type === 'personal' && !publishPreview" label-placement="top">
          <n-form-item :label="$t('page.knowledge.targetProject')" required>
            <n-select v-model:value="publishTargetProjectId" filterable :options="projectOptions" />
          </n-form-item>
        </n-form>
        <section v-if="publishPreview" class="knowledge-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.knowledge.importDestination") }}
          </div>
          <div class="aira-type-card-title mt-2">
            {{ publishTargetLabel }}
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3">
            {{ $t("page.knowledge.filesOmitted", { count: publishPreview.impact.private_files_omitted.length }) }}
          </p>
        </section>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="publishPreview ? publishPreview = null : publishModalVisible = false">
            {{ publishPreview ? $t("page.knowledge.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!publishPreview" type="primary" :disabled="!canPreviewPublish" :loading="publishSaving" @click="previewPublish">
            {{ $t("page.knowledge.previewPublish") }}
          </n-button>
          <n-button v-else type="primary" :loading="publishSaving" @click="confirmPublish">
            {{ $t("page.knowledge.confirmPublish") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="protocolDraftModalVisible"
      style="--aira-dialog-width: 42rem"
      preset="card"
      class="aira-dialog knowledge-modal"
      :title="$t('page.knowledge.createProtocolDraft')"
    >
      <template v-if="protocolDraftItem">
        <n-alert type="info" class="mb-4">
          {{ $t("page.knowledge.protocolDraftImpact") }}
        </n-alert>
        <section class="knowledge-preview-card mb-4">
          <div class="aira-type-eyebrow">
            {{ $t("page.knowledge.protocolDraftSource") }}
          </div>
          <div class="aira-type-card-title mt-2">
            {{ protocolDraftItem.title }}
          </div>
          <p class="aira-type-meta mb-0 mt-2">
            {{ $t("page.knowledge.revision", { revision: protocolDraftItem.revision }) }}
          </p>
        </section>
        <n-form label-placement="top">
          <n-form-item :label="$t('page.knowledge.targetProject')" required>
            <n-select
              v-model:value="protocolTargetProjectId"
              filterable
              :options="protocolProjectOptions"
              :placeholder="$t('page.knowledge.targetProject')"
            />
          </n-form-item>
        </n-form>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="protocolDraftModalVisible = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            type="primary"
            :disabled="!protocolTargetProjectId"
            @click="startProtocolDraft"
          >
            {{ $t("page.knowledge.openProtocolDraft") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type {
  AiraPaperKnowledgeDraft,
  KnowledgeItem,
  KnowledgeKind,
  KnowledgePublishPreview,
  KnowledgeScope,
  KnowledgeState,
  KnowledgeVisibility,
  PaperCollection,
  PaperLibraryEntry,
  ResearchFileSummary,
} from "@/service/api/knowledge"
import type { TagProps } from "naive-ui"
import { useRouterPush } from "@/composables"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import {
  addPaperToCollection,
  confirmKnowledgePublish,
  createCollection,
  draftPaperKnowledgeWithAira,
  exportPaper,
  fetchCollections,
  fetchKnowledgeItems,
  fetchPaper,
  fetchPapers,
  fetchResearchFile,
  previewKnowledgePublish,
  removePaperFromCollection,
  reviewKnowledgeItem,
  updatePaperEntry,
} from "@/service/api/knowledge"
import { getLabInfoByUid } from "@/service/api/labs"
import { getProjectInfo } from "@/service/api/projects"
import { fetchUserProjects } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { knowledgeViewFromQuery, researchArtifactTypeKey, researchArtifactVersionLabel } from "@/utils/knowledge-presentation"
import { useRoute } from "vue-router"
import ImportPaperModal from "./components/import-paper-modal.vue"
import KnowledgeEditorModal from "./components/knowledge-editor-modal.vue"

const { t: $t } = useOrganizationTranslation()

interface KnowledgeEditorHandle {
  open: (options?: {
    item?: KnowledgeItem
    paperId?: string
    paperTitle?: string
    restrictedSource?: boolean
    airaDraft?: AiraPaperKnowledgeDraft
  }) => void
}

const route = useRoute()
const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const { routerPushByKey } = useRouterPush()
const editorRef = ref<KnowledgeEditorHandle | null>(null)
const activeView = ref(knowledgeViewFromQuery(route.query.view))
const loading = ref(true)
const contextsLoading = ref(true)
const loadError = ref(false)
const search = ref("")
const page = ref(1)
const pageSize = 20
const hasNextPage = ref(false)
const projects = ref<Api.Project.MyProjectInfo[]>([])
const selectedScopeKey = ref("personal")
const routeProject = ref<Api.Project.MyProjectInfo | null>(null)
const routeLab = ref<Api.Lab.LabInfo | null>(null)
const papers = ref<PaperLibraryEntry[]>([])
const knowledgeItems = ref<KnowledgeItem[]>([])
const collections = ref<PaperCollection[]>([])
const kindFilter = ref<KnowledgeKind | null>(null)
const stateFilter = ref<KnowledgeState | null>(null)

const paperDrawerVisible = ref(false)
const paperLoading = ref(false)
const paperSaving = ref(false)
const fileLoading = ref(false)
const airaDraftLoading = ref(false)
const selectedPaper = ref<PaperLibraryEntry | null>(null)
const paperNotes = ref("")
const paperTags = ref<string[]>([])
const paperCollectionIds = ref<string[]>([])

const collectionModalVisible = ref(false)
const collectionSaving = ref(false)
const collectionForm = reactive({ name: "", description: "" })

const publishModalVisible = ref(false)
const publishSaving = ref(false)
const publishingItem = ref<KnowledgeItem | null>(null)
const publishTargetProjectId = ref("")
const publishPreview = ref<KnowledgePublishPreview | null>(null)
const protocolDraftModalVisible = ref(false)
const protocolDraftItem = ref<KnowledgeItem | null>(null)
const protocolTargetProjectId = ref("")

const contextLocked = computed(() => route.name === "lab-knowledge" || route.name === "project-knowledge")
const contextKey = computed(() => `${String(route.name)}:${route.params.labUid || ""}:${route.params.projectUid || ""}`)
const resolvedContextKey = ref("")
const contextReady = computed(() => resolvedContextKey.value === contextKey.value && !contextsLoading.value)
let contextSequence = 0
let viewSequence = 0
const availableLabs = computed(() => {
  const values = new Map<string, { id: string, uid: string, name: string }>()
  projects.value.forEach((project) => {
    values.set(String(project.lab_id), {
      id: String(project.lab_id),
      uid: project.lab_uid,
      name: project.lab_name || project.lab_uid,
    })
  })
  return [...values.values()]
})
const scopeOptions = computed(() => [
  { label: $t("page.knowledge.myKnowledge"), value: "personal" },
  ...availableLabs.value.map(lab => ({
    label: `${$t("page.knowledge.scopeLab")} · ${lab.name}`,
    value: `lab:${lab.id}`,
  })),
  ...projects.value.map(project => ({
    label: `${$t("page.knowledge.scopeProject")} · ${project.lab_name || project.lab_uid} / ${project.name}`,
    value: `project:${project.id}`,
  })),
])
const selectedProject = computed(() => {
  if (routeProject.value)
    return routeProject.value
  if (!selectedScopeKey.value.startsWith("project:"))
    return null
  return projects.value.find(project => String(project.id) === selectedScopeKey.value.slice(8)) || null
})
const selectedLab = computed(() => {
  if (routeLab.value)
    return { id: String(routeLab.value.id), uid: routeLab.value.uid, name: routeLab.value.name }
  if (selectedProject.value) {
    return {
      id: String(selectedProject.value.lab_id),
      uid: selectedProject.value.lab_uid,
      name: selectedProject.value.lab_name || selectedProject.value.lab_uid,
    }
  }
  if (!selectedScopeKey.value.startsWith("lab:"))
    return null
  return availableLabs.value.find(lab => lab.id === selectedScopeKey.value.slice(4)) || null
})
const scope = computed<KnowledgeScope>(() => {
  if (selectedProject.value) {
    return {
      scope_type: "project",
      lab_id: String(selectedProject.value.lab_id),
      project_id: String(selectedProject.value.id),
      visibility: "project",
    }
  }
  if (selectedLab.value) {
    return {
      scope_type: "lab",
      lab_id: selectedLab.value.id,
      visibility: "lab",
    }
  }
  return { scope_type: "personal", visibility: "private" }
})
const scopeLabel = computed(() => {
  if (selectedProject.value)
    return `${selectedProject.value.lab_name || selectedProject.value.lab_uid} / ${selectedProject.value.name}`
  if (selectedLab.value)
    return selectedLab.value.name
  return $t("page.knowledge.myKnowledge")
})
const pageTitle = computed(() => {
  if (route.name === "project-knowledge" || (!contextLocked.value && selectedScopeKey.value.startsWith("project:")))
    return $t("page.knowledge.projectKnowledge")
  if (route.name === "lab-knowledge" || (!contextLocked.value && selectedScopeKey.value.startsWith("lab:")))
    return $t("page.knowledge.labKnowledge")
  return $t("page.knowledge.myKnowledge")
})
const kindOptions = computed(() => (["reference", "note", "method", "decision", "finding"] as KnowledgeKind[]).map(value => ({
  value,
  label: kindLabel(value),
})))
const stateOptions = computed(() => (["suggested", "draft", "reviewed", "superseded", "archived"] as KnowledgeState[]).map(value => ({
  value,
  label: stateLabel(value),
})))
const collectionOptions = computed(() => collections.value.map(item => ({ label: item.name, value: item.id })))
const projectOptions = computed(() => projects.value.map(project => ({
  label: `${project.lab_name || project.lab_uid} / ${project.name}`,
  value: String(project.id),
})))
const protocolProjects = computed(() => {
  const item = protocolDraftItem.value
  if (!item)
    return []
  if (item.scope_type === "project")
    return projects.value.filter(project => String(project.id) === String(item.project_id))
  if (item.scope_type === "lab")
    return projects.value.filter(project => String(project.lab_id) === String(item.lab_id))
  return projects.value
})
const protocolProjectOptions = computed(() => protocolProjects.value.map(project => ({
  label: `${project.lab_name || project.lab_uid} / ${project.name}`,
  value: String(project.id),
})))
const paperDrawerWidth = computed(() => Math.min(640, Math.max(320, window.innerWidth - 24)))
const canPreviewPublish = computed(() => {
  if (!publishingItem.value)
    return false
  return publishingItem.value.scope_type === "project" || Boolean(publishTargetProjectId.value)
})
const publishTargetLabel = computed(() => {
  if (publishingItem.value?.scope_type === "project")
    return selectedLab.value?.name || "Lab"
  const project = projects.value.find(item => String(item.id) === publishTargetProjectId.value)
  return project ? `${project.lab_name || project.lab_uid} / ${project.name}` : "Project"
})

async function loadContexts() {
  const ticket = ++contextSequence
  const key = contextKey.value
  const name = route.name
  const { labUid, projectUid } = route.params as Record<string, string>
  ++viewSequence
  contextsLoading.value = true
  loading.value = true
  loadError.value = false
  resolvedContextKey.value = ""
  routeProject.value = null
  routeLab.value = null
  selectedScopeKey.value = "personal"
  papers.value = []
  knowledgeItems.value = []
  collections.value = []
  hasNextPage.value = false
  paperDrawerVisible.value = false
  collectionModalVisible.value = false
  publishModalVisible.value = false
  protocolDraftModalVisible.value = false
  try {
    if (name === "project-knowledge") {
      const project = await getProjectInfo({ labUid, projectUid })
      if (ticket !== contextSequence || key !== contextKey.value)
        return false
      if (!project)
        throw new Error("Project not found")
      routeProject.value = project
      selectedScopeKey.value = `project:${project.id}`
    }
    else if (name === "lab-knowledge") {
      const response = await getLabInfoByUid(labUid)
      if (ticket !== contextSequence || key !== contextKey.value)
        return false
      routeLab.value = response.data?.data || null
      if (!routeLab.value)
        throw new Error("Lab not found")
      selectedScopeKey.value = `lab:${routeLab.value.id}`
    }
    else {
      const result = await fetchUserProjects(authStore.userInfo.id, {
        page: 1,
        pageSize: 100,
        sortedBy: "updated_at",
      })
      if (ticket !== contextSequence || key !== contextKey.value)
        return false
      projects.value = result?.projects || []
    }
    resolvedContextKey.value = key
    return true
  }
  catch {
    if (ticket === contextSequence) {
      loadError.value = true
      loading.value = false
    }
    return false
  }
  finally {
    if (ticket === contextSequence)
      contextsLoading.value = false
  }
}

async function loadCollections() {
  if (!contextReady.value)
    return
  const requestedScope = { ...scope.value }
  const result = await fetchCollections(requestedScope)
  if (contextReady.value && JSON.stringify(scope.value) === JSON.stringify(requestedScope))
    collections.value = result.items
}

async function loadCurrentView(append = false) {
  if (!contextReady.value && !(await loadContexts()))
    return
  const ticket = ++viewSequence
  const requestedScope = { ...scope.value }
  loading.value = true
  loadError.value = false
  try {
    if (!append)
      page.value = 1
    if (activeView.value === "papers") {
      const [result, groups] = await Promise.all([
        fetchPapers({ ...requestedScope, q: search.value.trim(), page: page.value, pageSize }),
        fetchCollections(requestedScope),
      ])
      if (ticket !== viewSequence)
        return
      papers.value = append ? [...papers.value, ...result.items] : result.items
      hasNextPage.value = result.items.length === pageSize
      collections.value = groups.items
    }
    else {
      const result = await fetchKnowledgeItems({
        ...requestedScope,
        q: search.value.trim(),
        kind: kindFilter.value || undefined,
        state: stateFilter.value || undefined,
        page: page.value,
        pageSize,
      })
      if (ticket !== viewSequence)
        return
      knowledgeItems.value = append ? [...knowledgeItems.value, ...result.items] : result.items
      hasNextPage.value = result.items.length === pageSize
    }
  }
  catch {
    if (ticket === viewSequence)
      loadError.value = true
  }
  finally {
    if (ticket === viewSequence)
      loading.value = false
  }
}

async function handleScopeChange() {
  selectedPaper.value = null
  await loadCurrentView()
}

async function loadMore() {
  page.value += 1
  await loadCurrentView(true)
}

async function openPaper(entryId: string) {
  paperDrawerVisible.value = true
  paperLoading.value = true
  try {
    selectedPaper.value = await fetchPaper(entryId)
    paperNotes.value = selectedPaper.value.notes || ""
    paperTags.value = [...selectedPaper.value.tags]
    paperCollectionIds.value = [...(selectedPaper.value.collection_ids || [])]
  }
  finally {
    paperLoading.value = false
  }
}

async function savePaperMetadata() {
  if (!selectedPaper.value)
    return
  paperSaving.value = true
  try {
    selectedPaper.value = await updatePaperEntry(selectedPaper.value.id, {
      notes: paperNotes.value,
      tags: paperTags.value,
    })
    window.$message?.success($t("page.knowledge.saved"))
    await loadCurrentView()
  }
  finally {
    paperSaving.value = false
  }
}

async function updatePaperCollections(nextIds: string[]) {
  if (!selectedPaper.value)
    return
  const previous = new Set(selectedPaper.value.collection_ids || [])
  const next = new Set(nextIds)
  await Promise.all([
    ...[...next].filter(id => !previous.has(id)).map(id => addPaperToCollection(id, selectedPaper.value!.id)),
    ...[...previous].filter(id => !next.has(id)).map(id => removePaperFromCollection(id, selectedPaper.value!.id)),
  ])
  selectedPaper.value.collection_ids = nextIds
}

function saveBlob(blob: Blob, filename: string, open = false) {
  const url = URL.createObjectURL(blob)
  if (open) {
    window.open(url, "_blank", "noopener,noreferrer")
  }
  else {
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.click()
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

async function openProtectedFile(file: ResearchFileSummary, mode: "preview" | "download") {
  fileLoading.value = true
  try {
    const blob = await fetchResearchFile(file.id, mode)
    saveBlob(blob, file.filename, mode === "preview")
  }
  catch {
    window.$message?.error($t("page.knowledge.fileOpenError"))
  }
  finally {
    fileLoading.value = false
  }
}

async function downloadExport(format: "bibtex" | "ris") {
  if (!selectedPaper.value)
    return
  const blob = await exportPaper(selectedPaper.value.id, format)
  if (blob)
    saveBlob(blob, `paper.${format === "bibtex" ? "bib" : "ris"}`)
}

function createKnowledgeFromPaper() {
  if (!selectedPaper.value)
    return
  paperDrawerVisible.value = false
  editorRef.value?.open({
    paperId: selectedPaper.value.id,
    paperTitle: selectedPaper.value.paper.title,
    restrictedSource: paperHasRestrictedSource(selectedPaper.value),
  })
}

function paperHasRestrictedSource(paper: PaperLibraryEntry) {
  return paper.visibility === "restricted"
    || paper.files?.some(file => file.visibility === "restricted") === true
}

async function runAiraKnowledgeDraft(confirmRestrictedProcessing = false) {
  if (!selectedPaper.value || !instanceStore.aiEnabled)
    return
  airaDraftLoading.value = true
  try {
    const paper = selectedPaper.value
    const draft = await draftPaperKnowledgeWithAira(
      paper.id,
      "",
      confirmRestrictedProcessing,
    )
    paperDrawerVisible.value = false
    editorRef.value?.open({
      paperId: paper.id,
      paperTitle: paper.paper.title,
      restrictedSource: paperHasRestrictedSource(paper),
      airaDraft: draft,
    })
  }
  finally {
    airaDraftLoading.value = false
  }
}

function createAiraKnowledgeFromPaper() {
  if (!selectedPaper.value || !instanceStore.aiEnabled)
    return
  if (!paperHasRestrictedSource(selectedPaper.value)) {
    void runAiraKnowledgeDraft()
    return
  }
  window.$dialog?.warning({
    title: $t("page.knowledge.restrictedAiraTitle"),
    content: $t("page.knowledge.restrictedAiraConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    async onPositiveClick() {
      await runAiraKnowledgeDraft(true)
    },
  })
}

async function saveCollection() {
  if (!contextReady.value || !collectionForm.name.trim())
    return
  collectionSaving.value = true
  try {
    await createCollection({
      ...scope.value,
      name: collectionForm.name.trim(),
      description: collectionForm.description.trim(),
    })
    window.$message?.success($t("page.knowledge.collectionCreated"))
    collectionModalVisible.value = false
    Object.assign(collectionForm, { name: "", description: "" })
    await loadCollections()
  }
  finally {
    collectionSaving.value = false
  }
}

function reviewItem(item: KnowledgeItem) {
  window.$dialog?.warning({
    title: $t("page.knowledge.review"),
    content: $t("page.knowledge.reviewHint"),
    positiveText: $t("page.knowledge.review"),
    negativeText: $t("common.cancel"),
    async onPositiveClick() {
      await reviewKnowledgeItem(item.id, item.revision)
      window.$message?.success($t("page.knowledge.reviewed"))
      await loadCurrentView()
    },
  })
}

function openPublish(item: KnowledgeItem) {
  publishingItem.value = item
  publishPreview.value = null
  publishTargetProjectId.value = projects.value.length === 1 ? String(projects.value[0].id) : ""
  publishModalVisible.value = true
}

function openProtocolDraft(item: KnowledgeItem) {
  protocolDraftItem.value = item
  const currentProject = selectedProject.value
  const eligible = protocolProjects.value
  const preferred = currentProject && eligible.some(project => project.id === currentProject.id)
    ? currentProject
    : eligible.length === 1
      ? eligible[0]
      : null
  protocolTargetProjectId.value = preferred ? String(preferred.id) : ""
  protocolDraftModalVisible.value = true
}

async function startProtocolDraft() {
  const item = protocolDraftItem.value
  const project = protocolProjects.value.find(
    candidate => String(candidate.id) === protocolTargetProjectId.value,
  )
  if (!item || !project)
    return
  protocolDraftModalVisible.value = false
  await routerPushByKey("protocol-editor", {
    params: {
      labUid: project.lab_uid,
      projectUid: project.uid,
      protocolUid: "new",
      protocolVersion: "",
    },
    query: {
      show_ai_create: "true",
      knowledge_id: item.id,
      knowledge_revision: String(item.revision),
    },
  })
}

function publishPayload() {
  if (!publishingItem.value)
    throw new Error("No Knowledge item selected")
  if (publishingItem.value.scope_type === "project") {
    return {
      target_scope_type: "lab" as const,
      target_lab_id: publishingItem.value.lab_id || undefined,
    }
  }
  const project = projects.value.find(item => String(item.id) === publishTargetProjectId.value)
  if (!project)
    throw new Error("Target Project is required")
  return {
    target_scope_type: "project" as const,
    target_lab_id: String(project.lab_id),
    target_project_id: String(project.id),
  }
}

async function previewPublish() {
  if (!publishingItem.value)
    return
  publishSaving.value = true
  try {
    publishPreview.value = await previewKnowledgePublish(publishingItem.value.id, publishPayload())
  }
  finally {
    publishSaving.value = false
  }
}

async function confirmPublish() {
  if (!publishingItem.value || !publishPreview.value)
    return
  publishSaving.value = true
  try {
    await confirmKnowledgePublish(publishingItem.value.id, {
      ...publishPayload(),
      expected_revision: publishingItem.value.revision,
      preview_digest: publishPreview.value.preview_digest,
    })
    window.$message?.success($t("page.knowledge.published"))
    publishModalVisible.value = false
    await loadCurrentView()
  }
  finally {
    publishSaving.value = false
  }
}

function handlePaperImported(entry: PaperLibraryEntry) {
  activeView.value = "papers"
  void loadCurrentView().then(() => openPaper(entry.id))
}

function handleKnowledgeSaved() {
  activeView.value = "items"
  void loadCurrentView()
}

function visibilityLabel(value: KnowledgeVisibility) {
  const key = value === "private"
    ? "visibilityPrivate"
    : value === "lab"
      ? "visibilityLab"
      : value === "project"
        ? "visibilityProject"
        : "visibilityRestricted"
  return $t(`page.knowledge.${key}` as I18n.I18nKey)
}

function kindLabel(value: KnowledgeKind) {
  const suffix = value.charAt(0).toUpperCase() + value.slice(1)
  return $t(`page.knowledge.kind${suffix}` as I18n.I18nKey)
}

function stateLabel(value: KnowledgeState) {
  const suffix = value.charAt(0).toUpperCase() + value.slice(1)
  return $t(`page.knowledge.state${suffix}` as I18n.I18nKey)
}

function stateType(value: KnowledgeState): TagProps["type"] {
  if (value === "reviewed")
    return "success"
  if (value === "suggested")
    return "info"
  if (value === "superseded" || value === "archived")
    return "default"
  return "warning"
}

watch(contextKey, async () => {
  if (!["knowledge-home", "project-knowledge", "lab-knowledge"].includes(String(route.name)))
    return
  activeView.value = knowledgeViewFromQuery(route.query.view)
  if (await loadContexts())
    await loadCurrentView()
}, { immediate: true })

watch(() => route.query.view, () => {
  activeView.value = knowledgeViewFromQuery(route.query.view)
  if (contextReady.value)
    void loadCurrentView()
})

onMounted(async () => {
  try {
    if (contextLocked.value && !projects.value.length && authStore.userInfo.id) {
      const result = await fetchUserProjects(authStore.userInfo.id, { page: 1, pageSize: 100, sortedBy: "updated_at" })
      projects.value = result?.projects || []
    }
  }
  catch {
    // Optional publication destinations must not block the current knowledge scope.
  }
})

onBeforeUnmount(() => {
  contextSequence++
  viewSequence++
})
</script>

<style scoped>
.knowledge-page {
  width: 100%;
}

.knowledge-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid rgb(229 231 235);
}

.knowledge-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.knowledge-scope-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.5rem;
  background: white;
  padding: 0.5rem 0.75rem;
  color: rgb(75 85 99);
}

.knowledge-card {
  display: block;
  width: 100%;
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
  text-align: left;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.knowledge-evidence-source {
  border: 1px solid rgb(209 250 229);
  border-radius: 0.625rem;
  background: rgb(236 253 245 / 52%);
  padding: 0.75rem;
}

button.knowledge-card:hover,
button.knowledge-card:focus-visible {
  border-color: rgb(16 185 129 / 45%);
  box-shadow: 0 10px 28px rgb(15 23 42 / 8%);
  outline: none;
  transform: translateY(-1px);
}

.knowledge-empty {
  min-height: 18rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.knowledge-preview-card {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1rem;
}

@media (max-width: 48rem) {
  .knowledge-hero {
    flex-direction: column;
  }
}
</style>
