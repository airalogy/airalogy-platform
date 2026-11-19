<template>
  <n-split
    v-model:size="splitSize" v-bind="splitProps"
    :class="{ 'record-compact-layout': compact }"
    :data-testid="compact ? 'record-compact-layout' : undefined"
  >
    <template #1>
      <component :is="props.wrapper" v-if="!compact && props.wrapper">
        <slot name="prefix" />
        <n-tabs
          v-model:value="selectedTab" placement="left" type="card"
          :theme-overrides="props.themeOverrides"
          tab-class="bg-white" class="h-full w-full" pane-class="!h-full overflow-y-auto"
        >
          <template #prefix>
            <n-button quaternary class="mb-2.5" @click="handleToggle">
              <template #icon>
                <n-icon size="24">
                  <icon-local-menu-collapsed v-if="isCollapsed" />
                  <icon-local-menu-expand v-else />
                </n-icon>
              </template>
            </n-button>
          </template>
          <slot name="tabs" />
        </n-tabs>
      </component>
      <n-tabs
        v-else-if="!compact"
        v-model:value="selectedTab" placement="left" type="card"
        :theme-overrides="props.themeOverrides"
        tab-class="bg-white" class="h-full w-full" pane-class="!h-full overflow-y-auto"
      >
        <template #prefix>
          <n-button quaternary class="mb-2.5" @click="handleToggle">
            <template #icon>
              <n-icon size="24">
                <icon-local-menu-collapsed v-if="isCollapsed" />
                <icon-local-menu-expand v-else />
              </n-icon>
            </template>
          </n-button>
        </template>
        <slot name="tabs" />
      </n-tabs>
    </template>
    <template #2>
      <div v-if="compact" class="mb-3 flex flex-wrap gap-2">
        <n-button data-testid="record-open-fields" @click="isCollapsed = false">
          <template #icon>
            <n-icon><icon-local-menu-expand /></n-icon>
          </template>
          {{ $t('common.fields') }}
        </n-button>
      </div>
      <div
        class="min-w-0 w-full" :class="[props.contentClass, { 'h-full overflow-y-auto': !compact }]"
        data-testid="record-main-content"
      >
        <slot name="content" />
        <n-back-top v-if="!compact && showBackTop" />
      </div>
      <n-drawer v-if="compact" :show="!isCollapsed" display-directive="show" width="calc(100vw - 2rem)" placement="left" @update:show="value => isCollapsed = !value">
        <n-drawer-content :title="$t('common.fields')" closable :native-scrollbar="false" body-content-class="record-fields-drawer" data-testid="record-fields-drawer">
          <slot name="prefix" />
          <n-tabs v-model:value="selectedTab" type="card" :theme-overrides="props.themeOverrides" pane-class="min-w-0">
            <slot name="tabs" />
          </n-tabs>
        </n-drawer-content>
      </n-drawer>
    </template>
    <template #resize-trigger>
      <div v-if="!isCollapsed" class="n-split__resize-trigger h-full w-full" />
    </template>
  </n-split>
</template>

<script setup lang="ts">
import type { Component } from "vue"
import { useMediaQuery } from "@vueuse/core"

defineOptions({ name: "AddRecordLayout" })

const props = withDefaults(defineProps<IProps>(), {
  defaultSpiltSize: 0.35,
  collapsed: false,
  domMounted: false,
  themeOverrides: () => ({
    panePaddingMedium: "0 0 0 0",
    barColor: "transparent",
    tabGapMediumCardVertical: "10px",
    tabColor: "#fff",
    tabPaddingVerticalMediumCard: "0",
    tabBorderColor: "transparent",
  }),
  showBackTop: true,
  selectedTab: undefined,
  contentClass: "",
  responsive: false,
})

const emit = defineEmits<{
  (e: "update:splitSize", payload: string | number): void
  (e: "update:collapsed", payload: boolean): void
  (e: "update:selectedTab", payload: string | undefined): void
}>()

interface IProps {
  defaultSpiltSize?: number
  collapsed?: boolean
  domMounted?: boolean
  themeOverrides?: Record<string, any>
  showBackTop?: boolean
  selectedTab?: string
  wrapper?: Component
  contentClass?: string
  responsive?: boolean
}

const isCollapsed = useVModel(props, "collapsed")
const selectedTab = useVModel(props, "selectedTab")
const splitSize = ref(props.defaultSpiltSize)
const narrow = useMediaQuery("(max-width: 767px)")
const compact = computed(() => props.responsive && narrow.value)
watch(compact, (value) => {
  if (value)
    isCollapsed.value = true
}, { immediate: true })

watch(
  splitSize,
  (val) => {
    if (isCollapsed.value && val > 0) {
      isCollapsed.value = false
    }
    emit("update:splitSize", val)
  },
)

watch(isCollapsed, (val) => {
  if (val) {
    splitSize.value = 0
  }
  else {
    splitSize.value = props.defaultSpiltSize
  }
})

const splitProps = computed(() => {
  if (isCollapsed.value) {
    return { min: 0, max: 1, defaultSize: 0 }
  }

  return { min: 0.35, max: 0.65, defaultSize: props.defaultSpiltSize }
})

function handleToggle() {
  if (isCollapsed.value) {
    handleExpand()
  }
  else {
    handleCollapse()
  }
}

function handleExpand() {
  splitSize.value = props.defaultSpiltSize
  isCollapsed.value = false
}

function handleCollapse() {
  splitSize.value = 0
  isCollapsed.value = true
}

defineExpose({
  toggle: () => {
    if (isCollapsed.value) {
      splitSize.value = props.defaultSpiltSize
    }
    else {
      splitSize.value = 0
    }
    isCollapsed.value = !isCollapsed.value
  },
})
</script>

<style scoped lang="sass">
.record-compact-layout
  display: block
  min-width: 0
  width: 100%
  height: auto

  :deep(.n-split-pane-1), :deep(.n-split__resize-trigger-wrapper)
    display: none

  :deep(.n-split-pane-2)
    height: auto
    overflow: visible

:global(.record-fields-drawer)
  min-width: 0
  overflow-wrap: anywhere

:deep(.n-tabs-nav-scroll-wrapper)
  &:before,&:after
    display: none

:deep(.n-tabs-nav--segment-type)
  position: relative
  margin: 20px 24px

:deep(.n-tabs-tab--active)
  --n-tab-text-color-hover: var(--n-tab-text-color-active)

:deep(.n-tabs-rail)
  padding: 0

:deep(.n-split-pane-1)
  min-width: 60px
</style>
