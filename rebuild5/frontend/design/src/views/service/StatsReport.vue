<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getServiceReport, type ServiceReportPayload, type ServiceReportRow } from '../../api/service'
import { fmt } from '../../composables/useFormat'

type SortKey = 'cell_total' | 'qualified_cell_total' | 'bs_total' | 'avg_p90'

const payload = ref<ServiceReportPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  rows: [],
})

const sortKey = ref<SortKey>('cell_total')
const sortAsc = ref(false)

const sortedRows = computed(() => {
  const rows = [...payload.value.rows]
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  rows.sort((a, b) => (a[key] - b[key]) * dir)
  return rows
})

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = false
  }
}

function sortIndicator(key: SortKey): string {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? ' ↑' : ' ↓'
}

const totalCells = computed(() => payload.value.rows.reduce((sum, row) => sum + row.cell_total, 0))
const totalBs = computed(() => payload.value.rows.reduce((sum, row) => sum + row.bs_total, 0))
const bestP90 = computed(() => [...payload.value.rows].sort((a, b) => a.avg_p90 - b.avg_p90)[0] ?? null)
const worstP90 = computed(() => [...payload.value.rows].sort((a, b) => b.avg_p90 - a.avg_p90)[0] ?? null)
const bestQualifiedBs = computed(() => {
  return [...payload.value.rows].sort((a, b) => (b.bs_total > 0 ? b.qualified_bs_total / b.bs_total : 0) - (a.bs_total > 0 ? a.qualified_bs_total / a.bs_total : 0))[0] ?? null
})

function downloadCsv(): void {
  const header = ['operator_code', 'operator_cn', 'lac', 'cell_total', 'qualified_cell_total', 'excellent_cell_total', 'bs_total', 'qualified_bs_total', 'avg_p90']
  const lines = payload.value.rows.map((row: ServiceReportRow) => [
    row.operator_code,
    row.operator_cn || '',
    row.lac,
    row.cell_total,
    row.qualified_cell_total,
    row.excellent_cell_total,
    row.bs_total,
    row.qualified_bs_total,
    row.avg_p90,
  ].join(','))
  const csv = [header.join(','), ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `rebuild5-report-${payload.value.version.snapshot_version || 'v0'}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try {
    payload.value = await getServiceReport()
  } catch {
    payload.value = { ...payload.value }
  }
})
</script>

<template>
  <PageHeader title="统计报表" description="可复用的汇总结果和趋势报表。保留版本标识，保证报表可追溯。">
    <div class="text-xs text-secondary">
      数据集 {{ payload.version.dataset_key || '-' }} ｜ 发布 {{ payload.version.run_id || '-' }} ｜ {{ payload.version.snapshot_version_prev }} → {{ payload.version.snapshot_version }}
    </div>
  </PageHeader>

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="数据集" :value="payload.version.dataset_key || '-'" />
    <SummaryCard title="快照版本" :value="payload.version.snapshot_version" />
    <SummaryCard title="覆盖 LAC" :value="fmt(payload.rows.length)" />
    <SummaryCard title="可信 Cell" :value="fmt(totalCells)" :subtitle="fmt(totalBs) + ' 个 BS'" />
  </div>

  <div class="card mb-lg">
    <div class="flex justify-between items-center mb-md wrap-row gap-sm">
      <span class="font-semibold text-sm">按 LAC 汇总</span>
      <button class="btn" @click="downloadCsv">导出 CSV</button>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>LAC</th>
          <th>运营商</th>
          <th class="sortable-th" @click="toggleSort('cell_total')">Cell 总量{{ sortIndicator('cell_total') }}</th>
          <th>qualified+ Cell</th>
          <th>excellent Cell</th>
          <th class="sortable-th" @click="toggleSort('bs_total')">BS 总量{{ sortIndicator('bs_total') }}</th>
          <th>qualified+ BS</th>
          <th class="sortable-th" @click="toggleSort('avg_p90')">平均 P90 (m){{ sortIndicator('avg_p90') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in sortedRows" :key="`${row.operator_code}-${row.lac}`">
          <td class="font-mono font-semibold">{{ row.lac }}</td>
          <td>{{ row.operator_cn || row.operator_code }}</td>
          <td class="font-mono">{{ fmt(row.cell_total) }}</td>
          <td class="font-mono">{{ fmt(row.qualified_cell_total) }}</td>
          <td class="font-mono">{{ fmt(row.excellent_cell_total) }}</td>
          <td class="font-mono">{{ fmt(row.bs_total) }}</td>
          <td class="font-mono">{{ fmt(row.qualified_bs_total) }}</td>
          <td class="font-mono">{{ Math.round(row.avg_p90) }}</td>
        </tr>
        <tr v-if="payload.rows.length === 0"><td colspan="8" class="empty-row">暂无统计报表数据</td></tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-3 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-sm">精度最佳 LAC</div>
      <div class="text-xl font-semibold">{{ bestP90 ? 'LAC ' + bestP90.lac : '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ bestP90 ? Math.round(bestP90.avg_p90) + 'm 平均 P90' : '暂无数据' }}</div>
    </div>
    <div class="card">
      <div class="font-semibold text-sm mb-sm">精度最弱 LAC</div>
      <div class="text-xl font-semibold">{{ worstP90 ? 'LAC ' + worstP90.lac : '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ worstP90 ? Math.round(worstP90.avg_p90) + 'm 平均 P90' : '暂无数据' }}</div>
    </div>
    <div class="card">
      <div class="font-semibold text-sm mb-sm">qualified BS 占比最高</div>
      <div class="text-xl font-semibold">{{ bestQualifiedBs ? 'LAC ' + bestQualifiedBs.lac : '-' }}</div>
      <div class="text-xs text-secondary mt-sm">{{ bestQualifiedBs ? ((bestQualifiedBs.qualified_bs_total / Math.max(bestQualifiedBs.bs_total, 1)) * 100).toFixed(1) + '%' : '暂无数据' }}</div>
    </div>
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">报表说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>所有数据基于快照版本 {{ payload.version.snapshot_version || 'v0' }}，数据集 {{ payload.version.dataset_key || '-' }}</li>
      <li>qualified+ 包含 qualified 和 excellent 两个状态</li>
      <li>点击表头可排序（Cell 总量 / BS 总量 / 平均 P90）</li>
      <li>导出文件自动带上版本号，方便业务复核与回溯</li>
    </ul>
  </div>
</template>

<style scoped>
.wrap-row { flex-wrap: wrap; }
.empty-row {
  padding: 20px;
  text-align: center;
  color: var(--c-text-muted);
}
.sortable-th {
  cursor: pointer;
  user-select: none;
}
.sortable-th:hover {
  color: var(--c-primary);
}
</style>
