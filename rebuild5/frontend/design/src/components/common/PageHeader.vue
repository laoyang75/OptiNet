<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="page-header">
    <h1 class="page-title">{{ title }}</h1>
    <p v-if="description" class="page-desc text-secondary">{{ description }}</p>
    <slot />
  </div>
</template>

<style scoped>
.page-header { margin-bottom: var(--sp-xl); }
.page-title { font-size: 18px; font-weight: 700; line-height: 1.3; color: var(--c-text); margin: 0; }
.page-desc { font-size: 13px; margin-top: var(--sp-xs); }
</style>
