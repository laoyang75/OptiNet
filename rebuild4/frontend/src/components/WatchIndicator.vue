<script setup lang="ts">
defineProps<{ watch?: boolean }>()
</script>
<template>
  <span v-if="watch" class="watch-indicator">WATCH</span>
</template>
<style scoped>
.watch-indicator { display: inline-block; padding: 1px 6px; border-radius: var(--radius-sm); font-size: 10px; font-weight: 700; background: var(--orange-50); color: var(--orange-600); border: 1px solid var(--orange-500); letter-spacing: 0.5px; }
</style>
