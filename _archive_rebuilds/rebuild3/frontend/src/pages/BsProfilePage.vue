<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 筛选 -->
    <div class="section">
      <div class="section-title">筛选</div>
      <div class="filters-grid filters-grid--five">
        <div class="filter-field"><label>运营商</label><select v-model="filters.operator_code"><option value="">全部</option><option value="46000">中国移动</option><option value="46001">中国联通</option><option value="46011">中国电信</option></select></div>
        <div class="filter-field"><label>制式</label><select v-model="filters.tech_norm"><option value="">全部</option><option value="4G">4G</option><option value="5G">5G</option></select></div>
        <div class="filter-field"><label>LAC</label><input v-model="filters.lac" placeholder="LAC 编号" /></div>
        <div class="filter-field"><label>健康状态</label><select v-model="filters.health_state"><option value="">全部</option><option value="healthy">健康</option><option value="insufficient">证据不足</option><option value="collision_suspect">碰撞嫌疑</option><option value="collision_confirmed">碰撞确认</option><option value="dynamic">动态</option><option value="migration_suspect">迁移嫌疑</option><option value="gps_bias">GPS偏差</option></select></div>
        <div class="filter-field"><label>资格</label><select v-model="filters.qualification"><option value="">全部</option><option value="anchorable">可锚定</option><option value="not_anchorable">不可锚定</option><option value="baseline">基线合格</option><option value="not_baseline">基线不合格</option></select></div>
      </div>
      <div class="flex-row gap-4" style="margin-top:12px;">
        <button class="action-button" @click="applyFilters">筛选</button>
        <button class="inline-button" @click="resetFilters">重置</button>
      </div>
    </div>

    <!-- 汇总 -->
    <div v-if="summary" class="summary-grid">
      <div class="summary-card"><div class="label">总数</div><div class="value">{{ fmtN(summary.total) }}</div></div>
      <div class="summary-card"><div class="label">活跃</div><div class="value">{{ fmtN(summary.active) }}</div></div>
      <div class="summary-card"><div class="label">健康</div><div class="value">{{ fmtN(summary.healthy) }}</div></div>
      <div class="summary-card"><div class="label">锚点可用</div><div class="value">{{ fmtN(summary.anchorable) }}</div></div>
    </div>

    <!-- 表格 -->
    <div class="section">
      <div v-if="loading" class="loader">正在加载 BS 画像...</div>
      <div v-else-if="!rows.length" class="page-empty">无数据</div>
      <div v-else class="table-wrap">
        <table class="table table--compact">
          <thead>
            <tr>
              <th class="sortable" @click="toggleSort('operator')">运营商</th>
              <th>制式</th>
              <th>LAC</th>
              <th>BS ID</th>
              <th>生命周期</th>
              <th>健康状态</th>
              <th>资格</th>
              <th class="sortable" @click="toggleSort('cell_count')">Cell 数</th>
              <th class="sortable" @click="toggleSort('gps_p50')">P50(m)</th>
              <th class="sortable" @click="toggleSort('gps_p90')">P90(m)</th>
              <th>面积 km²</th>
              <th>GPS 原始率</th>
              <th>信号原始率</th>
              <th>RSRP</th>
              <th style="color:var(--gray-400)">旧分类(参考)</th>
              <th style="color:var(--gray-400)">GPS质量(参考)</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.object_id">
              <tr class="is-expandable" @click="toggleExpand(row.object_id)">
                <td>{{ row.operator_name || '—' }}</td>
                <td>{{ row.tech_norm || '—' }}</td>
                <td class="mono">{{ row.lac || '—' }}</td>
                <td class="mono">{{ row.bs_id || '—' }}</td>
                <td><LifecycleBadge :state="row.lifecycle_state" /></td>
                <td><HealthBadge :state="row.health_state" /></td>
                <td class="qualification-cell"><QualificationTags :anchorable="!!row.anchorable" :baseline-eligible="!!row.baseline_eligible" /></td>
                <td>{{ fmtN(row.cell_count) }}</td>
                <td class="mono">{{ row.gps_p50_dist_m ?? '—' }}</td>
                <td class="mono">{{ row.gps_p90_dist_m ?? '—' }}</td>
                <td>{{ row.area_km2 ?? '—' }}</td>
                <td>{{ pct(row.gps_original_ratio) }}</td>
                <td>{{ pct(row.signal_original_ratio) }}</td>
                <td>{{ row.rsrp_avg ?? '—' }}</td>
                <td class="text-muted text-sm">{{ row.classification_v2 || '—' }}</td>
                <td class="text-muted text-sm">{{ row.gps_quality_reference || '—' }}</td>
              </tr>
              <tr v-if="expandedRows[row.object_id]">
                <td colspan="16">
                  <div class="expand-panel">
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                      <div>
                        <div class="text-sm font-semibold">空间精度</div>
                        <div class="text-muted text-sm">中心点 ({{ row.center_lat ?? '—' }}, {{ row.center_lon ?? '—' }}) · P50 {{ row.gps_p50_dist_m ?? '—' }}m · P90 {{ row.gps_p90_dist_m ?? '—' }}m · 面积 {{ row.area_km2 ?? '—' }}km²</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">对象状态</div>
                        <div class="text-muted text-sm">lifecycle: {{ row.lifecycle_state }} · health: {{ row.health_state }} · anchorable: {{ row.anchorable ? '是' : '否' }} · baseline: {{ row.baseline_eligible ? '是' : '否' }}</div>
                        <div class="text-muted text-sm" style="color:var(--gray-400);margin-top:4px;">旧分类(参考): {{ row.classification_v2 || '—' }} · GPS质量(参考): {{ row.gps_quality_reference || '—' }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">GPS 来源构成</div>
                        <div class="text-muted text-sm">原始率 {{ pct(row.gps_original_ratio) }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">信号质量</div>
                        <div class="text-muted text-sm">RSRP {{ row.rsrp_avg ?? '—' }} · RSRQ {{ row.rsrq_avg ?? '—' }} · SINR {{ row.sinr_avg ?? '—' }}</div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div class="flex-row gap-4" style="margin-top:12px;justify-content:space-between;">
        <span class="text-muted text-sm">共 {{ fmtN(total) }} 条，第 {{ filters.page }}/{{ totalPages }} 页</span>
        <div class="badge-row">
          <button class="inline-button" :disabled="filters.page <= 1" @click="changePage(filters.page - 1)">上一页</button>
          <button class="inline-button" :disabled="filters.page >= totalPages" @click="changePage(filters.page + 1)">下一页</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import HealthBadge from '../components/HealthBadge.vue';
import LifecycleBadge from '../components/LifecycleBadge.vue';
import QualificationTags from '../components/QualificationTags.vue';
import { api } from '../lib/api';

const filters = reactive({ operator_code: '', tech_norm: '', lac: '', health_state: '', qualification: '', page: 1, page_size: 10 });
const loading = ref(false); const error = ref(''); const summary = ref<any>(null);
const rows = ref<any[]>([]); const total = ref(0); const totalPages = ref(1);
const sortField = ref(''); const sortDir = ref<'asc'|'desc'>('asc');
const expandedRows = reactive<Record<string, boolean>>({});

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function pct(n: number | undefined): string { return n != null ? (n * 100).toFixed(1) + '%' : '—'; }
function toggleExpand(id: string) { expandedRows[id] = !expandedRows[id]; }
function toggleSort(f: string) { if (sortField.value === f) { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; } else { sortField.value = f; sortDir.value = 'asc'; } }

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const p = await api.getProfileList({ object_type: 'bs', query: filters.lac, operator_code: filters.operator_code, tech_norm: filters.tech_norm, health_state: filters.health_state, qualification: filters.qualification, page: filters.page, page_size: filters.page_size });
    summary.value = p.summary; rows.value = p.rows ?? []; total.value = p.total ?? 0; totalPages.value = p.total_pages ?? 1;
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

function applyFilters() { filters.page = 1; loadPage(); }
function resetFilters() { Object.assign(filters, { operator_code: '', tech_norm: '', lac: '', health_state: '', qualification: '', page: 1 }); loadPage(); }
function changePage(p: number) { filters.page = p; loadPage(); }

onMounted(loadPage);
</script>
