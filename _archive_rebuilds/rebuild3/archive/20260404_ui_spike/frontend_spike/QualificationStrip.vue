<template>
  <div class="qualification-strip" :class="{ 'qualification-strip--compact': compact }">
    <BadgePill :tone="anchorable ? 'green' : 'slate'" :label="anchorable ? '可锚定' : '锚点禁用'" />
    <BadgePill :tone="baselineEligible ? 'blue' : 'slate'" :label="baselineEligible ? '基线合格' : '基线禁用'" />
  </div>
</template>

<script setup lang="ts">
import BadgePill from './BadgePill.vue';

defineProps<{
  anchorable: boolean;
  baselineEligible: boolean;
  compact?: boolean;
}>();
</script>

<style scoped>
.qualification-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0.42rem;
}

.qualification-strip--compact :deep(.badge-pill) {
  min-height: 24px;
  padding: 0 0.64rem;
  font-size: 0.7rem;
}
</style>
