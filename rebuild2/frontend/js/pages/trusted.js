/**
 * L2 可信库：LAC / Cell / 综合 三个子页面。
 *
 * 可信 LAC 过滤规则：
 *   以移动日均 3500 为基准，按各运营商+制式上报量占比等比换算门槛
 *   广电全量保留，排除哨兵 LAC，active_days = 7
 */

import { api } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, showToast, renderTable,
} from '../ui/common.js';

let currentStep = 'lac';
let currentTab = 'stats';

function switchStep(step) { currentStep = step; currentTab = 'stats'; loadTrusted(true); }
function switchTab(tab) { currentTab = tab; loadTrusted(true); }
window.switchTrustedStep = switchStep;
window.switchTrustedTab = switchTab;

function techTag(t) {
  const m = { '5G': 'tag-blue', '4G': 'tag-green' };
  return `<span class="tag ${m[t] || 'tag-gray'}">${escapeHtml(t)}</span>`;
}
function operatorTag(op) {
  const m = { '移动': 'tag-blue', '联通': 'tag-red', '电信': 'tag-green', '广电': 'tag-orange' };
  return `<span class="tag ${m[op] || 'tag-gray'}">${escapeHtml(op)}</span>`;
}

// ════════════════════════════════════════════════════════════
//  LAC — 统计预览
// ════════════════════════════════════════════════════════════

async function loadLacStats() {
  const data = await api('/trusted/lac/stats', { ttl: 10000, force: true });
  const f = data.funnel || {};
  const cmp = data.comparison || {};
  const thresholds = data.thresholds || {};

  return `
    ${renderStepNav()}
    ${renderLacTabs()}

    <div class="card">
      <div class="card-title"><h3>过滤漏斗</h3></div>
      ${renderTable([
        { key: 'step', label: '步骤' },
        { key: 'remain', label: '剩余', className: 'num', render: v => `<b>${fmt(v)}</b>` },
        { key: 'filtered', label: '淘汰', className: 'num', render: v => v > 0 ? `<span style="color:var(--red)">-${fmt(v)}</span>` : '—' },
        { key: 'desc', label: '说明', render: v => `<span style="font-size:12px;color:var(--text-dim)">${escapeHtml(v)}</span>` },
      ], [
        { step: '① 全量 LAC (4G+5G, 四运营商)', remain: f.total, filtered: 0, desc: '' },
        { step: '② active_days = 7', remain: f.days7, filtered: f.total - f.days7, desc: '7天满窗口' },
        { step: '③ LAC ID 合规性', remain: f.days7 - (f.compliance_filtered||0), filtered: f.compliance_filtered||0, desc: '4G: 256~65533 (16bit)  5G: 256~16777213 (24bit)' },
        { step: '④ 日均上报量门槛（占比换算）', remain: data.trusted_count, filtered: f.threshold_filtered||0, desc: '移动基准 ' + fmt(data.cmcc_base_daily) + '/天，按占比换算' },
      ])}
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">移动基准(日均)</div><div class="stat-value blue">${fmt(data.cmcc_base_daily)}</div></div>
      <div class="stat-box"><div class="stat-label">最终可信 LAC</div><div class="stat-value green">${fmt(data.trusted_count)}</div></div>
      <div class="stat-box"><div class="stat-label">上轮可信 LAC</div><div class="stat-value">${fmt(cmp.legacy)}</div></div>
      <div class="stat-box"><div class="stat-label">重叠</div><div class="stat-value">${fmt(cmp.overlap)}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>门槛规则</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>LAC ID 合规性</b>：4G TAC 有效范围 256~65533 (16bit)，5G TAC 有效范围 256~16777213 (24bit)，排除保留值(0~255)和溢出值(0xFFFE/0xFFFF/INT_MAX)<br>
        <b>日均门槛</b>：以移动日均 ${fmt(data.cmcc_base_daily)} 条为基准，按各运营商+制式的总上报量占比等比换算：
      </div>
      ${renderTable([
        { key: 'group', label: '运营商+制式' },
        { key: 'ratio', label: '占比', className: 'num' },
        { key: 'threshold', label: '日均门槛', className: 'num', render: v => v === 0 ? '<span style="color:var(--text-dim)">全量保留</span>' : fmt(v) },
        { key: 'total7', label: '7天门槛', className: 'num', render: v => v === 0 ? '—' : fmt(v) },
      ], buildThresholdRows(thresholds, data.cmcc_base_daily))}
    </div>

    <div class="card">
      <div class="card-title"><h3>可信 LAC 按运营商+制式</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac_count', label: 'LAC 数', className: 'num', render: v => fmt(v) },
        { key: 'total_records', label: '总记录数', className: 'num', render: v => fmt(v) },
        { key: 'threshold', label: '日均门槛', className: 'num', render: v => v === 0 ? '全量' : fmt(v) },
        { key: 'min_daily_avg', label: '最小日均', className: 'num', render: v => fmt(v) },
      ], data.by_group || [])}
    </div>

    ${renderComparison(data)}

    <div class="card">
      <div class="card-title">
        <h3>可信 LAC 明细（前 30 条）</h3>
        <span class="card-subtitle">共 ${fmt(data.trusted_count)} 条，按总上报量降序</span>
      </div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: 'LAC' },
        { key: 'total_records', label: '总上报', className: 'num', render: v => fmt(v) },
        { key: 'avg_daily_records', label: '日均上报', className: 'num', render: v => fmt(v) },
        { key: 'min_daily_records', label: '最低日', className: 'num', render: v => fmt(v) },
        { key: 'avg_daily_devices', label: '日均设备', className: 'num', render: v => fmt(v) },
        { key: 'cv', label: 'CV', className: 'num', render: v => v != null ? Number(v).toFixed(3) : '—' },
        { key: 'avg_daily_cells', label: '日均Cell', className: 'num', render: v => fmt(v) },
      ], (data.items || []).slice(0, 30))}
    </div>

    <div style="margin-top:16px;text-align:center">
      <button class="btn btn-primary" style="min-width:240px;padding:10px 24px" onclick="buildTrustedLac()">
        确认规则，构建 dim_lac_trusted
      </button>
    </div>
  `;
}

