<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import BatchSelector from '../../components/common/BatchSelector.vue'
import {
  getBSEvaluation, type BSEvaluationItem,
  fetchBSRuleImpact, type RuleImpactPayload,
  fetchTrend, type TrendPoint,
} from '../../api/evaluation'
import type { LifecycleState } from '../../types'

const distribution = ref({ excellent: 0, qualified: 0, observing: 0, waiting: 0, dormant: 0, retired: 0 })
const items = ref<BSEvaluationItem[]>([])
const page = ref(1)
const pageSize = ref(50)
const totalCount = ref(0)
const totalPages = ref(0)

const currentBatchId = ref<number | undefined>()
const ruleImpact = ref<RuleImpactPayload>({ rules: {}, impact: [] })
const trendPoints = ref<TrendPoint[]>([])

async function loadData() {
  try {
    const payload = await getBSEvaluation(page.value, pageSize.value, currentBatchId.value)
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
    fetchBSRuleImpact(batchId).then(p => { ruleImpact.value = p }).catch(() => {}),
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
  const maxVal = Math.max(1, ...pts.flatMap(p => STATES.map(s => p.bs[s] ?? 0)))
  const w = 600, h = 140
  return pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : (i / (pts.length - 1)) * w
    const y = h - ((p.bs[state] ?? 0) / maxVal) * (h - 10)
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <PageHeader title="BS 流转" description="BS 由下属 Cell 上卷而来。查看 BS 状态、下属 Cell 构成、规则影响与晋升条件。" />

  <BatchSelector @batch-change="onBatchChange" />

  <!-- 第一层：状态数据 -->
  <StateDistribution title="BS 状态分布" :data="distribution" class="mb-lg" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>bs_id</th><th>LAC</th><th>运营商</th><th>状态</th><th>锚点</th>
          <th>总 Cell</th><th>qualified+ Cell</th><th>excellent Cell</th><th>大覆盖</th><th>晋升分析</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in items" :key="b.bs_id + '-' + b.lac + '-' + b.operator_code">
          <td class="font-mono font-semibold">{{ b.bs_id }}</td>
          <td class="font-mono">{{ b.lac }}</td>
          <td class="font-mono text-xs">{{ b.operator_code }}</td>
          <td><StatusTag :state="b.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="b.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ b.total_cells }}</td>
          <td class="font-mono" :style="b.qualified_cells >= 3 ? 'color:var(--c-success)' : ''">{{ b.qualified_cells }}</td>
          <td class="font-mono" :style="b.excellent_cells >= 1 ? 'color:var(--c-excellent)' : ''">{{ b.excellent_cells }}</td>
          <td>
            <span v-if="b.large_spread" class="tag" style="background:#fef3c7;color:#92400e">大覆盖</span>
            <span v-else class="text-muted text-xs">-</span>
          </td>
          <td class="text-xs text-secondary">
            <template v-if="b.excellent_cells >= 1">有 excellent Cell，已达标</template>
            <template v-else-if="b.qualified_cells >= 3">qualified+ ≥ 3，已达标</template>
            <template v-else>差 {{ Math.max(0, 3 - b.qualified_cells) }} 个 qualified+ Cell</template>
          </td>
        </tr>
        <tr v-if="items.length === 0">
          <td colspan="10" class="text-center text-secondary" style="padding:20px">暂无 BS 评估结果</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pagination :page="page" :page-size="pageSize" :total-count="totalCount" :total-pages="totalPages" @update:page="p => page = p" />

  <!-- 第二层：规则影响 -->
  <div class="card mt-lg" v-if="ruleImpact.impact.length > 0">
    <div class="font-semibold text-sm mb-md">BS 规则影响分析</div>
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
    <div class="font-semibold text-sm mb-sm">BS 晋升规则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li><strong>qualified</strong>：≥ 1 个 excellent Cell，或 ≥ 3 个 qualified+ Cell</li>
      <li><strong>observing</strong>：至少 1 个下属 Cell 有 GPS 证据</li>
      <li><strong>anchor_eligible</strong>：至少 1 个下属 Cell 为 anchor_eligible</li>
      <li>BS 不直接读取原始报文，只看下属 Cell 聚合结果</li>
    </ul>
  </div>

  <!-- 第三层：批次趋势 -->
  <div class="card mt-lg" v-if="trendPoints.length > 1">
    <div class="font-semibold text-sm mb-md">BS 批次趋势</div>
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
