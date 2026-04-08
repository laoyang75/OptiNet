<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { mockFillStats } from '../../mock/data'
import { fmt, pct } from '../../composables/useFormat'

const s = mockFillStats
const gpsFillRate = s.gps_filled / s.total_path_a
const anomalyRate = s.gps_anomaly_count / s.total_path_a

const fieldFills = [
  { field: 'GPS (lon/lat)', filled: s.gps_filled, rate: gpsFillRate, source: 'trusted_cell 质心' },
  { field: 'RSRP', filled: s.signal_filled, rate: s.signal_filled / s.total_path_a, source: 'trusted_cell rsrp_avg' },
  { field: '运营商', filled: s.operator_filled, rate: s.operator_filled / s.total_path_a, source: 'trusted_cell operator_code' },
]
</script>

<template>
  <PageHeader title="知识补数" description="Step 4 基于上一轮正式库的知识补数效果。仅处理 Path A 命中记录。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="Path A 总量" :value="fmt(s.total_path_a)" subtitle="命中正式库的记录" />
    <SummaryCard title="GPS 补数" :value="fmt(s.gps_filled)" :subtitle="pct(gpsFillRate) + ' 补齐率'" color="var(--c-primary)" />
    <SummaryCard title="GPS 异常" :value="fmt(s.gps_anomaly_count)" :subtitle="pct(anomalyRate)" color="var(--c-danger)" />
    <SummaryCard title="donor 分布" :value="fmt(s.donor_excellent_count + s.donor_qualified_count)" subtitle="可用 donor Cell" />
  </div>

  <!-- 字段级补数 -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">字段级补数统计</div>
    <table class="data-table">
      <thead><tr><th>字段</th><th>补数量</th><th style="width:200px">补数率</th><th>来源</th></tr></thead>
      <tbody>
        <tr v-for="f in fieldFills" :key="f.field">
          <td class="font-mono font-semibold">{{ f.field }}</td>
          <td class="font-mono">{{ fmt(f.filled) }}</td>
          <td><PercentBar :value="f.rate" /></td>
          <td class="text-xs text-secondary font-mono">{{ f.source }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-2 gap-lg">
    <!-- donor 质量分布 -->
    <div class="card">
      <div class="font-semibold text-sm mb-md">donor 质量分布</div>
      <div class="flex flex-col gap-sm">
        <div class="flex justify-between items-center">
          <span class="text-sm">excellent donor</span>
          <span class="font-mono font-semibold" style="color:var(--c-excellent)">{{ fmt(s.donor_excellent_count) }}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-sm">qualified donor</span>
          <span class="font-mono font-semibold" style="color:var(--c-qualified)">{{ fmt(s.donor_qualified_count) }}</span>
        </div>
      </div>
    </div>

    <!-- GPS 异常样本 -->
    <div class="card">
      <div class="font-semibold text-sm mb-md">GPS 异常初筛</div>
      <p class="text-xs text-secondary mb-md">
        自带 GPS 的记录与可信质心距离超出阈值，标记为疑似异常。最终判定由 Step 5 完成。
      </p>
      <div class="flex flex-col gap-sm">
        <div class="flex justify-between items-center">
          <span class="text-sm">异常记录数</span>
          <span class="font-mono font-semibold" style="color:var(--c-danger)">{{ fmt(s.gps_anomaly_count) }}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-sm">异常率</span>
          <span class="font-mono">{{ pct(anomalyRate) }}</span>
        </div>
      </div>
      <router-link to="/governance/cell" class="btn mt-md" style="font-size:12px">查看 Cell 维护 →</router-link>
    </div>
  </div>
</template>
