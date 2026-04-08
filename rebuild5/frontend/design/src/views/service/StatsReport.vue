<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { fmt } from '../../composables/useFormat'
</script>

<template>
  <PageHeader title="统计报表" description="可复用的汇总结果和趋势报表。保留版本标识，保证报表可追溯。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="数据集" value="sample_6lac" />
    <SummaryCard title="快照版本" value="v3" />
    <SummaryCard title="统计时间" value="2026-04-08" />
    <SummaryCard title="覆盖 LAC" value="6" />
  </div>

  <!-- 汇总报表 -->
  <div class="card mb-lg">
    <div class="flex justify-between items-center mb-md">
      <span class="font-semibold text-sm">按 LAC 汇总</span>
      <button class="btn">导出 CSV</button>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>LAC</th>
          <th>运营商</th>
          <th>Cell 总量</th>
          <th>qualified+ Cell</th>
          <th>excellent Cell</th>
          <th>BS 总量</th>
          <th>qualified+ BS</th>
          <th>平均 P90 (m)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in 6" :key="i">
          <td class="font-mono font-semibold">{{ 4000 + i - 1 }}</td>
          <td>{{ ['中国移动','中国联通','中国电信'][i % 3] }}</td>
          <td class="font-mono">{{ fmt(Math.floor(Math.random() * 800 + 400)) }}</td>
          <td class="font-mono">{{ fmt(Math.floor(Math.random() * 500 + 200)) }}</td>
          <td class="font-mono">{{ fmt(Math.floor(Math.random() * 200 + 50)) }}</td>
          <td class="font-mono">{{ fmt(Math.floor(Math.random() * 200 + 50)) }}</td>
          <td class="font-mono">{{ fmt(Math.floor(Math.random() * 100 + 20)) }}</td>
          <td class="font-mono">{{ Math.floor(Math.random() * 500 + 400) }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 趋势区域预留 -->
  <div class="card" style="height:200px;display:flex;align-items:center;justify-content:center;background:var(--c-bg)">
    <span class="text-muted text-sm">趋势图表（预留，后续接入图表库）</span>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">报表说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>所有数据基于快照版本 v3，数据集 sample_6lac</li>
      <li>qualified+ 包含 qualified 和 excellent 两个状态</li>
      <li>导出文件包含版本标识，保证可追溯</li>
    </ul>
  </div>
</template>
