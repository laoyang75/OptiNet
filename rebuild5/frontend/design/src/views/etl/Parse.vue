<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import PercentBar from '../../components/common/PercentBar.vue'
import { getEtlStats, type ParseSourceItem } from '../../api/etl'
import { fmt, pct } from '../../composables/useFormat'

const inputRecords = ref(0)
const outputRecords = ref(0)
const expansionRatio = ref(0)
const sources = ref<ParseSourceItem[]>([])
const coverageChange = ref<Array<{ field: string; before: number; after: number }>>([])

onMounted(async () => {
  try {
    const payload = await getEtlStats()
    inputRecords.value = payload.parse.inputRecords
    outputRecords.value = payload.parse.outputRecords
    expansionRatio.value = payload.parse.expansionRatio
    sources.value = payload.parse.sources
    coverageChange.value = (payload.parse as any).coverageChange ?? []
  } catch {
    sources.value = []
  }
})
</script>

<template>
  <PageHeader title="解析" description="判断 cell_infos 和 ss1 的解析扩展是否正常，解析前后多出了什么结构化信息。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="输入记录" :value="fmt(inputRecords)" subtitle="原始报文数" />
    <SummaryCard title="输出记录" :value="fmt(outputRecords)" subtitle="解析扩展后" />
    <SummaryCard title="扩展比" :value="expansionRatio + 'x'" subtitle="每条报文平均产出行数" color="var(--c-primary)" />
  </div>

  <div class="grid grid-2 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md">来源贡献分布</div>
      <table class="data-table">
        <thead><tr><th>解析来源</th><th>输入</th><th>输出</th><th>扩展比</th></tr></thead>
        <tbody>
          <tr v-for="s in sources" :key="s.name">
            <td class="font-semibold">{{ s.name }}</td>
            <td class="font-mono">{{ fmt(s.inputCount) }}</td>
            <td class="font-mono">{{ fmt(s.outputCount) }}</td>
            <td class="font-mono">{{ s.ratio }}x</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md">解析前后字段覆盖率</div>
      <table class="data-table">
        <thead><tr><th>字段</th><th style="width:140px">解析前</th><th style="width:140px">解析后</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="c in coverageChange" :key="c.field">
            <td class="font-mono font-semibold">{{ c.field }}</td>
            <td><PercentBar :value="c.before" color="var(--c-text-muted)" /></td>
            <td><PercentBar :value="c.after" /></td>
            <td class="text-xs text-secondary">
              <template v-if="c.before === 0 && c.after > 0">解析新增</template>
              <template v-else-if="c.after > c.before">+{{ pct(c.after - c.before) }}</template>
              <template v-else>原始字段</template>
            </td>
          </tr>
        </tbody>
      </table>
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
