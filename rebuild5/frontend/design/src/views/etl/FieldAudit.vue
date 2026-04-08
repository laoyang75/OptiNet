<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import PercentBar from '../../components/common/PercentBar.vue'

const fields = [
  { name: 'cell_id', type: 'bigint', decision: 'keep', coverage: 1.0, sample: '12345678' },
  { name: 'lac', type: 'int', decision: 'keep', coverage: 0.98, sample: '4001' },
  { name: 'bs_id', type: 'int', decision: 'parse', coverage: 0.95, sample: '50123' },
  { name: 'operator_code', type: 'varchar', decision: 'keep', coverage: 0.92, sample: '46000' },
  { name: 'tech_norm', type: 'varchar', decision: 'parse', coverage: 0.88, sample: '4G' },
  { name: 'rsrp', type: 'float', decision: 'keep', coverage: 0.73, sample: '-95.5' },
  { name: 'lon_raw', type: 'float', decision: 'keep', coverage: 0.68, sample: '116.4312' },
  { name: 'lat_raw', type: 'float', decision: 'keep', coverage: 0.68, sample: '39.9156' },
  { name: 'rsrq', type: 'float', decision: 'keep', coverage: 0.41, sample: '-12.3' },
  { name: 'sinr', type: 'float', decision: 'keep', coverage: 0.39, sample: '8.2' },
  { name: 'pressure', type: 'float', decision: 'keep', coverage: 0.12, sample: '1013.25' },
  { name: 'wifi_mac', type: 'varchar', decision: 'drop', coverage: 0.05, sample: 'AA:BB:CC...' },
]

const decisionStyle: Record<string, string> = {
  keep: 'background:#dcfce7;color:#166534',
  parse: 'background:#dbeafe;color:#1e40af',
  drop: 'background:#fee2e2;color:#991b1b',
}
const decisionLabel: Record<string, string> = { keep: '保留', parse: '解析', drop: '丢弃' }
</script>

<template>
  <PageHeader title="字段审计" description="判断原始字段哪些被保留、解析或丢弃。快速定位覆盖率低或被丢弃的字段。" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>字段名</th>
          <th>类型</th>
          <th>决策</th>
          <th style="width:220px">覆盖率</th>
          <th>样本值</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in fields" :key="f.name">
          <td class="font-mono font-semibold">{{ f.name }}</td>
          <td class="font-mono text-xs text-secondary">{{ f.type }}</td>
          <td><span class="tag" :style="decisionStyle[f.decision]">{{ decisionLabel[f.decision] }}</span></td>
          <td><PercentBar :value="f.coverage" /></td>
          <td class="font-mono text-xs text-muted">{{ f.sample }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
