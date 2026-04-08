<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getRunsCurrent } from '../lib/api'
import DataOriginBanner from '../components/DataOriginBanner.vue'
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue'

const loading = ref(true)
const error = ref('')
const context = ref<Record<string, any>>({})
const currentRun = ref<Record<string, any> | null>(null)
const runs = ref<any[]>([])

onMounted(async () => {
  try {
    const res = await getRunsCurrent()
    context.value = res.context || {}
    currentRun.value = res.data?.current_run || null
    runs.value = res.data?.runs || []
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
    <DataOriginBanner
      :profileRunId="context.profile_run_id"
      :snapshotLabel="context.snapshot_label"
      :snapshotCount="context.snapshot_count"
    />

    <h2 class="page-title">画像运行中心</h2>

    <div v-if="loading" class="empty-state">加载中…</div>
    <div v-else-if="error" class="empty-state" style="color:var(--red-600)">{{ error }}</div>
    <template v-else>

      <!-- Current run -->
      <div v-if="currentRun" class="section">
        <div class="section-title">当前运行</div>
        <div class="grid-4">
          <MetricCardWithDelta label="Run ID" :value="currentRun.profile_run_id" />
          <MetricCardWithDelta label="模式" :value="currentRun.mode" />
          <MetricCardWithDelta label="快照数" :value="currentRun.snapshot_count" />
          <MetricCardWithDelta label="参数哈希" :value="currentRun.params_hash" />
          <MetricCardWithDelta label="Cell" :value="fmt(currentRun.final_cell_count)" />
          <MetricCardWithDelta label="BS" :value="fmt(currentRun.final_bs_count)" />
          <MetricCardWithDelta label="LAC" :value="fmt(currentRun.final_lac_count)" />
          <MetricCardWithDelta label="状态" :value="currentRun.status" />
        </div>
      </div>

      <!-- Run history -->
      <div class="section">
        <div class="section-title">运行历史</div>
        <div v-if="runs.length === 0" class="empty-state">暂无运行记录</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>模式</th>
              <th>状态</th>
              <th>快照数</th>
              <th>Cell</th>
              <th>BS</th>
              <th>LAC</th>
              <th>参数</th>
              <th>数据范围</th>
              <th>开始时间</th>
              <th>完成时间</th>
              <th>当前</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.profile_run_id" :class="{ 'row-current': r.is_current }">
              <td class="mono">{{ r.profile_run_id }}</td>
              <td>{{ r.mode }}</td>
              <td>{{ r.status }}</td>
              <td>{{ r.snapshot_count }}</td>
              <td>{{ fmt(r.final_cell_count) }}</td>
              <td>{{ fmt(r.final_bs_count) }}</td>
              <td>{{ fmt(r.final_lac_count) }}</td>
              <td class="mono">{{ r.params_hash || '-' }}</td>
              <td>{{ r.source_date_from ? r.source_date_from.slice(0,10) : '-' }} ~ {{ r.source_date_to ? r.source_date_to.slice(0,10) : '-' }}</td>
              <td>{{ fmtTime(r.started_at) }}</td>
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
</style>
