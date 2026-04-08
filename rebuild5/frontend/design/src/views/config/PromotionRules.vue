<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import RuleCard from '../../components/common/RuleCard.vue'
</script>

<template>
  <PageHeader title="晋级规则" description="当前系统用于判定 waiting / observing / qualified / excellent 的阈值定义。只读展示。" />

  <div class="grid grid-2 gap-lg mb-lg">
    <RuleCard title="Cell → qualified 条件" :rules="[
      { label: '独立观测量', value: '≥ 3', unit: '条' },
      { label: '独立设备数', value: '≥ 2', unit: '台' },
      { label: 'P90 半径', value: '< 1500', unit: 'm' },
      { label: '观测跨度', value: '≥ 24', unit: 'h' },
      { label: '碰撞阻断', value: '非 collision', unit: '' },
    ]" />
    <RuleCard title="Cell → excellent 条件（在 qualified 基础上）" :rules="[
      { label: '独立观测量', value: '≥ 8', unit: '条' },
      { label: '独立设备数', value: '≥ 3', unit: '台' },
      { label: 'P90 半径', value: '< 500', unit: 'm' },
    ]" />
    <RuleCard title="Cell 锚点资格 (anchor_eligible)" :rules="[
      { label: 'GPS 有效数', value: '≥ 10', unit: '条' },
      { label: '独立设备数', value: '≥ 2', unit: '台' },
      { label: 'P90 半径', value: '< 1500', unit: 'm' },
      { label: '观测跨度', value: '≥ 24', unit: 'h' },
      { label: '碰撞阻断', value: '非 collision', unit: '' },
    ]" />
    <RuleCard title="Cell → waiting 条件" :rules="[
      { label: '独立观测量', value: '< 3', unit: '条' },
      { label: '或独立设备数', value: '< 2', unit: '台' },
    ]" />
  </div>

  <div class="grid grid-2 gap-lg mb-lg">
    <RuleCard title="BS → qualified 条件（满足任一）" :rules="[
      { label: '下属 excellent Cell', value: '≥ 1', unit: '个' },
      { label: '或 qualified+ Cell', value: '≥ 3', unit: '个' },
    ]" />
    <RuleCard title="LAC → qualified 条件（满足任一）" :rules="[
      { label: 'qualified BS', value: '≥ 3', unit: '个' },
      { label: '或 qualified BS 占比', value: '≥ 10', unit: '%' },
    ]" />
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>以上阈值来自 <code>profile_params.yaml</code>，当前版本为只读展示</li>
      <li>observing 状态由 waiting 和 qualified 反推，不满足 waiting 且不满足 qualified 即为 observing</li>
      <li>BS / LAC 完全由下层上卷，不重新读取原始报文</li>
    </ul>
  </div>
</template>

<style scoped>
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