function buildThresholdRows(thresholds, base) {
  const ratios = { '46000|4G': 1.0, '46000|5G': 1.0, '46001|4G': 0.584, '46001|5G': 0.553, '46011|4G': 0.325, '46011|5G': 0.230 };
  const names = { '46000': '移动', '46001': '联通', '46011': '电信', '46015': '广电' };
  const rows = [];
  for (const [key, ratio] of Object.entries(ratios)) {
    const [op, tech] = key.split('|');
    const t = thresholds[key] || Math.round(base * ratio);
    rows.push({ group: `${names[op]} ${tech}`, ratio: (ratio * 100).toFixed(1) + '%', threshold: t, total7: t * 7 });
  }
  rows.push({ group: '广电 4G/5G', ratio: '—', threshold: 0, total7: 0 });
  return rows;
}

function renderComparison(data) {
  const cmp = data.comparison || {};
  const legacy = data.legacy_groups || [];
  const current = data.by_group || [];

  const map = {};
  for (const g of legacy) {
    const key = `${g.operator_code}|${g.tech_norm}`;
    map[key] = { operator_code: g.operator_code, tech_norm: g.tech_norm, legacy_lac: g.lac_count };
  }
  for (const g of current) {
    const key = `${g.operator_code}|${g.tech_norm}`;
    if (!map[key]) map[key] = { operator_code: g.operator_code, tech_norm: g.tech_norm };
    map[key].current_lac = g.lac_count;
    map[key].operator_cn = g.operator_cn;
  }
  const rows = Object.values(map).sort((a, b) => (b.current_lac || 0) - (a.current_lac || 0));

  return `
    <div class="card">
      <div class="card-title"><h3>与上一轮对比</h3></div>
      <div class="stat-grid" style="margin-bottom:12px">
        <div class="stat-box"><div class="stat-label">当前</div><div class="stat-value blue">${fmt(cmp.current)}</div></div>
        <div class="stat-box"><div class="stat-label">上轮</div><div class="stat-value">${fmt(cmp.legacy)}</div></div>
        <div class="stat-box"><div class="stat-label">重叠</div><div class="stat-value green">${fmt(cmp.overlap)}</div></div>
        <div class="stat-box"><div class="stat-label">仅当前</div><div class="stat-value blue">${fmt(cmp.only_current)}</div></div>
        <div class="stat-box"><div class="stat-label">仅上轮</div><div class="stat-value orange">${fmt(cmp.only_legacy)}</div></div>
      </div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: (v, r) => operatorTag(v || r.operator_code) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'legacy_lac', label: '上轮', className: 'num', render: v => fmt(v) },
        { key: 'current_lac', label: '当前', className: 'num', render: v => fmt(v) },
        { key: 'diff', label: '差异', className: 'num', render: (_, r) => {
          const d = (r.current_lac || 0) - (r.legacy_lac || 0);
          const color = d > 0 ? 'var(--green)' : d < 0 ? 'var(--red)' : 'var(--text-dim)';
          return `<span style="color:${color};font-weight:600">${d > 0 ? '+' : ''}${d}</span>`;
        }},
      ], rows)}
    </div>
  `;
}

