<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import type { LifecycleState } from '../../types'

interface WatchItem {
  cell_id: string; lac: string; op: string; state: LifecycleState
  obs: number; devs: number; p90: number; span_h: number
  gap: string
}

const items: WatchItem[] = [
  { cell_id: '10201', lac: '4001', op: '46000', state: 'observing', obs: 3, devs: 2, p90: 1680, span_h: 30, gap: 'p90 差 180m（需 < 1500m）' },
  { cell_id: '10202', lac: '4002', op: '46001', state: 'observing', obs: 5, devs: 1, p90: 920, span_h: 48, gap: '设备数差 1（需 ≥ 2）' },
  { cell_id: '10203', lac: '4001', op: '46000', state: 'waiting', obs: 2, devs: 1, p90: 0, span_h: 8, gap: '观测量差 1，设备数差 1' },
  { cell_id: '10204', lac: '4003', op: '46011', state: 'observing', obs: 4, devs: 3, p90: 1200, span_h: 18, gap: '跨度差 6h（需 ≥ 24h）' },
  { cell_id: '10205', lac: '4002', op: '46001', state: 'observing', obs: 6, devs: 2, p90: 480, span_h: 36, gap: '已满足 qualified，碰撞阻断中' },
  { cell_id: '10206', lac: '4001', op: '46000', state: 'waiting', obs: 1, devs: 1, p90: 0, span_h: 2, gap: '首次出现，证据极少' },
]
</script>

<template>
  <PageHeader title="观察工作台" description="找出仍在 waiting / observing 的对象，诊断离晋升还差什么条件。" />

  <div class="card mb-lg">
    <div class="flex justify-between items-center mb-md">
      <span class="font-semibold text-sm">观察对象列表</span>
      <div class="flex gap-sm">
        <button class="btn">waiting</button>
        <button class="btn">observing</button>
        <button class="btn">全部</button>
      </div>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>cell_id</th>
          <th>LAC</th>
          <th>运营商</th>
          <th>状态</th>
          <th>观测量</th>
          <th>设备数</th>
          <th>P90 (m)</th>
          <th>跨度 (h)</th>
          <th>晋升差距</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.cell_id">
          <td class="font-mono font-semibold">{{ item.cell_id }}</td>
          <td class="font-mono">{{ item.lac }}</td>
          <td class="font-mono text-xs">{{ item.op }}</td>
          <td><StatusTag :state="item.state" size="sm" /></td>
          <td class="font-mono" :style="item.obs < 3 ? 'color:var(--c-danger)' : ''">{{ item.obs }}</td>
          <td class="font-mono" :style="item.devs < 2 ? 'color:var(--c-danger)' : ''">{{ item.devs }}</td>
          <td class="font-mono" :style="item.p90 > 1500 ? 'color:var(--c-danger)' : ''">{{ item.p90 || '-' }}</td>
          <td class="font-mono" :style="item.span_h < 24 ? 'color:var(--c-warning)' : ''">{{ item.span_h }}</td>
          <td class="text-sm" style="color:var(--c-dormant);white-space:normal;max-width:240px">{{ item.gap }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">晋升条件参考（qualified）</div>
    <div class="grid grid-4 gap-md text-xs">
      <div><span class="text-muted">观测量</span> <code>≥ 3</code></div>
      <div><span class="text-muted">设备数</span> <code>≥ 2</code></div>
      <div><span class="text-muted">P90</span> <code>&lt; 1500m</code></div>
      <div><span class="text-muted">跨度</span> <code>≥ 24h</code></div>
    </div>
  </div>
</template>

<style scoped>
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
