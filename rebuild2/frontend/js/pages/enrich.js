/**
 * L3 基站定位与信号补齐：Phase 3 数据补齐与修正。
 *
 * 正常数据处理：
 *   第一步: 基站(BS)中心点精算
 *   第二步: 小区(Cell) GPS 校验
 *   第三步: 明细行 GPS 修正
 *   第四步: 信号补齐
 *   第五步: 回算
 */

import { api } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, showToast, renderTable,
} from '../ui/common.js';

let currentStep = 'step1';

function switchStep(step) { currentStep = step; loadEnrich(true); }
window.switchEnrichStep = switchStep;

function techTag(t) {
  const m = { '5G': 'tag-blue', '4G': 'tag-green' };
  return `<span class="tag ${m[t] || 'tag-gray'}">${escapeHtml(t)}</span>`;
}
function operatorTag(op) {
  const m = { '移动': 'tag-blue', '联通': 'tag-red', '电信': 'tag-green', '广电': 'tag-orange' };
  return `<span class="tag ${m[op] || 'tag-gray'}">${escapeHtml(op)}</span>`;
}
function qualityTag(q) {
  const labels = { 'Usable': '可用', 'Risk': '风险', 'Unusable': '不可用' };
  const m = { 'Usable': 'tag-green', 'Risk': 'tag-orange', 'Unusable': 'tag-red' };
  return `<span class="tag ${m[q] || 'tag-gray'}">${escapeHtml(labels[q] || q)}</span>`;
}

function gpsSourceLabel(src) {
  const labels = {
    'original':        '原始上报 GPS',
    'cell_center':     '小区(Cell)精算中心点',
    'bs_center':       '基站(BS)精算中心点（可用）',
    'bs_center_risk':  '基站(BS)精算中心点（风险）',
    'not_filled':      '未能填充',
  };
  return labels[src] || escapeHtml(src || '—');
}

function gpsSourceTag(src) {
  const colors = {
    'original':        'tag-green',
    'cell_center':     'tag-blue',
    'bs_center':       'tag-orange',
    'bs_center_risk':  'tag-red',
    'not_filled':      'tag-gray',
  };
  return `<span class="tag ${colors[src] || 'tag-gray'}">${gpsSourceLabel(src)}</span>`;
}

// ════════════════════════════════════════════════════════════
//  漏斗步骤渲染
// ════════════════════════════════════════════════════════════

