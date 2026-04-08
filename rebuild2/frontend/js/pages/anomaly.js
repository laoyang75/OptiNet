/**
 * L3 问题数据研究：GPS 异常分析与质量评估。
 *
 * 子栏目：
 *   总览: GPS 样本分档统计 + 单设备问题 + GPS 补齐来源
 *   质心分析: 多质心 / 双质心 / 面积大无法确认（后续实现）
 */

import { api } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, renderTable,
} from '../ui/common.js';

let currentTab = 'overview';

function switchTab(tab) { currentTab = tab; loadAnomaly(true); }
window.switchAnomalyTab = switchTab;

// ── 标签工具 ──

function tierTag(tier) {
  const m = {
    'no_gps': ['无 GPS', 'tag-gray'],
    'low':    ['低(1-3)', 'tag-red'],
    'medium': ['中(4-9)', 'tag-orange'],
    'high':   ['高(≥10)', 'tag-green'],
  };
  const [label, cls] = m[tier] || [tier, 'tag-gray'];
  return `<span class="tag ${cls}">${label}</span>`;
}

function confidenceTag(tier) {
  const m = {
    'no_gps': ['不可用', 'tag-gray'],
    'low':    ['低', 'tag-red'],
    'medium': ['中等', 'tag-orange'],
    'high':   ['高', 'tag-green'],
  };
  const [label, cls] = m[tier] || [tier, 'tag-gray'];
  return `<span class="tag ${cls}">${label}</span>`;
}

function sourceTag(src) {
  const labels = {
    'original':       '原始 GPS',
    'cell_center':    'Cell 中心点',
    'bs_center':      'BS 中心点(可用)',
    'bs_center_risk': 'BS 中心点(风险)',
    'not_filled':     '未填充',
  };
  const colors = {
    'original':       'tag-green',
    'cell_center':    'tag-blue',
    'bs_center':      'tag-orange',
    'bs_center_risk': 'tag-red',
    'not_filled':     'tag-gray',
  };
  return `<span class="tag ${colors[src] || 'tag-gray'}">${labels[src] || src}</span>`;
}

// ── 百分比条 ──

