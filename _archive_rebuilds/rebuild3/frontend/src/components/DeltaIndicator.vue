<template>
  <div class="delta-indicator">
    <span class="delta-current">{{ formattedCurrent }}</span>
    <span class="delta-batch" :class="batchColorClass">
      <span class="delta-label">本批</span>{{ batchPrefix }}{{ formattedBatch }}
    </span>
    <span class="delta-vs" :class="vsColorClass">
      <span class="delta-label">较上批</span>{{ vsPrefix }}{{ formattedVs }}{{ vsArrow }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  current: number;
  batch: number;
  vs: number;
  inverse?: boolean;
}>();

function fmt(n: number): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

const formattedCurrent = computed(() => fmt(props.current));
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
