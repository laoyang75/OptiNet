<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getRoutingPayload, runProfilePipeline, type RoutingMetrics, type RoutingSummary } from '../../api/profile'
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
const version = ref({ dataset_key: 'sample_6lac', run_id: '', snapshot_version_prev: 'v0', snapshot_version: 'v0' })
const loading = ref(false)
const running = ref(false)
const message = ref('')
const collisionThreshold = ref(2200)

const pathA_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_a_record_count / summary.value.input_record_count : 0)
const pathB_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_b_record_count / summary.value.input_record_count : 0)
const pathC_pct = computed(() => summary.value.input_record_count > 0 ? summary.value.path_c_drop_count / summary.value.input_record_count : 0)

async function loadRouting() {
  loading.value = true
  try {
    const payload = await getRoutingPayload()
    summary.value = payload.summary
    metrics.value = payload.path_b_metrics
    version.value = payload.version
    collisionThreshold.value = Number(payload.rules.collision_match_gps_threshold_m ?? 2200)
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
  <PageHeader title="基础画像与分流" description="本批数据的三路径分流全景。命中正式库 → Path A，待评估 → Path B，数据不全 → Path C 丢弃。">
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
    <SummaryCard title="Path A 命中" :value="fmt(summary.path_a_record_count)" :subtitle="pct(pathA_pct) + ' → Step 4 补数'" color="var(--c-primary)" />
    <SummaryCard title="Path B 待评估" :value="fmt(summary.path_b_record_count)" :subtitle="pct(pathB_pct) + ' → Step 3 评估'" color="var(--c-success)" />
    <SummaryCard title="Path C 丢弃" :value="fmt(summary.path_c_drop_count)" :subtitle="pct(pathC_pct) + ' 数据不全'" color="var(--c-danger)" />
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
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-primary)"></span> Path A — 命中正式库 → 知识补数</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-success)"></span> Path B — 有 GPS，待评估 → 流式评估</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-danger)"></span> Path C — 缺 GPS 或缺关键字段，丢弃</span>
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
      <div class="font-semibold text-sm mb-md">Path B 基础画像统计</div>
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
          <span class="text-xs text-muted">完整 Cell</span>
          <span class="font-mono font-semibold">{{ fmt(metrics.path_b_complete_cell_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">部分缺口 Cell</span>
          <span class="font-mono font-semibold">{{ fmt(metrics.path_b_partial_cell_count) }}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">分流规则说明</div>
    <ul class="rule-list">
      <li><strong>Path A 命中规则</strong>：本期冷启动，未接入 Step 5 正式库，因此当前批次 Path A 为 0。</li>
      <li><strong>Path B 进入条件</strong>：未命中正式库，且同一个 Cell 至少存在 1 条原始有效 GPS 记录。</li>
      <li><strong>Path C 丢弃原因</strong>：未命中，且缺少可用于空间画像的 GPS 或关键标识字段。</li>
      <li><strong>碰撞阈值</strong>：局部防护保留 {{ collisionThreshold }}m 口径，等待后续 Step 5 正式库启用。</li>
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
.wrap-row { flex-wrap: wrap; }
@media (max-width: 900px) {
  .header-row { flex-direction: column; align-items: flex-start; }
}
</style>
