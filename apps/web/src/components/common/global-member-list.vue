<template>
  <n-list class="member-list" hoverable>
    <n-list-item v-for="item in props.list" :key="item.id" class="member-list__item">
      <template #prefix>
        <n-avatar
          v-if="item.avatar_url"
          :src="item.avatar_url"
          :size="40"
          color="transparent"
          object-fit="cover"
          class="vertical-middle"
        />
        <role-icon v-else :type="props.type" :role="roleRecord[item.id]" />
      </template>
      <global-member-item
        :item="item"
        directory-entry
        :is-compact="false"
        :type="props.type"
        :project-type="projectInfo?.type"
        class="min-w-0 w-fit"
      />
      <template v-if="checkPermission(item)" #suffix>
        <n-dropdown
          v-if="isMobile"
          trigger="click"
          :options="mobileActionOptions(item)"
          @select="handleMobileAction($event, item)"
        >
          <n-button
            quaternary
            circle
            size="small"
            :aria-label="$t('common.actions')"
            :title="$t('common.actions')"
          >
            <template #icon>
              <icon-tabler-dots-vertical />
            </template>
          </n-button>
        </n-dropdown>
        <div v-else class="flex flex-wrap items-center gap-1">
          <n-button v-if="canConvert(item)" size="small" @click="openConversion(item)">{{ $t("page.guests.convert") }}</n-button>
          <n-button
            v-if="props.type === 'lab' && checkPermission(item)"
            class="mr-3"
            size="small"
            @click="showUpdateLabAliasDialog(item as Api.Lab.MemberListItem)"
          >
            {{ $t("common.setAlias") }}
          </n-button>
          <n-button
            v-if="props.type === 'lab' && instanceStore.isSingleLab && checkPermission(item)"
            class="mr-3"
            size="small"
            :loading="resettingUserId === item.id"
            @click="showPasswordResetLink(item as Api.Lab.MemberListItem)"
          >
            {{ $t("page.instance.createResetLink") }}
          </n-button>
          <n-button
            v-if="canChangeMemberRole"
            class="mr-3"
            size="small"
            @click="showRoleChangeDialog(item)"
          >
            {{ $t("common.changeRole") }}
          </n-button>
          <delete-button v-if="!checkIsSelf(item)" @click="handleRemoveUser(item)" />
        </div>
      </template>
    </n-list-item>
  </n-list>
  <guest-conversion v-if="converting" :key="converting.id" :user-id="converting.id" :name="converting.name"
                    @close="converting = null" @converted="converted" />
</template>

