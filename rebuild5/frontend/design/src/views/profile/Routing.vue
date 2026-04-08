<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { mockRoutingStats } from '../../mock/data'
import { fmt, pct } from '../../composables/useFormat'

const stats = mockRoutingStats
const pathA_pct = stats.path_a_record_count / stats.input_record_count
const pathB_pct = stats.path_b_record_count / stats.input_record_count
const pathC_pct = stats.path_c_drop_count / stats.input_record_count
</script>

<template>
  <PageHeader title="基础画像与分流" description="本批数据的三路径分流全景。命中正式库 → Path A，待评估 → Path B，数据不全 → Path C 丢弃。" />

  <!-- 分流概览 -->
  <div class="grid grid-4 mb-lg">
    <SummaryCard title="输入总量" :value="fmt(stats.input_record_count)" subtitle="来自 etl_cleaned" />
    <SummaryCard title="Path A 命中" :value="fmt(stats.path_a_record_count)" :subtitle="pct(pathA_pct) + ' → Step 4 补数'" color="var(--c-primary)" />
    <SummaryCard title="Path B 待评估" :value="fmt(stats.path_b_record_count)" :subtitle="pct(pathB_pct) + ' → Step 3 评估'" color="var(--c-success)" />
    <SummaryCard title="Path C 丢弃" :value="fmt(stats.path_c_drop_count)" :subtitle="pct(pathC_pct) + ' 数据不全'" color="var(--c-danger)" />
  </div>

  <!-- 分流条形图 -->
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
    <div class="flex gap-xl mt-md text-xs">
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-primary)"></span> Path A — 命中正式库 → 知识补数</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-success)"></span> Path B — 有 GPS，待评估 → 流式评估</span>
      <span class="flex items-center gap-xs"><span class="dot" style="background:var(--c-danger)"></span> Path C — 缺 GPS，丢弃</span>
    </div>
  </div>

  <!-- 碰撞防护 -->
  <div class="grid grid-2 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md">碰撞 cell_id 局部防护</div>
      <div class="grid grid-2 gap-md">
        <div class="mini-stat">
          <span class="text-xs text-muted">碰撞候选</span>
          <span class="font-mono font-semibold">{{ fmt(stats.collision_candidate_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">成功命中</span>
          <span class="font-mono font-semibold" style="color:var(--c-success)">{{ fmt(stats.collision_path_a_match_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">待定（缺 GPS）</span>
          <span class="font-mono font-semibold" style="color:var(--c-warning)">{{ fmt(stats.collision_pending_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">拦截丢弃</span>
          <span class="font-mono font-semibold" style="color:var(--c-danger)">{{ fmt(stats.collision_drop_count) }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md">Path B 基础画像统计</div>
      <div class="grid grid-2 gap-md">
        <div class="mini-stat">
          <span class="text-xs text-muted">待评估 Cell 数</span>
          <span class="font-mono font-semibold">{{ fmt(stats.path_b_cell_count) }}</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">平均观测点</span>
          <span class="font-mono font-semibold">228</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">平均设备数</span>
          <span class="font-mono font-semibold">4.2</span>
        </div>
        <div class="mini-stat">
          <span class="text-xs text-muted">平均 P90 (m)</span>
          <span class="font-mono font-semibold">680</span>
        </div>
      </div>
    </div>
  </div>

  <!-- 规则说明 -->
  <div class="card">
    <div class="font-semibold text-sm mb-sm">分流规则说明</div>
    <ul class="rule-list">
      <li><strong>Path A 命中规则</strong>：cell_id 在上一轮 trusted_cell_library 中匹配成功。碰撞 cell_id 需三字段全匹配 + GPS 距离 &lt; 2200m。</li>
      <li><strong>Path B 进入条件</strong>：未命中正式库，且本批记录中该 Cell 至少存在有效原始 GPS。</li>
      <li><strong>Path C 丢弃原因</strong>：未命中，且无有效 GPS，无法构建空间画像。冷启动阶段正常。</li>
      <li><strong>碰撞防护</strong>：三字段全匹配但 GPS 距离 ≥ 2200m 的记录视为错误命中，直接丢弃。</li>
    </ul>
  </div>
</template>

<style scoped>
.routing-bar { display: flex; height: 28px; border-radius: 6px; overflow: hidden; }
.seg { display: flex; align-items: center; justify-content: center; min-width: 40px; }
.seg-a { background: var(--c-primary); }
.seg-b { background: var(--c-success); }
.seg-c { background: var(--c-danger); }
.seg-label { color: white; font-size: 11px; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mini-stat { display: flex; flex-direction: column; gap: 2px; }
.rule-list { padding-left: 18px; font-size: 12px; color: var(--c-text-secondary); line-height: 2; }
</style>
