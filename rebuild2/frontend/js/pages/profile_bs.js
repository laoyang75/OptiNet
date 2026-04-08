/**
 * L4 BS 画像：样本评估。
 */

import { api, qs } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, renderTable, openDrawer,
} from '../ui/common.js';

let currentTab = 'bs-profile';
let filters = {};
let sortBy = 'total_records';
let sortDir = 'desc';
let page = 0;
const PAGE_SIZE = 50;

function switchTab(tab) { currentTab = tab; loadProfileBs(true); }
window.switchProfileBsTab = switchTab;

// ── 运营商 / 制式标签 ──

const OP_MAP = {
  '46000': ['中国移动', 'tag-blue'],
  '46001': ['中国联通', 'tag-red'],
  '46011': ['中国电信', 'tag-green'],
  '46015': ['中国广电', 'tag-gray'],
};
function opTag(code) {
  const [label, cls] = OP_MAP[code] || [code, 'tag-gray'];
  return `<span class="tag ${cls}">${label}</span>`;
}
function techTag(t) {
  return t === '5G' ? '<span class="tag tag-blue">5G</span>' : '<span class="tag tag-gray">4G</span>';
}

// ── 百分比条 ──

function pctBar(ratio, color = 'var(--blue)') {
  const p = (ratio || 0) * 100;
  return `<div style="display:flex;align-items:center;gap:8px">
    <div style="flex:1;height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">
      <div style="height:100%;width:${Math.min(p, 100)}%;background:${color};border-radius:3px"></div>
    </div>
    <span style="font-size:12px;color:var(--text-dim);min-width:44px;text-align:right">${p.toFixed(1)}%</span>
  </div>`;
}

// ── 可信度标签 ──

function confidenceTag(level) {
  const map = {
    high: ['tag-green', '高'],
    medium: ['tag-orange', '中'],
    low: ['tag-red', '低'],
    none: ['tag-gray', '无'],
  };
  const [cls, label] = map[level] || ['tag-gray', level || '—'];
  return `<span class="tag ${cls}">${label}</span>`;
}

// ── 异常分类标签 ──

function classificationTag(cls) {
  if (!cls) return '<span style="color:var(--text-dim)">正常</span>';
  const map = {
    dynamic_bs: ['tag-purple', '动态BS'],
    collision_confirmed: ['tag-red', '确认碰撞'],
    collision_suspected: ['tag-orange', '疑似碰撞'],
    single_large: ['tag-blue', '面积大'],
    normal_spread: ['tag-green', 'GPS噪声'],
    collision_uncertain: ['tag-gray', '不确定'],
  };
  const [tagCls, label] = map[cls] || ['tag-gray', cls];
  return `<span class="tag ${tagCls}">${label}</span>`;
}

// ── 柱状图 ──

function barChart(data, { valueKey, labelKey = 'hour_of_day', height = 120, color = 'var(--blue)' }) {
  const vals = data.map(d => Number(d[valueKey]) || 0);
  const max = Math.max(...vals, 1);
  return `<div style="display:flex;align-items:flex-end;gap:1px;height:${height}px;padding:4px 0">
    ${data.map(d => {
      const v = Number(d[valueKey]) || 0;
      const h = max > 0 ? Math.max(v / max * height, 1) : 1;
      const label = d[labelKey];
      const tipVal = typeof v === 'number' && v % 1 !== 0 ? v.toFixed(1) : fmt(v);
      return `<div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:0" title="${label}:00 → ${tipVal}">
        <div style="width:100%;max-width:20px;height:${h}px;background:${typeof color === 'function' ? color(d) : color};border-radius:2px 2px 0 0"></div>
        ${data.length <= 24 ? `<span style="font-size:9px;color:var(--text-dim);margin-top:2px">${label}</span>` : ''}
      </div>`;
    }).join('')}
  </div>`;
}

// ── Tab 导航 ──

