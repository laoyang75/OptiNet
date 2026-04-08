<template>
  <span class="fact-badge" :class="badgeClass">
    <span class="fact-icon">{{ icon }}</span>
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  layer: string;
}>();

const CONFIG: Record<string, { label: string; icon: string; cls: string }> = {
  fact_governed:             { label: '已治理', icon: '✓', cls: 'fact-governed' },
  fact_pending_observation:  { label: '观察中', icon: '⏱', cls: 'fact-pending-obs' },
  fact_pending_issue:        { label: '待复核', icon: '⚠', cls: 'fact-pending-issue' },
  fact_rejected:             { label: '已拒收', icon: '⊘', cls: 'fact-rejected' },
};

const config = computed(() => CONFIG[props.layer] || { label: props.layer, icon: '?', cls: 'fact-governed' });
const label = computed(() => config.value.label);
const icon = computed(() => config.value.icon);
const badgeClass = computed(() => config.value.cls);
</script>
