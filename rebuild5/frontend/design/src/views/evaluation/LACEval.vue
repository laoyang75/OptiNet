<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { mockLACStateDistribution, mockLACList } from '../../mock/data'
import { pct } from '../../composables/useFormat'
</script>

<template>
  <PageHeader title="LAC 评估" description="区域整体质量。LAC 完全由下属 BS 上卷而来。" />

  <StateDistribution title="LAC 状态分布" :data="mockLACStateDistribution" class="mb-lg" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>LAC</th>
          <th>运营商</th>
          <th>状态</th>
          <th>锚点</th>
          <th>总 BS</th>
          <th>qualified BS</th>
          <th style="width:160px">qualified 比例</th>
          <th>晋升分析</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="l in mockLACList" :key="l.lac">
          <td class="font-mono font-semibold">{{ l.lac }}</td>
          <td class="font-mono text-xs">{{ l.operator_code }}</td>
          <td><StatusTag :state="l.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="l.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ l.total_bs }}</td>
          <td class="font-mono">{{ l.qualified_bs }}</td>
          <td><PercentBar :value="l.qualified_bs_ratio" /></td>
          <td class="text-xs text-secondary">
            <template v-if="l.qualified_bs >= 3 || l.qualified_bs_ratio >= 0.1">
              已达标（qualified BS ≥ 3 或占比 ≥ 10%）
            </template>
            <template v-else>
              差 {{ Math.max(0, 3 - l.qualified_bs) }} 个 qualified BS
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">LAC 晋升规则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li><strong>qualified</strong>：qualified BS ≥ 3，或 qualified BS / 全部 BS ≥ 10%</li>
      <li><strong>observing</strong>：至少 1 个下属 BS 为非 waiting</li>
      <li>LAC 不跳过 BS 直接从 Cell 重判</li>
    </ul>
  </div>
</template>
