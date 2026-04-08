<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import StateDistribution from '../../components/common/StateDistribution.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { mockBSStateDistribution, mockBSList } from '../../mock/data'
</script>

<template>
  <PageHeader title="BS 评估" description="BS 由下属 Cell 上卷而来。查看 BS 状态、下属 Cell 构成和晋升条件。" />

  <StateDistribution title="BS 状态分布" :data="mockBSStateDistribution" class="mb-lg" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>bs_id</th>
          <th>LAC</th>
          <th>运营商</th>
          <th>状态</th>
          <th>锚点</th>
          <th>总 Cell</th>
          <th>qualified+ Cell</th>
          <th>excellent Cell</th>
          <th>大覆盖</th>
          <th>晋升分析</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in mockBSList" :key="b.bs_id">
          <td class="font-mono font-semibold">{{ b.bs_id }}</td>
          <td class="font-mono">{{ b.lac }}</td>
          <td class="font-mono text-xs">{{ b.operator_code }}</td>
          <td><StatusTag :state="b.lifecycle_state" size="sm" /></td>
          <td>
            <span v-if="b.anchor_eligible" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="font-mono">{{ b.total_cells }}</td>
          <td class="font-mono" :style="b.qualified_cells >= 3 ? 'color:var(--c-success)' : ''">{{ b.qualified_cells }}</td>
          <td class="font-mono" :style="b.excellent_cells >= 1 ? 'color:var(--c-excellent)' : ''">{{ b.excellent_cells }}</td>
          <td>
            <span v-if="b.large_spread" class="tag" style="background:#fef3c7;color:#92400e">大覆盖</span>
            <span v-else class="text-muted text-xs">-</span>
          </td>
          <td class="text-xs text-secondary">
            <template v-if="b.excellent_cells >= 1">有 excellent Cell，已达标</template>
            <template v-else-if="b.qualified_cells >= 3">qualified+ ≥ 3，已达标</template>
            <template v-else>差 {{ Math.max(0, 3 - b.qualified_cells) }} 个 qualified+ Cell</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">BS 晋升规则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li><strong>qualified</strong>：≥ 1 个 excellent Cell，或 ≥ 3 个 qualified+ Cell</li>
      <li><strong>observing</strong>：至少 1 个下属 Cell 有 GPS 证据</li>
      <li><strong>anchor_eligible</strong>：至少 1 个下属 Cell 为 anchor_eligible</li>
      <li>BS 不直接读取原始报文，只看下属 Cell 聚合结果</li>
    </ul>
  </div>
</template>