window.buildTrustedLac = async function () {
  if (!confirm('确认构建 dim_lac_trusted？已有表将被重建。')) return;
  const btn = document.querySelector('button[onclick="buildTrustedLac()"]');
  if (btn) { btn.disabled = true; btn.textContent = '构建中...'; }
  try {
    const result = await api('/trusted/lac/build', { method: 'POST', force: true });
    if (result.ok) {
      showToast(`构建完成：${result.trusted_lac_count} 个可信 LAC`);
      switchTab('built');
    } else {
      showToast('构建失败: ' + (result.error || ''));
    }
  } catch (e) {
    showToast('构建失败: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '确认规则，构建 dim_lac_trusted'; }
  }
};

// ════════════════════════════════════════════════════════════
//  LAC — 已构建
// ════════════════════════════════════════════════════════════

async function loadLacBuilt() {
  const data = await api('/trusted/lac/built', { ttl: 5000, force: true });
  if (!data.exists) {
    return `${renderStepNav()}${renderLacTabs()}
      <div class="card"><div class="empty-state">尚未构建，请先在"统计预览"确认后构建</div></div>`;
  }
  return `
    ${renderStepNav()}
    ${renderLacTabs()}
    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">可信 LAC 总数</div><div class="stat-value green">${fmt(data.count)}</div></div>
    </div>
    <div class="card">
      <div class="card-title"><h3>按运营商+制式</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac_count', label: 'LAC 数', className: 'num', render: v => fmt(v) },
        { key: 'total_records', label: '总记录', className: 'num', render: v => fmt(v) },
      ], data.by_group || [])}
    </div>
    <div class="card">
      <div class="card-title"><h3>明细（前 30 条）</h3><span class="card-subtitle">共 ${fmt(data.count)} 条</span></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: 'LAC' },
        { key: 'record_count', label: '总上报', className: 'num', render: v => fmt(v) },
        { key: 'avg_daily_records', label: '日均上报', className: 'num', render: v => fmt(v) },
        { key: 'avg_daily_devices', label: '日均设备', className: 'num', render: v => fmt(v) },
        { key: 'cv', label: 'CV', className: 'num', render: v => v != null ? Number(v).toFixed(3) : '—' },
      ], (data.items || []).slice(0, 30))}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
//  Cell Step
// ════════════════════════════════════════════════════════════

async function loadCellStep() {
  const data = await api('/trusted/cell/stats', { ttl: 10000, force: true });
  if (!data.exists) {
    return `${renderStepNav()}<div class="card"><div class="empty-state">dim_cell_stats 尚未构建。请先通过 SSH 执行聚合。</div></div>`;
  }

  const legacy = data.legacy_groups || [];
  const current = data.by_group || [];
  const map = {};
  for (const g of legacy) {
    const key = `${g.operator_code}|${g.tech_norm}`;
    map[key] = { tech_norm: g.tech_norm, legacy_cells: g.cell_count };
  }
  for (const g of current) {
    const key = `${g.operator_cn === '移动' ? '46000' : g.operator_cn === '联通' ? '46001' : g.operator_cn === '电信' ? '46011' : '46015'}|${g.tech_norm}`;
    if (!map[key]) map[key] = { tech_norm: g.tech_norm };
    Object.assign(map[key], { operator_cn: g.operator_cn, current_cells: g.cell_count, current_bs: g.bs_count, current_records: g.total_records, cells_7day: g.cells_7day, cells_with_gps: g.cells_with_gps });
  }
  const cmpRows = Object.values(map).sort((a, b) => (b.current_records || 0) - (a.current_records || 0));

  return `
    ${renderStepNav()}

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">Cell 总数</div><div class="stat-value blue">${fmt(data.total_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">BS 总数</div><div class="stat-value green">${fmt(data.total_bs)}</div></div>
      <div class="stat-box"><div class="stat-label">总记录数</div><div class="stat-value">${fmt(data.total_records)}</div></div>
      <div class="stat-box"><div class="stat-label">7天满覆盖 Cell</div><div class="stat-value">${fmt(data.cells_7day)}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>合规规则</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>数据源</b>：l0_lac JOIN dim_lac_trusted（可信 LAC 范围内）<br>
        <b>CellID 合规</b>：4G ECI 有效 1~268435455 (28bit)，5G NCI 有效 1~68719476735 (36bit)<br>
        <b>聚合维度</b>：(运营商, 制式, LAC, CellID)，含 GPS 中心点（中位数）
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>按运营商+制式</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'cell_count', label: 'Cell 数', className: 'num', render: v => fmt(v) },
        { key: 'bs_count', label: 'BS 数', className: 'num', render: v => fmt(v) },
        { key: 'total_records', label: '总记录', className: 'num', render: v => fmt(v) },
        { key: 'cells_7day', label: '7天Cell', className: 'num', render: v => fmt(v) },
        { key: 'cells_with_gps', label: '有GPS', className: 'num', render: v => fmt(v) },
        { key: 'avg_records', label: '平均记录/Cell', className: 'num', render: v => fmt(v) },
      ], data.by_group || [])}
    </div>

    <div class="card">
      <div class="card-title"><h3>与上一轮对比</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v || '—') },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'legacy_cells', label: '上轮 Cell', className: 'num', render: v => fmt(v) },
        { key: 'current_cells', label: '当前 Cell', className: 'num', render: v => fmt(v) },
        { key: 'current_bs', label: '当前 BS', className: 'num', render: v => fmt(v) },
      ], cmpRows)}
    </div>

    <div class="card">
      <div class="card-title"><h3>Cell 明细 Top 30</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: 'LAC' },
        { key: 'cell_id', label: 'CellID', render: v => String(v) },
        { key: 'bs_id', label: 'BS ID', render: v => String(v) },
        { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
        { key: 'distinct_device_count', label: '设备数', className: 'num', render: v => fmt(v) },
        { key: 'active_days', label: '活跃天', className: 'num' },
        { key: 'gps_center_lon', label: '经度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
        { key: 'gps_center_lat', label: '纬度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
      ], data.items || [])}
    </div>

    <div style="margin-top:16px;text-align:center">
      <button class="btn btn-primary" style="min-width:200px;padding:10px 24px" onclick="buildBsStats()">
        从 Cell 聚合生成 BS 统计表
      </button>
    </div>
  `;
}

window.buildBsStats = async function () {
  if (!confirm('确认从 dim_cell_stats 聚合生成 dim_bs_stats？')) return;
  try {
    const result = await api('/trusted/bs/build', { method: 'POST', force: true });
    if (result.ok) {
      showToast(`BS 构建完成：${fmt(result.total_bs)} 个 BS`);
      switchStep('overview');
    } else {
      showToast('构建失败: ' + (result.error || ''));
    }
  } catch (e) {
    showToast('构建失败: ' + e.message);
  }
};

// ════════════════════════════════════════════════════════════
//  综合 (BS + 汇总)
// ════════════════════════════════════════════════════════════

async function loadOverviewStep() {
  const [bs, summary] = await Promise.all([
    api('/trusted/bs/stats', { ttl: 10000, force: true }),
    api('/trusted/summary', { ttl: 10000, force: true }),
  ]);

  const layers = summary.layers || {};

  const summaryContent = `
    <div class="card">
      <div class="card-title"><h3>Phase 2 各层级汇总</h3></div>
      ${renderTable([
        { key: 'layer', label: '层级' },
        { key: 'count', label: '行数', className: 'num', render: v => fmt(v) },
      ], [
        { layer: 'L0 GPS 源表 (l0_gps)', count: layers.l0_gps },
        { layer: 'L0 LAC 源表 (l0_lac)', count: layers.l0_lac },
        { layer: '可信 LAC (dim_lac_trusted)', count: layers.dim_lac_trusted },
        { layer: '可信 Cell (dim_cell_stats)', count: layers.dim_cell_stats },
        { layer: 'Cell 推算 BS 去重数', count: layers.distinct_bs_from_cells },
        { layer: 'BS 聚合表 (dim_bs_stats)', count: layers.dim_bs_stats },
      ])}
    </div>
  `;

  if (!bs.exists) {
    return `${renderStepNav()}${summaryContent}
      <div class="card"><div class="empty-state">dim_bs_stats 尚未构建，请先在 Cell 页面点击构建</div></div>`;
  }

  return `
    ${renderStepNav()}
    ${summaryContent}

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">BS 总数</div><div class="stat-value blue">${fmt(bs.total_bs)}</div></div>
      <div class="stat-box"><div class="stat-label">Cell 总数</div><div class="stat-value">${fmt(bs.total_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">总记录</div><div class="stat-value">${fmt(bs.total_records)}</div></div>
      <div class="stat-box"><div class="stat-label">上轮 BS 数</div><div class="stat-value">${fmt(bs.legacy_bs_count)}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>BS 按运营商+制式</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'bs_count', label: 'BS 数', className: 'num', render: v => fmt(v) },
        { key: 'cell_count', label: 'Cell 数', className: 'num', render: v => fmt(v) },
        { key: 'total_records', label: '总记录', className: 'num', render: v => fmt(v) },
        { key: 'avg_cells_per_bs', label: '平均Cell/BS', className: 'num' },
      ], bs.by_group || [])}
    </div>

    <div class="card">
      <div class="card-title"><h3>BS 明细 Top 30</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: 'LAC' },
        { key: 'bs_id', label: 'BS ID', render: v => String(v) },
        { key: 'cell_count', label: 'Cell 数', className: 'num', render: v => fmt(v) },
        { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
        { key: 'gps_center_lon', label: '经度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
        { key: 'gps_center_lat', label: '纬度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
      ], bs.items || [])}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
