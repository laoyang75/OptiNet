<template>
  <div class="page-stack">
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 类型 Tab + 筛选 -->
    <div class="section">
      <div class="tab-row" style="margin-bottom: 12px;">
        <button v-for="t in typeOptions" :key="t.value" class="tab-button" :class="{ 'tab-button--active': filters.object_type === t.value }" @click="switchType(t.value)">{{ t.label }}</button>
      </div>

      <div class="filters-grid filters-grid--five">
        <div class="filter-field"><label>搜索</label><input v-model="filters.query" placeholder="object_id / LAC / BS / Cell" @keyup.enter="applyFilters" /></div>
        <div class="filter-field"><label>生命周期</label>
          <select v-model="filters.lifecycle_state">
            <option value="all">全部</option>
            <option value="waiting">等待</option>
            <option value="observing">观察</option>
            <option value="active">活跃</option>
            <option value="dormant">休眠</option>
            <option value="retired">退役</option>
            <option value="rejected">拒收</option>
          </select>
        </div>
        <div class="filter-field"><label>健康状态</label>
          <select v-model="filters.health_state">
            <option value="all">全部</option>
            <option value="healthy">健康</option>
            <option value="insufficient">证据不足</option>
            <option value="collision_suspect">碰撞嫌疑</option>
            <option value="collision_confirmed">碰撞确认</option>
            <option value="dynamic">动态</option>
            <option value="gps_bias">GPS偏差</option>
            <option value="migration_suspect">迁移嫌疑</option>
          </select>
        </div>
        <div class="filter-field"><label>资格</label>
          <select v-model="filters.qualification">
            <option value="all">全部</option>
            <option value="anchorable">可锚定</option>
            <option value="not_anchorable">锚点禁用</option>
            <option value="baseline">基线合格</option>
            <option value="not_baseline">基线禁用</option>
          </select>
        </div>
        <div class="filter-field"><label>搜索 / 排序</label>
          <div class="flex-row gap-2">
            <button class="action-button" @click="applyFilters">筛选</button>
            <button class="inline-button" @click="resetFilters">重置</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 汇总条（水平 flex） -->
    <div v-if="summary" class="obj-summary-bar">
      <div class="obj-summary-item"><span class="obj-summary-label">总数</span><strong>{{ fmtN(summary.total) }}</strong></div>
      <div class="obj-summary-item"><span class="obj-summary-label">活跃</span><strong>{{ fmtN(summary.active) }}</strong></div>
      <div class="obj-summary-item"><span class="obj-summary-label">健康</span><strong>{{ fmtN(summary.healthy) }}</strong></div>
      <div class="obj-summary-item"><span class="obj-summary-label">锚点可用</span><strong>{{ fmtN(summary.anchorable) }}</strong></div>
      <div class="obj-summary-item"><span class="obj-summary-label">WATCH</span><strong>{{ fmtN(summary.watch) }}</strong></div>
      <div class="obj-summary-item"><span class="obj-summary-label">基线合格</span><strong>{{ fmtN(summary.baseline_eligible) }}</strong></div>
    </div>

    <!-- 表格 -->
    <div class="section">
      <div v-if="loading" class="loader">正在加载对象列表...</div>
      <div v-else-if="!rows.length" class="page-empty">未找到匹配对象。</div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>主键</th>
              <th>生命周期</th>
              <th>健康状态</th>
              <th>锚点</th>
              <th>基线</th>
              <th>样本数</th>
              <th>设备数</th>
              <th>活跃天数</th>
              <th>最近活跃</th>
              <th>异常标签</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.object_id"
              :class="{ 'is-watch': isWatch(row) }"
            >
              <td>
                <RouterLink :to="detailLink(row)" class="link-button mono">{{ row.object_id }}</RouterLink>
                <div class="text-muted text-sm">{{ objectTypeLabel(row.object_type) }}</div>
              </td>
              <td><LifecycleBadge :state="row.lifecycle_state" /></td>
              <td>
                <HealthBadge :state="row.health_state" />
                <WatchIndicator :lifecycle-state="row.lifecycle_state" :health-state="row.health_state" />
              </td>
              <td>{{ row.anchorable ? '✓' : '✗' }}</td>
              <td>{{ row.baseline_eligible ? '✓' : '✗' }}</td>
              <td class="mono">{{ fmtN(row.record_count) }}</td>
              <td class="mono">{{ fmtN(row.device_count) }}</td>
              <td>{{ row.active_days ?? '—' }}</td>
              <td class="text-sm">{{ row.last_active || '—' }}</td>
              <td>
                <span v-if="row.anomaly_tags" class="text-sm text-muted">{{ row.anomaly_tags }}</span>
                <span v-else class="text-muted text-sm">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex-row gap-4" style="margin-top:12px;justify-content:space-between;">
        <span class="text-muted text-sm">共 {{ fmtN(total) }} 条，第 {{ filters.page }}/{{ totalPages }} 页</span>
        <div class="badge-row">
          <button class="inline-button" :disabled="filters.page <= 1" @click="changePage(filters.page - 1)">上一页</button>
          <button class="inline-button" :disabled="filters.page >= totalPages" @click="changePage(filters.page + 1)">下一页</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';

