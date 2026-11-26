<script setup lang="ts">
import { guestDirectory, type GuestPerson } from "@/service/api/project-guests"

const people = ref<GuestPerson[]>()
onMounted(async () => {
  const { data } = await guestDirectory()
  if (data)
    people.value = data
})
</script>

<template>
  <ul class="m-0 list-none p-0">
    <li v-for="person in people" :key="person.id" class="grid gap-1 border-b py-3">
      <div class="flex flex-wrap items-baseline gap-2">
        <strong>{{ person.name }}</strong><span class="aira-type-meta break-all">{{ person.email }}</span>
      </div>
      <span>{{ person.projects.join(" · ") || $t("page.guests.noProjects") }}</span>
    </li>
  </ul>
  <p v-if="people && !people.length">
    {{ $t("page.guests.empty") }}
  </p>
</template>
