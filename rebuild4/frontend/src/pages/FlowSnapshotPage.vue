<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { getFlowSnapshotTimepoints, getFlowSnapshot } from '../lib/api'
import DataOriginBanner from '../components/DataOriginBanner.vue'

const loading = ref(true)
const error = ref('')
const context = ref<Record<string, any>>({})
const timepoints = ref<any[]>([])

const selectedA = ref<number | ''>('')
const selectedB = ref<number | ''>('')
const snapA = ref<Record<string, any>>({})
const snapB = ref<Record<string, any>>({})
const diffA = ref<Record<string, any>>({})
const diffB = ref<Record<string, any>>({})
const loadingSnaps = ref(false)

const metricRows = [
  { key: 'stream_cell_count', label: 'Cell 总数' },
  { key: 'active_count',      label: '活跃' },
  { key: 'observing_count',   label: '观察中' },
  { key: 'waiting_count',     label: '等待中' },
  { key: 'anchorable_count',  label: '锚点可用' },
  { key: 'bs_count',          label: 'BS' },
  { key: 'lac_count',         label: 'LAC' },
]

onMounted(async () => {
  try {
    const res = await getFlowSnapshotTimepoints()
    context.value = res.context || {}
    timepoints.value = res.data || []
    // pre-select first two
    if (timepoints.value.length >= 2) {
      selectedA.value = timepoints.value[0].snapshot_seq
      selectedB.value = timepoints.value[1].snapshot_seq
    } else if (timepoints.value.length === 1) {
      selectedA.value = timepoints.value[0].snapshot_seq
    }
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
})

async function loadSnapshots() {
  loadingSnaps.value = true
  try {
    const promises: Promise<any>[] = []
    promises.push(selectedA.value !== '' ? getFlowSnapshot(selectedA.value as number) : Promise.resolve({ data: {} }))
    promises.push(selectedB.value !== '' ? getFlowSnapshot(selectedB.value as number) : Promise.resolve({ data: {} }))
    const [resA, resB] = await Promise.all(promises)
    snapA.value = resA.data?.snapshot || {}
    snapB.value = resB.data?.snapshot || {}
    diffA.value = resA.data?.diff_summary || {}
    diffB.value = resB.data?.diff_summary || {}
  } catch (e: any) {
    error.value = e.message || '快照加载失败'
  } finally {
    loadingSnaps.value = false
  }
}

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}

function tpLabel(tp: any) {
  return `${tp.snapshot_label} (${tp.window_end_date ? tp.window_end_date.slice(0, 10) : ''})`
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

      <!-- Two-column comparison selector -->
      <div class="compare-columns">
        <div class="compare-col col-a">
          <div class="col-header">时间点 A</div>
          <select v-model="selectedA" class="select-control full-w">
            <option value="">请选择</option>
            <option v-for="tp in timepoints" :key="tp.snapshot_seq" :value="tp.snapshot_seq">
              {{ tpLabel(tp) }}
            </option>
          </select>
        </div>
        <div class="compare-col col-b">
          <div class="col-header">时间点 B</div>
          <select v-model="selectedB" class="select-control full-w">
            <option value="">请选择</option>
            <option v-for="tp in timepoints" :key="tp.snapshot_seq" :value="tp.snapshot_seq">
              {{ tpLabel(tp) }}
            </option>
          </select>
        </div>
      </div>

      <div style="text-align:center;margin:20px 0;">
        <button class="btn" :disabled="loadingSnaps" @click="loadSnapshots">
          {{ loadingSnaps ? '加载中…' : '加载快照数据' }}
        </button>
      </div>

      <!-- Comparison table -->
      <div class="section" v-if="Object.keys(snapA).length > 0 || Object.keys(snapB).length > 0">
        <div class="section-title">快照对比</div>
        <table class="data-table snapshot-table">
          <thead>
            <tr>
              <th>指标</th>
              <th class="col-a-val">{{ snapA.snapshot_label || '时间点A' }}</th>
              <th class="col-b-val">{{ snapB.snapshot_label || '时间点B' }}</th>
              <th>差值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in metricRows" :key="m.key">
              <td class="metric-name">{{ m.label }}</td>
              <td class="col-a-val">{{ fmt(snapA[m.key]) }}</td>
              <td class="col-b-val">{{ fmt(snapB[m.key]) }}</td>
              <td>
                <template v-if="typeof snapA[m.key] === 'number' && typeof snapB[m.key] === 'number'">
                  <span :class="{ 'delta-pos': snapB[m.key] - snapA[m.key] > 0, 'delta-neg': snapB[m.key] - snapA[m.key] < 0 }">
                    {{ snapB[m.key] - snapA[m.key] > 0 ? '+' : '' }}{{ (snapB[m.key] - snapA[m.key]).toLocaleString() }}
                  </span>
                </template>
                <template v-else>-</template>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Diff details for B -->
        <div v-if="Object.keys(diffB).length > 0" class="diff-section">
          <div class="section-title" style="margin-top:16px;">时间点 B 与上一帧 Diff</div>
          <div class="diff-bar">
            <span class="diff-tag added">+ {{ fmt(diffB.added_cells) }} 新增</span>
            <span class="diff-tag changed">~ {{ fmt(diffB.changed_cells) }} 变化</span>
            <span class="diff-tag unchanged">= {{ fmt(diffB.unchanged_cells) }} 不变</span>
            <span class="diff-tag active">{{ fmt(diffB.new_active) }} 新激活</span>
          </div>
        </div>
      </div>

      <div v-else-if="!loadingSnaps" class="empty-state">
        选择时间点后点击「加载快照数据」查看对比
      </div>

    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1060px; margin: 0 auto; padding: 24px 16px; }
.full-w { width: 100%; }

.compare-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 8px; }
.compare-col { border-radius: var(--radius-md, 8px); padding: 14px; background: #fafafa; }
.col-a { border: 2px solid #d97706; }
.col-b { border: 2px solid #16a34a; }
.col-header { font-weight: 700; font-size: 13px; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
.col-a .col-header { color: #d97706; }
.col-b .col-header { color: #16a34a; }

.col-a-val { background: #fffbeb; text-align: right; }
.col-b-val { background: #f0fdf4; text-align: right; }
.metric-name { font-size: 13px; }
.snapshot-table th { font-size: 12px; letter-spacing: 0.03em; }

.delta-pos { color: #16a34a; font-weight: 600; }
.delta-neg { color: #dc2626; font-weight: 600; }

.diff-bar { display: flex; gap: 12px; flex-wrap: wrap; }
.diff-tag { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: 600; }
.diff-tag.added     { background: #dcfce7; color: #16a34a; }
.diff-tag.changed   { background: #fef3c7; color: #d97706; }
.diff-tag.unchanged { background: #f3f4f6; color: #6b7280; }
.diff-tag.active    { background: #dbeafe; color: #2563eb; }
</style>
