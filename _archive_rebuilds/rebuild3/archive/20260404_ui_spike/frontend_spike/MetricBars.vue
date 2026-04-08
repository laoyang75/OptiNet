<template>
  <div class="metric-bars">
    <div v-if="!items.length" class="metric-bars__empty">{{ emptyText }}</div>
    <div v-for="item in items" :key="item.label" class="metric-bars__row">
      <div class="metric-bars__meta">
        <span>{{ item.label }}</span>
        <strong>{{ item.count.toLocaleString('zh-CN') }}</strong>
      </div>
      <div class="metric-bars__track">
        <span :class="`metric-bars__fill metric-bars__fill--${tone}`" :style="{ width: `${width(item.count)}%` }"></span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    items: Array<{ label: string; count: number }>;
    tone?: 'blue' | 'green' | 'amber' | 'orange' | 'red' | 'slate';
    emptyText?: string;
  }>(),
  {
    tone: 'blue',
    emptyText: '暂无分布',
  },
);

const maxValue = computed(() => Math.max(...props.items.map((item) => item.count), 1));

function width(value: number): number {
  return Math.max(8, (value / maxValue.value) * 100);
}
</script>

<style scoped>
.metric-bars {
  display: grid;
  gap: 0.8rem;
}

.metric-bars__empty {
  border: 1px dashed var(--border-strong);
  border-radius: 18px;
  padding: 1rem;
  color: var(--text-soft);
}

.metric-bars__row {
  display: grid;
  gap: 0.36rem;
}

.metric-bars__meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  color: var(--text-soft);
  font-size: 0.9rem;
}

.metric-bars__meta strong {
  color: var(--text-strong);
}

.metric-bars__track {
  height: 0.7rem;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(83, 105, 146, 0.12);
}

.metric-bars__fill {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.metric-bars__fill--blue {
  background: linear-gradient(90deg, rgba(44, 94, 188, 0.84), rgba(78, 127, 218, 0.92));
}

.metric-bars__fill--green {
  background: linear-gradient(90deg, rgba(24, 140, 92, 0.82), rgba(49, 179, 119, 0.88));
}

.metric-bars__fill--amber {
  background: linear-gradient(90deg, rgba(197, 133, 18, 0.82), rgba(230, 172, 45, 0.9));
}

.metric-bars__fill--orange {
  background: linear-gradient(90deg, rgba(189, 100, 21, 0.82), rgba(235, 146, 63, 0.9));
}

.metric-bars__fill--red {
  background: linear-gradient(90deg, rgba(194, 66, 72, 0.82), rgba(223, 95, 101, 0.9));
}

.metric-bars__fill--slate {
  background: linear-gradient(90deg, rgba(96, 110, 133, 0.8), rgba(132, 144, 168, 0.88));
}
</style>
