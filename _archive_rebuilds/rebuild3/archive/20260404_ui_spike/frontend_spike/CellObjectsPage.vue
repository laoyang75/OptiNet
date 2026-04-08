<template>
  <section class="page-stack">
    <div class="page-hero panel-surface panel-surface--hero">
      <div>
        <p class="kicker">03 Objects / Cell</p>
        <h2>对象浏览先暴露口径，再看结果</h2>
        <p class="hero-blurb">
          在 Cell 列表页直接把过滤调整、资格门槛、legacy 差异和 BS 级联修复并排展示，避免结果解释断层。
        </p>
      </div>
      <div class="hero-status-block">
        <BadgePill :tone="list.status === 'ok' ? 'green' : 'blue'" :label="list.status === 'ok' ? '实时数据' : '快照数据'" />
        <p class="hero-status-text">最近更新：{{ summary.generated_at }}</p>
        <p class="hero-status-text">北京研究框：115.0~117.5 / 39.0~41.0</p>
      </div>
    </div>

    <div class="summary-grid">
      <article class="metric-card metric-card--hero">
        <p class="metric-card__label">Cell 总数</p>
        <strong class="metric-card__value">{{ formatNumber(summary.total_objects) }}</strong>
        <p class="metric-card__detail">对象量保持和全量主链路一致，先把基数看明白。</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">基线合格</p>
        <strong class="metric-card__value">{{ formatNumber(summary.baseline_enabled) }}</strong>
        <p class="metric-card__detail">当前可沉淀到 baseline / profile 的 Cell。</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">WATCH</p>
        <strong class="metric-card__value">{{ formatNumber(summary.watch_count) }}</strong>
        <p class="metric-card__detail">active 且 health != healthy 的对象必须高亮。</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">r3_only</p>
        <strong class="metric-card__value">{{ formatNumber(r3OnlyCount) }}</strong>
        <p class="metric-card__detail">与 rebuild2 对比时只在 rebuild3 进入 baseline 的 Cell。</p>
      </article>
    </div>

    <div class="content-split content-split--objects">
      <section class="panel-surface panel-stack list-panel">
        <header class="section-header">
          <div>
            <p class="kicker">Filters</p>
            <h3>筛选条件和对象表</h3>
          </div>
          <p class="section-note">WATCH 行用橙色边框高亮；点整行进入详情，点按钮直接跳画像。</p>
        </header>

        <div class="filter-grid">
          <label class="field-block field-block--wide">
            <span>搜索</span>
            <input v-model="filters.query" type="search" placeholder="Cell ID / BS ID / LAC / object_id" />
          </label>
          <label class="field-block">
            <span>运营商</span>
            <select v-model="filters.operator_code">
              <option value="all">全部</option>
              <option value="46000">中国移动</option>
              <option value="46001">中国联通</option>
              <option value="46011">中国电信</option>
            </select>
          </label>
          <label class="field-block">
            <span>制式</span>
            <select v-model="filters.tech_norm">
              <option value="all">全部</option>
              <option value="4G">4G</option>
              <option value="5G">5G</option>
            </select>
          </label>
          <label class="field-block">
            <span>生命周期</span>
            <select v-model="filters.lifecycle_state">
              <option value="all">全部</option>
              <option value="active">活跃</option>
              <option value="observing">观察中</option>
              <option value="waiting">等待中</option>
              <option value="dormant">休眠</option>
            </select>
          </label>
          <label class="field-block">
            <span>健康状态</span>
            <select v-model="filters.health_state">
              <option value="all">全部</option>
              <option value="healthy">健康</option>
              <option value="gps_bias">GPS偏差</option>
              <option value="dynamic">动态</option>
              <option value="collision_suspect">碰撞嫌疑</option>
              <option value="collision_confirmed">碰撞确认</option>
            </select>
          </label>
          <label class="field-block">
            <span>资格</span>
            <select v-model="filters.qualification">
              <option value="all">全部</option>
              <option value="anchorable">可锚定</option>
              <option value="not_anchorable">锚点禁用</option>
              <option value="baseline">基线合格</option>
              <option value="not_baseline">基线禁用</option>
            </select>
          </label>
          <label class="field-block">
            <span>compare</span>
            <select v-model="filters.membership">
              <option value="all">全部</option>
              <option value="aligned">口径对齐</option>
              <option value="r3_only">仅 rebuild3</option>
              <option value="r2_only">仅 rebuild2</option>
            </select>
          </label>
          <label class="field-block">
            <span>排序</span>
            <select v-model="filters.sort_by">
              <option value="record_count">记录数</option>
              <option value="active_days">活跃天数</option>
              <option value="device_count">设备数</option>
              <option value="gps_p90_dist_m">P90</option>
              <option value="cell_id">Cell ID</option>
            </select>
          </label>
          <label class="field-block">
            <span>方向</span>
            <select v-model="filters.sort_dir">
              <option value="desc">降序</option>
              <option value="asc">升序</option>
            </select>
          </label>
        </div>

        <div class="summary-ribbons">
          <div class="summary-ribbon">
            <span>生命周期分布</span>
            <MetricBars :items="summary.lifecycle" tone="green" />
          </div>
          <div class="summary-ribbon">
            <span>健康状态分布</span>
            <MetricBars :items="summary.health" tone="orange" />
          </div>
        </div>

        <div class="table-shell">
          <div class="table-toolbar">
            <div>
              <strong>{{ formatNumber(list.total) }}</strong>
              <span class="muted-text"> 条匹配结果</span>
            </div>
            <div class="table-toolbar__right">
              <span class="tiny-note">页 {{ list.page }} / {{ list.total_pages }}</span>
              <BadgePill :tone="list.status === 'ok' ? 'green' : 'blue'" :label="list.status === 'ok' ? 'live' : 'snapshot'" />
            </div>
          </div>

          <div v-if="loading" class="loading-state">正在刷新 Cell 列表...</div>
          <div v-else-if="!list.rows.length" class="empty-state">
            未找到匹配的对象，请调整筛选条件。
          </div>
          <table v-else class="objects-table">
            <thead>
              <tr>
                <th>主键</th>
                <th>状态</th>
                <th>资格</th>
                <th>样本 / 活跃</th>
                <th>P90 / 原始率</th>
                <th>legacy 参考</th>
                <th>动作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in list.rows"
                :key="row.object_id"
                class="table-row"
                :class="{ 'table-row--watch': row.watch }"
                @click="openDetail(row.object_id)"
              >
                <td>
                  <div class="primary-cell">
                    <strong>{{ row.operator_name }} · {{ row.tech_norm }}</strong>
                    <code>{{ row.object_id }}</code>
                    <span class="tiny-note">LAC {{ row.lac }} / BS {{ row.bs_id }} / Cell {{ row.cell_id }}</span>
                  </div>
                </td>
                <td>
                  <div class="badge-stack">
                    <BadgePill :tone="lifecycleTone(row.lifecycle_state)" :label="lifecycleLabel(row.lifecycle_state)" />
                    <BadgePill :tone="healthTone(row.health_state)" :label="healthLabel(row.health_state)" />
                    <BadgePill v-if="row.watch" tone="orange" label="WATCH" />
                  </div>
                </td>
                <td>
                  <QualificationStrip :anchorable="row.anchorable" :baseline-eligible="row.baseline_eligible" compact />
                  <div class="table-subtle-tags">
                    <BadgePill :tone="compareTone(row.compare_membership)" :label="compareLabel(row.compare_membership)" />
                    <BadgePill v-if="row.outside_beijing_bbox" tone="red" label="北京框外" />
                  </div>
                </td>
                <td>
                  <div class="metric-stack">
                    <strong>{{ formatNumber(row.record_count) }} 条</strong>
                    <span>{{ formatNumber(row.device_count) }} 设备 · {{ row.active_days }} 天</span>
                  </div>
                </td>
                <td>
                  <div class="metric-stack">
                    <strong>{{ formatMeters(row.gps_p90_dist_m, 2) }}</strong>
                    <span>GPS {{ formatPercent(row.gps_original_ratio) }} · 信号 {{ formatPercent(row.signal_original_ratio) }}</span>
                  </div>
                </td>
                <td>
                  <div class="reference-stack">
                    <span>GPS可信度：{{ row.legacy_gps_quality }}</span>
                    <span>旧分类：{{ row.legacy_bs_classification ?? '无' }}</span>
                    <span :class="{ 'reference-stack__warn': row.legacy_gps_anomaly }">
                      {{ row.legacy_gps_anomaly ? row.legacy_gps_anomaly_reason : '未命中 legacy gps_anomaly' }}
                    </span>
                  </div>
                </td>
                <td>
                  <div class="action-stack">
                    <button class="action-button" @click.stop="openDetail(row.object_id)">详情</button>
                    <button class="action-button action-button--ghost" @click.stop="openProfile(row.object_id)">画像</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="pagination-row">
            <button class="page-button" :disabled="list.page <= 1" @click="changePage(list.page - 1)">上一页</button>
            <span class="tiny-note">第 {{ list.page }} 页，共 {{ list.total_pages }} 页</span>
            <button class="page-button" :disabled="list.page >= list.total_pages" @click="changePage(list.page + 1)">下一页</button>
          </div>
        </div>
      </section>

      <aside class="rail-stack">
        <article class="panel-surface panel-stack">
          <header class="section-header section-header--compact">
            <div>
              <p class="kicker">Change Log</p>
              <h3>本次到底调整了什么</h3>
            </div>
            <BadgePill tone="blue" :label="`+${transparency.impact.baseline_delta} Cell`" />
          </header>
          <div class="change-list compact-list">
            <article v-for="change in transparency.change_log" :key="change.label" class="mini-card">
              <div class="mini-card__head">
                <strong>{{ change.label }}</strong>
                <span>{{ change.impact_metric }}</span>
              </div>
              <p>{{ change.effect }}</p>
              <code>{{ change.source_ref }}</code>
            </article>
          </div>
        </article>

        <article class="panel-surface panel-stack">
          <header class="section-header section-header--compact">
            <div>
              <p class="kicker">Cell Gates</p>
              <h3>资格门槛常驻可见</h3>
            </div>
          </header>
          <div class="compact-list compact-list--stages">
            <article v-for="stage in transparency.cell_stages" :key="stage.stage" class="mini-card mini-card--stage">
              <strong>{{ stage.stage }}</strong>
              <p>{{ stage.summary }}</p>
              <span>{{ stage.purpose }}</span>
            </article>
          </div>
        </article>

        <article class="panel-surface panel-stack">
          <header class="section-header section-header--compact">
            <div>
              <p class="kicker">Scope + Guardrails</p>
              <h3>研究期范围与 BS 兜底</h3>
            </div>
          </header>
          <div class="compact-list">
            <article v-for="scope in transparency.source_scope" :key="scope.label" class="mini-card">
              <div class="mini-card__head">
                <strong>{{ scope.label }}</strong>
                <BadgePill tone="slate" :label="scope.value" />
              </div>
              <p>{{ scope.detail }}</p>
            </article>
          </div>
          <div class="guardrail-grid">
            <div v-for="item in transparency.bs_guardrails" :key="item.label" class="guardrail-tile">
              <span>{{ item.label }}</span>
              <strong :class="{ 'guardrail-tile__bad': item.value > 0 }">{{ item.value }}</strong>
            </div>
          </div>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import BadgePill from '../components/BadgePill.vue';
