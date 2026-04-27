<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import {
  getDeviceWeightedP90,
  getMaintenanceCells,
  getMaintenanceStats,
  runMaintenance,
  type DeviceWeightedP90Payload,
  type MaintenanceCellItem,
  type MaintenanceStatsPayload,
} from '../../api/maintenance'
// 注：p90_radius_m 现在是方案 B（MAD + 设备-天去重）输出，在列表中以"质心覆盖"展示
import { fmt, pct } from '../../composables/useFormat'
import { DRIFT_LABELS, type DriftPattern } from '../../types'

// 来源 antitoxin_params.yaml: drift.insufficient_min_days
const INSUFFICIENT_MIN_DAYS = 2
type CurrentDriftPattern = Exclude<DriftPattern, 'moderate_drift'>

// 新分类顺序（正常 → 覆盖大 → 双质心 → 迁移 → 碰撞 → 动态 → 多质心 → 单簇超大 → 证据不足）
const driftKeys: CurrentDriftPattern[] = [
  'stable', 'large_coverage', 'dual_cluster', 'migration',
  'collision', 'dynamic', 'uncertain', 'oversize_single', 'insufficient',
]
type FilterKind = 'all' | 'anomaly' | DriftPattern | 'multi_centroid' | 'has_ta' | 'ta_reliable'
const selectedKind = ref<FilterKind>('all')
const cells = ref<MaintenanceCellItem[]>([])
const expandedIdx = ref<number | null>(null)
const activeDetailTab = ref<'overview' | 'weighted-p90'>('overview')
const page = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const totalPages = ref(0)
const running = ref(false)
const taRangeMin = ref(0)
const taRangeMax = ref(1300)
const freqBandFilter = ref('all')
const taVerificationFilters = ref<string[]>([])
const timingAdvanceFilter = ref<'all' | 'has' | 'none'>('all')
const weightedP90ByCell = ref<Record<string, DeviceWeightedP90Payload | null>>({})
const weightedP90Loading = ref<Record<string, boolean>>({})
const stats = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0, published_bs_count: 0, published_lac_count: 0,
    collision_cell_count: 0, multi_centroid_cell_count: 0, dynamic_cell_count: 0, anomaly_bs_count: 0,
  },
  drift_distribution: {},
})

const driftDist = computed<Record<CurrentDriftPattern, number>>(() => ({
  stable: Number(stats.value.drift_distribution.stable ?? 0),
  large_coverage: Number(stats.value.drift_distribution.large_coverage ?? 0),
  dual_cluster: Number((stats.value.drift_distribution as any).dual_cluster ?? 0),
  migration: Number(stats.value.drift_distribution.migration ?? 0),
  collision: Number(stats.value.drift_distribution.collision ?? 0),
  dynamic: Number((stats.value.drift_distribution as any).dynamic ?? 0),
  uncertain: Number((stats.value.drift_distribution as any).uncertain ?? 0),
  oversize_single: Number((stats.value.drift_distribution as any).oversize_single ?? 0),
  insufficient: Number(stats.value.drift_distribution.insufficient ?? 0),
}))
const driftTotal = computed(() => Object.values(driftDist.value).reduce((s, v) => s + v, 0))
function segW(n: number) { return `${driftTotal.value > 0 ? (n / driftTotal.value) * 100 : 0}%` }

const gradeCfg: Record<string, { label: string; cls: string }> = {
  excellent: { label: '优秀', cls: 'grade-excellent' },
  good: { label: '良好', cls: 'grade-good' },
  qualified: { label: '合格', cls: 'grade-qualified' },
  unqualified: { label: '不合格', cls: 'grade-unqualified' },
}
const scaleCfg: Record<string, { label: string; cls: string }> = {
  major: { label: '主力', cls: 'scale-major' },
  large: { label: '大型', cls: 'scale-large' },
  medium: { label: '中型', cls: 'scale-medium' },
  small: { label: '小型', cls: 'scale-small' },
  micro: { label: '微型', cls: 'scale-micro' },
}

const filterKinds = [
  { key: 'all', label: '全量' },
  { key: 'stable', label: '正常' },
  { key: 'large_coverage', label: '覆盖大' },
  { key: 'dual_cluster', label: '双质心' },
  { key: 'migration', label: '迁移' },
  { key: 'collision', label: '碰撞' },
  { key: 'dynamic', label: '动态' },
  { key: 'uncertain', label: '多质心' },
  { key: 'oversize_single', label: '单簇超大' },
  { key: 'insufficient', label: '证据不足' },
  { key: 'anomaly', label: '全部异常' },
  { key: 'has_ta', label: '有 TA' },
  { key: 'ta_reliable', label: 'TA 可信 (n≥10)' },
]

const taVerificationOptions = [
  { key: 'verified', label: 'verified' },
  { key: 'disputed', label: 'disputed' },
  { key: 'unverified', label: 'unverified' },
]

function taVerificationGroup(v: string | null | undefined): string {
  if (v === 'ok') return 'verified'
  if (v === 'large' || v === 'xlarge') return 'disputed'
  return 'unverified'
}

