<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { mockCellStateDistribution, mockCells } from '../../mock/data'
import { fmt } from '../../composables/useFormat'
import { OPERATORS } from '../../types'
</script>

<template>
  <PageHeader title="Cell 评估" description="单个 Cell 的状态、资格和晋升差距。支持按状态、资格、运营商筛选。" />

  <StateDistribution title="Cell 状态分布" :data="mockCellStateDistribution" class="mb-lg" />

  <!-- 筛选区 -->
  <div class="card mb-lg flex gap-md items-center">
    <select class="filter-select">
      <option value="">全部状态</option>
      <option v-for="s in ['excellent','qualified','observing','waiting','dormant','retired']" :key="s">{{ s }}</option>
    </select>
    <select class="filter-select">
      <option value="">全部运营商</option>
      <option v-for="op in OPERATORS" :key="op.operator_code" :value="op.operator_code">{{ op.operator_cn }}</option>
    </select>
    <label class="flex items-center gap-xs text-xs">
      <input type="checkbox" /> 仅锚点
    </label>
    <label class="flex items-center gap-xs text-xs">
      <input type="checkbox" /> 仅基线
    </label>
  </div>

  <!-- Cell 列表 -->
  <div class="card" style="padding:0;overflow:auto;max-height:520px">
    <table class="data-table">
      <thead>
        <tr>
          <th>cell_id</th>
          <th>LAC</th>
          <th>bs_id</th>
          <th>运营商</th>
          <th>制式</th>
          <th>状态</th>
          <th>锚点</th>
          <th>观测量</th>
          <th>设备数</th>
          <th>P90 (m)</th>
          <th>跨度 (h)</th>
          <th>活跃天</th>
          <th>RSRP 均</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in mockCells" :key="c.cell_id">
          <td class="font-mono font-semibold">{{ c.cell_id }}</td>
          <td class="font-mono">{{ c.lac }}</td>
          <td class="font-mono text-xs">{{ c.bs_id }}</td>
          <td class="font-mono text-xs">{{ c.operator_code }}</td>
          <td><span class="tag" :style="c.tech_norm === '5G' ? 'background:#ede9fe;color:#6d28d9' : 'background:#e0f2fe;color:#075985'">{{ c.tech_norm }}</span></td>
          <td><StatusTag :state="c.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="c.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ c.independent_obs }}</td>
          <td class="font-mono">{{ c.distinct_dev_id }}</td>
          <td class="font-mono">{{ c.p90_radius_m }}</td>
          <td class="font-mono">{{ c.observed_span_hours }}</td>
          <td class="font-mono">{{ c.active_days }}</td>
          <td class="font-mono">{{ c.rsrp_avg ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.filter-select {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  background: var(--c-surface);
}
</style>
