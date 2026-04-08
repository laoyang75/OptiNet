<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getFlowOverview } from '../lib/api'
import DataOriginBanner from '../components/DataOriginBanner.vue'
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue'

const loading = ref(true)
const error = ref('')
const context = ref<Record<string, any>>({})
const currentSnapshot = ref<Record<string, any>>({})
const diffSummary = ref<Record<string, any>>({})
const bsDiffSummary = ref<Record<string, any>>({})
const lacDiffSummary = ref<Record<string, any>>({})
const trend = ref<any[]>([])
const bsTrend = ref<any[]>([])
const lacTrend = ref<any[]>([])
const lifecycleRules = ref<Record<string, any>>({})

// 合并三层趋势数据为一张表
const mergedTrend = computed(() => {
  return trend.value.map((t, i) => ({
    ...t,
    bs_total: bsTrend.value[i]?.bs_total ?? '-',
    bs_active: bsTrend.value[i]?.bs_active ?? '-',
    bs_observing: bsTrend.value[i]?.bs_observing ?? '-',
    bs_waiting: bsTrend.value[i]?.bs_waiting ?? '-',
    lac_total: lacTrend.value[i]?.lac_total ?? '-',
    lac_active: lacTrend.value[i]?.lac_active ?? '-',
    lac_observing: lacTrend.value[i]?.lac_observing ?? '-',
  }))
})

onMounted(async () => {
  try {
    const res = await getFlowOverview()
    context.value = res.context || {}
    currentSnapshot.value = res.data?.current_snapshot || {}
    diffSummary.value = res.data?.diff_summary || {}
    bsDiffSummary.value = res.data?.bs_diff_summary || {}
    lacDiffSummary.value = res.data?.lac_diff_summary || {}
    trend.value = res.data?.trend || []
    bsTrend.value = res.data?.bs_trend || []
    lacTrend.value = res.data?.lac_trend || []
    lifecycleRules.value = res.data?.lifecycle_rules || {}
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
})

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}
</script>

