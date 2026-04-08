<template>
  <div v-if="origin === 'fallback'" class="origin-banner origin-banner--fallback">
    {{ subjectNote || '当前为 fallback 数据，不代表实时结果。' }}
  </div>
  <div v-else-if="origin === 'synthetic' && showSynthetic" class="origin-banner origin-banner--synthetic">
    <OriginBadge origin="synthetic" />
    <span>{{ subjectNote || '当前内容含合成数据，仅供诊断参考。' }}</span>
  </div>
</template>

<script setup lang="ts">
import OriginBadge from './OriginBadge.vue';

defineProps<{
  origin?: string;
  subjectNote?: string;
  showSynthetic?: boolean;
}>();
</script>

<style scoped>
.origin-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid transparent;
  font-size: 13px;
}

.origin-banner--fallback {
  background: #fff1f2;
  border-color: #fecdd3;
  color: #9f1239;
  box-shadow: 0 8px 24px rgba(159, 18, 57, 0.08);
}

.origin-banner--synthetic {
  background: #fffbeb;
  border-color: #fcd34d;
  color: #92400e;
}
</style>
