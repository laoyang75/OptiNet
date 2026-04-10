<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pageSize: number
  totalCount: number
  totalPages: number
}>()

const emit = defineEmits<{
  (e: 'update:page', page: number): void
}>()

const pages = computed(() => {
  const total = props.totalPages
  const current = props.page
  const result: (number | '...')[] = []
  if (total <= 7) {
    for (let i = 1; i <= total; i++) result.push(i)
  } else {
    result.push(1)
    if (current > 3) result.push('...')
    const start = Math.max(2, current - 1)
    const end = Math.min(total - 1, current + 1)
    for (let i = start; i <= end; i++) result.push(i)
    if (current < total - 2) result.push('...')
    result.push(total)
  }
  return result
})

function go(p: number) {
  if (p >= 1 && p <= props.totalPages && p !== props.page) {
    emit('update:page', p)
  }
}
</script>

<template>
  <div v-if="totalPages > 1" class="pagination">
    <span class="page-info">共 {{ totalCount }} 条</span>
    <button class="page-btn" :disabled="page <= 1" @click="go(page - 1)">‹</button>
    <template v-for="p in pages" :key="p">
      <span v-if="p === '...'" class="page-ellipsis">…</span>
      <button v-else class="page-btn" :class="{ active: p === page }" @click="go(p as number)">{{ p }}</button>
    </template>
    <button class="page-btn" :disabled="page >= totalPages" @click="go(page + 1)">›</button>
  </div>
</template>

<style scoped>
.pagination {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: var(--sp-lg);
  font-size: 12px;
}
.page-info {
  color: var(--c-text-muted);
  margin-right: var(--sp-sm);
}
.page-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-surface);
  color: var(--c-text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.1s;
}
.page-btn:hover:not(:disabled) { background: var(--c-bg); color: var(--c-text); }
.page-btn.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.page-btn:disabled { opacity: 0.4; cursor: default; }
.page-ellipsis { color: var(--c-text-muted); padding: 0 2px; }
</style>
