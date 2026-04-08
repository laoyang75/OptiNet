<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载初始化数据...</div>

    <template v-else-if="payload">
      <DataOriginBanner :origin="payload.data_origin" :subject-note="payload.subject_note" :show-synthetic="true" />

      <div v-if="payload.empty_state" class="page-empty">
        {{ payload.empty_state.description || '暂无初始化数据。' }}
      </div>

      <template v-else>
      <!-- 上下文条（5 字段） -->
      <div class="context-bar">
        <div class="ctx-item"><span class="ctx-label">run_id</span><span class="ctx-value">{{ payload.context?.run_id || '—' }}</span></div>
        <div class="ctx-divider"></div>
        <div class="ctx-item"><span class="ctx-label">窗口</span><span class="ctx-value">{{ payload.context?.window || '—' }}</span></div>
        <div class="ctx-divider"></div>
        <div class="ctx-item"><span class="ctx-label">状态</span><span class="ctx-value">{{ payload.context?.status || '—' }}</span></div>
        <div class="ctx-divider"></div>
        <div class="ctx-item"><span class="ctx-label">完成时间</span><span class="ctx-value">{{ payload.context?.completed_at || '—' }}</span></div>
        <div class="ctx-divider"></div>
        <div class="ctx-item"><span class="ctx-label">规则版本</span><span class="ctx-value">{{ payload.context?.rule_set_version || '—' }}</span></div>
      </div>

      <!-- 初始化流程步骤（含输入/输出/通过率） -->
      <div class="section">
        <div class="section-title">初始化流程</div>
        <div class="init-step-list">
          <div v-for="step in payload.steps || []" :key="step.index" class="init-step-item">
            <div class="init-step-index">{{ step.index }}</div>
            <div class="init-step-body">
              <div class="init-step-name">{{ step.label }}</div>
              <div class="init-step-status" :class="'status-' + (step.status || 'pending')">{{ statusLabel(step.status) }}</div>
              <div v-if="step.input || step.output || step.pass_rate" class="init-step-metrics">
                <span v-if="step.input != null" class="text-muted text-sm">输入: {{ fmtN(step.input) }}</span>
                <span v-if="step.output != null" class="text-muted text-sm">输出: {{ fmtN(step.output) }}</span>
                <span v-if="step.pass_rate != null" class="text-muted text-sm">通过率: {{ (step.pass_rate * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 结果汇总 -->
      <div class="section">
        <div class="section-title">结果汇总</div>
        <div class="summary-grid">
          <div v-for="item in payload.summary_cards || []" :key="item.label" class="summary-card">
            <div class="label">{{ item.label }}</div>
            <div class="value" style="font-size:20px;">{{ summaryValue(item.value) }}</div>
          </div>
        </div>
      </div>

      <!-- 四分流 -->
      <div v-if="(payload.flow_summary || []).length" class="section">
        <div class="section-title">四分流分布</div>
        <div class="table-wrap">
          <table class="table table--compact">
            <thead><tr><th>路由</th><th>数量</th><th>占比</th></tr></thead>
            <tbody>
              <tr v-for="item in payload.flow_summary" :key="item.route">
                <td><FactLayerBadge :layer="item.route" /></td>
                <td class="mono">{{ fmtN(item.count) }}</td>
                <td>{{ item.ratio != null ? (item.ratio * 100).toFixed(1) + '%' : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 说明 -->
      <div v-if="(payload.notes || []).length" class="section">
        <div class="section-title">研究期说明</div>
        <ul style="padding-left:18px;display:flex;flex-direction:column;gap:6px;color:var(--gray-600);font-size:13px;">
          <li v-for="item in payload.notes" :key="item">{{ item }}</li>
        </ul>
      </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';

import DataOriginBanner from '../components/DataOriginBanner.vue';
import FactLayerBadge from '../components/FactLayerBadge.vue';
import { api } from '../lib/api';

const loading = ref(false);
const error = ref('');
const payload = ref<any>(null);

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function summaryValue(v: number | string) { const n = Number(v); return Number.isNaN(n) ? String(v) : fmtN(n); }
function statusLabel(s: string): string { return { completed: '已完成', running: '运行中', pending: '待处理', skipped: '已跳过' }[s] || s || '—'; }

async function loadPage() {
  loading.value = true; error.value = '';
  try { payload.value = await api.getInitialization(); }
  catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; }
  finally { loading.value = false; }
}

onMounted(loadPage);
</script>

<style scoped>
.init-step-list { display: flex; flex-direction: column; gap: 12px; }
.init-step-item {
  display: grid; grid-template-columns: 48px 1fr; gap: 14px; align-items: start;
  padding: 14px 0; border-bottom: 1px solid var(--surface-border);
}
.init-step-index {
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--primary-50); color: var(--primary-600); font-weight: 700;
}
.init-step-name { font-weight: 600; font-size: 14px; }
.init-step-status { font-size: 12px; font-weight: 600; margin-top: 2px; }
.init-step-status.status-completed { color: var(--green-600); }
.init-step-status.status-running { color: var(--blue-600); }
.init-step-status.status-pending { color: var(--gray-400); }
.init-step-metrics { display: flex; gap: 12px; margin-top: 4px; }
</style>
