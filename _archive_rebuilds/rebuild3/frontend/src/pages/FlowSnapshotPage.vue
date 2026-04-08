<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载流转快照...</div>

    <template v-else>
      <DataOriginBanner :origin="payload?.data_origin" :subject-note="payload?.subject_note" :show-synthetic="true" />

      <div class="section">
        <div class="view-switch">
          <RouterLink class="view-btn" to="/flow/overview">流程图视图</RouterLink>
          <button class="view-btn view-btn--active" type="button">时间快照视图</button>
        </div>
        <div class="section-title">时间快照对照</div>
        <p class="text-muted snapshot-intro">
          本视图用于批次回放和局部重跑对照。左列固定为初始化完成后，右侧仅允许选择同一运行场景下的两个后续时间点，不再把 sample / full / baseline 伪装成时间快照。
        </p>
      </div>

      <div class="section">
        <div class="section-title">选择时间点</div>

        <div v-if="!payload?.run_options?.length" class="page-empty">
          {{ payload?.empty_state?.description || '暂无可回放的运行场景。' }}
        </div>

        <template v-else>
          <div class="filter-field snapshot-run-selector">
            <label>运行场景</label>
            <select v-model="selectedRunId" @change="changeRun">
              <option v-for="option in payload.run_options" :key="option.run_id" :value="option.run_id">
                {{ option.label }}
              </option>
            </select>
            <div class="selector-hint">
              {{ payload.selected_run_summary?.subtitle || '—' }} · 已完成 {{ fmtN(payload.selected_run_summary?.completed_batch_count) }} 个批次
            </div>
          </div>

          <div class="time-selector-card">
            <div class="time-selectors">
              <article class="ts-col init">
                <div class="ts-col-header">
                  <span class="ts-col-tag init">固定</span>
                  <span class="ts-col-title">初始化完成后</span>
                </div>
                <label>初始化批次</label>
                <div class="ts-readonly mono">{{ initColumn?.context?.batch_id || '—' }}</div>
                <div class="ts-info">
                  <strong>基线版本:</strong> {{ initColumn?.context?.baseline_version || '—' }}<br />
                  <strong>快照时间:</strong> {{ shortTime(initColumn?.context?.snapshot_recorded_at) }}<br />
                  <strong>窗口:</strong> {{ initColumn?.context?.window || '—' }}
                </div>
              </article>

              <article class="ts-col t1">
                <div class="ts-col-header">
                  <span class="ts-col-tag t1">自定义 1</span>
                  <span class="ts-col-title">时间点 A</span>
                </div>
                <label>选择批次完成时间</label>
                <select v-model="selectedTimeA" :disabled="!payload.timepoint_options.length">
                  <option value="">暂无可选时间点</option>
                  <option v-for="option in payload.timepoint_options" :key="option.batch_id" :value="option.batch_id">
                    {{ option.label }}
                  </option>
                </select>
                <div class="ts-info">
                  <strong>基线版本:</strong> {{ selectedOptionA?.baseline_version || '—' }}<br />
                  <strong>类型:</strong> {{ batchTypeLabel(selectedOptionA) }}<br />
                  <strong>窗口:</strong> {{ selectedOptionA?.window || '—' }}
                </div>
              </article>

              <article class="ts-col t2">
                <div class="ts-col-header">
                  <span class="ts-col-tag t2">自定义 2</span>
                  <span class="ts-col-title">时间点 B</span>
                </div>
                <label>选择批次完成时间</label>
                <select v-model="selectedTimeB" :disabled="payload.timepoint_options.length < 2">
                  <option value="">暂无更多时间点</option>
                  <option v-for="option in payload.timepoint_options" :key="option.batch_id" :value="option.batch_id">
                    {{ option.label }}
                  </option>
                </select>
                <div class="ts-info">
                  <strong>基线版本:</strong> {{ selectedOptionB?.baseline_version || '—' }}<br />
                  <strong>类型:</strong> {{ batchTypeLabel(selectedOptionB) }}<br />
                  <strong>窗口:</strong> {{ selectedOptionB?.window || '—' }}
                </div>
              </article>
            </div>

            <div class="selector-actions">
              <button class="action-button" type="button" @click="applySelection">加载快照数据</button>
              <div class="selector-hint mono">
                {{ (payload.storage_tables || []).join(' · ') }}
              </div>
            </div>
          </div>

          <div v-if="payload.warnings?.length" class="warning-stack">
            <div v-for="warning in payload.warnings" :key="warning" class="snapshot-warning">
              {{ warning }}
            </div>
          </div>
        </template>
      </div>

      <div v-if="payload?.groups?.length" class="section">
        <div class="section-title">流水线各阶段数据快照</div>
        <div class="table-wrap snapshot-card">
          <table class="snapshot-table">
            <thead>
              <tr>
                <th>处理阶段</th>
                <th v-for="column in payload.columns" :key="column.id" :class="columnClass(column)">
                  <div>{{ column.label }}</div>
                  <span class="snapshot-th-note">{{ column.available ? column.header_note : '暂无时间点' }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <template v-for="group in payload.groups" :key="group.stage_name">
                <tr class="group-row">
                  <td :colspan="1 + payload.columns.length">{{ group.label }}</td>
                </tr>
                <tr v-for="row in group.rows" :key="row.metric_name">
                  <td>
                    <div class="stage-label-cell">
                      <span class="stage-text">{{ row.label }}</span>
                      <span class="stage-sub">{{ row.subtitle }}</span>
                    </div>
                  </td>
                  <td v-for="(cell, index) in row.cells" :key="`${row.metric_name}-${index}`" :class="columnClass(payload.columns[index])">
                    {{ cell.display_value }}
                    <span v-if="cell.percent" class="pct">{{ cell.percent }}</span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="page-empty">
        {{ payload?.empty_state?.description || '当前选择下暂无可展示的快照指标。' }}
      </div>

      <div class="section">
        <div class="note-box">
          <strong>快照底座：</strong>
          每次批次完成后都应把阶段指标写入 <code>batch_snapshot</code>，页面再按 <code>run → init batch → 后续时间点</code> 装配对照列。
          <template v-if="payload?.data_origin === 'synthetic'">
            当前暂无真实时间点快照，因此页面已显式切换到 synthetic scenario 评估模式，方便功能验证。
          </template>
          <template v-else>
            当前页优先读取真实运行元数据，不再把环境对照误当成时间演进。
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import DataOriginBanner from '../components/DataOriginBanner.vue';
import { api } from '../lib/api';

type RunOption = {
  run_id: string;
  label: string;
  subtitle: string;
  completed_batch_count: number;
};

type TimepointOption = {
  batch_id: string;
  label: string;
  window: string;
  batch_type: string;
  baseline_version: string;
  is_rerun: boolean;
  snapshot_recorded_at?: string;
};

type ColumnContext = {
  batch_id?: string;
  baseline_version?: string;
  batch_type?: string;
  window?: string;
  snapshot_recorded_at?: string;
};

type SnapshotColumn = {
  id: string;
  label: string;
  badge: string;
  tone: 'init' | 't1' | 't2';
  available: boolean;
  context: ColumnContext;
  header_note: string;
};

type SnapshotCell = {
  display_value: string;
  percent: string;
};

type SnapshotRow = {
  metric_name: string;
  label: string;
  subtitle: string;
  cells: SnapshotCell[];
};

type SnapshotGroup = {
  stage_name: string;
  label: string;
  rows: SnapshotRow[];
};

type SnapshotPayload = {
  data_origin?: string;
  subject_note?: string;
  run_options: RunOption[];
  selected_run_id: string;
  selected_run_summary?: RunOption & { subtitle?: string };
  timepoint_options: TimepointOption[];
  selected_time_a: string;
  selected_time_b: string;
  columns: SnapshotColumn[];
  groups: SnapshotGroup[];
  warnings: string[];
  storage_tables: string[];
  empty_state?: { title?: string; description?: string } | null;
};

const loading = ref(false);
const error = ref('');
const payload = ref<SnapshotPayload | null>(null);
const selectedRunId = ref('');
const selectedTimeA = ref('');
const selectedTimeB = ref('');

const initColumn = computed(() => payload.value?.columns?.[0]);
const selectedOptionA = computed(() => payload.value?.timepoint_options?.find((item) => item.batch_id === selectedTimeA.value));
const selectedOptionB = computed(() => payload.value?.timepoint_options?.find((item) => item.batch_id === selectedTimeB.value));

function fmtN(value: number | string | undefined): string {
  if (value == null || value === '') return '—';
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : numeric.toLocaleString();
}

function shortTime(value: string | undefined): string {
  if (!value) return '—';
  return value.slice(0, 16).replace('T', ' ');
}

function batchTypeLabel(option: TimepointOption | undefined): string {
  if (!option) return '—';
  if (option.is_rerun) return '重跑批次';
  return option.batch_type || '常规批次';
}

function columnClass(column: SnapshotColumn): string {
  return `snapshot-col-${column.tone}`;
}

async function loadPage(query?: { run_id?: string; time_a?: string; time_b?: string }) {
  loading.value = true;
  error.value = '';
  try {
    const next = await api.getFlowSnapshots(query);
    payload.value = next;
    selectedRunId.value = next.selected_run_id || '';
    selectedTimeA.value = next.selected_time_a || '';
    selectedTimeB.value = next.selected_time_b || '';
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载流转快照';
  } finally {
    loading.value = false;
  }
}

function changeRun() {
  loadPage({ run_id: selectedRunId.value });
}

function applySelection() {
  loadPage({
    run_id: selectedRunId.value,
    time_a: selectedTimeA.value,
    time_b: selectedTimeB.value,
  });
}

onMounted(() => {
  loadPage();
});
</script>

<style scoped>
.snapshot-intro {
  margin-top: 4px;
  line-height: 1.7;
}

.snapshot-run-selector {
  margin-bottom: 16px;
}

.selector-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--gray-500);
}

