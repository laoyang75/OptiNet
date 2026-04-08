<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { mockBSList } from '../../mock/data'
import { fmt } from '../../composables/useFormat'

const anomalyBS = mockBSList.filter(b => b.large_spread || b.lifecycle_state === 'dormant')
</script>

<template>
  <PageHeader title="BS 维护" description="BS 层面的面积异常、多质心、下属 Cell 健康度和退出预警。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="总 BS" :value="fmt(mockBSList.length)" />
    <SummaryCard title="大覆盖 BS" :value="fmt(mockBSList.filter(b => b.large_spread).length)" subtitle="max(cell_to_bs) > 2500m" color="var(--c-warning)" />
    <SummaryCard title="休眠 BS" :value="fmt(mockBSList.filter(b => b.lifecycle_state === 'dormant').length)" color="var(--c-dormant)" />
    <SummaryCard title="异常 BS 占比" value="15%" subtitle="需重点关注" color="var(--c-danger)" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0">
      <span class="font-semibold text-sm">异常 BS 列表</span>
      <span class="text-xs text-muted" style="margin-left:8px">面积异常或处于退出链路</span>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th>bs_id</th>
          <th>LAC</th>
          <th>运营商</th>
          <th>状态</th>
          <th>总 Cell</th>
          <th>qualified+ Cell</th>
          <th>大覆盖</th>
          <th>异常来源</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in anomalyBS" :key="b.bs_id">
          <td class="font-mono font-semibold">{{ b.bs_id }}</td>
          <td class="font-mono">{{ b.lac }}</td>
          <td class="font-mono text-xs">{{ b.operator_code }}</td>
          <td><StatusTag :state="b.lifecycle_state" size="sm" /></td>
          <td class="font-mono">{{ b.total_cells }}</td>
          <td class="font-mono">{{ b.qualified_cells }}</td>
          <td>
            <span v-if="b.large_spread" class="tag" style="background:#fef3c7;color:#92400e">&#10003; 大覆盖</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="text-xs text-secondary">
            <template v-if="b.large_spread">下属 Cell 离散 &gt; 2500m</template>
            <template v-else-if="b.lifecycle_state === 'dormant'">连续多批无新数据</template>
            <template v-else>-</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">BS 维护规则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li><strong>面积异常</strong>：max(下属 Cell 到 BS 质心距离) &gt; 2500m → large_spread 标记</li>
      <li><strong>下属 Cell 健康度</strong>：异常 Cell（碰撞/迁移/多质心）占比过高时标记</li>
      <li><strong>退出管理</strong>：所有下属 Cell 均为 dormant 或 retired 时，BS 联动退出</li>
    </ul>
  </div>
</template>
