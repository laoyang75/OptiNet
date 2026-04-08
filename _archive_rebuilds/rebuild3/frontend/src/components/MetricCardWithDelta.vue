<template>
  <div class="metric-card">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value">{{ formattedValue }}</div>
    <div class="metric-delta-row">
      <div class="metric-delta-item">
        <span class="metric-delta-label">本批</span>
        <span :class="batchColorClass">{{ batchPrefix }}{{ formattedBatch }}</span>
      </div>
      <div class="metric-delta-item">
        <span class="metric-delta-label">较上批</span>
        <span :class="vsColorClass">{{ vsPrefix }}{{ formattedVs }}{{ vsArrow }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  label: string;
  value: number;
  batch: number;
  vs: number;
  inverse?: boolean;
}>();

function fmt(n: number): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

const formattedValue = computed(() => fmt(props.value));
const formattedBatch = computed(() => fmt(Math.abs(props.batch)));
const formattedVs = computed(() => fmt(Math.abs(props.vs)));

const batchPrefix = computed(() => props.batch > 0 ? '+' : props.batch < 0 ? '-' : '');
const vsPrefix = computed(() => props.vs > 0 ? '+' : props.vs < 0 ? '-' : '');
const vsArrow = computed(() => props.vs > 0 ? ' ↑' : props.vs < 0 ? ' ↓' : '');

function colorClass(val: number, inverse?: boolean): string {
  if (val === 0) return 'delta-gray';
  const positive = val > 0;
  if (inverse) return positive ? 'delta-red' : 'delta-green';
  return positive ? 'delta-green' : 'delta-red';
}

const batchColorClass = computed(() => colorClass(props.batch, props.inverse));
const vsColorClass = computed(() => colorClass(props.vs, props.inverse));
</script>