<template>
  <div class="page">
    <DataOriginBanner
      :profileRunId="context.profile_run_id"
      :snapshotLabel="context.snapshot_label"
      :snapshotCount="context.snapshot_count"
    />

    <div v-if="loading" class="empty-state">加载中…</div>
    <div v-else-if="error" class="empty-state" style="color:var(--red-600)">{{ error }}</div>
    <template v-else>

      <!-- 三层当前状态 -->
      <div class="section">
        <div class="section-title">当前画像快照 — {{ currentSnapshot.snapshot_label || '-' }}</div>
        <div class="tier-grid">
          <!-- Cell -->
          <div class="tier-card">
            <div class="tier-label">Cell</div>
            <div class="tier-total">{{ fmt(currentSnapshot.stream_cell_count) }}</div>
            <div class="tier-states">
              <span class="state active">活跃 {{ fmt(currentSnapshot.active_count) }}</span>
              <span class="state observing">观察 {{ fmt(currentSnapshot.observing_count) }}</span>
              <span class="state waiting">等待 {{ fmt(currentSnapshot.waiting_count) }}</span>
            </div>
            <div class="tier-delta" v-if="diffSummary.new_active">
              +{{ diffSummary.new_active }} 新激活 / +{{ diffSummary.added_cells ?? 0 }} 新增
            </div>
          </div>
          <!-- BS -->
          <div class="tier-card">
            <div class="tier-label">BS (基站)</div>
            <div class="tier-total">{{ fmt(currentSnapshot.bs_count) }}</div>
            <div class="tier-states" v-if="bsTrend.length > 0">
              <span class="state active">活跃 {{ fmt(bsTrend[bsTrend.length-1]?.bs_active) }}</span>
              <span class="state observing">观察 {{ fmt(bsTrend[bsTrend.length-1]?.bs_observing) }}</span>
              <span class="state waiting">等待 {{ fmt(bsTrend[bsTrend.length-1]?.bs_waiting) }}</span>
            </div>
            <div class="tier-delta" v-if="bsDiffSummary.new_active">
              +{{ bsDiffSummary.new_active }} 新激活 / +{{ bsDiffSummary.added ?? 0 }} 新增
            </div>
          </div>
          <!-- LAC -->
          <div class="tier-card">
            <div class="tier-label">LAC (位置区)</div>
            <div class="tier-total">{{ fmt(currentSnapshot.lac_count) }}</div>
            <div class="tier-states" v-if="lacTrend.length > 0">
              <span class="state active">活跃 {{ fmt(lacTrend[lacTrend.length-1]?.lac_active) }}</span>
              <span class="state observing">观察 {{ fmt(lacTrend[lacTrend.length-1]?.lac_observing) }}</span>
              <span class="state waiting">等待 {{ fmt(lacTrend[lacTrend.length-1]?.lac_waiting) }}</span>
            </div>
            <div class="tier-delta" v-if="lacDiffSummary.new_active">
              +{{ lacDiffSummary.new_active }} 新激活
            </div>
          </div>
        </div>
      </div>

      <!-- 晋级规则 -->
      <div class="section" v-if="Object.keys(lifecycleRules).length > 0">
        <div class="section-title">当前晋级规则（可配置）</div>
        <div class="rules-grid">
          <div class="rule-card">
            <div class="rule-tier">Cell → Active</div>
            <div class="rule-detail" v-if="lifecycleRules.cell?.active">
              观测 ≥ {{ lifecycleRules.cell.active.min_obs }},
              设备 ≥ {{ lifecycleRules.cell.active.min_devs }},
              P90 &lt; {{ lifecycleRules.cell.active.max_p90_m }}m,
              跨度 ≥ {{ lifecycleRules.cell.active.min_span_hours }}h
            </div>
          </div>
          <div class="rule-card">
            <div class="rule-tier">BS → Active</div>
            <div class="rule-detail" v-if="lifecycleRules.bs?.active">
              {{ lifecycleRules.bs.active.min_excellent_cells }} 个优秀 Cell
              或 {{ lifecycleRules.bs.active.min_qualified_cells }} 个及格 Cell
            </div>
          </div>
          <div class="rule-card">
            <div class="rule-tier">LAC → Active</div>
            <div class="rule-detail" v-if="lifecycleRules.lac?.active">
              ≥ {{ lifecycleRules.lac.active.min_active_bs }} 个活跃 BS
              或活跃比 ≥ {{ (lifecycleRules.lac.active.min_active_bs_ratio * 100).toFixed(0) }}%
            </div>
          </div>
        </div>
      </div>

      <!-- Cell Diff 摘要 -->
      <div class="section" v-if="Object.keys(diffSummary).length > 0">
        <div class="section-title">与上一帧的变化</div>
        <div class="diff-bar">
          <span class="diff-tag added">+ {{ fmt(diffSummary.added_cells) }} 新增</span>
          <span class="diff-tag changed">~ {{ fmt(diffSummary.changed_cells) }} 变化</span>
          <span class="diff-tag unchanged">= {{ fmt(diffSummary.unchanged_cells) }} 不变</span>
          <span class="diff-tag removed" v-if="diffSummary.removed_cells">- {{ fmt(diffSummary.removed_cells) }} 移除</span>
          <span class="diff-tag shift" v-if="diffSummary.large_shift_cells">⚠ {{ fmt(diffSummary.large_shift_cells) }} 大位移</span>
        </div>
      </div>

      <!-- 三层收敛曲线表 -->
      <div class="section">
        <div class="section-title">流式收敛曲线（三层级联）</div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th rowspan="2">帧</th>
                <th rowspan="2">截止日期</th>
                <th colspan="4" class="group-header cell-group">Cell</th>
                <th colspan="3" class="group-header bs-group">BS</th>
                <th colspan="2" class="group-header lac-group">LAC</th>
              </tr>
              <tr>
                <th>总数</th><th>活跃</th><th>观察</th><th>等待</th>
                <th>总数</th><th>活跃</th><th>观察</th>
                <th>总数</th><th>活跃</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in mergedTrend" :key="t.snapshot_seq"
                  :class="{ 'row-current': t.snapshot_seq === context.snapshot_seq }">
                <td>{{ t.snapshot_label }}</td>
                <td>{{ t.window_end_date ? t.window_end_date.slice(0, 10) : '-' }}</td>
                <td>{{ fmt(t.stream_cell_count) }}</td>
                <td>{{ fmt(t.active_count) }}</td>
                <td>{{ fmt(t.observing_count) }}</td>
                <td>{{ fmt(t.waiting_count) }}</td>
                <td>{{ fmt(t.bs_total) }}</td>
                <td>{{ fmt(t.bs_active) }}</td>
                <td>{{ fmt(t.bs_observing) }}</td>
                <td>{{ fmt(t.lac_total) }}</td>
                <td>{{ fmt(t.lac_active) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }

.tier-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.tier-card {
  border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px;
  background: #fafafa;
}
.tier-label { font-size: 13px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }
.tier-total { font-size: 28px; font-weight: 700; color: #111; margin-bottom: 8px; }
.tier-states { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.state {
  font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.state.active    { background: #dcfce7; color: #16a34a; }
.state.observing { background: #fef3c7; color: #d97706; }
.state.waiting   { background: #f3f4f6; color: #6b7280; }
.tier-delta { font-size: 12px; color: #16a34a; }

.rules-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.rule-card {
  border: 1px solid #e0e7ff; border-radius: 6px; padding: 12px;
  background: #f0f4ff;
}
.rule-tier { font-size: 13px; font-weight: 600; color: #4338ca; margin-bottom: 4px; }
.rule-detail { font-size: 12px; color: #374151; line-height: 1.5; }

.diff-bar { display: flex; gap: 12px; flex-wrap: wrap; }
.diff-tag {
  display: inline-block; padding: 4px 12px; border-radius: 12px;
  font-size: 13px; font-weight: 600;
}
.diff-tag.added     { background: #dcfce7; color: #16a34a; }
.diff-tag.changed   { background: #fef3c7; color: #d97706; }
.diff-tag.unchanged { background: #f3f4f6; color: #6b7280; }
.diff-tag.removed   { background: #fee2e2; color: #dc2626; }
.diff-tag.shift     { background: #fef3c7; color: #b45309; }

.table-scroll { overflow-x: auto; }
.group-header { text-align: center; border-bottom: 2px solid; }
.cell-group { border-color: #16a34a; color: #16a34a; }
.bs-group   { border-color: #2563eb; color: #2563eb; }
.lac-group  { border-color: #9333ea; color: #9333ea; }

.row-current { background: #eff6ff; }
</style>