function _funnelStep(level, title, desc, count, total, remaining, color) {
  const pct = total > 0 ? (count / total * 100).toFixed(2) : '0';
  const barWidth = total > 0 ? Math.max(count / total * 100, 2) : 0;
  const indent = (level - 1) * 20;
  const colors = { green: 'var(--green)', blue: '#2563eb', orange: 'var(--orange)', red: 'var(--red)' };
  const c = colors[color] || 'var(--text-dim)';
  const isInput = level === 1;

  return `<div style="margin-left:${indent}px;margin-bottom:${isInput ? 8 : 12}px;padding:${isInput ? '8px 12px' : '10px 12px'};border-left:3px solid ${c};background:${isInput ? 'var(--bg-card)' : 'var(--bg)'}; border-radius:0 6px 6px 0">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <div>
        <span style="font-weight:600;color:${c}">${isInput ? '▶' : '├─'} ${escapeHtml(title)}</span>
        ${!isInput ? `<span style="font-size:12px;color:var(--text-dim);margin-left:8px">${escapeHtml(desc)}</span>` : ''}
      </div>
      <div style="text-align:right;white-space:nowrap">
        <span style="font-weight:700;color:${c};font-size:${isInput ? '16px' : '15px'}">${fmt(count)}</span>
        <span style="font-size:12px;color:var(--text-dim);margin-left:4px">${isInput ? '条' : `(${pct}%)`}</span>
      </div>
    </div>
    ${isInput ? `<div style="font-size:12px;color:var(--text-dim);margin-top:2px">${escapeHtml(desc)}</div>` : ''}
    ${!isInput ? `<div style="margin-top:4px;height:4px;background:#e5e7eb;border-radius:2px;overflow:hidden">
      <div style="height:100%;width:${barWidth}%;background:${c};border-radius:2px"></div>
    </div>` : ''}
    ${remaining != null && remaining > 0 ? `<div style="font-size:11px;color:var(--text-dim);margin-top:3px;text-align:right">剩余 ${fmt(remaining)} 条进入下一级 ↓</div>` : ''}
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  步骤导航
// ════════════════════════════════════════════════════════════

// 记录各步骤是否已完成（done），用于控制导航按钮是否可点击
const _stepDone = { step1: false, step2: false, step3: false, step4: false, step5: false };

async function refreshStepDoneFlags() {
  // 并发查询所有步骤状态
  const keys = ['step1', 'step2', 'step3', 'step4', 'step5'];
  await Promise.all(keys.map(async k => {
    try {
      const s = await api(`/enrich/${k}/status`, { ttl: 5000, force: false });
      _stepDone[k] = (s.status === 'done');
    } catch { _stepDone[k] = false; }
  }));
}

function renderStepNav() {
  const steps = [
    { key: 'step1', label: '第一步：基站(BS)中心点精算' },
    { key: 'step2', label: '第二步：小区(Cell) GPS 校验' },
    { key: 'step3', label: '第三步：明细行 GPS 修正' },
    { key: 'step4', label: '第四步：信号补齐' },
    { key: 'step5', label: '第五步：回算' },
  ];

  // 某一步可点击的条件：前一步已完成，或当前步本身（始终可点）
  const enabled = {
    step1: true,
    step2: _stepDone.step1,
    step3: _stepDone.step2,
    step4: _stepDone.step3,
    step5: _stepDone.step4,
  };

  return `<div class="toolbar" style="margin-bottom:16px;gap:4px">
    ${steps.map(s => {
      const isEnabled = enabled[s.key];
      const isActive  = currentStep === s.key;
      return `<button class="btn ${isActive ? 'btn-primary' : 'btn-ghost'}"
        onclick="switchEnrichStep('${s.key}')"
        ${isEnabled ? '' : 'disabled style="opacity:0.5"'}
      >${s.label}</button>`;
    }).join('')}
  </div>`;
}

// ════════════════════════════════════════════════════════════
//  第一步：基站(BS)中心点精算
// ════════════════════════════════════════════════════════════

let _pollTimer = null;

async function loadStep1() {
  const status = await api('/enrich/step1/status', { ttl: 3000, force: true });

  if (status.status === 'running') {
    return renderStep1Running();
  }
  if (status.status === 'done') {
    return await renderStep1Result();
  }
  return await renderStep1Preview(status);
}

async function renderStep1Preview(status) {
  const data = await api('/enrich/step1/preview', { ttl: 10000, force: true });
  const gps = data.gps_overview || {};
  const qp = data.quality_preview || {};
  const params = data.params || {};
  const note = data.data_quality_note || {};

  const errorHtml = status?.status === 'error'
    ? `<div class="card" style="border-left:3px solid var(--red);margin-bottom:16px">
        <div class="card-title"><h3 style="color:var(--red)">上次执行失败</h3></div>
        <pre style="font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(status.stderr || status.message || '')}</pre>
       </div>` : '';

  return `
    ${renderStepNav()}
    ${errorHtml}

    <div class="card">
      <div class="card-title"><h3>第一步：基站(BS)中心点精算</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>问题</b>：Phase 2 的基站(BS) GPS 中心点是简单中位数，没有做信号加权、异常剔除和设备去重，中心点可能被远处飘点或同一设备重复上报拉偏。<br>
        <b>目标</b>：用信号强度加权选种 + 设备去重 + 分箱中位数 + 异常剔除四步精算，得到更准确的基站(BS)中心点。<br>
        <b>产出</b>：rebuild2.dim_bs_refined（${fmt(gps.total_bs)} 个基站，含 GPS 质量分级）
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">基站(BS)总数</div><div class="stat-value blue">${fmt(gps.total_bs)}</div></div>
      <div class="stat-box"><div class="stat-label">有 GPS 中心点</div><div class="stat-value green">${fmt(gps.bs_with_center)}</div></div>
      <div class="stat-box"><div class="stat-label">无 GPS 中心点</div><div class="stat-value orange">${fmt(gps.bs_no_center)}</div></div>
      <div class="stat-box"><div class="stat-label">每基站(BS)平均 GPS 点数</div><div class="stat-value">${fmt(gps.avg_gps_per_bs)}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>预估 GPS 质量分级</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">根据基站(BS)下属小区的 GPS 覆盖情况预估质量等级</div>
      <div class="stat-grid" style="margin-top:8px">
        <div class="stat-box"><div class="stat-label">可用（2个以上小区有 GPS）</div><div class="stat-value green">${fmt(qp.usable)}</div></div>
        <div class="stat-box"><div class="stat-label">风险（仅1个小区(Cell)有 GPS）</div><div class="stat-value orange">${fmt(qp.risk)}</div></div>
        <div class="stat-box"><div class="stat-label">不可用（无小区有 GPS）</div><div class="stat-value" style="color:var(--red)">${fmt(qp.unusable)}</div></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>各运营商基站(BS) GPS 覆盖</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'bs_count', label: '基站(BS)数', className: 'num', render: v => fmt(v) },
        { key: 'bs_with_gps', label: '有 GPS 的基站(BS)', className: 'num', render: v => fmt(v) },
        { key: 'total_gps_points', label: 'GPS 总点数', className: 'num', render: v => fmt(v) },
        { key: 'total_cells', label: '小区(Cell)总数', className: 'num', render: v => fmt(v) },
      ], data.by_operator || [])}
    </div>

    <div class="card">
      <div class="card-title"><h3>精算算法参数</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2.2">
        <b>① 设备去重</b>：GPS 点超过 ${params.device_dedup_threshold} 个的基站(BS)，每台设备只取信号最强的一条记录，防止同一设备多次上报拉偏中心<br>
        <b>② 信号加权选种</b>：按信号强度（RSRP）从强到弱选取种子点
        ${renderTable([
          { key: 'range', label: '基站(BS) GPS 点数' },
          { key: 'take', label: '选取规则' },
        ], (params.seed_tiers || []).map(t => ({
          range: t.min_points > 0 ? '≥ ' + t.min_points + ' 个点' : '不足 5 个点',
          take: typeof t.take === 'number' ? '取信号最强的 ' + t.take + ' 个' : t.take,
        })))}
        <b>③ 中心点计算</b>：分箱中位数（经纬度四舍五入到万分位，精度约 11 米）<br>
        <b>④ 异常剔除</b>：种子点距中心超过 ${fmt(params.outlier_distance_m)} 米的视为飘点，剔除后重新计算中心<br>
        <b>⑤ 无效信号值</b>：RSRP 为 ${(params.rsrp_invalid_values || []).join('、')} 的记录排除<br>
        <b>⑥ GPS 范围</b>：${params.gps_bounds || '中国范围'}
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>数据质量参考（来自 Phase 2）</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        GPS 有效率：${note.gps_coverage || '—'}<br>
        信号强度覆盖率：${note.rsrp_coverage || '—'}<br>
        GPS 和信号强度同时有效：${note.gps_and_rsrp || '—'}
      </div>
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:12px 24px;font-size:15px"
        onclick="executeStep1()">
        确认参数，执行基站(BS)中心点精算
      </button>
      <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">
        将通过 SSH 在服务器上执行，预计 5~15 分钟
      </div>
    </div>
  `;
}

function renderStep1Running() {
  if (!_pollTimer) {
    _pollTimer = setInterval(async () => {
      try {
        const s = await api('/enrich/step1/status', { ttl: 0, force: true });
        if (s.status !== 'running') {
          clearInterval(_pollTimer);
          _pollTimer = null;
          loadEnrich(true);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  return `
    ${renderStepNav()}
    <div class="card" style="text-align:center;padding:40px">
      <div class="loading" style="margin-bottom:16px">基站(BS)中心点精算执行中...</div>
      <div style="font-size:13px;color:var(--text-dim)">
        正在服务器上处理约 3000 万行数据，请耐心等待<br>
        页面每 5 秒自动检查进度
      </div>
    </div>
  `;
}

async function renderStep1Result() {
  const data = await api('/enrich/step1/result', { ttl: 10000, force: true });
  if (!data.exists) {
    return renderStepNav() + '<div class="card"><div class="empty-state">精算结果表尚未创建</div></div>';
  }

  const t = data.totals || {};
  const drift = data.center_drift || {};
  const dist = data.dist_distribution || {};

  return `
    ${renderStepNav()}

    <div class="card">
      <div class="card-title"><h3>第一步结果：基站(BS)精算维表</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">表名：rebuild2.dim_bs_refined</div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">基站(BS)总数</div><div class="stat-value blue">${fmt(t.total_bs)}</div></div>
      <div class="stat-box"><div class="stat-label">有精算中心点</div><div class="stat-value green">${fmt(t.has_center)}</div></div>
      <div class="stat-box"><div class="stat-label">做过异常剔除的基站(BS)</div><div class="stat-value orange">${fmt(t.outlier_removed)}</div></div>
      <div class="stat-box"><div class="stat-label">种子点中位距离（均值）</div><div class="stat-value">${fmt(t.avg_p50)} 米</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>GPS 质量分级</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        质量等级根据基站(BS)下属小区中有多少个小区(Cell)携带了 GPS 数据来判定
      </div>
      <div class="stat-grid" style="margin-top:8px">
        <div class="stat-box"><div class="stat-label">可用（2个以上小区有 GPS）</div><div class="stat-value green">${fmt(t.usable)}</div></div>
        <div class="stat-box"><div class="stat-label">风险（仅1个小区(Cell)有 GPS）</div><div class="stat-value orange">${fmt(t.risk)}</div></div>
        <div class="stat-box"><div class="stat-label">不可用（无 GPS 数据）</div><div class="stat-value" style="color:var(--red)">${fmt(t.unusable)}</div></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>各运营商精算结果</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'bs_count', label: '基站(BS)数', className: 'num', render: v => fmt(v) },
        { key: 'usable', label: '可用', className: 'num', render: v => fmt(v) },
        { key: 'risk', label: '风险', className: 'num', render: v => fmt(v) },
        { key: 'unusable', label: '不可用', className: 'num', render: v => fmt(v) },
        { key: 'avg_p50', label: '中位距离均值（米）', className: 'num', render: v => fmt(v) },
        { key: 'avg_p90', label: '90分位距离均值（米）', className: 'num', render: v => fmt(v) },
      ], data.by_operator || [])}
    </div>

    <div class="card">
      <div class="card-title"><h3>种子点 90 分位距离分布</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        90 分位距离反映基站(BS)下 GPS 点的散布程度。距离越大说明 GPS 点越分散，超过 1500 米的可能是编码碰撞（不同物理基站(BS)共用同一编号）
      </div>
      ${renderTable([
        { key: 'range', label: '距离范围' },
        { key: 'count', label: '基站(BS)数', className: 'num', render: v => fmt(v) },
        { key: 'note', label: '含义' },
      ], [
        { range: '500 米以内', count: dist.p90_le_500, note: '正常覆盖' },
        { range: '500 ~ 1000 米', count: dist.p90_500_1000, note: '正常偏大' },
        { range: '1000 ~ 1500 米', count: dist.p90_1000_1500, note: '需关注' },
        { range: '1500 ~ 2500 米', count: dist.p90_1500_2500, note: '碰撞嫌疑' },
        { range: '超过 2500 米', count: dist.p90_gt_2500, note: '高风险碰撞' },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>精算前后中心点变化</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        对比同一基站在 Phase 2（简单中位数）和本步精算后的中心点位置差异。<br>
        偏移大的说明精算有效修正了被飘点或重复设备拉偏的旧中心点。
      </div>
      ${renderTable([
        { key: 'metric', label: '指标' },
        { key: 'value', label: '数值', className: 'num', render: v => fmt(v) },
        { key: 'note', label: '说明' },
      ], [
        { metric: '参与对比的基站(BS)', value: drift.total_compared, note: '新旧均有中心点的基站(BS)' },
        { metric: '偏移超过 100 米', value: drift.drifted_gt_100m, note: '精算修正了这些基站的位置' },
        { metric: '偏移超过 500 米', value: drift.drifted_gt_500m, note: '精算显著修正了位置' },
        { metric: '平均偏移距离', value: drift.avg_drift_m, note: '单位：米' },
      ])}
    </div>

    <div class="card">
      <div class="card-title">
        <h3>基站明细（前 30 条，按记录数排序）</h3>
      </div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: '位置区编码' },
        { key: 'bs_id', label: '基站(BS)编号', render: v => String(v) },
        { key: 'cell_count', label: '小区(Cell)数', className: 'num', render: v => fmt(v) },
        { key: 'cells_with_gps', label: '有 GPS 的小区(Cell)数', className: 'num', render: v => fmt(v) },
        { key: 'seed_count', label: '种子点数', className: 'num', render: v => fmt(v) },
        { key: 'gps_center_lon', label: '精算经度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
        { key: 'gps_center_lat', label: '精算纬度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
        { key: 'gps_p50_dist_m', label: '中位距离（米）', className: 'num', render: v => fmt(v) },
        { key: 'gps_p90_dist_m', label: '90分位距离（米）', className: 'num', render: v => fmt(v) },
        { key: 'gps_quality', label: '质量等级', render: v => qualityTag(v) },
        { key: 'had_outlier_removal', label: '异常剔除', render: v => v ? '<span style="color:var(--orange)">是</span>' : '—' },
      ], data.items || [])}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:10px 24px"
        onclick="switchEnrichStep('step2')">
        下一步：小区(Cell) GPS 校验 →
      </button>
    </div>
  `;
}

window.executeStep1 = async function () {
  if (!confirm('确认执行基站(BS)中心点精算？\n\n将通过 SSH 在服务器上执行，处理约 3000 万行数据，预计 5~15 分钟。\n已有 dim_bs_refined 将被重建。')) return;
  const btn = document.querySelector('button[onclick="executeStep1()"]');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const result = await api('/enrich/step1/execute', { method: 'POST', force: true });
    if (result.ok) {
      showToast('基站(BS)精算已启动');
      loadEnrich(true);
    } else {
      showToast('启动失败: ' + (result.error || ''));
      if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行基站(BS)中心点精算'; }
    }
  } catch (e) {
    showToast('启动失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行基站(BS)中心点精算'; }
  }
};

// ════════════════════════════════════════════════════════════
//  第二步：小区(Cell) GPS 校验
// ════════════════════════════════════════════════════════════

async function loadStep2() {
  const status = await api('/enrich/step2/status', { ttl: 3000, force: true });

  if (status.status === 'running') {
    return renderStep2Running();
  }
  if (status.status === 'done') {
    return await renderStep2Result();
  }
  return await renderStep2Preview(status);
}

async function renderStep2Preview(status) {
  const data = await api('/enrich/step2/preview', { ttl: 10000, force: true });
  const overview = data.cell_stats_overview || {};
  const params = data.validation_params || {};
  const byOp = data.by_operator || [];

  const errorHtml = status?.status === 'error'
    ? `<div class="card" style="border-left:3px solid var(--red);margin-bottom:16px">
        <div class="card-title"><h3 style="color:var(--red)">上次执行失败</h3></div>
        <pre style="font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(status.stderr || status.message || '')}</pre>
       </div>` : '';

  return `
    ${renderStepNav()}
    ${errorHtml}

    <div class="card">
      <div class="card-title"><h3>第二步：小区(Cell) GPS 校验</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>问题</b>：明细行中上报的小区(Cell) GPS 坐标可能存在飘点——坐标偏离该小区(Cell)所属基站(BS)的精算中心点过远，说明该坐标不可信。<br>
        <b>目标</b>：将 dim_cell_stats（小区维表）中每个小区(Cell)的 GPS 代表点与基站(BS)精算中心点做距离校验，超过阈值的小区(Cell) GPS 标记为异常。<br>
        <b>产出</b>：rebuild2.dim_cell_refined（小区(Cell)精算维表，含异常标记字段 gps_anomaly）
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">小区(Cell)总数</div><div class="stat-value blue">${fmt(overview.total_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">有 GPS 代表点的小区(Cell)</div><div class="stat-value green">${fmt(overview.cells_with_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">无 GPS 代表点的小区(Cell)</div><div class="stat-value orange">${fmt(overview.cells_no_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">所属基站(BS)有精算中心点的小区(Cell)</div><div class="stat-value">${fmt(overview.cells_bs_has_center)}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>校验参数</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2.2">
        小区(Cell) GPS 代表点到基站(BS)精算中心点的距离超过以下阈值，则将该小区(Cell) GPS 标记为异常（不可信），后续步骤不使用该坐标：<br>
        <b>4G 小区距离阈值</b>：${fmt(params.threshold_4g_m || 2000)} 米（4G 覆盖范围较大）<br>
        <b>5G 小区距离阈值</b>：${fmt(params.threshold_5g_m || 1000)} 米（5G 覆盖范围较小）<br>
        <b>注意</b>：仅当小区(Cell) GPS 和基站(BS)精算中心点同时存在时才进行校验；任意一方缺失则不做校验，沿用原始数据。
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>各运营商小区(Cell) GPS 覆盖情况</h3></div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'cell_count', label: '小区(Cell)总数', className: 'num', render: v => fmt(v) },
        { key: 'cells_with_gps', label: '有 GPS 的小区(Cell)', className: 'num', render: v => fmt(v) },
        { key: 'gps_coverage_rate', label: 'GPS 覆盖率', className: 'num', render: v => v != null ? (Number(v) * 100).toFixed(1) + '%' : '—' },
      ], byOp)}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:12px 24px;font-size:15px"
        onclick="executeStep2()">
        确认参数，执行小区(Cell) GPS 校验
      </button>
      <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">
        将通过 SSH 在服务器上执行，预计 2~5 分钟
      </div>
    </div>
  `;
}

function renderStep2Running() {
  if (!_pollTimer) {
    _pollTimer = setInterval(async () => {
      try {
        const s = await api('/enrich/step2/status', { ttl: 0, force: true });
        if (s.status !== 'running') {
          clearInterval(_pollTimer);
          _pollTimer = null;
          loadEnrich(true);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  return `
    ${renderStepNav()}
    <div class="card" style="text-align:center;padding:40px">
      <div class="loading" style="margin-bottom:16px">小区(Cell) GPS 校验执行中...</div>
      <div style="font-size:13px;color:var(--text-dim)">
        正在服务器上对小区维表做距离校验，请耐心等待<br>
        页面每 5 秒自动检查进度
      </div>
    </div>
  `;
}

async function renderStep2Result() {
  const data = await api('/enrich/step2/result', { ttl: 10000, force: true });
  if (!data.exists) {
    return renderStepNav() + '<div class="card"><div class="empty-state">校验结果表尚未创建</div></div>';
  }

  const t = data.totals || {};
  const byTech = data.by_tech || [];
  const bsQuality = data.bs_quality || [];
  const anomalyReasons = data.anomaly_reasons || [];
  const topAnomalies = data.top_anomalies || [];
  const anomalyRate = t.total_cells > 0 ? (t.anomaly_cells / t.total_cells * 100).toFixed(2) : '—';

  return `
    ${renderStepNav()}

    <div class="card">
      <div class="card-title"><h3>第二步结果：小区(Cell) GPS 校验维表</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">表名：rebuild2.dim_cell_refined</div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">小区(Cell)总数</div><div class="stat-value blue">${fmt(t.total_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">有 GPS 中心点的小区(Cell)</div><div class="stat-value green">${fmt(t.cells_with_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">标记为 GPS 异常的小区(Cell)</div><div class="stat-value" style="color:var(--red)">${fmt(t.anomaly_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">异常率</div><div class="stat-value orange">${anomalyRate}%</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>按制式校验结果</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        4G 小区(Cell)异常阈值：小区(Cell)中心到基站(BS)中心距离超过 2000 米；5G 阈值：超过 1000 米
      </div>
      ${renderTable([
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'cell_count', label: '小区(Cell)总数', className: 'num', render: v => fmt(v) },
        { key: 'with_gps', label: '有 GPS 的小区(Cell)', className: 'num', render: v => fmt(v) },
        { key: 'anomaly_count', label: '异常小区(Cell)数', className: 'num', render: v => `<span style="color:var(--red)">${fmt(v)}</span>` },
        { key: 'anomaly_rate', label: '异常率', className: 'num', render: (_, r) => r.cell_count > 0 ? (r.anomaly_count / r.cell_count * 100).toFixed(2) + '%' : '—' },
        { key: 'avg_dist_m', label: '平均偏差距离（米）', className: 'num', render: v => fmt(v) },
      ], byTech)}
    </div>

    <div class="card">
      <div class="card-title"><h3>异常原因分布</h3></div>
      ${renderTable([
        { key: 'gps_anomaly_reason', label: '异常原因', render: v => {
          if (v && v.includes('non5G')) return '4G 小区(Cell)偏差超 2000 米';
          if (v && v.includes('1000m(5G)')) return '5G 小区(Cell)偏差超 1000 米';
          return escapeHtml(v || '—');
        }},
        { key: 'cnt', label: '小区(Cell)数', className: 'num', render: v => fmt(v) },
      ], anomalyReasons)}
    </div>

    <div class="card">
      <div class="card-title"><h3>按基站(BS) GPS 质量分组</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        小区(Cell)异常可能是小区(Cell)本身 GPS 飘点，也可能因为所属基站(BS)的 GPS 质量等级较低
      </div>
      ${renderTable([
        { key: 'bs_gps_quality', label: '基站(BS) GPS 质量等级', render: v => qualityTag(v) },
        { key: 'cell_count', label: '该等级下小区(Cell)数', className: 'num', render: v => fmt(v) },
        { key: 'anomaly_count', label: '其中异常小区(Cell)', className: 'num', render: v => fmt(v) },
        { key: 'anomaly_rate', label: '异常率', className: 'num', render: (_, r) => r.cell_count > 0 ? (r.anomaly_count / r.cell_count * 100).toFixed(2) + '%' : '—' },
      ], bsQuality)}
    </div>

    <div class="card">
      <div class="card-title"><h3>异常小区(Cell) Top 20（按偏差距离排序）</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">偏差距离最大的小区(Cell)，可能是漫游用户上报的外地基站坐标</div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: '位置区' },
        { key: 'cell_id', label: '小区(Cell)编号', render: v => String(v) },
        { key: 'dist_to_bs_m', label: '偏差距离（米）', className: 'num', render: v => fmt(Math.round(v)) },
        { key: 'record_count', label: '记录数', className: 'num', render: v => fmt(v) },
        { key: 'bs_gps_quality', label: '基站(BS)质量', render: v => qualityTag(v) },
      ], topAnomalies)}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:10px 24px"
        onclick="switchEnrichStep('step3')">
        下一步：明细行 GPS 修正 →
      </button>
    </div>
  `;
}

window.executeStep2 = async function () {
  if (!confirm('确认执行小区(Cell) GPS 校验？\n\n将通过 SSH 在服务器上执行，预计 2~5 分钟。\n已有 dim_cell_refined 将被重建。')) return;
  const btn = document.querySelector('button[onclick="executeStep2()"]');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const result = await api('/enrich/step2/execute', { method: 'POST', force: true });
    if (result.ok) {
      showToast('小区(Cell) GPS 校验已启动');
      loadEnrich(true);
    } else {
      showToast('启动失败: ' + (result.error || ''));
      if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行小区(Cell) GPS 校验'; }
    }
  } catch (e) {
    showToast('启动失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行小区(Cell) GPS 校验'; }
  }
};

// ════════════════════════════════════════════════════════════
//  第三步：明细行 GPS 修正
// ════════════════════════════════════════════════════════════

async function loadStep3() {
  const status = await api('/enrich/step3/status', { ttl: 3000, force: true });

  if (status.status === 'running') {
    return renderStep3Running();
  }
  if (status.status === 'done') {
    return await renderStep3Result();
  }
  return await renderStep3Preview(status);
}

async function renderStep3Preview(status) {
  const data = await api('/enrich/step3/preview', { ttl: 10000, force: true });
  const overview = data.row_overview || {};
  const methods = data.fix_methods || [];
  const estimated = data.estimated_counts || {};

  const errorHtml = status?.status === 'error'
    ? `<div class="card" style="border-left:3px solid var(--red);margin-bottom:16px">
        <div class="card-title"><h3 style="color:var(--red)">上次执行失败</h3></div>
        <pre style="font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(status.stderr || status.message || '')}</pre>
       </div>` : '';

  return `
    ${renderStepNav()}
    ${errorHtml}

    <div class="card">
      <div class="card-title"><h3>第三步：明细行 GPS 修正</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>问题</b>：明细行中许多记录的 GPS 字段为空，或者已在第二步被标记为异常（飘点），无法直接用于定位。<br>
        <b>目标</b>：按优先级逐级回填 GPS——优先用小区(Cell)精算中心点，其次用基站(BS)精算中心点（可用级），再次用基站(BS)精算中心点（风险级），最后标记为无法填充。<br>
        <b>产出</b>：明细表增加 gps_lon_fixed、gps_lat_fixed、gps_source 三个字段
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">明细行总数</div><div class="stat-value blue">${fmt(overview.total_rows)}</div></div>
      <div class="stat-box"><div class="stat-label">原始 GPS 有效行</div><div class="stat-value green">${fmt(overview.rows_with_valid_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">GPS 为空或异常的行</div><div class="stat-value orange">${fmt(overview.rows_need_fix)}</div></div>
      <div class="stat-box"><div class="stat-label">GPS 缺失率</div><div class="stat-value">${overview.missing_rate != null ? (Number(overview.missing_rate) * 100).toFixed(1) + '%' : '—'}</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>GPS 回填优先级策略</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        对于 GPS 缺失或异常的行，按以下优先级依次尝试回填：
      </div>
      ${renderTable([
        { key: 'priority', label: '优先级', className: 'num' },
        { key: 'source_label', label: '回填来源' },
        { key: 'condition', label: '使用条件' },
        { key: 'gps_source_value', label: 'gps_source 字段值' },
      ], [
        { priority: 1, source_label: '原始上报 GPS', condition: '明细行 GPS 有效且小区未标记异常', gps_source_value: '原始上报 GPS' },
        { priority: 2, source_label: '小区(Cell)精算中心点', condition: '小区维表有 GPS 代表点且未被标记为异常', gps_source_value: '小区(Cell)精算中心点' },
        { priority: 3, source_label: '基站(BS)精算中心点（可用）', condition: '基站(BS)质量等级为"可用"', gps_source_value: '基站(BS)精算中心点（可用）' },
        { priority: 4, source_label: '基站(BS)精算中心点（风险）', condition: '基站(BS)质量等级为"风险"', gps_source_value: '基站(BS)精算中心点（风险）' },
        { priority: 5, source_label: '未能填充', condition: '以上来源均不可用', gps_source_value: '未能填充' },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>预估各回填来源行数</h3></div>
      ${renderTable([
        { key: 'source', label: '回填来源' },
        { key: 'estimated_rows', label: '预估行数', className: 'num', render: v => fmt(v) },
        { key: 'estimated_pct', label: '预估占比', className: 'num', render: v => v != null ? (Number(v) * 100).toFixed(1) + '%' : '—' },
      ], (methods.length ? methods : [
        { source: '原始上报 GPS', estimated_rows: estimated.original, estimated_pct: estimated.original_pct },
        { source: '小区(Cell)精算中心点', estimated_rows: estimated.cell_center, estimated_pct: estimated.cell_center_pct },
        { source: '基站(BS)精算中心点（可用）', estimated_rows: estimated.bs_center, estimated_pct: estimated.bs_center_pct },
        { source: '基站(BS)精算中心点（风险）', estimated_rows: estimated.bs_center_risk, estimated_pct: estimated.bs_center_risk_pct },
        { source: '未能填充', estimated_rows: estimated.not_filled, estimated_pct: estimated.not_filled_pct },
      ]))}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:12px 24px;font-size:15px"
        onclick="executeStep3()">
        确认策略，执行明细行 GPS 修正
      </button>
      <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">
        将通过 SSH 在服务器上执行，处理明细行数据，预计 10~30 分钟
      </div>
    </div>
  `;
}

function renderStep3Running() {
  if (!_pollTimer) {
    _pollTimer = setInterval(async () => {
      try {
        const s = await api('/enrich/step3/status', { ttl: 0, force: true });
        if (s.status !== 'running') {
          clearInterval(_pollTimer);
          _pollTimer = null;
          loadEnrich(true);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  return `
    ${renderStepNav()}
    <div class="card" style="text-align:center;padding:40px">
      <div class="loading" style="margin-bottom:16px">明细行 GPS 修正执行中...</div>
      <div style="font-size:13px;color:var(--text-dim)">
        正在服务器上对所有明细行进行 GPS 回填，数据量较大请耐心等待<br>
        页面每 5 秒自动检查进度
      </div>
    </div>
  `;
}

async function renderStep3Result() {
  const data = await api('/enrich/step3/result', { ttl: 10000, force: true });
  if (!data.exists) {
    return renderStepNav() + '<div class="card"><div class="empty-state">GPS 修正结果尚未创建</div></div>';
  }

  const t = data.totals || {};
  const sourceDist = data.source_distribution || [];
  const totalRows = t.total_rows || 0;

  // 构建漏斗数据：按优先级排列，逐级累减
  const sourceMap = {};
  sourceDist.forEach(r => { sourceMap[r.gps_source] = r.row_count; });
  const s1 = sourceMap['original'] || 0;
  const s2 = sourceMap['cell_center'] || 0;
  const s3 = sourceMap['bs_center'] || 0;
  const s4 = sourceMap['bs_center_risk'] || 0;
  const s5 = sourceMap['not_filled'] || 0;
  const remain1 = totalRows - s1;
  const remain2 = remain1 - s2;
  const remain3 = remain2 - s3;

  return `
    ${renderStepNav()}

    <div class="card">
      <div class="card-title"><h3>第三步结果：明细行 GPS 修正</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        数据表：rebuild2.${t.data_table || 'dwd_fact_enriched'} &nbsp;|&nbsp;
        GPS 覆盖率从原始约 84% 提升到 <b>${t.gps_coverage_pct || '—'}%</b>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">明细行总数</div><div class="stat-value blue">${fmt(totalRows)}</div></div>
      <div class="stat-box"><div class="stat-label">GPS 已填充</div><div class="stat-value green">${fmt(t.rows_with_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">未能填充</div><div class="stat-value" style="color:var(--red)">${fmt(t.rows_no_gps)}</div></div>
      <div class="stat-box"><div class="stat-label">最终 GPS 覆盖率</div><div class="stat-value">${t.gps_coverage_pct || '—'}%</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>GPS 修正漏斗</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        按优先级从高到低逐级处理，每级处理后剩余的行数进入下一级
      </div>
      <div style="margin-top:12px">
        ${_funnelStep(1, '输入', '可信 LAC 范围内全部明细行', totalRows, totalRows, null, 'blue')}
        ${_funnelStep(2, '保留原始 GPS', '原始 GPS 有效，且到小区(Cell)中心距离在阈值内（4G≤1000米，5G≤500米）', s1, totalRows, remain1, 'green')}
        ${_funnelStep(3, '小区(Cell)中心点回填', '原始 GPS 缺失或超阈值 → 用小区(Cell)精算中心点替代', s2, totalRows, remain2, 'blue')}
        ${_funnelStep(4, '基站(BS)中心点回填（可用）', '小区(Cell)无有效 GPS → 用基站(BS)精算中心点（质量等级"可用"）', s3, totalRows, remain3, 'orange')}
        ${_funnelStep(5, '基站(BS)中心点回填（风险）', '基站(BS)质量等级为"风险"，回填但标记风险', s4, totalRows, s5, 'orange')}
        ${_funnelStep(6, '未能填充', '基站(BS)质量等级为"不可用"，无可用坐标来源，止损不回填', s5, totalRows, null, 'red')}
      </div>
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:10px 24px"
        onclick="switchEnrichStep('step4')">
        下一步：信号补齐 →
      </button>
    </div>
  `;
}

window.executeStep3 = async function () {
  if (!confirm('确认执行明细行 GPS 修正？\n\n将通过 SSH 在服务器上执行，处理所有明细行数据，预计 10~30 分钟。\n明细表将新增 gps_lon_fixed、gps_lat_fixed、gps_source 字段。')) return;
  const btn = document.querySelector('button[onclick="executeStep3()"]');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const result = await api('/enrich/step3/execute', { method: 'POST', force: true });
    if (result.ok) {
      showToast('明细行 GPS 修正已启动');
      loadEnrich(true);
    } else {
      showToast('启动失败: ' + (result.error || ''));
      if (btn) { btn.disabled = false; btn.textContent = '确认策略，执行明细行 GPS 修正'; }
    }
  } catch (e) {
    showToast('启动失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '确认策略，执行明细行 GPS 修正'; }
  }
};

// ════════════════════════════════════════════════════════════
//  第四步：信号补齐
// ════════════════════════════════════════════════════════════

async function loadStep4() {
  const status = await api('/enrich/step4/status', { ttl: 3000, force: true });

  if (status.status === 'running') {
    return renderStep4Running();
  }
  if (status.status === 'done') {
    return await renderStep4Result();
  }
  return await renderStep4Preview(status);
}

async function renderStep4Preview(status) {
  const data = await api('/enrich/step4/preview', { ttl: 10000, force: true });
  const coverage = data.signal_coverage || {};
  const params = data.params || {};

  const errorHtml = status?.status === 'error'
    ? `<div class="card" style="border-left:3px solid var(--red);margin-bottom:16px">
        <div class="card-title"><h3 style="color:var(--red)">上次执行失败</h3></div>
        <pre style="font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(status.stderr || status.message || '')}</pre>
       </div>` : '';

  return `
    ${renderStepNav()}
    ${errorHtml}

    <div class="card">
      <div class="card-title"><h3>第四步：信号补齐</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>问题</b>：明细行中部分信号指标（RSRP、RSRQ、SINR、信号强度 dBm）为空或为无效占位值，影响后续分析精度。<br>
        <b>目标</b>：利用同一小区同一时间段内其他记录的信号值，对缺失信号进行中位数补齐，提升信号字段覆盖率。<br>
        <b>产出</b>：明细表新增 rsrp_filled、rsrq_filled、sinr_filled、dbm_filled 字段
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>当前信号字段覆盖率（补齐前）</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">统计明细表中各信号字段的非空有效覆盖情况</div>
      <div class="stat-grid" style="margin-top:8px">
        <div class="stat-box">
          <div class="stat-label">RSRP（参考信号接收功率）覆盖率</div>
          <div class="stat-value ${coverage.rsrp_rate >= 0.8 ? 'green' : coverage.rsrp_rate >= 0.5 ? 'orange' : ''}">${coverage.rsrp_rate != null ? (Number(coverage.rsrp_rate) * 100).toFixed(1) + '%' : '—'}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">RSRQ（参考信号接收质量）覆盖率</div>
          <div class="stat-value ${coverage.rsrq_rate >= 0.8 ? 'green' : coverage.rsrq_rate >= 0.5 ? 'orange' : ''}">${coverage.rsrq_rate != null ? (Number(coverage.rsrq_rate) * 100).toFixed(1) + '%' : '—'}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">SINR（信号与干扰加噪声比）覆盖率</div>
          <div class="stat-value ${coverage.sinr_rate >= 0.8 ? 'green' : coverage.sinr_rate >= 0.5 ? 'orange' : ''}">${coverage.sinr_rate != null ? (Number(coverage.sinr_rate) * 100).toFixed(1) + '%' : '—'}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">信号强度（dBm）覆盖率</div>
          <div class="stat-value ${coverage.dbm_rate >= 0.8 ? 'green' : coverage.dbm_rate >= 0.5 ? 'orange' : ''}">${coverage.dbm_rate != null ? (Number(coverage.dbm_rate) * 100).toFixed(1) + '%' : '—'}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>信号指标空值情况（补齐前）</h3></div>
      ${renderTable([
        { key: 'field_label', label: '信号指标' },
        { key: 'total_rows', label: '总行数', className: 'num', render: v => fmt(v) },
        { key: 'null_rows', label: '空值行数', className: 'num', render: v => fmt(v) },
        { key: 'null_rate', label: '空值率', className: 'num', render: v => v != null ? (Number(v) * 100).toFixed(2) + '%' : '—' },
      ], [
        { field_label: 'RSRP（参考信号接收功率）', total_rows: coverage.total_rows, null_rows: coverage.rsrp_null, null_rate: coverage.rsrp_null_rate },
        { field_label: 'RSRQ（参考信号接收质量）', total_rows: coverage.total_rows, null_rows: coverage.rsrq_null, null_rate: coverage.rsrq_null_rate },
        { field_label: 'SINR（信号与干扰加噪声比）', total_rows: coverage.total_rows, null_rows: coverage.sinr_null, null_rate: coverage.sinr_null_rate },
        { field_label: '信号强度（dBm）', total_rows: coverage.total_rows, null_rows: coverage.dbm_null, null_rate: coverage.dbm_null_rate },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>补齐参数</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2.2">
        <b>补齐方法</b>：${params.fill_method || '同一小区同一时段中位数补齐'}<br>
        <b>分组维度</b>：${params.group_by || '运营商 + 制式 + 位置区编码 + 基站(BS)编号 + 小区(Cell)编号'}<br>
        <b>时间粒度</b>：${params.time_granularity || '按小时分组'}<br>
        <b>无效值过滤</b>：RSRP 值为 ${(params.rsrp_invalid_values || [0, -999, 999]).join('、')} 的记录不参与补齐计算，视为无效上报
      </div>
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:12px 24px;font-size:15px"
        onclick="executeStep4()">
        确认参数，执行信号补齐
      </button>
      <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">
        将通过 SSH 在服务器上执行，处理全量明细行，预计 10~20 分钟
      </div>
    </div>
  `;
}

function renderStep4Running() {
  if (!_pollTimer) {
    _pollTimer = setInterval(async () => {
      try {
        const s = await api('/enrich/step4/status', { ttl: 0, force: true });
        if (s.status !== 'running') {
          clearInterval(_pollTimer);
          _pollTimer = null;
          loadEnrich(true);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  return `
    ${renderStepNav()}
    <div class="card" style="text-align:center;padding:40px">
      <div class="loading" style="margin-bottom:16px">信号补齐执行中...</div>
      <div style="font-size:13px;color:var(--text-dim)">
        正在服务器上对全量明细行进行信号字段补齐，请耐心等待<br>
        页面每 5 秒自动检查进度
      </div>
    </div>
  `;
}

async function renderStep4Result() {
  const data = await api('/enrich/step4/result', { ttl: 10000, force: true });
  if (!data.exists) {
    return renderStepNav() + '<div class="card"><div class="empty-state">信号补齐结果尚未创建</div></div>';
  }

  const t = data.totals || {};
  const fillDist = data.signal_fill_distribution || [];
  const crossTab = data.gps_signal_cross || [];
  const totalRows = t.total_rows || 0;

  // 信号覆盖率
  const rsrpRate = totalRows > 0 ? (t.rsrp_filled / totalRows * 100).toFixed(2) : '—';
  const rsrqRate = totalRows > 0 ? (t.rsrq_filled / totalRows * 100).toFixed(2) : '—';
  const sinrRate = totalRows > 0 ? (t.sinr_filled / totalRows * 100).toFixed(2) : '—';
  const dbmRate  = totalRows > 0 ? (t.dbm_filled / totalRows * 100).toFixed(2) : '—';

  // 信号补齐来源
  function signalSourceLabel(src) {
    const m = { 'original': '原始记录有信号', 'cell_fill': '同小区(Cell)最近记录补齐', 'unfilled': '未能补齐（无同小区信号记录）' };
    return m[src] || src || '—';
  }

  // 漏斗数据（只有 original → cell_fill → unfilled，跨小区补齐已废弃）
  const sigMap = {};
  fillDist.forEach(r => { sigMap[r.signal_fill_source] = r.row_count; });
  const sig1 = sigMap['original'] || 0;
  const sig2 = sigMap['cell_fill'] || 0;
  const sig4 = (sigMap['unfilled'] || 0) + (sigMap['bs_fill'] || 0); // bs_fill 已合并到 unfilled
  const sigRemain1 = totalRows - sig1;

  // cell_fill 时间差分布（从元数据）
  const timeDelta = data.cell_fill_time_delta || {};

  // 交叉表
  const crossRows = (crossTab || []).map(r => ({
    gps_label: gpsSourceLabel(r.gps_source),
    signal_label: signalSourceLabel(r.signal_fill_source),
    cnt: r.cnt,
  }));

  return `
    ${renderStepNav()}

    <div class="card">
      <div class="card-title"><h3>第四步结果：信号补齐</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">数据表：rebuild2.dwd_fact_enriched</div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">明细行总数</div><div class="stat-value blue">${fmt(totalRows)}</div></div>
      <div class="stat-box"><div class="stat-label">RSRP 覆盖率</div><div class="stat-value green">${rsrpRate}%</div></div>
      <div class="stat-box"><div class="stat-label">RSRQ 覆盖率</div><div class="stat-value green">${rsrqRate}%</div></div>
      <div class="stat-box"><div class="stat-label">SINR 覆盖率</div><div class="stat-value">${sinrRate}%</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>信号补齐漏斗</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        信号只能用同小区(Cell)内的记录补齐（跨小区的信号无物理意义，已废弃）
      </div>
      <div style="margin-top:12px">
        ${_funnelStep(1, '输入', '第三步 GPS 修正后的全部明细行', totalRows, totalRows, null, 'blue')}
        ${_funnelStep(2, '原始记录有信号', '明细行本身的 RSRP 等信号字段已有值，无需补齐', sig1, totalRows, sigRemain1, 'green')}
        ${_funnelStep(3, '同小区(Cell)最近记录补齐', '在同一小区(Cell)内，按上报时间找前后最近的有信号记录，逐字段补齐', sig2, totalRows, sig4, 'blue')}
        ${_funnelStep(4, '未能补齐', '同小区(Cell)范围内无可用信号记录（跨小区补齐已废弃，不使用其他小区的信号值）', sig4, totalRows, null, 'red')}
      </div>
    </div>

    ${timeDelta.total ? `
    <div class="card">
      <div class="card-title"><h3>同小区(Cell)补齐的时间差分布</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        补齐记录与最近有信号记录之间的时间间隔。时间差越小，补齐值越可信。超过 1 小时的需要关注。
      </div>
      ${renderTable([
        { key: 'range', label: '时间差范围' },
        { key: 'count', label: '行数', className: 'num', render: v => fmt(v) },
        { key: 'pct', label: '占比', className: 'num' },
        { key: 'note', label: '可信度' },
      ], [
        { range: '1 分钟以内', count: timeDelta.within_1min, pct: timeDelta.total > 0 ? (timeDelta.within_1min / timeDelta.total * 100).toFixed(1) + '%' : '—', note: '高可信' },
        { range: '1 ~ 5 分钟', count: timeDelta.within_5min, pct: timeDelta.total > 0 ? (timeDelta.within_5min / timeDelta.total * 100).toFixed(1) + '%' : '—', note: '可信' },
        { range: '5 分钟 ~ 1 小时', count: timeDelta.within_1hour, pct: timeDelta.total > 0 ? (timeDelta.within_1hour / timeDelta.total * 100).toFixed(1) + '%' : '—', note: '可接受' },
        { range: '超过 1 小时', count: timeDelta.over_1hour, pct: timeDelta.total > 0 ? (timeDelta.over_1hour / timeDelta.total * 100).toFixed(1) + '%' : '—', note: '需关注' },
        { range: '无同小区(Cell)信号记录', count: timeDelta.no_donor, pct: timeDelta.total > 0 ? (timeDelta.no_donor / timeDelta.total * 100).toFixed(1) + '%' : '—', note: '质量存疑' },
      ])}
    </div>
    ` : ''}

    <div class="card">
      <div class="card-title"><h3>各信号字段最终覆盖率</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">补齐后各信号字段的非空行数及覆盖率</div>
      ${renderTable([
        { key: 'field', label: '信号指标' },
        { key: 'filled', label: '有值行数', className: 'num', render: v => fmt(v) },
        { key: 'missing', label: '仍为空的行数', className: 'num', render: v => fmt(v) },
        { key: 'rate', label: '最终覆盖率', className: 'num' },
      ], [
        { field: 'RSRP（参考信号接收功率）', filled: t.rsrp_filled, missing: totalRows - (t.rsrp_filled || 0), rate: rsrpRate + '%' },
        { field: 'RSRQ（参考信号接收质量）', filled: t.rsrq_filled, missing: totalRows - (t.rsrq_filled || 0), rate: rsrqRate + '%' },
        { field: 'SINR（信号与干扰加噪声比）', filled: t.sinr_filled, missing: totalRows - (t.sinr_filled || 0), rate: sinrRate + '%' },
        { field: '信号强度 dBm', filled: t.dbm_filled, missing: totalRows - (t.dbm_filled || 0), rate: dbmRate + '%' },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>GPS 来源 × 信号来源 交叉统计</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">展示 GPS 修正和信号补齐两个维度的组合分布（前 20 组）</div>
      ${renderTable([
        { key: 'gps_label', label: 'GPS 来源' },
        { key: 'signal_label', label: '信号来源' },
        { key: 'cnt', label: '行数', className: 'num', render: v => fmt(v) },
      ], crossRows)}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:10px 24px"
        onclick="switchEnrichStep('step5')">
        下一步：回算 →
      </button>
    </div>
  `;
}

window.executeStep4 = async function () {
  if (!confirm('确认执行信号补齐？\n\n将通过 SSH 在服务器上执行，处理全量明细行，预计 10~20 分钟。\n明细表将新增 rsrp_filled、rsrq_filled、sinr_filled、dbm_filled 字段。')) return;
  const btn = document.querySelector('button[onclick="executeStep4()"]');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const result = await api('/enrich/step4/execute', { method: 'POST', force: true });
    if (result.ok) {
      showToast('信号补齐已启动');
      loadEnrich(true);
    } else {
      showToast('启动失败: ' + (result.error || ''));
      if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行信号补齐'; }
    }
  } catch (e) {
    showToast('启动失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '确认参数，执行信号补齐'; }
  }
};

// ════════════════════════════════════════════════════════════
//  第五步：回算
// ════════════════════════════════════════════════════════════

async function loadStep5() {
  const status = await api('/enrich/step5/status', { ttl: 3000, force: true });

  if (status.status === 'running') {
    return renderStep5Running();
  }
  if (status.status === 'done') {
    return await renderStep5Result();
  }
  return await renderStep5Preview(status);
}

async function renderStep5Preview(status) {
  const data = await api('/enrich/step5/preview', { ttl: 10000, force: true });
  const overview = data.recalc_overview || {};

  const errorHtml = status?.status === 'error'
    ? `<div class="card" style="border-left:3px solid var(--red);margin-bottom:16px">
        <div class="card-title"><h3 style="color:var(--red)">上次执行失败</h3></div>
        <pre style="font-size:12px;max-height:200px;overflow:auto;white-space:pre-wrap">${escapeHtml(status.stderr || status.message || '')}</pre>
       </div>` : '';

  return `
    ${renderStepNav()}
    ${errorHtml}

    <div class="card">
      <div class="card-title"><h3>第五步：回算</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        <b>问题</b>：经过前四步处理，明细行的 GPS 和信号字段已得到补齐和修正。但原来用于生成小区/基站(BS)中心点的汇总维表，是基于补齐之前的明细行计算的，存在偏差。<br>
        <b>目标</b>：以补齐后的全量明细行为基础，重新计算小区(Cell)精算中心点（dim_cell_refined）和基站(BS)精算中心点（dim_bs_refined），使中心点更准确地反映实际位置。<br>
        <b>产出</b>：dim_cell_refined 和 dim_bs_refined 两张维表的中心点字段更新
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>回算涉及的数据规模</h3></div>
      <div class="stat-grid" style="margin-top:8px">
        <div class="stat-box"><div class="stat-label">明细行总数（含补齐）</div><div class="stat-value blue">${fmt(overview.total_rows)}</div></div>
        <div class="stat-box"><div class="stat-label">有 GPS 的明细行</div><div class="stat-value green">${fmt(overview.rows_with_gps)}</div></div>
        <div class="stat-box"><div class="stat-label">参与回算的小区(Cell)数</div><div class="stat-value">${fmt(overview.cells_to_recalc)}</div></div>
        <div class="stat-box"><div class="stat-label">参与回算的基站(BS)数</div><div class="stat-value">${fmt(overview.bs_to_recalc)}</div></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><h3>回算步骤说明</h3></div>
      ${renderTable([
        { key: 'step_no', label: '步骤', className: 'num' },
        { key: 'action', label: '操作' },
        { key: 'target_table', label: '目标表' },
        { key: 'description', label: '说明' },
      ], [
        {
          step_no: 1,
          action: '重算小区(Cell)中心点',
          target_table: 'dim_cell_refined',
          description: '以补齐后的 GPS 坐标为来源，重新计算每个小区(Cell)的 GPS 代表点（中位数），并重新做异常标记校验',
        },
        {
          step_no: 2,
          action: '重算基站(BS)中心点',
          target_table: 'dim_bs_refined',
          description: '以更新后的小区(Cell)中心点为基础，重新计算每个基站的精算中心点，并更新质量分级',
        },
        {
          step_no: 3,
          action: '更新明细行关联',
          target_table: '明细表',
          description: '用回算后的小区(Cell)/基站(BS)中心点重新填充明细行中 gps_source 为"小区(Cell)精算中心点"或"基站(BS)精算中心点"的记录',
        },
      ])}
    </div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" style="min-width:280px;padding:12px 24px;font-size:15px"
        onclick="executeStep5()">
        确认，执行回算
      </button>
      <div style="margin-top:8px;font-size:12px;color:var(--text-dim)">
        将通过 SSH 在服务器上执行，预计 15~30 分钟
      </div>
    </div>
  `;
}

function renderStep5Running() {
  if (!_pollTimer) {
    _pollTimer = setInterval(async () => {
      try {
        const s = await api('/enrich/step5/status', { ttl: 0, force: true });
        if (s.status !== 'running') {
          clearInterval(_pollTimer);
          _pollTimer = null;
          loadEnrich(true);
        }
      } catch { /* ignore */ }
    }, 5000);
  }

  return `
    ${renderStepNav()}
    <div class="card" style="text-align:center;padding:40px">
      <div class="loading" style="margin-bottom:16px">回算执行中...</div>
      <div style="font-size:13px;color:var(--text-dim)">
        正在服务器上重新计算小区与基站(BS)中心点，请耐心等待<br>
        页面每 5 秒自动检查进度
      </div>
    </div>
  `;
}

async function renderStep5Result() {
  const data = await api('/enrich/step5/result', { ttl: 10000, force: true });
  if (!data.exists) {
    return renderStepNav() + '<div class="card"><div class="empty-state">回算结果尚未生成</div></div>';
  }

  const cell = data.cell_drift || {};
  const bs   = data.bs_drift || {};
  const topDrifts = data.top_cell_drifts || [];

  return `
    ${renderStepNav()}

    <div class="card">
      <div class="card-title"><h3>第五步结果：回算完成</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">dim_cell_refined 与 dim_bs_refined 的中心点字段已基于补齐后的明细行重新计算</div>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">小区(Cell)新增中心点</div><div class="stat-value green">${fmt(cell.newly_covered_cells)}</div></div>
      <div class="stat-box"><div class="stat-label">基站(BS)新增中心点</div><div class="stat-value green">${fmt(bs.newly_covered_bs)}</div></div>
      <div class="stat-box"><div class="stat-label">小区偏移超 100 米</div><div class="stat-value orange">${fmt(cell.drift_gt_100m)}</div></div>
      <div class="stat-box"><div class="stat-label">基站(BS)平均偏移</div><div class="stat-value">${fmt(bs.avg_drift_m)} 米</div></div>
    </div>

    <div class="card">
      <div class="card-title"><h3>小区(Cell)中心点回算前后对比</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        对比回算前后 dim_cell_refined 中每个小区(Cell)的 GPS 代表点变化情况
      </div>
      ${renderTable([
        { key: 'metric', label: '指标' },
        { key: 'value', label: '数值', className: 'num', render: v => fmt(v) },
        { key: 'note', label: '说明' },
      ], [
        { metric: '参与对比的小区(Cell)', value: cell.comparable_cells, note: '回算前后均有中心点的小区(Cell)' },
        { metric: '偏移超过 100 米的小区(Cell)', value: cell.drift_gt_100m, note: '回算显著修正了小区位置' },
        { metric: '偏移超过 500 米的小区(Cell)', value: cell.drift_gt_500m, note: '回算大幅修正了小区位置' },
        { metric: '平均偏移距离', value: cell.avg_drift_m, note: '单位：米' },
        { metric: '回算后新增中心点的小区(Cell)', value: cell.newly_covered_cells, note: '补齐前无 GPS、补齐后有 GPS 的小区(Cell)' },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>基站(BS)中心点回算前后对比</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">
        对比回算前后 dim_bs_refined 中每个基站的精算中心点变化情况
      </div>
      ${renderTable([
        { key: 'metric', label: '指标' },
        { key: 'value', label: '数值', className: 'num', render: v => fmt(v) },
        { key: 'note', label: '说明' },
      ], [
        { metric: '参与对比的基站(BS)', value: bs.comparable_bs, note: '回算前后均有中心点的基站(BS)' },
        { metric: '偏移超过 100 米的基站(BS)', value: bs.drift_gt_100m, note: '回算显著修正了基站位置' },
        { metric: '偏移超过 500 米的基站(BS)', value: bs.drift_gt_500m, note: '回算大幅修正了基站位置' },
        { metric: '平均偏移距离', value: bs.avg_drift_m, note: '单位：米' },
        { metric: '回算后新增中心点的基站(BS)', value: bs.newly_covered_bs, note: '补齐前无 GPS、补齐后有 GPS 的基站(BS)' },
      ])}
    </div>

    <div class="card">
      <div class="card-title"><h3>偏移最大的小区(Cell) Top 20</h3></div>
      <div style="padding:4px 0;font-size:13px;color:var(--text-dim)">回算前后中心点偏移距离最大的小区(Cell)，可能是漫游用户上报导致的外地坐标被修正</div>
      ${renderTable([
        { key: 'operator_cn', label: '运营商', render: v => operatorTag(v) },
        { key: 'tech_norm', label: '制式', render: v => techTag(v) },
        { key: 'lac', label: '位置区' },
        { key: 'cell_id', label: '小区(Cell)编号', render: v => String(v) },
        { key: 'drift_m', label: '偏移距离（米）', className: 'num', render: v => fmt(v) },
        { key: 'gps_center_lon', label: '回算前经度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
        { key: 'gps_center_lon_recalc', label: '回算后经度', className: 'num', render: v => v ? Number(v).toFixed(4) : '—' },
      ], topDrifts)}
    </div>

    <div class="card" style="border-left:3px solid var(--green)">
      <div class="card-title"><h3 style="color:var(--green)">全流程处理完成</h3></div>
      <div style="padding:8px 0;font-size:13px;color:var(--text-dim);line-height:2">
        已完成全部五个步骤：基站(BS)中心点精算 → 小区(Cell) GPS 校验 → 明细行 GPS 修正 → 信号补齐 → 回算。<br>
        最终产出表 rebuild2.dwd_fact_enriched（${fmt(30082381)} 行），GPS 覆盖率 99.99%，信号覆盖率 99.98%。
      </div>
    </div>
  `;
}

window.executeStep5 = async function () {
  if (!confirm('确认执行回算？\n\n将通过 SSH 在服务器上重新计算小区与基站(BS)中心点，预计 15~30 分钟。\ndim_cell_refined 和 dim_bs_refined 的中心点字段将被更新。')) return;
  const btn = document.querySelector('button[onclick="executeStep5()"]');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const result = await api('/enrich/step5/execute', { method: 'POST', force: true });
    if (result.ok) {
      showToast('回算已启动');
      loadEnrich(true);
    } else {
      showToast('启动失败: ' + (result.error || ''));
      if (btn) { btn.disabled = false; btn.textContent = '确认，执行回算'; }
    }
  } catch (e) {
    showToast('启动失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '确认，执行回算'; }
  }
};

// ════════════════════════════════════════════════════════════
//  入口
// ════════════════════════════════════════════════════════════

export async function loadEnrich(force = false) {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }

  setMain('<div class="loading">加载基站定位与信号补齐...</div>');
  try {
    // 刷新各步骤完成状态，用于导航按钮启用控制
    await refreshStepDoneFlags();

    let content;
    switch (currentStep) {
      case 'step1': content = await loadStep1(); break;
      case 'step2': content = await loadStep2(); break;
      case 'step3': content = await loadStep3(); break;
      case 'step4': content = await loadStep4(); break;
      case 'step5': content = await loadStep5(); break;
      default:
        content = renderStepNav() +
          '<div class="card"><div class="empty-state">该步骤尚未实现，请先完成前置步骤</div></div>';
    }
    setMain(`
      <div class="page-head"><div>
        <h2>基站定位与信号补齐</h2>
        <p>Phase 3：基站(BS)中心点精算 → 小区(Cell) GPS 校验 → 明细行 GPS 修正 → 信号补齐 → 回算</p>
      </div></div>
      ${content}
    `);
  } catch (error) {
    setMain(pageError('基站定位与信号补齐加载失败', error));
  }
}
