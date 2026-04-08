<script setup lang="ts">
defineProps<{ value?: number }>()
function cls(v?: number) { return !v ? 'delta-flat' : v > 0 ? 'delta-up' : 'delta-down' }
function sign(v?: number) { return !v ? '' : v > 0 ? '+' : '' }
</script>
<template>
  <span v-if="value !== undefined" class="delta-indicator" :class="cls(value)">
    {{ sign(value) }}{{ value?.toLocaleString() }}
  </span>
</template>
<style scoped>
.delta-indicator { font-size: 12px; font-family: var(--font-mono); }
</style>
