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
      <div class="mt-6 h-fit w-full text-center text-gray-400 md:mt-0">
        <div class="space-x-3">
          <span>&copy; {{ currYear }}</span>
          <span>{{ footerText.copyright }}</span>
          <china-compliance-footer />
        </div>
        <div class="mt-1 text-white lg:text-gray-600">
          <platform-version />
        </div>
      </div>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import ChinaComplianceFooter from "@/components/common/china-compliance-footer.vue"
import PlatformVersion from "@/components/common/platform-version.vue"
import { $t } from "@/locales"
import { useAppStore } from "@/store/modules/app"
import { useWindowSize } from "@vueuse/core"

const appStore = useAppStore()
const currYear = new Date().getFullYear()
const { width } = useWindowSize()

const heroTitle = computed(() => $t("page.auth.heroTitle"))
const footerText = computed(() => ({
  copyright: $t("common.footer.copyright"),
}))

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