import HealthBadge from '../components/HealthBadge.vue';
import LifecycleBadge from '../components/LifecycleBadge.vue';
import WatchIndicator from '../components/WatchIndicator.vue';
import { api } from '../lib/api';
import { objectTypeLabel } from '../lib/format';

const typeOptions = [
  { value: 'cell', label: 'Cell' },
  { value: 'bs', label: 'BS' },
  { value: 'lac', label: 'LAC' },
];

const filters = reactive({
  object_type: 'cell', query: '', lifecycle_state: 'all', health_state: 'all', qualification: 'all',
  page: 1, page_size: 20, sort_by: 'record_count', sort_dir: 'desc',
});

const loading = ref(false); const error = ref('');
const summary = ref<any>(null); const rows = ref<any[]>([]);
const total = ref(0); const totalPages = ref(1);

function fmtN(n: number | undefined): string { return n != null ? n.toLocaleString() : '—'; }
function isWatch(row: any): boolean { return row.lifecycle_state === 'active' && row.health_state !== 'healthy'; }
function detailLink(row: any) { return { name: 'object-detail', params: { objectType: row.object_type, objectId: row.object_id } }; }

async function loadPage() {
  loading.value = true; error.value = '';
  try {
    const [s, l] = await Promise.all([api.getObjectsSummary(filters.object_type), api.getObjectsList(filters)]);
    summary.value = s.summary; rows.value = l.rows ?? []; total.value = l.total ?? 0; totalPages.value = l.total_pages ?? 1;
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; } finally { loading.value = false; }
}

function applyFilters() { filters.page = 1; loadPage(); }
function resetFilters() { Object.assign(filters, { query: '', lifecycle_state: 'all', health_state: 'all', qualification: 'all', page: 1 }); loadPage(); }
function changePage(p: number) { filters.page = p; loadPage(); }
function switchType(t: string) { filters.object_type = t; filters.page = 1; loadPage(); }

onMounted(loadPage);
</script>

<style scoped>
.obj-summary-bar {
  display: flex; align-items: center; gap: 0;
  background: var(--surface-bg); border: 1px solid var(--surface-border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card); overflow: hidden;
}
.obj-summary-item {
  flex: 1; padding: 12px 20px; display: flex; align-items: center; gap: 8px;
  border-right: 1px solid var(--gray-100);
}
.obj-summary-item:last-child { border-right: none; }
.obj-summary-label { font-size: 12px; color: var(--gray-400); font-weight: 500; }
.obj-summary-item strong { font-size: 18px; font-weight: 700; }
</style>
