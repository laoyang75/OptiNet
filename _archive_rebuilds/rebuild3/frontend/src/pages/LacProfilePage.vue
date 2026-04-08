<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 筛选 -->
    <div class="section">
      <div class="section-title">筛选</div>
      <div class="flex-row gap-4">
        <div class="filter-field">
          <label>搜索 LAC</label>
          <input v-model="filters.query" placeholder="LAC 编号" @keyup.enter="applyFilters" />
        </div>
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
      <div v-if="loading" class="loader">正在加载 LAC 画像...</div>
      <div v-else-if="!rows.length" class="page-empty">无数据</div>
      <div v-else class="table-wrap">
        <table class="table table--compact">
          <thead>
            <tr>
              <th class="sortable" @click="toggleSort('operator')">运营商</th>
              <th class="sortable" @click="toggleSort('rat')">制式</th>
              <th class="sortable" @click="toggleSort('lac_id')">LAC</th>
              <th>位置</th>
              <th>生命周期</th>
              <th>健康状态</th>
              <th>区域质量标签</th>
              <th>资格</th>
              <th class="sortable" @click="toggleSort('cell_count')">Cell 数</th>
              <th class="sortable" @click="toggleSort('bs_count')">BS 数</th>
              <th>面积 km²</th>
              <th>异常 BS 占比</th>
              <th>GPS 原始率</th>
              <th>信号原始率</th>
              <th>RSRP 均值</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.object_id">
              <tr class="is-expandable" @click="toggleExpand(row.object_id)">
                <td>{{ row.operator_name || row.operator || '—' }}</td>
                <td>{{ row.tech_norm || row.rat || '—' }}</td>
                <td class="mono">{{ row.lac || row.lac_id || '—' }}</td>
                <td>{{ row.location_name || '—' }}</td>
                <td><LifecycleBadge :state="row.lifecycle_state" /></td>
                <td><HealthBadge :state="row.health_state" /></td>
                <td>{{ row.region_quality_label || '—' }}</td>
                <td class="qualification-cell"><QualificationTags variant="lac" :anchorable="!!row.anchorable" /></td>
                <td>{{ fmtN(row.cell_count) }}</td>
                <td>{{ fmtN(row.bs_count) }}</td>
                <td>{{ row.area_km2 ?? '—' }}</td>
                <td>{{ row.anomaly_bs_ratio != null ? (row.anomaly_bs_ratio * 100).toFixed(1) + '%' : '—' }}</td>
                <td>{{ row.gps_original_ratio != null ? (row.gps_original_ratio * 100).toFixed(1) + '%' : '—' }}</td>
                <td>{{ row.signal_original_ratio != null ? (row.signal_original_ratio * 100).toFixed(1) + '%' : '—' }}</td>
                <td>{{ row.rsrp_avg ?? '—' }}</td>
              </tr>
              <tr v-if="expandedRows[row.object_id]">
                <td colspan="15">
                  <div class="expand-panel">
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                      <div>
                        <div class="text-sm font-semibold">基本信息</div>
                        <div class="text-muted text-sm">运营商: {{ row.operator_name }} · 制式: {{ row.tech_norm }} · 面积: {{ row.area_km2 ?? '—' }} km²</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">区域 Cell/BS 统计</div>
                        <div class="text-muted text-sm">Cell {{ fmtN(row.cell_count) }} (活跃 {{ fmtN(row.active_cell_count) }}) · BS {{ fmtN(row.bs_count) }} (活跃 {{ fmtN(row.active_bs_count) }})</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">异常 BS 命中</div>
                        <div class="text-muted text-sm">异常 BS 占比: {{ row.anomaly_bs_ratio != null ? (row.anomaly_bs_ratio * 100).toFixed(1) + '%' : '—' }}</div>
                      </div>
                      <div>
                        <div class="text-sm font-semibold">GPS/信号来源构成</div>
                        <div class="text-muted text-sm">GPS 原始率 {{ row.gps_original_ratio != null ? (row.gps_original_ratio * 100).toFixed(1) + '%' : '—' }} · 信号原始率 {{ row.signal_original_ratio != null ? (row.signal_original_ratio * 100).toFixed(1) + '%' : '—' }}</div>
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

const filters = reactive({ query: '', page: 1, page_size: 10 });
const loading = ref(false);
const error = ref('');
const summary = ref<any>(null);
const rows = ref<any[]>([]);
const total = ref(0);
const totalPages = ref(1);
const sortField = ref('');
const sortDir = ref<'asc' | 'desc'>('asc');
const expandedRows = reactive<Record<string, boolean>>({});

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function toggleExpand(id: string) { expandedRows[id] = !expandedRows[id]; }
function toggleSort(field: string) { if (sortField.value === field) { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; } else { sortField.value = field; sortDir.value = 'asc'; } }

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const p = await api.getProfileList({ object_type: 'lac', query: filters.query, page: filters.page, page_size: filters.page_size });
    summary.value = p.summary; rows.value = p.rows ?? []; total.value = p.total ?? 0; totalPages.value = p.total_pages ?? 1;
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

function applyFilters() { filters.page = 1; loadPage(); }
function resetFilters() { filters.query = ''; filters.page = 1; loadPage(); }
function changePage(p: number) { filters.page = p; loadPage(); }

onMounted(loadPage);
</script>
