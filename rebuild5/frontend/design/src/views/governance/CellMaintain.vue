<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { getMaintenanceCells, getMaintenanceStats, runMaintenance, type MaintenanceCellItem, type MaintenanceStatsPayload } from '../../api/maintenance'
import { fmt, pct } from '../../composables/useFormat'
import { DRIFT_LABELS, type DriftPattern } from '../../types'

const driftKeys: DriftPattern[] = ['stable', 'large_coverage', 'insufficient', 'moderate_drift', 'collision', 'migration']
const selectedKind = ref<'anomaly' | 'collision' | 'migration' | 'multi_centroid' | 'all'>('all')
const cells = ref<MaintenanceCellItem[]>([])
const expandedIdx = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const totalPages = ref(0)
const running = ref(false)
const stats = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: 'sample_6lac', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0, published_bs_count: 0, published_lac_count: 0,
    collision_cell_count: 0, multi_centroid_cell_count: 0, dynamic_cell_count: 0, anomaly_bs_count: 0,
  },
  drift_distribution: {},
})

const driftDist = computed<Record<DriftPattern, number>>(() => ({
  stable: Number(stats.value.drift_distribution.stable ?? 0),
  large_coverage: Number(stats.value.drift_distribution.large_coverage ?? 0),
  insufficient: Number(stats.value.drift_distribution.insufficient ?? 0),
  moderate_drift: Number(stats.value.drift_distribution.moderate_drift ?? 0),
  collision: Number(stats.value.drift_distribution.collision ?? 0),
  migration: Number(stats.value.drift_distribution.migration ?? 0),
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
  { key: 'collision', label: '碰撞' },
  { key: 'migration', label: '迁移' },
  { key: 'multi_centroid', label: '多质心' },
  { key: 'anomaly', label: '全部异常' },
  { key: 'dormant', label: '休眠' },
  { key: 'retired', label: '退出' },
]

function densityLabel(days: number): { label: string; style: string } {
  if (days >= 20) return { label: '高密度', style: 'background:#fee2e2;color:#991b1b' }
  if (days >= 10) return { label: '中密度', style: 'background:#fef3c7;color:#92400e' }
  return { label: '低密度', style: 'background:#f3f4f6;color:#6b7280' }
}

function fmtRsrp(v: any): string {
  if (v == null) return '-'
  return Number(v).toFixed(3)
}

function fmtTime(v: string | null): string {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 19)
}

function tag(cfg: Record<string, { label: string; cls: string }>, key: string | null) {
  return cfg[key || ''] || { label: key || '-', cls: '' }
}

function toggle(idx: number) { expandedIdx.value = expandedIdx.value === idx ? null : idx }

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
  <PageHeader title="Cell 画像维护" description="中位数质心 + 日漂移分类 + 质量分级 + 规模分级。点击行展开详情。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} ｜ {{ stats.version.snapshot_version_prev }} → {{ stats.version.snapshot_version }}
      <button class="btn btn-sm ml-md" :disabled="running" @click="doRun">{{ running ? '运行中...' : '运行 Step 5' }}</button>
    </div>
  </PageHeader>

  <!-- Summary cards -->
  <div class="grid grid-7 mb-lg">
    <SummaryCard title="总数" :value="fmt(stats.summary.published_cell_count)" />
    <SummaryCard title="稳定" :value="fmt(driftDist.stable)" color="var(--c-success)" />
    <SummaryCard title="碰撞" :value="fmt(stats.summary.collision_cell_count)" color="var(--c-danger)" />
    <SummaryCard title="多质心" :value="fmt(stats.summary.multi_centroid_cell_count)" color="var(--c-warning)" />
    <SummaryCard title="大覆盖" :value="fmt(driftDist.large_coverage)" color="#d97706" />
    <SummaryCard title="迁移" :value="fmt(driftDist.migration)" color="#7c3aed" />
    <SummaryCard title="证据不足" :value="fmt(driftDist.insufficient)" />
  </div>

  <!-- Drift bar -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">漂移分类分布</div>
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

    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th style="width:20px"></th>
          <th>运营商</th><th>制式</th><th>LAC</th><th>BS</th><th>Cell ID</th>
          <th>质量</th><th>规模</th><th>漂移</th><th>状态</th>
          <th>独立观测</th><th>设备</th><th>P90(m)</th><th>RSRP</th><th>窗口量</th><th>最后观测</th><th>位置</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(item, idx) in cells" :key="`${item.operator_code}-${item.lac}-${item.cell_id}`">
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
            <td><StatusTag :state="item.lifecycle_state as any" size="sm" /></td>
            <td class="font-mono">{{ item.independent_obs ?? '-' }}</td>
            <td class="font-mono">{{ item.distinct_dev_id ?? '-' }}</td>
            <td class="font-mono">{{ item.p90_radius_m ? Math.round(item.p90_radius_m) : '-' }}</td>
            <td class="font-mono">{{ fmtRsrp((item as any).rsrp_avg) }}</td>
            <td class="font-mono">{{ item.window_obs_count ?? '-' }}</td>
            <td class="text-xs">{{ fmtTime(item.last_observed_at) }}</td>
            <td class="text-xs loc-td">{{ (item as any).district_name || (item as any).city_name || '-' }}</td>
          </tr>
          <!-- Expanded detail -->
          <tr v-if="expandedIdx === idx" class="detail-row">
            <td :colspan="17">
              <div class="detail-content">
                <div class="detail-section">
                  <div class="section-title">空间</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">中位数质心</span><span class="dv font-mono">{{ item.center_lon ? `${Number(item.center_lon).toFixed(4)}, ${Number(item.center_lat).toFixed(4)}` : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">P50 / P90</span><span class="dv">{{ item.p50_radius_m ? Math.round(item.p50_radius_m) : '-' }}m / {{ item.p90_radius_m ? Math.round(item.p90_radius_m) : '-' }}m</span></div>
                    <div class="detail-item"><span class="dl">位置质量</span><span class="dv">{{ tag(gradeCfg, item.position_grade).label }}</span></div>
                    <div class="detail-item"><span class="dl">物理位置</span><span class="dv">{{ (item as any).province_name || '' }} {{ (item as any).city_name || '' }} {{ (item as any).district_name || '-' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">漂移分析</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">漂移模式</span><span class="dv" :style="item.is_collision ? 'color:var(--c-danger)' : ''">{{ DRIFT_LABELS[item.drift_pattern as DriftPattern] ?? item.drift_pattern ?? '-' }}</span></div>
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
                    <div class="detail-item"><span class="dl">独立观测点</span><span class="dv">{{ fmt(item.independent_obs) }} ({{ fmt(item.distinct_dev_id) }} 台)</span></div>
                    <div class="detail-item"><span class="dl">滑窗观测量</span><span class="dv">{{ fmt(item.window_obs_count) }}</span></div>
                    <div class="detail-item"><span class="dl">锚点资格</span><span class="dv" :style="item.anchor_eligible ? 'color:var(--c-success)' : ''">{{ item.anchor_eligible ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">基线资格</span><span class="dv" :style="!item.baseline_eligible ? 'color:var(--c-danger)' : ''">{{ item.baseline_eligible ? '是' : '否（被阻断）' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">信号与状态</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">RSRP 均值</span><span class="dv">{{ fmtRsrp((item as any).rsrp_avg) }} dBm</span></div>
                    <div class="detail-item"><span class="dl">气压均值</span><span class="dv font-mono">{{ item.pressure_avg != null ? Number(item.pressure_avg).toFixed(1) + ' hPa' : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">防毒化命中</span><span class="dv" :style="item.antitoxin_hit ? 'color:var(--c-danger);font-weight:600' : ''">{{ item.antitoxin_hit ? '是 (阻断)' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">最后观测</span><span class="dv">{{ fmtTime(item.last_observed_at) }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">退出管理</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">30天活跃天数</span><span class="dv font-mono">{{ item.active_days_30d }}</span></div>
                    <div class="detail-item"><span class="dl">连续不活跃天数</span><span class="dv font-mono" :style="item.consecutive_inactive_days > 0 ? 'color:var(--c-dormant)' : ''">{{ item.consecutive_inactive_days }}d</span></div>
                    <div class="detail-item"><span class="dl">密度等级</span><span class="dv"><span class="tag" :style="densityLabel(item.active_days_30d).style">{{ densityLabel(item.active_days_30d).label }}</span></span></div>
                    <div class="detail-item"><span class="dl">窗口观测量</span><span class="dv">{{ fmt(item.window_obs_count) }}</span></div>
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
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="cells.length === 0">
          <td colspan="17" class="empty-row">暂无 Cell 维护数据</td>
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
.ml-md { margin-left: var(--sp-md); }
.btn-sm { padding: 3px 10px; font-size: 11px; }

.drift-bar { display: flex; height: 14px; border-radius: 7px; overflow: hidden; }
.drift-seg { min-width: 2px; }
.drift-stable { background: var(--c-success); }
.drift-collision { background: var(--c-danger); }
.drift-migration { background: #7c3aed; }
.drift-large_coverage { background: var(--c-warning); }
.drift-moderate_drift { background: var(--c-dormant); }
.drift-insufficient { background: var(--c-waiting); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.bg-stable { background: var(--c-success); }
.bg-collision { background: var(--c-danger); }
.bg-migration { background: #7c3aed; }
.bg-large_coverage { background: var(--c-warning); }
.bg-moderate_drift { background: var(--c-dormant); }
.bg-insufficient { background: var(--c-waiting); }

.drift-tag-stable { background: #dcfce7; color: #166534; }
.drift-tag-collision { background: #fee2e2; color: #991b1b; }
.drift-tag-migration { background: #ede9fe; color: #5b21b6; }
.drift-tag-large_coverage { background: #fef9c3; color: #854d0e; }
.drift-tag-moderate_drift { background: #fff7ed; color: #9a3412; }
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

.detail-row td { background: var(--c-bg); padding: 0 !important; }
.detail-content { padding: 16px 20px; }
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

.drift-ratio-bar {
  display: inline-flex; align-items: center; gap: 6px;
  width: 100%; max-width: 140px;
}
.drift-ratio-bar .drift-ratio-fill {
  height: 6px; background: var(--c-primary); border-radius: 3px; min-width: 2px;
  flex-shrink: 0;
}
.drift-ratio-val { font-size: 11px; }
</style>