.time-selector-card {
  background: var(--surface-bg);
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 20px 24px;
}

.time-selectors {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.ts-col {
  padding: 16px;
  border-radius: 12px;
  border: 2px solid transparent;
}

.ts-col.init {
  background: var(--blue-50);
  border-color: #60A5FA;
}

.ts-col.t1 {
  background: var(--amber-50);
  border-color: #F59E0B;
}

.ts-col.t2 {
  background: var(--green-50);
  border-color: #22C55E;
}

.ts-col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.ts-col-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 700;
  color: white;
}

.ts-col-tag.init {
  background: var(--blue-600);
}

.ts-col-tag.t1 {
  background: #D97706;
}

.ts-col-tag.t2 {
  background: var(--green-600);
}

.ts-col-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-900);
}

.ts-col label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--gray-500);
}

.ts-col select,
.ts-readonly {
  width: 100%;
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-md);
  background: white;
  color: var(--gray-800);
  font-size: 13px;
}

.ts-col select:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.ts-info {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--gray-500);
}

.ts-info strong {
  color: var(--gray-700);
}

.selector-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.warning-stack {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.snapshot-warning {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--amber-50);
  border: 1px solid #FCD34D;
  color: #92400E;
  font-size: 13px;
}

.snapshot-card {
  overflow-x: auto;
}

