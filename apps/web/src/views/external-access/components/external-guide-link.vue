<script setup lang="ts">
import { useAppStore } from "@/store/modules/app"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { documentationPageUrl } from "@airalogy/shared/utils"

const app = useAppStore()
const instance = useInstanceStore()
const href = computed(() => documentationPageUrl(instance.documentationUrl, app.locale, "external-agent-access"))
</script>

<template>
  <a :href="href" target="_blank" rel="noopener" class="text-sm underline">{{ $t("externalAccess.documentation") }}</a>
</template>
