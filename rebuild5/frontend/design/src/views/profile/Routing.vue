<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getRoutingPayload, runProfilePipeline, type RoutingMetrics, type RoutingRules, type RoutingSummary } from '../../api/profile'
import { fmt, pct } from '../../composables/useFormat'

const summary = ref<RoutingSummary>({
  input_record_count: 0,
  path_a_record_count: 0,
  path_b_record_count: 0,
  path_b_cell_count: 0,
  path_c_drop_count: 0,
  collision_candidate_count: 0,
  collision_path_a_match_count: 0,
  collision_pending_count: 0,
  collision_drop_count: 0,
})
const metrics = ref<RoutingMetrics>({
  avg_independent_obs: 0,
  avg_independent_devs: 0,
  avg_observed_span_hours: 0,
  avg_p50_radius_m: 0,
  avg_p90_radius_m: 0,
  avg_gps_original_ratio: 0,
  avg_signal_original_ratio: 0,
  path_b_complete_cell_count: 0,
  path_b_partial_cell_count: 0,
})
const version = ref({ dataset_key: '', run_id: '', snapshot_version_prev: 'v0', snapshot_version: 'v0' })
const loading = ref(false)
const running = ref(false)
const message = ref('')
const rules = ref<RoutingRules>({
  collision_match_gps_threshold_m: 2200,
  obs_dedup_window_minutes: 1,
  centroid_algorithm: 'median',
})

const pathA_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_a_record_count / summary.value.input_record_count : 0)
const pathB_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_b_record_count / summary.value.input_record_count : 0)
const pathC_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_c_drop_count / summary.value.input_record_count : 0)
const isColdStart = computed(() => version.value.snapshot_version_prev === 'v0' && summary.value.path_a_record_count === 0)
const centroidLabel = computed(() => {
  const mapping: Record<string, string> = {
    median: '中位数',
    avg: '均值',
    weighted: '加权',
  }
  return mapping[rules.value.centroid_algorithm] || rules.value.centroid_algorithm
})

