<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'

const datasets = [
  { key: 'sample_6lac', name: '6 LAC 样本', status: 'active', sources: 3, records: '1.25M', created: '2026-04-01', lastRun: '2026-04-08' },
  { key: 'beijing_7d', name: '北京 7 日全量', status: 'standby', sources: 5, records: '12.8M', created: '2026-03-20', lastRun: '2026-03-28' },
  { key: 'test_mini', name: '测试小集', status: 'archived', sources: 1, records: '50K', created: '2026-02-15', lastRun: '2026-02-20' },
]

const statusMap: Record<string, { label: string; class: string }> = {
  active: { label: '当前使用', class: 'st-active' },
  standby: { label: '待命', class: 'st-standby' },
  archived: { label: '已归档', class: 'st-archived' },
}
</script>

<template>
  <PageHeader title="数据集选择" description="选择当前系统处理的数据集。所有治理页面将基于选中的数据集展示结果。" />

  <div class="dataset-list">
    <div v-for="ds in datasets" :key="ds.key" class="dataset-card card" :class="{ active: ds.status === 'active' }">
      <div class="flex justify-between items-center mb-md">
        <div>
          <span class="font-semibold text-lg">{{ ds.name }}</span>
          <span class="font-mono text-xs text-muted" style="margin-left:8px">{{ ds.key }}</span>
        </div>
        <span class="tag" :class="statusMap[ds.status].class">{{ statusMap[ds.status].label }}</span>
      </div>
      <div class="grid grid-4 gap-lg">
        <div class="info-item">
          <span class="text-xs text-muted">数据源</span>
          <span class="font-mono font-semibold">{{ ds.sources }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">记录数</span>
          <span class="font-mono font-semibold">{{ ds.records }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">创建时间</span>
          <span class="text-sm">{{ ds.created }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">最近运行</span>
          <span class="text-sm">{{ ds.lastRun }}</span>
        </div>
      </div>
      <div class="flex gap-sm mt-md" v-if="ds.status !== 'active'">
        <button class="btn btn-primary">切换到此数据集</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dataset-list { display: flex; flex-direction: column; gap: var(--sp-lg); }
.dataset-card.active { border-color: var(--c-primary); box-shadow: 0 0 0 1px var(--c-primary), var(--shadow-sm); }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.st-active { background: #dcfce7; color: #166534; }
.st-standby { background: #dbeafe; color: #1e40af; }
.st-archived { background: #f3f4f6; color: #6b7280; }
</style>
