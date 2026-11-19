import type { UploadFileInfo } from "naive-ui"
import type { ComputedRef, Ref } from "vue"

export function useLogoUpload(
  logoValue: Ref<string | undefined>,
  logoUrlValue?: ComputedRef<string | undefined>,
) {
  const defaultFileList = computed(() => {
    if (!logoValue.value) {
      return []
    }

    return [{
      id: logoValue.value,
      name: logoValue.value,
      url: logoUrlValue?.value || logoValue.value,
      status: "finished",
    } as UploadFileInfo]
  })

  function handleSelectLogo(fileInfo: {
    file: UploadFileInfo
    fileList: UploadFileInfo[]
    event?: Event | undefined
  }) {
    if (fileInfo.file.status === "removed")
      logoValue.value = undefined
  }

  function handleUploadedLogo(fileInfo: Api.Attachment.AttachmentItem) {
    const { id } = fileInfo
    logoValue.value = id
  }

  return {
    defaultFileList,
    handleSelectLogo,
    handleUploadedLogo,
  }
}
