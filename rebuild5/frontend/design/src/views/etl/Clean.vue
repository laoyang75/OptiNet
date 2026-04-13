<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getCleanRules, getEtlStats, type CleanRuleItem } from '../../api/etl'
import { fmt, pct } from '../../composables/useFormat'

const summary = ref({ inputRecords: 0, passedRecords: 0, deletedRecords: 0, passRate: 0 })
const rules = ref<CleanRuleItem[]>([])

onMounted(async () => {
  try {
    const [statsPayload, cleanPayload] = await Promise.all([getEtlStats(), getCleanRules()])
    summary.value = cleanPayload.summary
    rules.value = cleanPayload.rules
    if (!cleanPayload.summary.inputRecords) {
      summary.value = {
        inputRecords: statsPayload.clean.inputRecords,
        passedRecords: statsPayload.clean.passedRecords,
        deletedRecords: statsPayload.clean.deletedRecords,
        passRate: statsPayload.clean.passRate,
      }
    }
  } catch {
    rules.value = []
  }
})
</script>

<template>
  <PageHeader title="清洗" description="ODS 清洗 19 条规则命中情况。查看哪些数据被删除及原因。最终删行条件为 cell_id IS NULL 或 event_time_std IS NULL。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="输入记录" :value="fmt(summary.inputRecords)" />
    <SummaryCard title="通过记录" :value="fmt(summary.passedRecords)" color="var(--c-success)" />
    <SummaryCard title="删除记录" :value="fmt(summary.deletedRecords)" color="var(--c-danger)" />
    <SummaryCard title="整体通过率" :value="pct(summary.passRate)" subtitle="置空不计入删除" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>规则 ID</th>
          <th>规则名称</th>
          <th>说明</th>
          <th>命中数</th>
          <th>删除数</th>
          <th>动作</th>
          <th>通过率</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rules" :key="r.rule_id">
          <td class="font-mono font-semibold">{{ r.rule_id }}</td>
          <td class="font-semibold">{{ r.rule_name }}</td>
          <td class="text-secondary text-sm">{{ r.description }}</td>
          <td class="font-mono">{{ fmt(r.hit_count) }}</td>
          <td class="font-mono" :style="r.drop_count > 0 ? 'color:var(--c-danger)' : ''">{{ fmt(r.drop_count) }}</td>
          <td>
            <span class="tag" :style="r.drop_count > 0 ? 'background:#fee2e2;color:#991b1b' : 'background:#fef9c3;color:#854d0e'">
              {{ r.drop_count > 0 ? '删除' : '置空' }}
            </span>
          </td>
          <td class="font-mono">{{ pct(r.pass_rate) }}</td>
        </tr>
        <tr v-if="rules.length === 0">
          <td colspan="7" class="text-center text-secondary" style="padding:20px">暂无清洗结果，请先运行 Step 1</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">规则说明</div>
    <ul class="rule-explain">
      <li><strong>删除型规则</strong>：主键级错误（CellID=0 / 溢出值）和无可用事件时间的记录会在最终清洗结果中被删除。</li>
      <li><strong>置空型规则</strong>：字段值越界（经纬度、RSRP、运营商），置空对应字段，保留记录。</li>
      <li><strong>非原生 GPS</strong>：WiFi / 基站定位数据标记为非有效 GPS，不参与空间计算，但保留记录。</li>
      <li><strong>WiFi 清洗</strong>：占位符 WiFi 名称（unknown）和全零/随机化 MAC 地址置空，避免污染补齐链路。</li>
      <li><strong>经纬度越界</strong>：合理范围为全国（经度 73~135，纬度 3~54），非中国境内坐标标记为无效 GPS。</li>
    </ul>
  </div>
</template>

<style scoped>
.rule-explain { padding-left: 20px; font-size: 12px; color: var(--c-text-secondary); line-height: 1.8; }
.rule-explain li { margin-bottom: 4px; }
</style>
