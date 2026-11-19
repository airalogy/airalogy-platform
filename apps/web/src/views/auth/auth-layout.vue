<template>
  <n-layout has-sider class="user-layout">
    <n-layout-sider
      content-class="page__hero !overflow-hidden"
      :scrollbar-props="{ scrollable: false, style: { 'overflow-y': 'hidden' } }"
      :width="siderWidth"
      :show="showSider"
    >
      <span class="hero__title">
        {{ heroTitle }}
      </span>
    </n-layout-sider>
    <n-layout content-class="form__container">
      <div class="mb-4 max-w-620px w-full flex shrink-0 justify-end">
        <div role="group" :aria-label="$t('icon.lang')" class="inline-flex overflow-hidden border border-gray-200 rounded-lg bg-white" data-testid="auth-language-switch">
          <button
            v-for="option in appStore.localeOptions"
            :key="option.key"
            type="button"
            class="min-h-10 px-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-inset"
            :class="appStore.locale === option.key ? 'bg-primary text-white' : 'bg-white text-gray-700 hover:bg-gray-100'"
            :aria-pressed="appStore.locale === option.key"
            :lang="option.key"
            @click="appStore.changeLocale(option.key)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <router-view />
      <footer class="auth-footer">
        <global-footer legal-only />
      </footer>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import GlobalFooter from "@/layouts/modules/global-footer/index.vue"
import { $t } from "@/locales"
import { useAppStore } from "@/store/modules/app"
import { useWindowSize } from "@vueuse/core"

const appStore = useAppStore()
const { width } = useWindowSize()

const heroTitle = computed(() => $t("page.auth.heroTitle"))

const showSider = computed(() => width.value >= 1024)
const siderWidth = computed(() => {
  if (width.value >= 1440)
    return 606
  if (width.value >= 1024)
    return width.value * 0.4
  return 0
})
</script>

<style scoped lang="sass">
.auth-footer
  width: 100%
  max-width: 620px
  margin-top: 1rem
  overflow: hidden
  border: 1px solid var(--aira-shell-border)
  border-radius: 0.5rem

.user-layout
  min-height: 100vh

:deep(.page__hero)
  min-height: 100vh
  height: 100%
  position: relative
  background-color: #005CE2
  background-image: url("/images/user_form_hero.png"), url("/images/user_form_hero_gear.png")
  background-position: center center, 220% -20%
  background-size: contain, 80%
  background-repeat: no-repeat
  overflow: hidden

  @media (max-width: 1024px)
    display: none

.hero__title
  position: absolute
  width: 100%
  bottom: calc(50% - 300px)
  text-align: left
  padding: 0 40px
  color: white
  font-size: 18px
  word-spacing: .3em

  @media (max-width: 1200px)
    font-size: 16px
    padding: 0 24px

:deep(.form__container)
  display: flex
  height: 100%
  flex-direction: column
  justify-content: center
  align-items: center
  padding: 20px

  @media (max-width: 1024px)
    min-height: 100vh
    background-color: #005CE2
    background-image: url("/images/user_form_hero.png"), url("/images/user_form_hero_gear.png")
    background-position: top center, 220% -20%
    background-size: contain, 80%
    background-repeat: no-repeat

@media screen and (max-height: 500px)
  .hero__title
    bottom: 50px
</style>
