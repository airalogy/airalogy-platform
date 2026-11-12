<script setup lang="ts">
import type { recentResearchDocuments } from "@/service/api/research-documents"
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"

defineProps<{ items: Awaited<ReturnType<typeof recentResearchDocuments>>["items"] }>()
const { t } = useOrganizationTranslation()
</script>

<template>
  <section v-if="items.length" data-testid="home-recent-documents" class="mt-5 border border-gray-200 rounded-xl p-4">
    <h2 class="aira-type-card-title">
      {{ t("page.researchDocuments.recent") }}
    </h2>
    <div class="flex flex-col gap-2">
      <router-link
        v-for="item in items"
        :key="item.id"
        :to="{ name: 'research-document-detail', params: { documentId: item.id } }"
        class="break-words text-primary hover:underline"
      >
        {{ item.title }}
      </router-link>
    </div>
  </section>
</template>
