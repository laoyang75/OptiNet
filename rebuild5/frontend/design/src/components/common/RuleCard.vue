<script setup lang="ts">
defineProps<{
  title: string
  rules: Array<{ label: string; value: string; unit?: string }>
}>()
</script>

<template>
  <div class="rule-card card">
    <div class="rule-title font-semibold text-sm mb-md">{{ title }}</div>
    <div class="rule-list">
      <div v-for="(rule, i) in rules" :key="i" class="rule-row">
        <span class="rule-label text-secondary text-xs">{{ rule.label }}</span>
        <span class="rule-value font-mono text-xs font-semibold">
          {{ rule.value }}<span v-if="rule.unit" class="text-muted"> {{ rule.unit }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-list { display: flex; flex-direction: column; gap: 6px; }
.rule-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid var(--c-border-light);
}
.rule-row:last-child { border-bottom: none; }
</style>
