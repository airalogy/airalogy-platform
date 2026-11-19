<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import { documentRequest } from "@/service/api/research-documents"
import { useI18n } from "vue-i18n"
import ResearchActivity from "../research-activity/index.vue"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"

interface WorkLink { id: string, title: string }
interface OverviewProject {
  id: string
  uid: string
  name: string
  owners: string[]
  blockers: (WorkLink & { text: string })[]
  next_steps: (WorkLink & { text: string })[]
  milestone: (WorkLink & { date: string | null }) | null
}
const { labInfo } = useOrProvideLabInfoStore(null)
const { t } = useI18n()
const projects = ref<OverviewProject[]>([])
const state = ref<"loading" | "ready" | "error">("loading")
const retry = ref(0)
watch([() => labInfo.value?.id, retry], async ([id], _, cleanup) => {
  let active = true
  cleanup(() => {
    active = false
  })
  projects.value = []
  state.value = "loading"
  if (!id)
    return
  try {
    const result = await documentRequest<{ projects: OverviewProject[] }>({ url: `/project-work/organizations/${id}/overview` })
    if (active) {
      projects.value = result.projects
      state.value = "ready"
    }
  }
  catch {
    if (active)
      state.value = "error"
  }
}, { immediate: true })
function link(project: OverviewProject, item?: WorkLink): RouteLocationRaw {
  return {
    name: item ? "project-work" : "project-overview",
    params: { labUid: labInfo.value?.uid, projectUid: project.uid },
    query: item ? { item: item.id } : {},
  }
}
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="org-research-overview">
    <n-spin v-if="state === 'loading'" size="small" />
    <n-alert v-else-if="state === 'error'" type="error" role="alert">
      {{ t('page.orgResearch.error') }}
      <n-button size="small" @click="retry++">
        {{ t('page.orgResearch.retry') }}
      </n-button>
    </n-alert>
    <template v-else-if="labInfo">
      <section aria-labelledby="org-projects" class="overview-projects">
        <h2 id="org-projects">{{ t('page.orgResearch.projects') }} <small>({{ projects.length }})</small></h2>
        <p v-if="!projects.length">{{ t('page.orgResearch.empty') }}</p>
        <article v-for="project in projects" :key="project.id" data-testid="org-project">
          <header>
            <router-link :to="link(project)" class="font-semibold">{{ project.name }}</router-link>
            <span>{{ t('page.orgResearch.owner') }} · {{ project.owners.join(' / ') || t('page.orgResearch.noOwner') }}</span>
          </header>
          <dl>
            <div v-for="column in (['blockers', 'next_steps'] as const)" :key="column">
              <dt>{{ t(column === 'blockers' ? 'page.orgResearch.blockers' : 'page.orgResearch.next') }}</dt>
              <dd v-if="project[column].length">
                <router-link :to="link(project, project[column][0])">
                  {{ project[column][0].text || project[column][0].title }}
                </router-link>
                <details v-if="project[column].length > 1">
                  <summary>{{ t('page.orgResearch.more', { count: project[column].length - 1 }) }}</summary>
                  <router-link v-for="entry in project[column].slice(1)" :key="entry.id" :to="link(project, entry)">
                    {{ entry.text || entry.title }}
                  </router-link>
                </details>
              </dd>
              <dd v-else class="muted">{{ t(column === 'blockers' ? 'page.orgResearch.noBlockers' : 'page.orgResearch.noNext') }}</dd>
            </div>
            <div>
              <dt>{{ t('page.orgResearch.milestone') }}</dt>
              <dd v-if="project.milestone">
                <router-link :to="link(project, project.milestone)">{{ project.milestone.title }}</router-link>
                <small>{{ project.milestone.date || t('page.orgResearch.noDate') }}</small>
              </dd>
              <dd v-else class="muted">{{ t('page.orgResearch.noMilestone') }}</dd>
            </div>
          </dl>
        </article>
      </section>
      <research-activity :scope="{ scope_type: 'lab', lab_id: labInfo.id }" compact organization-overview />
    </template>
  </section>
</template>

<style scoped>
.overview-projects { border: 1px solid #dbe3ed; border-radius: .75rem; padding: 1rem 1.25rem; }
h2 { margin: 0; font-size: 1.2rem; }
article { border-top: 1px solid #e1e7ef; margin-top: .8rem; padding-top: .8rem; overflow-wrap: anywhere; }
header { display: flex; align-items: baseline; flex-wrap: wrap; gap: .25rem 1rem; }
header span, dt, small, .muted { font-size: .85rem; color: #52647a; }
dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem 1rem; margin: .6rem 0 0; }
dd { margin: .15rem 0 0; }
a { color: #164e8c; }
a:hover { text-decoration: underline; }
small { margin-inline-start: .4em; }
details a { display: block; }
summary { cursor: pointer; color: #465d77; font-size: .85rem; }
@media (max-width: 639px) {
  dl { grid-template-columns: 1fr; }
  dl > div { display: grid; grid-template-columns: 6rem minmax(0,1fr); gap: .5rem; }
  dd { margin: 0; }
}
</style>