<script setup lang="tsx">
import type { RoleInfo } from "@/composables"
import type { ProjectRole } from "@/enum"
import type { DropdownOption } from "naive-ui"
import { getRoleLabel, projectRoleHierarchyPrivate, useBasicLayout, useClosableMessage, useRoleDescription } from "@/composables"
import { useLabPermissions } from "@/composables/useLabPermissions"
import { useProjectPermissions } from "@/composables/useProjectPermissions"
import { LabRole, ProjectType } from "@/enum"
import { deleteGroupsMember } from "@/service/api/groups"
import { createPasswordResetLink } from "@/service/api/instance"
import { deleteLabMember, putLabMember } from "@/service/api/labs"
import { deleteProjectMember, putProjectMember } from "@/service/api/projects"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideLabInfoStore } from "@/views/labs/hooks/useLabsInfoStore"
import GuestConversion from "@/views/labs/modules/guest-conversion.vue"
import UpdateAliasModal from "@/views/labs/modules/lab/UpdateAliasModal.vue"
import { useOrProvideProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { copyToClip } from "@airalogy/shared"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import RoleChangeDialog from "./role-change-dialog.vue"

defineOptions({ name: "GlobalMemberList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
})

const emit = defineEmits<IEmits>()

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const { isMobile } = useBasicLayout()
const resettingUserId = ref("")
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { labInfo } = useOrProvideLabInfoStore(null)

const {
  canAssignRoles,
  userRole: userProjectRole,
} = useProjectPermissions(projectInfo)

const {
  isOwner: isLabOwner,
  isManager: isLabManager,
} = useLabPermissions(labInfo)

interface IProps {
  type: "lab" | "project" | "group"
  id: string | string[] | number
  list: (Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem)[]
}

interface IEmits {
  (
    e: "update:role",
    payload: { id: string | number, role: Api.Lab.LabRole | Api.Project.ProjectRole },
  ): void
}

const roleRecord = computed(() => {
  return props.list.reduce(
    (acc, it) => {
      const { id } = it
      if (props.type === "lab") {
        acc[id] = (it as Api.Lab.MemberListItem).lab_role
      }
      else if (props.type === "project") {
        acc[id] = (it as Api.Project.MemberListItem).project_role
      }

      return acc
    },
    {} as Record<string, Api.Lab.LabRole>,
  )
})

const projectType = computed(() => projectInfo.value?.type)
const { projectRoleOptions } = useRoleDescription(userProjectRole, toRef(props.type), projectType, true)

const dialog = useDialog()
const message = useClosableMessage()
const { reloadPage } = useAppStore()
const { t } = useI18n()
const canChangeMemberRole = computed(() => props.type === "project" || (props.type === "lab" && isLabOwner.value))
const options = computed(() => props.type === "project"
  ? projectRoleOptions.value
  : [
      { label: t("role.manager"), value: LabRole.MANAGER },
      { label: t("role.member"), value: LabRole.MEMBER },
    ])

const converting = ref<{ id: string, name: string, role: Api.Lab.LabRole } | null>(null)
type DirectoryMember = IProps["list"][number]
function canConvert(item: DirectoryMember) {
  return props.type === "lab" && instanceStore.isSingleLab && !checkIsSelf(item) && checkPermission(item)
    && (item as Api.Lab.MemberListItem).lab_role !== LabRole.OWNER
}
function openConversion(item: DirectoryMember) {
  converting.value = { id: String(item.id), name: item.name || item.username, role: (item as Api.Lab.MemberListItem).lab_role }
}
function converted() {
  if (converting.value)
    emit("update:role", converting.value)
  converting.value = null
}

type MobileMemberAction = "convert" | "alias" | "reset-password" | "change-role" | "remove"

function mobileActionOptions(
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem,
): DropdownOption[] {
  return [
    ...(props.type === "lab" ? [{ label: t("common.setAlias"), key: "alias" }] : []),
    ...(props.type === "lab" && instanceStore.isSingleLab
      ? [{ label: t("page.instance.createResetLink"), key: "reset-password" }]
      : []),
    ...(canConvert(item) ? [{ label: t("page.guests.convert"), key: "convert" }] : []),
    ...(canChangeMemberRole.value ? [{ label: t("common.changeRole"), key: "change-role" }] : []),
    ...(!checkIsSelf(item) ? [{ label: t("common.remove"), key: "remove" }] : []),
  ]
}

function handleMobileAction(
  key: string | number,
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem,
) {
  switch (key as MobileMemberAction) {
    case "convert":
      openConversion(item)
      break
    case "alias":
      showUpdateLabAliasDialog(item as Api.Lab.MemberListItem)
      break
    case "reset-password":
      showPasswordResetLink(item as Api.Lab.MemberListItem)
      break
    case "change-role":
      showRoleChangeDialog(item)
      break
    case "remove":
      handleRemoveUser(item)
      break
  }
}

async function showPasswordResetLink(item: Api.Lab.MemberListItem) {
  resettingUserId.value = item.id
  try {
    const { data } = await createPasswordResetLink(String(item.id))
    if (!data)
      return

    const resetUrl = data.url
    dialog.info({
      title: t("page.instance.resetLinkFor", { name: item.name || item.username }),
      content: () => (
        <div class="space-y-3">
          <n-input value={resetUrl} readonly type="textarea" autosize={{ minRows: 2, maxRows: 4 }} />
          <div class="text-xs text-gray-500">
            {t("page.instance.linkExpiresAt", {
              time: new Intl.DateTimeFormat(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(new Date(data.expires_at)),
            })}
          </div>
          <n-button
            type="primary"
            onClick={async () => {
              await copyToClip(resetUrl)
              message.success(t("page.instance.linkCopied"))
            }}
          >
            {t("page.instance.copyResetLink")}
          </n-button>
        </div>
      ),
      positiveText: t("common.close"),
      showIcon: false,
    })
  }
  finally {
    resettingUserId.value = ""
  }
}

function handleRemoveUser(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: userId, username, name: userDisplayName } = item
  const { id: parentId, type } = props

  if (!userId || !parentId || Array.isArray(parentId)) {
    message.error(t("common.memberRemoveFailed"))
    return
  }

  const orgName = type === "group"
    ? t("common.group")
    : type === "project"
      ? (projectInfo.value?.name || t("common.project"))
      : (labInfo.value?.name || t("common.lab"))
  const roleName = getRoleLabel(
    type === "project" || type === "group"
      ? (item as Api.Project.MemberListItem).project_role
      : type === "lab" ? (item as Api.Lab.MemberListItem).lab_role : null,
    type,
  ) || t("role.member")

  dialog.error({
    title: orgName ? t("common.memberRemoveTitleWithOrg", { name: orgName }) : t("common.memberRemoveTitle"),
    showIcon: false,
    content: () => (
      <div>
        <div class="mb-2">{t("common.memberRemoveConfirm", { role: roleName, name: userDisplayName })}</div>

        <div class="flex items-center rounded-lg bg-gray-100 p-2">
          {item.avatar_url
            ? (
                <n-avatar
                  src={item.avatar_url}
                  size="small"
                  color="transparent"
                  object-fit="cover"
                  class="shrink-0"
                />
              )
            : <role-icon type={props.type} role={roleRecord.value[item.id]} />}

          <router-link
            to={{ name: "user-profile", params: { username: item.username } }}
            target="_blank"
            class="ml-2 !hover:router-link"
          >
            <span>{item.name || item.username}</span>
          </router-link>
        </div>
      </div>
    ),
    positiveText: t("common.remove"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      try {
        if (type === "lab") {
          const success = await deleteLabMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }
        if (type === "group") {
          const success = await deleteGroupsMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }
        if (type === "project") {
          const success = await deleteProjectMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }

        message.error(t("common.memberRemoveFailed"))
      }
      catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

function showUpdateLabAliasDialog(item: Api.Lab.MemberListItem) {
  const editor = ref<InstanceType<typeof UpdateAliasModal>>()
  const modal = dialog.info({
    title: t("common.setAlias"),
    content: () => h(UpdateAliasModal, {
      ref: editor,
      alias: item.lab_alias,
      label: t("common.labAliasLabel"),
      placeholder: t("common.labAliasPlaceholder"),
      hint: t("common.organizationNameHint"),
      maxlength: 255,
      required: false,
    }),
    positiveText: t("common.save"),
    negativeText: t("common.cancel"),
    showIcon: false,
    onPositiveClick: async () => {
      if (!editor.value || modal.loading)
        return false
      modal.loading = true
      try {
        const alias = await editor.value.getAlias()
        const { data, error } = await putLabMember(String(props.id), { userId: item.id, alias: alias.trim() || null })
        if (error || !data)
          throw new Error(t("common.memberNameSaveFailed"))
        emit("update:role", { id: item.id, role: item.lab_role })
        message.success(t("common.memberNameSaved"))
      }
      catch {
        message.error(t("common.memberNameSaveFailed"))
        return false
      }
      finally {
        modal.loading = false
      }
    },
  })
}

function showRoleChangeDialog(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const isProject = props.type === "project"
  const currentRole = isProject
    ? (item as Api.Project.MemberListItem).project_role
    : (item as Api.Lab.MemberListItem).lab_role

  const newRole = ref<ProjectRole | LabRole>(currentRole)
  const name = (item as Api.Lab.MemberListItem).lab_alias?.trim() || item.name || item.username
  const handleUpdateRole = (value: ProjectRole | LabRole) => {
    newRole.value = value
  }
  const modal = dialog.info({
    title: t("common.memberRoleTitle", { name }),
    content: () =>
      (
        <RoleChangeDialog
          availableRoles={options.value as RoleInfo[]}
          currentRole={currentRole}
          role={newRole.value}
          onUpdate:role={handleUpdateRole}
        />
      ),
    positiveText: t("common.save"),
    negativeText: t("common.cancel"),
    showIcon: false,
    style: { width: "min(36rem, calc(100vw - 2rem))" },
    onPositiveClick: async () => {
      if (newRole.value === currentRole)
        return
      if (modal.loading)
        return false
      modal.loading = true
      try {
        const parentId = Array.isArray(props.id) ? props.id.join("") : props.id
        if (!parentId || (isProject && projectType.value === ProjectType.PRIVATE && !projectRoleHierarchyPrivate.includes(newRole.value as ProjectRole)))
          throw new Error(t("common.memberRoleSaveFailed"))
        const result = isProject
          ? await putProjectMember(parentId, { role: newRole.value as ProjectRole, userId: item.id })
          : await putLabMember(parentId, { role: newRole.value as LabRole, userId: item.id })
        if (result.error || !result.data)
          throw new Error(t("common.memberRoleSaveFailed"))
        message.success(t("common.memberRoleSaved", { name, role: getRoleLabel(newRole.value, props.type) }))
        emit("update:role", { id: item.id, role: newRole.value })
      }
      catch {
        message.error(t("common.memberRoleSaveFailed"))
        return false
      }
      finally { modal.loading = false }
    },
  })
}

function checkIsSelf(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: userId } = authStore.userInfo
  return item.id === userId
}

function checkPermission(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: currentUserId } = authStore.userInfo
  if (item.id === currentUserId) {
    return false
  }

  if (props.type === "project") {
    return canAssignRoles.value && toValue(userProjectRole) < (item as Api.Project.MemberListItem).project_role
  }

  if (props.type === "lab" || props.type === "group") {
    if (isLabOwner.value) {
      return true
    }
    if (isLabManager.value) {
      const targetUserRole = (item as Api.Lab.MemberListItem).lab_role
      return targetUserRole > LabRole.MANAGER
    }
  }

  return false
}
</script>

<style scoped lang="sass">
@media (max-width: 639px)
  :deep(.member-list__item)
    padding: 12px 8px

  :deep(.member-list__item .n-list-item__main)
    min-width: 0

  :deep(.member-list__item .n-list-item__prefix)
    margin-right: 10px

  :deep(.member-list__item .n-list-item__suffix)
    flex-shrink: 0
    margin-left: 8px
</style>
