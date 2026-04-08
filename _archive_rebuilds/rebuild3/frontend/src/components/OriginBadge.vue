<template>
  <span v-if="visible" class="origin-chip" :class="chipClass">{{ resolvedLabel }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  origin?: string;
  label?: string;
}>();

const visible = computed(() => Boolean(props.origin) && props.origin !== 'real');
const chipClass = computed(() => {
  if (props.origin === 'fallback') return 'origin-chip--fallback';
  return 'origin-chip--synthetic';
});
const resolvedLabel = computed(() => {
  if (props.label) return props.label;
  return props.origin === 'fallback' ? 'Fallback' : '合成数据';
});
</script>

<style scoped>
.origin-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.origin-chip--synthetic {
  background: #fef3c7;
  color: #92400e;
}

.origin-chip--fallback {
  background: #fee2e2;
  color: #991b1b;
}
</style>
