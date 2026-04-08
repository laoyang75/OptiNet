<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { fmt } from '../../composables/useFormat'

const parseStats = {
  inputRecords: 1_248_350,
  outputRecords: 3_872_640,
  expansionRatio: 3.1,
  sources: [
    { name: 'cell_infos 解析', inputCount: 1_248_350, outputCount: 3_124_200, ratio: 2.5 },
    { name: 'ss1 解析', inputCount: 1_248_350, outputCount: 748_440, ratio: 0.6 },
  ],
}

const coverageChange = [
  { field: 'bs_id', before: 0.45, after: 0.95 },
  { field: 'tech_norm', before: 0.32, after: 0.88 },
  { field: 'cell_id', before: 0.99, after: 1.0 },
  { field: 'rsrp', before: 0.25, after: 0.73 },
  { field: 'lac', before: 0.88, after: 0.98 },
]
</script>

<template>
  <PageHeader title="解析" description="判断 cell_infos 和 ss1 的解析扩展是否正常，解析前后多出了什么结构化信息。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="输入记录" :value="fmt(parseStats.inputRecords)" subtitle="原始报文数" />
    <SummaryCard title="输出记录" :value="fmt(parseStats.outputRecords)" subtitle="解析扩展后" />
    <SummaryCard title="扩展比" :value="parseStats.expansionRatio + 'x'" subtitle="每条报文平均产出行数" color="var(--c-primary)" />
  </div>

  <div class="grid grid-2 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md">来源贡献分布</div>
      <table class="data-table">
        <thead><tr><th>解析来源</th><th>输入</th><th>输出</th><th>扩展比</th></tr></thead>
        <tbody>
          <tr v-for="s in parseStats.sources" :key="s.name">
            <td class="font-semibold">{{ s.name }}</td>
            <td class="font-mono">{{ fmt(s.inputCount) }}</td>
            <td class="font-mono">{{ fmt(s.outputCount) }}</td>
            <td class="font-mono">{{ s.ratio }}x</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md">解析前后字段覆盖率变化</div>
      <div class="flex flex-col gap-md">
        <div v-for="c in coverageChange" :key="c.field" class="coverage-row">
          <span class="font-mono text-xs" style="width:80px">{{ c.field }}</span>
          <div style="flex:1">
            <div class="flex gap-sm items-center mb-sm">
              <span class="text-xs text-muted" style="width:20px">前</span>
              <PercentBar :value="c.before" color="var(--c-text-muted)" />
            </div>
            <div class="flex gap-sm items-center">
              <span class="text-xs text-muted" style="width:20px">后</span>
              <PercentBar :value="c.after" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.coverage-row {
  display: flex;
  gap: var(--sp-md);
  align-items: flex-start;
  padding: var(--sp-sm) 0;
  border-bottom: 1px solid var(--c-border-light);
}
.coverage-row:last-child { border-bottom: none; }
</style>
