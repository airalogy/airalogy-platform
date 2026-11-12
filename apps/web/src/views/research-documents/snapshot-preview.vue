<script setup lang="ts">
import { useOrganizationTranslation } from "@/composables/useOrganizationTranslation"

const props = defineProps<{ snapshot?: Record<string, unknown> }>()
const { t } = useOrganizationTranslation()
const content = computed(
  () => (props.snapshot?.content || props.snapshot || {}) as Record<string, unknown>,
)
const values = computed(() => {
  const document = content.value.document as Record<string, unknown> | undefined
  const data = (content.value.record_data || document?.record_data || {}) as Record<
    string,
    Record<string, unknown>
  >
  return Object.entries(data).flatMap(([scope, fields]) =>
    Object.entries(fields || {}).map(([field, value]) => ({ field: `${scope}.${field}`, value })),
  )
})
function display(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value)
}
</script>

<template>
  <section class="max-h-55vh overflow-y-auto rounded-lg bg-gray-50 p-4">
    <h3 class="aira-type-card-title break-words">
      {{ content.title }}
    </h3>
    <pre class="whitespace-pre-wrap break-words font-inherit">{{ content.body }}</pre>
    <h4 v-if="values.length">
      {{ t("page.researchDocuments.fill") }}
    </h4>
    <dl class="space-y-2">
      <div
        v-for="item in values"
        :key="item.field"
        class="grid grid-cols-1 gap-1 border-b border-gray-200 pb-2 sm:grid-cols-2"
      >
        <dt class="break-all">
          {{ item.field }}
        </dt><dd class="m-0 whitespace-pre-wrap break-all">
          {{ display(item.value) }}
        </dd>
      </div>
    </dl>
  </section>
</template>
