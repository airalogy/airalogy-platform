<script setup lang="ts">
import type { ProjectWork, WorkState } from "@/service/api/project-work"
import { workStates } from "@/service/api/project-work"
import { useSortable } from "@airalogy/composables"
import { useI18n } from "vue-i18n"

const props = defineProps<{ state: WorkState, items: ProjectWork[], enabled: boolean, group: string, owner: (item: ProjectWork) => string }>()
const emit = defineEmits<{ open: [id: string], move: [id: string, state: WorkState] }>()
const { t } = useI18n()
const list = ref<HTMLElement | null>(null)
const targets = computed(() => workStates.filter(state => state !== props.state).map(key => ({ key, label: t(`page.projectWork.states.${key}`) })))
const sortable = useSortable(list, () => props.items, {
  group: props.group,
  disabled: !props.enabled,
  sort: false,
  draggable: "[data-work-card]",
  handle: ".board-card-main",
  delayOnTouchOnly: true,
  delay: 220,
  touchStartThreshold: 5,
  ghostClass: "work-card-ghost",
  onEnd({ from, to, item, oldIndex }) {
    if (from === to)
      return
    // Vue owns the cards. Restore Sortable's DOM move until the server confirms it.
    from.insertBefore(item, from.children[oldIndex ?? 0] || null)
    const target = workStates.find(state => state === to.dataset.workState)
    if (props.enabled && item.dataset.workCard && target)
      emit("move", item.dataset.workCard, target)
  },
})
function selectState(id: string, event: Event) {
  const select = event.currentTarget as HTMLSelectElement
  const target = workStates.find(state => state === select.value)
  select.value = ""
  if (target && props.enabled)
    emit("move", id, target)
}

watch(() => props.enabled, enabled => sortable.option("disabled", !enabled))
</script>

<template>
  <section class="min-w-0 flex flex-col rounded-lg bg-gray-50 p-3" :aria-label="t(`page.projectWork.states.${state}`)">
    <h2 class="m-0 mb-2 text-sm font-semibold">
      {{ t(`page.projectWork.states.${state}`) }} · {{ items.length }}
    </h2>
    <div ref="list" class="min-h-18 flex-1 space-y-2" :data-work-state="state">
      <article v-for="item in items" :key="item.id" :data-work-card="item.id" class="border border-gray-200 rounded bg-white text-sm hover:border-primary">
        <button type="button" class="board-card-main w-full p-2 text-left" :class="{ 'cursor-grab': enabled }" @click="emit('open', item.id)">
          <small>{{ t(`page.projectWork.kinds.${item.kind}`) }}</small>
          <strong class="my-1 block break-words">{{ item.title }}</strong>
          <span class="text-gray-500">{{ owner(item) }}</span>
          <time v-if="item.planned_end" class="mt-1 block text-xs">{{ item.planned_end }}</time>
        </button>
        <select
          v-if="enabled"
          class="min-h-9 w-full cursor-pointer border-0 border-t border-gray-100 bg-white px-2 text-xs text-primary"
          :aria-label="t('page.projectWork.moveItem', { title: item.title })"
          @change="selectState(item.id, $event)"
        >
          <option disabled selected value="">
            {{ t("page.projectWork.moveTo") }}
          </option>
          <option v-for="target in targets" :key="target.key" :value="target.key">
            {{ target.label }}
          </option>
        </select>
      </article>
    </div>
  </section>
</template>

<style scoped>
.work-card-ghost { opacity: .4; outline: 2px dashed var(--primary-color, #2563eb); }
</style>