const filteredCells = computed(() => cells.value.filter(item => {
  const taDist = item.ta_dist_p90_m
  if (taDist != null && (taDist < taRangeMin.value || taDist > taRangeMax.value)) return false
  if (taDist == null && (taRangeMin.value > 0 || taRangeMax.value < 1300)) return false
  if (freqBandFilter.value !== 'all') {
    if (freqBandFilter.value === 'unknown') {
      if (item.freq_band) return false
    } else if ((item.freq_band || '').toLowerCase() !== freqBandFilter.value) return false
  }
  if (taVerificationFilters.value.length > 0 && !taVerificationFilters.value.includes(taVerificationGroup(item.ta_verification))) return false
  if (timingAdvanceFilter.value === 'has' && (item.ta_n_obs ?? 0) <= 0) return false
  if (timingAdvanceFilter.value === 'none' && (item.ta_n_obs ?? 0) > 0) return false
  return true
}))

function densityLabel(days: number): { label: string; style: string } {
  if (days >= 20) return { label: '高密度', style: 'background:#fee2e2;color:#991b1b' }
  if (days >= 10) return { label: '中密度', style: 'background:#fef3c7;color:#92400e' }
  return { label: '低密度', style: 'background:#f3f4f6;color:#6b7280' }
}

// ==================== TA 覆盖评估辅助 ====================
// 源：trusted_cell_library.ta_verification（maintenance/publish_cell.py 判定）
const TA_VERIFY_LABEL: Record<string, string> = {
  ok: 'ok',
  insufficient: '样本不足',
  xlarge: '超大覆盖',
  large: '大覆盖',
  not_checked: '未校验',
  not_applicable: '不适用',
}
const TA_VERIFY_HINT: Record<string, string> = {
  ok: 'TA 估距与 lib p90 在合理区间',
  insufficient: '有效 TA 样本不足，估距不可信',
  xlarge: 'TA 估距 > 2.3 km，疑似或合法郊区大 cell',
  large: 'TA 估距 1.5–2.3 km，边界情况',
  not_checked: 'TDD 或频段未知，跳过校验',
  not_applicable: 'multi_centroid / collision cell，不参与 TA 校验',
}
function taVerifyLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return TA_VERIFY_LABEL[v] ?? v
}
function taVerifyHint(v: string | null | undefined): string {
  if (!v) return ''
  return TA_VERIFY_HINT[v] ?? ''
}
function freqBandLabel(v: string | null | undefined): string {
  if (!v) return '-'
  if (v === 'fdd') return 'FDD'
  if (v === 'tdd') return 'TDD'
  return v
}
/** lib p90 ÷ TA 估距 */
function taRatio(item: MaintenanceCellItem): number | null {
  const lib = item.p90_radius_m
  const ta = item.ta_dist_p90_m
  if (lib == null || ta == null || !ta) return null
  if ((item.ta_n_obs ?? 0) < 10) return null  // 样本过少不做比率
  return lib / ta
}
function ratioClass(r: number | null): string {
  if (r == null) return ''
  if (r >= 5) return 'ratio-danger'      // lib 远大于 TA → GPS 漂移污染嫌疑
  if (r <= 0.3) return 'ratio-warn'      // lib 远小于 TA → stable 但 TA 说大，漏判嫌疑
  return 'ratio-ok'
}
function ratioHint(r: number | null): string {
  if (r == null) return ''
  if (r >= 5) return 'lib >> TA，GPS 漂移污染嫌疑'
  if (r <= 0.3) return 'lib << TA，stable 漏判嫌疑'
  if (r >= 2) return 'lib 偏大，边界样本'
  if (r <= 0.5) return 'lib 偏小'
  return '吻合'
}
const P90_HARD_THRESHOLD_M = 1300  // antitoxin_params.yaml::multi_centroid_entry_p90_m
function p90Over1300(item: MaintenanceCellItem): boolean {
  return (item.p90_radius_m ?? 0) >= P90_HARD_THRESHOLD_M
}
function taOver1300(item: MaintenanceCellItem): boolean {
  return (item.ta_dist_p90_m ?? 0) >= P90_HARD_THRESHOLD_M
}
function taOver1300Label(item: MaintenanceCellItem): string {
  if (item.ta_dist_p90_m == null) return '无数据'
  return taOver1300(item) ? '≥1300m' : '<1300m'
}
/** 返回不一致说明，若一致返回空字符串 */
function thresholdConflict(item: MaintenanceCellItem): string {
  if (item.ta_dist_p90_m == null || (item.ta_n_obs ?? 0) < 10) return ''
  const libOver = p90Over1300(item)
  const taOver = taOver1300(item)
  if (libOver === taOver) return ''
  if (libOver && !taOver) return 'lib 超限但 TA 说小，漂移嫌疑'
  return 'lib 未超但 TA 说大，漏判嫌疑'
}

function fmtTime(v: string | null): string {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 19)
}

function tag(cfg: Record<string, { label: string; cls: string }>, key: string | null) {
  return cfg[key || ''] || { label: key || '-', cls: '' }
}

/** 按"合理精度范围"给质心覆盖上色（见 06_k_mad 报告 §9.5）*/
function coverageClass(p90: number | null | undefined): string {
  if (p90 == null) return ''
  if (p90 <= 200) return 'cov-excellent'      // 优秀
  if (p90 <= 500) return 'cov-good'           // 良好
  if (p90 <= 800) return 'cov-acceptable'     // 可接受
  return 'cov-large'                          // 偏大（将进入多质心深度分析）
}