async function loadRouting() {
  loading.value = true
  try {
    const payload = await getRoutingPayload()
    summary.value = payload.summary
    metrics.value = payload.path_b_metrics
    version.value = payload.version
    rules.value = payload.rules
  } catch (error) {
    message.value = error instanceof Error ? error.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function runPipeline() {
  running.value = true
  message.value = ''
  try {
    const result = await runProfilePipeline()
    message.value = `已完成 ${result.run_id}，生成快照 ${result.snapshot_version}`
    await loadRouting()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '运行失败'
  } finally {
    running.value = false
  }
}

onMounted(() => {
  void loadRouting()
})
</script>

<template>
  <PageHeader title="基础画像与分流" description="本批数据的三路径分流全景。命中可信库 → A，进入评估 → B，信息不足 → C 丢弃。">
    <div class="header-row">
      <div class="text-xs text-secondary">
        <span v-if="loading">正在加载路由统计…</span>
        <span v-else>数据集 {{ version.dataset_key }} ｜ 运行 {{ version.run_id || '-' }} ｜ 引用 {{ version.snapshot_version_prev }} ｜ 当前 {{ version.snapshot_version }}</span>
      </div>
      <button class="btn btn-primary" :disabled="running" @click="runPipeline">
        {{ running ? '运行中…' : '运行 Step 2 + Step 3' }}
      </button>
    </div>
  </PageHeader>

  <div v-if="message" class="card mb-lg text-sm">{{ message }}</div>

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="输入总量" :value="fmt(summary.input_record_count)" subtitle="来自 etl_cleaned" />
    <SummaryCard title="命中可信库（A）" :value="fmt(summary.path_a_record_count)" :subtitle="pct(pathA_pct) + ' → Step 4 补数'" color="var(--c-primary)" />
    <SummaryCard title="进入评估（B）" :value="fmt(summary.path_b_record_count)" :subtitle="pct(pathB_pct) + ' → Step 3 评估'" color="var(--c-success)" />
    <SummaryCard title="信息不足丢弃（C）" :value="fmt(summary.path_c_drop_count)" :subtitle="pct(pathC_pct) + ' 数据不全'" color="var(--c-danger)" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">分流比例</div>
    <div class="routing-bar">
      <div class="seg seg-a" :style="{ width: pathA_pct * 100 + '%' }">
        <span class="seg-label">A {{ pct(pathA_pct) }}</span>
      </div>
      <div class="seg seg-b" :style="{ width: pathB_pct * 100 + '%' }">
        <span class="seg-label">B {{ pct(pathB_pct) }}</span>
      </div>
      <div class="seg seg-c" :style="{ width: pathC_pct * 100 + '%' }">
        <span class="seg-label">C {{ pct(pathC_pct) }}</span>
      </div>
    </div>
    <div class="flex gap-xl mt-md text-xs wrap-row">
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-primary)"></span> 命中可信库（A）— 命中正式库 → 知识补数</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-success)"></span> 进入评估（B）— 有有效 GPS 证据 → 流式评估</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-danger)"></span> 信息不足丢弃（C）— 缺 GPS 或缺关键字段，丢弃</span>
    </div>
  </div>

    <div class="grid grid-2 gap-lg mb-lg">
      <div class="card">
        <div class="font-semibold text-sm mb-md">碰撞 cell_id 局部防护</div>
      <div class="grid grid-2 gap-md">
        <div class="mini-stat">
          <span class="text-xs text-muted">碰撞候选</span>
          <span class="font-mono font-semibold">{{ fmt(summary.collision_candidate_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">成功命中</span>
          <span class="font-mono font-semibold" style="color:var(--c-success)">{{ fmt(summary.collision_path_a_match_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">待定（缺 GPS）</span>
          <span class="font-mono font-semibold" style="color:var(--c-warning)">{{ fmt(summary.collision_pending_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">拦截丢弃</span>
          <span class="font-mono font-semibold" style="color:var(--c-danger)">{{ fmt(summary.collision_drop_count) }}</span>
        </div>
      </div>
    </div>

      <div class="card">
        <div class="font-semibold text-sm mb-md">进入评估（B）基础画像统计</div>
        <div class="grid grid-2 gap-md">
          <div class="mini-stat">
            <span class="text-xs text-muted">待评估 Cell 数</span>
            <span class="font-mono font-semibold">{{ fmt(summary.path_b_cell_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">平均观测点</span>
          <span class="font-mono font-semibold">{{ metrics.avg_independent_obs.toFixed(1) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">平均设备数</span>
          <span class="font-mono font-semibold">{{ metrics.avg_independent_devs.toFixed(1) }}</span>
        </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">平均 P90 (m)</span>
            <span class="font-mono font-semibold">{{ metrics.avg_p90_radius_m.toFixed(1) }}</span>
          </div>
        </div>
        <div class="mini-grid mt-md">
          <div class="mini-stat">
            <span class="text-xs text-muted">平均跨度 (h)</span>
            <span class="font-mono font-semibold">{{ metrics.avg_observed_span_hours.toFixed(1) }}</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">平均 P50 (m)</span>
            <span class="font-mono font-semibold">{{ metrics.avg_p50_radius_m.toFixed(1) }}</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">完整 Cell</span>
            <span class="font-mono font-semibold">{{ fmt(metrics.path_b_complete_cell_count) }}</span>
        </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">部分缺口 Cell</span>
            <span class="font-mono font-semibold">{{ fmt(metrics.path_b_partial_cell_count) }}</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">平均 GPS 原始覆盖率</span>
            <span class="font-mono font-semibold">{{ pct(metrics.avg_gps_original_ratio) }}</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">平均信号原始覆盖率</span>
            <span class="font-mono font-semibold">{{ pct(metrics.avg_signal_original_ratio) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-2 gap-lg mb-lg">
      <div class="card">
        <div class="font-semibold text-sm mb-md">当前规则口径</div>
        <div class="mini-grid">
          <div class="mini-stat">
            <span class="text-xs text-muted">碰撞 GPS 阈值</span>
            <span class="font-mono font-semibold">{{ fmt(rules.collision_match_gps_threshold_m) }}m</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">观测去重窗口</span>
            <span class="font-mono font-semibold">{{ fmt(rules.obs_dedup_window_minutes) }} 分钟</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">质心算法</span>
            <span class="font-mono font-semibold">{{ centroidLabel }}</span>
          </div>
          <div class="mini-stat">
            <span class="text-xs text-muted">交互状态</span>
            <span class="font-semibold">只读展示</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="font-semibold text-sm mb-md">当前支持 / 待开发</div>
        <div class="status-columns">
          <div>
            <div class="status-title">当前支持</div>
            <ul class="rule-list compact">
              <li>数据版本头部、A/B/C 分流概览、碰撞防护摘要</li>
              <li>进入评估（B）基础指标与完整度摘要</li>
              <li>当前规则口径只读展示</li>
            </ul>
          </div>
          <div>
            <div class="status-title">待开发</div>
            <ul class="rule-list compact">
              <li>按运营商 / LAC 筛选</li>
              <li>碰撞样本明细、进入评估（B）列表</li>
              <li>跳转 Step 3 / Step 4 的联动入口</li>
              <li>在线调整规则参数</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-sm">分流规则说明</div>
      <ul class="rule-list">
        <li>
          <strong>命中可信库（A）规则</strong>：
          <template v-if="isColdStart">当前为冷启动口径，上一轮正式库为空，因此命中可信库仍为 0。</template>
          <template v-else>当前按上一轮正式库执行命中判定，本批已命中 {{ fmt(summary.path_a_record_count) }} 条记录。</template>
        </li>
        <li><strong>进入评估（B）条件</strong>：未命中正式库，且同一个 Cell 至少存在 1 条原始有效 GPS 记录。</li>
        <li><strong>信息不足丢弃（C）汇总口径</strong>：当前展示为剩余丢弃总量；若存在碰撞局部防护拦截，请结合上方碰撞拦截丢弃数一并解释。</li>
        <li><strong>碰撞阈值</strong>：局部防护保留 {{ fmt(rules.collision_match_gps_threshold_m) }}m 口径，当前页面只读展示，不在线调整。</li>
      </ul>
    </div>
  </template>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-md);
  margin-top: var(--sp-md);
}
.routing-bar { display: flex; height: 28px; border-radius: 6px; overflow: hidden; }
.seg { display: flex; align-items: center; justify-content: center; min-width: 40px; }
.seg-a { background: var(--c-primary); }
.seg-b { background: var(--c-success); }
.seg-c { background: var(--c-danger); }
.seg-label { color: white; font-size: 11px; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mini-stat { display: flex; flex-direction: column; gap: 2px; }
.mini-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-md); }
.rule-list { padding-left: 18px; font-size: 12px; color: var(--c-text-secondary); line-height: 2; }
.rule-list.compact { margin: 0; line-height: 1.8; }
.wrap-row { flex-wrap: wrap; }
.status-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-lg);
}
.status-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: var(--sp-sm);
}
@media (max-width: 900px) {
  .header-row { flex-direction: column; align-items: flex-start; }
  .status-columns { grid-template-columns: 1fr; }
}
</style>
