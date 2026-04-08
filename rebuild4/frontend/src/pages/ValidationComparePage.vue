<script setup lang="ts">
</script>
<template>
  <div class="frozen-page">
    <div class="frozen-card">
      <div class="frozen-icon">&#10052;</div>
      <h2>验证/对照 — 当前冻结</h2>
      <p>该功能依赖旧 compare_job / compare_result 体系，已于本轮暂停。</p>
      <p>待 Streaming 模块稳定后，将基于 profile_run_id 的 snapshot diff 重建版本对比能力。</p>
    </div>
  </div>
</template>
<style scoped>
.frozen-page { display: flex; align-items: center; justify-content: center; min-height: 60vh; padding: 24px; }
.frozen-card { max-width: 480px; text-align: center; padding: 40px; border: 2px dashed var(--gray-300); border-radius: 12px; background: var(--gray-50); }
.frozen-icon { font-size: 48px; margin-bottom: 12px; }
h2 { font-size: 18px; font-weight: 700; color: var(--gray-700); margin: 0 0 12px; }
p { font-size: 13px; color: var(--gray-500); margin: 0 0 8px; line-height: 1.5; }
</style>
