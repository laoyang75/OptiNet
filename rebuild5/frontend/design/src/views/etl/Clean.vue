<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { mockCleanRules } from '../../mock/data'
import { fmt, pct } from '../../composables/useFormat'
</script>

<template>
  <PageHeader title="清洗" description="ODS 清洗规则命中情况。查看哪些数据被删除及原因。" />

  <div class="grid grid-4 mb-lg">
    <SummaryCard title="输入记录" :value="fmt(3_872_640)" />
    <SummaryCard title="通过记录" :value="fmt(3_156_210)" color="var(--c-success)" />
    <SummaryCard title="删除记录" :value="fmt(27_060)" color="var(--c-danger)" />
    <SummaryCard title="整体通过率" :value="pct(0.815)" subtitle="置空不计入删除" />
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
        <tr v-for="r in mockCleanRules" :key="r.rule_id">
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
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">规则说明</div>
    <ul class="rule-explain">
      <li><strong>删除型规则</strong>：主键级错误（cell_id 为 0、溢出）和结构性错误（时间戳异常），整行删除。</li>
      <li><strong>置空型规则</strong>：字段值越界（经纬度、RSRP、运营商），置空对应字段，保留记录。不直接删行。</li>
      <li><strong>非原生 GPS</strong>：WiFi / 基站定位数据标记为非有效 GPS，不参与空间计算，但保留记录。</li>
    </ul>
  </div>
</template>

<style scoped>
.rule-explain { padding-left: 20px; font-size: 12px; color: var(--c-text-secondary); line-height: 1.8; }
.rule-explain li { margin-bottom: 4px; }
</style>
