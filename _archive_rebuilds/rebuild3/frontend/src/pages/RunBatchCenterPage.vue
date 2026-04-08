<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载批次中心...</div>

    <template v-else>
      <DataOriginBanner :origin="payload?.data_origin" :subject-note="payload?.subject_note" :show-synthetic="true" />

      <div v-if="!runRows.length" class="page-empty">
        {{ payload?.empty_state?.description || '当前暂无运行批次。' }}
      </div>

      <template v-else>
        <div class="section">
          <div class="section-title">运行列表</div>
          <div class="table-wrap">
            <table class="table table--compact">
              <thead>
                <tr>
                  <th>场景 / run_id</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>批次数</th>
                  <th>最近快照</th>
                  <th>主语</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in runRows"
                  :key="row.run_id"
                  class="is-expandable"
                  :class="{ 'is-selected': selectedRunId === row.run_id }"
                  @click="selectRun(row.run_id)"
                >
                  <td>
                    <div class="text-sm font-semibold" style="display:flex;align-items:center;gap:8px;">
                      <span>{{ row.label }}</span>
                      <OriginBadge :origin="row.data_origin" />
                    </div>
                    <div class="mono text-sm">{{ row.run_id }}</div>
                    <div class="text-muted text-sm">{{ row.note || '—' }}</div>
                  </td>
                  <td>{{ runTypeLabel(row) }}</td>
                  <td>{{ statusLabel(row.status) }}</td>
                  <td>{{ fmtN(row.completed_batch_count) }} / {{ fmtN(row.batch_count) }}</td>
                  <td>{{ shortTime(row.last_snapshot_time) }}</td>
                  <td>{{ subjectLabel(row.subject_scope) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="selectedRun" class="section">
          <div class="section-title" style="display:flex;align-items:center;gap:8px;">
            <span>批次子列表</span>
            <OriginBadge :origin="selectedRun.data_origin" />
          </div>
          <div class="text-muted text-sm" style="margin-bottom:12px;">
            {{ selectedRun.note || '当前 run 无补充说明。' }}
          </div>

          <div class="tab-row" style="margin-bottom: 12px;">
            <button class="tab-button" :class="{ 'tab-button--active': filterType === '' }" @click="filterType = ''">全部</button>
            <button class="tab-button" :class="{ 'tab-button--active': filterType === 'normal' }" @click="filterType = 'normal'">正常</button>
            <button class="tab-button" :class="{ 'tab-button--active': filterType === 'rerun' }" @click="filterType = 'rerun'">重跑</button>
          </div>

          <div class="table-wrap">
            <table class="table table--compact">
              <thead>
                <tr>
                  <th>角色</th>
                  <th>批次 ID</th>
                  <th>快照时间</th>
                  <th>窗口</th>
                  <th>问题池</th>
                  <th>四分流</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in filteredBatches"
                  :key="row.batch_id"
                  class="is-expandable"
                  :class="{ 'is-selected': selectedBatchId === row.batch_id }"
                  @click="selectBatch(row.batch_id)"
                >
                  <td>
                    <div style="display:flex;align-items:center;gap:8px;">
                      <span>{{ batchRoleLabel(row) }}</span>
                      <OriginBadge :origin="row.data_origin" />
                    </div>
                  </td>
                  <td class="mono">{{ row.batch_id }}</td>
                  <td>{{ shortTime(row.snapshot_at || row.snapshot_recorded_at) }}</td>
                  <td>{{ row.window }}</td>
                  <td>{{ fmtN(row.headline_metric) }}</td>
                  <td class="text-sm">
                    <span v-for="item in (row.flow || []).slice(0, 4)" :key="item.route" style="margin-right:8px;">
                      {{ routeShort(item.route) }} {{ item.ratio != null ? (item.ratio * 100).toFixed(0) + '%' : '' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="selectedRun" class="section">
          <div class="section-title">结构趋势</div>
          <div v-if="!selectedRun.trend?.available" class="page-empty page-empty--compact">
            {{ selectedRun.trend?.label || '真实批次不足，无法形成趋势。' }}
          </div>
          <div v-else class="summary-grid--three" style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;">
            <div v-for="series in selectedRun.trend?.series || []" :key="series.metric" class="summary-card">
              <div class="label">{{ snapshotLabel(series.metric) }}</div>
              <div class="value">{{ fmtN(series.points?.at?.(-1)?.value) }}</div>
              <div class="meta">
                <span>{{ fmtN(series.points?.[0]?.value) }} → {{ fmtN(series.points?.at?.(-1)?.value) }}</span>
                <span :class="trendDeltaClass(series)">Δ {{ fmtSigned(trendDelta(series)) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="detail" class="section">
          <DataOriginBanner :origin="detail.data_origin" :subject-note="detail.subject_note" :show-synthetic="true" />
          <div class="section-title">批次详情 — {{ detail.context?.batch_id }}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
            <div>
              <div class="text-sm font-semibold" style="margin-bottom:8px;">批次上下文</div>
              <div class="bl-kv-list" style="display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;">
                <div><span class="text-muted text-sm">运行 ID</span><strong class="mono" style="display:block;font-size:13px;">{{ detail.context?.run_id }}</strong></div>
                <div><span class="text-muted text-sm">基线版本</span><strong style="display:block;font-size:13px;">{{ detail.context?.baseline_version }}</strong></div>
                <div><span class="text-muted text-sm">规则集版本</span><strong style="display:block;font-size:13px;">{{ detail.context?.rule_set_version }}</strong></div>
                <div><span class="text-muted text-sm">契约版本</span><strong style="display:block;font-size:13px;">{{ detail.context?.contract_version }}</strong></div>
              </div>

              <div class="text-sm font-semibold" style="margin:16px 0 8px;">基线刷新</div>
              <div class="text-muted text-sm">{{ detail.baseline_refresh?.baseline_version || '未刷新' }} — {{ detail.baseline_refresh?.refresh_reason || '—' }}</div>
            </div>

            <div>
              <div class="text-sm font-semibold" style="margin-bottom:8px;">级联摘要</div>
              <div v-if="detail.decision_summary?.lifecycle_distribution" class="text-muted text-sm">
                Cell：活跃 {{ fmtN(decisionCount('cell:active')) }} · 观察 {{ fmtN(decisionCount('cell:observing')) }} · 等待 {{ fmtN(decisionCount('cell:waiting')) }}<br>
                BS：活跃 {{ fmtN(decisionCount('bs:active')) }} · 观察 {{ fmtN(decisionCount('bs:observing')) }}<br>
                LAC：活跃 {{ fmtN(decisionCount('lac:active')) }} · 观察 {{ fmtN(decisionCount('lac:observing')) }}
              </div>
              <div v-else class="text-muted text-sm">无级联数据</div>

              <div class="text-sm font-semibold" style="margin:16px 0 8px;">异常</div>
              <div v-for="item in (detail.anomalies || [])" :key="item.name" class="flex-row gap-2" style="margin-bottom:4px;">
                <HealthBadge :state="item.name" />
                <span class="mono text-sm">{{ item.count }}</span>
              </div>
              <div v-if="!(detail.anomalies || []).length" class="text-muted text-sm">无异常</div>
            </div>
          </div>

          <div class="flex-row gap-4" style="margin-top:16px;">
            <RouterLink class="inline-button" to="/anomalies">异常工作台</RouterLink>
            <RouterLink class="inline-button" to="/baseline">基线/画像</RouterLink>
            <RouterLink class="inline-button" to="/objects">对象浏览</RouterLink>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import DataOriginBanner from '../components/DataOriginBanner.vue';
import HealthBadge from '../components/HealthBadge.vue';
import OriginBadge from '../components/OriginBadge.vue';
import { api } from '../lib/api';

const loading = ref(false);
const error = ref('');
const payload = ref<any>(null);
const detail = ref<any>(null);
const selectedRunId = ref('');
const selectedBatchId = ref('');
const filterType = ref('');

const runRows = computed(() => payload.value?.rows ?? []);
const selectedRun = computed(() => runRows.value.find((row: any) => row.run_id === selectedRunId.value) ?? null);
const filteredBatches = computed(() => {
  const batches = selectedRun.value?.batches ?? [];
  if (!filterType.value) return batches;
  if (filterType.value === 'rerun') return batches.filter((row: any) => row.is_rerun);
  return batches.filter((row: any) => !row.is_rerun);
});

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function fmtSigned(v: number): string { return v > 0 ? `+${fmtN(v)}` : v < 0 ? `-${fmtN(Math.abs(v))}` : '0'; }
function shortTime(value: string | undefined): string { return value ? value.slice(0, 16).replace('T', ' ') : '—'; }
function statusLabel(s: string): string { return { completed: '已完成', running: '运行中', pending: '待处理', failed: '失败' }[s] || s; }
function routeShort(r: string): string { return { fact_governed: '治', fact_pending_observation: '观', fact_pending_issue: '问', fact_rejected: '拒' }[r] || r; }
function subjectLabel(scope: string): string { return { current_batch: '主批次', initialization_run: '初始化主语', validation_reference: '验证参考', baseline_version: '基线版本' }[scope] || scope || '—'; }
function runTypeLabel(row: any): string {
  if (row.run_type === 'scenario_replay') return 'Scenario Replay';
  if (row.run_type === 'full_initialization') return 'Full Initialization';
  return row.run_type || '—';
}
function batchRoleLabel(row: any): string {
  if (row.timepoint_role === 'init') return '初始化批';
  if (row.batch_seq != null) return `批次 #${row.batch_seq}`;
  return row.batch_type || '—';
}

const SNAPSHOT_LABELS: Record<string, string> = {
  fact_standardized: '输入事件', fact_governed: '已治理', fact_pending_observation: '观察池',
  fact_pending_issue: '问题池', fact_rejected: '拒收池', obj_cell: 'Cell 对象',
  obj_bs: 'BS 对象', obj_lac: 'LAC 对象', baseline_cell: 'Cell 基线', baseline_bs: 'BS 基线',
};
function snapshotLabel(k: string): string { return SNAPSHOT_LABELS[k] || k; }

function trendDelta(s: any): number {
  const pts = s?.points ?? [];
  if (pts.length < 2) return 0;
  return Number(pts.at(-1)?.value ?? 0) - Number(pts[0]?.value ?? 0);
}
function trendDeltaClass(s: any): string { const d = trendDelta(s); return d > 0 ? 'd-up' : d < 0 ? 'd-down' : 'd-neutral'; }
function decisionCount(key: string): number { return Number(detail.value?.decision_summary?.lifecycle_distribution?.[key] ?? 0); }

async function selectRun(runId: string) {
  selectedRunId.value = runId;
  const firstBatch = (runRows.value.find((row: any) => row.run_id === runId)?.batches ?? [])[0];
  if (firstBatch?.batch_id) {
    await selectBatch(firstBatch.batch_id);
  } else {
    selectedBatchId.value = '';
    detail.value = null;
  }
}

async function selectBatch(batchId: string) {
  selectedBatchId.value = batchId;
  try {
    detail.value = await api.getBatchDetail(batchId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败';
  }
}

async function loadPage() {
  loading.value = true;
  error.value = '';
  try {
    payload.value = await api.getBatches();
    const preferredRunId = payload.value?.selected_run_id || runRows.value[0]?.run_id || '';
    if (preferredRunId) {
      await selectRun(preferredRunId);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPage);
</script>

<style scoped>
.page-empty--compact {
  padding: 18px;
}
</style>
