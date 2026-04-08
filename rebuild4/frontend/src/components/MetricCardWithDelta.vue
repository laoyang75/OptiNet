<script setup lang="ts">
defineProps<{ label: string; value: number | string; delta?: number; deltaLabel?: string }>()
function fmt(n: number | string) { return typeof n === 'number' ? n.toLocaleString() : n }
function deltaClass(d?: number) { return !d ? 'delta-flat' : d > 0 ? 'delta-up' : 'delta-down' }
function deltaSign(d?: number) { return !d ? '' : d > 0 ? '+' : '' }
</script>
<template>
  <div class="metric-card">
    <div class="metric-value">{{ fmt(value) }}</div>
    <div class="metric-label">{{ label }}</div>
    <div v-if="delta !== undefined" class="metric-delta" :class="deltaClass(delta)">
      {{ deltaSign(delta) }}{{ delta?.toLocaleString() }} {{ deltaLabel || '' }}
    </div>
  </div>
</template>
