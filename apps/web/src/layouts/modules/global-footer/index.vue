<template>
  <div class="platform-footer container mx-auto" :class="{ 'platform-footer--legal': legalOnly }" :style="containerStyle">
    <global-logo v-if="!legalOnly" class="platform-footer__brand" aria-label="Airalogy" />
    <footer-link
      v-if="!legalOnly && showLink" class="platform-footer__partners"
      :title="$t('common.footer.partners')" :list="partners"
    />
    <div class="platform-footer__legal">
      <span>© {{ currYear }} {{ $t("common.footer.copyright") }}</span>
      <china-compliance-footer />
    </div>
    <div class="platform-footer__version">
      <platform-version />
    </div>
    <div v-if="showIcon" class="platform-footer__social">
      <footer-icon v-for="item in sns" :key="item.name" :name="item.name" :to="item.to" />
    </div>
  </div>
</template>

<script setup lang="ts">
import IconAiraXiv from "@/assets/link-icon/airaxiv.svg"
import ChinaComplianceFooter from "@/components/common/china-compliance-footer.vue"
import PlatformVersion from "@/components/common/platform-version.vue"
import { $t } from "@/locales"

defineOptions({ name: "GlobalFooter" })

const props = withDefaults(defineProps<{
  showLink?: boolean
  showIcon?: boolean
  legalOnly?: boolean
  maxWidth?: number
}>(), { showLink: true })

const containerStyle = computed(() => props.maxWidth ? { maxWidth: `${props.maxWidth}px` } : undefined)
const currYear = new Date().getFullYear()
const partners = [{ name: "AiraXiv", to: "https://airaxiv.com", external: true, icon: IconAiraXiv }]
const sns = [
  { name: "facebook", to: "https://facebook.com" },
  { name: "github", to: "https://github.com" },
  { name: "wechat", to: "https://wechat.com" },
  { name: "twitter", to: "https://twitter.com" },
] as const
</script>

<style scoped>
.platform-footer {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  grid-template-areas: "brand partners legal version";
  align-items: center;
  gap: 0.25rem 1.5rem;
  padding: 0.625rem 1rem;
  background: var(--aira-shell-surface);
  color: #475b72;
  font-size: 0.8125rem;
  line-height: 1.5;
}
.platform-footer__brand { grid-area: brand; justify-self: start; display: inline-flex; align-items: center; min-height: 2.75rem; padding: 0; color: #183453; }
.platform-footer__brand :deep(svg) { width: 92px; height: 25px; }
.platform-footer__partners { grid-area: partners; }
.platform-footer__legal { grid-area: legal; display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 0 0.875rem; min-width: 0; overflow-wrap: anywhere; }
.platform-footer__version { grid-area: version; justify-self: end; min-width: 0; }
.platform-footer__version :deep(button) { min-height: 2.75rem; font: inherit; }
.platform-footer__social { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 0.25rem; }
.platform-footer :deep(:focus-visible) { outline: 2px solid #165bb7; outline-offset: 2px; }
.platform-footer :deep(a:hover), .platform-footer__version :deep(button:enabled:hover) { color: #165bb7; }
@media (max-width: 63.99rem) {
  .platform-footer { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "brand partners" "legal version"; gap: 0 1rem; }
  .platform-footer__partners { justify-self: end; }
  .platform-footer__legal { justify-content: flex-start; }
}
@media (max-width: 39.99rem) {
  .platform-footer { grid-template-areas: "brand partners" "legal legal" "version version"; padding: 0.375rem 1rem; }
  .platform-footer__version { justify-self: start; }
  .platform-footer__version :deep(button) { padding-inline: 0; }
}
.platform-footer--legal {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0 1rem;
}
.platform-footer--legal .platform-footer__legal { justify-content: center; text-align: center; }
</style>