function renderTabNav() {
  const tabs = [
    { key: 'bs-profile', label: 'BS 画像' },
    { key: 'bs-overview', label: 'BS 总览', disabled: true },
  ];
  return `<div class="toolbar" style="margin-bottom:16px;gap:4px">
    ${tabs.map(t => `<button class="btn ${currentTab === t.key ? 'btn-primary' : 'btn-ghost'}"
      onclick="switchProfileBsTab('${t.key}')"
      ${t.disabled ? 'disabled style="opacity:0.5"' : ''}
    >${t.label}</button>`).join('')}
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  BS 详情（抽屉）
// ════════════════════════════════════════════════════════════

window.openBsDetail = async function(op, tech, lac, bsId, bsDataJson) {
  const bs = JSON.parse(decodeURIComponent(bsDataJson));
  openDrawer({
    title: `BS ${bsId}`,
    kicker: `${OP_MAP[op]?.[0] || op} · ${tech} · LAC ${lac}`,
    body: '<div class="loading">加载中...</div>',
  });

  try {
    const params = qs({ operator_code: op, tech_norm: tech, lac, bs_id: bsId });
    const [hRes, dRes] = await Promise.all([
      api(`/profile/bs/sample/hourly${params}`, { ttl: 60000 }),
      api(`/profile/bs/sample/daily${params}`, { ttl: 60000 }),
    ]);
    const hourly = hRes.hourly || [];
    const daily = dRes.daily || [];

    document.getElementById('drawer-body').innerHTML = `
      <!-- 位置 + 基本信息 -->
      ${bs.province_name ? `<div style="margin-bottom:12px;padding:8px 14px;background:var(--bg);border-radius:6px;font-size:13px">
        <span style="color:var(--text-dim)">位置：</span><b>${bs.province_name} ${bs.city_name} ${bs.district_name || ''}</b>
      </div>` : ''}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;font-size:13px">
        <div style="background:var(--bg);padding:10px;border-radius:6px">
          <div style="color:var(--text-dim)">GPS 中心点</div>
          <div style="font-weight:500">${bs.center_lon ?? '—'}, ${bs.center_lat ?? '—'}</div>
        </div>
        <div style="background:var(--bg);padding:10px;border-radius:6px">
          <div style="color:var(--text-dim)">覆盖面积</div>
          <div style="font-weight:500">${bs.area_km2 ?? '—'} km²</div>
        </div>
      </div>

      <!-- 空间指标 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">空间精度</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:13px">
          <div><span style="color:var(--text-dim)">P50 距离</span><br><b>${fmt(bs.gps_p50_dist_m)} m</b></div>
          <div><span style="color:var(--text-dim)">P90 距离</span><br><b>${fmt(bs.gps_p90_dist_m)} m</b></div>
          <div><span style="color:var(--text-dim)">最大距离</span><br><b>${fmt(bs.gps_max_dist_m)} m</b></div>
        </div>
      </div>

      <!-- 分类 & 可信度 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">分类与可信度</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:13px">
          <div><span style="color:var(--text-dim)">异常分类</span><br>${classificationTag(bs.classification_v2)}</div>
          <div><span style="color:var(--text-dim)">GPS 可信度</span><br>${confidenceTag(bs.gps_confidence)}</div>
          <div><span style="color:var(--text-dim)">信号可信度</span><br>${confidenceTag(bs.signal_confidence)}</div>
        </div>
        ${bs.classification_v2 ? `<div style="font-size:12px;color:var(--text-dim);margin-top:6px">
          Cell 质心跨度 ${fmt(bs.static_cell_span_m)} m · 静态Cell ${bs.static_cells_cnt} · 动态Cell ${bs.dynamic_cells_cnt}
          ${bs.device_cross_rate != null ? ` · 设备交叉率 ${(bs.device_cross_rate * 100).toFixed(1)}%` : ''}
        </div>` : ''}
      </div>

      <!-- GPS 补齐构成 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">GPS 来源构成</div>
        <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;margin-bottom:6px">
          ${[
            { cnt: bs.gps_original_cnt, color: 'var(--green)', label: '原始' },
            { cnt: bs.gps_valid_cnt - bs.gps_original_cnt, color: 'var(--orange)', label: '补齐' },
          ].map(s => {
            const w = bs.total_records > 0 ? (Math.max(s.cnt, 0) / bs.total_records * 100) : 0;
            return w > 0 ? `<div style="width:${w}%;background:${s.color}" title="${s.label}: ${fmt(s.cnt)} (${w.toFixed(1)}%)"></div>` : '';
          }).join('')}
        </div>
        <div style="font-size:12px;color:var(--text-dim)">
          原始 ${fmt(bs.gps_original_cnt)} (${((bs.gps_original_ratio || 0) * 100).toFixed(1)}%)
          · 有效 ${fmt(bs.gps_valid_cnt)} (${((bs.gps_valid_ratio || 0) * 100).toFixed(1)}%)
        </div>
      </div>

      <!-- 信号信息 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">信号质量</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:13px">
          <div><span style="color:var(--text-dim)">RSRP 均值</span><br><b>${bs.rsrp_avg != null ? bs.rsrp_avg + ' dBm' : '—'}</b></div>
          <div><span style="color:var(--text-dim)">RSRQ 均值</span><br><b>${bs.rsrq_avg != null ? bs.rsrq_avg + ' dB' : '—'}</b></div>
          <div><span style="color:var(--text-dim)">SINR 均值</span><br><b>${bs.sinr_avg != null ? bs.sinr_avg + ' dB' : '—'}</b></div>
        </div>
        <div style="font-size:12px;color:var(--text-dim);margin-top:6px">
          信号原始率 ${((bs.signal_original_ratio || 0) * 100).toFixed(1)}%
        </div>
      </div>

      <!-- 24 小时记录量 -->
      <div style="margin-bottom:20px">
        <div style="font-weight:600;margin-bottom:6px">24 小时记录量（7 天合计）</div>
        ${barChart(hourly, { valueKey: 'record_cnt', height: 100, color: 'var(--blue)' })}
      </div>

      <!-- 日级趋势 -->
      <div style="margin-bottom:20px">
        <div style="font-weight:600;margin-bottom:6px">7 天日级趋势</div>
        ${renderTable(
          [
            { key: 'report_date', label: '日期', render: v => v ? v.substring(5) : '—' },
            { key: 'record_cnt', label: '记录数', className: 'num', render: v => fmt(v) },
            { key: 'device_cnt', label: '设备数', className: 'num', render: v => fmt(v) },
            { key: 'cell_cnt', label: 'Cell', className: 'num', render: v => fmt(v) },
            { key: 'gps_original_ratio', label: 'GPS原始率', render: v => pctBar(v, 'var(--green)') },
            { key: 'signal_original_ratio', label: '信号原始率', render: v => pctBar(v, 'var(--blue)') },
            { key: 'rsrp_avg', label: 'RSRP', className: 'num', render: v => v != null ? `${v} dBm` : '—' },
          ],
          daily
        )}
      </div>
    `;
  } catch (e) {
    document.getElementById('drawer-body').innerHTML = `<div class="error-card">${escapeHtml(e.message)}</div>`;
  }
};

// ════════════════════════════════════════════════════════════
//  筛选 & 排序 & 翻页
// ════════════════════════════════════════════════════════════

window.bsFilterChange = function() {
  filters = {};
  const op = document.getElementById('bs-filter-op')?.value;
  const tech = document.getElementById('bs-filter-tech')?.value;
  const lac = document.getElementById('bs-filter-lac')?.value;
  const cls = document.getElementById('bs-filter-cls')?.value;
  const gc = document.getElementById('bs-filter-gc')?.value;
  if (op) filters.operator_code = op;
  if (tech) filters.tech_norm = tech;
  if (lac) filters.lac = lac;
  if (cls) filters.classification = cls;
  if (gc) filters.gps_confidence = gc;
  page = 0;
  loadProfileBs(true);
};

window.bsSortChange = function(col) {
  if (sortBy === col) {
    sortDir = sortDir === 'desc' ? 'asc' : 'desc';
  } else {
    sortBy = col;
    sortDir = 'desc';
  }
  page = 0;
  loadProfileBs(true);
};

window.bsPageChange = function(dir) {
  page = Math.max(0, page + dir);
  loadProfileBs(true);
};

// ════════════════════════════════════════════════════════════
//  BS 画像 — 样本列表
// ════════════════════════════════════════════════════════════

function sortIcon(col) {
  if (sortBy !== col) return '';
  return sortDir === 'desc' ? ' &#9660;' : ' &#9650;';
}

async function loadBsProfile() {
  const params = {
    sort_by: sortBy,
    sort_dir: sortDir,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    ...filters,
  };
  const d = await api(`/profile/bs/sample/list${qs(params)}`, { ttl: 30000 });
  const rows = d.rows || [];
  const stats = d.stats || {};
  const total = d.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return `
    ${renderTabNav()}

    <div class="page-head">
      <div>
        <h2>L4 BS 画像 — 样本评估</h2>
        <p>基于 6 个样本 LAC 的 ${fmt(stats.total_bs)} 个 BS。点击行查看详情（空间精度、补齐构成、潮汐、日级趋势）。</p>
      </div>
    </div>

    <!-- 概况 -->
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-label">样本 BS</div>
        <div class="stat-value blue">${fmt(stats.total_bs)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">总记录数</div>
        <div class="stat-value blue">${fmt(stats.total_records)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">异常 BS</div>
        <div class="stat-value" style="color:var(--orange)">${fmt(stats.anomaly_bs)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">GPS 可信度</div>
        <div style="font-size:13px;line-height:1.6">
          <span class="tag tag-green">高 ${stats.gps_high}</span>
          <span class="tag tag-orange">中 ${stats.gps_medium}</span>
          <span class="tag tag-red">低 ${stats.gps_low}</span>
          <span class="tag tag-gray">无 ${stats.gps_none}</span>
        </div>
      </div>
    </div>

    <!-- 异常分类分布 -->
    <div class="card" style="margin-bottom:16px">
      <div class="card-title"><h3>异常分类分布</h3></div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:13px">
        <span class="tag tag-purple">动态BS ${stats.dynamic_bs_cnt || 0}</span>
        <span class="tag tag-red">确认碰撞 ${stats.collision_confirmed_cnt || 0}</span>
        <span class="tag tag-orange">疑似碰撞 ${stats.collision_suspected_cnt || 0}</span>
        <span class="tag tag-blue">面积大 ${stats.single_large_cnt || 0}</span>
        <span class="tag tag-green">GPS噪声 ${stats.normal_spread_cnt || 0}</span>
        <span style="color:var(--text-dim)">正常 ${(stats.total_bs || 0) - (stats.anomaly_bs || 0)}</span>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="card" style="margin-bottom:16px">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:13px">
        <select id="bs-filter-op" onchange="bsFilterChange()" style="padding:4px 8px;border-radius:4px;border:1px solid #d1d5db">
          <option value="">全部运营商</option>
          <option value="46000" ${filters.operator_code === '46000' ? 'selected' : ''}>中国移动</option>
          <option value="46001" ${filters.operator_code === '46001' ? 'selected' : ''}>中国联通</option>
          <option value="46011" ${filters.operator_code === '46011' ? 'selected' : ''}>中国电信</option>
        </select>
        <select id="bs-filter-tech" onchange="bsFilterChange()" style="padding:4px 8px;border-radius:4px;border:1px solid #d1d5db">
          <option value="">全部制式</option>
          <option value="4G" ${filters.tech_norm === '4G' ? 'selected' : ''}>4G</option>
          <option value="5G" ${filters.tech_norm === '5G' ? 'selected' : ''}>5G</option>
        </select>
        <select id="bs-filter-cls" onchange="bsFilterChange()" style="padding:4px 8px;border-radius:4px;border:1px solid #d1d5db">
          <option value="">全部分类</option>
          <option value="normal" ${filters.classification === 'normal' ? 'selected' : ''}>正常</option>
          <option value="dynamic_bs" ${filters.classification === 'dynamic_bs' ? 'selected' : ''}>动态BS</option>
          <option value="collision_confirmed" ${filters.classification === 'collision_confirmed' ? 'selected' : ''}>确认碰撞</option>
          <option value="collision_suspected" ${filters.classification === 'collision_suspected' ? 'selected' : ''}>疑似碰撞</option>
          <option value="single_large" ${filters.classification === 'single_large' ? 'selected' : ''}>面积大</option>
          <option value="normal_spread" ${filters.classification === 'normal_spread' ? 'selected' : ''}>GPS噪声</option>
        </select>
        <select id="bs-filter-gc" onchange="bsFilterChange()" style="padding:4px 8px;border-radius:4px;border:1px solid #d1d5db">
          <option value="">全部GPS可信度</option>
          <option value="high" ${filters.gps_confidence === 'high' ? 'selected' : ''}>高</option>
          <option value="medium" ${filters.gps_confidence === 'medium' ? 'selected' : ''}>中</option>
          <option value="low" ${filters.gps_confidence === 'low' ? 'selected' : ''}>低</option>
          <option value="none" ${filters.gps_confidence === 'none' ? 'selected' : ''}>无</option>
        </select>
        <span style="color:var(--text-dim)">共 ${fmt(total)} 个 BS（第 ${page + 1}/${Math.max(totalPages, 1)} 页）</span>
      </div>
    </div>

    <!-- BS 列表 -->
    <div class="card">
      <div class="card-title"><h3>BS 画像列表</h3></div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">点击行展开详情。点击表头排序。</p>
      <div style="overflow-x:auto">
      <table class="compact-table">
        <thead><tr>
          <th>运营商</th><th>制式</th><th>LAC</th><th>位置</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('bs_id')">BS ID${sortIcon('bs_id')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('total_records')">记录数${sortIcon('total_records')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('total_devices')">设备${sortIcon('total_devices')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('total_cells')">Cell${sortIcon('total_cells')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('gps_p50_dist_m')">P50(m)${sortIcon('gps_p50_dist_m')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('gps_p90_dist_m')">P90(m)${sortIcon('gps_p90_dist_m')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('area_km2')">面积km²${sortIcon('area_km2')}</th>
          <th style="cursor:pointer" onclick="bsSortChange('gps_original_ratio')">GPS原始率${sortIcon('gps_original_ratio')}</th>
          <th style="cursor:pointer" onclick="bsSortChange('signal_original_ratio')">信号原始率${sortIcon('signal_original_ratio')}</th>
          <th class="num" style="cursor:pointer" onclick="bsSortChange('rsrp_avg')">RSRP${sortIcon('rsrp_avg')}</th>
          <th>分类</th>
          <th>GPS可信</th>
        </tr></thead>
        <tbody>
          ${rows.map(r => {
            const bsJson = encodeURIComponent(JSON.stringify(r));
            return `<tr style="cursor:pointer" onclick="openBsDetail('${r.operator_code}','${r.tech_norm}','${r.lac}',${r.bs_id},'${bsJson}')">
            <td>${opTag(r.operator_code)}</td>
            <td>${techTag(r.tech_norm)}</td>
            <td>${r.lac}</td>
            <td><span style="font-size:12px">${r.district_name || r.city_name || '—'}</span></td>
            <td class="num">${r.bs_id}</td>
            <td class="num">${fmt(r.total_records)}</td>
            <td class="num">${fmt(r.total_devices)}</td>
            <td class="num">${fmt(r.total_cells)}</td>
            <td class="num">${r.gps_p50_dist_m != null ? fmt(r.gps_p50_dist_m) : '—'}</td>
            <td class="num">${r.gps_p90_dist_m != null ? fmt(r.gps_p90_dist_m) : '—'}</td>
            <td class="num">${r.area_km2 != null ? r.area_km2 : '—'}</td>
            <td>${pctBar(r.gps_original_ratio, 'var(--green)')}</td>
            <td>${pctBar(r.signal_original_ratio, 'var(--blue)')}</td>
            <td class="num">${r.rsrp_avg != null ? r.rsrp_avg + ' dBm' : '—'}</td>
            <td>${classificationTag(r.classification_v2)}</td>
            <td>${confidenceTag(r.gps_confidence)}</td>
          </tr>`}).join('')}
        </tbody>
      </table>
      </div>

      <!-- 分页 -->
      <div style="display:flex;justify-content:center;gap:12px;margin-top:12px">
        <button class="btn btn-ghost" onclick="bsPageChange(-1)" ${page === 0 ? 'disabled' : ''}>上一页</button>
        <span style="line-height:32px;font-size:13px;color:var(--text-dim)">${page + 1} / ${Math.max(totalPages, 1)}</span>
        <button class="btn btn-ghost" onclick="bsPageChange(1)" ${page + 1 >= totalPages ? 'disabled' : ''}>下一页</button>
      </div>
    </div>

    <!-- 口径说明 -->
    <div class="card">
      <div class="card-title"><h3>口径说明</h3></div>
      <div style="font-size:13px;color:var(--text-dim);line-height:1.8">
        <p><b>空间指标</b>：基于 GPS 原始点（gps_source='original'）计算中心点和距离分位数</p>
        <p><b>P50/P90 距离</b> = GPS 原始点到 BS 中心点的距离中位数/90 分位数（米）</p>
        <p><b>GPS 原始率</b> = gps_source='original' / 总记录数</p>
        <p><b>信号原始率</b> = signal_fill_source='original' / 总记录数</p>
        <p><b>GPS 可信度</b>：高（原始GPS>=10 且设备>=2 且无异常）/ 中 / 低 / 无</p>
        <p><b>异常分类</b>：来自 Phase 3 Cell 质心法 v2（_research_bs_classification_v2）</p>
      </div>
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
//  BS 总览（待实现）
// ════════════════════════════════════════════════════════════

async function loadBsOverview() {
  return `
    ${renderTabNav()}
    <div class="page-head"><div><h2>L4 BS 总览</h2><p>画像属性确认后，全量执行并在此展示</p></div></div>
    <div class="card"><div class="empty-state">画像属性评估确认后解锁</div></div>
  `;
}

// ════════════════════════════════════════════════════════════
//  入口
// ════════════════════════════════════════════════════════════

export async function loadProfileBs(force = false) {
  try {
    let html;
    switch (currentTab) {
      case 'bs-profile': html = await loadBsProfile(); break;
      case 'bs-overview': html = await loadBsOverview(); break;
      default: html = await loadBsProfile();
    }
    setMain(html);
  } catch (e) {
    setMain(pageError('BS 画像加载失败', e));
  }
}
