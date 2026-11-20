import type { ProjectWork, WorkContent } from "./project-work"
import { documentRequest } from "./research-documents"

export interface MeetingParticipant {
  user_id: string | null
  person_id?: string | null
  name: string
  organization: string
  attendance: "attended" | "invited" | "absent" | "unknown"
}
export interface MeetingAccess {
  user_id: string
  role: "viewer" | "commenter" | "editor"
}
export interface MeetingContent {
  title: string
  body: string
  status: "held" | "planned" | "cancelled"
  occurred_at: string | null
  scheduled_at: string | null
  time_precision: "date" | "datetime"
  time_zone: string
  visibility: "project" | "selected"
  participants: MeetingParticipant[]
  access: MeetingAccess[]
}
export interface Meeting extends MeetingContent {
  id: string
  project_id: string
  revision: number
  created_at: string
  updated_at: string
  can_manage: boolean
  can_edit: boolean
  can_comment: boolean
  can_create_work: boolean
  work?: { relation: string, source_revision: number, item: ProjectWork }[]
}
export interface MeetingMember {
  id: string
  name: string
  username: string
  can_write: boolean
}
export interface MeetingComment {
  id: string
  body: string
  created_at: string
  author: { id: string, name: string, username: string }
}
export function meetingContent(m: MeetingContent): MeetingContent {
  return {
    title: m.title,
    body: m.body,
    status: m.status,
    occurred_at: m.occurred_at,
    scheduled_at: m.scheduled_at,
    time_precision: m.time_precision,
    time_zone: m.time_zone,
    visibility: m.visibility,
    participants: m.participants,
    access: m.access,
  }
}
export function listMeetings(params: {
  project_id: string
  q?: string
  participant_id?: string
  person_id?: string
  status?: string
  date_from?: string
  date_to?: string
  time_zone: string
  page?: number
}) {
  return documentRequest<{ items: Meeting[], total: number, can_write: boolean }>({
    url: "/meetings",
    params,
  })
}
export const getMeeting = (id: string) => documentRequest<Meeting>({ url: `/meetings/${id}` })
export async function meetingMembers(projectId: string) {
  const result = await documentRequest<{ members: (MeetingMember & { display_name?: string })[] }>({
    url: "/meetings/members",
    params: { project_id: projectId },
  })
  return { members: result.members.map(member => ({ ...member, name: member.display_name || member.name || member.username })) }
}
export function saveMeeting(id: string, projectId: string, content: MeetingContent, revision?: number) {
  return documentRequest<Meeting>({
    url: revision ? `/meetings/${id}` : "/meetings",
    method: revision ? "PUT" : "POST",
    data: {
      ...content,
      ...(revision ? { expected_revision: revision } : { id, project_id: projectId }),
    },
  })
}
export function meetingComments(id: string, page = 1) {
  return documentRequest<{ items: MeetingComment[], total: number }>({
    url: `/meetings/${id}/comments`,
    params: { page },
  })
}
export function addMeetingComment(id: string, requestId: string, body: string) {
  return documentRequest({
    url: `/meetings/${id}/comments`,
    method: "POST",
    data: { id: requestId, body },
  })
}
export function linkMeetingWork(id: string, taskId: string, revision: number) {
  return documentRequest<Meeting>({
    url: `/meetings/${id}/work`,
    method: "POST",
    data: { task_id: taskId, expected_revision: revision },
  })
}
export function createMeetingAction(id: string, data: {
  id: string
  expected_revision: number
  title: string
  assignee_user_id: string | null
  planned_end: string | null
}) {
  return documentRequest<Meeting>({ url: `/meetings/${id}/actions`, method: "POST", data })
}

export interface MeetingActionDraft extends WorkContent { id: string }
export function saveMeetingActions(id: string, requestId: string, revision: number, actions: MeetingActionDraft[], existingWorkIds: string[] = []) {
  return documentRequest<Meeting>({ url: `/meetings/${id}/actions/batch`, method: "POST", data: { request_id: requestId, expected_revision: revision, actions, existing_work_ids: existingWorkIds } })
}

export function saveMeetingWithActions(id: string, projectId: string, content: MeetingContent, requestId: string, actions: MeetingActionDraft[], existingWorkIds: string[] = []) {
  return documentRequest<Meeting>({ url: "/meetings/with-actions", method: "POST", data: { meeting: { ...content, id, project_id: projectId }, actions: { request_id: requestId, expected_revision: 1, actions, existing_work_ids: existingWorkIds } } })
}

export interface MeetingProposal {
  title: string
  body: string
  occurred_on: string | null
  actions: string[]
}

export function meetingDraftAvailability(projectId: string, signal: AbortSignal) {
  return documentRequest<{ available: boolean }>({ url: "/meetings/aira/availability", signal, params: { project_id: projectId } })
}

export interface MeetingConversation {
  id: string
  project_id: string
  meeting_id: string | null
  turns: { user: string, reply: string }[]
  proposal: MeetingProposal | null
}

export function getMeetingConversation(id: string, signal: AbortSignal) {
  return documentRequest<MeetingConversation>({ url: `/meetings/aira/conversations/${id}`, signal })
}

export function requestMeetingDraft(projectId: string, message: string, conversationId: string, meetingId: string | null, expectedTurns: number, requestId: string, signal: AbortSignal) {
  return documentRequest<MeetingConversation>({
    url: "/meetings/aira/draft",
    signal,
    timeout: 100_000,
    method: "POST",
    data: { project_id: projectId, message, conversation_id: conversationId, meeting_id: meetingId, expected_turns: expectedTurns, request_id: requestId },
  })
}
