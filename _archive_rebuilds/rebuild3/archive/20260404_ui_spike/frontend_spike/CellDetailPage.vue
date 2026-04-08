<template>
  <section class="page-stack" v-if="detail">
    <nav class="breadcrumbs">
      <RouterLink :to="{ name: 'cell-objects' }">对象浏览</RouterLink>
      <span>/</span>
      <span>{{ detail.snapshot.cell_id }}</span>
    </nav>

    <header class="page-hero panel-surface panel-surface--hero detail-hero">
      <div class="hero-main">
        <p class="kicker">04 Object Detail / Cell</p>
        <h2>{{ detail.snapshot.object_id }}</h2>
        <p class="hero-blurb">
          这个页面把当前状态、资格原因、事实路由、legacy 差异和 BS 级联影响合成一个完整证据链。
        </p>
        <div class="badge-stack">
          <BadgePill :tone="lifecycleTone(detail.snapshot.lifecycle_state)" :label="lifecycleLabel(detail.snapshot.lifecycle_state)" />
          <BadgePill :tone="healthTone(detail.snapshot.health_state)" :label="healthLabel(detail.snapshot.health_state)" />
          <BadgePill :tone="compareTone(detail.compare_context.membership)" :label="compareLabel(detail.compare_context.membership)" />
          <BadgePill v-if="detail.snapshot.watch" tone="orange" label="WATCH" />
          <BadgePill v-if="detail.snapshot.outside_beijing_bbox" tone="red" label="北京框外" />
        </div>
      </div>
      <div class="hero-actions">
        <BadgePill :tone="detail.status === 'ok' ? 'green' : 'blue'" :label="detail.status === 'ok' ? '实时数据' : '快照数据'" />
        <RouterLink class="hero-link" :to="{ name: 'cell-profile', params: { objectId } }">查看 Cell 画像</RouterLink>
        <RouterLink class="hero-link hero-link--ghost" :to="{ name: 'cell-objects' }">返回列表</RouterLink>
      </div>
    </header>

    <div class="detail-grid">
      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Snapshot</p>
            <h3>基本信息</h3>
          </div>
        </header>
        <div class="kv-grid">
          <div class="kv-item"><span>运营商</span><strong>{{ detail.snapshot.operator_name }}</strong></div>
          <div class="kv-item"><span>制式</span><strong>{{ detail.snapshot.tech_norm }}</strong></div>
          <div class="kv-item"><span>LAC</span><strong>{{ detail.snapshot.lac }}</strong></div>
          <div class="kv-item"><span>BS ID</span><strong>{{ detail.snapshot.bs_id }}</strong></div>
          <div class="kv-item"><span>Cell ID</span><strong>{{ detail.snapshot.cell_id }}</strong></div>
          <div class="kv-item"><span>批次</span><strong>{{ detail.snapshot.batch_id }}</strong></div>
          <div class="kv-item"><span>run_id</span><strong>{{ detail.snapshot.run_id }}</strong></div>
          <div class="kv-item"><span>legacy GPS可信度</span><strong>{{ detail.snapshot.legacy_gps_quality }}</strong></div>
          <div class="kv-item"><span>旧分类（来自 BS）</span><strong>{{ detail.snapshot.legacy_bs_classification ?? '无' }}</strong></div>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Profile Summary</p>
            <h3>画像摘要</h3>
          </div>
        </header>
        <div class="kv-grid">
          <div class="kv-item"><span>记录数</span><strong>{{ formatNumber(detail.snapshot.record_count) }}</strong></div>
          <div class="kv-item"><span>GPS样本</span><strong>{{ formatNumber(detail.snapshot.gps_count) }}</strong></div>
          <div class="kv-item"><span>设备数</span><strong>{{ formatNumber(detail.snapshot.device_count) }}</strong></div>
          <div class="kv-item"><span>活跃天数</span><strong>{{ detail.snapshot.active_days }} 天</strong></div>
          <div class="kv-item"><span>P50</span><strong>{{ formatMeters(detail.snapshot.gps_p50_dist_m, 1) }}</strong></div>
          <div class="kv-item"><span>P90</span><strong>{{ formatMeters(detail.snapshot.gps_p90_dist_m, 2) }}</strong></div>
          <div class="kv-item"><span>GPS原始率</span><strong>{{ formatPercent(detail.snapshot.gps_original_ratio) }}</strong></div>
          <div class="kv-item"><span>信号原始率</span><strong>{{ formatPercent(detail.snapshot.signal_original_ratio) }}</strong></div>
          <div class="kv-item"><span>RSRP</span><strong>{{ detail.snapshot.rsrp_avg ?? '--' }}</strong></div>
          <div class="kv-item"><span>中心偏移</span><strong>{{ formatMeters(detail.snapshot.center_shift_m, 2) }}</strong></div>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Compare</p>
            <h3>rebuild2 / rebuild3 差异上下文</h3>
          </div>
        </header>
        <div class="compare-card">
          <div class="badge-stack">
            <BadgePill :tone="compareTone(detail.compare_context.membership)" :label="compareLabel(detail.compare_context.membership)" />
            <BadgePill :tone="detail.compare_context.r3_baseline_eligible ? 'blue' : 'slate'" :label="detail.compare_context.r3_baseline_eligible ? 'R3 基线合格' : 'R3 基线禁用'" />
            <BadgePill :tone="detail.compare_context.r2_baseline_eligible ? 'green' : 'slate'" :label="detail.compare_context.r2_baseline_eligible ? 'R2 基线合格' : 'R2 基线禁用'" />
          </div>
          <p>{{ detail.compare_context.explanation }}</p>
          <div class="kv-grid kv-grid--tight">
            <div class="kv-item"><span>R2 health</span><strong>{{ healthLabel(detail.compare_context.r2_health_state) }}</strong></div>
            <div class="kv-item"><span>R3 health</span><strong>{{ healthLabel(detail.compare_context.r3_health_state) }}</strong></div>
            <div class="kv-item"><span>legacy gps_anomaly</span><strong>{{ detail.compare_context.legacy_gps_anomaly ? '命中' : '未命中' }}</strong></div>
            <div class="kv-item"><span>legacy 原因</span><strong>{{ detail.compare_context.legacy_gps_anomaly_reason ?? '无' }}</strong></div>
          </div>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Facts</p>
            <h3>最近事实去向</h3>
          </div>
        </header>
        <MetricBars :items="factBars" tone="blue" />
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">History</p>
            <h3>状态历史</h3>
          </div>
        </header>
        <div class="timeline">
          <article v-for="item in detail.history" :key="`${item.changed_at}-${item.changed_reason}`" class="timeline-item">
            <div class="timeline-item__dot"></div>
            <div class="timeline-item__body">
              <div class="timeline-item__head">
                <strong>{{ item.changed_reason }}</strong>
                <span>{{ item.changed_at }}</span>
              </div>
              <div class="badge-stack">
                <BadgePill :tone="lifecycleTone(item.lifecycle_state)" :label="lifecycleLabel(item.lifecycle_state)" />
                <BadgePill :tone="healthTone(item.health_state)" :label="healthLabel(item.health_state)" />
                <BadgePill :tone="item.anchorable ? 'green' : 'slate'" :label="item.anchorable ? '可锚定' : '锚点禁用'" />
                <BadgePill :tone="item.baseline_eligible ? 'blue' : 'slate'" :label="item.baseline_eligible ? '基线合格' : '基线禁用'" />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Qualification</p>
            <h3>资格原因</h3>
          </div>
        </header>
        <div class="reason-grid">
          <article v-for="group in detail.qualification_reasons" :key="group.label" class="reason-card">
            <div class="reason-card__head">
              <strong>{{ group.label }}</strong>
              <BadgePill :tone="group.passed ? 'green' : 'orange'" :label="group.passed ? '通过' : '未通过'" />
            </div>
            <ul>
              <li v-for="item in group.items" :key="item">{{ item }}</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Rule Audit</p>
            <h3>页面必须直出的规则审计</h3>
          </div>
        </header>
        <div class="audit-list">
          <article v-for="item in detail.rule_audit" :key="item.label" class="audit-row">
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
            <p class="kicker">Anomalies</p>
            <h3>关联异常</h3>
          </div>
        </header>
        <div v-if="!detail.anomalies.length" class="empty-state">当前对象没有展开中的异常明细。</div>
        <div v-else class="compact-list">
          <article v-for="item in detail.anomalies" :key="`${item.type}-${item.detail}`" class="mini-card">
            <div class="mini-card__head">
              <strong>{{ item.type }}</strong>
              <BadgePill :tone="item.severity === 'high' ? 'red' : item.severity === 'medium' ? 'orange' : 'amber'" :label="item.severity" />
            </div>
            <p>{{ item.detail }}</p>
          </article>
        </div>
      </section>

      <section class="panel-surface panel-stack">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Downstream</p>
            <h3>下游影响</h3>
          </div>
        </header>
        <div class="kv-grid kv-grid--tight">
          <div class="kv-item"><span>BS 对象</span><strong>{{ detail.downstream.bs_object_id }}</strong></div>
          <div class="kv-item"><span>BS health</span><strong>{{ healthLabel(detail.downstream.bs_health_state ?? 'healthy') }}</strong></div>
          <div class="kv-item"><span>BS active cell</span><strong>{{ formatNumber(detail.downstream.bs_active_cell_count) }}</strong></div>
          <div class="kv-item"><span>同 BS Cell 总数</span><strong>{{ formatNumber(detail.downstream.sibling_cell_count) }}</strong></div>
          <div class="kv-item"><span>同 BS active Cell</span><strong>{{ formatNumber(detail.downstream.sibling_active_cell_count) }}</strong></div>
          <div class="kv-item"><span>同 BS baseline Cell</span><strong>{{ formatNumber(detail.downstream.sibling_baseline_cell_count) }}</strong></div>
          <div class="kv-item"><span>LAC 对象</span><strong>{{ detail.downstream.lac_object_id }}</strong></div>
          <div class="kv-item"><span>LAC health</span><strong>{{ healthLabel(detail.downstream.lac_health_state ?? 'healthy') }}</strong></div>
          <div class="kv-item"><span>LAC active BS</span><strong>{{ formatNumber(detail.downstream.lac_active_bs_count) }}</strong></div>
        </div>
      </section>

      <section class="panel-surface panel-stack detail-grid__wide">
        <header class="section-header section-header--compact">
          <div>
            <p class="kicker">Change Log</p>
            <h3>全局调整清单</h3>
          </div>
        </header>
        <div class="compact-list compact-list--grid">
          <article v-for="item in detail.change_log" :key="item.label" class="mini-card">
            <div class="mini-card__head">
              <strong>{{ item.label }}</strong>
              <span>{{ item.impact_metric }}</span>
            </div>
            <p>{{ item.effect }}</p>
            <code>{{ item.source_ref }}</code>
          </article>
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
import { fallbackCellObjectId, fetchCellDetail, type CellDetailResponse } from '../lib/cellApi';
import {
  compareLabel,
  compareTone,
  formatMeters,
  formatNumber,
  formatPercent,
  healthLabel,
  healthTone,
  lifecycleLabel,
  lifecycleTone,
  ruleLabel,
  ruleTone,
} from '../lib/format';

