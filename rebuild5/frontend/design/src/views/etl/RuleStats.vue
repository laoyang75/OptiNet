<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import SummaryCard from '../../components/common/SummaryCard.vue'
import { getRuleStats, type EtlRuleStatsItem } from '../../api/etl'
import { fmt, pct } from '../../composables/useFormat'

const RULE_FULL_TEXT: Record<string, string> = {
  'ODS-019': 'CellInfos 解析阶段过滤陈旧缓存对象：past_time - timeStamp 超过配置阈值的 connected cell_infos 对象不进入 etl_ci；字段缺失或格式异常时保守保留。',
  'ODS-020': 'SS1 子记录按本 record_id 内 max(ts_sec) 为锚点，超过 etl_ss1.max_age_from_anchor_sec 的历史子记录丢弃。',
  'ODS-021': 'SS1 cell 与 sig 必须同组同制式匹配。无配套 sig 的 cell 不 emit，用于抑制双卡或缓存 cell_id 污染。',
  'ODS-022': 'SS1 sig 条目中 ss、rsrp、rsrq、sinr 全为 -1 时视为无效信号，解析阶段丢弃。',
  'ODS-023b': 'LTE FDD 频段下 timing_advance >= 255 或 < 0 的异常值置空，保留远郊大 cell 的合法 TA=100-200 区间。',
  'ODS-024b': 'CellInfos 同一 record_id、cell_id 重复出现时仅保留 age 最小的对象，清理 SDK 缓存重复对象。',
}

const rows = ref<EtlRuleStatsItem[]>([])
const batches = ref<number[]>([])
const selectedBatch = ref<number>(0)
const loading = ref(false)
const modalRule = ref<EtlRuleStatsItem | null>(null)

const totalHits = computed(() => rows.value.reduce((sum, row) => sum + Number(row.hit_count || 0), 0))
const maxHit = computed(() => Math.max(...rows.value.map(row => Number(row.hit_count || 0)), 1))
const latestRecordedAt = computed(() => rows.value.map(r => r.recorded_at).filter(Boolean).sort().pop() || '-')

function fmtTime(v: string | null): string {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 19)
}

async function loadStats() {
  loading.value = true
  try {
    const payload = await getRuleStats(selectedBatch.value || undefined)
    rows.value = [...payload.items].sort((a, b) => Number(b.hit_count) - Number(a.hit_count))
    batches.value = payload.batches
    if (!selectedBatch.value && payload.batches.length > 0) selectedBatch.value = payload.batches[0]
  } catch {
    rows.value = []
    batches.value = []
  } finally {
    loading.value = false
  }
}

watch(selectedBatch, () => loadStats())
onMounted(loadStats)
</script>

<template>
  <PageHeader title="ODS 规则命中" description="Step 1 清洗与解析规则 hit count 监控，覆盖 ODS-019/020/021/022/023b/024b。">
    <div class="flex items-center gap-sm text-xs text-secondary">
      <span>batch</span>
      <select v-model.number="selectedBatch" class="select-sm">
        <option :value="0">最新</option>
        <option v-for="b in batches" :key="b" :value="b">batch {{ b }}</option>
      </select>
    </div>
  </PageHeader>

  <div class="grid grid-3 mb-lg">
    <SummaryCard title="规则数" :value="fmt(rows.length)" />
    <SummaryCard title="总命中" :value="fmt(totalHits)" color="var(--c-warning)" />
    <SummaryCard title="记录时间" :value="fmtTime(latestRecordedAt)" />
  </div>

  <div class="card" style="padding:0;overflow:auto">
    <div class="table-head">
      <span class="font-semibold text-sm">规则命中列表</span>
      <span class="text-xs text-secondary">{{ loading ? '加载中...' : `${fmt(rows.length)} 条` }}</span>
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>规则</th>
          <th>说明</th>
          <th class="num">命中数</th>
          <th>命中率</th>
          <th>总行数</th>
          <th>记录时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="`${row.batch_id}-${row.rule_code}`">
          <td><button class="link-btn font-mono font-semibold" @click="modalRule = row">{{ row.rule_code }}</button></td>
          <td class="text-sm text-secondary">{{ row.rule_desc }}</td>
          <td class="font-mono num">{{ fmt(row.hit_count) }}</td>
          <td>
            <div class="hit-cell">
              <div class="hit-track">
                <div class="hit-fill" :style="{ width: `${Math.max(row.hit_pct * 100, row.hit_count > 0 ? 2 : 0)}%` }"></div>
              </div>
              <span class="font-mono">{{ pct(row.hit_pct) }}</span>
            </div>
          </td>
          <td class="font-mono">{{ row.total_rows != null ? fmt(row.total_rows) : '-' }}</td>
          <td class="text-xs">{{ fmtTime(row.recorded_at) }}</td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="6" class="empty-row">暂无规则命中数据，等待 Step 1 重跑后写入 rb5_meta.etl_rule_stats</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card mt-lg">
    <div class="font-semibold text-sm mb-sm">命中规模</div>
    <div class="rank-list">
      <div v-for="row in rows" :key="`rank-${row.rule_code}`" class="rank-row">
        <span class="font-mono">{{ row.rule_code }}</span>
        <div class="rank-track"><div class="rank-fill" :style="{ width: `${(row.hit_count / maxHit) * 100}%` }"></div></div>
        <span class="font-mono num">{{ fmt(row.hit_count) }}</span>
      </div>
    </div>
  </div>

  <div v-if="modalRule" class="modal-mask" @click.self="modalRule = null">
    <div class="modal-card">
      <div class="modal-head">
        <span class="font-mono font-semibold">{{ modalRule.rule_code }}</span>
        <button class="btn btn-sm" @click="modalRule = null">关闭</button>
      </div>
      <p class="rule-text">{{ RULE_FULL_TEXT[modalRule.rule_code] || modalRule.rule_desc }}</p>
    </div>
  </div>
</template>

<style scoped>
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp-md); }
.select-sm { height: 28px; padding: 2px 8px; border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-card); color: var(--c-text); }
.table-head { display: flex; align-items: center; justify-content: space-between; padding: var(--sp-lg) var(--sp-lg) 0; }
.num { text-align: right; }
.link-btn { border: 0; background: transparent; color: var(--c-primary); cursor: pointer; padding: 0; }
.hit-cell { display: grid; grid-template-columns: minmax(90px, 1fr) 54px; align-items: center; gap: 8px; }
.hit-track, .rank-track { height: 8px; border-radius: 4px; background: var(--c-bg); overflow: hidden; }
.hit-fill, .rank-fill { height: 100%; border-radius: 4px; background: var(--c-warning); }
.rank-list { display: flex; flex-direction: column; gap: 8px; }
.rank-row { display: grid; grid-template-columns: 76px minmax(120px, 1fr) 90px; align-items: center; gap: 10px; font-size: 12px; }
.empty-row { padding: 20px; text-align: center; color: var(--c-text-muted); }
.modal-mask { position: fixed; inset: 0; background: rgb(15 23 42 / 45%); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal-card { width: min(560px, calc(100vw - 32px)); background: var(--c-card); border: 1px solid var(--c-border); border-radius: 8px; padding: 16px; box-shadow: var(--shadow-lg); }
.modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.rule-text { margin: 0; font-size: 13px; line-height: 1.7; color: var(--c-text-secondary); }
.btn-sm { padding: 3px 10px; font-size: 11px; }
@media (max-width: 900px) { .grid-3 { grid-template-columns: 1fr; } }
</style>
