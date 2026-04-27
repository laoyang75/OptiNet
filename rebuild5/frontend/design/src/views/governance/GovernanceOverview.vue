<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import Pagination from '../../components/common/Pagination.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import {
  getMaintenanceStats, getCollisionList, getAntitoxinHits, getExitWarnings,
  runMaintenance,
  type MaintenanceStatsPayload, type CollisionItem, type AntitoxinHitItem, type ExitWarningItem,
} from '../../api/maintenance'
import { fmt } from '../../composables/useFormat'
import { DRIFT_LABELS, type DriftPattern } from '../../types'

// 8 类对齐 fix5/fix6/loop_optim 后的实际 drift_pattern 落库分类
// (moderate_drift 是 PG17 时代旧值,新数据不再产生,展示用 fallback)
const driftKeys: DriftPattern[] = [
  'stable', 'large_coverage', 'dual_cluster', 'uncertain',
  'oversize_single', 'migration', 'collision', 'insufficient',
]

const running = ref(false)
const stats = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0, published_bs_count: 0, published_lac_count: 0,
    collision_cell_count: 0, multi_centroid_cell_count: 0, dynamic_cell_count: 0, anomaly_bs_count: 0,
  },
  drift_distribution: {},
})

// Collision
const collisionItems = ref<CollisionItem[]>([])
const collisionPage = ref(1)
const collisionTotal = ref(0)
const collisionTotalPages = ref(0)
const expandedCollisionIdx = ref<number | null>(null)

// Antitoxin
const antitoxinItems = ref<AntitoxinHitItem[]>([])
const antitoxinPage = ref(1)
const antitoxinTotal = ref(0)
const antitoxinTotalPages = ref(0)

// Exit warnings
const exitItems = ref<ExitWarningItem[]>([])
const exitPage = ref(1)
const exitTotal = ref(0)
const exitTotalPages = ref(0)

// Drift distribution(8 类对齐 fix5/fix6/loop_optim 后实际落库分类)
const driftDist = computed<Record<DriftPattern, number>>(() => {
  const d = stats.value.drift_distribution as Record<string, unknown>
  return {
    stable: Number(d.stable ?? 0),
    large_coverage: Number(d.large_coverage ?? 0),
    dual_cluster: Number(d.dual_cluster ?? 0),
    uncertain: Number(d.uncertain ?? 0),
    oversize_single: Number(d.oversize_single ?? 0),
    migration: Number(d.migration ?? 0),
    collision: Number(d.collision ?? 0),
    insufficient: Number(d.insufficient ?? 0),
    dynamic: Number(d.dynamic ?? 0),
    moderate_drift: Number(d.moderate_drift ?? 0),  // PG17 时代旧值,fallback
  }
})
const driftMax = computed(() => Math.max(...Object.values(driftDist.value), 1))

function fmtTime(v: string | null): string {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 19)
}

function triggerLabel(item: AntitoxinHitItem): string {
  const parts: string[] = []
  if (item.centroid_shift_m != null && item.centroid_shift_m > 0) parts.push(`质心偏移 ${Math.round(item.centroid_shift_m)}m`)
  if (item.p90_ratio != null && item.p90_ratio > 1.5) parts.push(`P90 膨胀 ${item.p90_ratio.toFixed(1)}x`)
  if (item.dev_ratio != null && item.dev_ratio > 2) parts.push(`设备突增 ${item.dev_ratio.toFixed(1)}x`)
  return parts.length > 0 ? parts.join(' / ') : '综合判定'
}

const densityCfg: Record<string, { label: string; style: string }> = {
  high: { label: '高密度', style: 'background:#fee2e2;color:#991b1b' },
  mid: { label: '中密度', style: 'background:#fef3c7;color:#92400e' },
  low: { label: '低密度', style: 'background:#f3f4f6;color:#6b7280' },
}

function toggleCollision(idx: number) { expandedCollisionIdx.value = expandedCollisionIdx.value === idx ? null : idx }

