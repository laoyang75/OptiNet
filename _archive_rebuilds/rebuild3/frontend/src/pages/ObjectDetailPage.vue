<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载对象详情...</div>

    <template v-else-if="detail">
      <!-- 头部 -->
      <div class="section">
        <RouterLink class="link-button text-sm" to="/objects" style="margin-bottom:8px;display:inline-block;">← 返回对象列表</RouterLink>
        <div class="flex-row gap-4" style="justify-content:space-between;align-items:flex-start;">
          <div>
            <div style="font-size:20px;font-weight:700;">{{ objectTypeLabel(detail.object_type) }} · {{ detail.snapshot?.object_id }}</div>
            <div class="flex-row gap-2" style="margin-top:8px;">
              <LifecycleBadge :state="detail.snapshot?.lifecycle_state" />
              <HealthBadge :state="detail.snapshot?.health_state" />
              <WatchIndicator :lifecycle-state="detail.snapshot?.lifecycle_state || ''" :health-state="detail.snapshot?.health_state || ''" />
            </div>
          </div>
          <QualificationTags :anchorable="!!detail.snapshot?.anchorable" :baseline-eligible="!!detail.snapshot?.baseline_eligible" />
        </div>
      </div>

      <!-- 基本信息 + 画像摘要 -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
        <div class="section">
          <div class="section-title">基本信息</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;">
            <div><span class="text-muted text-sm">运营商</span><strong style="display:block;">{{ detail.snapshot?.operator_name }}</strong></div>
            <div><span class="text-muted text-sm">制式</span><strong style="display:block;">{{ detail.snapshot?.tech_norm }}</strong></div>
            <div><span class="text-muted text-sm">LAC</span><strong style="display:block;" class="mono">{{ detail.snapshot?.lac }}</strong></div>
            <div v-if="detail.snapshot?.bs_id"><span class="text-muted text-sm">BS</span><strong style="display:block;" class="mono">{{ detail.snapshot?.bs_id }}</strong></div>
            <div v-if="detail.snapshot?.cell_id"><span class="text-muted text-sm">Cell</span><strong style="display:block;" class="mono">{{ detail.snapshot?.cell_id }}</strong></div>
          </div>
        </div>

        <div class="section">
          <div class="section-title">画像摘要</div>
          <div class="summary-grid" style="grid-template-columns:repeat(3,1fr);">
            <div class="summary-card"><div class="label">记录数</div><div class="value" style="font-size:20px;">{{ fmtN(detail.snapshot?.record_count) }}</div></div>
            <div class="summary-card"><div class="label">GPS 数</div><div class="value" style="font-size:20px;">{{ fmtN(detail.snapshot?.gps_count) }}</div></div>
            <div class="summary-card"><div class="label">活跃天数</div><div class="value" style="font-size:20px;">{{ detail.snapshot?.active_days ?? '—' }}</div></div>
          </div>
        </div>
      </div>

      <!-- 事实去向（按批次展示） -->
      <div class="section">
        <div class="section-title">事实去向</div>
        <div class="tab-row" style="margin-bottom: 12px;">
          <button class="tab-button" :class="{ 'tab-button--active': factView === 'aggregate' }" @click="factView = 'aggregate'">聚合</button>
          <button class="tab-button" :class="{ 'tab-button--active': factView === 'per_batch' }" @click="factView = 'per_batch'">按批次</button>
        </div>

        <div v-if="factView === 'aggregate'" class="table-wrap">
          <table class="table table--compact">
            <thead><tr><th>事实层</th><th>数量</th><th>占比</th></tr></thead>
            <tbody>
              <tr v-for="item in detail.facts || []" :key="item.route">
                <td><FactLayerBadge :layer="item.route" /></td>
                <td class="mono">{{ fmtN(item.count) }}</td>
                <td>
                  <div class="progress-bar-track" style="max-width:200px;">
                    <div class="progress-bar-fill" :class="factBarClass(item.route)" :style="{ width: factPct(item.count) + '%' }"></div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="text-muted text-sm">按批次明细视图即将实现（需后端 per-batch facts API）</div>
      </div>

      <!-- 下游影响 — 卡片网格 -->
      <div class="section">
        <div class="section-title">下游影响</div>
        <div v-if="downstreamEntries.length" class="summary-grid" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));">
          <div v-for="item in downstreamEntries" :key="item.label" class="summary-card">
            <div class="label">{{ item.label }}</div>
            <div class="value" style="font-size:20px;">{{ item.value }}</div>
          </div>
        </div>
        <div v-else class="text-muted text-sm">暂无下游影响数据</div>
      </div>

      <!-- 状态时间线 -->
      <div class="section">
        <div class="section-title">状态历史</div>
        <div v-if="(detail.history || []).length" class="timeline-list">
          <div v-for="item in detail.history" :key="item.changed_at + item.changed_reason" class="timeline-item">
            <div class="timeline-dot" :class="timelineDotClass(item)"></div>
            <div class="timeline-content">
              <div class="timeline-date">{{ item.changed_at }}</div>
              <div class="text-sm" style="margin-top:2px;">{{ item.changed_reason }}</div>
              <div class="flex-row gap-2" style="margin-top:4px;">
                <LifecycleBadge :state="item.lifecycle_state" />
                <HealthBadge :state="item.health_state" />
              </div>
            </div>
          </div>
        </div>
        <div v-else class="page-empty">暂无状态历史。</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';

import FactLayerBadge from '../components/FactLayerBadge.vue';
import HealthBadge from '../components/HealthBadge.vue';
import LifecycleBadge from '../components/LifecycleBadge.vue';
import QualificationTags from '../components/QualificationTags.vue';
import WatchIndicator from '../components/WatchIndicator.vue';
import { api } from '../lib/api';
import { objectTypeLabel } from '../lib/format';

const props = defineProps<{ objectType?: string; objectId?: string }>();

const loading = ref(false);
const error = ref('');
const detail = ref<any>(null);
const factView = ref<'aggregate' | 'per_batch'>('aggregate');

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }

const downstreamEntries = computed(() => {
  const d = detail.value?.downstream ?? {};
  return Object.entries(d).map(([label, value]) => ({
    label,
    value: typeof value === 'number' ? value.toLocaleString() : String(value ?? '—'),
  }));
});

function factPct(count: number): number {
  const max = Math.max(...(detail.value?.facts || []).map((f: any) => Number(f.count ?? 0)), 1);
  return Math.max((count / max) * 100, 4);
}

function factBarClass(route: string): string {
  if (route === 'fact_governed') return 'green';
  if (route === 'fact_pending_observation') return 'amber';
  if (route === 'fact_pending_issue') return 'orange';
  return 'orange';
}

function timelineDotClass(item: any): string {
  const colorMap: Record<string, string> = {
    active: 'background: var(--green-500)',
    waiting: 'background: var(--amber-400)',
    observing: 'background: var(--amber-500)',
    dormant: 'background: var(--gray-400)',
    retired: 'background: var(--gray-300)',
    rejected: 'background: var(--red-500)',
  };
  return '';
}

async function loadPage() {
  if (!props.objectType || !props.objectId) return;
  loading.value = true; error.value = '';
  try {
    detail.value = await api.getObjectDetail(props.objectType, props.objectId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败';
  } finally { loading.value = false; }
}

watch(() => [props.objectType, props.objectId], loadPage, { immediate: true });
</script>

<style scoped>
.timeline-list .timeline-dot {
  background: var(--primary-600);
}
</style>
