<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { getEtlCoverage, getEtlStats } from '../../api/etl'
import { fmt, pct } from '../../composables/useFormat'

interface FillField {
  field: string
  before: number
  after: number
  before_count: number
  filled_count: number
  source: string
  note: string
}

interface SourceDist {
  count: number
  rate: number
}

const totalRecords = ref(0)
const coverageFields = ref<FillField[]>([])
const sourceDistribution = ref<Record<string, SourceDist>>({})
const timeWindowSeconds = ref(60)

const gpsImprove = computed(() => {
  const gpsRow = coverageFields.value.find((item) => item.field.startsWith('GPS'))
  return gpsRow ? Math.max(gpsRow.after - gpsRow.before, 0) : 0
})

onMounted(async () => {
  try {
    const [statsPayload, coveragePayload] = await Promise.all([getEtlStats(), getEtlCoverage()])
    totalRecords.value = coveragePayload.total_records ?? statsPayload.summary.filled_record_count
    coverageFields.value = coveragePayload.fields as any
    sourceDistribution.value = coveragePayload.source_distribution as any
    timeWindowSeconds.value = coveragePayload.time_window_seconds
  } catch {
    coverageFields.value = []
  }
})
</script>

<template>
  <PageHeader title="补齐" description="Step 1 同报文内字段对齐效果。这不是历史知识补数，仅限同一 record_id 内的结构性互补。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="补齐记录" :value="fmt(totalRecords)" subtitle="与清洗输出一致" />
    <SummaryCard title="GPS 补齐提升" :value="pct(gpsImprove)" subtitle="补齐前后覆盖率差值" color="var(--c-primary)" />
    <SummaryCard title="时间约束" :value="`≤ ${timeWindowSeconds} 秒`" subtitle="同报文内事件时间差阈值" />
  </div>

  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">补齐前后覆盖率对比</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>字段</th>
          <th>补齐前</th>
          <th>补齐后</th>
          <th>补齐数</th>
          <th>来源</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in coverageFields" :key="f.field">
          <td class="font-mono font-semibold">{{ f.field }}</td>
          <td>
            <div class="flex items-center gap-sm">
              <PercentBar :value="f.before" color="var(--c-text-muted)" style="width:100px" />
              <span class="font-mono text-xs">{{ fmt(f.before_count) }}</span>
            </div>
          </td>
          <td>
            <div class="flex items-center gap-sm">
              <PercentBar :value="f.after" style="width:100px" />
              <span class="font-mono text-xs">{{ pct(f.after) }}</span>
            </div>
          </td>
          <td class="font-mono" :style="f.filled_count > 0 ? 'color:var(--c-success);font-weight:600' : ''">
            {{ f.filled_count > 0 ? '+' + fmt(f.filled_count) : '-' }}
          </td>
          <td class="font-mono text-xs">{{ f.source }}</td>
          <td class="text-sm text-secondary">{{ f.note }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="grid grid-2 gap-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-sm">GPS 来源分布</div>
      <div class="flex flex-col gap-sm">
        <div v-for="(item, key) in sourceDistribution" :key="key" class="flex justify-between text-sm">
          <span>{{ { raw_gps: 'raw_gps（原始 GPS）', ss1_own: 'ss1_own（同报文 SS1）', same_cell: 'same_cell（同 cell_id 互补）', none: 'none（仍缺失）' }[key] || key }}</span>
          <span class="font-mono">
            {{ fmt(item.count) }}
            <span class="text-muted text-xs">（{{ pct(item.rate) }}）</span>
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-sm">边界说明</div>
      <ul class="note-list">
        <li>同报文定义：<code>record_id</code> 相同的多行记录</li>
        <li>GPS / RSRP / WiFi：事件时间差值 ≤ {{ timeWindowSeconds }} 秒</li>
        <li>运营商 / LAC：总是可补，不受时间约束</li>
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
