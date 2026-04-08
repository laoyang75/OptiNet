<script setup lang="ts">
defineProps<{ state?: string }>()
const colors: Record<string, string> = {
  waiting: 'amber', observing: 'amber', active: 'green', dormant: 'gray', retired: 'gray', rejected: 'red',
}
const labelMap: Record<string, string> = {
  waiting: '等待中', observing: '观察中', active: '活跃', dormant: '休眠', retired: '退役', rejected: '拒绝',
}
</script>
<template>
  <span v-if="state" class="lifecycle-badge" :class="colors[state] || 'gray'">
    <span class="dot"></span>{{ labelMap[state] || state }}
  </span>
</template>
<style scoped>
.lifecycle-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.dot { width: 6px; height: 6px; border-radius: 50%; }
.amber { background: var(--amber-50); color: var(--amber-600); }
.amber .dot { background: var(--amber-500); }
.green { background: var(--green-50); color: var(--green-600); }
.green .dot { background: var(--green-500); }
.gray { background: var(--gray-100); color: var(--gray-500); }
.gray .dot { background: var(--gray-400); }
.red { background: var(--red-50); color: var(--red-600); }
.red .dot { background: var(--red-500); }
</style>
