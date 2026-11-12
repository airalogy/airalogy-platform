<script setup lang="ts">
import type { RatingSummary } from "@/service/api/protocol-rating"
import { ratingApi } from "@/service/api/protocol-rating"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import ProtocolRatingPanel from "./protocol-rating-panel.vue"

const props = defineProps<{ protocolId: string | number, version: string, recordId?: string, compact?: boolean, publicOnly?: boolean }>()
const show = ref(false)
const summary = ref<RatingSummary | null>(null)
const auth = useAuthStore()
let sequence = 0
async function load() {
  const seq = ++sequence
  summary.value = null
  if (!props.compact || !props.version)
    return
  const result = await ratingApi.summary(String(props.protocolId), props.version, props.publicOnly ? "public" : "accessible")
  if (seq === sequence && result.data)
    summary.value = result.data
}
watch(() => [props.protocolId, props.version, auth.userInfo.id], load, { immediate: true })
</script>

<template>
  <div class="min-w-0" @click.stop>
    <n-button text type="primary" class="max-w-full !whitespace-normal !text-left" :aria-label="$t('page.protocol.rating.open')" @click="show = true">
      <template v-if="compact && summary">
        {{ summary.score === null ? $t('page.protocol.rating.insufficient') : `${$t('page.protocol.rating.recommendation')} ${summary.score}/100` }}
        · {{ summary.rating_average === null ? '—' : `${summary.rating_average}/5` }} · {{ $t('page.protocol.rating.reviewers', { count: summary.rating_count }) }}
      </template>
      <template v-else>
        {{ $t(recordId ? 'page.protocol.rating.optionalFeedback' : 'page.protocol.rating.title') }}
      </template>
    </n-button>
    <n-modal v-model:show="show" preset="card" :title="$t('page.protocol.rating.title')" class="w-[min(900px,calc(100vw-32px))]" :style="{ maxHeight: 'calc(100dvh - 32px)', overflowY: 'auto' }" :mask-closable="false">
      <protocol-rating-panel v-if="show" embedded :protocol-id="String(protocolId)" :version="version" :record-id="recordId" :initial-scope="publicOnly ? 'public' : 'accessible'" @changed="load" />
    </n-modal>
  </div>
</template>
