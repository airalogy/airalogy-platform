import type { MeetingProposal } from "@/service/api/meetings"
import type { InjectionKey, Ref } from "vue"

export interface MeetingHandoff {
  key: string
  projectId: string
  proposal: MeetingProposal
}

export const meetingHandoffKey: InjectionKey<Ref<MeetingHandoff | null>> = Symbol("meetingHandoff")
export interface MinutesDraft {
  prompt: string
  apply: (proposal: MeetingProposal) => boolean
}
export const organizeMinutesKey: InjectionKey<{ available: Ref<boolean>, visible: Ref<boolean>, open: (draft: MinutesDraft, trigger: HTMLElement) => void }> = Symbol("organizeMinutes")
export const meetingNameKey: InjectionKey<Ref<string>> = Symbol("meetingName")
