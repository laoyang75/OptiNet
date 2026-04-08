<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 筛选 -->
    <div class="section">
      <div class="section-title">筛选</div>
      <div class="filters-grid">
        <div class="filter-field"><label>运营商</label><select v-model="filters.operator_code"><option value="">全部</option><option value="46000">中国移动</option><option value="46001">中国联通</option><option value="46011">中国电信</option></select></div>
        <div class="filter-field"><label>制式</label><select v-model="filters.tech_norm"><option value="">全部</option><option value="4G">4G</option><option value="5G">5G</option></select></div>
        <div class="filter-field"><label>LAC</label><input v-model="filters.lac" placeholder="LAC 编号" /></div>
        <div class="filter-field"><label>BS</label><input v-model="filters.bs" placeholder="BS ID" /></div>
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
      <div v-if="loading" class="loader">正在加载 Cell 画像...</div>
      <div v-else-if="!rows.length" class="page-empty">无数据</div>
      <div v-else class="table-wrap">
        <table class="table table--compact">
          <thead>
            <tr>
              <th>运营商</th>
              <th>制式</th>
              <th>LAC</th>
              <th>BS ID</th>
              <th>Cell ID</th>
              <th>生命周期</th>
              <th>健康状态</th>
              <th>资格</th>
              <th class="sortable" @click="toggleSort('record_count')">记录数</th>
              <th class="sortable" @click="toggleSort('gps_p90')">P90(m)</th>
              <th>GPS 原始率</th>
              <th>信号原始率</th>
              <th>RSRP</th>
              <th style="color:var(--gray-400)">旧分类(来自BS)</th>
              <th style="color:var(--gray-400)">BS侧GPS质量(参考)</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.object_id">
              <tr class="is-expandable" @click="toggleExpand(row.object_id)">
                <td>{{ row.operator_name || '—' }}</td>
                <td>{{ row.tech_norm || '—' }}</td>
                <td class="mono">{{ row.lac || '—' }}</td>
                <td class="mono">{{ row.bs_id || '—' }}</td>
                <td class="mono">{{ row.cell_id || '—' }}</td>
                <td><LifecycleBadge :state="row.lifecycle_state" /></td>
                <td><HealthBadge :state="row.health_state" /></td>
                <td class="qualification-cell"><QualificationTags :anchorable="!!row.anchorable" :baseline-eligible="!!row.baseline_eligible" /></td>
                <td>{{ fmtN(row.record_count) }}</td>
                <td class="mono">{{ row.gps_p90_dist_m ?? '—' }}</td>
                <td>{{ pct(row.gps_original_ratio) }}</td>
                <td>{{ pct(row.signal_original_ratio) }}</td>
                <td>{{ row.rsrp_avg ?? '—' }}</td>
                <td class="text-muted text-sm">{{ row.classification_v2 || '—' }}</td>
                <td class="text-muted text-sm">{{ row.bs_gps_quality_reference || '—' }}</td>
              </tr>
              <tr v-if="expandedRows[row.object_id]">
                <td colspan="15">
                  <div class="expand-panel">
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                      <div>
                        <div class="text-sm font-semibold">GPS 中心 + 空间精度</div>
                        <div class="text-muted text-sm">
                          对象质心 ({{ row.center_lat ?? '—' }}, {{ row.center_lon ?? '—' }})
                          · 画像参考中心 ({{ row.profile_center_lat ?? '—' }}, {{ row.profile_center_lon ?? '—' }})
                          · 偏差 {{ row.centroid_deviation_m ?? '—' }}m
                        </div>
                        <div class="text-muted text-sm">P50 {{ row.gps_p50_dist_m ?? '—' }}m · P90 {{ row.gps_p90_dist_m ?? '—' }}m</div>
                        <div class="text-muted text-sm" style="color:var(--gray-500);margin-top:4px;">{{ row.coordinate_source_note || '对象质心以 obj_cell 快照为准。' }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">对象状态</div>
                        <div class="text-muted text-sm">lifecycle: {{ row.lifecycle_state }} · health: {{ row.health_state }}</div>
                        <div class="text-muted text-sm" style="color:var(--gray-400);margin-top:4px;">旧分类(来自BS，参考): {{ row.classification_v2 || '—' }} · BS侧GPS质量(参考): {{ row.bs_gps_quality_reference || '—' }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">画像质量 (GPS/信号来源)</div>
                        <div class="text-muted text-sm">GPS 原始率 {{ pct(row.gps_original_ratio) }} · 信号原始率 {{ pct(row.signal_original_ratio) }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">近期事实去向</div>
                        <div class="cell-fact-flow">
                          <div class="cell-fact-bar">
                            <div class="cell-fact-fill fact-governed" :style="{ width: factPct(row, 'governed') }"></div>
                            <div class="cell-fact-fill fact-pending-obs" :style="{ width: factPct(row, 'pending_observation') }"></div>
                            <div class="cell-fact-fill fact-pending-issue" :style="{ width: factPct(row, 'pending_issue') }"></div>
                            <div class="cell-fact-fill fact-rejected" :style="{ width: factPct(row, 'rejected') }"></div>
                          </div>
                          <div class="text-muted text-sm" style="margin-top:4px;">
                            fact_governed {{ row.fact_governed_count ?? 0 }} ·
                            fact_pending_observation {{ row.fact_pending_observation_count ?? 0 }} ·
                            fact_pending_issue {{ row.fact_pending_issue_count ?? 0 }} ·
                            fact_rejected {{ row.fact_rejected_count ?? 0 }}
                          </div>
                        </div>
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

const filters = reactive({ operator_code: '', tech_norm: '', lac: '', bs: '', health_state: '', qualification: '', page: 1, page_size: 10 });
const loading = ref(false); const error = ref(''); const summary = ref<any>(null);
const rows = ref<any[]>([]); const total = ref(0); const totalPages = ref(1);
const sortField = ref(''); const sortDir = ref<'asc'|'desc'>('asc');
const expandedRows = reactive<Record<string, boolean>>({});

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function pct(n: number | undefined): string { return n != null ? (n * 100).toFixed(1) + '%' : '—'; }
function toggleExpand(id: string) { expandedRows[id] = !expandedRows[id]; }
function toggleSort(f: string) { if (sortField.value === f) { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; } else { sortField.value = f; sortDir.value = 'asc'; } }

function factPct(row: any, type: string): string {
  const total = (row.fact_governed_count ?? 0) + (row.fact_pending_observation_count ?? 0) + (row.fact_pending_issue_count ?? 0) + (row.fact_rejected_count ?? 0);
  if (!total) return '0%';
  const val = row[`fact_${type}_count`] ?? 0;
  return Math.max((val / total) * 100, 2) + '%';
}

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const p = await api.getProfileList({ object_type: 'cell', query: filters.lac || filters.bs, operator_code: filters.operator_code, tech_norm: filters.tech_norm, health_state: filters.health_state, qualification: filters.qualification, page: filters.page, page_size: filters.page_size });
    summary.value = p.summary; rows.value = p.rows ?? []; total.value = p.total ?? 0; totalPages.value = p.total_pages ?? 1;
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

function applyFilters() { filters.page = 1; loadPage(); }
function resetFilters() { Object.assign(filters, { operator_code: '', tech_norm: '', lac: '', bs: '', health_state: '', qualification: '', page: 1 }); loadPage(); }
function changePage(p: number) { filters.page = p; loadPage(); }

onMounted(loadPage);
</script>

<style scoped>
.cell-fact-flow { margin-top: 4px; }
.cell-fact-bar {
  display: flex; height: 14px; border-radius: 4px; overflow: hidden; background: var(--gray-100);
}
.cell-fact-fill { height: 100%; min-width: 2px; }
.cell-fact-fill.fact-governed { background: var(--green-500); }
.cell-fact-fill.fact-pending-obs { background: var(--amber-500); }
.cell-fact-fill.fact-pending-issue { background: var(--orange-500); }
.cell-fact-fill.fact-rejected { background: var(--red-500); }
</style>
