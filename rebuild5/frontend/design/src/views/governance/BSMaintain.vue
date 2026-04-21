<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { getMaintenanceBS, getMaintenanceStats, type MaintenanceBSItem, type MaintenanceStatsPayload } from '../../api/maintenance'
import { fmt } from '../../composables/useFormat'

const stats = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0, published_bs_count: 0, published_lac_count: 0,
    collision_cell_count: 0, multi_centroid_cell_count: 0, dynamic_cell_count: 0, anomaly_bs_count: 0,
  },
  drift_distribution: {},
})
const bsItems = ref<MaintenanceBSItem[]>([])
const expandedIdx = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const totalPages = ref(0)

// 方案 BS-LAC-v1：8 类 classification
const classCfg: Record<string, { label: string; cls: string }> = {
  normal: { label: '正常', cls: 'cls-normal' },
  insufficient: { label: '证据不足', cls: 'cls-insuff' },
  collision_bs: { label: '碰撞', cls: 'cls-collision' },
  dynamic_bs: { label: '动态', cls: 'cls-dynamic' },
  dual_cluster_bs: { label: '双质心', cls: 'cls-dual' },
  uncertain_bs: { label: '多质心', cls: 'cls-multi' },
  migration_bs: { label: '迁移', cls: 'cls-migration' },
  anomaly: { label: '异常混合', cls: 'cls-anomaly' },
}

function classTag(key: string | null) {
  return classCfg[key || 'normal'] || { label: key || '-', cls: '' }
}

const normalBs = computed(() => bsItems.value.filter(i => i.classification === 'normal').length)
const insuffBs = computed(() => bsItems.value.filter(i => i.classification === 'insufficient').length)
const anomalyBs = computed(() => bsItems.value.filter(i =>
  ['collision_bs','dynamic_bs','dual_cluster_bs','uncertain_bs','migration_bs','anomaly'].includes(i.classification || '')
).length)
const qualifiedBs = computed(() => bsItems.value.filter(i => i.lifecycle_state === 'qualified').length)

const clsDist = computed(() => {
  const counts: Record<string, number> = {}
  for (const key of Object.keys(classCfg)) counts[key] = 0
  for (const item of bsItems.value) {
    const c = item.classification || 'normal'
    if (c in counts) counts[c]++
  }
  return counts
})
const clsDistMax = computed(() => Math.max(...Object.values(clsDist.value), 1))

function toggle(idx: number) { expandedIdx.value = expandedIdx.value === idx ? null : idx }

async function loadData(): Promise<void> {
  expandedIdx.value = null
  try {
    const [statsPayload, bsPayload] = await Promise.all([
      getMaintenanceStats(),
      getMaintenanceBS(page.value, pageSize.value),
    ])
    stats.value = statsPayload
    bsItems.value = bsPayload.items
    totalCount.value = bsPayload.totalCount
    totalPages.value = bsPayload.totalPages
  } catch {
    bsItems.value = []
  }
}

watch(page, loadData)
onMounted(loadData)
</script>