.snapshot-table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  font-size: 13px;
}

.snapshot-table thead th {
  padding: 10px 16px;
  text-align: left;
  background: var(--gray-50);
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 600;
  border-bottom: 2px solid var(--surface-border);
}

.snapshot-table thead th:not(:first-child) {
  text-align: right;
  min-width: 190px;
}

.snapshot-th-note {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  font-weight: 400;
}

.snapshot-table tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--gray-100);
}

.snapshot-table tbody td:not(:first-child) {
  text-align: right;
  font-family: var(--font-mono);
  font-weight: 600;
}

.snapshot-table tbody tr:hover td {
  background: var(--indigo-50);
}

.group-row td {
  background: var(--gray-50);
  color: var(--gray-400);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--surface-border);
  padding: 7px 16px;
}

.stage-label-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-text {
  font-weight: 600;
  color: var(--gray-800);
}

.stage-sub {
  font-size: 11px;
  color: var(--gray-400);
}

.pct {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 400;
  color: var(--gray-400);
}

.snapshot-col-init {
  color: var(--blue-600);
}

.snapshot-col-t1 {
  color: #92400E;
}

.snapshot-col-t2 {
  color: var(--green-600);
}

.note-box {
  background: var(--gray-50);
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  color: var(--gray-600);
  line-height: 1.7;
  font-size: 13px;
}

.note-box strong {
  color: var(--gray-800);
}

@media (max-width: 900px) {
  .time-selectors {
    grid-template-columns: 1fr;
  }

  .selector-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
