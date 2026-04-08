<template>
  <div v-if="visible" class="global-status-bar" :class="barClass">
    <span class="status-dot" :class="dotClass"></span>
    <span>{{ statusText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  runtime: {
    current: any;
    loading: boolean;
    error: string;
  };
}>();

const visible = computed(() => {
  const c = props.runtime.current;
  if (!c) return false;
  const status = c.service_status || c.status || '';
  return status === 'processing' || status === 'rerun' || status === 'validation';
});

const barClass = computed(() => {
  const c = props.runtime.current;
  if (!c) return '';
  const status = c.service_status || c.status || '';
  if (status === 'processing') return 'global-status-bar--processing';
  if (status === 'rerun') return 'global-status-bar--rerun';
  if (status === 'validation') return 'global-status-bar--validation';
  return 'global-status-bar--idle';
});

const dotClass = computed(() => {
  const c = props.runtime.current;
  if (!c) return '';
  const status = c.service_status || c.status || '';
  if (status === 'processing') return 'status-dot--processing';
  if (status === 'rerun') return 'status-dot--rerun';
  if (status === 'validation') return 'status-dot--validation';
  return '';
});

const statusText = computed(() => {
  const c = props.runtime.current;
  if (!c) return '';
  const status = c.service_status || c.status || '';
  const batchId = c.batch_id || '';
  if (status === 'processing') return `批次处理中 ${batchId}`;
  if (status === 'rerun') return `重跑中 ${batchId}`;
  if (status === 'validation') return '验证模式';
  return '';
});
</script>