<template>
  <PageHeader title="BS 维护" description="BS 层面的分类治理、面积异常、多质心和下属 Cell 健康度。点击行展开详情。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} | {{ stats.version.snapshot_version_prev }} -> {{ stats.version.snapshot_version }}
    </div>
  </PageHeader>

  <!-- Summary cards -->
  <div class="grid grid-5 mb-lg">
    <SummaryCard title="总数" :value="fmt(stats.summary.published_bs_count)" />
    <SummaryCard title="正常" :value="fmt(normalBs)" color="var(--c-success)" />
    <SummaryCard title="证据不足" :value="fmt(insuffBs)" color="var(--c-waiting)" />
    <SummaryCard title="异常" :value="fmt(anomalyBs)" color="var(--c-danger)" />
    <SummaryCard title="合格" :value="fmt(qualifiedBs)" color="#3b82f6" />
  </div>

  <!-- Classification distribution -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">BS 分类分布</div>
    <div class="cls-bar-chart">
      <div v-for="(cfg, key) in classCfg" :key="key" class="cls-bar-row">
        <span class="cls-bar-label text-xs">{{ cfg.label }}</span>
        <div class="cls-bar-track">
          <div class="cls-bar-fill" :class="cfg.cls" :style="{ width: clsDistMax > 0 ? `${((clsDist[key] ?? 0) / clsDistMax) * 100}%` : '0%' }"></div>
        </div>
        <span class="cls-bar-count font-mono text-xs">{{ fmt(clsDist[key] ?? 0) }}</span>
      </div>
    </div>
  </div>

  <!-- Table -->
  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">BS 画像列表 · {{ fmt(totalCount) }} 条</span>
    </div>

    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th style="width:20px"></th>
          <th>运营商</th><th>LAC</th><th>BS</th>
          <th>分类</th><th>状态</th>
          <th>总Cell</th><th>正常</th><th>异常</th><th>证据不足</th>
          <th title="正常 cell 到 BS 质心的 P90 距离">P90(m)</th><th>位置</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(item, idx) in bsItems" :key="`${item.operator_code}-${item.lac}-${item.bs_id}`">
          <tr class="clickable-row" @click="toggle(idx)">
            <td class="expand-icon">{{ expandedIdx === idx ? '▾' : '▸' }}</td>
            <td class="text-xs">{{ item.operator_cn || item.operator_code }}</td>
            <td class="font-mono">{{ item.lac }}</td>
            <td class="font-mono font-semibold">{{ item.bs_id }}</td>
            <td><span class="tag" :class="classTag(item.classification).cls">{{ classTag(item.classification).label }}</span></td>
            <td><StatusTag :state="item.lifecycle_state as any" size="sm" /></td>
            <td class="font-mono">{{ fmt(item.total_cells) }}</td>
            <td class="font-mono" :style="item.normal_cells > 0 ? 'color:var(--c-success)' : ''">{{ fmt(item.normal_cells ?? 0) }}</td>
            <td class="font-mono" :style="item.anomaly_cells > 0 ? 'color:var(--c-danger)' : ''">{{ fmt(item.anomaly_cells ?? 0) }}</td>
            <td class="font-mono" :style="item.insufficient_cells > 0 ? 'color:var(--c-text-muted)' : ''">{{ fmt(item.insufficient_cells ?? 0) }}</td>
            <td class="font-mono">{{ item.gps_p90_dist_m ? Math.round(item.gps_p90_dist_m) : '-' }}</td>
            <td class="text-xs loc-td">{{ item.center_lon ? `${Number(item.center_lon).toFixed(4)}, ${Number(item.center_lat).toFixed(4)}` : '-' }}</td>
          </tr>
          <!-- Expanded detail -->
          <tr v-if="expandedIdx === idx" class="detail-row">
            <td :colspan="12">
              <div class="detail-content">
                <div class="detail-section">
                  <div class="section-title">空间（基于正常 cell）</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">BS 质心（正常 cell 中位）</span><span class="dv font-mono">{{ item.center_lon ? `${Number(item.center_lon).toFixed(6)}, ${Number(item.center_lat).toFixed(6)}` : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">覆盖 P50 / P90</span><span class="dv">{{ item.gps_p50_dist_m ? Math.round(item.gps_p50_dist_m) : '-' }}m / {{ item.gps_p90_dist_m ? Math.round(item.gps_p90_dist_m) : '-' }}m</span></div>
                    <div class="detail-item"><span class="dl">分类</span><span class="dv"><span class="tag" :class="classTag(item.classification).cls">{{ classTag(item.classification).label }}</span></span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">Cell 三分类</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">总 Cell</span><span class="dv">{{ fmt(item.total_cells) }}</span></div>
                    <div class="detail-item"><span class="dl">正常 Cell</span><span class="dv" style="color:var(--c-success);font-weight:600">{{ fmt(item.normal_cells ?? 0) }}</span></div>
                    <div class="detail-item"><span class="dl">异常 Cell</span><span class="dv" :style="(item.anomaly_cells ?? 0) > 0 ? 'color:var(--c-danger);font-weight:600' : ''">{{ fmt(item.anomaly_cells ?? 0) }}</span></div>
                    <div class="detail-item"><span class="dl">证据不足 Cell</span><span class="dv">{{ fmt(item.insufficient_cells ?? 0) }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">生命周期与资格</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">生命周期</span><span class="dv"><StatusTag :state="item.lifecycle_state as any" size="sm" /></span></div>
                    <div class="detail-item"><span class="dl">合格 Cell</span><span class="dv">{{ fmt(item.qualified_cells) }}</span></div>
                    <div class="detail-item"><span class="dl">优秀 Cell</span><span class="dv">{{ fmt(item.excellent_cells) }}</span></div>
                    <div class="detail-item"><span class="dl">活跃 Cell 数</span><span class="dv font-mono">{{ item.window_active_cell_count ?? '-' }}</span></div>
                    <div class="detail-item"><span class="dl">锚点资格</span><span class="dv" :style="item.anchor_eligible ? 'color:var(--c-success)' : ''">{{ item.anchor_eligible ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">基线资格</span><span class="dv" :style="!item.baseline_eligible ? 'color:var(--c-danger)' : ''">{{ item.baseline_eligible ? '是' : '否' }}</span></div>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="bsItems.length === 0">
          <td colspan="12" class="empty-row">暂无 BS 维护数据</td>
        </tr>
      </tbody>
    </table>
    <div style="padding:0 var(--sp-lg) var(--sp-lg)">
      <Pagination :page="page" :page-size="pageSize" :total-count="totalCount" :total-pages="totalPages" @update:page="p => page = p" />
    </div>
  </div>
</template>

<style scoped>
.grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: var(--sp-md); }
.grid-7 { display: grid; grid-template-columns: repeat(7, 1fr); gap: var(--sp-md); }

/* BS-LAC-v1: 8 类 classification 颜色 */
.cls-normal { background: #dcfce7; color: #166534; }
.cls-insuff { background: #f3f4f6; color: #6b7280; }
.cls-collision { background: #fee2e2; color: #991b1b; }
.cls-dynamic { background: #fce7f3; color: #9d174d; }
.cls-dual { background: #cffafe; color: #155e75; }
.cls-multi { background: #fef3c7; color: #92400e; }
.cls-migration { background: #ede9fe; color: #5b21b6; }
.cls-anomaly { background: #fee2e2; color: #7f1d1d; }

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--c-bg); }
.expand-icon { font-size: 10px; color: var(--c-text-muted); text-align: center; }
.loc-td { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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
.empty-row { padding: 20px; text-align: center; color: var(--c-text-muted); }

.cls-bar-chart { display: flex; flex-direction: column; gap: 8px; }
.cls-bar-row { display: flex; align-items: center; gap: var(--sp-md); }
.cls-bar-label { width: 56px; text-align: right; flex-shrink: 0; color: var(--c-text-secondary); }
.cls-bar-track { flex: 1; height: 16px; background: var(--c-bg); border-radius: 3px; overflow: hidden; }
.cls-bar-fill { height: 100%; border-radius: 3px; min-width: 2px; transition: width 0.3s; }
.cls-bar-count { width: 40px; text-align: right; flex-shrink: 0; }
.cls-bar-fill.cls-normal { background: var(--c-success); }
.cls-bar-fill.cls-insuff { background: var(--c-waiting); }
.cls-bar-fill.cls-collision { background: var(--c-danger); }
.cls-bar-fill.cls-dynamic { background: #db2777; }
.cls-bar-fill.cls-dual { background: #0891b2; }
.cls-bar-fill.cls-multi { background: #f59e0b; }
.cls-bar-fill.cls-migration { background: #7c3aed; }
.cls-bar-fill.cls-anomaly { background: #7f1d1d; }
</style>
