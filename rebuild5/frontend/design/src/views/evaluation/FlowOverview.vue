<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import { mockCellStateDistribution, mockBSStateDistribution, mockLACStateDistribution, mockSnapshotDiff } from '../../mock/data'
import { fmt } from '../../composables/useFormat'

const cellTotal = Object.values(mockCellStateDistribution).reduce((a, b) => a + b, 0)
const bsTotal = Object.values(mockBSStateDistribution).reduce((a, b) => a + b, 0)
const lacTotal = Object.values(mockLACStateDistribution).reduce((a, b) => a + b, 0)
</script>

<template>
  <PageHeader title="流转总览" description="三层对象整体收敛情况。从总览可跳到具体层级评估页面。" />

  <!-- 核心指标 -->
  <div class="grid grid-6 mb-lg">
    <SummaryCard title="Cell 总量" :value="fmt(cellTotal)" />
    <SummaryCard title="BS 总量" :value="fmt(bsTotal)" />
    <SummaryCard title="LAC 总量" :value="fmt(lacTotal)" />
    <SummaryCard title="本批晋升" :value="fmt(mockSnapshotDiff.promoted)" color="var(--c-success)" />
    <SummaryCard title="本批降级" :value="fmt(mockSnapshotDiff.demoted)" color="var(--c-danger)" />
    <SummaryCard title="锚点 Cell" :value="fmt(mockCellStateDistribution.excellent + mockCellStateDistribution.qualified)" subtitle="anchor_eligible" />
  </div>

  <!-- 三层状态分布 -->
  <div class="flex flex-col gap-lg mb-lg">
    <StateDistribution title="Cell 状态分布" :data="mockCellStateDistribution" />
    <StateDistribution title="BS 状态分布" :data="mockBSStateDistribution" />
    <StateDistribution title="LAC 状态分布" :data="mockLACStateDistribution" />
  </div>

  <!-- 差异摘要 -->
  <div class="grid grid-2 gap-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md">本批变动摘要（vs 上一版快照）</div>
      <div class="diff-grid">
        <div class="diff-item"><span class="text-xs text-muted">新注册</span><span class="font-mono font-semibold">+{{ fmt(mockSnapshotDiff.new_registered) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">晋升 qualified</span><span class="font-mono font-semibold" style="color:var(--c-qualified)">+{{ fmt(mockSnapshotDiff.newly_qualified) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">晋升 excellent</span><span class="font-mono font-semibold" style="color:var(--c-excellent)">+{{ fmt(mockSnapshotDiff.newly_excellent) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">降级</span><span class="font-mono font-semibold" style="color:var(--c-danger)">{{ fmt(mockSnapshotDiff.demoted) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">进入休眠</span><span class="font-mono font-semibold" style="color:var(--c-dormant)">{{ fmt(mockSnapshotDiff.entered_dormant) }}</span></div>
        <div class="diff-item"><span class="text-xs text-muted">确认退出</span><span class="font-mono font-semibold" style="color:var(--c-retired)">{{ fmt(mockSnapshotDiff.entered_retired) }}</span></div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md">快速跳转</div>
      <div class="flex flex-col gap-sm">
        <router-link to="/evaluation/snapshot" class="jump-link">流转快照 → 查看版本差异详情</router-link>
        <router-link to="/evaluation/watchlist" class="jump-link">观察工作台 → 找出离晋升最近的对象</router-link>
        <router-link to="/evaluation/cell" class="jump-link">Cell 评估 → 单个 Cell 状态与规则</router-link>
        <router-link to="/evaluation/bs" class="jump-link">BS 评估 → 基站下属 Cell 构成</router-link>
        <router-link to="/evaluation/lac" class="jump-link">LAC 评估 → 区域整体质量</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-md); }
.diff-item { display: flex; flex-direction: column; gap: 2px; }
.jump-link {
  display: block;
  padding: 8px 12px;
  font-size: 12px;
  background: var(--c-bg);
  border-radius: var(--radius-md);
  color: var(--c-primary);
  transition: background 0.1s;
}
.jump-link:hover { background: var(--c-primary-light); text-decoration: none; }
</style>
