<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getMaintenanceStats, type MaintenanceStatsPayload } from '../../api/maintenance'
import { getSystemConfig, type SystemConfigPayload } from '../../api/system'
import { fmt } from '../../composables/useFormat'

function toRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

const config = ref<SystemConfigPayload>({
  current_version: { dataset_key: '', run_id: '', snapshot_version: 'v0', status: 'completed', updated_at: '' },
  dataset_mode: { key: 'single_active', label: '单活数据集', switch_supported: false, message: '', plan_doc: '' },
  datasets: [],
  params: {},
})
const maintenance = ref<MaintenanceStatsPayload>({
  version: { run_id: '', dataset_key: '', snapshot_version: 'v0', snapshot_version_prev: 'v0' },
  summary: {
    published_cell_count: 0,
    published_bs_count: 0,
    published_lac_count: 0,
    collision_cell_count: 0,
    multi_centroid_cell_count: 0,
    dynamic_cell_count: 0,
    anomaly_bs_count: 0,
  },
  drift_distribution: {},
})

const antitoxin = computed(() => toRecord(config.value.params.antitoxin))
const collision = computed(() => toRecord(antitoxin.value.collision))
const migration = computed(() => toRecord(antitoxin.value.migration))
const bs = computed(() => toRecord(antitoxin.value.bs))

const rules = computed(() => [
  { type: '碰撞', condition: `max_spread_m ≥ ${collision.value.min_spread_m ?? 0}m`, effect: '阻断基线资格，阻断基线刷新', link: '/governance/cell' },
  { type: '迁移', condition: `max_spread_m ≥ ${migration.value.min_spread_m ?? 0}m`, effect: '阻断基线资格，等待迁移确认', link: '/governance/cell' },
  { type: '面积异常 (BS)', condition: `gps_p90_dist_m > ${bs.value.max_cell_to_bs_distance_m ?? 0}m`, effect: 'BS 阻断基线资格', link: '/governance/bs' },
  { type: '多质心', condition: '空间聚类发现 ≥ 2 个稳定簇', effect: '阻断基线资格，标记多质心', link: '/governance/cell' },
  { type: 'GPS 异常时序', condition: '补数阶段连续命中异常轨迹', effect: '进入人工审核，不参与基线刷新', link: '/governance/cell' },
])

onMounted(async () => {
  try {
    const [configPayload, maintenancePayload] = await Promise.all([
      getSystemConfig(),
      getMaintenanceStats(),
    ])
    config.value = configPayload
    maintenance.value = maintenancePayload
  } catch {
    config.value = { ...config.value }
  }
})
</script>

<template>
  <PageHeader title="防毒化规则" description="以下异常会阻断基线资格，防止异常数据污染基线刷新。只读展示。">
    <div class="text-xs text-secondary">
      当前版本 {{ config.current_version.snapshot_version }} ｜ 最近维护 {{ maintenance.version.run_id || '-' }}
    </div>
  </PageHeader>

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="碰撞 Cell" :value="fmt(maintenance.summary.collision_cell_count)" color="var(--c-danger)" />
    <SummaryCard title="多质心 Cell" :value="fmt(maintenance.summary.multi_centroid_cell_count)" color="var(--c-warning)" />
    <SummaryCard title="异常 BS" :value="fmt(maintenance.summary.anomaly_bs_count)" color="var(--c-retired)" />
  </div>

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
        <tr v-for="rule in rules" :key="rule.type">
          <td class="font-semibold">{{ rule.type }}</td>
          <td class="font-mono text-xs">{{ rule.condition }}</td>
          <td class="text-sm text-secondary">{{ rule.effect }}</td>
          <td><router-link :to="rule.link" class="text-xs">查看详情 →</router-link></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">防毒化原则</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>防毒化是对基线资格的阻断，不是对锚点资格的阻断</li>
      <li>被阻断的对象仍可以作为展示结果被查询，但不会影响正式库刷新</li>
      <li>碰撞、迁移与 BS 面积阈值已外化到 <code>antitoxin_params.yaml</code>；多质心与异常时序仍是固定逻辑</li>
    </ul>
  </div>
</template>

<style scoped>
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
