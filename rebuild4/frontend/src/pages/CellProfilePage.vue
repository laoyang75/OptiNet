<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getProfileCell } from '../lib/api'

const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const summary = ref<Record<string, any>>({})
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const expandedIdx = ref<number | null>(null)

const f = ref({ operator: '', rat: '', lac: '', bs_id: '', lifecycle: '', drift: '', grade: '', scale: '' })

function fmt(n: any, d?: number) {
  if (n == null) return '-'
  if (typeof n === 'number') return d != null ? n.toFixed(d) : n.toLocaleString()
  return n
}
function pct(n: any) { return n != null ? (n * 100).toFixed(1) + '%' : '-' }
function toggle(idx: number) { expandedIdx.value = expandedIdx.value === idx ? null : idx }

async function load() {
  loading.value = true; error.value = ''
  try {
    const q: Record<string, any> = { page: page.value, size: pageSize.value }
    for (const [k, v] of Object.entries(f.value)) { if (v) q[k] = v }
    const res = await getProfileCell(q)
    items.value = res.data?.items || []
    summary.value = res.data?.summary || {}
    total.value = res.data?.total || 0
  } catch (e: any) { error.value = e.message || '加载失败' }
  finally { loading.value = false }
}
function doSearch() { page.value = 1; expandedIdx.value = null; load() }
function reset() { f.value = { operator:'', rat:'', lac:'', bs_id:'', lifecycle:'', drift:'', grade:'', scale:'' }; doSearch() }
function goPage(p: number) { page.value = p; expandedIdx.value = null; load() }
const totalPages = () => Math.max(1, Math.ceil(total.value / pageSize.value))

const driftCfg: Record<string, {label:string,cls:string}> = {
  stable: { label:'稳定', cls:'tag-green' },
  collision: { label:'碰撞', cls:'tag-red' },
  migration: { label:'搬迁', cls:'tag-purple' },
  dynamic: { label:'动态', cls:'tag-blue' },
  large_coverage: { label:'大覆盖', cls:'tag-teal' },
  moderate_drift: { label:'中度漂移', cls:'tag-amber' },
  insufficient: { label:'数据不足', cls:'tag-gray' },
}
const gradeCfg: Record<string, {label:string,cls:string}> = {
  excellent: { label:'优秀', cls:'tag-green' },
  good: { label:'良好', cls:'tag-blue' },
  qualified: { label:'合格', cls:'tag-amber' },
  unqualified: { label:'不合格', cls:'tag-gray' },
}
const scaleCfg: Record<string, {label:string,cls:string}> = {
  major: { label:'主力', cls:'tag-green' },
  large: { label:'大型', cls:'tag-blue' },
  medium: { label:'中型', cls:'tag-teal' },
  small: { label:'小型', cls:'tag-amber' },
  micro: { label:'微型', cls:'tag-gray' },
}

function tagFor(cfg: Record<string,{label:string,cls:string}>, key: string) {
  return cfg[key] || { label: key || '-', cls: 'tag-gray' }
}

const gradeBarData = computed(() => {
  const s = summary.value
  const t = s.total || 1
  return [
    { key:'excellent', label:'优秀', n: s.grade_excellent, pct: (s.grade_excellent||0)/t*100, cls:'bar-green' },
    { key:'good', label:'良好', n: s.grade_good, pct: (s.grade_good||0)/t*100, cls:'bar-blue' },
    { key:'qualified', label:'合格', n: s.grade_qualified, pct: (s.grade_qualified||0)/t*100, cls:'bar-amber' },
    { key:'unqualified', label:'不合格', n: s.grade_unqualified, pct: (s.grade_unqualified||0)/t*100, cls:'bar-gray' },
  ]
})

onMounted(load)
</script>

