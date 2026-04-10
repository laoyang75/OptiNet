<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import BatchSelector from '../../components/common/BatchSelector.vue'
import {
  getCellEvaluation, type CellEvaluationItem,
  getEvaluationWatchlist, type WatchItem,
  fetchCellRuleImpact, type RuleImpactPayload,
  fetchTrend, type TrendPoint,
} from '../../api/evaluation'
import { OPERATORS } from '../../types'
import type { LifecycleState } from '../../types'

/* ---------- state ---------- */
const distribution = ref({ excellent: 0, qualified: 0, observing: 0, waiting: 0, dormant: 0, retired: 0 })
const items = ref<CellEvaluationItem[]>([])
const stateFilter = ref('')
const operatorFilter = ref('')
const anchorOnly = ref(false)
const baselineOnly = ref(false)

const page = ref(1)
const pageSize = ref(50)
const totalCount = ref(0)
const totalPages = ref(0)

const currentBatchId = ref<number | undefined>()

/* watchlist (gap diagnosis) */
const watchItems = ref<WatchItem[]>([])
const watchRules = ref<Record<string, number>>({})

/* rule impact */
const ruleImpact = ref<RuleImpactPayload>({ rules: {}, impact: [] })

/* trend */
const trendPoints = ref<TrendPoint[]>([])

/* ---------- computed ---------- */
const filteredItems = computed(() => items.value.filter((item) => {
  if (stateFilter.value && item.lifecycle_state !== stateFilter.value) return false
  if (operatorFilter.value && item.operator_code !== operatorFilter.value) return false
  if (anchorOnly.value && !item.anchor_eligible) return false
  if (baselineOnly.value && !item.baseline_eligible) return false
  return true
}))

/* gap items: waiting/observing cells with gap text */
const gapItems = computed(() => watchItems.value.filter(w => w.state === 'waiting' || w.state === 'observing'))

/* ---------- load ---------- */
async function loadData() {
  try {
    const payload = await getCellEvaluation(page.value, pageSize.value, currentBatchId.value)
    distribution.value = payload.distribution
    items.value = payload.items
    totalCount.value = payload.totalCount
    totalPages.value = payload.totalPages
  } catch {
    items.value = []
  }
}

async function loadAll(batchId?: number) {
  currentBatchId.value = batchId
  page.value = 1
  await Promise.all([
    loadData(),
    getEvaluationWatchlist(batchId).then(p => { watchItems.value = p.items; watchRules.value = p.rules }).catch(() => {}),
    fetchCellRuleImpact(batchId).then(p => { ruleImpact.value = p }).catch(() => {}),
    fetchTrend().then(p => { trendPoints.value = p.points }).catch(() => {}),
  ])
}

function onBatchChange(batchId: number) {
  loadAll(batchId)
}

watch(page, loadData)
onMounted(() => loadAll())

/* ---------- trend SVG ---------- */
const STATES: LifecycleState[] = ['excellent', 'qualified', 'observing', 'waiting']
const STATE_COLORS: Record<string, string> = {
  excellent: 'var(--c-excellent, #22c55e)',
  qualified: 'var(--c-qualified, #3b82f6)',
  observing: 'var(--c-warning, #eab308)',
  waiting: 'var(--c-text-muted, #9ca3af)',
}

