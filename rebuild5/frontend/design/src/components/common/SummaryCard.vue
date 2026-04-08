<script setup lang="ts">
defineProps<{
  title: string
  value: string | number
  subtitle?: string
  color?: string
  trend?: 'up' | 'down' | 'flat'
  trendValue?: string
}>()
</script>

<template>
  <div class="summary-card card">
    <div class="card-title text-secondary text-sm">{{ title }}</div>
    <div class="card-value" :style="color ? { color } : {}">{{ value }}</div>
    <div v-if="subtitle" class="card-subtitle text-xs text-muted">{{ subtitle }}</div>
    <div v-if="trendValue" class="card-trend text-xs" :class="`trend-${trend}`">
      <span v-if="trend === 'up'">↑</span>
      <span v-else-if="trend === 'down'">↓</span>
      <span v-else>→</span>
      {{ trendValue }}
    </div>
  </div>
</template>

<style scoped>
.summary-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.card-title {
  font-weight: 500;
}
.card-value {
  font-size: 24px;
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 1.2;
  letter-spacing: -0.5px;
}
.card-subtitle {
  margin-top: 2px;
}
.card-trend { margin-top: 4px; }
.trend-up { color: var(--c-success); }
.trend-down { color: var(--c-danger); }
.trend-flat { color: var(--c-text-muted); }
</style>
