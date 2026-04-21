<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import BatchSelector from '../../components/common/BatchSelector.vue'
import {
  getEvaluationOverview, type EvaluationOverviewPayload,
  getEvaluationSnapshot, type SnapshotPayload,
  fetchTrend, type TrendPoint,
} from '../../api/evaluation'
import { fmt } from '../../composables/useFormat'
import { STATE_LABELS, type LifecycleState } from '../../types'

const emptyDistribution: Record<LifecycleState, number> = {
  excellent: 0, qualified: 0, observing: 0, waiting: 0, active: 0, dormant: 0, retired: 0,
}

const payload = ref<EvaluationOverviewPayload>({
  dataset_key: '', run_id: '', snapshot_version: 'v0', snapshot_version_prev: 'v0',
  cell_distribution: { ...emptyDistribution },
  bs_distribution: { ...emptyDistribution },
  lac_distribution: { ...emptyDistribution },
  diff_summary: { new: 0, promoted: 0, demoted: 0, eligibility_changed: 0, geometry_changed: 0, unchanged: 0 },
  counts: { cell_total: 0, bs_total: 0, lac_total: 0, anchor_eligible_cells: 0 },
  cleanup: { waiting_pruned_cells: 0, dormant_marked_cells: 0 },
})

const snapshot = ref<SnapshotPayload>({
  snapshot_version: '', snapshot_version_prev: '',
  summary: { new: 0, promoted: 0, demoted: 0, unchanged: 0 },
  items: [],
})

const trendPoints = ref<TrendPoint[]>([])
const currentBatchId = ref<number | undefined>()

async function loadData(batchId?: number) {
  currentBatchId.value = batchId
  try {
    const [ov, snap, trend] = await Promise.all([
      getEvaluationOverview(batchId),
      getEvaluationSnapshot(batchId),
      fetchTrend(),
    ])
    payload.value = ov
    snapshot.value = snap
    trendPoints.value = trend.points
  } catch { /* keep defaults */ }
}

function onBatchChange(batchId: number) {
  loadData(batchId)
}

onMounted(() => loadData())

/* ---------- trend SVG helpers ---------- */
const STATES: LifecycleState[] = ['excellent', 'qualified', 'observing', 'waiting']
const STATE_COLORS: Record<string, string> = {
  excellent: 'var(--c-excellent, #22c55e)',
  qualified: 'var(--c-qualified, #3b82f6)',
  observing: 'var(--c-warning, #eab308)',
  waiting: 'var(--c-text-muted, #9ca3af)',
}