import MetricBars from '../components/MetricBars.vue';
import QualificationStrip from '../components/QualificationStrip.vue';
import {
  fallbackTransparency,
  fetchCellList,
  fetchCellSummary,
  fetchCellTransparency,
  type CellListResponse,
  type CellListFilters,
  type SummaryResponse,
  type TransparencyResponse,
} from '../lib/cellApi';
import {
  compareLabel,
  compareTone,
  formatMeters,
  formatNumber,
  formatPercent,
  healthLabel,
  healthTone,
  lifecycleLabel,
  lifecycleTone,
} from '../lib/format';

const router = useRouter();

const summary = ref<SummaryResponse>({
  status: 'snapshot',
  generated_at: 'loading',
  total_objects: 0,
  watch_count: 0,
  baseline_enabled: 0,
  anchorable_enabled: 0,
  compare_membership: [],
  lifecycle: [],
  health: [],
  qualification: [],
});
const transparency = ref<TransparencyResponse>(fallbackTransparency);
const list = ref<CellListResponse>({
  status: 'snapshot',
  generated_at: 'loading',
  rows: [],
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 1,
  sort_by: 'record_count',
  sort_dir: 'desc',
});
const loading = ref(false);

const filters = reactive<CellListFilters>({
  query: '',
  operator_code: 'all',
  tech_norm: 'all',
  lifecycle_state: 'all',
  health_state: 'all',
  qualification: 'all',
  membership: 'all',
  page: 1,
  page_size: 10,
  sort_by: 'record_count',
  sort_dir: 'desc',
});

