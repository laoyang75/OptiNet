<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载等待/观察工作台...</div>

    <template v-else-if="payload">
      <!-- 汇总条 -->
      <div class="obs-summary-bar">
        <div class="obs-summary-item">
          <div class="obs-summary-label">等待中</div>
          <div class="obs-summary-value">{{ fmtN(payload.summary.waiting_count) }}</div>
          <div class="obs-summary-meta">
            <span>本批 +{{ payload.summary.waiting_batch_delta ?? 0 }}</span>
            <span :class="deltaClass(payload.summary.waiting_vs_delta)">
              较上批 {{ fmtDelta(payload.summary.waiting_vs_delta) }}
            </span>
          </div>
        </div>
        <div class="obs-summary-item">
          <div class="obs-summary-label">观察中</div>
          <div class="obs-summary-value">{{ fmtN(payload.summary.observing_count) }}</div>
          <div class="obs-summary-meta">
            <span>本批 +{{ payload.summary.observing_batch_delta ?? 0 }}</span>
            <span :class="deltaClass(payload.summary.observing_vs_delta)">
              较上批 {{ fmtDelta(payload.summary.observing_vs_delta) }}
            </span>
          </div>
        </div>
        <div class="obs-summary-item">
          <div class="obs-summary-label">本批晋升</div>
          <div class="obs-summary-value">{{ payload.summary.promoted_count ?? 0 }}</div>
        </div>
        <div class="obs-summary-item">
          <div class="obs-summary-label">本批转问题</div>
          <div class="obs-summary-value">{{ payload.summary.recommend_issue_count ?? 0 }}</div>
        </div>
        <div class="obs-summary-item">
          <div class="obs-summary-label">本批拒收</div>
          <div class="obs-summary-value">{{ payload.summary.rejected_count ?? 0 }}</div>
        </div>
        <div v-if="payload.summary.backlog_warning" class="obs-summary-item obs-summary-warning">
          <div class="obs-warning-text">
            <span>⚠</span> {{ payload.summary.backlog_warning }}
          </div>
        </div>
      </div>

      <!-- Tab 导航 -->
      <div class="section">
        <div class="obs-tabs">
          <div
            class="obs-tab"
            :class="{ active: activeTab === 'waiting' }"
            @click="activeTab = 'waiting'"
          >
            等待中<span class="obs-tab-count">{{ payload.summary.waiting_count }}</span>
          </div>
          <div
            class="obs-tab"
            :class="{ active: activeTab === 'observing' }"
            @click="activeTab = 'observing'"
          >
            观察中<span class="obs-tab-count">{{ payload.summary.observing_count }}</span>
          </div>
          <div
            class="obs-tab"
            :class="{ active: activeTab === 'all' }"
            @click="activeTab = 'all'"
          >全部</div>
        </div>

        <!-- 筛选栏 -->
        <div class="obs-filter-bar">
          <div class="filter-group">
            <span class="filter-label">推进状态</span>
            <select v-model="filterTrend" class="filter-select">
              <option value="">全部</option>
              <option value="advancing">前进中</option>
              <option value="stagnant">停滞</option>
              <option value="regressing">回退</option>
            </select>
          </div>
          <div class="obs-filter-divider"></div>
          <div class="filter-group">
            <span class="filter-label">缺失资格层</span>
            <select v-model="filterMissing" class="filter-select">
              <option value="">全部</option>
              <option value="existence">缺存在资格</option>
              <option value="anchorable">缺锚点资格</option>
              <option value="baseline">缺基线资格</option>
              <option value="complete">全部达标</option>
            </select>
          </div>
          <div class="obs-filter-divider"></div>
          <div class="filter-group">
            <span class="filter-label">排序</span>
            <select v-model="sortBy" class="filter-select">
              <option value="progress">进度降序</option>
              <option value="first_seen">首次发现</option>
              <option value="stalled">停滞批次数</option>
            </select>
          </div>
        </div>

        <!-- 候选卡片网格 -->
        <div v-if="filteredCards.length" class="obs-card-grid">
          <article
            v-for="card in filteredCards"
            :key="card.object_id"
            class="obs-candidate-card"
            :class="cardBorderClass(card)"
          >
            <!-- 卡片头部 -->
            <div class="obs-card-header">
              <RouterLink :to="detailLink(card)" class="obs-card-pk">{{ card.title || card.object_id }}</RouterLink>
              <LifecycleBadge :state="card.lifecycle_state" />
            </div>

            <!-- 三层资格进度 -->
            <div class="obs-qual-layers">
              <!-- L1 存在资格 -->
              <div class="obs-qual-layer" :class="qualLayerClass(card.existence_progress, true)">
                <div class="obs-qual-header" @click="toggleExpand(card.object_id, 'l1')">
                  <div class="obs-qual-left">
                    <span class="obs-qual-icon" :class="qualIconClass(card.existence_progress, 'existence')">
                      {{ card.existence_progress >= 100 ? '✓' : '◆' }}
                    </span>
                    <span class="obs-qual-name">存在资格</span>
                  </div>
                  <span class="obs-qual-pct" :class="{ complete: card.existence_progress >= 100 }">
                    {{ card.existence_progress >= 100 ? '100%' : card.existence_progress + '%' }}
                  </span>
                </div>
                <div v-if="card.existence_progress < 100 && isExpanded(card.object_id, 'l1')" class="obs-qual-details">
                  <div v-for="d in card.existence_details || []" :key="d.label" class="obs-qual-detail-row">
                    <span class="obs-qual-detail-label">{{ d.label }}</span>
                    <div class="obs-qual-detail-track">
                      <div class="obs-qual-detail-fill" :class="detailFillClass(d.ratio)" :style="{ width: `${Math.min(d.ratio * 100, 100)}%` }"></div>
                    </div>
                    <span class="obs-qual-detail-value">{{ d.display }}</span>
                  </div>
                </div>
              </div>

              <!-- L2 锚点资格 -->
              <div class="obs-qual-layer" :class="qualLayerClass(card.anchor_progress, card.existence_progress >= 100)">
                <div class="obs-qual-header" @click="card.existence_progress >= 100 && toggleExpand(card.object_id, 'l2')">
                  <div class="obs-qual-left">
                    <span class="obs-qual-icon" :class="qualIconClass(card.anchor_progress, 'anchorable', card.existence_progress >= 100)">
                      {{ card.anchor_progress >= 100 ? '✓' : '◆' }}
                    </span>
                    <span class="obs-qual-name">锚点资格</span>
                  </div>
                  <span class="obs-qual-pct" :class="{ complete: card.anchor_progress >= 100 }">
                    {{ card.existence_progress < 100 ? '--' : (card.anchor_progress >= 100 ? '100%' : card.anchor_progress + '%') }}
                  </span>
                </div>
                <div v-if="card.existence_progress < 100" class="obs-qual-locked-text">需存在资格达成后才能评估</div>
                <div v-else-if="card.anchor_progress < 100 && isExpanded(card.object_id, 'l2')" class="obs-qual-details">
                  <div v-for="d in card.anchor_details || []" :key="d.label" class="obs-qual-detail-row">
                    <span class="obs-qual-detail-label">{{ d.label }}</span>
                    <div class="obs-qual-detail-track">
                      <div class="obs-qual-detail-fill" :class="detailFillClass(d.ratio)" :style="{ width: `${Math.min(d.ratio * 100, 100)}%` }"></div>
                    </div>
                    <span class="obs-qual-detail-value">{{ d.display }}</span>
                  </div>
                </div>
              </div>

              <!-- L3 基线资格 -->
              <div class="obs-qual-layer" :class="qualLayerClass(card.baseline_progress, card.anchor_progress >= 100)">
                <div class="obs-qual-header" @click="card.anchor_progress >= 100 && toggleExpand(card.object_id, 'l3')">
                  <div class="obs-qual-left">
                    <span class="obs-qual-icon" :class="qualIconClass(card.baseline_progress, 'baseline', card.anchor_progress >= 100)">
                      {{ card.baseline_progress >= 100 ? '✓' : '◆' }}
                    </span>
                    <span class="obs-qual-name">基线资格</span>
                  </div>
                  <span class="obs-qual-pct" :class="{ complete: card.baseline_progress >= 100 }">
                    {{ card.anchor_progress < 100 ? '--' : (card.baseline_progress >= 100 ? '100%' : card.baseline_progress + '%') }}
                  </span>
                </div>
                <div v-if="card.anchor_progress < 100" class="obs-qual-locked-text">需锚点资格达成后才能评估</div>
                <div v-else-if="card.baseline_progress < 100 && isExpanded(card.object_id, 'l3')" class="obs-qual-details">
                  <div v-for="d in card.baseline_details || []" :key="d.label" class="obs-qual-detail-row">
                    <span class="obs-qual-detail-label">{{ d.label }}</span>
                    <div class="obs-qual-detail-track">
                      <div class="obs-qual-detail-fill" :class="detailFillClass(d.ratio)" :style="{ width: `${Math.min(d.ratio * 100, 100)}%` }"></div>
                    </div>
                    <span class="obs-qual-detail-value">{{ d.display }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 趋势 + 建议动作 -->
            <div class="obs-card-trend-action">
              <span class="obs-trend-badge" :class="trendClass(card.trend)">{{ trendIcon(card.trend) }} {{ trendLabel(card.trend) }}</span>
              <span class="obs-mini-trend mono">{{ card.trend_values || '' }}</span>
            </div>
            <div>
              <span class="obs-action-badge" :class="actionClass(card)">{{ card.suggested_action }}</span>
            </div>

            <!-- 质量指标 -->
            <div class="obs-card-quality text-muted text-sm">
              质心({{ card.centroid_lat ?? '—' }}, {{ card.centroid_lon ?? '—' }}) P90半径 {{ card.p90_m ?? '—' }}m
            </div>

            <!-- 底部 -->
            <div class="obs-card-footer">
              <span>首次发现 {{ card.first_seen || '—' }}</span>
              <span>停滞批次: {{ card.stalled_batches ?? 0 }}</span>
            </div>
          </article>
        </div>
        <div v-else class="page-empty">当前筛选下没有候选对象。</div>
      </div>

      <!-- 堆积分析 -->
      <div class="section">
        <div class="section-title">堆积分析</div>
        <div class="obs-accumulation">
          <div class="obs-accum-chart">
            <div class="obs-accum-title">近 6 批等待池规模</div>
            <div class="obs-mini-bar-chart">
              <div v-for="(b, i) in (payload.backlog_trend || []).slice(-6)" :key="i" class="obs-mini-bar-col">
                <div class="obs-mini-bar" :class="{ latest: i === (payload.backlog_trend || []).slice(-6).length - 1 }" :style="{ height: barHeight(b.value) }"></div>
                <span class="obs-mini-bar-value mono">{{ b.value }}</span>
                <span class="obs-mini-bar-label mono">{{ b.label }}</span>
              </div>
            </div>
          </div>
          <div class="obs-accum-dist">
            <div class="obs-accum-title">按缺失资格分布</div>
            <div v-for="item in payload.backlog_analysis || []" :key="item.label" class="obs-reason-row">
              <span class="obs-reason-label">{{ item.label }}</span>
              <div class="obs-reason-track">
                <div class="obs-reason-fill" :class="reasonClass(item.type)" :style="{ width: `${item.ratio ? item.ratio * 100 : reasonPct(item.count)}%` }"></div>
              </div>
              <span class="obs-reason-pct">{{ item.ratio ? Math.round(item.ratio * 100) + '%' : fmtN(item.count) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';

import LifecycleBadge from '../components/LifecycleBadge.vue';
import { api } from '../lib/api';
import '../styles/pages/observation-workspace.css';

const loading = ref(false);
const error = ref('');
const payload = ref<any>(null);
const activeTab = ref<'waiting' | 'observing' | 'all'>('all');
const filterTrend = ref('');
const filterMissing = ref('');
const sortBy = ref('progress');
const expandedMap = reactive<Record<string, boolean>>({});

function fmtN(n: number | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

function fmtDelta(n: number | undefined): string {
  if (n == null) return '—';
  const prefix = n > 0 ? '+' : '';
  const arrow = n > 0 ? ' ↑' : n < 0 ? ' ↓' : '';
  return `${prefix}${n}${arrow}`;
}

function deltaClass(n: number | undefined): string {
  if (n == null || n === 0) return 'delta-gray';
  return n > 0 ? 'delta-red' : 'delta-green';
}

const filteredCards = computed(() => {
  let cards = [...(payload.value?.cards ?? [])];

  if (activeTab.value !== 'all') {
    cards = cards.filter((c: any) => c.lifecycle_state === activeTab.value);
  }

  if (filterTrend.value) {
    cards = cards.filter((c: any) => normalizedTrend(c.trend) === filterTrend.value);
  }

  if (filterMissing.value) {
    if (filterMissing.value === 'existence') {
      cards = cards.filter((c: any) => c.existence_progress < 100);
    } else if (filterMissing.value === 'anchorable') {
      cards = cards.filter((c: any) => c.existence_progress >= 100 && c.anchor_progress < 100);
    } else if (filterMissing.value === 'baseline') {
      cards = cards.filter((c: any) => c.anchor_progress >= 100 && c.baseline_progress < 100);
    } else if (filterMissing.value === 'complete') {
      cards = cards.filter((c: any) => c.baseline_progress >= 100);
    }
  }

  cards.sort((a: any, b: any) => {
    if (sortBy.value === 'first_seen') {
      return String(a.first_seen ?? '').localeCompare(String(b.first_seen ?? ''));
    }
    if (sortBy.value === 'stalled') {
      return Number(b.stalled_batches ?? 0) - Number(a.stalled_batches ?? 0);
    }
    return progressScore(b) - progressScore(a);
  });

  return cards;
});

function detailLink(card: any) {
  return { name: 'object-detail', params: { objectType: card.object_type || 'cell', objectId: card.object_id } };
}

function toggleExpand(id: string, layer: string) {
  const key = `${id}-${layer}`;
  expandedMap[key] = !expandedMap[key];
}

function isExpanded(id: string, layer: string): boolean {
  return !!expandedMap[`${id}-${layer}`];
}

function qualLayerClass(progress: number, unlocked: boolean): string {
  if (!unlocked) return 'locked';
  if (progress >= 100) return 'met';
  return '';
}

function qualIconClass(progress: number, type: string, unlocked = true): string {
  if (progress >= 100) return 'done';
  if (!unlocked) return type;
  return type;
}

function detailFillClass(ratio: number): string {
  if (ratio >= 1) return 'met';
  if (ratio >= 0.7) return 'close';
  return 'far';
}

function trendClass(trend: string): string {
  const map: Record<string, string> = {
    advancing: 'advancing',
    approaching: 'advancing',
    ready: 'advancing',
    stagnant: 'stagnant',
    steady: 'stagnant',
    regressing: 'regressing',
    risk: 'regressing',
    new: 'new-entry',
    new_entry: 'new-entry',
  };
  return map[trend] || 'stagnant';
}

function trendIcon(trend: string): string {
  if (trend === 'advancing' || trend === 'approaching' || trend === 'ready') return '↗';
  if (trend === 'stagnant' || trend === 'steady') return '→';
  if (trend === 'regressing' || trend === 'risk') return '↘';
  return '●';
}

function trendLabel(trend: string): string {
  const map: Record<string, string> = {
    advancing: '前进中',
    approaching: '接近达标',
    ready: '即将晋升',
    stagnant: '停滞',
    steady: '继续观察',
    regressing: '回退',
    risk: '风险上升',
    new: '新进入',
    new_entry: '新进入',
  };
  return map[trend] || trend;
}

function normalizedTrend(trend: string): string {
  const map: Record<string, string> = {
    advancing: 'advancing',
    ready: 'advancing',
    approaching: 'advancing',
    stagnant: 'stagnant',
    steady: 'stagnant',
    regressing: 'regressing',
    risk: 'regressing',
    new: 'new',
    new_entry: 'new',
  };
  return map[trend] || trend;
}

function progressScore(card: any): number {
  return Math.max(
    Number(card.existence_progress ?? 0),
    Number(card.anchor_progress ?? 0),
    Number(card.baseline_progress ?? 0),
  );
}

function cardBorderClass(card: any): string {
  if (card.baseline_progress >= 100) return 'suggest-promote';
  if (String(card.suggested_action).includes('问题') || String(card.suggested_action).includes('issue')) return 'suggest-issue';
  return '';
}

function actionClass(card: any): string {
  if (card.baseline_progress >= 100) return 'near-promote';
  if (String(card.suggested_action).includes('问题')) return 'to-issue';
  return 'continue';
}

function barHeight(val: number): string {
  const maxVal = Math.max(...(payload.value?.backlog_trend || []).map((b: any) => b.value || 0), 1);
  return Math.max((val / maxVal) * 80, 4) + 'px';
}

function reasonClass(type: string): string {
  if (type === 'existence') return 'existence';
  if (type === 'anchorable') return 'anchorable';
  if (type === 'baseline') return 'baseline-q';
  return 'existence';
}

function reasonPct(count: number): number {
  const total = (payload.value?.summary?.total_candidates || 1);
  return Math.max((count / total) * 100, 3);
}

async function loadPage() {
  loading.value = true;
  error.value = '';
  try {
    payload.value = await api.getObservationWorkspace();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载等待/观察工作台';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPage);
</script>
