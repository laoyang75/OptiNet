<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getObjects, getObjectsSummary } from '../lib/api'
import LifecycleBadge from '../components/LifecycleBadge.vue'
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue'

const router = useRouter()

const activeType = ref<'cell' | 'bs' | 'lac'>('cell')
const filters = reactive({
  search: '',
  lifecycle: '',
  anchorable: '',
  position_grade: '',
  drift_pattern: '',
  cell_scale: '',
})

const summary = reactive({ total: 0, active: 0, observing: 0, waiting: 0, anchorable: 0, good_position: 0 })
const rows = ref<any[]>([])
const page = ref(1)
const pageSize = 20
const totalCount = ref(0)
const loading = ref(false)

async function fetchSummary() {
  try {
    const res = await getObjectsSummary(activeType.value)
    Object.assign(summary, res.data)
  } catch { /* tolerate */ }
}

async function fetchObjects() {
  loading.value = true
  try {
    const q: Record<string, any> = {
      type: activeType.value,
      page: page.value,
      size: pageSize,
    }
    if (filters.search) q.q = filters.search
    if (filters.lifecycle) q.lifecycle = filters.lifecycle
    if (filters.anchorable) q.anchorable = filters.anchorable
    if (filters.position_grade) q.position_grade = filters.position_grade
    if (filters.drift_pattern) q.drift_pattern = filters.drift_pattern
    if (filters.cell_scale) q.cell_scale = filters.cell_scale
    const res = await getObjects(q)
    rows.value = res.data ?? []
    totalCount.value = res.context?.total ?? rows.value.length
  } catch { rows.value = [] }
  loading.value = false
}

function switchType(t: 'cell' | 'bs' | 'lac') {
  activeType.value = t
  page.value = 1
}

function goDetail(row: any) {
  const pk = activeType.value === 'cell' ? row.cell_id : activeType.value === 'bs' ? row.bs_id : row.lac
  router.push(`/objects/${activeType.value}/${pk}`)
}

function prevPage() { if (page.value > 1) page.value-- }
function nextPage() { if (page.value * pageSize < totalCount.value) page.value++ }
function resetFilters() {
  filters.search = ''; filters.lifecycle = ''; filters.anchorable = ''
  filters.position_grade = ''; filters.drift_pattern = ''; filters.cell_scale = ''
  page.value = 1
}

watch([activeType, page], () => { fetchSummary(); fetchObjects() })
watch(filters, () => { page.value = 1; fetchObjects() })
onMounted(() => { fetchSummary(); fetchObjects() })

const lifecycleOptions = [
  { value: '', label: '全部' },
  { value: 'waiting', label: '等待' },
  { value: 'observing', label: '观察' },
  { value: 'active', label: '活跃' },
]
const anchorableOptions = [
  { value: '', label: '全部' },
  { value: 'true', label: '可锚定' },
  { value: 'false', label: '不可锚定' },
]
const gradeOptions = [
  { value: '', label: '全部' },
  { value: 'excellent', label: '优秀' },
  { value: 'good', label: '良好' },
  { value: 'qualified', label: '合格' },
  { value: 'unqualified', label: '不合格' },
]
const driftOptions = [
  { value: '', label: '全部' },
  { value: 'stable', label: '稳定' },
  { value: 'moderate_drift', label: '中等漂移' },
  { value: 'collision', label: '碰撞' },
  { value: 'migration', label: '迁移' },
  { value: 'large_coverage', label: '大覆盖' },
  { value: 'insufficient', label: '数据不足' },
]

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}

const driftLabel: Record<string, string> = {
  stable: '稳定', collision: '碰撞', migration: '搬迁',
  large_coverage: '大覆盖', moderate_drift: '中度漂移', insufficient: '数据不足',
}
const gradeLabel: Record<string, string> = {
  excellent: '优秀', good: '良好', qualified: '合格', unqualified: '不合格',
}
</script>

