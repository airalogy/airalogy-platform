<template>
  <main class="mx-auto w-full max-w-xl px-4 py-16">
    <h1 class="m-0 text-xl font-semibold">{{ $t(copy[0]) }}</h1>
    <p class="mt-2 text-sm color-text-secondary">{{ $t(copy[1]) }}</p>
    <router-link to="/" class="mt-4 inline-block text-primary">{{ $t("common.backToHome") }}</router-link>
  </main>
</template>

<script setup lang="ts">
const props = defineProps<{ type: "403" | "404" | "500" }>()
const messages = {
  403: ["resourceAccess.forbidden", "resourceAccess.forbiddenHint"],
  404: ["resourceAccess.missing", "resourceAccess.missingHint"],
  500: ["resourceAccess.loadFailed", "resourceAccess.retryHint"],
} as const
const copy = computed(() => messages[props.type])
</script>