function pctBar(value, total, color = 'var(--blue)') {
  const p = total > 0 ? (value / total * 100) : 0;
  return `<div style="display:flex;align-items:center;gap:8px">
    <div style="flex:1;height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">
      <div style="height:100%;width:${Math.min(p, 100)}%;background:${color};border-radius:3px"></div>
    </div>
    <span style="font-size:12px;color:var(--text-dim);min-width:48px;text-align:right">${p.toFixed(1)}%</span>
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  Tab 导航
// ════════════════════════════════════════════════════════════

function renderTabNav() {
  const tabs = [
    { key: 'overview', label: '总体问题数据' },
    { key: 'centroid', label: '质心分析' },
  ];
  return `<div class="toolbar" style="margin-bottom:16px;gap:4px">
    ${tabs.map(t => `<button class="btn ${currentTab === t.key ? 'btn-primary' : 'btn-ghost'}"
      onclick="switchAnomalyTab('${t.key}')"
      ${t.disabled ? 'disabled style="opacity:0.5"' : ''}
    >${t.label}</button>`).join('')}
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  总览页
// ════════════════════════════════════════════════════════════

const TIER_ORDER = ['no_gps', 'low', 'medium', 'high'];
function sortTiers(rows, key = 'tier') {
  return [...rows].sort((a, b) => TIER_ORDER.indexOf(a[key]) - TIER_ORDER.indexOf(b[key]));
}

async function loadOverview() {
  const d = await api('/anomaly/overview', { ttl: 30000 });
  const bs = d.bs_totals;
  const cell = d.cell_totals;

  d.bs_tiers = sortTiers(d.bs_tiers);
  d.cell_tiers = sortTiers(d.cell_tiers);
  d.single_dev_detail = sortTiers(d.single_dev_detail, 'gps_tier');

  const totalBs = d.bs_tiers.reduce((s, r) => s + r.bs_count, 0);
  const totalCell = d.cell_tiers.reduce((s, r) => s + r.cell_count, 0);
  const totalRecords = d.bs_tiers.reduce((s, r) => s + Number(r.record_count), 0);

  // 问题 BS 总数
  const problemBs = bs.bs_no_gps + bs.bs_low_gps + bs.bs_single_device;
  const problemBsRecords = d.bs_tiers
    .filter(r => r.tier === 'no_gps' || r.tier === 'low')
    .reduce((s, r) => s + Number(r.record_count), 0);

  // 单设备 BS 的记录数
  const singleDevRecords = d.single_dev_detail.reduce((s, r) => s + Number(r.record_count), 0);

  return `
    ${renderTabNav()}

    <div class="page-head">
      <div>
        <h2>L3 问题数据总览</h2>
        <p>GPS 样本不足、单设备、补齐异常等问题数据的统计分析，用于 Phase 4 画像质量标记</p>
      </div>
    </div>

    <!-- 核心指标 -->
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-label">基站(BS)总数</div>
        <div class="stat-value blue">${fmt(totalBs)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">问题 BS（无GPS + 低样本 + 单设备）</div>
        <div class="stat-value red">${fmt(problemBs)}</div>
        <div style="font-size:12px;color:var(--text-dim)">${(problemBs / totalBs * 100).toFixed(1)}% 的基站</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">小区(Cell)总数</div>
        <div class="stat-value blue">${fmt(totalCell)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">GPS 异常小区</div>
        <div class="stat-value orange">${fmt(cell.cell_gps_anomaly)}</div>
        <div style="font-size:12px;color:var(--text-dim)">${(cell.cell_gps_anomaly / totalCell * 100).toFixed(1)}% 的小区</div>
      </div>
    </div>

    <!-- BS GPS 分档 -->
    <div class="card">
      <div class="card-title"><h3>基站(BS) GPS 样本分档</h3></div>
      ${renderTable(
        [
          { key: 'tier', label: '分档', render: v => tierTag(v) },
          { key: 'confidence', label: 'GPS 可信度', render: (_, r) => confidenceTag(r.tier) },
          { key: 'bs_count', label: '基站数', className: 'num', render: v => fmt(v) },
          { key: 'bs_pct', label: '占比', render: (_, r) => pctBar(r.bs_count, totalBs, tierBarColor(r.tier)) },
          { key: 'record_count', label: '上报记录数', className: 'num', render: v => fmt(v) },
          { key: 'rec_pct', label: '记录占比', render: (_, r) => pctBar(Number(r.record_count), totalRecords, tierBarColor(r.tier)) },
          { key: 'single_device_count', label: '单设备 BS', className: 'num', render: v => fmt(v) },
        ],
        d.bs_tiers
      )}
      <div style="margin-top:8px;padding:8px 12px;background:var(--bg);border-radius:6px;font-size:13px;color:var(--text-dim)">
        <b>说明</b>：GPS 点数 ≤3 的基站无法可靠计算中心点（样本=中位数本身），标记为低可信度。
        单设备 BS 即 GPS 全部来自同一台终端，不具有空间代表性。
      </div>
    </div>

    <!-- 单设备 BS 详情 -->
    <div class="card">
      <div class="card-title">
        <h3>单设备基站(BS)详情</h3>
        <span class="tag tag-red">${fmt(bs.bs_single_device)} 个 BS · ${fmt(singleDevRecords)} 条记录</span>
      </div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
        GPS 点数 ≥ 4 但仅有 1 台设备（设备标识）上报，GPS 中心点不具有代表性
      </p>
      ${renderTable(
        [
          { key: 'gps_tier', label: 'GPS 分档', render: v => tierTag(v) },
          { key: 'bs_count', label: '基站数', className: 'num', render: v => fmt(v) },
          { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
          { key: 'avg_p90_dist', label: '平均 P90 偏移(m)', className: 'num', render: v => fmt(v) },
          { key: 'avg_max_dist', label: '平均最大偏移(m)', className: 'num', render: v => fmt(v) },
        ],
        d.single_dev_detail
      )}
    </div>

    <!-- Cell GPS 分档 -->
    <div class="card">
      <div class="card-title"><h3>小区(Cell) GPS 样本分档</h3></div>
      ${renderTable(
        [
          { key: 'tier', label: '分档', render: v => tierTag(v) },
          { key: 'confidence', label: 'GPS 可信度', render: (_, r) => confidenceTag(r.tier) },
          { key: 'cell_count', label: '小区数', className: 'num', render: v => fmt(v) },
          { key: 'cell_pct', label: '占比', render: (_, r) => pctBar(r.cell_count, totalCell, tierBarColor(r.tier)) },
          { key: 'record_count', label: '上报记录数', className: 'num', render: v => fmt(v) },
          { key: 'rec_pct', label: '记录占比', render: (_, r) => pctBar(Number(r.record_count), totalRecords, tierBarColor(r.tier)) },
        ],
        d.cell_tiers
      )}
    </div>

    <!-- GPS 补齐来源分布 -->
    <div class="card">
      <div class="card-title"><h3>GPS 补齐来源分布</h3></div>
      ${renderGpsSourceChart(d.gps_source, totalRecords)}
    </div>

    <!-- 高散布 BS 预览 -->
    <div class="card">
      <div class="card-title">
        <h3>高散布异常 BS（待质心分析）</h3>
        <span class="tag tag-orange">${fmt(bs.bs_high_spread)} 个 BS</span>
      </div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:8px">
        GPS ≥ 10 且设备 ≥ 2，P90 偏移 > 1500m 或最大偏移 > 5000m 的基站，将在「质心分析」中进一步分类
      </p>
    </div>
  `;
}

function tierBarColor(tier) {
  const m = { 'no_gps': '#9ca3af', 'low': 'var(--red)', 'medium': 'var(--orange)', 'high': 'var(--green)' };
  return m[tier] || '#6b7280';
}

function renderGpsSourceChart(sources, total) {
  const colors = {
    'original':       'var(--green)',
    'cell_center':    '#2563eb',
    'bs_center':      'var(--orange)',
    'bs_center_risk': 'var(--red)',
    'not_filled':     '#9ca3af',
  };

  // 堆叠条
  const barHtml = `<div style="display:flex;height:24px;border-radius:6px;overflow:hidden;margin-bottom:16px">
    ${sources.map(s => {
      const w = (Number(s.cnt) / total * 100);
      return `<div style="width:${w}%;background:${colors[s.gps_source] || '#ccc'}" title="${s.gps_source}: ${fmt(s.cnt)}"></div>`;
    }).join('')}
  </div>`;

  // 图例表格
  const tableHtml = renderTable(
    [
      { key: 'gps_source', label: '来源', render: v => sourceTag(v) },
      { key: 'cnt', label: '记录数', className: 'num', render: v => fmt(v) },
      { key: 'pct', label: '占比', render: (_, r) => pctBar(Number(r.cnt), total, colors[r.gps_source] || '#ccc') },
    ],
    sources
  );

  return barHtml + tableHtml;
}

// ════════════════════════════════════════════════════════════
//  质心分析 — 漏斗视图
// ════════════════════════════════════════════════════════════

const CAT_META = {
  // Cell 质心法 v2 分类
  dynamic_bs:            { label: '动态BS（含移动Cell）',   color: '#7c3aed', tag: 'tag-purple' },
  collision_confirmed:   { label: '确认碰撞（需拆分）',     color: 'var(--red)', tag: 'tag-red' },
  collision_suspected:   { label: '疑似碰撞（需拆分）',     color: 'var(--orange)', tag: 'tag-orange' },
  collision_uncertain:   { label: '碰撞不确定',              color: '#9ca3af', tag: 'tag-gray' },
  single_large:          { label: '固定Cell质心较近（面积大/低精度）', color: '#2563eb', tag: 'tag-blue' },
  normal_spread:         { label: '固定Cell质心重合（GPS噪声）', color: 'var(--green)', tag: 'tag-green' },
};

function catTag(cat) {
  const m = CAT_META[cat];
  if (!m) return `<span class="tag tag-gray">${cat}</span>`;
  return `<span class="tag ${m.tag}">${m.label}</span>`;
}

function funnelStep(level, title, bs, records, totalBs, totalRecords, color, desc) {
  const bsPct = totalBs > 0 ? (bs / totalBs * 100).toFixed(1) : '0';
  const recPct = totalRecords > 0 ? (records / totalRecords * 100).toFixed(1) : '0';
  const indent = level * 24;
  const barW = totalBs > 0 ? Math.max(bs / totalBs * 100, 1) : 0;
  return `<div style="margin-left:${indent}px;margin-bottom:10px;padding:10px 14px;border-left:3px solid ${color};background:var(--bg-card);border-radius:0 6px 6px 0">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <div>
        <span style="font-weight:600;color:${color}">${level === 0 ? '▶' : '├─'} ${escapeHtml(title)}</span>
        ${desc ? `<span style="font-size:12px;color:var(--text-dim);margin-left:8px">${escapeHtml(desc)}</span>` : ''}
      </div>
      <div style="text-align:right;white-space:nowrap">
        <span style="font-weight:700;color:${color};font-size:15px">${fmt(bs)}</span>
        <span style="font-size:12px;color:var(--text-dim);margin-left:4px">BS (${bsPct}%)</span>
        <span style="font-size:12px;color:var(--text-dim);margin-left:12px">${fmt(records)} 条 (${recPct}%)</span>
      </div>
    </div>
    <div style="margin-top:4px;height:4px;background:#e5e7eb;border-radius:2px;overflow:hidden">
      <div style="height:100%;width:${barW}%;background:${color};border-radius:2px"></div>
    </div>
  </div>`;
}

async function loadCentroid() {
  const d = await api('/anomaly/centroid', { ttl: 30000 });
  const f = d.funnel;
  const totalBs = f.total.bs;
  const totalRec = f.total.records;

  // 从 candidates 数组提取各分类
  const catMap = {};
  (f.candidates || []).forEach(c => { catMap[c.category] = c; });
  const getCat = (k) => catMap[k] || { bs: 0, records: 0, avg_devices: 0, avg_cell_span: 0 };

  // 需拆分合计
  const splitBs = getCat('collision_confirmed').bs + getCat('collision_suspected').bs;
  const splitRec = Number(getCat('collision_confirmed').records) + Number(getCat('collision_suspected').records);

  // 异常候选总计
  const candTotal = f.candidates.reduce((s, c) => s + c.bs, 0);
  const candRecTotal = f.candidates.reduce((s, c) => s + Number(c.records), 0);

  return `
    ${renderTabNav()}

    <div class="page-head">
      <div>
        <h2>质心分析 — Cell 质心法</h2>
        <p>对每个 Cell 独立计算质心和空间跨度，再按 BS 级 Cell 质心间距分类。算法不受 GPS 飘点影响。</p>
      </div>
    </div>

    <!-- 核心指标 -->
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-label">全部 BS</div>
        <div class="stat-value blue">${fmt(totalBs)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">数据不足（过滤）</div>
        <div class="stat-value" style="color:#9ca3af">${fmt(f.insufficient.bs)}</div>
        <div style="font-size:12px;color:var(--text-dim)">${(f.insufficient.bs / totalBs * 100).toFixed(1)}%</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">正常 BS</div>
        <div class="stat-value green">${fmt(f.normal.bs)}</div>
        <div style="font-size:12px;color:var(--text-dim)">${(f.normal.bs / totalBs * 100).toFixed(1)}%</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">确认碰撞（需拆分）</div>
        <div class="stat-value red">${fmt(splitBs)}</div>
        <div style="font-size:12px;color:var(--text-dim)">${fmt(splitRec)} 条 (${(Number(splitRec) / Number(totalRec) * 100).toFixed(1)}%)</div>
      </div>
    </div>

    <!-- 漏斗 -->
    <div class="card">
      <div class="card-title"><h3>分析漏斗</h3></div>

      ${funnelStep(0, '全部 BS', totalBs, Number(totalRec), totalBs, Number(totalRec), '#2563eb', `${fmt(totalRec)} 条上报记录`)}

      ${funnelStep(1, '① 数据不足（过滤）', f.insufficient.bs, Number(f.insufficient.records), totalBs, Number(totalRec), '#9ca3af', '无GPS + 低样本(≤3) + 单设备')}

      ${funnelStep(1, '② 正常 BS', f.normal.bs, Number(f.normal.records), totalBs, Number(totalRec), 'var(--green)', '空间不异常，直接进入 Phase 4')}

      ${funnelStep(1, '③ 异常候选（Cell 质心分析）', candTotal, candRecTotal, totalBs, Number(totalRec), 'var(--orange)', 'GPS≥10, 设备≥2, 空间散布异常 → 逐Cell计算质心')}

      ${funnelStep(2, '动态BS（含移动Cell）', getCat('dynamic_bs').bs, Number(getCat('dynamic_bs').records), totalBs, Number(totalRec), '#7c3aed', 'Cell跨度>1.5km → 高铁/车载/移动基站')}

      ${funnelStep(2, 'Cell质心重合（GPS噪声）', getCat('normal_spread').bs, Number(getCat('normal_spread').records), totalBs, Number(totalRec), 'var(--green)', '固定Cell质心间距<500m → BS位置正常')}

      ${funnelStep(2, 'Cell质心较近（面积大）', getCat('single_large').bs, Number(getCat('single_large').records), totalBs, Number(totalRec), '#2563eb', '固定Cell质心间距500-1500m → 标记精度低')}

      ${funnelStep(2, '确认碰撞（需拆分）', getCat('collision_confirmed').bs, Number(getCat('collision_confirmed').records), totalBs, Number(totalRec), 'var(--red)', '固定Cell质心>1.5km + 设备交叉率<5%')}

      ${funnelStep(2, '疑似碰撞（需拆分）', getCat('collision_suspected').bs, Number(getCat('collision_suspected').records), totalBs, Number(totalRec), 'var(--orange)', '固定Cell质心>1.5km + 设备交叉率5-20%')}

      ${getCat('collision_uncertain').bs > 0 ? funnelStep(2, '碰撞不确定', getCat('collision_uncertain').bs, Number(getCat('collision_uncertain').records), totalBs, Number(totalRec), '#9ca3af', '设备交叉率>20%') : ''}

      <div style="margin-top:16px;padding:10px 14px;border-left:3px solid var(--red);background:#fef2f2;border-radius:0 6px 6px 0">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <span style="font-weight:700;color:var(--red)">★ 需拆分处理合计</span>
          <span><span style="font-weight:700;color:var(--red);font-size:16px">${fmt(splitBs)}</span>
          <span style="font-size:12px;color:var(--text-dim);margin-left:4px">BS (${(splitBs / totalBs * 100).toFixed(1)}%)</span>
          <span style="font-size:12px;color:var(--text-dim);margin-left:12px">${fmt(splitRec)} 条 (${(Number(splitRec) / Number(totalRec) * 100).toFixed(1)}%)</span></span>
        </div>
      </div>
    </div>

    <!-- 需拆分：分类汇总表 -->
    <div class="card">
      <div class="card-title"><h3>需拆分 BS 汇总</h3></div>
      ${renderTable(
        [
          { key: 'category', label: '分类', render: v => catTag(v) },
          { key: 'bs', label: 'BS 数', className: 'num', render: v => fmt(v) },
          { key: 'pct', label: '占比', render: (_, r) => pctBar(r.bs, splitBs, (CAT_META[r.category]||{}).color || '#ccc') },
          { key: 'records', label: '记录数', className: 'num', render: v => fmt(v) },
          { key: 'avg_devices', label: '均设备数', className: 'num', render: v => fmt(v) },
          { key: 'avg_cell_span', label: '均Cell跨度(m)', className: 'num', render: v => v ? fmt(v) : '—' },
        ],
        [getCat('collision_confirmed'), getCat('collision_suspected')].filter(r => r.bs > 0)
      )}
    </div>

    <!-- 确认碰撞 TOP -->
    <div class="card">
      <div class="card-title">
        <h3>确认碰撞 TOP 50</h3>
        <span class="tag tag-red">${fmt(getCat('collision_confirmed').bs)} 个 BS</span>
      </div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
        固定Cell 质心间距>1.5km + 设备交叉率<5% → 确认碰撞。Phase 4 按 Cell 空间聚类拆分。
      </p>
      ${renderTable(
        [
          { key: 'operator_code', label: '运营商' },
          { key: 'tech_norm', label: '制式' },
          { key: 'lac', label: 'LAC' },
          { key: 'bs_id', label: 'BS ID', className: 'num' },
          { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
          { key: 'distinct_gps_devices', label: '设备数', className: 'num', render: v => fmt(v) },
          { key: 'cell_span', label: 'Cell跨度(m)', className: 'num', render: v => fmt(v) },
          { key: 'static_cells', label: '固定Cell', className: 'num', render: v => fmt(v) },
          { key: 'dynamic_cells', label: '动态Cell', className: 'num', render: v => fmt(v) },
          { key: 'cross_pct', label: '交叉率%', className: 'num', render: v => v != null ? v + '%' : '—' },
        ],
        d.collision
      )}
    </div>

    <!-- 疑似碰撞 TOP -->
    ${d.suspected && d.suspected.length > 0 ? `
    <div class="card">
      <div class="card-title">
        <h3>疑似碰撞 TOP 50</h3>
        <span class="tag tag-orange">${fmt(getCat('collision_suspected').bs)} 个 BS</span>
      </div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
        固定Cell 质心间距>1.5km + 设备交叉率5-20%。
      </p>
      ${renderTable(
        [
          { key: 'operator_code', label: '运营商' },
          { key: 'tech_norm', label: '制式' },
          { key: 'lac', label: 'LAC' },
          { key: 'bs_id', label: 'BS ID', className: 'num' },
          { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
          { key: 'distinct_gps_devices', label: '设备数', className: 'num', render: v => fmt(v) },
          { key: 'cell_span', label: 'Cell跨度(m)', className: 'num', render: v => fmt(v) },
          { key: 'static_cells', label: '固定Cell', className: 'num' },
          { key: 'cross_pct', label: '交叉率%', className: 'num', render: v => v != null ? v + '%' : '—' },
        ],
        d.suspected
      )}
    </div>` : ''}

    <!-- 面积大 TOP -->
    <div class="card">
      <div class="card-title">
        <h3>Cell质心较近 · 面积大 TOP 50</h3>
        <span class="tag tag-blue">${fmt(getCat('single_large').bs)} 个 BS</span>
      </div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
        固定Cell 质心间距500-1500m，非碰撞但覆盖范围较大。
      </p>
      ${renderTable(
        [
          { key: 'operator_code', label: '运营商' },
          { key: 'tech_norm', label: '制式' },
          { key: 'lac', label: 'LAC' },
          { key: 'bs_id', label: 'BS ID', className: 'num' },
          { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
          { key: 'distinct_gps_devices', label: '设备数', className: 'num', render: v => fmt(v) },
          { key: 'p90_dist', label: 'P90(m)', className: 'num', render: v => fmt(v) },
          { key: 'cell_span', label: 'Cell跨度(m)', className: 'num', render: v => fmt(v) },
          { key: 'static_cells', label: '固定Cell', className: 'num' },
          { key: 'dynamic_cells', label: '动态Cell', className: 'num' },
        ],
        d.large_area
      )}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
//  入口
// ════════════════════════════════════════════════════════════

export async function loadAnomaly(force = false) {
  try {
    let html;
    switch (currentTab) {
      case 'overview': html = await loadOverview(); break;
      case 'centroid': html = await loadCentroid(); break;
      default: html = await loadOverview();
    }
    setMain(html);
  } catch (e) {
    setMain(pageError('问题数据加载失败', e));
  }
}
