<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSystemStatus } from '../lib/api'

const status = ref<any>(null)

async function load() {
  try { status.value = await getSystemStatus() } catch { status.value = null }
}
onMounted(load)
</script>
<template>
  <div v-if="status?.status === 'processing'" class="global-status-bar processing">
    <span class="pulse-dot"></span> 正在处理批次...
  </div>
  <div v-else-if="status?.mode === 'rerun'" class="global-status-bar rerun">
    重跑中
  </div>
  <div v-else-if="status?.mode === 'validation'" class="global-status-bar validation">
    验收模式 ({{ status.gate }})
  </div>
</template>
<style scoped>
.global-status-bar { padding: 6px 24px; font-size: 12px; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.processing { background: var(--blue-50); color: var(--blue-600); }
.rerun { background: var(--purple-50); color: var(--purple-600); }
.validation { background: var(--gray-100); color: var(--gray-600); }
.pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--blue-600); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
