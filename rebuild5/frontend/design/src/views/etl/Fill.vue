<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { pct } from '../../composables/useFormat'

const fillFields = [
  { field: 'lon / lat', before: 0.68, after: 0.74, source: 'same_cell / ss1_own', note: '同报文内 GPS 互补' },
  { field: 'operator_code', before: 0.92, after: 0.96, source: 'same_cell', note: '同 cell_id 内运营商一致' },
  { field: 'rsrp', before: 0.73, after: 0.78, source: 'same_cell', note: '同报文内信号互补' },
  { field: 'tech_norm', before: 0.88, after: 0.93, source: 'same_cell', note: '同 cell_id 内制式一致' },
]
</script>

<template>
  <PageHeader title="补齐" description="Step 1 同报文内字段对齐效果。这不是历史知识补数，仅限同一 record_id 内的结构性互补。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="补齐记录" value="3,156,210" subtitle="与清洗输出一致" />
    <SummaryCard title="GPS 补齐提升" :value="pct(0.06)" subtitle="68% → 74%" color="var(--c-primary)" />
    <SummaryCard title="时间约束" value="≤ 1 分钟" subtitle="同报文内事件时间差阈值" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">补齐前后覆盖率对比</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>字段</th>
          <th style="width:180px">补齐前</th>
          <th style="width:180px">补齐后</th>
          <th>来源</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in fillFields" :key="f.field">
          <td class="font-mono font-semibold">{{ f.field }}</td>
          <td><PercentBar :value="f.before" color="var(--c-text-muted)" /></td>
          <td><PercentBar :value="f.after" /></td>
          <td class="font-mono text-xs">{{ f.source }}</td>
          <td class="text-sm text-secondary">{{ f.note }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-2 gap-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-sm">来源分布</div>
      <div class="flex flex-col gap-sm">
        <div class="flex justify-between text-sm">
          <span>raw_gps（原始 GPS）</span>
          <span class="font-mono">68.0%</span>
        </div>
        <div class="flex justify-between text-sm">
          <span>ss1_own（同报文 SS1）</span>
          <span class="font-mono">3.2%</span>
        </div>
        <div class="flex justify-between text-sm">
          <span>same_cell（同 cell_id 互补）</span>
          <span class="font-mono">2.8%</span>
        </div>
        <div class="flex justify-between text-sm">
          <span>none（仍缺失）</span>
          <span class="font-mono text-muted">26.0%</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-sm">边界说明</div>
      <ul class="note-list">
        <li>同报文定义：<code>record_id</code> 相同的多行记录</li>
        <li>时间约束：<code>event_time_std</code> 差值 ≤ 1 分钟</li>
        <li>不覆盖已有值：仅对仍为空的 <code>*_filled</code> 列补齐</li>
        <li>这不是 Step 4 知识补数，不读取可信库</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.note-list { padding-left: 18px; font-size: 12px; color: var(--c-text-secondary); line-height: 2; }
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