function trendPath(layer: 'cell' | 'bs' | 'lac', state: LifecycleState): string {
  if (trendPoints.value.length === 0) return ''
  const pts = trendPoints.value
  const maxVal = Math.max(1, ...pts.flatMap(p => STATES.map(s => p[layer]?.[s] ?? 0)))
  const w = 480, h = 120
  return pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : (i / (pts.length - 1)) * w
    const y = h - ((p[layer]?.[state] ?? 0) / maxVal) * (h - 10)
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <PageHeader title="流转总览" description="三层对象整体收敛情况。从总览可跳到具体层级评估页面。" />

  <BatchSelector @batch-change="onBatchChange" />

  <!-- 关键指标 -->
  <div class="grid grid-6 mb-lg">
    <SummaryCard title="Cell 总量" :value="fmt(payload.counts.cell_total)" />
    <SummaryCard title="BS 总量" :value="fmt(payload.counts.bs_total)" />
    <SummaryCard title="LAC 总量" :value="fmt(payload.counts.lac_total)" />
    <SummaryCard title="本批新增" :value="fmt(payload.diff_summary.new)" color="var(--c-success)" />
    <SummaryCard title="本批晋升" :value="fmt(payload.diff_summary.promoted)" color="var(--c-primary)" />
    <SummaryCard title="锚点 Cell" :value="fmt(payload.counts.anchor_eligible_cells)" subtitle="具备锚点资格" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-sm">候选池清理</div>
    <div class="flex gap-lg wrap-row text-sm">
      <span>本批等待超时清理 <strong class="font-mono">{{ fmt(payload.cleanup.waiting_pruned_cells) }}</strong></span>
      <span>本批 dormant 转移
        <strong class="font-mono">
          <template v-if="payload.cleanup.dormant_marked_cells > 0">{{ fmt(payload.cleanup.dormant_marked_cells) }}</template>
          <template v-else>待开发</template>
        </strong>
      </span>
    </div>
  </div>

  <!-- 三层状态分布 -->
  <div class="flex flex-col gap-lg mb-lg">
    <StateDistribution title="Cell 状态分布" :data="payload.cell_distribution" />
    <StateDistribution title="BS 状态分布" :data="payload.bs_distribution" />
    <StateDistribution title="LAC 状态分布" :data="payload.lac_distribution" />
  </div>

  <div class="grid grid-2 gap-lg mb-lg">
    <!-- Diff 摘要面板（原 Snapshot 页内容） -->
    <div class="card">
      <div class="font-semibold text-sm mb-md">
        本批变动摘要
        <span class="text-xs text-muted" style="margin-left:6px">{{ snapshot.snapshot_version_prev }} → {{ snapshot.snapshot_version }}</span>
      </div>
      <div class="diff-grid mb-md">
        <div class="diff-item"><span class="text-xs text-muted">新注册</span><span class="font-mono font-semibold">+{{ fmt(payload.diff_summary.new) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">晋升</span><span class="font-mono font-semibold" style="color:var(--c-qualified)">+{{ fmt(payload.diff_summary.promoted) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">降级</span><span class="font-mono font-semibold" style="color:var(--c-danger)">{{ fmt(payload.diff_summary.demoted) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">资格变化</span><span class="font-mono font-semibold">{{ fmt(payload.diff_summary.eligibility_changed) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">几何变化</span><span class="font-mono font-semibold">{{ fmt(payload.diff_summary.geometry_changed) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">未变化</span><span class="font-mono font-semibold">{{ fmt(payload.diff_summary.unchanged) }}</span></div>
      </div>

      <!-- 变动对象列表（从 Snapshot.vue 合并） -->
      <div v-if="snapshot.items.length > 0">
        <div class="text-xs text-muted mb-sm">变动对象（前 50 条）</div>
        <div style="max-height:240px;overflow:auto">
          <table class="data-table" style="font-size:11px">
            <thead>
              <tr><th>cell_id</th><th>LAC</th><th>运营商</th><th>前</th><th></th><th>现</th><th>类型</th><th>原因</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in snapshot.items.slice(0, 50)" :key="d.cell_id + '-' + d.lac + '-' + d.operator_code + '-' + (d.tech_norm || '') + '-' + d.diff_kind">
                <td class="font-mono">{{ d.cell_id }}</td>
                <td class="font-mono">{{ d.lac }}</td>
                <td class="font-mono">{{ d.operator_code }}</td>
                <td><StatusTag v-if="d.prev" :state="d.prev" size="sm" /><span v-else class="text-muted">-</span></td>
                <td class="text-muted">→</td>
                <td><StatusTag v-if="d.curr" :state="d.curr" size="sm" /><span v-else class="text-muted">-</span></td>
                <td class="font-mono">{{ d.diff_kind }}</td>
                <td class="text-secondary">{{ d.reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 快速跳转 -->
    <div class="card">
      <div class="font-semibold text-sm mb-md">快速跳转</div>
      <div class="flex flex-col gap-sm">
        <router-link to="/evaluation/cell" class="jump-link">Cell 流转 → 单 Cell 状态、规则影响与晋升差距</router-link>
        <router-link to="/evaluation/bs" class="jump-link">BS 流转 → 基站下属 Cell 构成与晋升分析</router-link>
        <router-link to="/evaluation/lac" class="jump-link">LAC 流转 → 区域整体质量与覆盖</router-link>
      </div>
    </div>
  </div>

  <!-- 跨批次趋势 -->
  <div class="card" v-if="trendPoints.length > 1">
    <div class="font-semibold text-sm mb-md">跨批次趋势</div>
    <div class="grid grid-3 gap-lg">
      <div v-for="layer in (['cell', 'bs', 'lac'] as const)" :key="layer">
        <div class="text-xs text-muted mb-xs" style="text-transform:uppercase">{{ layer }}</div>
        <svg viewBox="0 0 480 120" class="trend-svg">
          <path v-for="s in STATES" :key="s" :d="trendPath(layer, s)" fill="none" :stroke="STATE_COLORS[s]" stroke-width="2" />
        </svg>
        <div class="flex gap-md mt-xs">
          <span v-for="s in STATES" :key="s" class="text-xs flex items-center gap-xs">
            <span class="legend-dot" :style="{ background: STATE_COLORS[s] }"></span>{{ STATE_LABELS[s] }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-md); }
.diff-item { display: flex; flex-direction: column; gap: 2px; }
.jump-link {
  display: block;
  padding: 8px 12px;
  font-size: 12px;
  background: var(--c-bg);
  border-radius: var(--radius-md);
  color: var(--c-primary);
  transition: background 0.1s;
}
.jump-link:hover { background: var(--c-primary-light); text-decoration: none; }
.trend-svg { width: 100%; height: auto; background: var(--c-bg); border-radius: var(--radius-md); }
.legend-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
</style>
