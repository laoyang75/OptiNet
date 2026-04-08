<template>
  <span class="badge" :class="badgeClass">
    <span v-if="state === 'dormant'" class="dot-hollow"></span>
    <span v-else-if="state !== 'retired'" class="dot"></span>
    {{ label }}
    <span v-if="state === 'observing' && progress != null" class="mini-progress">
      <span class="mini-progress-fill" :style="{ width: `${Math.min(progress, 100)}%` }"></span>
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  state: string;
  progress?: number;
}>();

const LABEL_MAP: Record<string, string> = {
  waiting: '等待',
  observing: '观察',
  active: '活跃',
  dormant: '休眠',
  retired: '退役',
  rejected: '拒收',
};

const label = computed(() => LABEL_MAP[props.state] || props.state);

const badgeClass = computed(() => {
  const map: Record<string, string> = {
    waiting: 'badge-waiting',
    observing: 'badge-observing',
    active: 'badge-active',
    dormant: 'badge-dormant',
    retired: 'badge-retired',
    rejected: 'badge-rejected',
  };
  return map[props.state] || 'badge-waiting';
});
</script>