function detailKey(item: MaintenanceCellItem): string {
  return `${item.operator_code}-${item.lac}-${item.cell_id}-${item.tech_norm || ''}`
}

function maskDevId(v: string | null | undefined): string {
  if (!v) return '-'
  if (v.length <= 8) return v
  return `${v.slice(0, 4)}...${v.slice(-4)}`
}

function toggle(idx: number) {
  expandedIdx.value = expandedIdx.value === idx ? null : idx
  activeDetailTab.value = 'overview'
}

async function openWeightedP90(item: MaintenanceCellItem) {
  activeDetailTab.value = 'weighted-p90'
  const key = detailKey(item)
  if (weightedP90ByCell.value[key] !== undefined || weightedP90Loading.value[key]) return
  weightedP90Loading.value = { ...weightedP90Loading.value, [key]: true }
  try {
    const payload = await getDeviceWeightedP90(item.cell_id)
    weightedP90ByCell.value = { ...weightedP90ByCell.value, [key]: payload }
  } catch {
    weightedP90ByCell.value = { ...weightedP90ByCell.value, [key]: null }
  } finally {
    weightedP90Loading.value = { ...weightedP90Loading.value, [key]: false }
  }
}

async function loadCells(kind = selectedKind.value) {
  selectedKind.value = kind
  expandedIdx.value = null
  try {
    const payload = await getMaintenanceCells(kind, page.value, pageSize.value)
    cells.value = payload.items
    totalCount.value = payload.totalCount
    totalPages.value = payload.totalPages
  } catch { cells.value = [] }
}

function switchKind(kind: typeof selectedKind.value) { page.value = 1; loadCells(kind) }
watch(page, () => loadCells())

async function doRun() {
  running.value = true
  try {
    await runMaintenance()
    stats.value = await getMaintenanceStats()
    await loadCells()
  } catch { /* */ }
  finally { running.value = false }
}

onMounted(async () => {
  try { stats.value = await getMaintenanceStats() } catch { /* */ }
  await loadCells('all')
})
</script>

