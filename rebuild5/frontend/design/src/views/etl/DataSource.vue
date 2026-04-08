<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { fmt } from '../../composables/useFormat'

const sources = [
  { id: 'src_01', name: 'ODS 采集主表', type: 'MaxCompute', table: 'ods_cell_scan', status: 'active', records: 824600, lastSync: '2026-04-08 06:00', fields: 55 },
  { id: 'src_02', name: 'GPS 补充源', type: 'MaxCompute', table: 'ods_gps_track', status: 'active', records: 312450, lastSync: '2026-04-08 06:00', fields: 18 },
  { id: 'src_03', name: '历史对照源', type: 'PostgreSQL', table: 'legacy_cell_ref', status: 'standby', records: 111300, lastSync: '2026-04-01 00:00', fields: 32 },
]
</script>

<template>
  <PageHeader title="数据源注册" description="查看当前数据集接入的原始数据源、来源范围和接入状态。" />

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="数据源总数" :value="sources.length" subtitle="已激活 2 / 待命 1" />
    <SummaryCard title="原始记录总量" :value="fmt(1248350)" subtitle="来自 3 个源表" />
    <SummaryCard title="最近同步" value="2026-04-08 06:00" subtitle="距今 12 小时" />
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
              {{ s.status === 'active' ? '已激活' : '待命' }}
            </span>
          </td>
          <td class="font-mono">{{ fmt(s.records) }}</td>
          <td class="font-mono">{{ s.fields }}</td>
          <td class="text-sm text-secondary">{{ s.lastSync }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
