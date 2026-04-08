<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'

const rules = [
  { type: '碰撞 (collision)', condition: 'max_spread_m ≥ 2200m 且 ratio < 0.3', effect: 'baseline_eligible = false，阻断基线刷新', link: '/governance/cell' },
  { type: '迁移 (migration)', condition: 'max_spread_m ≥ 2200m 且 ratio ≥ 0.7', effect: 'baseline_eligible = false，等待迁移确认', link: '/governance/cell' },
  { type: '多质心 (multi_centroid)', condition: '空间聚类发现 ≥ 2 个稳定簇', effect: 'baseline_eligible = false，标记多质心', link: '/governance/cell' },
  { type: 'GPS 异常时序', condition: '连续 3+ 批 GPS 偏差 > 阈值', effect: '暂缓基线刷新，进入人工审核', link: '/governance/cell' },
  { type: '面积异常 (BS)', condition: 'max(cell_to_bs_distance_m) > 2500m', effect: 'BS baseline_eligible = false', link: '/governance/bs' },
]
</script>

<template>
  <PageHeader title="防毒化规则" description="以下异常会阻断 baseline_eligible，防止异常数据污染基线刷新。只读展示。" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>异常类型</th>
          <th>触发条件</th>
          <th>阻断效果</th>
          <th>关联页面</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rules" :key="r.type">
          <td class="font-semibold">{{ r.type }}</td>
          <td class="font-mono text-xs">{{ r.condition }}</td>
          <td class="text-sm text-secondary">{{ r.effect }}</td>
          <td><router-link :to="r.link" class="text-xs">查看详情 →</router-link></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">防毒化原则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>防毒化是对 <code>baseline_eligible</code> 的阻断，不是对 <code>anchor_eligible</code> 的阻断</li>
      <li>被阻断的对象仍然可以参与补数（如果 anchor_eligible = true），但不能影响基线刷新</li>
      <li>阻断解除需要异常消失或人工确认</li>
    </ul>
  </div>
</template>

<style scoped>
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
