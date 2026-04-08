<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载基线/画像...</div>

    <template v-else-if="payload">
      <DataOriginBanner :origin="payload.data_origin" :subject-note="payload.subject_note" :show-synthetic="true" />

      <div v-if="payload.empty_state" class="page-empty">
        {{ payload.empty_state.description || '尚未生成正式 baseline。' }}
      </div>

      <template v-else>
      <!-- 当前版本信息 + 触发详情 -->
      <div class="section">
        <div class="section-title">当前版本</div>
        <div class="bl-version-grid">
          <div class="bl-version-card">
            <div class="bl-version-label">基线版本</div>
            <div class="bl-version-value">{{ payload.current_version?.baseline_version || payload.context?.baseline_version || '—' }}</div>
            <div class="bl-kv-list">
              <div class="bl-kv-item"><span>运行 ID</span><strong class="mono">{{ payload.context?.run_id || '—' }}</strong></div>
              <div class="bl-kv-item"><span>批次 ID</span><strong class="mono">{{ payload.context?.batch_id || '—' }}</strong></div>
              <div class="bl-kv-item"><span>触发方式</span><strong>{{ refreshTriggerLabel(payload.current_version?.triggered) }}</strong></div>
              <div class="bl-kv-item"><span>创建时间</span><strong>{{ payload.current_version?.created_at || '—' }}</strong></div>
            </div>
          </div>

          <!-- 触发详情卡片 (设计稿要求高亮) -->
          <div class="bl-trigger-card">
            <div class="bl-trigger-title">刷新触发详情</div>
            <div class="bl-trigger-reason">{{ payload.current_version?.refresh_reason || '当前无刷新记录' }}</div>
            <div class="bl-kv-list">
              <div class="bl-kv-item"><span>触发条件</span><strong>{{ payload.trigger_detail?.condition || '—' }}</strong></div>
              <div class="bl-kv-item"><span>触发类型</span><strong>{{ payload.trigger_detail?.type || '—' }}</strong></div>
              <div class="bl-kv-item"><span>等待贡献</span><strong>{{ payload.trigger_detail?.waiting_contribution ?? '—' }}</strong></div>
              <div class="bl-kv-item"><span>异常贡献</span><strong>{{ payload.trigger_detail?.anomaly_contribution ?? '—' }}</strong></div>
            </div>
          </div>
        </div>
      </div>

      <!-- 稳定性评分 -->
      <div class="section">
        <div class="section-title">稳定性评分</div>
        <div class="bl-stability-grid">
          <div class="bl-stability-main">
            <div class="bl-stability-score" :class="stabilityScoreClass">
              {{ stabilityScore }}<span class="bl-stability-unit">/100</span>
            </div>
            <div class="bl-stability-label">{{ stabilityLabel }}</div>
            <!-- 进度条 -->
            <div class="progress-bar-container" style="max-width: 100%; margin-top: 12px;">
              <div class="progress-bar-track">
                <div class="progress-bar-fill" :class="stabilityBarClass" :style="{ width: stabilityScore + '%' }"></div>
              </div>
            </div>
          </div>
          <div class="bl-risk-factors">
            <div class="bl-risk-title">风险因素</div>
            <ul class="bl-risk-list">
              <li v-for="item in payload.risk_factors || []" :key="item">{{ item }}</li>
            </ul>
            <div v-if="!(payload.risk_factors || []).length" class="text-muted text-sm">无明显风险因素</div>
          </div>
        </div>
      </div>

      <!-- 覆盖与质量 -->
      <div class="section">
        <div class="section-title">覆盖与质量</div>
        <div class="summary-grid">
          <div v-for="item in payload.coverage_cards || []" :key="item.label" class="summary-card">
            <div class="label">{{ item.label }}</div>
            <div class="value">{{ fmtCoverage(item) }}</div>
          </div>
        </div>
        <div class="bl-quality-row">
          <div class="bl-quality-item">
            <span class="text-muted text-sm">GPS 原始率</span>
            <strong>{{ fmtPct(payload.quality?.gps_original_ratio) }}</strong>
          </div>
          <div class="bl-quality-item">
            <span class="text-muted text-sm">信号原始率</span>
            <strong>{{ fmtPct(payload.quality?.signal_original_ratio) }}</strong>
          </div>
        </div>
      </div>

      <!-- 差异样本 — 摘要 + 展开 -->
      <div class="section">
        <div class="section-title">差异样本</div>
        <div class="bl-diff-summary">
          <div class="bl-diff-stat">
            <span class="bl-diff-stat-label">新增</span>
            <strong class="d-up">{{ diffStats.added }}</strong>
          </div>
          <div class="bl-diff-stat">
            <span class="bl-diff-stat-label">移除</span>
            <strong class="d-down">{{ diffStats.removed }}</strong>
          </div>
          <div class="bl-diff-stat">
            <span class="bl-diff-stat-label">画像变更</span>
            <strong class="d-warn">{{ diffStats.changed }}</strong>
          </div>
        </div>

        <div v-if="!(payload.diff_samples || []).length" class="page-empty page-empty--compact">
          {{ payload.diff_notice || '暂无版本差异可展示。' }}
        </div>

        <div v-if="showDiffTable" class="table-wrap" style="margin-top: 12px;">
          <table class="table table--compact">
            <thead>
              <tr>
                <th>对象</th>
                <th>r2 健康状态</th>
                <th>r3 健康状态</th>
                <th>P90 对照</th>
                <th>归属</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in payload.diff_samples || []" :key="row.object_id">
                <td>
                  <RouterLink :to="detailLink(row)" class="link-button">{{ row.title }}</RouterLink>
                  <div class="text-muted text-sm">{{ row.subtitle }}</div>
                </td>
                <td>{{ row.r2_health_state || '—' }}</td>
                <td>{{ row.r3_health_state || '—' }}</td>
                <td class="mono text-sm">{{ row.r2_p90 ?? '—' }}m → {{ row.r3_p90 ?? '—' }}m</td>
                <td>{{ row.membership || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <button v-if="(payload.diff_samples || []).length > 0" class="inline-button" style="margin-top: 8px;" @click="showDiffTable = !showDiffTable">
          {{ showDiffTable ? '收起详情' : '展开详情 (' + (payload.diff_samples || []).length + ' 条)' }}
        </button>
      </div>

      <!-- 版本历史 -->
      <div class="section">
        <div class="section-title">版本历史</div>
        <div class="table-wrap">
          <table class="table table--compact">
            <thead>
              <tr>
                <th>范围</th>
                <th>基线版本</th>
                <th>运行 ID</th>
                <th>对象数</th>
                <th>刷新原因</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in payload.version_history || []" :key="row.baseline_version + row.created_at">
                <td><span class="bl-scope-badge" :class="row.scope === '正式' ? 'scope-full' : 'scope-sample'">{{ row.scope || '—' }}</span></td>
                <td class="mono">{{ row.baseline_version }}</td>
                <td class="mono text-sm">{{ row.run_id }}</td>
                <td>{{ fmtN(row.object_count) }}</td>
                <td>{{ refreshReasonLabel(row.refresh_reason) }}</td>
                <td class="text-sm">{{ row.created_at || '—' }}</td>
              </tr>
            </tbody>
          </table>
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
import { api } from '../lib/api';

const loading = ref(false);
const error = ref('');
const payload = ref<any>(null);
const showDiffTable = ref(false);

function fmtN(n: number | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

function fmtPct(n: number | undefined): string {
  if (n == null) return '—';
  return (n * 100).toFixed(1) + '%';
}

function fmtCoverage(item: any): string {
  if (String(item.label).includes('P90')) return (item.value ?? 0) + 'm';
  return fmtN(item.value);
}

const stabilityScore = computed(() => {
  if (!payload.value) return 0;
  let score = payload.value.quality?.stability_score ?? 88;
  if (typeof score !== 'number') {
    score = 88;
    if (Number(payload.value.quality?.gps_original_ratio ?? 0) < 0.7) score -= 8;
    if (Number(payload.value.quality?.signal_original_ratio ?? 0) < 0.6) score -= 5;
    score -= Math.min(10, (payload.value.diff_samples?.length ?? 0) / 2);
    score = Math.max(60, Math.round(score));
  }
  return score;
});

const stabilityScoreClass = computed(() => {
  if (stabilityScore.value >= 80) return 'score-green';
  if (stabilityScore.value >= 70) return 'score-amber';
  return 'score-red';
});

const stabilityBarClass = computed(() => {
  if (stabilityScore.value >= 80) return 'green';
  if (stabilityScore.value >= 70) return 'amber';
  return 'orange';
});

const stabilityLabel = computed(() => {
  if (stabilityScore.value >= 80) return '首版可接受';
  if (stabilityScore.value >= 70) return '需持续观察';
  return '风险偏高';
});

const diffStats = computed(() => {
  const samples = payload.value?.diff_samples || [];
  return {
    added: samples.filter((s: any) => ['r3_only', '仅 rebuild3'].includes(s.membership)).length,
    removed: samples.filter((s: any) => ['r2_only', '仅 rebuild2'].includes(s.membership)).length,
    changed: samples.filter((s: any) => ['both_changed', 'both', '口径对齐'].includes(s.membership)).length,
  };
});

function refreshTriggerLabel(value: boolean | string | null | undefined): string {
  if (value === true) return '批次触发';
  if (value === false) return '未触发';
  return String(value ?? '—');
}

function refreshReasonLabel(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    sample_initial_baseline: '样本初始基线',
    full_initial_baseline: '全量初始基线',
    batch_trigger: '批次触发',
    manual: '手动触发',
  };
  return labels[reason ?? ''] ?? reason ?? '—';
}

function detailLink(row: any) {
  return { name: 'object-detail', params: { objectType: row.object_type || 'cell', objectId: row.object_id } };
}

async function loadPage() {
  loading.value = true;
  error.value = '';
  try {
    payload.value = await api.getBaselineProfile();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载基线/画像';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPage);
</script>

<style scoped>
.bl-version-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.bl-version-card, .bl-trigger-card {
  background: white; border: 1px solid var(--surface-border); border-radius: var(--radius-lg);
  padding: 20px; box-shadow: var(--shadow-card);
}
.bl-trigger-card { border-color: var(--primary-100); background: var(--primary-50); }
.bl-version-label { font-size: 12px; color: var(--gray-400); font-weight: 500; }
.bl-version-value { font-size: 28px; font-weight: 700; color: var(--gray-900); margin: 4px 0 12px; }
.bl-trigger-title { font-size: 13px; font-weight: 600; color: var(--primary-600); margin-bottom: 4px; }
.bl-trigger-reason { font-size: 14px; color: var(--gray-700); margin-bottom: 12px; }
.bl-kv-list { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.bl-kv-item span { font-size: 11px; color: var(--gray-400); }
.bl-kv-item strong { display: block; font-size: 13px; margin-top: 2px; }

/* Stability */
.bl-stability-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.bl-stability-main { text-align: center; }
.bl-stability-score { font-size: 48px; font-weight: 700; line-height: 1; }
.bl-stability-score.score-green { color: var(--green-600); }
.bl-stability-score.score-amber { color: var(--amber-500); }
.bl-stability-score.score-red { color: var(--red-500); }
.bl-stability-unit { font-size: 18px; font-weight: 400; color: var(--gray-400); }
.bl-stability-label { font-size: 14px; color: var(--gray-600); margin-top: 4px; }
.bl-risk-title { font-size: 13px; font-weight: 600; color: var(--gray-800); margin-bottom: 8px; }
.bl-risk-list { padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--gray-600); }

/* Quality row */
.bl-quality-row { display: flex; gap: 24px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--surface-border); }
.bl-quality-item { display: flex; flex-direction: column; gap: 2px; }

/* Diff summary */
.bl-diff-summary { display: flex; gap: 24px; }
.bl-diff-stat { display: flex; align-items: center; gap: 8px; }
.bl-diff-stat-label { font-size: 13px; color: var(--gray-500); }
.bl-diff-stat strong { font-size: 18px; }

/* Scope badge */
.bl-scope-badge { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 6px; }
.bl-scope-badge.scope-full { background: var(--primary-50); color: var(--primary-600); }
.bl-scope-badge.scope-sample { background: var(--blue-50); color: var(--blue-600); }
</style>
