<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import {
  getServiceBS,
  getServiceCell,
  getServiceLAC,
  getServiceSearch,
  type ServiceBSDetail,
  type ServiceCellDetail,
  type ServiceLACDetail,
  type ServiceSearchItem,
  type ServiceSearchPayload,
} from '../../api/service'
import { pct } from '../../composables/useFormat'

type SearchLevel = 'cell' | 'bs' | 'lac'

const level = ref<SearchLevel>('cell')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 50
const payload = ref<ServiceSearchPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  query: { q: '', level: 'cell', operator_code: null, limit: 50 },
  items: [],
  total_count: 0,
  total_pages: 0,
})
const selectedItem = ref<ServiceSearchItem | null>(null)
const cellDetail = ref<ServiceCellDetail | null>(null)
const bsDetail = ref<ServiceBSDetail | null>(null)
const lacDetail = ref<ServiceLACDetail | null>(null)

const detailTitle = computed(() => {
  if (!selectedItem.value) return '查询详情'
  if (selectedItem.value.level === 'cell') return `Cell ${selectedItem.value.cell_id}`
  if (selectedItem.value.level === 'bs') return `BS ${selectedItem.value.bs_id}`
  return `LAC ${selectedItem.value.lac}`
})

function secondaryValue(item: ServiceSearchItem): string {
  if (item.level === 'cell') return item.bs_id ? String(item.bs_id) : '-'
  if (item.level === 'bs') return item.total_cells ? `${item.total_cells} cells` : '-'
  return item.total_bs ? `${item.total_bs} BS` : '-'
}

function qualityValue(item: ServiceSearchItem): string {
  if (item.level === 'lac') return item.position_grade || 'stable'
  return item.position_grade || '-'
}

function metricValue(item: ServiceSearchItem): string {
  if (item.level === 'lac') {
    return item.qualified_bs_ratio !== undefined ? pct(item.qualified_bs_ratio) : '-'
  }
  return item.p90_radius_m !== null && item.p90_radius_m !== undefined ? `${Math.round(item.p90_radius_m)}m` : '-'
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return typeof v === 'number' ? v.toFixed(2) : String(v)
}

async function loadDetail(item: ServiceSearchItem): Promise<void> {
  selectedItem.value = item
  cellDetail.value = null
  bsDetail.value = null
  lacDetail.value = null
  if (item.level === 'cell' && item.cell_id !== null) {
    cellDetail.value = await getServiceCell(item.cell_id, {
      operator_code: item.operator_code,
      lac: item.lac,
      tech_norm: item.tech_norm,
    })
  } else if (item.level === 'bs' && item.bs_id !== null) {
    bsDetail.value = await getServiceBS(item.bs_id, {
      operator_code: item.operator_code,
      lac: item.lac,
    })
  } else if (item.level === 'lac' && item.lac !== null) {
    lacDetail.value = await getServiceLAC(item.lac, {
      operator_code: item.operator_code,
    })
  }
}

async function runSearch(page = 1): Promise<void> {
  currentPage.value = page
  try {
    payload.value = await getServiceSearch(searchQuery.value.trim(), level.value, null, page, pageSize)
    if (payload.value.items.length > 0) {
      await loadDetail(payload.value.items[0])
    } else {
      selectedItem.value = null
      cellDetail.value = null
      bsDetail.value = null
      lacDetail.value = null
    }
  } catch {
    payload.value = { ...payload.value, items: [] }
    selectedItem.value = null
  }
}

function onPageChange(page: number) {
  void runSearch(page)
}

function trendColor(trend: string | null | undefined): string {
  if (trend === 'improving') return 'var(--c-success)'
  if (trend === 'degrading') return '#ef4444'
  return 'var(--c-primary)'
}

onMounted(async () => {
  await runSearch()
})
</script>

