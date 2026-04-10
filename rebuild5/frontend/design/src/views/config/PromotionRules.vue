<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import RuleCard from '../../components/common/RuleCard.vue'
import { getSystemConfig, type SystemConfigPayload } from '../../api/system'

function toRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

const config = ref<SystemConfigPayload>({
  current_version: { dataset_key: 'sample_6lac', run_id: '', snapshot_version: 'v0', status: 'completed', updated_at: '' },
  datasets: [],
  params: {},
})

const profile = computed(() => toRecord(config.value.params.profile))
const cell = computed(() => toRecord(profile.value.cell))
const bs = computed(() => toRecord(profile.value.bs))
const lac = computed(() => toRecord(profile.value.lac))
const waiting = computed(() => toRecord(cell.value.waiting))
const qualified = computed(() => toRecord(cell.value.qualified))
const excellent = computed(() => toRecord(cell.value.excellent))
const anchorable = computed(() => toRecord(cell.value.anchorable))
const bsQualified = computed(() => toRecord(bs.value.qualified))
const lacQualified = computed(() => toRecord(lac.value.qualified))

function asPercent(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(value || 0)
  return `${(num * 100).toFixed(0)}%`
}

onMounted(async () => {
  try {
    config.value = await getSystemConfig()
  } catch {
    config.value = { ...config.value }
  }
})
</script>

<template>
  <PageHeader title="晋级规则" description="当前系统用于判定 waiting / observing / qualified / excellent 的阈值定义。只读展示。">
    <div class="text-xs text-secondary">
      数据集 {{ config.current_version.dataset_key }} ｜ 当前版本 {{ config.current_version.snapshot_version }} ｜ 最近运行 {{ config.current_version.run_id || '-' }}
    </div>
  </PageHeader>

  <div class="grid grid-2 gap-lg mb-lg">
    <RuleCard title="Cell → qualified 条件" :rules="[
      { label: '独立观测量', value: String(qualified.min_independent_obs ?? 0), unit: '条' },
      { label: '独立设备数', value: String(qualified.min_distinct_devices ?? 0), unit: '台' },
      { label: 'P90 半径', value: '< ' + String(qualified.max_p90_radius_m ?? 0), unit: 'm' },
      { label: '观测跨度', value: '≥ ' + String(qualified.min_observed_span_hours ?? 0), unit: 'h' },
      { label: '碰撞阻断', value: '非 collision', unit: '' },
    ]" />
    <RuleCard title="Cell → excellent 条件（在 qualified 基础上）" :rules="[
      { label: '独立观测量', value: '≥ ' + String(excellent.min_independent_obs ?? 0), unit: '条' },
      { label: '独立设备数', value: '≥ ' + String(excellent.min_distinct_devices ?? 0), unit: '台' },
      { label: 'P90 半径', value: '< ' + String(excellent.max_p90_radius_m ?? 0), unit: 'm' },
      { label: '观测跨度', value: '≥ ' + String(excellent.min_observed_span_hours ?? 0), unit: 'h' },
    ]" />
    <RuleCard title="Cell 锚点资格 (anchor_eligible)" :rules="[
      { label: 'GPS 有效数', value: '≥ ' + String(anchorable.min_gps_valid_count ?? 0), unit: '条' },
      { label: '独立设备数', value: '≥ ' + String(anchorable.min_distinct_devices ?? 0), unit: '台' },
      { label: 'P90 半径', value: '< ' + String(anchorable.max_p90_radius_m ?? 0), unit: 'm' },
      { label: '观测跨度', value: '≥ ' + String(anchorable.min_observed_span_hours ?? 0), unit: 'h' },
      { label: '碰撞阻断', value: '非 collision', unit: '' },
    ]" />
    <RuleCard title="Cell → waiting 条件" :rules="[
      { label: '独立观测量', value: '< ' + String(waiting.min_independent_obs ?? 0), unit: '条' },
      { label: '或独立设备数', value: '< ' + String(waiting.min_distinct_devices ?? 0), unit: '台' },
    ]" />
  </div>

  <div class="grid grid-2 gap-lg mb-lg">
    <RuleCard title="BS → qualified 条件（满足任一）" :rules="[
      { label: '下属 excellent Cell', value: '≥ ' + String(bsQualified.min_excellent_cells ?? 0), unit: '个' },
      { label: '或 qualified+ Cell', value: '≥ ' + String(bsQualified.min_qualified_cells ?? 0), unit: '个' },
    ]" />
    <RuleCard title="LAC → qualified 条件（满足任一）" :rules="[
      { label: 'qualified BS', value: '≥ ' + String(lacQualified.min_qualified_bs ?? 0), unit: '个' },
      { label: '或 qualified BS 占比', value: '≥ ' + asPercent(lacQualified.min_qualified_bs_ratio ?? 0), unit: '' },
    ]" />
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>以上阈值来自 <code>profile_params.yaml</code> 的实时加载结果</li>
      <li>observing 状态由 waiting 和 qualified 反推，不满足 waiting 且不满足 qualified 即为 observing</li>
      <li>BS / LAC 完全由下层上卷，不重新读取原始报文</li>
    </ul>
  </div>
</template>

<style scoped>
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
