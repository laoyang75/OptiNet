<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getServiceCoverage, type ServiceCoveragePayload } from '../../api/service'
import { fmt } from '../../composables/useFormat'

const payload = ref<ServiceCoveragePayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: { trusted_cell_total: 0, lac_total: 0, avg_p90: 0 },
  operators: [],
})

const topCells = computed(() => payload.value.operators[0] ?? null)
const bestPrecision = computed(() => [...payload.value.operators].sort((a, b) => a.avg_p90 - b.avg_p90)[0] ?? null)
const bestExcellent = computed(() => [...payload.value.operators].sort((a, b) => b.excellent_pct - a.excellent_pct)[0] ?? null)

onMounted(async () => {
  try {
    payload.value = await getServiceCoverage()
  } catch {
    payload.value = { ...payload.value }
  }
})
</script>

<template>
  <PageHeader title="覆盖分析" description="区域覆盖密度、质量结构和运营商对比。面向业务用户。">
    <div class="text-xs text-secondary">
      数据集 {{ payload.version.dataset_key || '-' }} ｜ 发布 {{ payload.version.run_id || '-' }} ｜ {{ payload.version.snapshot_version_prev }} → {{ payload.version.snapshot_version }}
    </div>
  </PageHeader>

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="可信 Cell 总量" :value="fmt(payload.summary.trusted_cell_total)" subtitle="正式库当前版本" />
    <SummaryCard title="覆盖 LAC 数" :value="fmt(payload.summary.lac_total)" subtitle="当前可查询区域" />
    <SummaryCard title="平均 P90 精度" :value="Math.round(payload.summary.avg_p90) + 'm'" subtitle="全运营商加权" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">运营商覆盖对比</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>运营商</th>
          <th>可信 Cell 数</th>
          <th style="width:160px">合格+ 占比</th>
          <th style="width:160px">excellent 占比</th>
          <th>平均 P90 (m)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="operator in payload.operators" :key="operator.operator_code">
          <td class="font-semibold">{{ operator.operator_cn || operator.operator_code }}</td>
          <td class="font-mono">{{ fmt(operator.cells) }}</td>
          <td><PercentBar :value="operator.qualified_pct" /></td>
          <td><PercentBar :value="operator.excellent_pct" color="var(--c-excellent)" /></td>
          <td class="font-mono">{{ Math.round(operator.avg_p90) }}</td>
        </tr>
        <tr v-if="payload.operators.length === 0"><td colspan="5" class="empty-row">暂无覆盖分析数据</td></tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-3 gap-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-sm">规模最大</div>
      <div class="text-xl font-semibold">{{ topCells?.operator_cn || '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ topCells ? fmt(topCells.cells) + ' 个可信 Cell' : '暂无数据' }}</div>
    </div>
    <div class="card">
      <div class="font-semibold text-sm mb-sm">精度最佳</div>
      <div class="text-xl font-semibold">{{ bestPrecision?.operator_cn || '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ bestPrecision ? Math.round(bestPrecision.avg_p90) + 'm 平均 P90' : '暂无数据' }}</div>
    </div>
    <div class="card">
      <div class="font-semibold text-sm mb-sm">优秀占比最高</div>
      <div class="text-xl font-semibold">{{ bestExcellent?.operator_cn || '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ bestExcellent ? (bestExcellent.excellent_pct * 100).toFixed(1) + '%' : '暂无数据' }}</div>
    </div>
  </div>
</template>

<style scoped>
.empty-row {
  padding: 20px;
  text-align: center;
  color: var(--c-text-muted);
}
</style>
