<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import {
  getGovernanceOverview,
  getGovernanceFields, getGovernanceTables, getGovernanceUsage, getGovernanceMigration,
  getGovernanceFieldAudit, getGovernanceTargetFields,
  getGovernanceOdsRules, getGovernanceOdsExecutions, getGovernanceParseRules, getGovernanceComplianceRules,
  getGovernanceTrustedLoss,
} from '../lib/api'

const loading = ref(true)
const error = ref('')
const overview = ref<Record<string, any>>({})

/* Tab system */
type TabKey = 'fields' | 'tables' | 'usage' | 'migration' | 'field_audit' | 'target_fields' | 'ods_rules' | 'ods_executions' | 'parse_rules' | 'compliance_rules' | 'trusted_loss'

interface TabGroup { title: string; tabs: { key: TabKey; label: string }[] }
const tabGroups: TabGroup[] = [
  { title: '资产管理', tabs: [
    { key: 'fields', label: '字段目录' },
    { key: 'tables', label: '表目录' },
    { key: 'usage', label: '使用关系' },
    { key: 'migration', label: '迁移状态' },
  ]},
  { title: '字段审计', tabs: [
    { key: 'field_audit', label: '字段审计' },
    { key: 'target_fields', label: '目标字段' },
  ]},
  { title: '规则体系', tabs: [
    { key: 'ods_rules', label: 'ODS规则' },
    { key: 'ods_executions', label: 'ODS执行' },
    { key: 'parse_rules', label: '解析规则' },
    { key: 'compliance_rules', label: '合规规则' },
  ]},
  { title: '损耗分析', tabs: [
    { key: 'trusted_loss', label: 'trusted_loss' },
  ]},
]

const activeTab = ref<TabKey>('fields')
const tabLoading = ref(false)
const tabData = ref<any[]>([])
const tabExtra = ref<Record<string, any>>({})

/* usage sub */
const usageTable = ref('')

function fmt(n: any) {
  return typeof n === 'number' ? n.toLocaleString() : (n ?? '-')
}

function pctFmt(n: any) {
  if (typeof n !== 'number') return '-'
  return n.toFixed(2) + '%'
}

/* migration label helper */
function migrationLabel(status: string): string {
  const map: Record<string, string> = {
    direct_reuse: '直接复用',
    restructure: '重组迁移',
    reference_only: '仅参考',
    deprecate: '可淘汰',
  }
  return map[status] || status || '-'
}

async function loadTab() {
  tabLoading.value = true
  tabData.value = []
  tabExtra.value = {}
  try {
    switch (activeTab.value) {
      case 'fields': { const r = await getGovernanceFields(); tabData.value = r.data || []; break }
      case 'tables': { const r = await getGovernanceTables(); tabData.value = r.data || []; break }
      case 'usage': {
        if (usageTable.value) {
          const r = await getGovernanceUsage(usageTable.value); tabData.value = r.data || []
        } else {
          tabData.value = []
        }
        break
      }
      case 'migration': { const r = await getGovernanceMigration(); tabData.value = r.data || []; break }
      case 'field_audit': { const r = await getGovernanceFieldAudit(); tabData.value = r.data || []; break }
      case 'target_fields': { const r = await getGovernanceTargetFields(); tabData.value = r.data || []; break }
      case 'ods_rules': { const r = await getGovernanceOdsRules(); tabData.value = r.data || []; break }
      case 'ods_executions': { const r = await getGovernanceOdsExecutions(); tabData.value = r.data || []; break }
      case 'parse_rules': { const r = await getGovernanceParseRules(); tabData.value = r.data || []; break }
      case 'compliance_rules': { const r = await getGovernanceComplianceRules(); tabData.value = r.data || []; break }
      case 'trusted_loss': {
        const [ovRes, bdRes] = await Promise.all([
          getGovernanceTrustedLoss('overview'),
          getGovernanceTrustedLoss('breakdown'),
        ])
        tabExtra.value = ovRes.data || {}
        tabData.value = Array.isArray(bdRes.data) ? bdRes.data : []
        break
      }
    }
  } catch (e: any) {
    tabData.value = []
  } finally {
    tabLoading.value = false
  }
}

