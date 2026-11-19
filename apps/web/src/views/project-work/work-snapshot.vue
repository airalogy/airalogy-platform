<script setup lang="ts">
import type { ProjectPerson } from "@/service/api/project-people"
import type { ProjectWork } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"
import EvidenceLinks from "./evidence-links.vue"

const props = defineProps<{
  item: ProjectWork
  people?: ProjectPerson[]
  members: { id: string, name: string }[]
  items: ProjectWork[]
  projectId: string
}>()
const { t } = useI18n()
function person(id: string | null) {
  return props.members.find(member => member.id === id)?.name
    || t(id ? "page.projectWork.formerMember" : "page.projectWork.unassigned")
}
function personName(id: string | null) {
  return props.people?.find(p => p.id === id)?.display_name
    || props.item.people_snapshot?.find(p => p.id === id)?.name
}
const fields = computed(() => [
  ["titleLabel", props.item.title],
  ["kind", t(`page.projectWork.kinds.${props.item.kind}`)],
  ["state", t(`page.projectWork.states.${props.item.state}`)],
  ["priority", t(`page.projectWork.priorities.${props.item.priority}`)],
  ["assignee", personName(props.item.assignee_person_id) || person(props.item.assignee_user_id)],
  ["collaborators", [...props.item.collaborator_ids.map(person), ...(props.item.collaborator_person_ids || []).map(id => personName(id) || "")].join(" · ")],
  ["goal", props.item.goal],
  ["acceptance", props.item.acceptance],
  ["start", props.item.planned_start],
  ["end", props.item.planned_end],
  ["deadlineNote", props.item.deadline_note],
  ["blocker", props.item.blocker],
  ["nextStep", props.item.next_step],
  ["dependencies", props.item.dependency_ids.map(id => props.items.find(item => item.id === id)?.title || t("page.projectWork.linkedWork")).join(" · ")],
])
</script>

<template>
  <section class="rounded bg-gray-50 p-3">
    <dl class="m-0 space-y-2">
      <template v-for="[key, value] in fields" :key="key!">
        <div v-if="value" class="grid grid-cols-1 gap-1 sm:grid-cols-[8rem_1fr]">
          <dt class="text-sm text-gray-500">{{ t(`page.projectWork.${key}`) }}</dt>
          <dd class="m-0 whitespace-pre-wrap break-words">{{ value }}</dd>
        </div>
      </template>
    </dl>
    <evidence-links v-if="item.evidence.length" class="mt-3" :model-value="item.evidence" :project-id="projectId" />
  </section>
</template>
