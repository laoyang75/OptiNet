<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import { getSystemConfig, prepareCurrentDataset, type CurrentVersion, type DatasetItem, type DatasetMode } from '../../api/system'
import { fmtCompact } from '../../composables/useFormat'

const datasets = ref<DatasetItem[]>([])
const currentVersion = ref<CurrentVersion | null>(null)
const datasetMode = ref<DatasetMode | null>(null)
const loading = ref(false)
const preparing = ref(false)
const prepMessage = ref('')

const statusMap: Record<string, { label: string; class: string }> = {
  active: { label: '当前使用', class: 'st-active' },
  standby: { label: '待命', class: 'st-standby' },
  archived: { label: '已归档', class: 'st-archived' },
}

const viewDatasets = computed(() => datasets.value.map((dataset) => {
  const viewStatus = dataset.is_current ? 'active' : dataset.status === 'ready' ? 'standby' : 'archived'
  return {
    ...dataset,
    viewStatus,
  }
}))

async function loadConfig() {
  loading.value = true
  try {
    const payload = await getSystemConfig()
    currentVersion.value = payload.current_version
    datasetMode.value = payload.dataset_mode
    datasets.value = payload.datasets
  } finally {
    loading.value = false
  }
}

async function prepareCurrent() {
  preparing.value = true
  prepMessage.value = ''
  try {
    const result = await prepareCurrentDataset()
    prepMessage.value = `已按配置重建 ${result.dataset_key}：raw_lac ${fmtCompact(result.raw_lac_count)} / raw_gps ${fmtCompact(result.raw_gps_count)}`
    await loadConfig()
  } catch (error) {
    prepMessage.value = error instanceof Error ? error.message : '重建失败'
  } finally {
    preparing.value = false
  }
}

onMounted(() => {
  void loadConfig()
})
</script>

<template>
  <PageHeader title="当前数据集" description="当前版本仅支持单活数据集运行。页面展示元数据和当前上下文，不支持在线切换。" />

  <div class="flex justify-between items-center mb-lg">
    <div class="text-xs text-secondary">
      <span v-if="loading">正在加载数据集信息…</span>
      <span v-else>共 {{ viewDatasets.length }} 个数据集元数据；当前仅使用 `config/dataset.yaml` 指定的单活数据集。</span>
    </div>
    <button class="btn btn-primary" :disabled="preparing" @click="prepareCurrent">
      {{ preparing ? '正在重建…' : `重建当前数据集${currentVersion ? `（${currentVersion.dataset_key}）` : ''}` }}
    </button>
  </div>

  <div class="card mb-lg warning-card">
    <div class="font-semibold mb-xs">{{ datasetMode?.label || '单活数据集' }}</div>
    <div class="text-sm">
      {{ datasetMode?.message || '当前版本不支持在线切换数据集；如需更换数据集，请修改 config/dataset.yaml 后清理共享结果并重跑。' }}
    </div>
    <div class="text-xs text-muted mt-sm">
      未来切换方案文档：{{ datasetMode?.plan_doc || 'rebuild5/docs/dev/05_多数据集切换方案.md' }}
    </div>
  </div>

  <div v-if="prepMessage" class="card mb-lg text-sm">{{ prepMessage }}</div>

  <div class="dataset-list">
    <div v-for="ds in viewDatasets" :key="ds.dataset_key" class="dataset-card card" :class="{ active: ds.is_current }">
      <div class="flex justify-between items-center mb-md">
        <div>
          <span class="font-semibold text-lg">{{ ds.source_desc }}</span>
          <span class="font-mono text-xs text-muted" style="margin-left:8px">{{ ds.dataset_key }}</span>
        </div>
        <span class="tag" :class="statusMap[ds.viewStatus].class">{{ statusMap[ds.viewStatus].label }}</span>
      </div>
      <div class="grid grid-4 gap-lg">
        <div class="info-item">
          <span class="text-xs text-muted">记录数</span>
          <span class="font-mono font-semibold">{{ fmtCompact(ds.record_count) }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">LAC 范围</span>
          <span class="text-sm">{{ ds.lac_scope }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">导入时间</span>
          <span class="text-sm">{{ ds.imported_at || '-' }}</span>
        </div>
        <div class="info-item">
          <span class="text-xs text-muted">最近运行</span>
          <span class="text-sm">{{ ds.last_updated_at || '-' }}</span>
        </div>
      </div>
      <div class="text-xs text-muted mt-md">时间范围：{{ ds.time_range }}</div>
      <div v-if="!ds.is_current" class="text-xs text-muted mt-sm">
        当前仅保留该数据集的元数据展示；在线切换能力尚未开发。
      </div>
    </div>
  </div>
</template>

<style scoped>
.dataset-list { display: flex; flex-direction: column; gap: var(--sp-lg); }
.dataset-card.active { border-color: var(--c-primary); box-shadow: 0 0 0 1px var(--c-primary), var(--shadow-sm); }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.warning-card { border-color: #f59e0b; background: #fffbeb; }
.st-active { background: #dcfce7; color: #166534; }
.st-standby { background: #dbeafe; color: #1e40af; }
.st-archived { background: #f3f4f6; color: #6b7280; }
</style>
