<script setup lang="ts">
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { getObservationWorkspace } from '../lib/api'
import LifecycleBadge from '../components/LifecycleBadge.vue'
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue'

const activeTab = ref<'waiting' | 'observing' | 'all'>('all')
const filters = reactive({ sort: 'anchorable_desc' })
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const items = ref<any[]>([])
const summary = reactive({ waiting: 0, observing: 0, active: 0, anchorable: 0 })
const signals = ref<Record<string, any>>({})
const totalCount = ref(0)

async function fetchData() {
  loading.value = true
  try {
    const q: Record<string, any> = { page: page.value, size: pageSize, sort: filters.sort }
    if (activeTab.value !== 'all') q.lifecycle = activeTab.value
    const res = await getObservationWorkspace(q)
    items.value = res.data?.items ?? []
    totalCount.value = res.data?.total ?? items.value.length
    if (res.data?.summary) Object.assign(summary, res.data.summary)
    signals.value = res.data?.observation_signals || {}
  } catch { items.value = [] }
  loading.value = false
}

const tabCounts = computed(() => ({
  waiting: summary.waiting,
  observing: summary.observing,
  all: summary.waiting + summary.observing,
}))

function switchTab(t: 'waiting' | 'observing' | 'all') {
  activeTab.value = t
  page.value = 1
}

function prevPage() { if (page.value > 1) page.value-- }
function nextPage() { if (page.value * pageSize < totalCount.value) page.value++ }

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}

function fmtM(n: any) {
  if (typeof n !== 'number') return '-'
  return n < 1 ? '< 1m' : Math.round(n) + 'm'
}

watch([activeTab, page], fetchData)
watch(filters, () => { page.value = 1; fetchData() })
onMounted(fetchData)

const driftLabel: Record<string, string> = {
  stable: '稳定', collision: '碰撞', migration: '搬迁',
  large_coverage: '大覆盖', moderate_drift: '中度漂移', insufficient: '数据不足',
}
const gradeLabel: Record<string, string> = {
  excellent: '优秀', good: '良好', qualified: '合格', unqualified: '不合格',
}
const lifecycleLabel: Record<string, string> = {
  active: '活跃', observing: '观察中', waiting: '等待中',
}

const sortOptions = [
  { value: 'anchorable_desc', label: '按锚点资格排序' },
  { value: 'obs_desc',        label: '按观测量排序' },
  { value: 'active_days_desc', label: '按活跃天数排序' },
]
</script>

