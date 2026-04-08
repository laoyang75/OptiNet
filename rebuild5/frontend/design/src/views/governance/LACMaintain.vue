<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { mockLACList } from '../../mock/data'

const lacMaintenance = mockLACList.map(l => ({
  ...l,
  anomaly_bs_ratio: Math.random() * 0.2,
  trend: ['stable', 'improving', 'degrading'][Math.floor(Math.random() * 3)] as string,
}))
</script>

<template>
  <PageHeader title="LAC 维护" description="区域层整体质量趋势，异常 BS 比例变化和退出预警。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="LAC 总量" :value="String(mockLACList.length)" />
    <SummaryCard title="异常 BS 占比最高" value="18.2%" subtitle="LAC 4003" color="var(--c-danger)" />
    <SummaryCard title="整体趋势" value="改善中" subtitle="3 个 LAC 质量提升" color="var(--c-success)" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>LAC</th>
          <th>运营商</th>
          <th>状态</th>
          <th>总 BS</th>
          <th>qualified BS</th>
          <th style="width:140px">qualified 比例</th>
          <th style="width:140px">异常 BS 比例</th>
          <th>趋势</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="l in lacMaintenance" :key="l.lac">
          <td class="font-mono font-semibold">{{ l.lac }}</td>
          <td class="font-mono text-xs">{{ l.operator_code }}</td>
          <td><StatusTag :state="l.lifecycle_state" size="sm" /></td>
          <td class="font-mono">{{ l.total_bs }}</td>
          <td class="font-mono">{{ l.qualified_bs }}</td>
          <td><PercentBar :value="l.qualified_bs_ratio" /></td>
          <td><PercentBar :value="l.anomaly_bs_ratio" color="var(--c-danger)" /></td>
          <td>
            <span class="tag" :style="l.trend === 'improving' ? 'background:#dcfce7;color:#166534' : l.trend === 'degrading' ? 'background:#fee2e2;color:#991b1b' : 'background:#f3f4f6;color:#6b7280'">
              {{ l.trend === 'improving' ? '↑ 改善' : l.trend === 'degrading' ? '↓ 恶化' : '→ 稳定' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">LAC 维护说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>区域质量由下属 BS 聚合，不跳过 BS 直接从 Cell 重判</li>
      <li>异常 BS 比例 = (碰撞 + 迁移 + 大覆盖 BS) / 总 BS</li>
      <li>趋势基于最近 3 批运行的 qualified_bs_ratio 变化</li>
    </ul>
  </div>
</template>
