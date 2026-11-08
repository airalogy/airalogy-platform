<script setup lang="ts">
import type { ResearchLogScopeParams } from "@/service/api/research-log"
import { useI18n } from "vue-i18n"

defineProps<{ scope: ResearchLogScopeParams, name?: string, compact?: boolean }>()
const { t } = useI18n()
</script>

<template>
  <div class="document-audience text-sm leading-relaxed" :class="compact ? 'text-gray-600' : 'rounded-lg bg-gray-50 px-3 py-2'" data-testid="document-audience">
    <p class="m-0 break-words font-medium">
      {{ t('page.researchDocuments.scope') }}：{{ name || t(`page.documentTemplates.${scope.scope_type}`) }}
      · {{ t(`page.documentBrowse.audience${scope.scope_type}`) }}
    </p>
    <p v-if="!compact && scope.scope_type !== 'personal'" class="aira-type-meta m-0 mt-1">
      {{ t('page.documentBrowse.draftAudience') }}
    </p>
  </div>
</template>
