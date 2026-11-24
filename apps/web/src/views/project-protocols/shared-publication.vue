<script setup lang="ts">
import type { Publication } from "@/service/api/sharing"
import ResourceAccessState from "@/components/common/resource-access-state.vue"
import SharedProtocolText from "@/components/protocol/shared-protocol-text"
import { useResourcePage } from "@/composables/useResourcePage"
import { sharing } from "@/service/api/sharing"

const route = useRoute()
const page = ref<Publication | null>(null)
const { failure, retry } = useResourcePage(() => String(route.params.id), async (signal) => {
  const { data, error } = await sharing.read(String(route.params.id), signal)
  if (!data)
    throw error
  return data
}, (value) => { page.value = value })
async function download(name: string) {
  if (!page.value)
    return
  const { data } = await sharing.file(page.value.id, name)
  if (!data)
    return
  const url = URL.createObjectURL(data)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = name.split("/").pop() || name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <main class="mx-auto max-w-3xl px-4 py-8 space-y-5">
    <resource-access-state v-if="failure" :failure="failure" @retry="retry" />
    <template v-else-if="page">
      <header>
        <p class="text-sm color-text-secondary">
          {{ $t(page.audience === 'public' ? 'sharing.public' : 'sharing.organization') }}
        </p>
        <h1 class="break-words text-2xl">
          {{ page.title }}
        </h1>
        <p v-if="page.version">
          v{{ page.version }}
        </p>
      </header>
      <shared-protocol-text :body="page.body" />
      <section v-if="page.materials.length">
        <h2>{{ $t('sharing.materials') }}</h2>
        <n-button v-for="name in page.materials" :key="name" text block class="mb-2" @click="download(name)">
          {{ name }}
        </n-button>
      </section>
      <section v-if="!page.version">
        <h2>{{ $t('sharing.versions') }}</h2>
        <p v-if="!page.protocols.length">
          {{ $t('sharing.noVersions') }}
        </p>
        <p v-for="item in page.protocols" :key="item.path">
          <router-link :to="item.path" class="text-primary">
            {{ item.title }} · v{{ item.version }}
          </router-link>
        </p>
      </section>
    </template>
    <n-spin v-else />
  </main>
</template>
