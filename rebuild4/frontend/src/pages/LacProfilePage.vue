<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getProfileLac } from '../lib/api'

const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const summary = ref<Record<string, any>>({})
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const expandedIdx = ref<number | null>(null)
const f = ref({ operator: '', rat: '', lifecycle: '' })

function fmt(n: any, d?: number) { if (n == null) return '-'; if (typeof n === 'number') return d != null ? n.toFixed(d) : n.toLocaleString(); return n }
function pct(n: any) { return n != null ? (n * 100).toFixed(1) + '%' : '-' }
function toggle(idx: number) { expandedIdx.value = expandedIdx.value === idx ? null : idx }

async function load() {
  loading.value = true; error.value = ''
  try {
    const q: Record<string, any> = { page: page.value, size: pageSize.value }
    for (const [k, v] of Object.entries(f.value)) { if (v) q[k] = v }
    const res = await getProfileLac(q)
    items.value = res.data?.items || []; summary.value = res.data?.summary || {}; total.value = res.data?.total || 0
  } catch (e: any) { error.value = e.message || '加载失败' } finally { loading.value = false }
}
function doSearch() { page.value = 1; expandedIdx.value = null; load() }
function reset() { f.value = { operator:'', rat:'', lifecycle:'' }; doSearch() }
function goPage(p: number) { page.value = p; expandedIdx.value = null; load() }
const totalPages = () => Math.max(1, Math.ceil(total.value / pageSize.value))
onMounted(load)
</script>

<template>
  <div class="page">
    <h2 class="page-title">LAC 画像</h2>
    <p class="page-desc">从 BS 画像聚合 | 共 {{ fmt(summary.total) }} 个 LAC</p>
    <div class="filter-grid">
      <select v-model="f.operator" class="ctl"><option value="">全部运营商</option><option value="46000">移动</option><option value="46001">联通</option><option value="46011">电信</option></select>
      <select v-model="f.rat" class="ctl"><option value="">全部制式</option><option value="4G">4G</option><option value="5G">5G</option></select>
      <select v-model="f.lifecycle" class="ctl"><option value="">全部状态</option><option value="active">active</option><option value="observing">observing</option><option value="waiting">waiting</option></select>
    </div>
    <div class="filter-actions"><button class="btn" @click="doSearch">筛选</button><button class="btn" @click="reset">重置</button></div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="error" class="empty red">{{ error }}</div>
    <template v-else>
      <div class="cards-row">
        <div class="card"><div class="card-l">总数</div><div class="card-v">{{ fmt(summary.total) }}</div></div>
        <div class="card"><div class="card-l">Active</div><div class="card-v g">{{ fmt(summary.active) }}</div></div>
        <div class="card"><div class="card-l">Observing</div><div class="card-v a">{{ fmt(summary.observing) }}</div></div>
        <div class="card"><div class="card-l">Waiting</div><div class="card-v">{{ fmt(summary.waiting) }}</div></div>
        <div class="card"><div class="card-l">有异常BS</div><div class="card-v r">{{ fmt(summary.has_anomaly) }}</div></div>
      </div>
      <div class="table-wrap"><table class="dt"><thead><tr>
        <th style="width:24px"></th><th>运营商</th><th>制式</th><th>LAC</th><th>状态</th><th>BS数</th><th>Cell数</th><th>记录数</th><th>面积km2</th><th>异常BS率</th><th>RSRP</th><th>位置</th>
      </tr></thead><tbody>
        <template v-for="(row, idx) in items" :key="idx">
          <tr class="dr" @click="toggle(idx)">
            <td class="et">{{ expandedIdx===idx?'&#9662;':'&#9656;' }}</td>
            <td>{{ row.operator_cn||'-' }}</td><td>{{ row.tech_norm||'-' }}</td><td class="mono">{{ row.lac||'-' }}</td>
            <td><span :class="['tag',{active:'tag-green',observing:'tag-amber',waiting:'tag-gray'}[row.lifecycle_state]||'tag-gray']">{{ row.lifecycle_state||'-' }}</span></td>
            <td>{{ fmt(row.bs_count) }}</td><td>{{ fmt(row.cell_count) }}</td><td>{{ fmt(row.record_count) }}</td>
            <td>{{ fmt(row.area_km2) }}</td><td>{{ pct(row.anomaly_bs_ratio) }}</td><td>{{ fmt(row.rsrp_avg) }}</td>
            <td class="loc-td">{{ row.district_name||'-' }}</td>
          </tr>
          <tr v-if="expandedIdx===idx" class="expanded"><td :colspan="12"><div class="exp-content">
            <div class="sec-title">概况</div>
            <div class="dg">
              <div class="di"><span class="dl">LAC 中心</span><span class="dv mono">{{ fmt(row.center_lon,4) }}, {{ fmt(row.center_lat,4) }}</span></div>
              <div class="di"><span class="dl">面积</span><span class="dv">{{ fmt(row.area_km2) }} km2</span></div>
              <div class="di"><span class="dl">位置</span><span class="dv">{{ row.province_name }} {{ row.city_name }} {{ row.district_name }}</span></div>
              <div class="di"><span class="dl">位置质量</span><span class="dv">{{ row.position_grade }}</span></div>
            </div>
            <div class="sec-title">组成</div>
            <div class="dg">
              <div class="di"><span class="dl">BS / Active BS</span><span class="dv">{{ fmt(row.bs_count) }} / {{ fmt(row.active_bs_count) }}</span></div>
              <div class="di"><span class="dl">碰撞 BS</span><span class="dv" :class="{'red':row.collision_bs_count>0}">{{ fmt(row.collision_bs_count) }}</span></div>
              <div class="di"><span class="dl">动态 BS</span><span class="dv">{{ fmt(row.dynamic_bs_count) }}</span></div>
              <div class="di"><span class="dl">大覆盖 BS</span><span class="dv">{{ fmt(row.large_spread_bs_count) }}</span></div>
            </div>
            <div class="sec-title">质量</div>
            <div class="dg">
              <div class="di"><span class="dl">GPS 原始率</span><span class="dv">{{ pct(row.gps_original_ratio) }}</span></div>
              <div class="di"><span class="dl">信号原始率</span><span class="dv">{{ pct(row.signal_original_ratio) }}</span></div>
              <div class="di"><span class="dl">设备总数</span><span class="dv">{{ fmt(row.total_devices) }}</span></div>
              <div class="di"><span class="dl">活跃天数</span><span class="dv">{{ fmt(row.active_days) }}</span></div>
            </div>
          </div></td></tr>
        </template>
      </tbody></table></div>
      <div class="pag"><button class="btn btn-sm" :disabled="page<=1" @click="goPage(page-1)">上一页</button><span class="pag-info">共 {{ fmt(total) }} 条, 第 {{ page }}/{{ totalPages() }} 页</span><button class="btn btn-sm" :disabled="page>=totalPages()" @click="goPage(page+1)">下一页</button></div>
    </template>
  </div>
