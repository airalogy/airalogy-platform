<script setup lang="ts">
import { useAppStore } from "@/store/modules/app"
import { useInstanceStore } from "@/store/modules/instance"
import { documentationPageUrl } from "@airalogy/shared/utils"

const props = withDefaults(defineProps<{ lesson?: string }>(), { lesson: "" })
const app = useAppStore()
const instance = useInstanceStore()
const url = computed(() => documentationPageUrl(instance.documentationUrl, app.locale, `learn/${props.lesson}`))
</script>

<template>
  <a :href="url" target="_blank" rel="noopener noreferrer" class="max-w-full inline-flex items-center gap-1 text-sm text-primary hover:underline" data-testid="learning-link">
    <slot>{{ $t(lesson ? "page.learning.watch" : "page.learning.title") }}</slot>
    <span aria-hidden="true">↗</span>
  </a>
</template>
