<script setup lang="ts">
import { computed } from 'vue'
import { STATE_COLORS, STATE_LABELS, type LifecycleState } from '../../types'

const props = defineProps<{ data: Record<LifecycleState, number>; title?: string }>()

const total = computed(() => Object.values(props.data).reduce((a, b) => a + b, 0))
const items = computed(() => {
  const order: LifecycleState[] = ['excellent', 'qualified', 'observing', 'waiting', 'dormant', 'retired']
  return order.map(s => ({
    state: s,
    count: props.data[s] || 0,
    pct: total.value > 0 ? ((props.data[s] || 0) / total.value * 100) : 0,
    color: STATE_COLORS[s],
    label: STATE_LABELS[s],
  }))
})
</script>

<template>
  <div class="state-dist card">
    <div v-if="title" class="dist-title font-semibold mb-md">{{ title }}</div>
    <!-- 条形图 -->
    <div class="bar-row">
      <div
        v-for="item in items"
        :key="item.state"
        class="bar-segment"
        :style="{ width: item.pct + '%', background: item.color }"
        :title="`${item.label}: ${item.count}`"
      ></div>
    </div>
    <!-- 图例 -->
    <div class="legend">
      <div v-for="item in items" :key="item.state" class="legend-item">
        <span class="legend-dot" :style="{ background: item.color }"></span>
        <span class="text-secondary text-xs">{{ item.label }}</span>
        <span class="font-mono text-xs font-semibold">{{ item.count.toLocaleString() }}</span>
        <span class="text-muted text-xs">{{ item.pct.toFixed(1) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dist-title { font-size: 13px; }
.bar-row {
  display: flex;
  height: 12px;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: var(--sp-md);
}
.bar-segment {
  min-width: 2px;
  transition: width 0.3s;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-md) var(--sp-xl);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: var(--sp-xs);
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
