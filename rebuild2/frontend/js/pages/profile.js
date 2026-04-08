/**
 * L4 LAC 画像：样本评估 + 总览。
 */

import { api, qs } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, renderTable, openDrawer,
} from '../ui/common.js';

let currentTab = 'lac-profile';

function switchTab(tab) { currentTab = tab; loadProfile(true); }
window.switchProfileTab = switchTab;

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

// ── LAC 16 进制 ──
function lacHex(lac) {
  const n = Number(lac);
  if (Number.isNaN(n)) return lac;
  return `${lac} <span style="color:var(--text-dim);font-size:12px">(0x${n.toString(16).toUpperCase()})</span>`;
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

function ratioColor(r) {
  if (r >= 0.8) return 'var(--green)';
  if (r >= 0.5) return 'var(--orange)';
  return 'var(--red)';
}

// ── 柱状图 ──

function barChart(data, { valueKey, labelKey = 'hour_of_day', height = 120, color = 'var(--blue)', maxVal = null }) {
  const vals = data.map(d => Number(d[valueKey]) || 0);
  const max = maxVal != null ? maxVal : Math.max(...vals, 1);
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

// ── 异常分类标签 ──

function anomalyTag(label, cnt, cls) {
  if (!cnt) return '';
  return `<span class="tag ${cls}" style="margin-right:4px">${label} ${cnt}</span>`;
}

// ════════════════════════════════════════════════════════════
//  Tab 导航
// ════════════════════════════════════════════════════════════

function renderTabNav() {
  const tabs = [
    { key: 'lac-profile', label: 'LAC 画像' },
    { key: 'lac-overview', label: 'LAC 总览', disabled: true },
  ];
  return `<div class="toolbar" style="margin-bottom:16px;gap:4px">
    ${tabs.map(t => `<button class="btn ${currentTab === t.key ? 'btn-primary' : 'btn-ghost'}"
      onclick="switchProfileTab('${t.key}')"
      ${t.disabled ? 'disabled style="opacity:0.5"' : ''}
    >${t.label}</button>`).join('')}
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  LAC 潮汐详情（抽屉）
// ════════════════════════════════════════════════════════════

window.openLacDetail = async function(op, tech, lac, lacDataJson) {
  const lacData = JSON.parse(decodeURIComponent(lacDataJson));
  openDrawer({
    title: `LAC ${lac} (0x${Number(lac).toString(16).toUpperCase()})`,
    kicker: `${OP_MAP[op]?.[0] || op} · ${tech}`,
    body: '<div class="loading">加载中...</div>',
  });

  try {
    const params = qs({ operator_code: op, tech_norm: tech, lac });
    const [hRes, dRes] = await Promise.all([
      api(`/profile/lac/sample/hourly${params}`, { ttl: 60000 }),
      api(`/profile/lac/sample/daily${params}`, { ttl: 60000 }),
    ]);
    const hourly = hRes.hourly || [];
    const daily = dRes.daily || [];

    document.getElementById('drawer-body').innerHTML = `
      <!-- 位置 + 基本信息 -->
      ${lacData.province_name ? `<div style="margin-bottom:12px;padding:8px 14px;background:var(--bg);border-radius:6px;font-size:13px">
        <span style="color:var(--text-dim)">位置：</span>
        <b>${lacData.province_name}</b>${lacData.location_district_cnt > 1 ? ` · 覆盖 ${lacData.location_district_cnt} 区：${lacData.location_districts}` : ` · ${lacData.location_district}`}
      </div>` : ''}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;font-size:13px">
        <div style="background:var(--bg);padding:10px;border-radius:6px">
          <div style="color:var(--text-dim)">GPS 中心点</div>
          <div style="font-weight:500">${lacData.center_lon ?? '—'}, ${lacData.center_lat ?? '—'}</div>
        </div>
        <div style="background:var(--bg);padding:10px;border-radius:6px">
          <div style="color:var(--text-dim)">覆盖面积 / 上报密度</div>
          <div style="font-weight:500">${lacData.area_km2 ?? '—'} km² / ${fmt(lacData.report_density_per_km2)} 条/km²</div>
        </div>
      </div>

      <!-- 异常命中 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">异常 BS 命中</div>
        <div>
          ${anomalyTag('动态BS', lacData.dynamic_bs_cnt, 'tag-purple')}
          ${anomalyTag('确认碰撞', lacData.collision_confirmed_cnt, 'tag-red')}
          ${anomalyTag('疑似碰撞', lacData.collision_suspected_cnt, 'tag-orange')}
          ${anomalyTag('面积大', lacData.single_large_cnt, 'tag-blue')}
          ${anomalyTag('GPS噪声', lacData.normal_spread_cnt, 'tag-green')}
          ${!lacData.dynamic_bs_cnt && !lacData.collision_confirmed_cnt && !lacData.collision_suspected_cnt && !lacData.single_large_cnt && !lacData.normal_spread_cnt ? '<span style="color:var(--text-dim);font-size:13px">无异常 BS</span>' : ''}
        </div>
        <div style="font-size:12px;color:var(--text-dim);margin-top:4px">
          排除记录 ${fmt(lacData.excluded_record_cnt)} 条（${((lacData.excluded_ratio || 0) * 100).toFixed(1)}%），排除 BS ${fmt(lacData.excluded_bs_cnt)} 个
        </div>
      </div>

      <!-- GPS 补齐构成 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">GPS 来源构成</div>
        <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;margin-bottom:6px">
          ${[
            { cnt: lacData.gps_original_cnt, color: 'var(--green)', label: '原始' },
            { cnt: lacData.gps_cell_center_cnt, color: '#2563eb', label: 'Cell补齐' },
            { cnt: lacData.gps_bs_center_cnt, color: 'var(--orange)', label: 'BS补齐' },
            { cnt: lacData.gps_bs_center_risk_cnt, color: 'var(--red)', label: 'BS风险补齐' },
          ].map(s => {
            const w = lacData.record_cnt > 0 ? (s.cnt / lacData.record_cnt * 100) : 0;
            return w > 0 ? `<div style="width:${w}%;background:${s.color}" title="${s.label}: ${fmt(s.cnt)} (${w.toFixed(1)}%)"></div>` : '';
          }).join('')}
        </div>
        <div style="font-size:12px;color:var(--text-dim)">
          原始 ${fmt(lacData.gps_original_cnt)} · Cell补齐 ${fmt(lacData.gps_cell_center_cnt)} · BS补齐 ${fmt(lacData.gps_bs_center_cnt)} · BS风险 ${fmt(lacData.gps_bs_center_risk_cnt)}
        </div>
      </div>

      <!-- 信号补齐构成 -->
      <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px">
        <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text-soft)">信号来源构成</div>
        <div style="display:flex;height:16px;border-radius:4px;overflow:hidden;margin-bottom:6px">
          ${[
            { cnt: lacData.signal_original_cnt, color: 'var(--green)', label: '原始' },
            { cnt: lacData.signal_fill_cnt, color: 'var(--orange)', label: 'Cell补齐' },
          ].map(s => {
            const w = lacData.record_cnt > 0 ? (s.cnt / lacData.record_cnt * 100) : 0;
            return w > 0 ? `<div style="width:${w}%;background:${s.color}" title="${s.label}: ${fmt(s.cnt)} (${w.toFixed(1)}%)"></div>` : '';
          }).join('')}
        </div>
        <div style="font-size:12px;color:var(--text-dim)">
          原始 ${fmt(lacData.signal_original_cnt)} · Cell补齐 ${fmt(lacData.signal_fill_cnt)}
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
            { key: 'bs_cnt', label: 'BS', className: 'num', render: v => fmt(v) },
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
//  LAC 画像 — 样本列表
// ════════════════════════════════════════════════════════════

async function loadLacProfile() {
  const d = await api('/profile/lac/sample/list', { ttl: 60000 });
  const rows = d.lacs || [];

  const totalRecords = rows.reduce((s, r) => s + Number(r.record_cnt || 0), 0);

  return `
    ${renderTabNav()}

    <div class="page-head">
      <div>
        <h2>L4 LAC 画像 — 样本评估</h2>
        <p>3 运营商 × 2 制式，每组 1 个 LAC。基于 LAC × 天 × 小时 压缩表，点击行查看详情。</p>
      </div>
    </div>

    <!-- 概况 -->
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-label">样本 LAC</div>
        <div class="stat-value blue">${fmt(rows.length)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">有效记录（排除异常后）</div>
        <div class="stat-value blue">${fmt(totalRecords)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">被排除记录</div>
        <div class="stat-value" style="color:var(--orange)">${fmt(rows.reduce((s, r) => s + Number(r.excluded_record_cnt || 0), 0))}</div>
      </div>
    </div>

    <!-- 汇总表 -->
    <div class="card">
      <div class="card-title"><h3>7 天汇总对比</h3></div>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">点击行展开详情（异常命中、补齐构成、24小时潮汐、日级趋势）</p>
      <table class="compact-table">
        <thead><tr>
          <th>运营商</th><th>制式</th><th>LAC</th><th>位置</th>
          <th class="num">记录数</th><th class="num">BS</th><th class="num">Cell</th><th class="num">设备数</th>
          <th class="num">面积km²</th><th class="num">BS密度/km²</th><th class="num">上报密度/km²</th>
          <th>GPS原始率</th><th>信号原始率</th>
          <th class="num">RSRP</th><th>异常排除率</th>
        </tr></thead>
        <tbody>
          ${rows.map(r => {
            const lacJson = encodeURIComponent(JSON.stringify(r));
            return `<tr style="cursor:pointer" onclick="openLacDetail('${r.operator_code}','${r.tech_norm}','${r.lac}','${lacJson}')">
            <td>${opTag(r.operator_code)}</td>
            <td>${techTag(r.tech_norm)}</td>
            <td>${lacHex(r.lac)}</td>
            <td><span style="font-size:12px">${r.province_name ? r.province_name + (r.location_district_cnt > 1 ? '<br>' + r.location_districts : ' ' + r.location_district) : '—'}</span></td>
            <td class="num">${fmt(r.record_cnt)}</td>
            <td class="num">${fmt(r.bs_cnt)}</td>
            <td class="num">${fmt(r.cell_cnt)}</td>
            <td class="num">${fmt(r.device_cnt)}</td>
            <td class="num">${r.area_km2 ?? '—'}</td>
            <td class="num">${r.bs_density_per_km2 ?? '—'}</td>
            <td class="num">${fmt(r.report_density_per_km2)}</td>
            <td>${pctBar(r.gps_original_ratio, 'var(--green)')}</td>
            <td>${pctBar(r.signal_original_ratio, 'var(--blue)')}</td>
            <td class="num">${r.rsrp_avg != null ? r.rsrp_avg + ' dBm' : '—'}</td>
            <td>${pctBar(r.excluded_ratio, 'var(--red)')}</td>
          </tr>`}).join('')}
        </tbody>
      </table>
    </div>

    <!-- 口径说明 -->
    <div class="card">
      <div class="card-title"><h3>口径说明</h3></div>
      <div style="font-size:13px;color:var(--text-dim);line-height:1.8">
        <p><b>有效口径</b>：剔除 dynamic_bs、collision_confirmed、collision_suspected 三类异常 BS 后统计</p>
        <p><b>GPS 原始率</b> = gps_source='original' / 有效记录</p>
        <p><b>信号原始率</b> = signal_fill_source='original' / 有效记录</p>
        <p><b>覆盖面积</b> = GPS 经纬度 P5-P95 矩形面积（去极端飘点）</p>
        <p><b>上报密度</b> = 有效记录数 / 覆盖面积(km²)</p>
      </div>
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
//  LAC 总览（待实现）
// ════════════════════════════════════════════════════════════

async function loadLacOverview() {
  return `
    ${renderTabNav()}
    <div class="page-head"><div><h2>L4 LAC 总览</h2><p>画像属性确认后，全量执行并在此展示</p></div></div>
    <div class="card"><div class="empty-state">画像属性评估确认后解锁</div></div>
  `;
}

// ════════════════════════════════════════════════════════════
//  入口
// ════════════════════════════════════════════════════════════

export async function loadProfile(force = false) {
  try {
    let html;
    switch (currentTab) {
      case 'lac-profile': html = await loadLacProfile(); break;
      case 'lac-overview': html = await loadLacOverview(); break;
      default: html = await loadLacProfile();
    }
    setMain(html);
  } catch (e) {
    setMain(pageError('画像加载失败', e));
  }
}
