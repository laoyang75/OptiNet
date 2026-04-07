<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getEtlFillStats } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const d = ref<any>(null)

function fmt(n: any) { return typeof n === 'number' ? n.toLocaleString() : (n ?? '-') }
function pct(n: any) { return typeof n === 'number' ? (n * 100).toFixed(1) + '%' : '-' }

onMounted(async () => {
  try { d.value = (await getEtlFillStats()).data } catch {}
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">5. 补齐</h2>
        <p class="page-desc">同报文（record_id）内，相同 cell_id 的行互补。补齐不增减行数，只填充空值。</p>
      </div>
      <div class="scope-select" v-if="d">
        <label>Scope</label>
        <select :value="d.scope || 'sample'"><option value="sample">sample</option></select>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="!d" class="loading">ETL 未执行，暂无数据。</div>
    <template v-else>

      <!-- GPS 补齐 -->
      <div class="section">
        <div class="section-title">GPS 补齐</div>
        <div class="compare-grid">
          <div class="card">
            <div class="card-title">补齐前</div>
            <div class="row"><span>有 GPS</span><strong>{{ fmt(d.before_gps) }}</strong></div>
            <div class="row"><span>无 GPS</span><strong>{{ fmt(d.before_total - d.before_gps) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong>{{ pct(d.before_gps / d.before_total) }}</strong></div>
          </div>
          <div class="arrow">→</div>
          <div class="card accent">
            <div class="card-title">补齐后</div>
            <div class="row"><span>原始有</span><strong>{{ fmt(d.gps_original) }}</strong></div>
            <div class="row hl"><span>同cell补齐</span><strong>+{{ fmt(d.gps_filled) }}</strong></div>
            <div class="row"><span>仍无</span><strong>{{ fmt(d.gps_none) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong class="good">{{ pct(d.gps_rate) }}</strong></div>
          </div>
        </div>
      </div>

      <!-- RSRP 补齐 -->
      <div class="section">
        <div class="section-title">RSRP 补齐</div>
        <div class="compare-grid">
          <div class="card">
            <div class="card-title">补齐前</div>
            <div class="row"><span>有 RSRP</span><strong>{{ fmt(d.before_rsrp) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong>{{ pct(d.before_rsrp / d.before_total) }}</strong></div>
          </div>
          <div class="arrow">→</div>
          <div class="card accent">
            <div class="card-title">补齐后</div>
            <div class="row"><span>原始有</span><strong>{{ fmt(d.rsrp_original) }}</strong></div>
            <div class="row hl"><span>同cell补齐</span><strong>+{{ fmt(d.rsrp_filled) }}</strong></div>
            <div class="row"><span>仍无</span><strong>{{ fmt(d.rsrp_none) }}</strong></div>
            <div class="row"><span>覆盖率</span><strong class="good">{{ pct(d.rsrp_rate) }}</strong></div>
          </div>
        </div>
      </div>

      <!-- 运营商 / LAC / WiFi 补齐 -->
      <div class="section">
        <div class="section-title">其他字段补齐</div>
        <table class="tbl">
          <thead><tr><th>字段</th><th>补齐前有值</th><th>同cell补齐</th><th>说明</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>运营商编码</strong></td>
              <td>{{ fmt(d.before_operator) }}</td>
              <td :class="{ hl: d.operator_filled > 0 }">+{{ fmt(d.operator_filled) }}</td>
              <td>总是可补（不受时间约束）</td>
            </tr>
            <tr>
              <td><strong>LAC</strong></td>
              <td>{{ fmt(d.before_lac) }}</td>
              <td :class="{ hl: d.lac_filled > 0 }">+{{ fmt(d.lac_filled) }}</td>
              <td>总是可补（不受时间约束）</td>
            </tr>
            <tr>
              <td><strong>WiFi 名称</strong></td>
              <td>{{ fmt(d.before_wifi) }}</td>
              <td :class="{ hl: d.wifi_filled > 0 }">+{{ fmt(d.wifi_filled) }}</td>
              <td>时间差 ≤ 60秒才补</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <div class="note">
          <strong>补齐规则</strong><br>
          同一报文内，相同 cell_id 的行互补。cell 碰撞在同一报文内几乎不会发生。<br>
          <strong>时间约束</strong>：cell_infos 行之间/cell_infos→ss1 总是全补。ss1→ss1 时间差 > 60秒只补运营商+LAC。
        </div>
        <div class="run-info" v-if="d.run_at">scope: {{ d.scope }} · 执行时间: {{ d.run_at }}</div>
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
.card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; min-width: 200px; }
.card.accent { background: #faf5ff; border-color: #a855f7; }
.card-title { font-size: 13px; font-weight: 700; color: var(--text-h); margin-bottom: 8px; }
.row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; color: var(--text-h); }
.row.hl { background: #fef3c7; margin: 2px -6px; padding: 3px 6px; border-radius: 4px; }
.arrow { display: flex; align-items: center; font-size: 24px; font-weight: 700; color: var(--text); }
.good { color: #059669; }

.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; padding: 7px 8px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 11px; color: var(--text); }
.tbl td { padding: 6px 8px; border-bottom: 1px solid var(--border); color: var(--text-h); }
.tbl td.hl { color: #b45309; font-weight: 700; }

.note { font-size: 12px; color: var(--text); background: var(--social-bg); padding: 10px 14px; border-radius: 6px; line-height: 1.6; }
</style>
