<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getEtlFillStats } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const data = ref<any>(null)

function fmt(n: any) { return typeof n === 'number' ? n.toLocaleString() : (n ?? '-') }
function pct(n: any) { return typeof n === 'number' ? (n * 100).toFixed(1) + '%' : '-' }

onMounted(async () => {
  try { data.value = (await getEtlFillStats()).data } catch {}
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">5. 补齐</h2>
        <p class="page-desc">同一报文（record_id）内，相同 cell_id 的行互补 GPS 和 RSRP。补齐不增减行数，只填充空值。</p>
      </div>
      <div class="scope-select">
        <label>Scope</label>
        <select :value="data?.scope || 'sample'">
          <option value="sample">sample</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="!data" class="loading">ETL 未执行，暂无数据。</div>
    <template v-else>

      <div class="section">
        <div class="section-title">GPS 补齐</div>
        <div class="compare-grid">
          <div class="compare-card">
            <div class="compare-title">补齐前</div>
            <div class="row"><span>有 GPS</span><strong>{{ fmt(data.before_gps) }}</strong></div>
            <div class="row"><span>无 GPS</span><strong>{{ fmt(data.before_total - data.before_gps) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong>{{ pct(data.before_gps / data.before_total) }}</strong></div>
          </div>
          <div class="arrow">→</div>
          <div class="compare-card accent">
            <div class="compare-title">补齐后</div>
            <div class="row"><span>原始有</span><strong>{{ fmt(data.gps_original) }}</strong></div>
            <div class="row highlight"><span>同cell补齐</span><strong>{{ fmt(data.gps_filled) }}</strong></div>
            <div class="row"><span>仍无</span><strong>{{ fmt(data.gps_none) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong class="good">{{ pct(data.gps_rate) }}</strong></div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">RSRP 补齐</div>
        <div class="compare-grid">
          <div class="compare-card">
            <div class="compare-title">补齐前</div>
            <div class="row"><span>有 RSRP</span><strong>{{ fmt(data.before_rsrp) }}</strong></div>
            <div class="row"><span>无 RSRP</span><strong>{{ fmt(data.before_total - data.before_rsrp) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong>{{ pct(data.before_rsrp / data.before_total) }}</strong></div>
          </div>
          <div class="arrow">→</div>
          <div class="compare-card accent">
            <div class="compare-title">补齐后</div>
            <div class="row"><span>原始有</span><strong>{{ fmt(data.rsrp_original) }}</strong></div>
            <div class="row highlight"><span>同cell补齐</span><strong>{{ fmt(data.rsrp_filled) }}</strong></div>
            <div class="row"><span>仍无</span><strong>{{ fmt(data.rsrp_none) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong class="good">{{ pct(data.rsrp_rate) }}</strong></div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="note">
          补齐逻辑：同一条原始报文内，相同 cell_id 且有效的行互补。<br>
          cell_infos 行通常有 GPS（来自原始上报），ss1 行通常有信号 → 互补后两者都更完整。
        </div>
        <div class="run-info">scope: {{ data.scope }} · 执行时间: {{ data.run_at }}</div>
      </div>

      <EtlFooter code-path="rebuild4/backend/app/etl/pipeline.py → step3_fill()" doc-path="rebuild4/docs/01_etl/03_补齐.md" />
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 980px; margin: 0 auto; padding: 24px 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-h); margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text); margin: 0; }
.scope-select { display: flex; align-items: center; gap: 8px; }
.scope-select label { font-size: 12px; font-weight: 600; color: var(--text); }
.scope-select select { font-size: 13px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text-h); }
.loading { text-align: center; padding: 48px; color: var(--text); }
.section { margin-bottom: 24px; }
.section-title { font-size: 15px; font-weight: 700; color: var(--text-h); margin-bottom: 10px; }
.run-info { font-size: 11px; color: var(--text); margin-top: 8px; }

.compare-grid { display: flex; align-items: stretch; gap: 16px; }
.compare-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; min-width: 200px; }
.compare-card.accent { background: #faf5ff; border-color: #a855f7; }
.compare-title { font-size: 13px; font-weight: 700; color: var(--text-h); margin-bottom: 8px; }
.row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; color: var(--text-h); }
.row.highlight { background: #fef3c7; margin: 2px -6px; padding: 3px 6px; border-radius: 4px; }
.arrow { display: flex; align-items: center; font-size: 24px; font-weight: 700; color: var(--text); }
.good { color: #059669; }

.note { font-size: 12px; color: var(--text); background: var(--social-bg); padding: 10px 14px; border-radius: 6px; line-height: 1.6; }
</style>