<template>
  <div class="page">
    <h2 class="page-title">Cell 画像</h2>
    <p class="page-desc">中位数质心 + 日漂移分类 + 质量分级 | 共 {{ fmt(summary.total) }} 个 Cell</p>

    <!-- Filters: 2 rows -->
    <div class="filter-grid">
      <select v-model="f.operator" class="ctl"><option value="">全部运营商</option><option value="46000">移动</option><option value="46001">联通</option><option value="46011">电信</option></select>
      <select v-model="f.rat" class="ctl"><option value="">全部制式</option><option value="4G">4G</option><option value="5G">5G</option><option value="2G">2G</option></select>
      <input v-model="f.lac" class="ctl" placeholder="LAC" />
      <input v-model="f.bs_id" class="ctl" placeholder="BS ID" />
      <select v-model="f.lifecycle" class="ctl"><option value="">全部生命周期</option><option value="active">active</option><option value="observing">observing</option><option value="waiting">waiting</option></select>
      <select v-model="f.drift" class="ctl"><option value="">全部漂移</option><option value="stable">稳定</option><option value="collision">碰撞</option><option value="migration">搬迁</option><option value="dynamic">动态</option><option value="large_coverage">大覆盖</option></select>
      <select v-model="f.grade" class="ctl"><option value="">全部质量</option><option value="excellent">优秀</option><option value="good">良好</option><option value="qualified">合格</option><option value="unqualified">不合格</option></select>
      <select v-model="f.scale" class="ctl"><option value="">全部规模</option><option value="major">主力</option><option value="large">大型</option><option value="medium">中型</option><option value="small">小型</option><option value="micro">微型</option></select>
    </div>
    <div class="filter-actions"><button class="btn" @click="doSearch">筛选</button><button class="btn" @click="reset">重置</button></div>

    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="error" class="empty red">{{ error }}</div>
    <template v-else>
      <!-- Summary cards -->
      <div class="cards-row">
        <div class="card"><div class="card-l">总数</div><div class="card-v">{{ fmt(summary.total) }}</div></div>
        <div class="card"><div class="card-l">Active</div><div class="card-v g">{{ fmt(summary.active) }}</div></div>
        <div class="card"><div class="card-l">Observing</div><div class="card-v a">{{ fmt(summary.observing) }}</div></div>
        <div class="card"><div class="card-l">Waiting</div><div class="card-v">{{ fmt(summary.waiting) }}</div></div>
        <div class="card"><div class="card-l">碰撞</div><div class="card-v r">{{ fmt((summary.collision||0)) }}</div></div>
        <div class="card"><div class="card-l">动态</div><div class="card-v b">{{ fmt(summary.dynamic) }}</div></div>
        <div class="card"><div class="card-l">搬迁</div><div class="card-v p">{{ fmt(summary.migration) }}</div></div>
      </div>

      <!-- Position grade bar -->
      <div class="bar-section">
        <div class="bar-label">位置质量分布</div>
        <div class="bar-track">
          <div v-for="b in gradeBarData" :key="b.key" :class="['bar-seg', b.cls]" :style="{width: b.pct+'%'}" :title="b.label+': '+fmt(b.n)"></div>
        </div>
        <div class="bar-legend">
          <span v-for="b in gradeBarData" :key="b.key" class="leg-item"><span :class="['dot', b.cls]"></span>{{ b.label }} {{ fmt(b.n) }}</span>
        </div>
      </div>

      <!-- Table -->
      <div class="table-wrap">
        <table class="dt">
          <thead><tr>
            <th style="width:24px"></th>
            <th>运营商</th><th>制式</th><th>LAC</th><th>BS</th><th>Cell ID</th>
            <th>质量</th><th>规模</th><th>漂移</th><th>生命周期</th>
            <th>独立观测</th><th>设备</th><th>P90(m)</th><th>RSRP</th><th>位置</th>
          </tr></thead>
          <tbody>
            <template v-for="(row, idx) in items" :key="idx">
              <tr class="dr" @click="toggle(idx)">
                <td class="et">{{ expandedIdx===idx?'&#9662;':'&#9656;' }}</td>
                <td>{{ row.operator_cn||'-' }}</td>
                <td>{{ row.tech_norm||'-' }}</td>
                <td class="mono">{{ row.lac||'-' }}</td>
                <td class="mono">{{ row.bs_id||'-' }}</td>
                <td class="mono">{{ row.cell_id||'-' }}</td>
                <td><span :class="['tag', tagFor(gradeCfg, row.position_grade).cls]">{{ tagFor(gradeCfg, row.position_grade).label }}</span></td>
                <td><span :class="['tag', tagFor(scaleCfg, row.cell_scale).cls]">{{ tagFor(scaleCfg, row.cell_scale).label }}</span></td>
                <td><span :class="['tag', tagFor(driftCfg, row.drift_pattern).cls]">{{ tagFor(driftCfg, row.drift_pattern).label }}</span></td>
                <td><span :class="['tag', {active:'tag-green',observing:'tag-amber',waiting:'tag-gray'}[row.lifecycle_state]||'tag-gray']">{{ row.lifecycle_state||'-' }}</span></td>
                <td>{{ fmt(row.independent_obs) }}</td>
                <td>{{ fmt(row.independent_devs) }}</td>
                <td>{{ fmt(row.p90_radius_m) }}</td>
                <td>{{ fmt(row.rsrp_avg) }}</td>
                <td class="loc-td">{{ row.district_name||'-' }}</td>
              </tr>
              <!-- Expanded -->
              <tr v-if="expandedIdx===idx" class="expanded">
                <td :colspan="15">
                  <div class="exp-content">
                    <div class="sec-title">空间</div>
                    <div class="dg">
                      <div class="di"><span class="dl">中位数质心</span><span class="dv mono">{{ fmt(row.center_lon, 4) }}, {{ fmt(row.center_lat, 4) }}</span></div>
                      <div class="di"><span class="dl">P50 / P90</span><span class="dv">{{ fmt(row.p50_radius_m) }}m / {{ fmt(row.p90_radius_m) }}m</span></div>
                      <div class="di"><span class="dl">Cell-BS 距离</span><span class="dv">{{ fmt(row.dist_to_bs_m) }}m</span></div>
                      <div class="di"><span class="dl">位置</span><span class="dv">{{ row.province_name }} {{ row.city_name }} {{ row.district_name }}</span></div>
                    </div>
                    <div class="sec-title">漂移分析</div>
                    <div class="dg">
                      <div class="di"><span class="dl">漂移模式</span><span :class="['dv', row.is_collision?'red':'']">{{ tagFor(driftCfg, row.drift_pattern).label }}</span></div>
                      <div class="di"><span class="dl">日间最大距离</span><span class="dv">{{ fmt(row.drift_max_spread_m) }}m</span></div>
                      <div class="di"><span class="dl">净漂移</span><span class="dv">{{ fmt(row.drift_net_m) }}m</span></div>
                      <div class="di"><span class="dl">质心天数</span><span class="dv">{{ fmt(row.drift_days) }}天</span></div>
                    </div>
                    <div class="sec-title">数据质量</div>
                    <div class="dg">
                      <div class="di"><span class="dl">独立观测点</span><span class="dv">{{ fmt(row.independent_obs) }} ({{ fmt(row.independent_devs) }}台 / {{ fmt(row.independent_days) }}天)</span></div>
                      <div class="di"><span class="dl">GPS 原始率 / 有效率</span><span class="dv">{{ pct(row.gps_original_ratio) }} / {{ pct(row.gps_valid_ratio) }}</span></div>
                      <div class="di"><span class="dl">GPS / 信号置信度</span><span class="dv">{{ row.gps_confidence }} / {{ row.signal_confidence }}</span></div>
                      <div class="di"><span class="dl">观测时段</span><span class="dv">{{ fmt(row.observed_span_hours) }}h / {{ fmt(row.active_days) }}天</span></div>
                    </div>
                    <div class="sec-title">信号</div>
                    <div class="dg">
                      <div class="di"><span class="dl">RSRP</span><span class="dv">{{ fmt(row.rsrp_avg) }} dBm</span></div>
                      <div class="di"><span class="dl">RSRQ</span><span class="dv">{{ fmt(row.rsrq_avg) }} dB</span></div>
                      <div class="di"><span class="dl">SINR</span><span class="dv">{{ fmt(row.sinr_avg) }} dB</span></div>
                      <div class="di"><span class="dl">原始信号率</span><span class="dv">{{ pct(row.signal_original_ratio) }}</span></div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div class="pag">
        <button class="btn btn-sm" :disabled="page<=1" @click="goPage(page-1)">上一页</button>
        <span class="pag-info">共 {{ fmt(total) }} 条, 第 {{ page }}/{{ totalPages() }} 页</span>
        <button class="btn btn-sm" :disabled="page>=totalPages()" @click="goPage(page+1)">下一页</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width:1500px; margin:0 auto; padding:24px 16px; }