async function loadCollision() {
  try {
    const p = await getCollisionList(collisionPage.value, 20)
    collisionItems.value = p.items; collisionTotal.value = p.totalCount; collisionTotalPages.value = p.totalPages
  } catch { collisionItems.value = [] }
}

async function loadAntitoxin() {
  try {
    const p = await getAntitoxinHits(antitoxinPage.value, 20)
    antitoxinItems.value = p.items; antitoxinTotal.value = p.totalCount; antitoxinTotalPages.value = p.totalPages
  } catch { antitoxinItems.value = [] }
}

async function loadExit() {
  try {
    const p = await getExitWarnings(exitPage.value, 20)
    exitItems.value = p.items; exitTotal.value = p.totalCount; exitTotalPages.value = p.totalPages
  } catch { exitItems.value = [] }
}

async function doRun() {
  running.value = true
  try {
    await runMaintenance()
    await loadAll()
  } catch { /* */ }
  finally { running.value = false }
}

async function loadAll() {
  const [statsP] = await Promise.all([
    getMaintenanceStats().catch(() => stats.value),
    loadCollision(),
    loadAntitoxin(),
    loadExit(),
  ])
  stats.value = statsP
}

onMounted(loadAll)
</script>

<template>
  <PageHeader title="治理总览" description="跨层级治理事件看板 — Step 5 运行后的治理概况和关键变化。">
    <div class="text-xs text-secondary">
      数据集 {{ stats.version.dataset_key }} ｜ {{ stats.version.snapshot_version_prev }} → {{ stats.version.snapshot_version }}
      <button class="btn btn-sm ml-md" :disabled="running" @click="doRun">{{ running ? '运行中...' : '运行 Step 5' }}</button>
    </div>
  </PageHeader>

  <!-- 集群版本信息条(2026-04-27 PG18 升级后)-->
  <!-- 注:静态展示,版本变化时手动更新此处 -->
  <div class="cluster-info-bar mb-md">
    <span class="info-pill"><span class="info-label">PostgreSQL</span> 18.3</span>
    <span class="info-pill"><span class="info-label">Citus</span> 14.0-1</span>
    <span class="info-pill"><span class="info-label">PostGIS</span> 3.6.3</span>
    <span class="info-pill"><span class="info-label">集群</span> 1 coord + 4 worker @ 5488</span>
    <span class="info-pill info-pill-fallback"><span class="info-label">PG17 fallback</span> 5487(观察期)</span>
  </div>

  <!-- Section 1: Key change cards -->
  <div class="grid grid-6 mb-lg">
    <SummaryCard title="发布 Cell 数" :value="fmt(stats.summary.published_cell_count)" />
    <SummaryCard title="碰撞 Cell" :value="fmt(stats.summary.collision_cell_count)" color="var(--c-danger)" />
    <SummaryCard title="防毒化阻断" :value="fmt(antitoxinTotal)" color="#b91c1c" />
    <SummaryCard title="退出预警" :value="fmt(exitTotal)" color="var(--c-dormant)" />
    <SummaryCard title="多质心" :value="fmt(stats.summary.multi_centroid_cell_count)" color="#7c3aed" />
    <SummaryCard title="动态 Cell" :value="fmt(stats.summary.dynamic_cell_count)" color="var(--c-warning)" />
  </div>

  <!-- Section 2: Collision table -->
  <div class="card mb-lg" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">碰撞全局表 · {{ fmt(collisionTotal) }} 条</span>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead><tr>
        <th style="width:20px"></th>
        <th>Cell ID</th><th>Combo 数</th><th>主导 Combo</th><th>版本</th>
      </tr></thead>
      <tbody>
        <template v-for="(item, idx) in collisionItems" :key="item.cell_id">
          <tr class="clickable-row" @click="toggleCollision(idx)">
            <td class="expand-icon">{{ expandedCollisionIdx === idx ? '▾' : '▸' }}</td>
            <td class="font-mono font-semibold">{{ item.cell_id }}</td>
            <td class="font-mono">{{ item.collision_combo_count }}</td>
            <td class="text-xs">{{ item.dominant_combo || '-' }}</td>
            <td class="text-xs font-mono">{{ item.snapshot_version }}</td>
          </tr>
          <tr v-if="expandedCollisionIdx === idx" class="detail-row">
            <td :colspan="5">
              <div class="detail-content">
                <div class="section-title">Combo 明细</div>
                <div class="combo-list">
                  <div v-for="(combo, ci) in item.combo_keys_json" :key="ci" class="combo-item font-mono text-xs">
                    {{ JSON.stringify(combo) }}
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="collisionItems.length === 0"><td colspan="5" class="empty-row">暂无碰撞数据</td></tr>
      </tbody>
    </table>
    <div style="padding:0 var(--sp-lg) var(--sp-lg)">
      <Pagination :page="collisionPage" :page-size="20" :total-count="collisionTotal" :total-pages="collisionTotalPages" @update:page="p => { collisionPage = p; loadCollision() }" />
    </div>
  </div>

  <!-- Section 3: Antitoxin hits -->
  <div class="card mb-lg" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">防毒化阻断列表 · {{ fmt(antitoxinTotal) }} 条</span>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead><tr>
        <th>运营商</th><th>LAC</th><th>Cell ID</th><th>触发维度</th>
        <th>质心偏移(m)</th><th>P90 旧→新</th><th>设备 旧→新</th>
      </tr></thead>
      <tbody>
        <tr v-for="item in antitoxinItems" :key="`${item.operator_code}-${item.lac}-${item.cell_id}`">
          <td class="text-xs">{{ item.operator_cn || item.operator_code }}</td>
          <td class="font-mono">{{ item.lac }}</td>
          <td class="font-mono font-semibold">{{ item.cell_id }}</td>
          <td class="text-xs"><span class="tag tag-danger">{{ triggerLabel(item) }}</span></td>
          <td class="font-mono">{{ item.centroid_shift_m != null ? Math.round(item.centroid_shift_m) : '-' }}</td>
          <td class="font-mono text-xs">{{ item.prev_p90_radius_m != null ? Math.round(item.prev_p90_radius_m) : '-' }} → {{ item.curr_p90_radius_m != null ? Math.round(item.curr_p90_radius_m) : '-' }}</td>
          <td class="font-mono text-xs">{{ item.prev_distinct_dev_id ?? '-' }} → {{ item.curr_distinct_dev_id ?? '-' }}</td>
        </tr>
        <tr v-if="antitoxinItems.length === 0"><td colspan="7" class="empty-row">暂无防毒化阻断</td></tr>
      </tbody>
    </table>
    <div style="padding:0 var(--sp-lg) var(--sp-lg)">
      <Pagination :page="antitoxinPage" :page-size="20" :total-count="antitoxinTotal" :total-pages="antitoxinTotalPages" @update:page="p => { antitoxinPage = p; loadAntitoxin() }" />
    </div>
  </div>

  <!-- Section 4: Exit warnings -->
  <div class="card mb-lg" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">退出预警列表 · {{ fmt(exitTotal) }} 条</span>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead><tr>
        <th>运营商</th><th>LAC</th><th>Cell ID</th><th>密度等级</th>
        <th>活跃天数(30d)</th><th>连续不活跃</th><th>阈值</th><th>紧迫度</th><th>最后观测</th>
      </tr></thead>
      <tbody>
        <tr v-for="item in exitItems" :key="`${item.operator_code}-${item.lac}-${item.cell_id}`">
          <td class="text-xs">{{ item.operator_cn || item.operator_code }}</td>
          <td class="font-mono">{{ item.lac }}</td>
          <td class="font-mono font-semibold">{{ item.cell_id }}</td>
          <td><span class="tag" :style="(densityCfg[item.density_level] || densityCfg.low).style">{{ (densityCfg[item.density_level] || densityCfg.low).label }}</span></td>
          <td class="font-mono">{{ item.active_days_30d }}</td>
          <td class="font-mono">{{ item.consecutive_inactive_days }}d</td>
          <td class="font-mono">{{ item.dormant_threshold_days }}d</td>
          <td>
            <PercentBar :value="Math.min(item.urgency_ratio, 1)" :color="item.urgency_ratio >= 0.8 ? 'var(--c-danger)' : item.urgency_ratio >= 0.5 ? 'var(--c-warning)' : 'var(--c-success)'" />
          </td>
          <td class="text-xs">{{ fmtTime(item.last_observed_at) }}</td>
        </tr>
        <tr v-if="exitItems.length === 0"><td colspan="9" class="empty-row">暂无退出预警</td></tr>
      </tbody>
    </table>
    <div style="padding:0 var(--sp-lg) var(--sp-lg)">
      <Pagination :page="exitPage" :page-size="20" :total-count="exitTotal" :total-pages="exitTotalPages" @update:page="p => { exitPage = p; loadExit() }" />
    </div>
  </div>

  <!-- Section 5: Drift distribution -->
  <div class="card">
    <div class="font-semibold text-sm mb-md">漂移分类全局分布</div>
    <div class="drift-chart">
      <div v-for="p in driftKeys" :key="p" class="drift-row">
        <span class="drift-label text-xs">{{ DRIFT_LABELS[p] }}</span>
        <div class="drift-bar-track">
          <div class="drift-bar-fill" :class="`drift-${p}`" :style="{ width: driftMax > 0 ? `${(driftDist[p] / driftMax) * 100}%` : '0%' }"></div>
        </div>
        <span class="drift-count font-mono text-xs">{{ fmt(driftDist[p]) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid-6 { display: grid; grid-template-columns: repeat(6, 1fr); gap: var(--sp-md); }
.ml-md { margin-left: var(--sp-md); }
.btn-sm { padding: 3px 10px; font-size: 11px; }

.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--c-bg); }
.expand-icon { font-size: 10px; color: var(--c-text-muted); text-align: center; }

