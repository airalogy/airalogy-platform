<template>
  <section class="mx-auto w-full max-w-xl px-4 py-12 sm:py-20" aria-live="polite" data-testid="resource-access-state">
    <h1 class="m-0 text-xl font-semibold">
      {{ $t(temporary ? "resourceAccess.loadFailed" : guest ? "resourceAccess.signInTitle" : "resourceAccess.unavailable") }}
    </h1>
    <p class="mt-2 text-sm color-text-secondary leading-relaxed">
      {{ $t(temporary ? "resourceAccess.retryHint" : guest ? "resourceAccess.signInHint" : "resourceAccess.unavailableHint") }}
    </p>
    <div class="mt-5 flex flex-wrap items-center gap-4">
      <n-button v-if="temporary" type="primary" @click="$emit('retry')">
        {{ $t("resourceAccess.retry") }}
      </n-button>
      <router-link v-else-if="guest" :to="{ name: 'login', query: { redirect: route.fullPath } }" custom v-slot="{ href, navigate }">
        <n-button tag="a" :href="href" type="primary" @click="navigate">{{ $t("resourceAccess.signIn") }}</n-button>
      </router-link>
      <router-link :to="{ name: guest ? 'root' : 'home' }" class="text-sm text-primary">{{ $t("common.backToHome") }}</router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { ResourceFailure } from "@/utils/resource-access"
import { useAuthStore } from "@/store/modules/auth"

const props = defineProps<{ failure: ResourceFailure }>()
defineEmits<{ retry: [] }>()
const route = useRoute()
const auth = useAuthStore()
const guest = computed(() => !auth.isLogin)
const temporary = computed(() => props.failure === "temporary")
</script>
