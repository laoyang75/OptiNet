<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { getMaintenanceLAC, getMaintenanceStats, type MaintenanceLACItem, type MaintenanceStatsPayload } from '../../api/maintenance'
import { fmt, pct } from '../../composables/useFormat'

const stats = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0, published_bs_count: 0, published_lac_count: 0,
    collision_cell_count: 0, multi_centroid_cell_count: 0, dynamic_cell_count: 0, anomaly_bs_count: 0,
  },
  drift_distribution: {},
})
const lacItems = ref<MaintenanceLACItem[]>([])
const expandedIdx = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const totalPages = ref(0)

const qualifiedLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'qualified').length)
const observingLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'observing').length)
const waitingLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'waiting').length)
const hasAnomalyLac = computed(() => lacItems.value.filter(i => (i.anomaly_bs_ratio ?? 0) > 0).length)

const trendCfg: Record<string, { label: string; style: string }> = {
  improving: { label: '改善', style: 'background:#dcfce7;color:#166534' },
  degrading: { label: '恶化', style: 'background:#fee2e2;color:#991b1b' },
  stable: { label: '稳定', style: 'background:#f3f4f6;color:#6b7280' },
}

function trendTag(t: string | null) {
  return trendCfg[t || 'stable'] || trendCfg.stable
}

function toggle(idx: number) { expandedIdx.value = expandedIdx.value === idx ? null : idx }

async function loadData(): Promise<void> {
  expandedIdx.value = null
  try {
    const [statsPayload, lacPayload] = await Promise.all([
      getMaintenanceStats(),
      getMaintenanceLAC(page.value, pageSize.value),
    ])
    stats.value = statsPayload
    lacItems.value = lacPayload.items
    totalCount.value = lacPayload.totalCount
    totalPages.value = lacPayload.totalPages
  } catch {
    lacItems.value = []
  }
}

watch(page, loadData)
onMounted(loadData)
</script>

<template>
  <PageHeader title="LAC 维护" description="区域层整体质量趋势，异常 BS 比例变化和退出预警。点击行展开详情。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} | {{ stats.version.snapshot_version_prev }} -> {{ stats.version.snapshot_version }}
    </div>
  </PageHeader>

  <!-- Summary cards -->
  <div class="grid grid-5 mb-lg">
    <SummaryCard title="总数" :value="fmt(stats.summary.published_lac_count)" />
    <SummaryCard title="合格" :value="fmt(qualifiedLac)" color="var(--c-success)" />
    <SummaryCard title="观察" :value="fmt(observingLac)" color="var(--c-dormant)" />
    <SummaryCard title="等待" :value="fmt(waitingLac)" />
    <SummaryCard title="有异常BS" :value="fmt(hasAnomalyLac)" color="var(--c-danger)" />
  </div>

  <!-- Table -->
  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">LAC 画像列表 · {{ fmt(totalCount) }} 条</span>
    </div>

    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th style="width:20px"></th>
          <th>运营商</th><th>LAC</th><th>状态</th>
          <th>BS数</th><th>活跃/退出</th><th>面积km2</th><th>边界稳定性</th><th>异常BS率</th><th>趋势</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(item, idx) in lacItems" :key="`${item.operator_code}-${item.lac}`">
          <tr class="clickable-row" @click="toggle(idx)">
            <td class="expand-icon">{{ expandedIdx === idx ? '▾' : '▸' }}</td>
            <td class="text-xs">{{ item.operator_cn || item.operator_code }}</td>
            <td class="font-mono font-semibold">{{ item.lac }}</td>
            <td><StatusTag :state="item.lifecycle_state as any" size="sm" /></td>
            <td class="font-mono">{{ fmt(item.total_bs) }}</td>
            <td class="font-mono text-xs">{{ item.active_bs_count ?? '-' }} / <span class="text-muted">{{ item.retired_bs_count ?? 0 }}</span></td>
            <td class="font-mono">{{ item.area_km2 != null ? Number(item.area_km2).toFixed(1) : '-' }}</td>
            <td style="min-width:100px"><PercentBar v-if="item.boundary_stability_score != null" :value="item.boundary_stability_score" :color="item.boundary_stability_score >= 0.8 ? 'var(--c-success)' : item.boundary_stability_score >= 0.5 ? 'var(--c-warning)' : 'var(--c-danger)'" /></td>
            <td class="font-mono" :style="(item.anomaly_bs_ratio ?? 0) > 0.2 ? 'color:var(--c-danger)' : ''">{{ item.anomaly_bs_ratio != null ? pct(item.anomaly_bs_ratio) : '-' }}</td>
            <td><span class="tag" :style="trendTag(item.trend).style">{{ trendTag(item.trend).label }}</span></td>
          </tr>
          <!-- Expanded detail -->
          <tr v-if="expandedIdx === idx" class="detail-row">
            <td :colspan="10">
              <div class="detail-content">
                <div class="detail-section">
                  <div class="section-title">区域构成</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">总 BS 数</span><span class="dv">{{ fmt(item.total_bs) }}</span></div>
                    <div class="detail-item"><span class="dl">活跃 BS</span><span class="dv font-mono" style="color:var(--c-success)">{{ item.active_bs_count ?? '-' }}</span></div>
                    <div class="detail-item"><span class="dl">退出 BS</span><span class="dv font-mono" :style="(item.retired_bs_count ?? 0) > 0 ? 'color:var(--c-danger)' : ''">{{ item.retired_bs_count ?? 0 }}</span></div>
                    <div class="detail-item"><span class="dl">合格 BS / 比例</span><span class="dv">{{ fmt(item.qualified_bs) }} ({{ pct(item.qualified_bs_ratio) }})</span></div>
                    <div class="detail-item"><span class="dl">面积</span><span class="dv">{{ item.area_km2 != null ? Number(item.area_km2).toFixed(2) + ' km2' : '-' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">稳定性与健康</div>
                  <div class="detail-grid">
                    <div class="detail-item">
                      <span class="dl">边界稳定性</span>
                      <span class="dv">
                        <PercentBar v-if="item.boundary_stability_score != null" :value="item.boundary_stability_score" :label="item.boundary_stability_score >= 0.8 ? '稳定' : item.boundary_stability_score >= 0.5 ? '波动' : '剧变'" />
                        <span v-else>-</span>
                      </span>
                    </div>
                    <div class="detail-item"><span class="dl">异常 BS 比例</span><span class="dv" :style="(item.anomaly_bs_ratio ?? 0) > 0.2 ? 'color:var(--c-danger)' : ''">{{ item.anomaly_bs_ratio != null ? pct(item.anomaly_bs_ratio) : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">锚点资格</span><span class="dv" :style="item.anchor_eligible ? 'color:var(--c-success)' : ''">{{ item.anchor_eligible ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">基线资格</span><span class="dv" :style="!item.baseline_eligible ? 'color:var(--c-danger)' : ''">{{ item.baseline_eligible ? '是' : '否' }}</span></div>
                    <div class="detail-item"><span class="dl">趋势</span><span class="dv"><span class="tag" :style="trendTag(item.trend).style">{{ trendTag(item.trend).label }}</span></span></div>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="lacItems.length === 0">
          <td colspan="10" class="empty-row">暂无 LAC 维护数据</td>
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

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--c-bg); }
.expand-icon { font-size: 10px; color: var(--c-text-muted); text-align: center; }
.loc-td { max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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
</style>
