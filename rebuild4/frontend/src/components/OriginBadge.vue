<script setup lang="ts">
defineProps<{ origin?: string }>()
</script>
<template>
  <span v-if="origin && origin !== 'real'" class="origin-badge" :class="origin">{{ origin }}</span>
</template>
<style scoped>
.origin-badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.origin-badge.synthetic { background: var(--amber-50); color: var(--amber-600); }
.origin-badge.fallback { background: var(--red-50); color: var(--red-600); }
</style>