</template>

<style scoped>
.page{max-width:1500px;margin:0 auto;padding:24px 16px}.page-title{font-size:20px;font-weight:700;color:var(--text-h);margin:0 0 4px}.page-desc{font-size:12px;color:var(--text);margin:0 0 16px}.filter-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:8px}.filter-actions{display:flex;gap:8px;margin-bottom:16px}.ctl{padding:5px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--bg);color:var(--text)}.btn{padding:5px 14px;border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;background:var(--bg);color:var(--text-h)}.btn:hover{background:var(--accent-bg)}.btn:disabled{opacity:.4;cursor:default}.btn-sm{padding:3px 10px;font-size:11px}.cards-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:14px}.card{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px}.card-l{font-size:11px;color:var(--text)}.card-v{font-size:18px;font-weight:700;color:var(--text-h)}.card-v.g{color:#16a34a}.card-v.a{color:#d97706}.card-v.r{color:#dc2626}.table-wrap{overflow-x:auto;margin-bottom:10px}.dt{width:100%;border-collapse:collapse;font-size:12px}.dt th{text-align:left;padding:7px 8px;border-bottom:2px solid var(--border);font-weight:600;font-size:11px;color:var(--text);white-space:nowrap}.dt td{padding:6px 8px;border-bottom:1px solid var(--border);color:var(--text-h)}.dr{cursor:pointer}.dr:hover{background:var(--accent-bg)}.mono{font-family:var(--mono);font-size:11px}.et{color:var(--text);font-size:10px;text-align:center}.loc-td{font-size:11px;max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tag{display:inline-block;padding:1px 7px;border-radius:3px;font-size:10px;font-weight:600;white-space:nowrap}.tag-green{background:#dcfce7;color:#15803d}.tag-amber{background:#fef3c7;color:#b45309}.tag-gray{background:#f3f4f6;color:#6b7280}.expanded td{background:var(--code-bg);padding:0}.exp-content{padding:14px 16px}.sec-title{font-size:10px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:.5px;margin:10px 0 4px;border-bottom:1px solid var(--border);padding-bottom:3px}.sec-title:first-child{margin-top:0}.dg{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.di{display:flex;flex-direction:column;gap:1px}.dl{font-size:10px;color:var(--text)}.dv{font-size:12px;color:var(--text-h);font-weight:500}.red{color:#dc2626}.pag{display:flex;align-items:center;justify-content:center;gap:12px;padding:10px 0}.pag-info{font-size:11px;color:var(--text)}.empty{text-align:center;padding:48px 16px;color:var(--text);font-size:14px}
</style>