<template>
  <div class="obs-page">
    <!-- Summary Bar -->
    <div class="summary-bar">
      <MetricCardWithDelta label="等待中" :value="summary.waiting" />
      <MetricCardWithDelta label="观察中" :value="summary.observing" />
      <MetricCardWithDelta label="已激活" :value="summary.active" />
      <MetricCardWithDelta label="锚点可用" :value="summary.anchorable" />
    </div>

    <!-- Observation signals -->
    <div v-if="Object.keys(signals).length > 0" class="signals-bar">
      <span class="signal-tag" v-if="signals.new_observing">{{ signals.new_observing }} 新进入观察</span>
      <span class="signal-tag promoted" v-if="signals.promoted_to_active">{{ signals.promoted_to_active }} 晋升为活跃</span>
      <span class="signal-tag shifted" v-if="signals.large_shift_cells">{{ signals.large_shift_cells }} 大位移</span>
      <span class="signal-tag" v-if="signals.anchorable_changed">{{ signals.anchorable_changed }} 锚点变化</span>
    </div>

    <!-- Tab Switch -->
    <div class="tab-row">
      <button v-for="t in (['waiting', 'observing', 'all'] as const)" :key="t"
        class="tab-btn" :class="{ active: activeTab === t }"
        @click="switchTab(t)">
        {{ t === 'waiting' ? '等待中' : t === 'observing' ? '观察中' : '全部' }}
        <span class="count-pill">{{ tabCounts[t] }}</span>
      </button>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <select v-model="filters.sort" class="filter-select">
        <option v-for="o in sortOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </div>

    <!-- Card Grid -->
    <div v-if="loading" class="center">加载中…</div>
    <div v-else-if="items.length === 0" class="center">暂无数据</div>
    <div v-else class="card-grid">
      <div v-for="item in items" :key="item.cell_id" class="obs-card">
        <div class="card-header">
          <span class="card-id">{{ item.cell_id }}</span>
          <LifecycleBadge :state="item.lifecycle_state" />
        </div>

        <!-- 3-layer qualification progress -->
        <div class="qual-layers">
          <div class="qual-layer" :class="item.independent_obs >= 3 && item.distinct_dev_id >= 2 ? 'layer-met' : 'layer-locked'">
            <span class="layer-label">存在资格</span>
            <span class="layer-val">{{ item.independent_obs }} 观测 / {{ item.distinct_dev_id }} 设备</span>
          </div>
          <div class="qual-layer" :class="item.anchorable ? 'layer-met' : 'layer-locked'">
            <span class="layer-label">锚点资格</span>
            <span class="layer-val">{{ item.anchorable ? '已达标' : '未达标' }}</span>
          </div>
          <div class="qual-layer" :class="item.lifecycle_state === 'active' ? 'layer-met' : 'layer-locked'">
            <span class="layer-label">激活状态</span>
            <span class="layer-val">{{ lifecycleLabel[item.lifecycle_state] || item.lifecycle_state }}</span>
          </div>
        </div>

        <div class="card-footer">
          <span class="footer-item">P90: {{ fmtM(item.p90_radius_m) }}</span>
          <span class="footer-item">定位: {{ gradeLabel[item.position_grade] || item.position_grade || '-' }}</span>
          <span class="footer-item">漂移: {{ driftLabel[item.drift_pattern] || item.drift_pattern || '-' }}</span>
        </div>
        <div class="card-footer">
          <span class="footer-item">BS: {{ item.bs_id || '-' }}</span>
          <span class="footer-item">LAC: {{ item.lac || '-' }}</span>
          <span class="footer-item">跨度: {{ item.observed_span_hours ? Math.round(item.observed_span_hours) + 'h' : '-' }}</span>
        </div>
      </div>
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
.obs-page { padding: 24px; max-width: 1200px; margin: 0 auto; }

.summary-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }

.signals-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.signal-tag {
  display: inline-block; padding: 4px 12px; border-radius: 12px;
  font-size: 12px; font-weight: 600; background: #dbeafe; color: #2563eb;
}
.signal-tag.promoted { background: #dcfce7; color: #16a34a; }
.signal-tag.shifted  { background: #fef3c7; color: #d97706; }

.tab-row { display: flex; gap: 4px; margin-bottom: 16px; }
.tab-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 16px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); background: var(--gray-50); font-size: 13px; font-weight: 500; cursor: pointer; }
.tab-btn.active { background: var(--primary-50); color: var(--primary-600); border-color: var(--primary-300); }
.count-pill { display: inline-block; padding: 0 6px; border-radius: 8px; font-size: 11px; font-weight: 600; background: var(--gray-200); color: var(--gray-600); }
.tab-btn.active .count-pill { background: var(--primary-200); color: var(--primary-700); }

.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-select { padding: 6px 10px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); font-size: 13px; background: white; }

.center { text-align: center; color: var(--gray-400); padding: 48px; }

.card-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }

.obs-card { border: 1px solid var(--gray-200); border-radius: var(--radius-sm); padding: 16px; background: white; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-id { font-weight: 600; font-family: var(--font-mono, monospace); font-size: 13px; }

.qual-layers { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.qual-layer { display: flex; align-items: center; gap: 8px; }
.layer-label { font-size: 11px; font-weight: 500; min-width: 60px; color: var(--gray-600); }
.layer-val { font-size: 12px; color: var(--gray-700); }
.layer-met { border-left: 3px solid var(--green-500); padding-left: 8px; }
.layer-locked { border-left: 3px dashed var(--gray-300); padding-left: 8px; opacity: 0.6; }

.card-footer { display: flex; gap: 16px; font-size: 11px; color: var(--gray-400); margin-bottom: 2px; }
.footer-item { white-space: nowrap; }

.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px; }
.page-btn { padding: 6px 16px; border: 1px solid var(--gray-200); border-radius: var(--radius-sm); background: white; font-size: 13px; cursor: pointer; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--gray-500); }
</style>
