<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载验证/对照...</div>

    <template v-else-if="selectedOverview">
      <DataOriginBanner :origin="meta.origin" :subject-note="meta.subjectNote" :show-synthetic="true" />

      <!-- 对比配置面板 -->
      <div class="section">
        <div class="section-title">对比配置</div>
        <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:16px;align-items:end;">
          <div class="filter-field">
            <label>Run A</label>
            <select v-model="activeScope">
              <option value="sample">样本 (sample)</option>
              <option value="full">全量 (full)</option>
            </select>
          </div>
          <div class="filter-field">
            <label>Run B</label>
            <select disabled>
              <option>rebuild2 历史参考（fallback）</option>
            </select>
          </div>
          <button class="action-button" @click="loadPage">刷新参考结果</button>
        </div>
      </div>

      <!-- 解释统计（三列网格） -->
      <div class="section">
        <div class="section-title">解释统计</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;">
          <div class="val-explain-card val-explain-ok">
            <div class="val-explain-label">可解释</div>
            <div class="val-explain-value">{{ explainStats.ok }}%</div>
            <div class="val-explain-sub">{{ explainStats.okCount }} 条差异可自然解释</div>
          </div>
          <div class="val-explain-card val-explain-warn">
            <div class="val-explain-label">需关注</div>
            <div class="val-explain-value">{{ explainStats.warn }}%</div>
            <div class="val-explain-sub">{{ explainStats.warnCount }} 条差异需要检查</div>
          </div>
          <div class="val-explain-card val-explain-note">
            <div class="val-explain-label">建议</div>
            <div class="val-explain-sub" style="margin-top:8px;">{{ selectedOverview.gate || '差异在可接受范围内' }}</div>
          </div>
        </div>
      </div>

      <!-- 汇总指标 -->
      <div class="summary-grid">
        <div v-for="item in selectedOverview.summary || []" :key="item.label" class="summary-card">
          <div class="label">{{ item.label }}</div>
          <div class="value" style="font-size:20px;">{{ summaryValue(item.value) }}</div>
        </div>
      </div>

      <!-- 路由差异表 -->
      <div class="section">
        <div class="section-title">路由差异</div>
        <div class="table-wrap">
          <table class="table table--compact">
            <thead>
              <tr>
                <th>路由</th>
                <th>rebuild2</th>
                <th>rebuild3</th>
                <th>差异</th>
                <th>可解释性</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in selectedOverview.routes || []" :key="row.route">
                <td><FactLayerBadge :layer="row.route" /></td>
                <td class="mono">{{ fmtN(row.r2) }}</td>
                <td class="mono">{{ fmtN(row.r3) }}</td>
                <td class="mono" :class="row.diff > 0 ? 'd-up' : row.diff < 0 ? 'd-down' : ''">{{ fmtSigned(row.diff) }}</td>
                <td>
                  <span v-if="Math.abs(row.diff || 0) < 10" class="val-explain-tag ok">✓ 正常</span>
                  <span v-else class="val-explain-tag warn">⚠ 需检查</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 差异对象 -->
      <div class="section">
        <div class="section-title">差异对象</div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>对象</th>
                <th>差异类型</th>
                <th>左值</th>
                <th>右值</th>
                <th>可解释性</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in selectedDiffs" :key="row.object_id + row.title">
                <td><span class="mono text-sm">{{ row.object_id }}</span><div class="text-muted text-sm">{{ row.title }}</div></td>
                <td>{{ row.diff_type }}</td>
                <td>{{ row.left_value }}</td>
                <td>{{ row.right_value }}</td>
                <td>
                  <span v-if="row.explainable !== false" class="val-explain-tag ok">✓ 正常</span>
                  <span v-else class="val-explain-tag warn">⚠ 需检查</span>
                </td>
                <td class="text-muted text-sm">{{ row.explanation }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 解释说明 -->
      <div v-if="(selectedOverview.notes || []).length" class="section">
        <div class="section-title">差异解释</div>
        <ul style="padding-left:18px;display:flex;flex-direction:column;gap:6px;color:var(--gray-600);font-size:13px;">
          <li v-for="item in selectedOverview.notes" :key="item">{{ item }}</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import DataOriginBanner from '../components/DataOriginBanner.vue';
import FactLayerBadge from '../components/FactLayerBadge.vue';
import { api } from '../lib/api';

const loading = ref(false);
const error = ref('');
const activeScope = ref<'sample' | 'full'>('sample');
const overviews = ref<any[]>([]);
const diffPayload = ref<any>(null);
const meta = ref({ origin: '', subjectNote: '' });

const selectedOverview = computed(() => overviews.value.find((i) => i.scope === activeScope.value) ?? null);
const selectedDiffs = computed(() => diffPayload.value?.[activeScope.value] ?? []);

const explainStats = computed(() => {
  const diffs = selectedDiffs.value;
  const total = diffs.length || 1;
  const okCount = diffs.filter((d: any) => d.explainable !== false).length;
  const warnCount = total - okCount;
  return {
    ok: Math.round((okCount / total) * 100),
    warn: Math.round((warnCount / total) * 100),
    okCount,
    warnCount,
  };
});

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function fmtSigned(v: number): string { return v > 0 ? `+${fmtN(v)}` : v < 0 ? `-${fmtN(Math.abs(v))}` : '0'; }
function summaryValue(v: number | string) { const n = Number(v); return Number.isNaN(n) ? String(v) : fmtN(n); }

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const [o, d] = await Promise.all([api.getCompareOverview(), api.getCompareDiffs()]);
    overviews.value = o.scopes ?? [];
    diffPayload.value = d;
    meta.value = { origin: o.data_origin || d.data_origin || '', subjectNote: o.subject_note || d.subject_note || '' };
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

onMounted(loadPage);
</script>

<style scoped>
.val-explain-card { padding: 20px; border-radius: var(--radius-lg); border: 1px solid var(--surface-border); }
.val-explain-card.val-explain-ok { background: var(--green-50); border-color: #BBF7D0; }
.val-explain-card.val-explain-warn { background: var(--orange-50); border-color: #FFEDD5; }
.val-explain-card.val-explain-note { background: var(--gray-50); }
.val-explain-label { font-size: 12px; color: var(--gray-500); font-weight: 500; }
.val-explain-value { font-size: 28px; font-weight: 700; }
.val-explain-ok .val-explain-value { color: var(--green-600); }
.val-explain-warn .val-explain-value { color: var(--orange-600); }
.val-explain-sub { font-size: 12px; color: var(--gray-500); margin-top: 4px; }
.val-explain-tag { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.val-explain-tag.ok { color: #166534; background: var(--green-50); }
.val-explain-tag.warn { color: #9A3412; background: var(--orange-50); }
</style>