const r3OnlyCount = computed(() => {
  return summary.value.compare_membership.find((item) => item.label === 'r3_only')?.count ?? 0;
});

async function loadList(): Promise<void> {
  loading.value = true;
  try {
    list.value = await fetchCellList(filters);
  } finally {
    loading.value = false;
  }
}

function openDetail(objectId: string): void {
  router.push({ name: 'cell-detail', params: { objectId } });
}

function openProfile(objectId: string): void {
  router.push({ name: 'cell-profile', params: { objectId } });
}

function changePage(page: number): void {
  filters.page = page;
}

watch(
  () => ({ ...filters }),
  async (_current, previous) => {
    if (previous && previous.query !== filters.query) {
      filters.page = 1;
    }
    await loadList();
  },
  { deep: true, immediate: true },
);

onMounted(async () => {
  const [summaryData, transparencyData] = await Promise.all([fetchCellSummary(), fetchCellTransparency()]);
  summary.value = summaryData;
  transparency.value = transparencyData;
});
</script>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.metric-card {
  display: grid;
  gap: 0.72rem;
  padding: 1.2rem 1.25rem;
  border-radius: 1.5rem;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--border-soft);
  min-height: 10rem;
}

.metric-card--hero {
  background: linear-gradient(135deg, rgba(32, 69, 144, 0.98), rgba(63, 102, 186, 0.92));
  color: white;
}

