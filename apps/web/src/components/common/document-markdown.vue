<script setup lang="ts">
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import DOMPurify from "dompurify"
import { marked } from "marked"

const props = defineProps<{ body: string, format: "aimd" | "md" }>()
const html = computed(() =>
  props.format === "md" ? DOMPurify.sanitize(marked.parse(props.body, { async: false })) : "",
)
</script>

<template>
  <aimd-markdown-preview v-if="format === 'aimd'" :content="body" />
  <article v-else class="markdown-body min-w-0 break-words" v-html="html" />
</template>
