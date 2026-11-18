import type { MeetingProposal } from "@/service/api/meetings"
import type { InjectionKey, Ref } from "vue"

export interface MeetingHandoff {
  key: string
  projectId: string
  proposal: MeetingProposal
}

export const meetingHandoffKey: InjectionKey<Ref<MeetingHandoff | null>> = Symbol("meetingHandoff")
