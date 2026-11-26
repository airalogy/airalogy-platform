import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"

export function useConfirmDocumentChange() {
  const dialog = useDialog()
  const { t } = useI18n()
  return (message: string) => new Promise<boolean>((resolve) => {
    dialog.warning({
      title: t("page.meetings.unsaved"),
      content: message,
      positiveText: t("common.confirm"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