function trendPath(state: LifecycleState): string {
  if (trendPoints.value.length === 0) return ''
  const pts = trendPoints.value
  const maxVal = Math.max(1, ...pts.flatMap(p => STATES.map(s => p.cell[s])))
  const w = 600, h = 140
  return pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : (i / (pts.length - 1)) * w
    const y = h - (p.cell[state] / maxVal) * (h - 10)
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <PageHeader title="Cell 流转" description="Cell 状态、规则影响与晋升差距诊断。三层结构：状态数据 → 规则影响 → 批次趋势。" />

  <BatchSelector @batch-change="onBatchChange" />

  <!-- 第一层：状态数据 -->
  <StateDistribution title="Cell 状态分布" :data="distribution" class="mb-lg" />

  <div class="card mb-lg flex gap-md items-center wrap-row">
    <select v-model="stateFilter" class="filter-select">
      <option value="">全部状态</option>
      <option v-for="s in ['excellent','qualified','observing','waiting','dormant','retired']" :key="s">{{ s }}</option>
    </select>
    <select v-model="operatorFilter" class="filter-select">
      <option value="">全部运营商</option>
      <option v-for="op in OPERATORS" :key="op.operator_code" :value="op.operator_code">{{ op.operator_cn }}</option>
    </select>
    <label class="flex items-center gap-xs text-xs">
      <input v-model="anchorOnly" type="checkbox" /> 仅锚点
    </label>
    <label class="flex items-center gap-xs text-xs">
      <input v-model="baselineOnly" type="checkbox" /> 仅基线
    </label>
    <span class="text-xs text-muted">显示 {{ filteredItems.length }} / {{ items.length }} 个 Cell</span>
  </div>

  <div class="card" style="padding:0;overflow:auto;max-height:520px">
    <table class="data-table">
      <thead>
        <tr>
          <th>cell_id</th><th>LAC</th><th>bs_id</th><th>运营商</th><th>制式</th>
          <th>状态</th><th>锚点</th><th>观测量</th><th>设备数</th>
          <th>P90 (m)</th><th>跨度 (h)</th><th>活跃天</th><th>RSRP 均</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in filteredItems" :key="c.cell_id + '-' + c.lac + '-' + c.operator_code">
          <td class="font-mono font-semibold">{{ c.cell_id }}</td>
          <td class="font-mono">{{ c.lac }}</td>
          <td class="font-mono text-xs">{{ c.bs_id }}</td>
          <td class="font-mono text-xs">{{ c.operator_code }}</td>
          <td><span class="tag" :style="c.tech_norm === '5G' ? 'background:#ede9fe;color:#6d28d9' : 'background:#e0f2fe;color:#075985'">{{ c.tech_norm }}</span></td>
          <td><StatusTag :state="c.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="c.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ c.independent_obs }}</td>
          <td class="font-mono">{{ c.distinct_dev_id }}</td>
          <td class="font-mono">{{ Math.round(c.p90_radius_m || 0) }}</td>
          <td class="font-mono">{{ Math.round(c.observed_span_hours || 0) }}</td>
          <td class="font-mono">{{ c.active_days }}</td>
          <td class="font-mono">{{ c.rsrp_avg ?? '-' }}</td>
        </tr>
        <tr v-if="filteredItems.length === 0">
          <td colspan="13" class="text-center text-secondary" style="padding:20px">暂无匹配 Cell</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pagination :page="page" :page-size="pageSize" :total-count="totalCount" :total-pages="totalPages" @update:page="p => page = p" />

  <!-- 晋升差距诊断（从 Watchlist.vue 合并） -->
  <div class="card mt-lg" v-if="gapItems.length > 0">
    <div class="font-semibold text-sm mb-md">
      晋升差距诊断
      <span class="text-xs text-muted" style="margin-left:6px">waiting / observing 的 Cell 距 qualified 还差什么</span>
    </div>
    <div style="max-height:320px;overflow:auto">
      <table class="data-table" style="font-size:11.5px">
        <thead>
          <tr><th>cell_id</th><th>LAC</th><th>运营商</th><th>状态</th><th>观测量</th><th>设备数</th><th>P90 (m)</th><th>跨度 (h)</th><th>晋升差距</th></tr>
        </thead>
        <tbody>
          <tr v-for="w in gapItems.slice(0, 100)" :key="w.cell_id">
            <td class="font-mono font-semibold">{{ w.cell_id }}</td>
            <td class="font-mono">{{ w.lac }}</td>
            <td class="font-mono">{{ w.op }}</td>
            <td><StatusTag :state="w.state" size="sm" /></td>
            <td class="font-mono" :style="w.obs < (watchRules.qualified_min_obs ?? 3) ? 'color:var(--c-danger)' : ''">{{ w.obs }}</td>
            <td class="font-mono" :style="w.devs < (watchRules.qualified_min_devs ?? 2) ? 'color:var(--c-danger)' : ''">{{ w.devs }}</td>
            <td class="font-mono" :style="w.p90 > (watchRules.qualified_max_p90 ?? 1500) ? 'color:var(--c-danger)' : ''">{{ w.p90 || '-' }}</td>
            <td class="font-mono" :style="w.span_h < (watchRules.qualified_min_span_hours ?? 24) ? 'color:var(--c-warning)' : ''">{{ w.span_h }}</td>
            <td class="text-sm" style="color:var(--c-dormant);white-space:normal;max-width:260px">{{ w.gap }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="mt-sm flex gap-lg text-xs text-muted">
      <span>观测量 ≥ {{ watchRules.qualified_min_obs ?? 3 }}</span>
      <span>设备数 ≥ {{ watchRules.qualified_min_devs ?? 2 }}</span>
      <span>P90 &lt; {{ watchRules.qualified_max_p90 ?? 1500 }}m</span>
      <span>跨度 ≥ {{ watchRules.qualified_min_span_hours ?? 24 }}h</span>
    </div>
  </div>

  <!-- 第二层：规则影响 -->
  <div class="card mt-lg" v-if="ruleImpact.impact.length > 0">
    <div class="font-semibold text-sm mb-md">规则影响分析</div>
    <table class="data-table">
      <thead>
        <tr><th>阈值条件</th><th>当前值</th><th>卡住数量</th><th>说明</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in ruleImpact.impact" :key="r.rule">
          <td class="font-mono text-xs">{{ r.rule }}</td>
          <td class="font-mono">{{ r.threshold }}</td>
          <td class="font-mono font-semibold" style="color:var(--c-danger)">{{ r.blocked }}</td>
          <td class="text-sm text-secondary">{{ r.desc }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 第三层：批次趋势 -->
  <div class="card mt-lg" v-if="trendPoints.length > 1">
    <div class="font-semibold text-sm mb-md">Cell 批次趋势</div>
    <svg viewBox="0 0 600 140" class="trend-svg">
      <path v-for="s in STATES" :key="s" :d="trendPath(s)" fill="none" :stroke="STATE_COLORS[s]" stroke-width="2" />
    </svg>
    <div class="flex gap-md mt-xs">
      <span v-for="s in STATES" :key="s" class="text-xs flex items-center gap-xs">
        <span class="legend-dot" :style="{ background: STATE_COLORS[s] }"></span>{{ s }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.filter-select {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  background: var(--c-surface);
}
.wrap-row { flex-wrap: wrap; }
.trend-svg { width: 100%; height: auto; background: var(--c-bg); border-radius: var(--radius-md); }
.legend-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
</style>
