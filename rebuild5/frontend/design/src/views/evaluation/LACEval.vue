<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import BatchSelector from '../../components/common/BatchSelector.vue'
import {
  getLACEvaluation, type LACEvaluationItem,
  fetchLACRuleImpact, type RuleImpactPayload,
  fetchTrend, type TrendPoint,
} from '../../api/evaluation'
import type { LifecycleState } from '../../types'

const distribution = ref({ excellent: 0, qualified: 0, observing: 0, waiting: 0, dormant: 0, retired: 0 })
const items = ref<LACEvaluationItem[]>([])
const page = ref(1)
const pageSize = ref(50)
const totalCount = ref(0)
const totalPages = ref(0)

const currentBatchId = ref<number | undefined>()
const ruleImpact = ref<RuleImpactPayload>({ rules: {}, impact: [] })
const trendPoints = ref<TrendPoint[]>([])

async function loadData() {
  try {
    const payload = await getLACEvaluation(page.value, pageSize.value, currentBatchId.value)
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
    fetchLACRuleImpact(batchId).then(p => { ruleImpact.value = p }).catch(() => {}),
    fetchTrend().then(p => { trendPoints.value = p.points }).catch(() => {}),
  ])
}

function onBatchChange(batchId: number) {
  loadAll(batchId)
}

watch(page, loadData)
onMounted(() => loadAll())

/* ---------- trend SVG ---------- */
const STATES: LifecycleState[] = ['qualified', 'observing', 'waiting']
const STATE_COLORS: Record<string, string> = {
  qualified: 'var(--c-qualified, #3b82f6)',
  observing: 'var(--c-warning, #eab308)',
  waiting: 'var(--c-text-muted, #9ca3af)',
}

function trendPath(state: LifecycleState): string {
  if (trendPoints.value.length === 0) return ''
  const pts = trendPoints.value
  const maxVal = Math.max(1, ...pts.flatMap(p => STATES.map(s => p.lac[s] ?? 0)))
  const w = 600, h = 140
  return pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : (i / (pts.length - 1)) * w
    const y = h - ((p.lac[state] ?? 0) / maxVal) * (h - 10)
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <PageHeader title="LAC 流转" description="区域整体质量。LAC 完全由下属 BS 上卷而来。" />

  <BatchSelector @batch-change="onBatchChange" />

  <!-- 第一层：状态数据 -->
  <StateDistribution title="LAC 状态分布" :data="distribution" class="mb-lg" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>LAC</th><th>运营商</th><th>状态</th><th>锚点</th>
          <th>总 BS</th><th>qualified BS</th><th style="width:160px">qualified 比例</th><th>晋升分析</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="l in items" :key="l.lac + '-' + l.operator_code">
          <td class="font-mono font-semibold">{{ l.lac }}</td>
          <td class="font-mono text-xs">{{ l.operator_code }}</td>
          <td><StatusTag :state="l.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="l.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ l.total_bs }}</td>
          <td class="font-mono">{{ l.qualified_bs }}</td>
          <td><PercentBar :value="l.qualified_bs_ratio" /></td>
          <td class="text-xs text-secondary">
            <template v-if="l.qualified_bs >= 3 || l.qualified_bs_ratio >= 0.1">
              已达标（qualified BS ≥ 3 或占比 ≥ 10%）
            </template>
            <template v-else>
              差 {{ Math.max(0, 3 - l.qualified_bs) }} 个 qualified BS
            </template>
          </td>
        </tr>
        <tr v-if="items.length === 0">
          <td colspan="8" class="text-center text-secondary" style="padding:20px">暂无 LAC 评估结果</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pagination :page="page" :page-size="pageSize" :total-count="totalCount" :total-pages="totalPages" @update:page="p => page = p" />

  <!-- 第二层：规则影响 -->
  <div class="card mt-lg" v-if="ruleImpact.impact.length > 0">
    <div class="font-semibold text-sm mb-md">LAC 规则影响分析</div>
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

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">LAC 晋升规则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li><strong>qualified</strong>：qualified BS ≥ 3，或 qualified BS / 全部 BS ≥ 10%</li>
      <li><strong>observing</strong>：至少 1 个下属 BS 为非 waiting</li>
      <li>LAC 不跳过 BS 直接从 Cell 重判</li>
    </ul>
  </div>

  <!-- 第三层：批次趋势 -->
  <div class="card mt-lg" v-if="trendPoints.length > 1">
    <div class="font-semibold text-sm mb-md">LAC 批次趋势</div>
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
.trend-svg { width: 100%; height: auto; background: var(--c-bg); border-radius: var(--radius-md); }
.legend-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
</style>
