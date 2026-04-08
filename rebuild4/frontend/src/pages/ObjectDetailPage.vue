<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getObjectDetail } from '../lib/api'
import LifecycleBadge from '../components/LifecycleBadge.vue'

const props = defineProps<{ objectType: string; objectId: string }>()

const detail = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await getObjectDetail(props.objectId)
    detail.value = res.data
  } catch { /* tolerate */ }
  loading.value = false
})

function fmtM(n: any) {
  if (typeof n !== 'number') return '-'
  return n < 1 ? '< 1m' : Math.round(n) + 'm'
}

const driftLabel: Record<string, string> = {
  stable: '稳定', collision: '碰撞', migration: '搬迁',
  large_coverage: '大覆盖', moderate_drift: '中度漂移', insufficient: '数据不足',
}
const gradeLabel: Record<string, string> = {
  excellent: '优秀', good: '良好', qualified: '合格', unqualified: '不合格',
}
const lifecycleLabel: Record<string, string> = {
  active: '活跃', observing: '观察中', waiting: '等待中',
}
const diffKindLabel: Record<string, string> = {
  added: '新增', removed: '移除', changed: '变化', unchanged: '不变',
}
</script>

<template>
  <div class="detail-page">
    <div v-if="loading" class="center">加载中…</div>
    <template v-else-if="detail">
      <!-- Header -->
      <div class="detail-header">
        <span class="type-label">{{ detail.object_type?.toUpperCase() || props.objectType.toUpperCase() }}</span>
        <h2 class="object-id">{{ detail.object?.cell_id || detail.object?.bs_id || detail.object?.lac || props.objectId }}</h2>
        <div class="badge-row">
          <LifecycleBadge :state="detail.object?.lifecycle_state" />
          <span v-if="detail.object?.anchorable" class="qual-tag anchorable">锚点可用</span>
          <span class="qual-tag grade">{{ gradeLabel[detail.object?.position_grade] || detail.object?.position_grade || '-' }}</span>
        </div>
      </div>

      <!-- Basic Info Grid -->
      <section class="section">
        <h3 class="section-title">画像信息</h3>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">运营商</span>
            <span class="info-value">{{ detail.object?.operator_cn || detail.object?.operator_code || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">LAC</span>
            <span class="info-value">{{ detail.object?.lac || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">BS</span>
            <span class="info-value">{{ detail.object?.bs_id || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">技术制式</span>
            <span class="info-value">{{ detail.object?.tech_norm || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">记录数</span>
            <span class="info-value">{{ detail.object?.record_count?.toLocaleString() || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">独立观测</span>
            <span class="info-value">{{ detail.object?.independent_obs?.toLocaleString() || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">独立天数</span>
            <span class="info-value">{{ detail.object?.independent_days || detail.object?.active_days || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">设备数</span>
            <span class="info-value">{{ detail.object?.distinct_dev_id || detail.object?.total_devices || '-' }}</span>
          </div>
        </div>
      </section>

      <!-- Spatial -->
      <section v-if="detail.object?.center_lon" class="section">
        <h3 class="section-title">空间画像</h3>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">质心</span>
            <span class="info-value">{{ Number(detail.object.center_lon).toFixed(4) }}, {{ Number(detail.object.center_lat).toFixed(4) }}</span>
          </div>
          <div class="info-item" v-if="detail.object.p50_radius_m != null">
            <span class="info-label">P50 半径</span>
            <span class="info-value">{{ fmtM(detail.object.p50_radius_m) }}</span>
          </div>
          <div class="info-item" v-if="detail.object.p90_radius_m != null">
            <span class="info-label">P90 半径</span>
            <span class="info-value">{{ fmtM(detail.object.p90_radius_m) }}</span>
          </div>
          <div class="info-item" v-if="detail.object.drift_pattern">
            <span class="info-label">漂移模式</span>
            <span class="info-value">{{ driftLabel[detail.object.drift_pattern] || detail.object.drift_pattern }}</span>
          </div>
          <div class="info-item" v-if="detail.object.drift_max_spread_m != null">
            <span class="info-label">漂移最大展幅</span>
            <span class="info-value">{{ fmtM(detail.object.drift_max_spread_m) }}</span>
          </div>
        </div>
      </section>

      <!-- Latest Diff -->
      <section v-if="detail.latest_diff" class="section">
        <h3 class="section-title">最近一次 Snapshot Diff</h3>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">变化类型</span>
            <span class="info-value">{{ diffKindLabel[detail.latest_diff.diff_kind] || detail.latest_diff.diff_kind }}</span>
          </div>
          <div class="info-item" v-if="detail.latest_diff.from_lifecycle_state">
            <span class="info-label">生命周期变化</span>
            <span class="info-value">{{ lifecycleLabel[detail.latest_diff.from_lifecycle_state] || detail.latest_diff.from_lifecycle_state }} → {{ lifecycleLabel[detail.latest_diff.to_lifecycle_state] || detail.latest_diff.to_lifecycle_state }}</span>
          </div>
          <div class="info-item" v-if="detail.latest_diff.centroid_shift_m != null">
            <span class="info-label">质心位移</span>
            <span class="info-value">{{ fmtM(detail.latest_diff.centroid_shift_m) }}</span>
          </div>
          <div class="info-item" v-if="detail.latest_diff.p90_delta_m != null">
            <span class="info-label">P90 变化</span>
            <span class="info-value">{{ fmtM(detail.latest_diff.p90_delta_m) }}</span>
          </div>
        </div>
      </section>

      <!-- Frozen notice -->
      <section v-if="detail.state_history_note" class="section frozen-section">
        <p class="frozen-text">{{ detail.state_history_note }}</p>
      </section>
    </template>
    <div v-else class="center">未找到该对象</div>
  </div>
</template>

<style scoped>
.detail-page { padding: 24px; max-width: 960px; margin: 0 auto; }
.center { text-align: center; color: var(--gray-400); padding: 48px; }

.detail-header { margin-bottom: 24px; }
.type-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--gray-400); letter-spacing: 0.5px; }
.object-id { font-size: 22px; font-weight: 700; margin: 4px 0 8px; font-family: var(--font-mono, monospace); }
.badge-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.qual-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 500; background: var(--gray-100); color: var(--gray-600); }
.qual-tag.anchorable { background: #dcfce7; color: #16a34a; }

.section { margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--gray-700); }

.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px 16px; }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-label { font-size: 11px; color: var(--gray-400); }
.info-value { font-size: 13px; font-weight: 500; }

.frozen-section { border: 1px dashed var(--gray-300); border-radius: var(--radius-sm); padding: 16px; background: var(--gray-50); }
.frozen-text { font-size: 13px; color: var(--gray-400); margin: 0; font-style: italic; }
</style>