.metric-card--hero .metric-card__label,
.metric-card--hero .metric-card__detail {
  color: rgba(239, 244, 255, 0.78);
}

.metric-card__label {
  font-size: 0.76rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.metric-card__value {
  font-size: clamp(1.8rem, 3vw, 2.8rem);
  line-height: 0.95;
  letter-spacing: -0.05em;
}

.metric-card__detail {
  color: var(--text-soft);
  line-height: 1.6;
}

.content-split--objects {
  grid-template-columns: minmax(0, 1.4fr) minmax(21rem, 0.88fr);
}

.list-panel {
  overflow: hidden;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.82rem;
}

.field-block--wide {
  grid-column: span 2;
}

.summary-ribbons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.summary-ribbon {
  padding: 1rem;
  border-radius: 1.2rem;
  border: 1px solid var(--border-soft);
  background: linear-gradient(180deg, rgba(251, 253, 255, 0.96), rgba(246, 249, 254, 0.92));
  display: grid;
  gap: 0.92rem;
}

.summary-ribbon > span {
  font-size: 0.8rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.table-shell {
  display: grid;
  gap: 1rem;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}

.table-toolbar__right {
  display: flex;
  gap: 0.7rem;
  align-items: center;
}

.objects-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.objects-table th {
  padding: 0.9rem 1rem;
  text-align: left;
  font-size: 0.76rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-soft);
  border-bottom: 1px solid var(--border-soft);
}

.objects-table td {
  padding: 1rem;
  border-bottom: 1px solid rgba(118, 135, 167, 0.12);
  vertical-align: top;
}

.table-row {
  cursor: pointer;
  transition: background-color 180ms ease, transform 180ms ease;
}

.table-row:hover {
  background: rgba(244, 248, 255, 0.88);
}

.table-row--watch {
  box-shadow: inset 4px 0 0 rgba(201, 116, 30, 0.88);
  background: rgba(255, 247, 235, 0.82);
}

.primary-cell {
  display: grid;
  gap: 0.38rem;
}

.primary-cell code {
  padding: 0.2rem 0.4rem;
  width: fit-content;
  border-radius: 0.55rem;
  background: rgba(32, 46, 74, 0.06);
  color: var(--text-strong);
  font-size: 0.78rem;
  word-break: break-all;
}

.badge-stack,
.table-subtle-tags,
.action-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.metric-stack,
.reference-stack {
  display: grid;
  gap: 0.32rem;
  color: var(--text-soft);
}

.metric-stack strong {
  color: var(--text-strong);
}

.reference-stack__warn {
  color: var(--orange-strong);
}

.action-stack {
  justify-content: flex-start;
}

.action-button,
.page-button {
  appearance: none;
  border: 1px solid rgba(44, 94, 188, 0.18);
  background: rgba(242, 247, 255, 0.9);
  color: var(--blue-strong);
  border-radius: 999px;
  padding: 0.54rem 0.9rem;
  font-size: 0.84rem;
  font-weight: 700;
  cursor: pointer;
}

.action-button--ghost,
.page-button:disabled {
  color: var(--text-soft);
  border-color: var(--border-soft);
  background: rgba(247, 249, 253, 0.9);
}

.page-button:disabled {
  cursor: not-allowed;
}

.pagination-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}

