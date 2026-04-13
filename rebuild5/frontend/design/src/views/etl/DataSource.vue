<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getEtlSource, type EtlSourceItem } from '../../api/etl'
import { fmt } from '../../composables/useFormat'

const sources = ref<EtlSourceItem[]>([])
const sourceCount = ref(0)
const rawRecordCount = ref(0)
const lastSync = ref('-')

onMounted(async () => {
  try {
    const payload = await getEtlSource()
    sources.value = payload.sources
    sourceCount.value = payload.summary.source_count
    rawRecordCount.value = payload.summary.raw_record_count
    lastSync.value = payload.summary.last_sync || '-'
  } catch {
    sources.value = []
  }
})
</script>

<template>
  <PageHeader title="数据源注册" description="查看当前数据集接入的原始数据源、来源范围和接入状态。当前为单活只读模式，暂不支持在线新增 / 编辑 / 停用数据源。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="数据源总数" :value="sourceCount" :subtitle="`当前激活 ${sourceCount} 个`" />
    <SummaryCard title="原始记录总量" :value="fmt(rawRecordCount)" subtitle="来自当前数据集源表" />
    <SummaryCard title="最近同步" :value="lastSync" subtitle="以元数据登记时间为准" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>源 ID</th>
          <th>名称</th>
          <th>类型</th>
          <th>表名</th>
          <th>状态</th>
          <th>记录数</th>
          <th>字段数</th>
          <th>最近同步</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sources" :key="s.id">
          <td class="font-mono text-xs">{{ s.id }}</td>
          <td class="font-semibold">{{ s.name }}</td>
          <td><span class="tag" style="background:#ede9fe;color:#6d28d9">{{ s.type }}</span></td>
          <td class="font-mono text-xs">{{ s.table }}</td>
          <td>
            <span class="tag" :style="s.status === 'active' ? 'background:#dcfce7;color:#166534' : 'background:#f3f4f6;color:#6b7280'">
              {{ s.status === 'active' ? '已激活' : s.status }}
            </span>
          </td>
          <td class="font-mono">{{ fmt(s.records) }}</td>
          <td class="font-mono">{{ s.fields }}</td>
          <td class="text-sm text-secondary">{{ s.lastSync || '-' }}</td>
        </tr>
        <tr v-if="sources.length === 0">
          <td colspan="8" class="text-center text-secondary" style="padding:20px">暂无数据源，请先准备当前数据集</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
