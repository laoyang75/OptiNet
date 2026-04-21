<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
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

// BS-LAC-v1: LAC 只有 active / dormant / retired
const activeLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'active').length)
const dormantLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'dormant').length)
const retiredLac = computed(() => lacItems.value.filter(i => i.lifecycle_state === 'retired').length)
const hasAnomalyLac = computed(() => lacItems.value.filter(i => (i.anomaly_bs ?? 0) > 0).length)

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
    <SummaryCard title="活跃" :value="fmt(activeLac)" color="var(--c-success)" />
    <SummaryCard title="休眠" :value="fmt(dormantLac)" color="var(--c-dormant)" />
    <SummaryCard title="退出" :value="fmt(retiredLac)" color="var(--c-danger)" />
    <SummaryCard title="含异常BS" :value="fmt(hasAnomalyLac)" color="#d97706" />
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
          <th>总BS</th><th>正常</th><th>异常</th><th>证据不足</th>
          <th>质心</th><th>面积km²</th><th>异常BS率</th>
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
            <td class="font-mono" :style="(item.normal_bs ?? 0) > 0 ? 'color:var(--c-success)' : ''">{{ fmt(item.normal_bs ?? 0) }}</td>
            <td class="font-mono" :style="(item.anomaly_bs ?? 0) > 0 ? 'color:var(--c-danger)' : ''">{{ fmt(item.anomaly_bs ?? 0) }}</td>
            <td class="font-mono" :style="(item.insufficient_bs ?? 0) > 0 ? 'color:var(--c-text-muted)' : ''">{{ fmt(item.insufficient_bs ?? 0) }}</td>
            <td class="text-xs loc-td">{{ item.center_lon ? `${Number(item.center_lon).toFixed(3)}, ${Number(item.center_lat).toFixed(3)}` : '-' }}</td>
            <td class="font-mono">{{ item.area_km2 != null ? Number(item.area_km2).toFixed(1) : '-' }}</td>
            <td class="font-mono" :style="(item.anomaly_bs_ratio ?? 0) > 0.2 ? 'color:var(--c-danger)' : ''">{{ item.anomaly_bs_ratio != null ? pct(item.anomaly_bs_ratio) : '-' }}</td>
          </tr>
          <!-- Expanded detail -->
          <tr v-if="expandedIdx === idx" class="detail-row">
            <td :colspan="11">
              <div class="detail-content">
                <div class="detail-section">
                  <div class="section-title">BS 三分类（观察用）</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">总 BS</span><span class="dv">{{ fmt(item.total_bs) }}</span></div>
                    <div class="detail-item"><span class="dl">正常 BS</span><span class="dv font-mono" style="color:var(--c-success);font-weight:600">{{ fmt(item.normal_bs ?? 0) }}</span></div>
                    <div class="detail-item"><span class="dl">异常 BS</span><span class="dv font-mono" :style="(item.anomaly_bs ?? 0) > 0 ? 'color:var(--c-danger);font-weight:600' : ''">{{ fmt(item.anomaly_bs ?? 0) }}</span></div>
                    <div class="detail-item"><span class="dl">证据不足 BS</span><span class="dv font-mono">{{ fmt(item.insufficient_bs ?? 0) }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">区域位置（基于正常 BS）</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">LAC 质心（正常 BS 中位）</span><span class="dv font-mono">{{ item.center_lon ? `${Number(item.center_lon).toFixed(6)}, ${Number(item.center_lat).toFixed(6)}` : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">面积（bbox 粗估）</span><span class="dv">{{ item.area_km2 != null ? Number(item.area_km2).toFixed(2) + ' km²' : '-' }}</span></div>
                    <div class="detail-item"><span class="dl">异常 BS 比例</span><span class="dv" :style="(item.anomaly_bs_ratio ?? 0) > 0.2 ? 'color:var(--c-danger)' : ''">{{ item.anomaly_bs_ratio != null ? pct(item.anomaly_bs_ratio) : '-' }}</span></div>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="section-title">BS 状态分布</div>
                  <div class="detail-grid">
                    <div class="detail-item"><span class="dl">活跃 BS</span><span class="dv font-mono" style="color:var(--c-success)">{{ item.active_bs_count ?? '-' }}</span></div>
                    <div class="detail-item"><span class="dl">退出 BS</span><span class="dv font-mono" :style="(item.retired_bs_count ?? 0) > 0 ? 'color:var(--c-danger)' : ''">{{ item.retired_bs_count ?? 0 }}</span></div>
                    <div class="detail-item"><span class="dl">合格 BS</span><span class="dv">{{ fmt(item.qualified_bs) }}</span></div>
                    <div class="detail-item"><span class="dl">生命周期</span><span class="dv"><StatusTag :state="item.lifecycle_state as any" size="sm" /></span></div>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="lacItems.length === 0">
          <td colspan="11" class="empty-row">暂无 LAC 维护数据</td>
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