.detail-row td { background: var(--c-bg); padding: 0 !important; }
.detail-content { padding: 16px 20px; }
.section-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--c-text-muted); border-bottom: 1px solid var(--c-border); padding-bottom: 3px; margin-bottom: 6px;
}
.combo-list { display: flex; flex-direction: column; gap: 4px; }
.combo-item {
  padding: 4px 8px; background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: var(--radius-sm); word-break: break-all;
}

.tag-danger { background: #fee2e2; color: #991b1b; }

.drift-chart { display: flex; flex-direction: column; gap: 8px; }
.drift-row { display: flex; align-items: center; gap: var(--sp-md); }
.drift-label { width: 64px; text-align: right; flex-shrink: 0; color: var(--c-text-secondary); }
.drift-bar-track { flex: 1; height: 16px; background: var(--c-bg); border-radius: 3px; overflow: hidden; }
.drift-bar-fill { height: 100%; border-radius: 3px; min-width: 2px; transition: width 0.3s; }
.drift-count { width: 48px; text-align: right; flex-shrink: 0; }

.drift-stable { background: var(--c-success); }
.drift-collision { background: var(--c-danger); }
.drift-migration { background: #7c3aed; }
.drift-large_coverage { background: var(--c-warning); }
.drift-moderate_drift { background: var(--c-dormant); }
.drift-insufficient { background: var(--c-waiting); }
/* fix5/fix6 新增 4 类 */
.drift-dual_cluster { background: #f97316; }       /* 双质心 - orange */
.drift-uncertain { background: #ec4899; }          /* 多质心 - pink */
.drift-oversize_single { background: #06b6d4; }    /* 单簇超大 - cyan */
.drift-dynamic { background: #ef4444; }            /* 动态 - red */

.empty-row { padding: 20px; text-align: center; color: var(--c-text-muted); }

/* 集群版本信息条 */
.cluster-info-bar {
  display: flex; flex-wrap: wrap; gap: var(--sp-sm);
  padding: var(--sp-sm) var(--sp-md); background: var(--c-bg);
  border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  font-size: 11px;
}
.info-pill {
  padding: 3px 10px; background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; color: var(--c-text-secondary);
}
.info-pill .info-label {
  color: var(--c-text-muted); margin-right: 4px;
}
.info-pill-fallback {
  background: #fef3c7; border-color: #fde68a; color: #92400e;
}
</style>