function switchTab(key: TabKey) {
  activeTab.value = key
  loadTab()
}

function loadUsage() {
  if (usageTable.value) loadTab()
}

onMounted(async () => {
  try {
    const res = await getGovernanceOverview()
    overview.value = res.data || {}
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
  loadTab()
})

/* overview cards */
const overviewCards = [
  { key: 'field_count', label: '字段数量' },
  { key: 'table_count', label: '表数量' },
  { key: 'usage_registrations', label: '使用登记' },
  { key: 'migration_decisions', label: '迁移决策' },
  { key: 'active_parse_rules', label: '解析规则' },
  { key: 'active_compliance_rules', label: '合规规则' },
]
</script>

<template>
  <div class="page">
    <h2 class="page-title">基础数据治理</h2>

    <div v-if="loading" class="empty-state">加载中…</div>
    <div v-else-if="error" class="empty-state" style="color:var(--red-600)">{{ error }}</div>
    <template v-else>

      <!-- Overview 6 cards -->
      <div class="grid-6">
        <div v-for="c in overviewCards" :key="c.key" class="stat-card">
          <div class="card-label">{{ c.label }}</div>
          <div class="card-value">{{ fmt(overview[c.key]) }}</div>
        </div>
      </div>

      <!-- Tab groups -->
      <div class="tab-nav">
        <template v-for="group in tabGroups" :key="group.title">
          <span class="tab-group-title">{{ group.title }}</span>
          <button
            v-for="tab in group.tabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            @click="switchTab(tab.key)"
          >{{ tab.label }}</button>
        </template>
      </div>

      <!-- Tab content -->
      <div class="tab-content">
        <div v-if="tabLoading" class="empty-state">加载中…</div>

        <!-- usage: needs table name input -->
        <template v-else-if="activeTab === 'usage'">
          <div class="filter-bar" style="margin-bottom:12px;">
            <input v-model="usageTable" class="input-control" placeholder="输入表名查询使用关系" @keyup.enter="loadUsage" />
            <button class="btn" @click="loadUsage">搜索</button>
          </div>
          <div v-if="tabData.length === 0" class="empty-state">{{ usageTable ? '无数据' : '请输入表名' }}</div>
          <table v-else class="data-table">
            <thead><tr><th v-for="col in Object.keys(tabData[0])" :key="col">{{ col }}</th></tr></thead>
            <tbody><tr v-for="(row, i) in tabData" :key="i"><td v-for="col in Object.keys(tabData[0])" :key="col">{{ fmt(row[col]) }}</td></tr></tbody>
          </table>
        </template>

        <!-- trusted_loss -->
        <template v-else-if="activeTab === 'trusted_loss'">
          <div class="loss-overview">
            <div class="loss-stat"><span class="loss-label">总量</span><span class="loss-value">{{ fmt(tabExtra.total_rows) }}</span></div>
            <div class="loss-stat"><span class="loss-label">可信</span><span class="loss-value">{{ fmt(tabExtra.trusted_rows) }}</span></div>
            <div class="loss-stat"><span class="loss-label">过滤</span><span class="loss-value">{{ fmt(tabExtra.filtered_rows) }}</span></div>
            <div class="loss-stat"><span class="loss-label">过滤率</span><span class="loss-value">{{ pctFmt(tabExtra.filtered_pct) }}</span></div>
            <div class="loss-stat"><span class="loss-label">有信号</span><span class="loss-value">{{ fmt(tabExtra.filtered_with_rsrp) }}</span></div>
            <div class="loss-stat"><span class="loss-label">有经纬度</span><span class="loss-value">{{ fmt(tabExtra.filtered_with_lon_lat) }}</span></div>
          </div>
          <div v-if="tabData.length === 0" class="empty-state">无明细数据</div>
          <table v-else class="data-table">
            <thead><tr><th v-for="col in Object.keys(tabData[0])" :key="col">{{ col }}</th></tr></thead>
            <tbody><tr v-for="(row, i) in tabData" :key="i"><td v-for="col in Object.keys(tabData[0])" :key="col">{{ fmt(row[col]) }}</td></tr></tbody>
          </table>
        </template>

        <!-- migration -->
        <template v-else-if="activeTab === 'migration'">
          <div v-if="tabData.length === 0" class="empty-state">暂无数据</div>
          <table v-else class="data-table">
            <thead><tr><th v-for="col in Object.keys(tabData[0])" :key="col">{{ col }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in tabData" :key="i">
                <td v-for="col in Object.keys(tabData[0])" :key="col">
                  <template v-if="col === 'migration_status'">{{ migrationLabel(row[col]) }}</template>
                  <template v-else>{{ fmt(row[col]) }}</template>
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- parse_rules -->
        <template v-else-if="activeTab === 'parse_rules'">
          <div v-if="tabData.length === 0" class="empty-state">暂无数据</div>
          <table v-else class="data-table">
            <thead>
              <tr>
                <th>rule_code</th>
                <th>source_reference</th>
                <th>fail_action</th>
                <th>severity</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in tabData" :key="i">
                <td class="mono">{{ row.rule_code ?? '-' }}</td>
                <td>{{ row.source_reference ?? '-' }}</td>
                <td>{{ row.fail_action ?? '-' }}</td>
                <td>{{ row.severity ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- compliance_rules -->
        <template v-else-if="activeTab === 'compliance_rules'">
          <div v-if="tabData.length === 0" class="empty-state">暂无数据</div>
          <table v-else class="data-table">
            <thead>
              <tr>
                <th>source_field</th>
                <th>target_field</th>
                <th>check_field</th>
                <th>source_reference</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in tabData" :key="i">
                <td class="mono">{{ row.source_field ?? '-' }}</td>
                <td class="mono">{{ row.target_field ?? '-' }}</td>
                <td class="mono">{{ row.check_field ?? '-' }}</td>
                <td>{{ row.source_reference ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- generic table for other tabs -->
        <template v-else>
          <div v-if="tabData.length === 0" class="empty-state">暂无数据</div>
          <table v-else class="data-table">
            <thead><tr><th v-for="col in Object.keys(tabData[0])" :key="col">{{ col }}</th></tr></thead>
            <tbody><tr v-for="(row, i) in tabData" :key="i"><td v-for="col in Object.keys(tabData[0])" :key="col">{{ fmt(row[col]) }}</td></tr></tbody>
          </table>
        </template>
      </div>

    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 16px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-h); margin: 0 0 16px; }

.grid-6 { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 20px; }
.stat-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.card-label { font-size: 11px; color: var(--text); margin-bottom: 4px; }
.card-value { font-size: 20px; font-weight: 700; color: var(--text-h); }

/* Tab navigation */
.tab-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.tab-group-title { font-size: 11px; font-weight: 600; color: var(--text); padding: 4px 6px; margin-left: 8px; }
.tab-group-title:first-child { margin-left: 0; }
.tab-btn { padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; cursor: pointer; background: var(--bg); color: var(--text); transition: all 0.15s; }
.tab-btn:hover { background: var(--accent-bg); }
.tab-btn.active { background: var(--accent-bg); color: var(--accent); border-color: var(--accent-border); font-weight: 600; }

.tab-content { min-height: 200px; }

.filter-bar { display: flex; gap: 8px; }
.input-control { flex: 1; max-width: 360px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--bg); color: var(--text); }
.btn { padding: 6px 16px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; cursor: pointer; background: var(--bg); color: var(--text-h); }
.btn:hover { background: var(--accent-bg); }

/* Trusted loss overview */
.loss-overview { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }
.loss-stat { background: var(--code-bg); border-radius: 8px; padding: 12px 14px; }
.loss-label { display: block; font-size: 11px; color: var(--text); margin-bottom: 4px; }
.loss-value { display: block; font-size: 18px; font-weight: 700; color: var(--text-h); }

/* Table */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 12px; color: var(--text); white-space: nowrap; }
.data-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); color: var(--text-h); }
.mono { font-family: var(--mono); font-size: 12px; }

.empty-state { text-align: center; padding: 48px 16px; color: var(--text); font-size: 14px; }
</style>
