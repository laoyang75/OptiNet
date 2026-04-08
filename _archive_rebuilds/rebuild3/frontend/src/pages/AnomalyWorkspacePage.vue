<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载异常工作台...</div>

    <template v-else-if="payload">
      <!-- 顶部汇总条（不随 Tab 切换） -->
      <div class="anom-summary-bar">
        <div class="anom-summary-item">
          <div class="anom-summary-label">对象级异常</div>
          <div class="anom-summary-value">{{ objectTotal }}</div>
          <div class="anom-summary-meta">
            <span>本批 <span :class="objectDeltaClass">+{{ payload.object_tab?.batch_new ?? 0 }}</span></span>
          </div>
        </div>
        <div class="anom-summary-item">
          <div class="anom-summary-label">记录级异常</div>
          <div class="anom-summary-value">{{ fmtN(recordTotal) }}</div>
          <div class="anom-summary-meta">
            <span>本批新增 {{ fmtN(payload.record_tab?.batch_new ?? 0) }}</span>
          </div>
        </div>
        <div class="anom-summary-item">
          <div class="anom-summary-label">锚点禁用</div>
          <div class="anom-summary-value">{{ blockedAnchor }}</div>
        </div>
        <div class="anom-summary-item">
          <div class="anom-summary-label">基线禁用</div>
          <div class="anom-summary-value">{{ blockedBaseline }}</div>
        </div>
        <div class="anom-summary-item">
          <div class="anom-summary-label">fact_rejected</div>
          <div class="anom-summary-value">{{ fmtN(rejectedCount) }}</div>
        </div>
      </div>

      <!-- Tab 切换 -->
      <div class="section">
        <div class="anom-tabs">
          <div class="anom-tab" :class="{ active: activeTab === 'object' }" @click="activeTab = 'object'">
            对象级异常<span class="anom-tab-count">{{ objectTotal }}</span>
          </div>
          <div class="anom-tab" :class="{ active: activeTab === 'record' }" @click="activeTab = 'record'">
            记录级异常 / 结构不合规<span class="anom-tab-count">{{ fmtN(recordTotal) }}</span>
          </div>
        </div>

        <!-- 对象级异常 Tab -->
        <template v-if="activeTab === 'object'">
          <!-- 子 Tab 按异常类型 -->
          <div class="tab-row" style="margin-bottom: 12px;">
            <button class="tab-button" :class="{ 'tab-button--active': objectSubTab === '' }" @click="objectSubTab = ''">全部</button>
            <button v-for="t in anomalyTypes" :key="t.key" class="tab-button" :class="{ 'tab-button--active': objectSubTab === t.key }" @click="objectSubTab = t.key">
              {{ t.label }}
            </button>
          </div>

          <!-- 筛选器 -->
          <div class="anom-filter-bar">
            <div class="filter-group">
              <span class="filter-label">严重度</span>
              <select v-model="filterSeverity" class="filter-select">
                <option value="">全部</option>
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </div>
            <div class="anom-filter-divider"></div>
            <div class="filter-group">
              <span class="filter-label">趋势</span>
              <select v-model="filterTrend" class="filter-select">
                <option value="">全部</option>
                <option value="worsening">恶化</option>
                <option value="stable">稳定</option>
                <option value="improving">改善</option>
              </select>
            </div>
          </div>

          <!-- 对象异常表 -->
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>对象</th>
                  <th>异常类型</th>
                  <th>严重度</th>
                  <th>发现批次</th>
                  <th>事实去向</th>
                  <th>锚点</th>
                  <th>基线</th>
                  <th>趋势</th>
                  <th>下游影响</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="row in filteredObjectRows" :key="row.object_id">
                  <tr class="is-expandable" @click="toggleExpand(row.object_id)">
                    <td>
                      <RouterLink :to="detailLink(row)" class="link-button" @click.stop>{{ row.title }}</RouterLink>
                      <div class="text-muted text-sm">{{ row.subtitle }}</div>
                    </td>
                    <td><HealthBadge :state="row.health_state" /></td>
                    <td><span class="anom-severity" :class="'sev-' + row.severity">{{ severityLabel(row.severity) }}</span></td>
                    <td class="mono text-sm">{{ row.batch_id }}</td>
                    <td><FactLayerBadge :layer="row.fact_route || 'fact_pending_issue'" /></td>
                    <td>{{ row.anchorable ? '✓' : '✗' }}</td>
                    <td>{{ row.baseline_eligible ? '✓' : '✗' }}</td>
                    <td><span class="anom-trend" :class="'trend-' + (row.evidence_trend || 'stable')">{{ trendLabel(row.evidence_trend) }}</span></td>
                    <td>{{ row.impact_count ?? 0 }}</td>
                  </tr>
                  <!-- 展开行 -->
                  <tr v-if="expandedRows[row.object_id]">
                    <td colspan="9">
                      <div class="expand-panel">
                        <div class="detail-grid--two" style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                          <div>
                            <div class="text-sm font-semibold" style="margin-bottom: 4px;">碰撞组 / 受影响对象</div>
                            <div class="text-muted text-sm">{{ row.collision_group || '无碰撞组' }}</div>
                            <div class="text-muted text-sm">受影响 Cell: {{ row.affected_cells ?? '—' }}</div>
                          </div>
                          <div>
                            <div class="text-sm font-semibold" style="margin-bottom: 4px;">事实去向说明</div>
                            <div class="text-muted text-sm">{{ row.fact_explanation || '—' }}</div>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </template>

        <!-- 记录级异常 Tab -->
        <template v-else>
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>异常类型</th>
                  <th>数量</th>
                  <th>本批新增</th>
                  <th>事实去向</th>
                  <th>锚点影响</th>
                  <th>基线影响</th>
                  <th>处理方式</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in payload.record_tab?.rows ?? []" :key="row.anomaly_type">
                  <td><span class="anom-type-badge" :class="'type-' + (row.type_class || 'default')">{{ row.anomaly_type }}</span></td>
                  <td class="mono">{{ fmtN(row.count) }}</td>
                  <td class="mono">+{{ row.batch_new ?? 0 }}</td>
                  <td><FactLayerBadge :layer="row.route || 'fact_governed'" /></td>
                  <td>{{ row.anchor_impact || '无' }}</td>
                  <td>{{ row.baseline_impact || '按标签决定' }}</td>
                  <td class="text-muted text-sm">{{ row.description }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';

import FactLayerBadge from '../components/FactLayerBadge.vue';
import HealthBadge from '../components/HealthBadge.vue';
import { api } from '../lib/api';

const loading = ref(false);
const error = ref('');
const payload = ref<any>(null);
const activeTab = ref<'object' | 'record'>('object');
const objectSubTab = ref('');
const filterSeverity = ref('');
const filterTrend = ref('');
const expandedRows = reactive<Record<string, boolean>>({});

function fmtN(n: number | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

const anomalyTypes = [
  { key: 'collision_suspect', label: '碰撞嫌疑' },
  { key: 'collision_confirmed', label: '碰撞确认' },
  { key: 'dynamic', label: '动态' },
  { key: 'migration_suspect', label: '迁移嫌疑' },
  { key: 'gps_bias', label: 'GPS偏差' },
];

const objectTotal = computed(() => (payload.value?.object_tab?.rows ?? []).length);
const recordTotal = computed(() => (payload.value?.record_tab?.rows ?? []).reduce((s: number, r: any) => s + Number(r.count ?? 0), 0));
const blockedAnchor = computed(() => (payload.value?.object_tab?.rows ?? []).filter((r: any) => !r.anchorable).length);
const blockedBaseline = computed(() => (payload.value?.object_tab?.rows ?? []).filter((r: any) => !r.baseline_eligible).length);
const rejectedCount = computed(() => Number((payload.value?.record_tab?.rows ?? []).find((r: any) => r.route === 'fact_rejected')?.count ?? 0));
const objectDeltaClass = computed(() => (payload.value?.object_tab?.batch_new ?? 0) > 0 ? 'd-down' : 'd-neutral');

const filteredObjectRows = computed(() => {
  let rows = payload.value?.object_tab?.rows ?? [];
  if (objectSubTab.value) {
    rows = rows.filter((r: any) => r.health_state === objectSubTab.value);
  }
  if (filterSeverity.value) {
    rows = rows.filter((r: any) => r.severity === filterSeverity.value);
  }
  if (filterTrend.value) {
    rows = rows.filter((r: any) => r.evidence_trend === filterTrend.value);
  }
  return rows;
});

function detailLink(row: any) {
  return { name: 'object-detail', params: { objectType: row.object_type, objectId: row.object_id } };
}

function toggleExpand(id: string) {
  expandedRows[id] = !expandedRows[id];
}

function severityLabel(s: string): string {
  return { high: '高', medium: '中', low: '低' }[s] || s;
}

function trendLabel(t: string | undefined): string {
  return { worsening: '恶化', stable: '稳定', improving: '改善', new: '新发现' }[t || ''] || t || '—';
}

async function loadPage() {
  loading.value = true;
  error.value = '';
  try {
    payload.value = await api.getAnomalyWorkspace();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载异常工作台';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPage);
</script>

<style scoped>
/* Summary bar */
.anom-summary-bar {
  display: flex; align-items: stretch; gap: 0;
  background: var(--surface-bg); border: 1px solid var(--surface-border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card); overflow: hidden;
}
.anom-summary-item { flex: 1; padding: 14px 20px; display: flex; flex-direction: column; gap: 2px; border-right: 1px solid var(--gray-100); }
.anom-summary-item:last-child { border-right: none; }
.anom-summary-label { font-size: 12px; color: var(--gray-400); font-weight: 500; }
.anom-summary-value { font-size: 24px; font-weight: 700; color: var(--gray-900); line-height: 1.2; }
.anom-summary-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--gray-500); margin-top: 2px; }

/* Tabs */
.anom-tabs { display: flex; gap: 0; border-bottom: 2px solid var(--gray-200); margin-bottom: 16px; }
.anom-tab { padding: 10px 20px; font-size: 14px; font-weight: 500; color: var(--gray-500); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: color .15s, border-color .15s; }
.anom-tab:hover { color: var(--gray-700); }
.anom-tab.active { color: var(--primary-600); border-bottom-color: var(--primary-600); font-weight: 600; }
.anom-tab-count { font-size: 12px; background: var(--gray-100); color: var(--gray-600); padding: 1px 7px; border-radius: 10px; margin-left: 6px; font-weight: 600; }
.anom-tab.active .anom-tab-count { background: var(--primary-50); color: var(--primary-600); }

/* Filter bar */
.anom-filter-bar { display: flex; align-items: center; gap: 16px; padding: 12px 20px; background: var(--surface-bg); border: 1px solid var(--surface-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-card); margin-bottom: 16px; }
.anom-filter-divider { width: 1px; height: 24px; background: var(--gray-200); }

/* Severity */
.anom-severity { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 6px; }
.anom-severity.sev-high { color: #991B1B; background: var(--red-50); }
.anom-severity.sev-medium { color: #9A3412; background: var(--orange-50); }
.anom-severity.sev-low { color: #92400E; background: var(--amber-50); }

/* Trend */
.anom-trend { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 6px; }
.anom-trend.trend-worsening { color: var(--red-600); background: var(--red-50); }
.anom-trend.trend-stable { color: var(--gray-500); background: var(--gray-100); }
.anom-trend.trend-improving { color: var(--green-600); background: var(--green-50); }
.anom-trend.trend-new { color: var(--blue-600); background: var(--blue-50); }

/* Type badges */
.anom-type-badge { font-size: 12px; font-weight: 500; padding: 2px 8px; border-radius: 6px; }
.anom-type-badge.type-normal_spread { background: var(--amber-50); color: #92400E; }
.anom-type-badge.type-single_large { background: var(--orange-50); color: #9A3412; }
.anom-type-badge.type-structure { background: var(--gray-100); color: var(--gray-600); }
.anom-type-badge.type-gps_fill { background: var(--blue-50); color: #1E40AF; }
.anom-type-badge.type-donor { background: var(--purple-50); color: #5B21B6; }
.anom-type-badge.type-default { background: var(--gray-100); color: var(--gray-600); }
</style>
