<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import StatusTag from '../../components/common/StatusTag.vue'
import { mockCells } from '../../mock/data'
import { fmt } from '../../composables/useFormat'
import { DRIFT_LABELS, type DriftPattern } from '../../types'

const driftDist: Record<DriftPattern, number> = { insufficient: 120, stable: 3200, collision: 85, migration: 42, large_coverage: 180, moderate_drift: 95 }

const anomalyCells = mockCells.filter(c => c.is_collision || c.drift_pattern === 'collision' || c.drift_pattern === 'migration' || c.is_multi_centroid)
</script>

<template>
  <PageHeader title="Cell 维护" description="Step 5 深度维护：漂移分类、碰撞确认、多质心、GPS 异常时序、退出管理。" />

  <div class="grid grid-6 mb-lg">
    <SummaryCard title="稳定" :value="fmt(driftDist.stable)" color="var(--c-success)" />
    <SummaryCard title="大覆盖" :value="fmt(driftDist.large_coverage)" color="var(--c-warning)" />
    <SummaryCard title="证据不足" :value="fmt(driftDist.insufficient)" />
    <SummaryCard title="中度漂移" :value="fmt(driftDist.moderate_drift)" color="var(--c-dormant)" />
    <SummaryCard title="碰撞" :value="fmt(driftDist.collision)" color="var(--c-danger)" />
    <SummaryCard title="迁移" :value="fmt(driftDist.migration)" color="var(--c-retired)" />
  </div>

  <!-- 漂移分类分布 -->
  <div class="card mb-lg">
    <div class="font-semibold text-sm mb-md">漂移分类分布</div>
    <div class="drift-bar">
      <div v-for="(count, pattern) in driftDist" :key="pattern" class="drift-seg" :class="`drift-${pattern}`"
        :style="{ width: (count / Object.values(driftDist).reduce((a,b) => a+b, 0) * 100) + '%' }"
        :title="`${DRIFT_LABELS[pattern as DriftPattern]}: ${count}`"
      ></div>
    </div>
    <div class="flex flex-wrap gap-lg mt-md text-xs">
      <span v-for="(count, pattern) in driftDist" :key="pattern" class="flex items-center gap-xs">
        <span class="dot" :class="`bg-${pattern}`"></span>
        {{ DRIFT_LABELS[pattern as DriftPattern] }} {{ count }}
      </span>
    </div>
  </div>

  <!-- 异常 Cell 列表 -->
  <div class="card" style="padding:0;overflow:auto">
    <div style="padding:var(--sp-lg) var(--sp-lg) 0" class="flex justify-between items-center">
      <span class="font-semibold text-sm">异常 Cell 列表</span>
      <div class="flex gap-sm">
        <button class="btn">碰撞</button>
        <button class="btn">迁移</button>
        <button class="btn">多质心</button>
        <button class="btn">全部异常</button>
      </div>
    </div>
    <table class="data-table" style="margin-top:var(--sp-sm)">
      <thead>
        <tr>
          <th>cell_id</th>
          <th>LAC</th>
          <th>状态</th>
          <th>漂移分类</th>
          <th>max_spread (m)</th>
          <th>碰撞</th>
          <th>多质心</th>
          <th>动态站</th>
          <th>规则命中</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in anomalyCells" :key="c.cell_id">
          <td class="font-mono font-semibold">{{ c.cell_id }}</td>
          <td class="font-mono">{{ c.lac }}</td>
          <td><StatusTag :state="c.lifecycle_state" size="sm" /></td>
          <td>
            <span class="tag" :class="`drift-tag-${c.drift_pattern}`">{{ DRIFT_LABELS[c.drift_pattern!] }}</span>
          </td>
          <td class="font-mono">{{ Math.floor(Math.random() * 5000 + 500) }}</td>
          <td>
            <span v-if="c.is_collision" style="color:var(--c-danger)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td>
            <span v-if="c.is_multi_centroid" style="color:var(--c-warning)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td>
            <span v-if="c.is_dynamic" style="color:var(--c-dormant)">&#10003;</span>
            <span v-else class="text-muted">-</span>
          </td>
          <td class="text-xs text-secondary">max_spread ≥ 2200m, ratio &lt; 0.3</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.drift-bar { display: flex; height: 12px; border-radius: 6px; overflow: hidden; }
.drift-seg { min-width: 2px; }
.drift-stable { background: var(--c-success); }
.drift-collision { background: var(--c-danger); }
.drift-migration { background: #7c3aed; }
.drift-large_coverage { background: var(--c-warning); }
.drift-moderate_drift { background: var(--c-dormant); }
.drift-insufficient { background: var(--c-waiting); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.bg-stable { background: var(--c-success); }
.bg-collision { background: var(--c-danger); }
.bg-migration { background: #7c3aed; }
.bg-large_coverage { background: var(--c-warning); }
.bg-moderate_drift { background: var(--c-dormant); }
.bg-insufficient { background: var(--c-waiting); }
.drift-tag-stable { background: #dcfce7; color: #166534; }
.drift-tag-collision { background: #fee2e2; color: #991b1b; }
.drift-tag-migration { background: #ede9fe; color: #5b21b6; }
.drift-tag-large_coverage { background: #fef9c3; color: #854d0e; }
.drift-tag-moderate_drift { background: #fff7ed; color: #9a3412; }
.drift-tag-insufficient { background: #f3f4f6; color: #6b7280; }
</style>
