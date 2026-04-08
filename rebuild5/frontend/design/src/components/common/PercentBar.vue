<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: number  // 0-1
  label?: string
  color?: string
  showPct?: boolean
}>()

const pct = computed(() => Math.min(100, Math.max(0, props.value * 100)))
const barColor = computed(() => {
  if (props.color) return props.color
  if (pct.value >= 90) return 'var(--c-success)'
  if (pct.value >= 60) return 'var(--c-primary)'
  if (pct.value >= 30) return 'var(--c-warning)'
  return 'var(--c-danger)'
})
</script>

<template>
  <div class="pct-bar-wrap">
    <div v-if="label" class="pct-label text-xs text-secondary">{{ label }}</div>
    <div class="pct-bar-row">
      <div class="progress-bar" style="flex:1">
        <div class="fill" :style="{ width: pct + '%', background: barColor }"></div>
      </div>
      <span v-if="showPct !== false" class="pct-val font-mono text-xs">{{ pct.toFixed(1) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.pct-bar-wrap { min-width: 0; }
.pct-label { margin-bottom: 2px; }
.pct-bar-row { display: flex; align-items: center; gap: var(--sp-sm); }
.pct-val { width: 42px; text-align: right; flex-shrink: 0; }
</style>
