<template>
  <n-button
    class="footer__icon h-11 w-11 p-1"
    :aria-label="props.name"
    tertiary
    @click="handleOpenTab"
  >
    <template #icon>
      <n-icon :size="20" color="currentColor">
        <logo-github v-if="props.name === 'github'" />
        <logo-facebook v-else-if="props.name === 'facebook'" />
        <logo-wechat v-else-if="props.name === 'wechat'" />
        <logo-twitter v-else-if="props.name === 'twitter'" />
        <global-logo v-else />
      </n-icon>
    </template>
  </n-button>
</template>

<script setup lang="ts">
import LogoFacebook from "~icons/ion/logo-facebook"

import LogoGithub from "~icons/ion/logo-github"
import LogoTwitter from "~icons/ion/logo-twitter"
import LogoWechat from "~icons/ion/logo-wechat"

interface IProps {
  name: "github" | "facebook" | "wechat" | "twitter" | "default"
  to: string
  external?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  name: "default",
  to: "/",
  external: true,
})
function handleOpenTab() {
  globalThis.open(props.to, "_blank", "noreferrer")
}
</script>

<style scoped lang="sass">
.footer__icon
  padding: 5px
  border-radius: 9px
  color: #354962
</style>
