<script setup lang="ts">
import type { MeetingMember } from "@/service/api/meetings"
import type { ProjectPerson } from "@/service/api/project-people"
import type { ProjectWork } from "@/service/api/project-work"
import { useI18n } from "vue-i18n"

const props = defineProps<{ item: ProjectWork, members: MeetingMember[], people: ProjectPerson[], showEmpty?: boolean }>()
const { t } = useI18n()
const assignee = computed(() => {
  const person = props.item.people_snapshot?.find(p => p.id === props.item.assignee_person_id)
  const member = props.members.find(m => m.id === props.item.assignee_user_id)
  return props.people.find(p => p.id === props.item.assignee_person_id)?.display_name || person?.name || member?.name || member?.username || t("page.projectWork.unassigned")
})
</script>

<template>
  <span class="follow-details block text-sm">
    <span>{{ t(`page.projectWork.states.${item.state}`) }} · {{ t('page.projectWork.assignee') }} {{ assignee }}</span>
    <span v-if="item.blocker || showEmpty">{{ t('page.projectWork.blocker') }} · {{ item.blocker || t('page.meetings.notRecorded') }}</span>
    <span v-if="item.next_step || showEmpty">{{ t('page.projectWork.nextStep') }} · {{ item.next_step || t('page.meetings.notRecorded') }}</span>
  </span>
</template>

<style scoped>
.follow-details { color: #526074; overflow-wrap: anywhere; }
.follow-details > span { display: block; margin: 2px 0 0; white-space: pre-line; }
</style>
