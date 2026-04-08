<template>
  <section class="page-stack" v-if="profile">
    <nav class="breadcrumbs">
      <RouterLink :to="{ name: 'cell-objects' }">对象浏览</RouterLink>
      <span>/</span>
      <RouterLink :to="{ name: 'cell-detail', params: { objectId } }">对象详情</RouterLink>
      <span>/</span>
      <span>Cell 画像</span>
    </nav>

    <header class="page-hero panel-surface panel-surface--hero profile-hero">
      <div>
        <p class="kicker">11 Cell Profile</p>
        <h2>{{ profile.snapshot.operator_name }} · {{ profile.snapshot.cell_id }}</h2>
        <p class="hero-blurb">
          Cell 画像页聚焦小区层的空间质量、来源构成、事实分流和规则口径，让“为什么这条进 / 不进 baseline”在这里直接可核查。
        </p>
      </div>
      <div class="profile-hero__aside">
        <BadgePill :tone="profile.status === 'ok' ? 'green' : 'blue'" :label="profile.status === 'ok' ? '实时数据' : '快照数据'" />
        <div class="badge-stack">
          <BadgePill :tone="lifecycleTone(profile.snapshot.lifecycle_state)" :label="lifecycleLabel(profile.snapshot.lifecycle_state)" />
          <BadgePill :tone="healthTone(profile.snapshot.health_state)" :label="healthLabel(profile.snapshot.health_state)" />
        </div>
      </div>
    </header>

    <div class="profile-summary-grid">
      <article class="metric-card metric-card--hero">
        <p class="metric-card__label">中心偏移</p>
        <strong class="metric-card__value">{{ formatMeters(profile.snapshot.center_shift_m, 2) }}</strong>
        <p class="metric-card__detail">当前批次质心与基线中心的距离。</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">GPS P90</p>
        <strong class="metric-card__value">{{ formatMeters(profile.snapshot.gps_p90_dist_m, 2) }}</strong>
        <p class="metric-card__detail">对象自身稳定性门槛，而不是 legacy Cell-BS 硬距离。</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">legacy 参考</p>
        <strong class="metric-card__value">{{ profile.snapshot.legacy_gps_anomaly ? '命中' : '未命中' }}</strong>
        <p class="metric-card__detail">{{ profile.snapshot.legacy_gps_anomaly_reason ?? '未命中 legacy gps_anomaly' }}</p>
      </article>
      <article class="metric-card">
        <p class="metric-card__label">compare</p>
        <strong class="metric-card__value">{{ compareLabel(profile.compare_context.membership) }}</strong>
        <p class="metric-card__detail">基线资格在 rebuild2 / rebuild3 之间的归属关系。</p>
      </article>
    </div>

    <div class="detail-grid">
      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Spatial Precision</p>
            <h3>GPS 中心点 + 空间精度</h3>
          </div>
        </header>
        <div class="kv-grid">
          <div class="kv-item"><span>当前质心经度</span><strong>{{ formatCoordinate(profile.snapshot.centroid_lon) }}</strong></div>
          <div class="kv-item"><span>当前质心纬度</span><strong>{{ formatCoordinate(profile.snapshot.centroid_lat) }}</strong></div>
          <div class="kv-item"><span>基线经度</span><strong>{{ formatCoordinate(profile.snapshot.baseline_center_lon) }}</strong></div>
          <div class="kv-item"><span>基线纬度</span><strong>{{ formatCoordinate(profile.snapshot.baseline_center_lat) }}</strong></div>
          <div class="kv-item"><span>P50</span><strong>{{ formatMeters(profile.snapshot.gps_p50_dist_m, 1) }}</strong></div>
          <div class="kv-item"><span>P90</span><strong>{{ formatMeters(profile.snapshot.gps_p90_dist_m, 2) }}</strong></div>
          <div class="kv-item"><span>基线 P50</span><strong>{{ formatMeters(profile.snapshot.baseline_gps_p50_dist_m, 1) }}</strong></div>
          <div class="kv-item"><span>基线 P90</span><strong>{{ formatMeters(profile.snapshot.baseline_gps_p90_dist_m, 2) }}</strong></div>
          <div class="kv-item"><span>北京框检查</span><strong>{{ profile.snapshot.outside_beijing_bbox ? '框外' : '框内' }}</strong></div>
          <div class="kv-item"><span>中国框检查</span><strong>{{ profile.snapshot.outside_china_bbox ? '框外' : '框内' }}</strong></div>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Object State</p>
            <h3>对象状态 + 旧参考信息</h3>
          </div>
        </header>
        <div class="badge-stack">
          <BadgePill :tone="lifecycleTone(profile.snapshot.lifecycle_state)" :label="lifecycleLabel(profile.snapshot.lifecycle_state)" />
          <BadgePill :tone="healthTone(profile.snapshot.health_state)" :label="healthLabel(profile.snapshot.health_state)" />
          <BadgePill :tone="profile.snapshot.anchorable ? 'green' : 'slate'" :label="profile.snapshot.anchorable ? '可锚定' : '不可锚定'" />
          <BadgePill :tone="profile.snapshot.baseline_eligible ? 'blue' : 'slate'" :label="profile.snapshot.baseline_eligible ? '基线合格' : '基线不合格'" />
        </div>
        <div class="reference-panel">
          <div class="kv-item"><span>旧分类（来自 BS）</span><strong>{{ profile.snapshot.legacy_bs_classification ?? '无' }}</strong></div>
          <div class="kv-item"><span>GPS 可信度（参考）</span><strong>{{ profile.snapshot.legacy_gps_quality }}</strong></div>
          <div class="kv-item"><span>R2 health</span><strong>{{ healthLabel(profile.compare_context.r2_health_state) }}</strong></div>
          <div class="kv-item"><span>R3 health</span><strong>{{ healthLabel(profile.compare_context.r3_health_state) }}</strong></div>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Source Mix</p>
            <h3>画像质量（GPS / 信号来源构成）</h3>
          </div>
        </header>
        <div class="bar-grid">
          <article class="mini-panel">
            <strong>GPS 来源</strong>
            <MetricBars :items="profile.gps_source_mix" tone="blue" />
          </article>
          <article class="mini-panel">
            <strong>信号来源</strong>
            <MetricBars :items="profile.signal_source_mix" tone="green" />
          </article>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Fact Routes</p>
            <h3>最近事实去向</h3>
          </div>
        </header>
        <MetricBars :items="factBars" tone="orange" />
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Rule Audit</p>
            <h3>过滤 / 门槛显示区</h3>
          </div>
        </header>
        <div class="audit-list">
          <article v-for="item in profile.rule_audit" :key="item.label" class="audit-row">
            <div class="audit-row__head">
              <strong>{{ item.label }}</strong>
              <BadgePill :tone="ruleTone(item.state)" :label="ruleLabel(item.state)" />
            </div>
            <p>{{ item.detail }}</p>
          </article>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Compare + Notes</p>
            <h3>口径说明</h3>
          </div>
        </header>
        <div class="compare-card">
          <div class="badge-stack">
            <BadgePill :tone="compareTone(profile.compare_context.membership)" :label="compareLabel(profile.compare_context.membership)" />
            <BadgePill :tone="profile.compare_context.legacy_gps_anomaly ? 'orange' : 'green'" :label="profile.compare_context.legacy_gps_anomaly ? 'legacy 命中' : 'legacy 未命中'" />
          </div>
          <p>{{ profile.compare_context.explanation }}</p>
          <p class="muted-text">legacy 原因：{{ profile.compare_context.legacy_gps_anomaly_reason ?? '无' }}</p>
          <ul class="note-list">
            <li v-for="item in profile.profile_notes" :key="item">{{ item }}</li>
            <li v-for="note in transparency.notes" :key="note">{{ note }}</li>
          </ul>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