<template>
  <PageHeader title="Cell 画像维护" description="基于 raw_gps + DBSCAN 多质心聚类的 cell 分类。点击行展开详情。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} ｜ {{ stats.version.snapshot_version_prev }} → {{ stats.version.snapshot_version }}
      <button class="btn btn-sm ml-md" :disabled="running" @click="doRun">{{ running ? '运行中...' : '运行 Step 5' }}</button>
    </div>
  </PageHeader>

  <!-- Summary cards：按新标签体系（9 标签 + 总数，与 drift_pattern 完全对齐）-->
  <div class="grid grid-10 mb-lg">
    <SummaryCard title="总数" :value="fmt(stats.summary.published_cell_count)" />
    <SummaryCard title="正常" :value="fmt(driftDist.stable)" color="var(--c-success)" />
    <SummaryCard title="覆盖大" :value="fmt(driftDist.large_coverage)" color="#d97706" />
    <SummaryCard title="双质心" :value="fmt(driftDist.dual_cluster)" color="#0891b2" />
    <SummaryCard title="迁移" :value="fmt(driftDist.migration)" color="#7c3aed" />
    <SummaryCard title="碰撞" :value="fmt(driftDist.collision)" color="var(--c-danger)" />
    <SummaryCard title="动态" :value="fmt(driftDist.dynamic)" color="#db2777" />
    <SummaryCard title="多质心" :value="fmt(driftDist.uncertain)" color="#f59e0b" />
    <SummaryCard title="单簇超大" :value="fmt(driftDist.oversize_single)" color="#991b1b" />
    <SummaryCard title="证据不足" :value="fmt(driftDist.insufficient)" />
  </div>

  <!-- 分类分布 bar -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">分类分布</div>
    <div class="drift-bar">
      <div v-for="p in driftKeys" :key="p" class="drift-seg" :class="`drift-${p}`" :style="{ width: segW(driftDist[p]) }" :title="`${DRIFT_LABELS[p]}: ${driftDist[p]}`"></div>
    </div>
    <div class="flex flex-wrap gap-lg mt-md text-xs">
      <span v-for="p in driftKeys" :key="p" class="flex items-center gap-xs">
        <span class="dot" :class="`bg-${p}`"></span>
        {{ DRIFT_LABELS[p] }} {{ fmt(driftDist[p]) }}
      </span>
    </div>
  </div>

  <!-- Filter + table -->
  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center wrap-row gap-sm">
      <span class="font-semibold text-sm">Cell 画像列表 · {{ fmt(totalCount) }} 条</span>
      <div class="flex gap-sm wrap-row">
        <button v-for="k in filterKinds" :key="k.key"
          class="btn" :class="{ 'btn-primary': selectedKind === k.key }" @click="switchKind(k.key as any)">
          {{ k.label }}
        </button>
      </div>
    </div>
    <div class="ta-filter-panel">
      <div class="ta-filter-head">
        <span class="font-semibold text-xs">TA 筛选</span>
        <span class="text-xs text-secondary">当前页命中 {{ fmt(filteredCells.length) }} / {{ fmt(cells.length) }}</span>
      </div>
      <div class="ta-filter-grid">
        <label class="filter-field">
          <span>TA 估距区间</span>
          <div class="range-row">
            <input v-model.number="taRangeMin" type="range" min="0" max="1300" step="50">
            <input v-model.number="taRangeMax" type="range" min="0" max="1300" step="50">
            <strong class="font-mono">{{ taRangeMin }}-{{ taRangeMax }}m</strong>
          </div>
        </label>
        <label class="filter-field">
          <span>freq_band</span>
          <select v-model="freqBandFilter">
            <option value="all">全部</option>
            <option value="fdd">FDD</option>
            <option value="tdd">TDD</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <div class="filter-field">
          <span>ta_verification</span>
          <div class="check-row">
            <label v-for="opt in taVerificationOptions" :key="opt.key">
              <input v-model="taVerificationFilters" type="checkbox" :value="opt.key">
              {{ opt.label }}
            </label>
          </div>
        </div>
        <label class="filter-field">
          <span>timing_advance</span>
          <select v-model="timingAdvanceFilter">
            <option value="all">全部</option>
            <option value="has">有值</option>
            <option value="none">无值</option>
          </select>
        </label>
      </div>
    </div>

    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th style="width:20px"></th>
          <th>运营商</th><th>制式</th><th>LAC</th><th>BS</th><th>Cell ID</th>
          <th>质量</th><th>规模</th><th>分类</th>
          <th>独立观测</th><th title="方案 B（MAD + 设备-天去重）后计算的 p90 覆盖半径">质心覆盖(m)</th>
          <th title="基于 timing_advance p90 估算的覆盖距离（m），下标 n=有效 TA 数">TA 估距(m)</th><th>位置</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(item, idx) in filteredCells" :key="`${item.operator_code}-${item.lac}-${item.cell_id}-${item.tech_norm || ''}`">
          <tr class="clickable-row" :class="{ 'antitoxin-row': item.antitoxin_hit }" @click="toggle(idx)">
            <td class="expand-icon">{{ expandedIdx === idx ? '▾' : '▸' }}</td>
            <td class="text-xs">{{ item.operator_cn || item.operator_code }}</td>
            <td><span class="tag" :style="item.tech_norm === '5G' ? 'background:#ede9fe;color:#6d28d9' : 'background:#e0f2fe;color:#075985'">{{ item.tech_norm || '-' }}</span></td>
            <td class="font-mono">{{ item.lac }}</td>
            <td class="font-mono text-xs">{{ item.bs_id }}</td>
            <td class="font-mono font-semibold">{{ item.cell_id }}</td>
            <td><span class="tag" :class="tag(gradeCfg, item.position_grade).cls">{{ tag(gradeCfg, item.position_grade).label }}</span></td>
            <td><span class="tag" :class="tag(scaleCfg, item.cell_scale).cls">{{ tag(scaleCfg, item.cell_scale).label }}</span></td>
            <td><span v-if="item.drift_pattern" class="tag" :class="`drift-tag-${item.drift_pattern}`">{{ DRIFT_LABELS[item.drift_pattern as DriftPattern] ?? item.drift_pattern }}</span><span v-else class="text-muted">-</span></td>
            <td class="font-mono">{{ item.independent_obs ?? '-' }}</td>
            <td class="font-mono coverage-cell" :class="coverageClass(item.p90_radius_m)">{{ item.p90_radius_m ? Math.round(item.p90_radius_m) : '-' }}</td>
            <td class="ta-cell">
              <div class="ta-dist font-mono">
                <span>{{ item.ta_dist_p90_m != null ? item.ta_dist_p90_m : '-' }}</span>
                <span v-if="item.ta_verification" class="ta-badge" :class="`tv-${item.ta_verification}`">{{ taVerifyLabel(item.ta_verification) }}</span>
              </div>
              <div class="ta-nobs text-xs" :class="{ 'ta-nobs-low': (item.ta_n_obs ?? 0) > 0 && (item.ta_n_obs ?? 0) < 10 }">
                n={{ item.ta_n_obs ?? 0 }}
              </div>
            </td>
            <td class="text-xs loc-td">{{ (item as any).district_name || (item as any).city_name || '-' }}</td>
          </tr>
          <!-- Expanded detail -->
          <tr v-if="expandedIdx === idx" class="detail-row">
            <td :colspan="13">
              <div class="detail-content">
                <div class="detail-tabs">
                  <button class="tab-btn" :class="{ active: activeDetailTab === 'overview' }" @click.stop="activeDetailTab = 'overview'">概览</button>
                  <button class="tab-btn" :class="{ active: activeDetailTab === 'weighted-p90' }" @click.stop="openWeightedP90(item)">加权 P90</button>
                </div>
                <template v-if="activeDetailTab === 'overview'">
                <div class="detail-section">
                  <div class="section-title">空间 · 质心覆盖（方案 B：MAD + 设备-天去重）</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">质心坐标</span><span class="dv font-mono">{{ item.center_lon ? `${Number(item.center_lon).toFixed(4)}, ${Number(item.center_lat).toFixed(4)}` : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">覆盖半径 P50 / P90</span><span class="dv">{{ item.p50_radius_m ? Math.round(item.p50_radius_m) : '-' }}m / <strong :class="coverageClass(item.p90_radius_m)">{{ item.p90_radius_m ? Math.round(item.p90_radius_m) : '-' }}m</strong></span></div>
                    <div class="detail-item"><span class="dl">位置质量</span><span class="dv">{{ tag(gradeCfg, item.position_grade).label }}</span></div>
                    <div class="detail-item"><span class="dl">物理位置</span><span class="dv">{{ (item as any).province_name || '' }} {{ (item as any).city_name || '' }} {{ (item as any).district_name || '-' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">漂移分析</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">分类</span><span class="dv" :style="item.is_collision ? 'color:var(--c-danger)' : ''">{{ DRIFT_LABELS[item.drift_pattern as DriftPattern] ?? item.drift_pattern ?? '-' }}</span></div>
                    <div class="detail-item"><span class="dl">碰撞标记</span><span class="dv" :style="item.is_collision ? 'color:var(--c-danger);font-weight:600' : ''">{{ item.is_collision ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">多质心</span><span class="dv">{{ item.is_multi_centroid ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">GPS 异常</span><span class="dv">{{ item.gps_anomaly_type || '无' }}</span></div>
                    <div class="detail-item"><span class="dl">最大离散(m)</span><span class="dv font-mono">{{ item.max_spread_m != null ? Math.round(item.max_spread_m) : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">净漂移(m)</span><span class="dv font-mono">{{ item.net_drift_m != null ? Math.round(item.net_drift_m) : '-' }}</span></div>
                    <div class="detail-item">
                      <span class="dl">漂移比 (0=随机 1=单向)</span>
                      <span class="dv">
                        <span v-if="item.drift_ratio != null" class="drift-ratio-bar">
                          <span class="drift-ratio-fill" :style="{ width: `${(item.drift_ratio * 100)}%` }"></span>
                          <span class="drift-ratio-val font-mono">{{ item.drift_ratio.toFixed(2) }}</span>
                        </span>
                        <span v-else>-</span>
                      </span>
                    </div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">数据质量</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">独立观测点</span><span class="dv">{{ item.independent_obs != null ? fmt(item.independent_obs) : '-' }} ({{ item.distinct_dev_id != null ? fmt(item.distinct_dev_id) : '-' }} 台)</span></div>
                    <div class="detail-item"><span class="dl">滑窗观测量</span><span class="dv">{{ fmt(item.window_obs_count) }}</span></div>
                    <div class="detail-item"><span class="dl">锚点资格</span><span class="dv" :style="item.anchor_eligible ? 'color:var(--c-success)' : ''">{{ item.anchor_eligible ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">基线资格</span><span class="dv" :style="!item.baseline_eligible ? 'color:var(--c-danger)' : ''">{{ item.baseline_eligible ? '是' : '否（被阻断）' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">信号与状态</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">频段</span><span class="dv">{{ freqBandLabel(item.freq_band) }}</span></div>
                    <div class="detail-item"><span class="dl">气压均值</span><span class="dv font-mono">{{ item.pressure_avg != null ? Number(item.pressure_avg).toFixed(1) + ' hPa' : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">防毒化命中</span><span class="dv" :style="item.antitoxin_hit ? 'color:var(--c-danger);font-weight:600' : ''">{{ item.antitoxin_hit ? '是 (阻断)' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">最后观测</span><span class="dv">{{ fmtTime(item.last_observed_at) }}</span></div>
                  </div>
                </div>
                <div class="detail-section ta-section">
                  <div class="section-title">TA 覆盖评估 <span class="section-hint">（用 timing_advance 估算覆盖距离，辅助判定 1300m 硬门槛）</span></div>
                  <div class="detail-grid">
                    <div class="detail-item">
                      <span class="dl">有效 TA 数</span>
                      <span class="dv font-mono" :class="{ 'ta-weak': (item.ta_n_obs ?? 0) > 0 && (item.ta_n_obs ?? 0) < 10, 'ta-none': (item.ta_n_obs ?? 0) === 0 }">
                        <strong>{{ item.ta_n_obs ?? 0 }}</strong>
                        <span v-if="(item.ta_n_obs ?? 0) === 0" class="text-muted ml-sm text-xs">无</span>
                        <span v-else-if="(item.ta_n_obs ?? 0) < 10" class="text-muted ml-sm text-xs">样本偏少</span>
                      </span>
                    </div>
                    <div class="detail-item"><span class="dl">TA P50 / P90</span><span class="dv font-mono">{{ item.ta_p50 ?? '-' }} / {{ item.ta_p90 ?? '-' }}</span></div>
                    <div class="detail-item"><span class="dl">TA 估算距离</span><span class="dv font-mono"><strong>{{ item.ta_dist_p90_m != null ? `${item.ta_dist_p90_m} m` : '-' }}</strong></span></div>
                    <div class="detail-item"><span class="dl">频段</span><span class="dv">{{ freqBandLabel(item.freq_band) }}</span></div>
                    <div class="detail-item">
                      <span class="dl">TA 校验</span>
                      <span class="dv">
                        <span v-if="item.ta_verification" class="tag ta-badge" :class="`tv-${item.ta_verification}`">{{ taVerifyLabel(item.ta_verification) }}</span>
                        <span v-else class="text-muted">-</span>
                        <span v-if="item.ta_verification" class="text-muted ml-sm text-xs">{{ taVerifyHint(item.ta_verification) }}</span>
                      </span>
                    </div>
                    <div class="detail-item">
                      <span class="dl">lib p90 ÷ TA 估距</span>
                      <span class="dv font-mono">
                        <template v-if="taRatio(item) != null">
                          <strong :class="ratioClass(taRatio(item))">{{ taRatio(item)!.toFixed(2) }}×</strong>
                          <span class="text-muted ml-sm text-xs">{{ ratioHint(taRatio(item)) }}</span>
                        </template>
                        <span v-else class="text-muted">缺数据</span>
                      </span>
                    </div>
                    <div class="detail-item" style="grid-column: span 2">
                      <span class="dl">1300m 门槛对照</span>
                      <span class="dv">
                        <span class="tag" :class="p90Over1300(item) ? 'threshold-over' : 'threshold-under'">lib p90: {{ p90Over1300(item) ? '≥1300m（进候选池）' : '<1300m（stable）' }}</span>
                        <span class="tag ml-sm" :class="taOver1300(item) ? 'threshold-over' : 'threshold-under'">TA 估距: {{ taOver1300Label(item) }}</span>
                        <span v-if="thresholdConflict(item)" class="tag ml-sm threshold-conflict">不一致：{{ thresholdConflict(item) }}</span>
                      </span>
                    </div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">生命周期与退出管理</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">生命周期状态</span><span class="dv"><StatusTag :state="item.lifecycle_state as any" size="sm" /></span></div>
                    <div class="detail-item"><span class="dl">30天活跃天数</span><span class="dv font-mono">{{ item.active_days_30d }}</span></div>
                    <div class="detail-item"><span class="dl">连续不活跃天数</span><span class="dv font-mono" :style="item.consecutive_inactive_days > 0 ? 'color:var(--c-dormant)' : ''">{{ item.consecutive_inactive_days }}d</span></div>
                    <div class="detail-item"><span class="dl">密度等级</span><span class="dv"><span class="tag" :style="densityLabel(item.active_days_30d).style">{{ densityLabel(item.active_days_30d).label }}</span></span></div>
                    <div class="detail-item"><span class="dl">窗口观测量</span><span class="dv">{{ fmt(item.window_obs_count) }}</span></div>
                    <div v-if="item.drift_pattern === 'insufficient'" class="detail-item" style="grid-column: span 2">
                      <span class="dl">判定依据</span>
                      <span class="dv" style="color:var(--c-text-muted)">活跃 {{ (item as any).active_days ?? 0 }} 天 &lt; 阈值 {{ INSUFFICIENT_MIN_DAYS }} 天</span>
                    </div>
                  </div>
                </div>
                <!-- Multi-centroid details -->
                <div v-if="(item as any).centroids?.length > 0" class="detail-section">
                  <div class="section-title">多质心簇（{{ (item as any).centroids.length }} 个）</div>
                  <table class="data-table centroid-table">
                    <thead><tr><th>簇 ID</th><th>质心经度</th><th>质心纬度</th><th>观测量</th><th>设备数</th><th>占比</th></tr></thead>
                    <tbody>
                      <tr v-for="c in (item as any).centroids" :key="c.cluster_id">
                        <td class="font-mono">{{ c.cluster_id }}</td>
                        <td class="font-mono">{{ Number(c.center_lon).toFixed(6) }}</td>
                        <td class="font-mono">{{ Number(c.center_lat).toFixed(6) }}</td>
                        <td class="font-mono">{{ c.obs_count }}</td>
                        <td class="font-mono">{{ c.dev_count }}</td>
                        <td class="font-mono">{{ (c.share_ratio * 100).toFixed(0) }}%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                </template>
                <div v-else class="detail-section weighted-section">
                  <div class="section-title">device-weighted p90</div>
                  <template v-if="weightedP90Loading[detailKey(item)]">
                    <div class="text-xs text-secondary">加载中...</div>
                  </template>
                  <template v-else-if="weightedP90ByCell[detailKey(item)]">
                    <div class="p90-compare">
                      <div class="p90-bar-row">
                        <span>无权 P90</span>
                        <div class="p90-track"><div class="p90-fill raw" :style="{ width: `${Math.min(((weightedP90ByCell[detailKey(item)]!.p90_unweighted_m || 0) / Math.max(weightedP90ByCell[detailKey(item)]!.p90_unweighted_m || 0, weightedP90ByCell[detailKey(item)]!.p90_device_weighted_m || 0, 1)) * 100, 100)}%` }"></div></div>
                        <strong class="font-mono">{{ weightedP90ByCell[detailKey(item)]!.p90_unweighted_m != null ? Math.round(weightedP90ByCell[detailKey(item)]!.p90_unweighted_m!) + 'm' : '-' }}</strong>
                      </div>
                      <div class="p90-bar-row">
                        <span>加权 P90</span>
                        <div class="p90-track"><div class="p90-fill weighted" :style="{ width: `${Math.min(((weightedP90ByCell[detailKey(item)]!.p90_device_weighted_m || 0) / Math.max(weightedP90ByCell[detailKey(item)]!.p90_unweighted_m || 0, weightedP90ByCell[detailKey(item)]!.p90_device_weighted_m || 0, 1)) * 100, 100)}%` }"></div></div>
                        <strong class="font-mono">{{ weightedP90ByCell[detailKey(item)]!.p90_device_weighted_m != null ? Math.round(weightedP90ByCell[detailKey(item)]!.p90_device_weighted_m!) + 'm' : '-' }}</strong>
                      </div>
                    </div>
                    <div class="delta-line">
                      加权后半径减少
                      <strong>{{ weightedP90ByCell[detailKey(item)]!.delta_pct != null ? pct(weightedP90ByCell[detailKey(item)]!.delta_pct!) : '-' }}</strong>
                      <span class="text-muted ml-sm">points={{ fmt(weightedP90ByCell[detailKey(item)]!.point_count) }} / devices={{ fmt(weightedP90ByCell[detailKey(item)]!.device_count) }}</span>
                    </div>
                    <table class="data-table centroid-table">
                      <thead><tr><th>设备</th><th>点数</th><th>权重</th><th>最大距离</th><th>平均距离</th><th>贡献</th></tr></thead>
                      <tbody>
                        <tr v-for="dev in weightedP90ByCell[detailKey(item)]!.top_polluting_devices" :key="dev.dev_id">
                          <td class="font-mono">{{ maskDevId(dev.dev_id) }}</td>
                          <td class="font-mono">{{ fmt(dev.point_count) }}</td>
                          <td class="font-mono">{{ dev.weight.toFixed(1) }}</td>
                          <td class="font-mono">{{ dev.max_dist_m != null ? Math.round(dev.max_dist_m) + 'm' : '-' }}</td>
                          <td class="font-mono">{{ dev.avg_dist_m != null ? Math.round(dev.avg_dist_m) + 'm' : '-' }}</td>
                          <td class="font-mono">{{ pct(dev.contribution_pct) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </template>
                  <div v-else class="text-xs text-secondary">暂无加权 P90 明细</div>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="filteredCells.length === 0">
          <td colspan="13" class="empty-row">暂无 Cell 维护数据</td>
        </tr>
      </tbody>
    </table>
    <div style="padding:0 var(--sp-lg) var(--sp-lg)">
      <Pagination :page="page" :page-size="pageSize" :total-count="totalCount" :total-pages="totalPages" @update:page="p => page = p" />
    </div>
  </div>
</template>

<style scoped>
.grid-7 { display: grid; grid-template-columns: repeat(7, 1fr); gap: var(--sp-md); }
.grid-10 { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: var(--sp-sm); }
@media (max-width: 1400px) { .grid-10 { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
.ml-md { margin-left: var(--sp-md); }
.btn-sm { padding: 3px 10px; font-size: 11px; }

.drift-bar { display: flex; height: 14px; border-radius: 7px; overflow: hidden; }
.drift-seg { min-width: 2px; }
.drift-stable { background: var(--c-success); }
.drift-large_coverage { background: var(--c-warning); }
.drift-dual_cluster { background: #0891b2; }
.drift-migration { background: #7c3aed; }
.drift-collision { background: var(--c-danger); }
.drift-dynamic { background: #db2777; }
.drift-uncertain { background: #f59e0b; }
.drift-oversize_single { background: #991b1b; }
.drift-insufficient { background: var(--c-waiting); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.bg-stable { background: var(--c-success); }
.bg-large_coverage { background: var(--c-warning); }
.bg-dual_cluster { background: #0891b2; }
.bg-migration { background: #7c3aed; }
.bg-collision { background: var(--c-danger); }
.bg-dynamic { background: #db2777; }
.bg-uncertain { background: #f59e0b; }
.bg-oversize_single { background: #991b1b; }
.bg-insufficient { background: var(--c-waiting); }

.drift-tag-stable { background: #dcfce7; color: #166534; }
.drift-tag-large_coverage { background: #fef9c3; color: #854d0e; }
.drift-tag-dual_cluster { background: #cffafe; color: #155e75; }
.drift-tag-migration { background: #ede9fe; color: #5b21b6; }
.drift-tag-collision { background: #fee2e2; color: #991b1b; }
.drift-tag-dynamic { background: #fce7f3; color: #9d174d; }
.drift-tag-uncertain { background: #fef3c7; color: #92400e; }
.drift-tag-oversize_single { background: #fee2e2; color: #7f1d1d; }
.drift-tag-insufficient { background: #f3f4f6; color: #6b7280; }

.grade-excellent { background: #dcfce7; color: #15803d; }
.grade-good { background: #dbeafe; color: #1d4ed8; }
.grade-qualified { background: #fef3c7; color: #b45309; }
.grade-unqualified { background: #f3f4f6; color: #6b7280; }

.scale-major { background: #dcfce7; color: #15803d; }
.scale-large { background: #dbeafe; color: #1d4ed8; }
.scale-medium { background: #ccfbf1; color: #0f766e; }
.scale-small { background: #fef3c7; color: #b45309; }
.scale-micro { background: #f3f4f6; color: #6b7280; }

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--c-bg); }
.expand-icon { font-size: 10px; color: var(--c-text-muted); text-align: center; }
.wrap-row { flex-wrap: wrap; }

.ta-filter-panel {
  margin: var(--sp-md) var(--sp-lg) 0;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-bg);
}
.ta-filter-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ta-filter-grid { display: grid; grid-template-columns: 1.4fr 150px 1.4fr 150px; gap: 10px; align-items: start; }
.filter-field { display: flex; flex-direction: column; gap: 5px; font-size: 11px; color: var(--c-text-muted); }
.filter-field select {
  height: 28px; border: 1px solid var(--c-border); border-radius: 4px;
  background: var(--c-card); color: var(--c-text); padding: 2px 8px;
}
.range-row { display: grid; grid-template-columns: 1fr 1fr 86px; gap: 6px; align-items: center; color: var(--c-text); }
.range-row input { min-width: 0; }
.check-row { display: flex; flex-wrap: wrap; gap: 6px 10px; color: var(--c-text); }
.check-row label { display: inline-flex; align-items: center; gap: 4px; }
@media (max-width: 1200px) { .ta-filter-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 760px) { .ta-filter-grid { grid-template-columns: 1fr; } }

.detail-row td { background: var(--c-bg); padding: 0 !important; }
.detail-content { padding: 16px 20px; }
.detail-tabs { display: flex; gap: 6px; margin-bottom: 12px; }
.tab-btn {
  border: 1px solid var(--c-border); background: var(--c-card); color: var(--c-text);
  border-radius: 4px; padding: 5px 10px; font-size: 12px; cursor: pointer;
}
.tab-btn.active { background: var(--c-primary); border-color: var(--c-primary); color: white; }
.detail-section { margin-bottom: 12px; }
.detail-section:last-child { margin-bottom: 0; }
.section-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--c-text-muted); border-bottom: 1px solid var(--c-border); padding-bottom: 3px; margin-bottom: 6px;
}
.detail-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.detail-item { display: flex; flex-direction: column; gap: 1px; }
.dl { font-size: 10px; color: var(--c-text-muted); }
.dv { font-size: 12px; color: var(--c-text); font-weight: 500; }

.loc-td { max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.centroid-table { font-size: 11px; margin-top: 6px; }
.centroid-table th { font-size: 10px; padding: 4px 8px; }
.centroid-table td { padding: 3px 8px; }
.empty-row { padding: 20px; text-align: center; color: var(--c-text-muted); }

.antitoxin-row { background: #fef2f2; }
.antitoxin-row:hover { background: #fee2e2 !important; }

/* 质心覆盖（按 §9.5 合理精度范围上色）*/
.coverage-cell { font-weight: 600; }
.cov-excellent { color: #15803d; }   /* <=200m 优秀 */
.cov-good      { color: #1d4ed8; }   /* <=500m 良好 */
.cov-acceptable { color: #b45309; }  /* <=800m 可接受 */
.cov-large     { color: #991b1b; }   /* >800m 偏大（触发多质心分析）*/

.drift-ratio-bar {
  display: inline-flex; align-items: center; gap: 6px;
  width: 100%; max-width: 140px;
}
.drift-ratio-bar .drift-ratio-fill {
  height: 6px; background: var(--c-primary); border-radius: 3px; min-width: 2px;
  flex-shrink: 0;
}
.drift-ratio-val { font-size: 11px; }

/* ==================== TA 覆盖评估 ==================== */
.ta-cell { padding: 4px 8px; }
.ta-dist { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ta-nobs { color: var(--c-text-muted); margin-top: 2px; }
.ta-nobs-low { color: #b45309; }

/* ta_verification 色标 badge */
.ta-badge {
  display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 11px; font-weight: 500; white-space: nowrap;
}
.tv-ok              { background: #dcfce7; color: #166534; }
.tv-insufficient    { background: #f3f4f6; color: #6b7280; font-style: italic; }
.tv-xlarge          { background: #fee2e2; color: #991b1b; }
.tv-large           { background: #ffedd5; color: #9a3412; }
.tv-not_checked     { background: #dbeafe; color: #1e40af; }
.tv-not_applicable  { background: #f3f4f6; color: #6b7280; }

/* 详情区 TA section 强调样式 */
.ta-section { background: #fafbfc; }
.section-hint { font-weight: 400; color: var(--c-text-muted); font-size: 12px; margin-left: 6px; }
.ta-weak strong { color: #b45309; }
.ta-none { color: var(--c-text-muted); }

/* lib/TA 比值色彩 */
.ratio-danger { color: var(--c-danger); }
.ratio-warn   { color: #b45309; }
.ratio-ok     { color: #166534; }

/* 1300m 门槛 tag */
.threshold-over    { background: #fee2e2; color: #991b1b; }
.threshold-under   { background: #dcfce7; color: #166534; }
.threshold-conflict{ background: #fef3c7; color: #92400e; font-weight: 600; }

.weighted-section { background: #fafbfc; padding: 8px; border-radius: 6px; }
.p90-compare { display: grid; gap: 8px; max-width: 620px; margin-bottom: 10px; }
.p90-bar-row { display: grid; grid-template-columns: 86px minmax(160px, 1fr) 70px; align-items: center; gap: 10px; font-size: 12px; }
.p90-track { height: 12px; background: #e5e7eb; border-radius: 6px; overflow: hidden; }
.p90-fill { height: 100%; border-radius: 6px; }
.p90-fill.raw { background: #f97316; }
.p90-fill.weighted { background: #0ea5e9; }
.delta-line { font-size: 12px; margin-bottom: 10px; color: var(--c-text); }
</style>
