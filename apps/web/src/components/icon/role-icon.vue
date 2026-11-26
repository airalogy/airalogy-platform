<template>
  <n-avatar :size="40" :src="src || source" color="transparent" object-fit="cover" :fallback-src="source" />
</template>

<script setup lang="ts">
import { LabRole, ProjectRole } from "@/enum"

interface IProps {
  role?: Api.Lab.LabRole | Api.Project.ProjectRole
  type: "lab" | "project" | "group" | "guest"
  src?: string | null
}

const props = withDefaults(defineProps<IProps>(), { role: 1, src: null })
const source = computed(() => {
  const { role, type } = props

  if (type === "guest")
    return "/images/role_member.png"

  if (type === "lab") {
    if (role === LabRole.OWNER)
      return "/images/role_owner.png"
    if (role === LabRole.MANAGER)
      return "/images/role_manager.png"
    if (role === LabRole.MEMBER)
      return "/images/role_member.png"
  }
  else if (type === "project") {
    if (role === ProjectRole.MANAGER)
      return "/images/role_manager.png"

    return "/images/role_member.png"
  }

  return "/images/role_default.png"
})
</script>

<style scoped></style>
