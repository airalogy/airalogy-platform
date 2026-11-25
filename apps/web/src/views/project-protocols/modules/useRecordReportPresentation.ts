import type { AimdRecordPresentation } from "@airalogy/aimd-renderer/vue"
import { createGlobalState, useLocalStorage } from "@vueuse/core"

export const useRecordReportPresentation = createGlobalState(() =>
  useLocalStorage<AimdRecordPresentation>("airalogy.recordReport.presentation", "detailed", { writeDefaults: false }))
