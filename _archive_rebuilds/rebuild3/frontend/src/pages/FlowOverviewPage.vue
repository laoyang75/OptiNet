<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="loader">正在加载流转总览...</div>

    <template v-else-if="overview">
      <DataOriginBanner :origin="overview.data_origin" :subject-note="overview.subject_note" :show-synthetic="true" />

      <div v-if="overview.empty_state" class="page-empty">
        {{ overview.empty_state.description || '当前暂无可展示的真实批次。' }}
      </div>

      <template v-else>
      <!-- 当前上下文 -->
      <div class="context-bar">
        <div class="ctx-item">
          <span class="ctx-label">run_id</span>
          <span class="ctx-value">{{ overview.context.run_id || '—' }}</span>
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item">
          <span class="ctx-label">batch_id</span>
          <span class="ctx-value">{{ overview.context.batch_id || '—' }}</span>
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item">
          <span class="ctx-label">窗口</span>
          <span class="ctx-value">{{ overview.context.window || '—' }}</span>
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item">
          <span class="ctx-label">基线版本</span>
          <span class="ctx-value">{{ overview.context.baseline_version || '—' }}</span>
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item">
          <span class="ctx-label">规则版本</span>
          <span class="ctx-value">{{ overview.context.rule_set_version || '—' }}</span>
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item">
          <span class="ctx-label">契约版本</span>
          <span class="ctx-value">{{ overview.context.contract_version || '—' }}</span>
        </div>
      </div>

      <!-- 视图切换 -->
      <div class="section">
        <div class="view-switch">
          <button class="view-btn view-btn--active">流程图视图</button>
          <RouterLink class="view-btn" to="/flow/snapshot">时间快照视图</RouterLink>
        </div>

        <div class="section-title">当前批次处理流程</div>

        <!-- 垂直流程图：匹配冻结文档 Section 7.1 增量流程 -->
        <div class="flow-card">
          <!-- 1. 2小时批次进入 -->
          <div class="flow-stage">
            <div class="flow-node input">入</div>
            <div class="flow-info">
              <div class="flow-name">2小时批次进入</div>
              <div class="flow-desc">原始记录导入系统</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowData.input_records) }}</div>
              <div class="sub">条原始记录</div>
            </div>
          </div>

          <!-- 2. 注册 batch_id -->
          <div class="flow-stage">
            <div class="flow-node process">注</div>
            <div class="flow-info">
              <div class="flow-name">注册 batch_id</div>
              <div class="flow-desc">{{ overview.context.batch_id }} · {{ overview.context.window }}</div>
            </div>
            <div class="flow-data">
              <div class="val" style="font-size:14px;color:var(--primary-600)">{{ overview.context.batch_id }}</div>
            </div>
          </div>

          <!-- 3. 标准化事件 -->
          <div class="flow-stage">
            <div class="flow-node process">标</div>
            <div class="flow-info">
              <div class="flow-name">标准化事件</div>
              <div class="flow-desc">解析为不可变标准事件 (fact_standardized)</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowData.standardized) }}</div>
              <div class="pct">通过率 {{ fmtPct(flowData.standardized, flowData.input_records) }}</div>
              <div class="sub">{{ fmtN(flowData.input_records - flowData.standardized) }} 条解析失败</div>
            </div>
          </div>

          <!-- 4. 查对象注册表和上一版baseline -->
          <div class="flow-stage">
            <div class="flow-node process">查</div>
            <div class="flow-info">
              <div class="flow-name">查对象注册表 + 上一版基线</div>
              <div class="flow-desc">匹配 obj_cell · 参考 baseline {{ overview.context.baseline_version }} — 当前批次只读取上一版冻结 baseline</div>
            </div>
            <div class="flow-data">
              <div class="val" style="font-size:14px">{{ fmtN(flowData.known_objects) }} 个已知对象</div>
              <div class="sub">基线 {{ overview.context.baseline_version }} · 规则 {{ overview.context.rule_set_version }}</div>
            </div>
          </div>

          <div class="flow-split"></div>

          <!-- 5. 四分流路由 -->
          <div class="flow-stage">
            <div class="flow-node route"><span>分</span></div>
            <div class="flow-info">
              <div class="flow-name" style="color:var(--primary-600)">四分流路由</div>
              <div class="flow-desc">事件进入哪条路径？</div>
            </div>
            <div class="flow-data">
              <div class="val" style="font-size:14px">{{ fmtN(flowData.standardized) }} 条待分流</div>
            </div>
          </div>

          <!-- 5a. fact_governed -->
          <div class="flow-stage branch">
            <div class="flow-node governed" style="width:40px;height:40px;font-size:13px">治</div>
            <div class="flow-info">
              <div class="flow-name">已治理事实 (fact_governed)</div>
              <div class="flow-desc">已知且健康，或仅记录级异常</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowRoute('fact_governed').count) }}</div>
              <div class="pct">{{ fmtPct(flowRoute('fact_governed').count, flowData.standardized) }}</div>
            </div>
          </div>

          <!-- 5b. fact_pending_observation -->
          <div class="flow-stage branch">
            <div class="flow-node pending_obs" style="width:40px;height:40px;font-size:13px">观</div>
            <div class="flow-info">
              <div class="flow-name">观察事实 (fact_pending_observation)</div>
              <div class="flow-desc">未知但合规，证据累计中</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowRoute('fact_pending_observation').count) }}</div>
              <div class="pct">{{ fmtPct(flowRoute('fact_pending_observation').count, flowData.standardized) }}</div>
            </div>
          </div>

          <!-- 5c. fact_pending_issue -->
          <div class="flow-stage branch">
            <div class="flow-node pending_issue" style="width:40px;height:40px;font-size:13px">问</div>
            <div class="flow-info">
              <div class="flow-name">问题事实 (fact_pending_issue)</div>
              <div class="flow-desc">已知但对象级异常/待复核</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowRoute('fact_pending_issue').count) }}</div>
              <div class="pct">{{ fmtPct(flowRoute('fact_pending_issue').count, flowData.standardized) }}</div>
            </div>
          </div>

          <!-- 5d. fact_rejected -->
          <div class="flow-stage branch">
            <div class="flow-node rejected" style="width:40px;height:40px;font-size:13px">拒</div>
            <div class="flow-info">
              <div class="flow-name">拒收事实 (fact_rejected)</div>
              <div class="flow-desc">结构不合规 → 留痕后结束</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowRoute('fact_rejected').count) }}</div>
              <div class="pct">{{ fmtPct(flowRoute('fact_rejected').count, flowData.standardized) }}</div>
            </div>
          </div>

          <div class="flow-split" style="margin-left:32px"></div>

          <!-- 6. 累计对象证据 -->
          <div class="flow-stage">
            <div class="flow-node merge">累</div>
            <div class="flow-info">
              <div class="flow-name">累计对象证据</div>
              <div class="flow-desc">governed + pending_observation + pending_issue → 对象证据更新</div>
            </div>
            <div class="flow-data">
              <div class="val">{{ fmtN(flowData.evidence_objects) }}</div>
              <div class="sub">个对象更新证据 (+{{ flowData.evidence_new }})</div>
            </div>
          </div>

          <div class="flow-divider">
            <div class="flow-divider-line"></div>
            <div class="flow-divider-text">批末统一决策</div>
            <div class="flow-divider-line"></div>
          </div>

          <!-- 7. 批末晋升 Cell -->
          <div class="flow-stage">
            <div class="flow-node decision">升</div>
            <div class="flow-info">
              <div class="flow-name">批末晋升 Cell</div>
              <div class="flow-desc">waiting → observing → active / active → dormant</div>
            </div>
            <div class="flow-data">
              <div class="val" style="color:var(--green-600)">
                {{ flowData.hasPromotionDelta ? `晋升 +${flowData.promotions}` : `活跃 ${fmtN(flowData.cell_active)}` }}
              </div>
              <div class="sub" :style="{ color: flowData.hasPromotionDelta ? 'var(--red-500)' : 'var(--gray-500)' }">
                {{ flowData.hasPromotionDelta ? `降级 -${flowData.demotions}` : `观察 ${fmtN(flowData.cell_observing)} · 等待 ${fmtN(flowData.cell_waiting)}` }}
              </div>
            </div>
          </div>

          <!-- 8. 级联更新 BS 和 LAC -->
          <div class="flow-stage">
            <div class="flow-node decision">联</div>
            <div class="flow-info">
              <div class="flow-name">级联更新 BS 和 LAC</div>
              <div class="flow-desc">由 active Cell 派生更新</div>
            </div>
            <div class="flow-data">
              <div class="val" style="font-size:14px">
                {{ flowData.hasCascadeDelta ? `+${flowData.cascade_bs} BS · +${flowData.cascade_lac} LAC` : `Active BS ${fmtN(flowData.bs_active)} · Active LAC ${fmtN(flowData.lac_active)}` }}
              </div>
              <div class="sub">
                {{ flowData.hasCascadeDelta ? `共 ${flowData.cascade_total} 个级联变化` : '当前生命周期分布来自批末 decision summary' }}
              </div>
            </div>
          </div>

          <!-- 9. 批末异常检测与状态转移 -->
          <div class="flow-stage">
            <div class="flow-node" style="background:var(--orange-500)">异</div>
            <div class="flow-info">
              <div class="flow-name">批末异常检测与状态转移</div>
              <div class="flow-desc">碰撞 / 动态 / 迁移 / GPS偏差</div>
            </div>
            <div class="flow-data">
              <div class="val" style="color:var(--orange-600)">{{ flowData.anomaly_total }} 个异常</div>
              <div class="sub">本批新增 +{{ flowData.anomaly_new }}</div>
            </div>
          </div>

          <!-- 10. 按触发条件刷新 baseline -->
          <div class="flow-stage">
            <div class="flow-node baseline">基</div>
            <div class="flow-info">
              <div class="flow-name">按触发条件刷新基线</div>
              <div class="flow-desc">批末统一判断，新基线仅供下一批次使用</div>
            </div>
            <div class="flow-data">
              <div class="val" :style="{ color: flowData.baseline_refreshed ? 'var(--green-600)' : 'var(--gray-400)' }">
                {{ flowData.baseline_refreshed ? '已触发刷新 → ' + flowData.baseline_next_version : '未触发刷新' }}
              </div>
              <div class="sub">当前 {{ overview.context.baseline_version }} {{ flowData.baseline_refreshed ? '' : '继续使用' }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 当前累计状态 -->
      <div class="section">
        <div class="section-title">当前累计状态（本批次后）</div>
        <div class="summary-grid">
          <MetricCardWithDelta
            v-for="m in summaryMetrics"
            :key="m.label"
            :label="m.label"
            :value="m.value"
            :batch="m.batch"
            :vs="m.vs"
            :inverse="m.inverse"
          />
        </div>
      </div>

      <!-- 问题入口 -->
      <div class="section">
        <div class="section-title">问题入口</div>
        <div class="issue-list">
          <RouterLink
            v-for="item in overview.issue_entries"
            :key="item.title"
            :to="item.href"
            class="issue-item"
          >
            <span class="issue-dot" :class="severityDotClass(item.severity)"></span>
            <span class="issue-text">{{ item.title }}</span>
            <span class="issue-target">{{ item.target || '查看' }} →</span>
          </RouterLink>
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
import MetricCardWithDelta from '../components/MetricCardWithDelta.vue';
import { api } from '../lib/api';
import { formatNumber } from '../lib/format';

const loading = ref(false);
const error = ref('');
const overview = ref<any>(null);

function fmtN(n: number | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

function fmtPct(part: number | undefined, total: number | undefined): string {
  if (!part || !total) return '—';
  return (part / total * 100).toFixed(1) + '%';
}

const flowData = computed(() => {
  if (!overview.value) return {} as any;
  const o = overview.value;
  const flow = o.flow || [];
  const metrics = o.key_metrics || [];
  const decisions = o.decision_summary?.lifecycle_distribution || {};

  const routeMap: Record<string, any> = {};
  for (const item of flow) {
    routeMap[item.route] = item;
  }

  const metricMap: Record<string, any> = {};
  for (const item of metrics) {
    metricMap[item.metric_name] = item;
  }

  return {
    input_records: o.context?.input_rows ||
      metricMap.fact_standardized?.value ||
      ((routeMap.fact_governed?.count || 0) + (routeMap.fact_pending_observation?.count || 0) + (routeMap.fact_pending_issue?.count || 0) + (routeMap.fact_rejected?.count || 0)),
    standardized: o.context?.output_rows ||
      metricMap.fact_standardized?.value ||
      ((routeMap.fact_governed?.count || 0) + (routeMap.fact_pending_observation?.count || 0) + (routeMap.fact_pending_issue?.count || 0) + (routeMap.fact_rejected?.count || 0)),
    known_objects: metricMap.obj_cell?.value || 0,
    evidence_objects: metricMap.obj_cell?.value || 0,
    evidence_new: metricMap.obj_cell?.delta || 0,
    promotions: o.promotions ?? 0,
    demotions: o.demotions ?? 0,
    hasPromotionDelta: Boolean(o.promotions || o.demotions),
    cell_waiting: decisions['cell:waiting'] ?? 0,
    cell_observing: decisions['cell:observing'] ?? 0,
    cell_active: decisions['cell:active'] ?? (metricMap.obj_cell?.value || 0),
    cascade_bs: o.cascade_bs ?? 0,
    cascade_lac: o.cascade_lac ?? 0,
    cascade_total: o.cascade_total ?? 0,
    hasCascadeDelta: Boolean(o.cascade_bs || o.cascade_lac || o.cascade_total),
    bs_active: decisions['bs:active'] ?? (metricMap.obj_bs?.value || 0),
    lac_active: decisions['lac:active'] ?? (metricMap.obj_lac?.value || 0),
    anomaly_total: metricMap.anomalies?.value ?? o.anomaly_total ?? 0,
    anomaly_new: metricMap.anomalies?.delta ?? o.anomaly_new ?? 0,
    baseline_refreshed: o.baseline_refreshed ?? false,
    baseline_next_version: o.baseline_next_version ?? '',
  };
});

function flowRoute(routeName: string) {
  const flow = overview.value?.flow || [];
  return flow.find((f: any) => f.route === routeName) || { count: 0, ratio: 0 };
}

const summaryMetrics = computed(() => {
  if (!overview.value) return [];
  const metrics = overview.value.key_metrics || [];
  const LABELS: Record<string, string> = {
    obj_cell: '活跃对象',
    fact_pending_observation: '等待 + 观察中',
    fact_pending_issue: '异常对象',
    anchorable: '锚点可用',
    baseline_eligible: '基线可用',
    fact_governed: '已治理事实',
    baseline_cell: 'Cell 基线',
    baseline_bs: 'BS 基线',
    obj_bs: 'BS 覆盖',
    obj_lac: 'LAC 覆盖',
  };
  const INVERSE = new Set(['fact_pending_issue', 'fact_rejected', 'fact_pending_observation']);
  return metrics.slice(0, 8).map((m: any) => ({
    label: LABELS[m.metric_name] || m.label || m.metric_name,
    value: m.value ?? 0,
    batch: m.batch_delta ?? m.delta ?? 0,
    vs: m.prev_batch_delta ?? 0,
    inverse: INVERSE.has(m.metric_name),
  }));
});

function severityDotClass(severity: string): string {
  const map: Record<string, string> = {
    critical: 'critical',
    high: 'critical',
    warning: 'warning',
    medium: 'warning',
    caution: 'caution',
    low: 'caution',
    info: 'info',
  };
  return map[severity] || 'info';
}

async function loadPage() {
  loading.value = true;
  error.value = '';
  try {
    const data = await api.getFlowOverview();
    overview.value = data;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载流转总览';
  } finally {
    loading.value = false;
  }
}

onMounted(loadPage);
</script>
