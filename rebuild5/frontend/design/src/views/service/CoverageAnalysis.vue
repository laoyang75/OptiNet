<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { fmt } from '../../composables/useFormat'

const operators = [
  { name: '中国移动', cells: 2840, qualifiedPct: 0.68, excellentPct: 0.22, avgP90: 620 },
  { name: '中国联通', cells: 2120, qualifiedPct: 0.61, excellentPct: 0.18, avgP90: 740 },
  { name: '中国电信', cells: 1880, qualifiedPct: 0.55, excellentPct: 0.15, avgP90: 810 },
]
</script>

<template>
  <PageHeader title="覆盖分析" description="区域覆盖密度、质量结构和运营商对比。面向业务用户。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="可信 Cell 总量" :value="fmt(6840)" subtitle="qualified + excellent" />
    <SummaryCard title="覆盖 LAC 数" value="6" subtitle="sample_6lac" />
    <SummaryCard title="平均 P90 精度" value="720m" subtitle="全运营商加权" />
  </div>

  <!-- 运营商对比 -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">运营商覆盖对比</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>运营商</th>
          <th>可信 Cell 数</th>
          <th style="width:160px">qualified+ 占比</th>
          <th style="width:160px">excellent 占比</th>
          <th>平均 P90 (m)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="op in operators" :key="op.name">
          <td class="font-semibold">{{ op.name }}</td>
          <td class="font-mono">{{ fmt(op.cells) }}</td>
          <td><PercentBar :value="op.qualifiedPct" /></td>
          <td><PercentBar :value="op.excellentPct" color="var(--c-excellent)" /></td>
          <td class="font-mono">{{ op.avgP90 }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 密度图预留 -->
  <div class="card" style="height:240px;display:flex;align-items:center;justify-content:center;background:var(--c-bg)">
    <span class="text-muted text-sm">覆盖密度热力图（预留，后续接入地图组件）</span>
  </div>
</template>
