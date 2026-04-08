<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { mockSnapshotDiff } from '../../mock/data'
import { fmt } from '../../composables/useFormat'
import type { LifecycleState } from '../../types'

const diffItems: Array<{ cell_id: string; lac: string; op: string; prev: LifecycleState; curr: LifecycleState; reason: string }> = [
  { cell_id: '10023', lac: '4001', op: '46000', prev: 'observing', curr: 'qualified', reason: 'independent_obs 达标，p90 < 1500m' },
  { cell_id: '10045', lac: '4002', op: '46001', prev: 'waiting', curr: 'observing', reason: '首次积累到 3 条独立观测' },
  { cell_id: '10078', lac: '4001', op: '46000', prev: 'qualified', curr: 'excellent', reason: 'obs ≥ 8, dev ≥ 3, p90 < 500m' },
  { cell_id: '10112', lac: '4003', op: '46011', prev: 'qualified', curr: 'dormant', reason: '连续 5 批无新数据' },
  { cell_id: '10156', lac: '4002', op: '46001', prev: 'excellent', curr: 'qualified', reason: 'p90 回升至 620m，不满足 excellent' },
]
</script>

<template>
  <PageHeader title="流转快照" description="查看 trusted_snapshot_t 的完整状态，与上一版快照的差异对比。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="快照版本" value="v3" subtitle="vs v2" />
    <SummaryCard title="晋升" :value="fmt(mockSnapshotDiff.promoted)" color="var(--c-success)" />
    <SummaryCard title="降级" :value="fmt(mockSnapshotDiff.demoted)" color="var(--c-danger)" />
    <SummaryCard title="未变化" :value="fmt(mockSnapshotDiff.unchanged)" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0">
      <span class="font-semibold text-sm">变动对象列表</span>
      <span class="text-xs text-muted" style="margin-left:8px">仅显示状态发生变化的对象</span>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th>cell_id</th>
          <th>LAC</th>
          <th>运营商</th>
          <th>前状态</th>
          <th>→</th>
          <th>现状态</th>
          <th>变化原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in diffItems" :key="d.cell_id">
          <td class="font-mono font-semibold">{{ d.cell_id }}</td>
          <td class="font-mono">{{ d.lac }}</td>
          <td class="font-mono text-xs">{{ d.op }}</td>
          <td><StatusTag :state="d.prev" size="sm" /></td>
          <td class="text-muted">→</td>
          <td><StatusTag :state="d.curr" size="sm" /></td>
          <td class="text-sm text-secondary">{{ d.reason }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
