<script setup lang="ts">
defineProps<{ layer?: string }>()
const styles: Record<string, { color: string; label: string }> = {
  fact_governed: { color: 'green', label: 'governed' },
  fact_pending_observation: { color: 'amber', label: 'pending_obs' },
  fact_pending_issue: { color: 'orange', label: 'pending_issue' },
  fact_rejected: { color: 'red', label: 'rejected' },
}
</script>
<template>
  <span v-if="layer && styles[layer]" class="fact-badge" :class="styles[layer].color">
    {{ styles[layer].label }}
  </span>
</template>
<style scoped>
.fact-badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm); font-size: 11px; font-weight: 500; border-left: 3px solid; }
.green { background: var(--green-50); color: var(--green-600); border-left-color: var(--green-500); }
.amber { background: var(--amber-50); color: var(--amber-600); border-left-color: var(--amber-500); }
.orange { background: var(--orange-50); color: var(--orange-600); border-left-color: var(--orange-500); }
.red { background: var(--red-50); color: var(--red-600); border-left-color: var(--red-500); }
</style>