//  导航
// ════════════════════════════════════════════════════════════

function renderStepNav() {
  return `<div class="toolbar" style="margin-bottom:16px;gap:4px">
    <button class="btn ${currentStep === 'lac' ? 'btn-primary' : 'btn-ghost'}" onclick="switchTrustedStep('lac')">Step 1: 可信 LAC</button>
    <button class="btn ${currentStep === 'cell' ? 'btn-primary' : 'btn-ghost'}" onclick="switchTrustedStep('cell')">Step 2: 可信 Cell</button>
    <button class="btn ${currentStep === 'overview' ? 'btn-primary' : 'btn-ghost'}" onclick="switchTrustedStep('overview')">Step 3: 综合(BS)</button>
  </div>`;
}
function renderLacTabs() {
  return `<div class="toolbar" style="margin-bottom:12px;gap:4px">
    <button class="btn btn-sm ${currentTab === 'stats' ? 'btn-primary' : 'btn-ghost'}" onclick="switchTrustedTab('stats')">统计预览</button>
    <button class="btn btn-sm ${currentTab === 'built' ? 'btn-primary' : 'btn-ghost'}" onclick="switchTrustedTab('built')">已构建</button>
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  入口
// ════════════════════════════════════════════════════════════

export async function loadTrusted(force = false) {
  setMain('<div class="loading">加载可信库构建...</div>');
  try {
    let content;
    switch (currentStep) {
      case 'lac':
        content = currentTab === 'built' ? await loadLacBuilt() : await loadLacStats();
        break;
      case 'cell': content = await loadCellStep(); break;
      case 'overview': content = await loadOverviewStep(); break;
      default: content = await loadLacStats();
    }
    setMain(`
      <div class="page-head"><div>
        <h2>L2 可信库构建</h2>
        <p>LAC → Cell → BS 层层收敛，从 l0_gps（3843 万行）构建可信基站库。</p>
      </div></div>
      ${content}
    `);
  } catch (error) {
    setMain(pageError('可信库加载失败', error));
  }
}
