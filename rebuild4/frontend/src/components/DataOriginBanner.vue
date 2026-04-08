<script setup lang="ts">
defineProps<{
  origin?: string
  profileRunId?: string
  snapshotLabel?: string
  snapshotCount?: number
}>()
</script>
<template>
  <div v-if="origin === 'synthetic'" class="origin-banner amber">
    <span class="banner-icon">&#9888;</span> 当前数据来源为 synthetic，仅供辅助验证参考
  </div>
  <div v-else-if="origin === 'fallback'" class="origin-banner rose">
    <span class="banner-icon">&#9888;</span> 当前数据来源为 fallback，无可用数据
  </div>
  <div v-if="profileRunId" class="origin-banner streaming">
    <span class="banner-icon">&#9881;</span>
    Streaming Run <code>{{ profileRunId }}</code>
    <span v-if="snapshotLabel"> &mdash; 当前帧: {{ snapshotLabel }}</span>
    <span v-if="snapshotCount"> (共 {{ snapshotCount }} 帧)</span>
  </div>
</template>
<style scoped>
.origin-banner { padding: 10px 16px; border-radius: var(--radius-md); font-size: 13px; font-weight: 500; margin-bottom: 12px; }
.origin-banner.amber { background: var(--amber-50); color: var(--amber-600); border: 1px solid var(--amber-500); }
.origin-banner.rose { background: var(--red-50); color: var(--red-600); border: 1px solid var(--red-500); }
.origin-banner.streaming { background: #eff6ff; color: #1d4ed8; border: 1px solid #93c5fd; }
.banner-icon { margin-right: 6px; }
code { font-family: var(--font-mono, monospace); font-size: 12px; background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; }
</style>
