<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载基础数据治理...</div>

    <template v-else-if="overview">
      <DataOriginBanner :origin="meta.origin" :subject-note="meta.subjectNote" :show-synthetic="true" />

      <!-- 概览卡片（6 张） -->
      <div class="summary-grid governance-summary-grid">
        <div class="summary-card"><div class="label">表数量</div><div class="value">{{ fmtN(overview.table_count) }}</div></div>
        <div class="summary-card"><div class="label">字段数量</div><div class="value">{{ fmtN(overview.field_count) }}</div></div>
        <div class="summary-card"><div class="label">使用登记</div><div class="value">{{ fmtN(overview.usage_count) }}</div></div>
        <div class="summary-card"><div class="label">待迁移确认</div><div class="value">{{ fmtN(overview.migration_pending) }}</div></div>
        <div class="summary-card"><div class="label">核心字段</div><div class="value">{{ fmtN(overview.core_field_count ?? 0) }}</div></div>
        <div class="summary-card"><div class="label">直接复用</div><div class="value">{{ fmtN(overview.direct_reuse_count ?? 0) }}</div></div>
      </div>

      <!-- Tab -->
      <div class="section">
        <div class="tab-row governance-tab-row">
          <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'fields' }" @click="activeTab = 'fields'">字段目录</button>
          <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'tables' }" @click="activeTab = 'tables'">表目录</button>
          <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'usage' }" @click="activeTab = 'usage'">实际使用</button>
          <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'migration' }" @click="activeTab = 'migration'">迁移状态</button>
        </div>

        <!-- 字段目录 -->
        <template v-if="activeTab === 'fields'">
          <div class="filters-grid governance-field-filters">
            <div class="filter-field"><label>搜索</label><input v-model="fieldQuery" placeholder="字段名 / 资产名" /></div>
            <div class="filter-field"><label>层级</label>
              <select v-model="fieldLayerFilter"><option value="">全部</option><option value="对象">对象层</option><option value="事实">事实层</option><option value="基线">基线层</option><option value="元数据">元数据层</option><option value="参考">参考层</option></select>
            </div>
            <div class="filter-field"><label>类型</label>
              <select v-model="fieldTypeFilter"><option value="">全部</option><option value="text">字符串</option><option value="numeric">数值</option><option value="boolean">布尔</option></select>
            </div>
            <div class="filter-field"><label>核心</label>
              <select v-model="fieldCoreFilter"><option value="">全部</option><option value="yes">是</option><option value="no">否</option></select>
            </div>
          </div>
          <div class="table-wrap">
            <table class="table table--compact">
              <thead><tr><th>资产</th><th>字段名</th><th>层级</th><th>类型</th><th>核心</th><th>迁移</th></tr></thead>
              <tbody>
                <tr v-for="row in filteredFields" :key="row.asset_name + row.field_name">
                  <td>{{ row.asset_name }}</td>
                  <td class="mono">{{ row.field_name }}</td>
                  <td>{{ row.layer }}</td>
                  <td>{{ row.type }}</td>
                  <td>{{ row.is_core ? '是' : '否' }}</td>
                  <td>{{ row.migration }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- 表目录 -->
        <template v-else-if="activeTab === 'tables'">
          <div class="filters-grid governance-table-filters">
            <div class="filter-field"><label>搜索表</label><input v-model="tableQuery" placeholder="表名" /></div>
            <div class="filter-field"><label>迁移状态</label>
              <select v-model="tableMigrationFilter"><option value="">全部</option><option value="direct_reuse">直接复用</option><option value="restructure">重组迁移</option><option value="reference_only">仅参考</option><option value="retire">可淘汰</option></select>
            </div>
          </div>
          <div class="table-wrap">
            <table class="table table--compact">
              <thead><tr><th>表名</th><th>表类型</th><th>迁移</th><th>使用情况</th></tr></thead>
              <tbody>
                <tr v-for="row in filteredTables" :key="row.table_name">
                  <td class="mono">{{ row.table_name }}</td>
                  <td>{{ row.table_type }}</td>
                  <td>{{ migrationLabel(row.migration) }}</td>
                  <td>{{ row.usage }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- 实际使用 -->
        <template v-else-if="activeTab === 'usage'">
          <div class="governance-usage-layout">
            <div class="governance-usage-list">
              <button v-for="row in tables" :key="row.table_name" class="inline-button governance-usage-button" :class="{ 'tab-button--active': selectedTable === row.table_name }" @click="selectTable(row.table_name)">
                <strong>{{ row.table_name }}</strong>
              </button>
            </div>
            <div class="panel">
              <div class="text-sm font-semibold">{{ selectedTable }}</div>
              <div v-if="usageError" class="text-muted text-sm governance-usage-state">{{ usageError }}</div>
              <template v-else-if="usage">
                <div class="governance-usage-block"><span class="text-muted text-sm">消费方</span>
                  <ul class="governance-usage-listing">
                    <li v-for="item in usage.consumers || []" :key="item.consumer_name">{{ item.consumer_type }} · {{ item.consumer_name }} · {{ item.role }}</li>
                  </ul>
                </div>
                <div class="governance-usage-block"><span class="text-muted text-sm">上游</span>
                  <div class="badge-row governance-upstream-row">
                    <span v-for="item in usage.upstream || []" :key="item" class="badge badge-insufficient">{{ item }}</span>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>

        <!-- 迁移状态 -->
        <template v-else>
          <div class="governance-migration-grid">
            <div v-for="group in migrationGroups" :key="group.key" class="panel">
              <div class="flex-row gap-2 governance-migration-head"><strong>{{ group.label }}</strong><span class="badge" :class="group.badgeClass">{{ group.items.length }}</span></div>
              <ul class="governance-migration-list">
                <li v-for="item in group.items" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import DataOriginBanner from '../components/DataOriginBanner.vue';
import { api } from '../lib/api';

const loading = ref(false); const error = ref('');
const overview = ref<any>(null);
const fields = ref<any[]>([]); const tables = ref<any[]>([]);
const migration = ref<any>(null); const usage = ref<any>(null);
const meta = ref({ origin: '', subjectNote: '' });
const selectedTable = ref('rebuild3.obj_cell'); const usageError = ref('');
const activeTab = ref<'fields'|'tables'|'usage'|'migration'>('fields');
const fieldQuery = ref(''); const tableQuery = ref('');
const fieldLayerFilter = ref(''); const fieldTypeFilter = ref(''); const fieldCoreFilter = ref('');
const tableMigrationFilter = ref('');

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function migrationLabel(value: string): string {
  return {
    direct_reuse: '直接复用',
    restructure: '重组迁移',
    reference_only: '仅参考',
    retire: '可淘汰',
  }[value] || value;
}

const filteredFields = computed(() => {
  let rows = fields.value;
  const q = fieldQuery.value.trim().toLowerCase();
  if (q) rows = rows.filter(r => `${r.asset_name} ${r.field_name}`.toLowerCase().includes(q));
  if (fieldLayerFilter.value) rows = rows.filter(r => r.layer === fieldLayerFilter.value);
  if (fieldTypeFilter.value) rows = rows.filter(r => r.type === fieldTypeFilter.value);
  if (fieldCoreFilter.value) rows = rows.filter(r => fieldCoreFilter.value === 'yes' ? r.is_core : !r.is_core);
  return rows;
});

const filteredTables = computed(() => {
  let rows = tables.value;
  const q = tableQuery.value.trim().toLowerCase();
  if (q) rows = rows.filter(r => r.table_name.toLowerCase().includes(q));
  if (tableMigrationFilter.value) rows = rows.filter(r => r.migration === tableMigrationFilter.value);
  return rows;
});

const migrationGroups = computed(() => {
  const g = migration.value ?? {};
  return [
    { key: 'direct_reuse', label: '直接复用', badgeClass: 'badge-active', items: g.direct_reuse ?? [] },
    { key: 'restructure', label: '重组迁移', badgeClass: 'badge-dynamic', items: g.restructure ?? [] },
    { key: 'reference_only', label: '仅参考', badgeClass: 'badge-gps-bias', items: g.reference_only ?? [] },
    { key: 'retire', label: '可淘汰/已替换', badgeClass: 'badge-rejected', items: g.retire ?? [] },
  ];
});

async function selectTable(name: string) {
  selectedTable.value = name; usageError.value = ''; usage.value = null;
  try { const p = await api.getGovernanceUsage(name); usage.value = p.detail; }
  catch (e) { usageError.value = e instanceof Error ? e.message : '未登记'; }
}

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const [o, f, t, m] = await Promise.all([api.getGovernanceOverview(), api.getGovernanceFields(), api.getGovernanceTables(), api.getGovernanceMigration()]);
    overview.value = o.overview; fields.value = f.rows ?? []; tables.value = t.rows ?? []; migration.value = m.groups;
    meta.value = { origin: o.data_origin || f.data_origin || '', subjectNote: o.subject_note || f.subject_note || '' };
    await selectTable(selectedTable.value);
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

onMounted(loadPage);
</script>

<style scoped>
.governance-summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.governance-tab-row,
.governance-field-filters,
.governance-table-filters {
  margin-bottom: 16px;
}

.governance-field-filters {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.governance-table-filters {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  max-width: 480px;
}

.governance-usage-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.8fr);
  gap: 20px;
}

.governance-usage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.governance-usage-button {
  justify-content: flex-start;
  text-align: left;
}

.governance-usage-state,
.governance-usage-block {
  margin-top: 12px;
}

.governance-usage-listing,
.governance-migration-list {
  padding-left: 18px;
  font-size: 13px;
  color: var(--gray-600);
}

.governance-usage-listing {
  margin-top: 4px;
}

.governance-upstream-row,
.governance-migration-head {
  margin-top: 4px;
}

.governance-migration-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.governance-migration-head {
  margin-bottom: 8px;
}

.governance-migration-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

@media (max-width: 900px) {
  .governance-summary-grid,
  .governance-field-filters,
  .governance-migration-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .governance-usage-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .governance-summary-grid,
  .governance-field-filters,
  .governance-table-filters,
  .governance-migration-grid {
    grid-template-columns: 1fr;
  }

  .governance-usage-list {
    gap: 6px;
  }
}
</style>
