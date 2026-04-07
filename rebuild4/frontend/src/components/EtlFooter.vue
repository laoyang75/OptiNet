<script setup lang="ts">
defineProps<{
  codePath?: string
  docPath?: string
}>()
</script>

<template>
  <div class="etl-footer">
    <div v-if="codePath" class="footer-item">
      <span class="footer-label">代码位置</span>
      <code class="footer-path">{{ codePath }}</code>
    </div>
    <div v-if="docPath" class="footer-item">
      <span class="footer-label">说明文档</span>
      <code class="footer-path">{{ docPath }}</code>
    </div>
  </div>
</template>

<style scoped>
.etl-footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border); }
.footer-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.footer-label { font-size: 11px; font-weight: 600; color: var(--text); min-width: 60px; }
.footer-path { font-size: 11px; color: var(--text); background: var(--code-bg); padding: 2px 6px; border-radius: 4px; }
</style>
