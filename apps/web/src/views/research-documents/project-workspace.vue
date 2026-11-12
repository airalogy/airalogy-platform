<script setup lang="ts">
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"
import { useAuthStore } from "@/store/modules/auth"
import WorkSummary from "@/views/project-work/work-summary.vue"
import { useProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import DocumentList from "./document-list.vue"
import MaterialLibrary from "./material-library.vue"

const { projectInfo } = useProjectInfoStore()
const auth = useAuthStore()
const route = useRoute()
const { t } = useOrganizationTranslation()
const scope = computed(() =>
  projectInfo.value
    ? {
        scope_type: "project" as const,
        lab_id: projectInfo.value.lab_id,
        project_id: projectInfo.value.id,
      }
    : null,
)
const overview = computed(() => route.name === "project-overview")
const materials = computed(() => route.name === "project-materials")
</script>

<template>
  <div v-if="scope" class="min-w-0 space-y-6" data-testid="project-research-workspace">
    <h1 v-if="overview || materials" class="aira-type-page-title">
      {{
        t(
          materials
            ? "page.researchDocuments.materials"
            : overview
              ? "page.researchDocuments.overview"
              : "page.documentUx.documents",
        )
      }}
    </h1>
    <template v-if="auth.isLogin">
      <work-summary v-if="overview" :project-id="scope.project_id" />
      <material-library v-if="materials" :scope="scope" />
      <document-list v-else :scope="scope" :scope-name="projectInfo?.name" :compact="overview" />
      <router-link v-if="overview" :to="{ name: 'project-documents', params: route.params }" class="inline-block text-primary">
        {{ t('page.researchDocuments.viewDocuments') }}
      </router-link>
    </template>
    <router-link v-else :to="{ name: 'project-protocols', params: route.params }">
      <n-button type="primary">
        {{ t("page.researchDocuments.viewProtocols") }}
      </n-button>
    </router-link>
  </div>
</template>
