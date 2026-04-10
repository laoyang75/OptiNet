<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { fetchBatches, type BatchItem } from '../../api/evaluation'

const emit = defineEmits<{ 'batch-change': [batchId: number] }>()

const batches = ref<BatchItem[]>([])
const selected = ref<number | undefined>()

onMounted(async () => {
  try {
    const payload = await fetchBatches()
    batches.value = payload.batches
    if (payload.batches.length > 0) {
      selected.value = payload.batches[0].batch_id
      emit('batch-change', payload.batches[0].batch_id)
    }
  } catch {
    batches.value = []
  }
})

watch(selected, (val) => {
  if (val != null) emit('batch-change', val)
})

const selectedBatch = () => batches.value.find(b => b.batch_id === selected.value)
</script>

<template>
  <div class="batch-selector card">
    <div class="flex items-center gap-md">
      <label class="text-xs font-semibold text-muted">批次</label>
      <select v-model="selected" class="batch-select">
        <option v-for="b in batches" :key="b.batch_id" :value="b.batch_id">
          {{ b.snapshot_version }} — {{ b.run_at }}
        </option>
      </select>
      <span v-if="selectedBatch()" class="text-xs text-secondary">
        数据集 {{ selectedBatch()!.dataset_key }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.batch-selector {
  padding: var(--sp-sm) var(--sp-lg);
  margin-bottom: var(--sp-lg);
}
.batch-select {
  padding: 4px 8px;
  font-size: 12px;
  font-family: var(--font-mono);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  background: var(--c-surface);
  min-width: 240px;
}
</style>
