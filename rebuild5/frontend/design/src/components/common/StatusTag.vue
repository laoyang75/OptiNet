<script setup lang="ts">
import { computed } from 'vue'
import { STATE_COLORS, STATE_LABELS, type LifecycleState } from '../../types'

const props = defineProps<{ state: LifecycleState; size?: 'sm' | 'md' }>()

const color = computed(() => STATE_COLORS[props.state])
const label = computed(() => STATE_LABELS[props.state])
</script>

<template>
  <span
    class="status-tag"
    :class="[`status-${state}`, size || 'md']"
    :style="{ '--tag-color': color }"
  >
    <span class="dot"></span>
    {{ label }}
  </span>
</template>

<style scoped>
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
  border-radius: 10px;
  background: color-mix(in srgb, var(--tag-color) 12%, transparent);
  color: var(--tag-color);
  white-space: nowrap;
}
.status-tag.md { padding: 2px 10px; font-size: 12px; }
.status-tag.sm { padding: 1px 7px; font-size: 11px; }
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--tag-color);
}
</style>
