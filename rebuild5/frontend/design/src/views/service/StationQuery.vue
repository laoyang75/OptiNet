<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '../../components/common/PageHeader.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import type { LifecycleState } from '../../types'

const searchQuery = ref('')

const results: Array<{
  cell_id: string; lac: string; bs_id: string; op: string; op_cn: string; tech: string
  state: LifecycleState; grade: string; lon: number; lat: number; p90: number; anchor: boolean
}> = [
  { cell_id: '10023', lac: '4001', bs_id: '5008', op: '46000', op_cn: '中国移动', tech: '4G', state: 'excellent', grade: 'excellent', lon: 116.4312, lat: 39.9156, p90: 320, anchor: true },
  { cell_id: '10045', lac: '4002', bs_id: '5015', op: '46001', op_cn: '中国联通', tech: '4G', state: 'qualified', grade: 'good', lon: 116.3891, lat: 39.9423, p90: 680, anchor: true },
  { cell_id: '10078', lac: '4001', bs_id: '5008', op: '46000', op_cn: '中国移动', tech: '5G', state: 'qualified', grade: 'qualified', lon: 116.4315, lat: 39.9160, p90: 1200, anchor: false },
]
</script>

<template>
  <PageHeader title="基站查询" description="查询小区或基站的位置、质量和标签。面向业务用户的简洁查询入口。" />

  <!-- 搜索框 -->
  <div class="card mb-lg flex gap-md items-center">
    <input v-model="searchQuery" class="search-input" placeholder="输入 cell_id、bs_id、LAC 或运营商..." />
    <button class="btn btn-primary">查询</button>
  </div>

  <!-- 结果列表 -->
  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>cell_id</th>
          <th>LAC</th>
          <th>bs_id</th>
          <th>运营商</th>
          <th>制式</th>
          <th>状态</th>
          <th>位置质量</th>
          <th>经度</th>
          <th>纬度</th>
          <th>P90 (m)</th>
          <th>可信锚点</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in results" :key="r.cell_id">
          <td class="font-mono font-semibold">{{ r.cell_id }}</td>
          <td class="font-mono">{{ r.lac }}</td>
          <td class="font-mono text-xs">{{ r.bs_id }}</td>
          <td>{{ r.op_cn }}</td>
          <td><span class="tag" :style="r.tech === '5G' ? 'background:#ede9fe;color:#6d28d9' : 'background:#e0f2fe;color:#075985'">{{ r.tech }}</span></td>
          <td><StatusTag :state="r.state" size="sm" /></td>
          <td class="font-semibold">{{ r.grade }}</td>
          <td class="font-mono text-xs">{{ r.lon.toFixed(4) }}</td>
          <td class="font-mono text-xs">{{ r.lat.toFixed(4) }}</td>
          <td class="font-mono">{{ r.p90 }}</td>
          <td>
            <span v-if="r.anchor" style="color:var(--c-success)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 地图预留区 -->
  <div class="card mt-lg" style="height:200px;display:flex;align-items:center;justify-content:center;background:var(--c-bg)">
    <span class="text-muted text-sm">地图区域（预留，后续接入地图组件）</span>
  </div>
</template>

<style scoped>
.search-input {
  flex: 1;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  outline: none;
}
.search-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 2px rgba(59,130,246,0.1); }
</style>
