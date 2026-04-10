<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import {
  getEnrichmentAnomalies,
  getEnrichmentCoverage,
  getEnrichmentStats,
  type EnrichmentAnomalyItem,
  type EnrichmentCoverageItem,
  type EnrichmentStatsPayload,
} from '../../api/enrichment'
import { fmt, pct } from '../../composables/useFormat'

const emptyStats: EnrichmentStatsPayload = {
  version: { run_id: '', dataset_key: 'sample_6lac', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    total_path_a: 0,
    donor_matched_count: 0,
    gps_filled: 0,
    rsrp_filled: 0,
    rsrq_filled: 0,
    sinr_filled: 0,
    operator_filled: 0,
    lac_filled: 0,
    tech_filled: 0,
    gps_anomaly_count: 0,
    collision_skip_anomaly_count: 0,
    donor_excellent_count: 0,
    donor_qualified_count: 0,
    remaining_none_gps: 0,
    remaining_none_signal: 0,
  },
  coverage: {
    gps_fill_rate: 0,
    signal_fill_rate: 0,
    operator_fill_rate: 0,
  },
}

const stats = ref<EnrichmentStatsPayload>(emptyStats)
const fieldFills = ref<EnrichmentCoverageItem[]>([])
const anomalies = ref<EnrichmentAnomalyItem[]>([])

const anomalyRate = computed(() => {
  const total = stats.value.summary.total_path_a
  return total > 0 ? stats.value.summary.gps_anomaly_count / total : 0
})

const donorTotal = computed(() => stats.value.summary.donor_excellent_count + stats.value.summary.donor_qualified_count)

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  try {
    const [statsPayload, coveragePayload, anomalyPayload] = await Promise.all([
      getEnrichmentStats(),
      getEnrichmentCoverage(),
      getEnrichmentAnomalies(6),
    ])
    stats.value = statsPayload
    fieldFills.value = coveragePayload.items
    anomalies.value = anomalyPayload.items
  } catch {
    stats.value = { ...emptyStats }
    fieldFills.value = []
    anomalies.value = []
  }
})
</script>

<template>
  <PageHeader title="知识补数" description="Step 4 基于上一轮正式库的知识补数效果。仅处理 Path A 命中记录。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} ｜ 运行 {{ stats.version.run_id || '-' }} ｜ {{ stats.version.snapshot_version_prev }} → {{ stats.version.snapshot_version }}
    </div>
  </PageHeader>

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="Path A 总量" :value="fmt(stats.summary.total_path_a)" :subtitle="'donor 命中 ' + fmt(stats.summary.donor_matched_count)" />
    <SummaryCard title="GPS 补数" :value="fmt(stats.summary.gps_filled)" :subtitle="pct(stats.coverage.gps_fill_rate) + ' 补齐率'" color="var(--c-primary)" />
    <SummaryCard title="信号补数" :value="fmt(stats.summary.rsrp_filled + stats.summary.rsrq_filled + stats.summary.sinr_filled)" :subtitle="pct(stats.coverage.signal_fill_rate) + ' 补齐率'" color="var(--c-qualified)" />
    <SummaryCard title="GPS 异常" :value="fmt(stats.summary.gps_anomaly_count)" :subtitle="pct(anomalyRate)" color="var(--c-danger)" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">字段级补数统计</div>
    <table class="data-table">
      <thead>
        <tr><th>字段</th><th>补数量</th><th style="width:220px">补数率</th><th>来源</th></tr>
      </thead>
      <tbody>
        <tr v-for="item in fieldFills" :key="item.field_name">
          <td class="font-mono font-semibold">{{ item.field_name }}</td>
          <td class="font-mono">{{ fmt(item.filled_count) }}</td>
          <td><PercentBar :value="item.fill_rate" /></td>
          <td class="text-xs text-secondary font-mono">{{ item.donor_source }}</td>
        </tr>
        <tr v-if="fieldFills.length === 0">
          <td colspan="4" class="empty-row">暂无补数统计</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-2 gap-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md">donor 质量分布</div>
      <div class="flex flex-col gap-sm">
        <div class="metric-row">
          <span class="text-sm">excellent donor</span>
          <span class="font-mono font-semibold" style="color:var(--c-excellent)">{{ fmt(stats.summary.donor_excellent_count) }}</span>
        </div>
        <div class="metric-row">
          <span class="text-sm">qualified donor</span>
          <span class="font-mono font-semibold" style="color:var(--c-qualified)">{{ fmt(stats.summary.donor_qualified_count) }}</span>
        </div>
        <div class="metric-row">
          <span class="text-sm">可用 donor 总量</span>
          <span class="font-mono">{{ fmt(donorTotal) }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md">GPS 异常样本</div>
      <div class="mini-table">
        <div v-for="item in anomalies" :key="item.record_id" class="mini-row">
          <div>
            <div class="font-mono font-semibold text-xs">{{ item.record_id }}</div>
            <div class="text-xs text-secondary">cell {{ item.cell_id ?? '-' }} ｜ bs {{ item.bs_id ?? '-' }}</div>
          </div>
          <div class="mini-meta">
            <span class="font-mono">{{ item.distance_to_donor_m ? Math.round(item.distance_to_donor_m) : '-' }}m</span>
            <span class="text-xs text-secondary">{{ formatDateTime(item.event_time_std) }}</span>
          </div>
        </div>
        <div v-if="anomalies.length === 0" class="empty-row">暂无异常样本</div>
      </div>
      <router-link to="/governance/cell" class="btn mt-md" style="font-size:12px">查看 Cell 维护 →</router-link>
    </div>
  </div>
</template>

<style scoped>
.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mini-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mini-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--c-border-light);
}
.mini-row:last-child { border-bottom: none; padding-bottom: 0; }
.mini-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.empty-row {
  padding: 20px;
  text-align: center;
  color: var(--c-text-muted);
}
</style>
