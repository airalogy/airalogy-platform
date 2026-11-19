<template>
  <nav class="footer-links" :aria-label="props.title">
    <span class="footer-links__label">{{ props.title }}</span>
    <template v-for="item in props.list" :key="item.name">
      <a v-if="item.external && typeof item.to === 'string'" :href="item.to" target="_blank" rel="noopener noreferrer">
        <img v-if="item.icon" :src="item.icon" alt="">
        {{ item.name }}
      </a>
      <router-link v-else :to="item.to">
        <img v-if="item.icon" :src="item.icon" alt="">
        {{ item.name }}
      </router-link>
    </template>
  </nav>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"

interface IProps {
  title: string
  list: { name: string, to: RouteLocationRaw, external?: boolean, icon?: string }[]
}
const props = withDefaults(defineProps<IProps>(), {
  title: "GO",
  list: () => [],
})
</script>

<style scoped>
.footer-links { display: flex; flex-wrap: wrap; align-items: center; gap: 0 0.5rem; }
.footer-links__label { color: #536780; }
a { display: inline-flex; align-items: center; min-height: 2.75rem; gap: 0.25rem; color: #29496b; text-decoration: none; }
a:hover { text-decoration: underline; }
img { width: 1rem; height: 1rem; }
</style>
