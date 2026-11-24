import type { MaybeRefOrGetter } from "vue"
import { ProjectType } from "@/enum"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { computed, toValue } from "vue"

export function useProjectVisibility(typeRef: MaybeRefOrGetter<ProjectType | undefined | null>, organizationReadable?: MaybeRefOrGetter<boolean | undefined>) {
  const instance = useInstanceStore()
  const visibilityLabel = computed(() => {
    const type = toValue(typeRef)
    if (type && instance.isSingleLab)
      return $t(toValue(organizationReadable) ? "sharing.organization" : "sharing.members")
    if (type === ProjectType.PRIVATE) {
      return $t("page.project.settingsPage.visibility.privateLabel")
    }
    if (type === ProjectType.PUBLIC) {
      return $t("page.project.settingsPage.visibility.publicLabel")
    }
    return ""
  })

  const visibilityClass = computed(() => {
    if (instance.isSingleLab && toValue(organizationReadable))
      return "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200"
    const type = toValue(typeRef)
    if (type === ProjectType.PRIVATE) {
      return "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200"
    }
    if (type === ProjectType.PUBLIC) {
      return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200"
    }
    return ""
  })

  return {
    visibilityLabel,
    visibilityClass,
  }
}
