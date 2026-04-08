<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getBaselineCurrent, getBaselineHistory } from '../lib/api'
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue'

const loading = ref(true)
const error = ref('')
const currentRun = ref<any>(null)
const previousRun = ref<any>(null)
const diffSummary = ref<any>(null)
const history = ref<any[]>([])

onMounted(async () => {
  try {
    const [curRes, histRes] = await Promise.all([
      getBaselineCurrent(),
      getBaselineHistory(),
    ])
    currentRun.value = curRes.data?.current_run || null
    previousRun.value = curRes.data?.previous_run || null
    diffSummary.value = curRes.data?.diff_summary || null
    history.value = histRes.data ?? []
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
})

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}
function fmtTime(t: any) {
  if (!t) return '-'
  return String(t).replace('T', ' ').slice(0, 19)
}
</script>

<template>
  <div class="page">
    <h2 class="page-title">画像版本基线</h2>

    <div v-if="loading" class="empty-state">加载中…</div>
    <div v-else-if="error" class="empty-state" style="color:var(--red-600)">{{ error }}</div>
    <template v-else>

      <!-- Current run info -->
      <div v-if="currentRun" class="section">
        <div class="section-title">当前版本</div>
        <div class="grid-4">
          <MetricCardWithDelta label="Run ID" :value="currentRun.profile_run_id" />
          <MetricCardWithDelta label="Cell" :value="fmt(currentRun.final_cell_count)" />
          <MetricCardWithDelta label="BS" :value="fmt(currentRun.final_bs_count)" />
          <MetricCardWithDelta label="LAC" :value="fmt(currentRun.final_lac_count)" />
          <MetricCardWithDelta label="快照数" :value="currentRun.snapshot_count" />
          <MetricCardWithDelta label="参数哈希" :value="currentRun.params_hash || '-'" />
          <MetricCardWithDelta label="完成时间" :value="fmtTime(currentRun.finished_at)" />
        </div>
      </div>
      <div v-else class="empty-state">暂无已完成的画像版本</div>

      <!-- Diff with previous -->
      <div v-if="diffSummary && previousRun" class="section">
        <div class="section-title">版本对比：{{ currentRun?.profile_run_id }} vs {{ previousRun.profile_run_id }}</div>
        <div class="grid-4">
          <MetricCardWithDelta label="当前 Cell" :value="fmt(diffSummary.cur_total)" />
          <MetricCardWithDelta label="上次 Cell" :value="fmt(diffSummary.prev_total)" />
          <MetricCardWithDelta label="新增" :value="fmt(diffSummary.added)" />
          <MetricCardWithDelta label="移除" :value="fmt(diffSummary.removed)" />
          <MetricCardWithDelta label="生命周期变化" :value="fmt(diffSummary.lifecycle_changed)" />
          <MetricCardWithDelta label="锚点变化" :value="fmt(diffSummary.anchorable_changed)" />
        </div>
        <div class="prev-info">
          上一版本: <code>{{ previousRun.profile_run_id }}</code>
          | 参数: <code>{{ previousRun.params_hash || '-' }}</code>
          | 完成: {{ fmtTime(previousRun.finished_at) }}
        </div>
      </div>
      <div v-else-if="currentRun" class="section">
        <div class="section-title">版本对比</div>
        <div class="empty-state">只有一次运行，暂无可比版本</div>
      </div>

      <!-- History -->
      <div v-if="history.length > 0" class="section">
        <div class="section-title">运行历史</div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>模式</th>
              <th>快照数</th>
              <th>Cell</th>
              <th>BS</th>
              <th>LAC</th>
              <th>参数</th>
              <th>完成时间</th>
              <th>当前</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in history" :key="r.profile_run_id" :class="{ 'row-current': r.is_current }">
              <td class="mono">{{ r.profile_run_id }}</td>
              <td>{{ r.mode }}</td>
              <td>{{ r.snapshot_count }}</td>
              <td>{{ fmt(r.final_cell_count) }}</td>
              <td>{{ fmt(r.final_bs_count) }}</td>
              <td>{{ fmt(r.final_lac_count) }}</td>
              <td class="mono">{{ r.params_hash || '-' }}</td>
              <td>{{ fmtTime(r.finished_at) }}</td>
              <td>{{ r.is_current ? '✓' : '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 16px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0 0 16px; }
.mono { font-family: var(--font-mono, monospace); font-size: 12px; }
.row-current { background: #eff6ff; }
.prev-info { font-size: 12px; color: var(--gray-500); margin-top: 12px; }
code { font-family: var(--font-mono, monospace); font-size: 11px; background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; }
</style>