<template>
  <PageHeader title="站点查询" description="查询 Cell / BS / LAC 的位置、质量和风险提示。当前支持关键词查询与结果详情；运营商筛选和坐标范围查询待开发。">
    <div class="text-xs text-secondary">
      数据集 {{ payload.version.dataset_key || '-' }} ｜ 发布 {{ payload.version.run_id || '-' }} ｜ {{ payload.version.snapshot_version_prev }} → {{ payload.version.snapshot_version }}
    </div>
  </PageHeader>

  <div class="card mb-lg flex gap-md items-center wrap-row">
    <input v-model="searchQuery" class="search-input" placeholder="输入 cell_id、bs_id、LAC 或运营商..." @keyup.enter="runSearch(1)" />
    <div class="flex gap-sm wrap-row">
      <button class="btn" :class="{ 'btn-primary': level === 'cell' }" @click="level = 'cell'; runSearch(1)">Cell</button>
      <button class="btn" :class="{ 'btn-primary': level === 'bs' }" @click="level = 'bs'; runSearch(1)">BS</button>
      <button class="btn" :class="{ 'btn-primary': level === 'lac' }" @click="level = 'lac'; runSearch(1)">LAC</button>
    </div>
    <button class="btn btn-primary" @click="runSearch(1)">查询</button>
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>{{ level === 'cell' ? 'cell_id' : level === 'bs' ? 'bs_id' : 'LAC' }}</th>
          <th>LAC</th>
          <th>关联信息</th>
          <th>运营商</th>
          <th>状态</th>
          <th>质量 / 分类</th>
          <th>{{ level === 'lac' ? 'qualified BS 比例' : 'P90 (m)' }}</th>
          <th>可用于补数</th>
          <th>可参与维护</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in payload.items" :key="`${item.level}-${item.operator_code}-${item.lac ?? 'na'}-${item.bs_id ?? 'na'}-${item.cell_id ?? 'na'}-${index}`" class="result-row" @click="loadDetail(item)">
          <td class="font-mono font-semibold">{{ item.level === 'cell' ? item.cell_id : item.level === 'bs' ? item.bs_id : item.lac }}</td>
          <td class="font-mono">{{ item.lac ?? '-' }}</td>
          <td class="font-mono text-xs">{{ secondaryValue(item) }}</td>
          <td>{{ item.operator_cn || item.operator_code }}</td>
          <td><StatusTag :state="item.lifecycle_state as any" size="sm" /></td>
          <td>{{ qualityValue(item) }}</td>
          <td class="font-mono">{{ metricValue(item) }}</td>
          <td><span v-if="item.anchor_eligible" style="color:var(--c-success)">&#10003;</span><span v-else class="text-muted">-</span></td>
          <td><span v-if="item.baseline_eligible" style="color:var(--c-primary)">&#10003;</span><span v-else class="text-muted">-</span></td>
        </tr>
        <tr v-if="payload.items.length === 0">
          <td colspan="9" class="empty-row">暂无查询结果</td>
        </tr>
      </tbody>
    </table>
    <Pagination
      :page="currentPage"
      :page-size="pageSize"
      :total-count="payload.total_count ?? 0"
      :total-pages="payload.total_pages ?? 0"
      @update:page="onPageChange"
    />
  </div>

  <div class="card mt-lg">
        <div class="font-semibold text-sm mb-md">{{ detailTitle }}</div>
        <div class="text-xs text-secondary mb-md">运营商筛选、LAC筛选和坐标范围查询待开发。</div>

    <!-- Cell 完整画像 -->
    <div v-if="selectedItem?.level === 'cell' && cellDetail" class="detail-sections">
      <div class="detail-section">
        <div class="detail-section-title">标识</div>
        <div class="detail-grid">
          <div><span class="text-muted">运营商</span><strong>{{ cellDetail.operator_cn || cellDetail.operator_code || '-' }}</strong></div>
          <div><span class="text-muted">LAC</span><strong class="font-mono">{{ cellDetail.lac ?? '-' }}</strong></div>
          <div><span class="text-muted">BS</span><strong class="font-mono">{{ cellDetail.bs_id ?? '-' }}</strong></div>
          <div><span class="text-muted">Cell</span><strong class="font-mono">{{ cellDetail.cell_id }}</strong></div>
          <div><span class="text-muted">制式</span><strong>{{ cellDetail.tech_norm || '-' }}</strong></div>
        </div>
      </div>

      <div class="detail-section">
        <div class="detail-section-title">位置 · 精度</div>
        <div class="detail-grid">
          <div><span class="text-muted">经度</span><strong class="font-mono">{{ cellDetail.center_lon ?? '-' }}</strong></div>
          <div><span class="text-muted">纬度</span><strong class="font-mono">{{ cellDetail.center_lat ?? '-' }}</strong></div>
          <div><span class="text-muted">P50 半径</span><strong class="font-mono">{{ cellDetail.p50_radius_m ? Math.round(cellDetail.p50_radius_m) + 'm' : '-' }}</strong></div>
          <div><span class="text-muted">P90 半径</span><strong class="font-mono">{{ cellDetail.p90_radius_m ? Math.round(cellDetail.p90_radius_m) + 'm' : '-' }}</strong></div>
          <div><span class="text-muted">物理位置</span><strong>{{ (cellDetail as any).province_name || '' }} {{ (cellDetail as any).city_name || '' }} {{ (cellDetail as any).district_name || '-' }}</strong></div>
        </div>
      </div>

      <div class="detail-section">
        <div class="detail-section-title">质量 · 资格</div>
        <div class="detail-grid">
          <div><span class="text-muted">位置质量</span><strong>{{ cellDetail.position_grade || '-' }}</strong></div>
          <div><span class="text-muted">生命周期</span><strong><StatusTag v-if="cellDetail.lifecycle_state" :state="cellDetail.lifecycle_state as any" size="sm" /><span v-else>-</span></strong></div>
          <div><span class="text-muted">可用于补数</span><strong>{{ cellDetail.anchor_eligible ? '✓ 是' : '否' }}</strong></div>
          <div><span class="text-muted">可参与维护</span><strong>{{ cellDetail.baseline_eligible ? '✓ 是' : '否' }}</strong></div>
        </div>
      </div>

      <div class="detail-section">
        <div class="detail-section-title">标签</div>
        <div class="detail-grid">
          <div><span class="text-muted">空间行为</span><strong>{{ cellDetail.drift_pattern || '-' }}</strong></div>
          <div><span class="text-muted">复用风险</span><strong :class="{ 'warn-text': cellDetail.is_collision }">{{ cellDetail.is_collision ? '⚠ 是' : '否' }}</strong></div>
          <div><span class="text-muted">动态特征</span><strong :class="{ 'warn-text': cellDetail.is_dynamic }">{{ cellDetail.is_dynamic ? '⚠ 是' : '否' }}</strong></div>
          <div><span class="text-muted">多位置特征</span><strong :class="{ 'warn-text': cellDetail.is_multi_centroid }">{{ cellDetail.is_multi_centroid ? '⚠ 是' : '否' }}</strong></div>
        </div>
      </div>

      <div class="detail-section">
        <div class="detail-section-title">信号</div>
        <div class="detail-grid">
          <div><span class="text-muted">RSRP 均值</span><strong class="font-mono">{{ fmtNum(cellDetail.rsrp_avg) }}</strong></div>
          <div><span class="text-muted">RSRQ 均值</span><strong class="font-mono">{{ fmtNum(cellDetail.rsrq_avg) }}</strong></div>
          <div><span class="text-muted">SINR 均值</span><strong class="font-mono">{{ fmtNum(cellDetail.sinr_avg) }}</strong></div>
          <div><span class="text-muted">气压均值</span><strong class="font-mono">{{ fmtNum(cellDetail.pressure_avg) }}</strong></div>
        </div>
      </div>

      <div class="detail-section">
        <div class="detail-section-title">活跃度</div>
        <div class="detail-grid">
          <div><span class="text-muted">独立观测数</span><strong class="font-mono">{{ cellDetail.independent_obs ?? '-' }}</strong></div>
          <div><span class="text-muted">独立设备数</span><strong class="font-mono">{{ cellDetail.distinct_dev_id ?? '-' }}</strong></div>
          <div><span class="text-muted">近 30 天活跃</span><strong class="font-mono">{{ cellDetail.active_days_30d ?? '-' }} 天</strong></div>
        </div>
      </div>
    </div>

    <!-- BS 详情 -->
    <div v-else-if="selectedItem?.level === 'bs' && bsDetail">
      <div class="detail-grid mb-md">
        <div><span class="text-muted">运营商</span><strong>{{ bsDetail.operator_cn || bsDetail.operator_code || '-' }}</strong></div>
        <div><span class="text-muted">LAC</span><strong>{{ bsDetail.lac ?? '-' }}</strong></div>
        <div><span class="text-muted">分类</span><strong>{{ bsDetail.classification || '-' }}</strong></div>
        <div><span class="text-muted">P90 扩散</span><strong>{{ bsDetail.gps_p90_dist_m ? Math.round(bsDetail.gps_p90_dist_m) + 'm' : '-' }}</strong></div>
        <div><span class="text-muted">总 Cell</span><strong class="font-mono">{{ bsDetail.total_cells ?? '-' }}</strong></div>
        <div><span class="text-muted">合格 Cell</span><strong class="font-mono">{{ bsDetail.qualified_cells ?? '-' }}</strong></div>
        <div><span class="text-muted">优秀 Cell</span><strong class="font-mono">{{ bsDetail.excellent_cells ?? '-' }}</strong></div>
        <div><span class="text-muted">异常 Cell 占比</span><strong class="font-mono">{{ bsDetail.anomaly_cell_ratio != null ? pct(bsDetail.anomaly_cell_ratio) : '-' }}</strong></div>
        <div><span class="text-muted">物理位置</span><strong>{{ (bsDetail as any).province_name || '' }} {{ (bsDetail as any).city_name || '' }} {{ (bsDetail as any).district_name || '-' }}</strong></div>
      </div>
      <table class="data-table compact-table">
        <thead>
          <tr><th>cell_id</th><th>状态</th><th>位置质量</th><th>P90 (m)</th><th>漂移</th></tr>
        </thead>
        <tbody>
          <tr v-for="cell in bsDetail.cells" :key="cell.cell_id">
            <td class="font-mono font-semibold">{{ cell.cell_id }}</td>
            <td><StatusTag :state="cell.lifecycle_state as any" size="sm" /></td>
            <td>{{ cell.position_grade || '-' }}</td>
            <td class="font-mono">{{ cell.p90_radius_m ? Math.round(cell.p90_radius_m) : '-' }}</td>
            <td>{{ cell.drift_pattern || '-' }}</td>
          </tr>
          <tr v-if="bsDetail.cells.length === 0"><td colspan="5" class="empty-row">该 BS 暂无下属 Cell 明细</td></tr>
        </tbody>
      </table>
    </div>

    <!-- LAC 详情 -->
    <div v-else-if="selectedItem?.level === 'lac' && lacDetail">
      <div class="detail-grid mb-md">
        <div><span class="text-muted">运营商</span><strong>{{ lacDetail.operator_cn || lacDetail.operator_code || '-' }}</strong></div>
        <div><span class="text-muted">状态</span><strong>{{ lacDetail.lifecycle_state || '-' }}</strong></div>
        <div><span class="text-muted">合格 BS</span><strong>{{ lacDetail.qualified_bs ?? '-' }} / {{ lacDetail.total_bs ?? '-' }}</strong></div>
        <div><span class="text-muted">合格比例</span><strong>{{ lacDetail.qualified_bs_ratio !== undefined ? pct(lacDetail.qualified_bs_ratio) : '-' }}</strong></div>
        <div>
          <span class="text-muted">趋势</span>
          <strong :style="{ color: trendColor(lacDetail.trend) }">{{ lacDetail.trend || '-' }}</strong>
        </div>
        <div><span class="text-muted">物理位置</span><strong>{{ (lacDetail as any).province_name || '' }} {{ (lacDetail as any).city_name || '' }} {{ (lacDetail as any).district_name || '-' }}</strong></div>
      </div>
      <table class="data-table compact-table">
        <thead>
          <tr><th>bs_id</th><th>状态</th><th>分类</th><th>总 Cell</th><th>合格+ Cell</th></tr>
        </thead>
        <tbody>
          <tr v-for="bs in lacDetail.bs_items" :key="bs.bs_id">
            <td class="font-mono font-semibold">{{ bs.bs_id }}</td>
            <td><StatusTag :state="bs.lifecycle_state as any" size="sm" /></td>
            <td>{{ bs.classification || '-' }}</td>
            <td class="font-mono">{{ bs.total_cells }}</td>
            <td class="font-mono">{{ bs.qualified_cells + bs.excellent_cells }}</td>
          </tr>
          <tr v-if="lacDetail.bs_items.length === 0"><td colspan="5" class="empty-row">该 LAC 暂无 BS 明细</td></tr>
        </tbody>
      </table>
    </div>

    <div v-else class="empty-row">点击上方结果可查看详情</div>
  </div>
</template>

<style scoped>
.search-input {
  flex: 1;
  min-width: 260px;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  outline: none;
}
.search-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 2px rgba(59,130,246,0.1); }
.wrap-row { flex-wrap: wrap; }
.result-row { cursor: pointer; }
.result-row:hover { background: var(--c-bg); }
.detail-sections { display: flex; flex-direction: column; gap: var(--sp-lg); }
.detail-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--c-text-muted);
  margin-bottom: var(--sp-sm);
  padding-bottom: 4px;
  border-bottom: 1px solid var(--c-border);
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-md);
}
.detail-grid div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-grid strong { font-family: var(--font-mono); font-size: 12px; }
.compact-table { margin-top: var(--sp-sm); }
.empty-row {
  padding: 20px;
  text-align: center;
  color: var(--c-text-muted);
}
.warn-text { color: #ef4444; font-weight: 600; }
</style>
