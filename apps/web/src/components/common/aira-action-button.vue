<template>
  <n-button attr-type="button" secondary type="primary" size="small" class="aira-action">
    <template #icon>
      <n-icon aria-hidden="true"><icon-shared-airalogy-chat /></n-icon>
    </template>
    <slot />
  </n-button>
</template>

<style scoped>
.aira-action { flex-shrink: 0; }
@media (pointer: coarse) {
  .aira-action { min-height: 40px; }
}
@media print {
  .aira-action { display: none; }
}
</style>