<template>
  <div class="objects-page">
    <!-- Type Tabs -->
    <div class="type-tabs">
      <button v-for="t in (['cell', 'bs', 'lac'] as const)" :key="t"
        class="type-tab" :class="{ active: activeType === t }"
        @click="switchType(t)">{{ t.toUpperCase() }}</button>
    </div>

    <!-- Summary Bar -->
    <div class="summary-bar">
      <MetricCardWithDelta label="总数" :value="summary.total" />
      <MetricCardWithDelta label="活跃" :value="summary.active" />
      <MetricCardWithDelta label="观察中" :value="summary.observing" />
      <MetricCardWithDelta label="等待中" :value="summary.waiting" />
      <MetricCardWithDelta label="锚点可用" :value="summary.anchorable" />
      <MetricCardWithDelta label="定位良好" :value="summary.good_position" />
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <input v-model="filters.search" class="filter-input" placeholder="搜索 ID..." />
      <select v-model="filters.lifecycle" class="filter-select">
        <option v-for="o in lifecycleOptions" :key="o.value" :value="o.value">
          {{ o.value ? o.label : '生命周期' }}
        </option>
      </select>
      <select v-model="filters.anchorable" class="filter-select">
        <option v-for="o in anchorableOptions" :key="o.value" :value="o.value">
          {{ o.value ? o.label : '锚点资格' }}
        </option>
      </select>
      <select v-model="filters.position_grade" class="filter-select">
        <option v-for="o in gradeOptions" :key="o.value" :value="o.value">
          {{ o.value ? o.label : '定位等级' }}
        </option>
      </select>
      <select v-if="activeType === 'cell'" v-model="filters.drift_pattern" class="filter-select">
        <option v-for="o in driftOptions" :key="o.value" :value="o.value">
          {{ o.value ? o.label : '漂移模式' }}
        </option>
      </select>
      <button class="filter-btn" @click="resetFilters">重置</button>
    </div>

    <!-- Data Table -->
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>生命周期</th>
            <th>锚点</th>
            <th>定位等级</th>
            <th v-if="activeType === 'cell'">漂移</th>
            <th>记录数</th>
            <th v-if="activeType !== 'lac'">设备数</th>
            <th>活跃天数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td :colspan="activeType === 'cell' ? 8 : 7" class="center">加载中…</td></tr>
          <tr v-else-if="rows.length === 0"><td :colspan="activeType === 'cell' ? 8 : 7" class="center">暂无数据</td></tr>
          <tr v-for="row in rows" :key="row.cell_id || row.bs_id || row.lac"
            class="data-row" @click="goDetail(row)">
            <td class="key-cell">{{ row.cell_id || row.bs_id || row.lac }}</td>
            <td><LifecycleBadge :state="row.lifecycle_state" /></td>
            <td>{{ row.anchorable ? '✓' : '—' }}</td>
            <td>{{ gradeLabel[row.position_grade] || row.position_grade || '-' }}</td>
            <td v-if="activeType === 'cell'">{{ driftLabel[row.drift_pattern] || row.drift_pattern || '-' }}</td>
            <td>{{ fmt(row.record_count) }}</td>
            <td v-if="activeType !== 'lac'">{{ fmt(row.distinct_dev_id || row.total_devices) }}</td>
            <td>{{ fmt(row.active_days) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="pagination">
      <button class="page-btn" :disabled="page <= 1" @click="prevPage">上一页</button>
      <span class="page-info">共 {{ fmt(totalCount) }} 条，第 {{ page }}/{{ Math.max(1, Math.ceil(totalCount / pageSize)) }} 页</span>
      <button class="page-btn" :disabled="page * pageSize >= totalCount" @click="nextPage">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.objects-page { padding: 24px; max-width: 1200px; margin: 0 auto; }

.type-tabs { display: flex; gap: 4px; margin-bottom: 16px; }
.type-tab { padding: 6px 20px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); background: var(--gray-50); font-size: 13px; font-weight: 500; cursor: pointer; }
.type-tab.active { background: var(--primary-50); color: var(--primary-600); border-color: var(--primary-300); }

.summary-bar { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }

.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-input { flex: 1; min-width: 160px; padding: 6px 10px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); font-size: 13px; }
.filter-select { padding: 6px 10px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); font-size: 13px; background: white; }
.filter-btn { padding: 6px 14px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); font-size: 13px; background: white; cursor: pointer; }
.filter-btn:hover { background: var(--gray-50); }

.table-wrap { overflow-x: auto; margin-bottom: 16px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 8px 12px; background: var(--gray-50); border-bottom: 2px solid var(--gray-200); font-weight: 600; font-size: 12px; color: var(--gray-500); }
.data-table td { padding: 8px 12px; border-bottom: 1px solid var(--gray-100); }
.data-row { cursor: pointer; transition: background 0.15s; }
.data-row:hover { background: var(--gray-50); }
.key-cell { font-weight: 500; font-family: var(--font-mono, monospace); }
.center { text-align: center; color: var(--gray-400); padding: 24px 12px; }

.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; }
.page-btn { padding: 6px 16px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); background: white; font-size: 13px; cursor: pointer; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--gray-500); }
</style>