const route = useRoute();
const detail = ref<CellDetailResponse | null>(null);

const objectId = computed(() => {
  return typeof route.params.objectId === 'string' && route.params.objectId ? route.params.objectId : fallbackCellObjectId;
});

const factBars = computed(() => {
  return detail.value?.facts.map((item) => ({ label: item.route, count: item.count })) ?? [];
});

async function load(): Promise<void> {
  detail.value = await fetchCellDetail(objectId.value);
}

watch(objectId, load, { immediate: true });
onMounted(load);
</script>

<style scoped>
.detail-hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.hero-main {
  display: grid;
  gap: 0.8rem;
}

.hero-actions {
  display: grid;
  gap: 0.65rem;
  justify-items: end;
}

.hero-link {
  padding: 0.68rem 1rem;
  border-radius: 999px;
  background: rgba(239, 245, 255, 0.92);
  color: var(--blue-strong);
  font-weight: 700;
  border: 1px solid rgba(44, 94, 188, 0.14);
}

.hero-link--ghost {
  color: var(--text-soft);
  background: rgba(250, 251, 253, 0.94);
  border-color: var(--border-soft);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.detail-grid__wide {
  grid-column: 1 / -1;
}

.compare-card,
.reason-card,
.audit-row,
.timeline-item {
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--border-soft);
  background: rgba(248, 251, 255, 0.9);
}

.compare-card {
  display: grid;
  gap: 0.85rem;
}

.kv-grid--tight {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.timeline,
.audit-list,
.reason-grid {
  display: grid;
  gap: 0.8rem;
}

.timeline-item {
  display: grid;
  grid-template-columns: 1rem minmax(0, 1fr);
  gap: 0.85rem;
}

.timeline-item__dot {
  margin-top: 0.35rem;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(44, 94, 188, 0.92), rgba(87, 127, 210, 0.82));
}

.timeline-item__body,
.reason-card {
  display: grid;
  gap: 0.65rem;
}

.timeline-item__head,
.reason-card__head,
.audit-row__head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.reason-card ul {
  margin: 0;
  padding-left: 1.1rem;
  color: var(--text-soft);
  line-height: 1.65;
}

.audit-row {
  display: grid;
  gap: 0.5rem;
}

.compact-list--grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 1040px) {
  .detail-grid,
  .compact-list--grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .detail-hero {
    flex-direction: column;
  }

  .hero-actions {
    justify-items: flex-start;
  }
}
</style>