import BadgePill from '../components/BadgePill.vue';
import MetricBars from '../components/MetricBars.vue';
import {
  fallbackCellObjectId,
  fallbackTransparency,
  fetchCellProfile,
  fetchCellTransparency,
  type CellProfileResponse,
  type TransparencyResponse,
} from '../lib/cellApi';
import {
  compareLabel,
  compareTone,
  formatCoordinate,
  formatMeters,
  healthLabel,
  healthTone,
  lifecycleLabel,
  lifecycleTone,
  ruleLabel,
  ruleTone,
} from '../lib/format';

const route = useRoute();
const profile = ref<CellProfileResponse | null>(null);
const transparency = ref<TransparencyResponse>(fallbackTransparency);

const objectId = computed(() => {
  return typeof route.params.objectId === 'string' && route.params.objectId ? route.params.objectId : fallbackCellObjectId;
});

const factBars = computed(() => {
  return profile.value?.facts.map((item) => ({ label: item.route, count: item.count })) ?? [];
});

async function load(): Promise<void> {
  const [profileData, transparencyData] = await Promise.all([fetchCellProfile(objectId.value), fetchCellTransparency()]);
  profile.value = profileData;
  transparency.value = transparencyData;
}

watch(objectId, load, { immediate: true });
onMounted(load);
</script>

<style scoped>
.profile-hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.profile-hero__aside {
  display: grid;
  gap: 0.65rem;
  justify-items: end;
}

.profile-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.metric-card {
  display: grid;
  gap: 0.72rem;
  padding: 1.2rem 1.25rem;
  border-radius: 1.5rem;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--border-soft);
  min-height: 10rem;
}

.metric-card--hero {
  background: linear-gradient(135deg, rgba(32, 69, 144, 0.98), rgba(63, 102, 186, 0.92));
  color: white;
}

.metric-card--hero .metric-card__label,
.metric-card--hero .metric-card__detail {
  color: rgba(239, 244, 255, 0.78);
}

.metric-card__label {
  font-size: 0.76rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.metric-card__value {
  font-size: clamp(1.75rem, 2.4vw, 2.5rem);
  line-height: 0.95;
  letter-spacing: -0.05em;
}

.metric-card__detail {
  color: var(--text-soft);
  line-height: 1.6;
}

.reference-panel,
.bar-grid {
  display: grid;
  gap: 1rem;
}

.bar-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mini-panel,
.compare-card,
.audit-row {
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--border-soft);
  background: rgba(248, 251, 255, 0.9);
}

.mini-panel,
.compare-card {
  display: grid;
  gap: 0.8rem;
}

.audit-list {
  display: grid;
  gap: 0.8rem;
}

.audit-row {
  display: grid;
  gap: 0.5rem;
}

.audit-row__head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

@media (max-width: 1120px) {
  .profile-summary-grid,
  .bar-grid,
  .detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .profile-hero {
    flex-direction: column;
  }

  .profile-hero__aside {
    justify-items: flex-start;
  }
}
</style>