.compact-list {
  display: grid;
  gap: 0.75rem;
}

.mini-card {
  display: grid;
  gap: 0.55rem;
  padding: 1rem;
  border-radius: 1.15rem;
  background: rgba(247, 250, 255, 0.88);
  border: 1px solid var(--border-soft);
}

.mini-card__head {
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
  align-items: baseline;
}

.mini-card p,
.mini-card span,
.mini-card code {
  color: var(--text-soft);
}

.mini-card code {
  font-size: 0.76rem;
  word-break: break-all;
}

.guardrail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
}

.guardrail-tile {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px solid var(--border-soft);
  background: rgba(252, 253, 255, 0.92);
  display: grid;
  gap: 0.42rem;
  color: var(--text-soft);
}

.guardrail-tile strong {
  font-size: 1.5rem;
  color: var(--green-strong);
}

.guardrail-tile__bad {
  color: var(--red-strong) !important;
}

@media (max-width: 1240px) {
  .summary-grid,
  .content-split--objects,
  .summary-ribbons,
  .guardrail-grid,
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .field-block--wide {
    grid-column: span 2;
  }
}

@media (max-width: 900px) {
  .summary-grid,
  .content-split--objects,
  .summary-ribbons,
  .guardrail-grid,
  .filter-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .field-block--wide {
    grid-column: span 1;
  }

  .objects-table,
  .objects-table thead,
  .objects-table tbody,
  .objects-table th,
  .objects-table td,
  .objects-table tr {
    display: block;
  }

  .objects-table thead {
    display: none;
  }

  .objects-table td {
    padding-top: 0.4rem;
    padding-bottom: 0.8rem;
  }

  .table-row {
    border: 1px solid var(--border-soft);
    border-radius: 1rem;
    margin-bottom: 0.9rem;
    overflow: hidden;
  }

  .pagination-row,
  .table-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