.page-title { font-size:20px; font-weight:700; color:var(--text-h); margin:0 0 4px; }
.page-desc { font-size:12px; color:var(--text); margin:0 0 16px; }
.filter-grid { display:grid; grid-template-columns:repeat(8,1fr); gap:6px; margin-bottom:8px; }
.filter-actions { display:flex; gap:8px; margin-bottom:16px; }
.ctl { padding:5px 10px; border:1px solid var(--border); border-radius:6px; font-size:12px; background:var(--bg); color:var(--text); }
.btn { padding:5px 14px; border:1px solid var(--border); border-radius:6px; font-size:12px; cursor:pointer; background:var(--bg); color:var(--text-h); }
.btn:hover { background:var(--accent-bg); }
.btn:disabled { opacity:.4; cursor:default; }
.btn-sm { padding:3px 10px; font-size:11px; }

.cards-row { display:grid; grid-template-columns:repeat(7,1fr); gap:8px; margin-bottom:12px; }
.card { background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px 12px; }
.card-l { font-size:11px; color:var(--text); }
.card-v { font-size:18px; font-weight:700; color:var(--text-h); }
.card-v.g { color:#16a34a; } .card-v.a { color:#d97706; } .card-v.r { color:#dc2626; }
.card-v.b { color:#2563eb; } .card-v.p { color:#7c3aed; }

.bar-section { margin-bottom:14px; }
.bar-label { font-size:12px; color:var(--text); margin-bottom:4px; }
.bar-track { display:flex; height:18px; border-radius:4px; overflow:hidden; background:var(--border); }
.bar-seg { min-width:2px; }
.bar-green { background:#16a34a; } .bar-blue { background:#2563eb; } .bar-amber { background:#d97706; } .bar-gray { background:#d1d5db; }
.bar-legend { display:flex; gap:14px; margin-top:5px; }
.leg-item { display:flex; align-items:center; gap:4px; font-size:11px; color:var(--text); }
.dot { width:8px; height:8px; border-radius:2px; }

.table-wrap { overflow-x:auto; margin-bottom:10px; }
.dt { width:100%; border-collapse:collapse; font-size:12px; }
.dt th { text-align:left; padding:7px 8px; border-bottom:2px solid var(--border); font-weight:600; font-size:11px; color:var(--text); white-space:nowrap; }
.dt td { padding:6px 8px; border-bottom:1px solid var(--border); color:var(--text-h); }
.dr { cursor:pointer; } .dr:hover { background:var(--accent-bg); }
.mono { font-family:var(--mono); font-size:11px; }
.et { color:var(--text); font-size:10px; text-align:center; }
.loc-td { font-size:11px; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

.tag { display:inline-block; padding:1px 7px; border-radius:3px; font-size:10px; font-weight:600; white-space:nowrap; }
.tag-green { background:#dcfce7; color:#15803d; }
.tag-blue { background:#dbeafe; color:#1d4ed8; }
.tag-teal { background:#ccfbf1; color:#0f766e; }
.tag-amber { background:#fef3c7; color:#b45309; }
.tag-orange { background:#ffedd5; color:#c2410c; }
.tag-red { background:#fee2e2; color:#dc2626; }
.tag-purple { background:#ede9fe; color:#6d28d9; }
.tag-gray { background:#f3f4f6; color:#6b7280; }

.expanded td { background:var(--code-bg); padding:0; }
.exp-content { padding:14px 16px; }
.sec-title { font-size:10px; font-weight:700; color:var(--text); text-transform:uppercase; letter-spacing:.5px; margin:10px 0 4px; border-bottom:1px solid var(--border); padding-bottom:3px; }
.sec-title:first-child { margin-top:0; }
.dg { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.di { display:flex; flex-direction:column; gap:1px; }
.dl { font-size:10px; color:var(--text); }
.dv { font-size:12px; color:var(--text-h); font-weight:500; }
.red { color:#dc2626; }

.pag { display:flex; align-items:center; justify-content:center; gap:12px; padding:10px 0; }
.pag-info { font-size:11px; color:var(--text); }
.empty { text-align:center; padding:48px 16px; color:var(--text); font-size:14px; }
</style>
