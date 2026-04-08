/**
 * 原始数据 · 字段挑选页。
 * 两张源表结构一致（27 列），统一为一份决策。
 */

import { api } from '../core/api.js';
import { state } from '../core/state.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, showToast, renderTable, openDrawer,
} from '../ui/common.js';

const DECISIONS = [
  { value: 'pending',   label: '待定',   color: 'tag-gray' },
  { value: 'keep',      label: '保留',   color: 'tag-green' },
  { value: 'rename',    label: '重命名', color: 'tag-blue' },
  { value: 'transform', label: '转换',   color: 'tag-blue' },
  { value: 'parse',     label: '解析',   color: 'tag-orange' },
  { value: 'merge',     label: '合并',   color: 'tag-orange' },
  { value: 'drop',      label: '丢弃',   color: 'tag-red' },
  { value: 'defer',     label: '延迟',   color: 'tag-gray' },
];

function decisionSelect(columnName, current) {
  const opts = DECISIONS.map(d =>
    `<option value="${d.value}" ${d.value === current ? 'selected' : ''}>${d.label}</option>`
  ).join('');
  return `<select class="decision-select" onchange="saveDecision('${escapeHtml(columnName)}', this.value)">${opts}</select>`;
}

function categoryTag(cat) {
  const colors = { '核心': 'tag-orange', '标识': 'tag-blue', '时间': 'tag-green', '网络': 'tag-blue', '位置': 'tag-green', '信号': 'tag-orange', '元数据': 'tag-gray' };
  return `<span class="tag ${colors[cat] || 'tag-gray'}">${escapeHtml(cat || '—')}</span>`;
}

function nullRateBar(frac) {
  if (frac == null) return '<span style="color:var(--text-dim)">—</span>';
  const v = (frac * 100).toFixed(1);
  const color = frac < 0.05 ? 'var(--green)' : frac < 0.3 ? 'var(--orange)' : 'var(--red)';
  return `<div class="compliance-bar"><div class="compliance-fill" style="width:${v}%;background:${color}"></div><span>${v}%</span></div>`;
}

async function saveDecision(columnName, decision) {
  try {
    await api('/audit/decisions', {
      method: 'PUT',
      body: { column_name: columnName, decision },
      ttl: 0,
    });
    const item = state.decisions.find(d => d.column_name === columnName);
    if (item) item.decision = decision;
    updateSummary();
    showToast(`${columnName}: ${DECISIONS.find(d => d.value === decision)?.label}`);
  } catch (e) {
    showToast(`保存失败: ${e.message}`, 3000);
  }
}
window.saveDecision = saveDecision;

function updateSummary() {
  const el = document.getElementById('decision-summary');
  if (!el) return;
  const counts = {};
  DECISIONS.forEach(d => { counts[d.value] = 0; });
  state.decisions.forEach(d => { counts[d.decision] = (counts[d.decision] || 0) + 1; });
  el.innerHTML = DECISIONS.map(d =>
    `<div class="stat-box"><div class="stat-label">${d.label}</div><div class="stat-value">${counts[d.value]}</div></div>`
  ).join('');
}

async function viewRawFieldDetail(columnName) {
  const [sampleData, distData] = await Promise.all([
    api(`/audit/fields/${encodeURIComponent(columnName)}/sample?limit=30`, { ttl: 120000 }),
    api(`/audit/fields/${encodeURIComponent(columnName)}/distribution?limit=30`, { ttl: 120000 }),
  ]);
  const decision = state.decisions.find(d => d.column_name === columnName);

  openDrawer({
    title: columnName,
    kicker: '原始字段详情',
    body: `
      <div class="section-stack">
        <div class="detail-panel">
          <h4>基本信息</h4>
          <p>${escapeHtml(decision?.description || '暂无说明')}</p>
          <div class="chips">
            ${categoryTag(decision?.category)}
            <span class="chip">类型: ${escapeHtml(decision?.data_type || '—')}</span>
            <span class="chip">空值率: ${pct(sampleData.null_frac)}</span>
          </div>
        </div>
        <div class="detail-panel">
          <h4>当前决策</h4>
          <div style="margin:8px 0">${decisionSelect(columnName, decision?.decision || 'pending')}</div>
        </div>
        <div class="detail-panel">
          <h4>值分布（采样 TOP 30）</h4>
          ${renderTable(
            [
              { key: 'value', label: '值', render: v => v === null || v === 'None' ? '<em>NULL</em>' : `<code>${escapeHtml(String(v).slice(0, 120))}</code>` },
              { key: 'count', label: '计数', className: 'num', render: v => fmt(v) },
              { key: 'ratio', label: '占比', className: 'num', render: v => pct(v) },
            ],
            distData.distribution || [],
          )}
        </div>
        <div class="detail-panel">
          <h4>采样值</h4>
          ${renderTable(
            [
              { key: 'value', label: '值', render: v => `<code>${escapeHtml(String(v).slice(0, 200))}</code>` },
              { key: 'count', label: '命中', className: 'num', render: v => fmt(v) },
            ],
            sampleData.samples || [],
          )}
        </div>
      </div>
    `,
  });
}
window.viewRawFieldDetail = viewRawFieldDetail;

export async function loadRaw(force = false) {
  setMain('<div class="loading">加载原始数据总览...</div>');
  try {
    const [rawSummary, fieldsData, decisionsData] = await Promise.all([
      api('/audit/raw-summary', { ttl: 600000, force }),
      api('/audit/fields', { ttl: 300000, force }),
      api('/audit/decisions', { ttl: 60000, force }),
    ]);

    state.fields = fieldsData.fields || [];
    state.decisions = decisionsData.items || [];

    document.getElementById('ctx-table').textContent = `RAW（${rawSummary.column_count} 列）`;

    const decisionMap = {};
    state.decisions.forEach(d => { decisionMap[d.column_name] = d; });
    const merged = state.fields.map(f => ({
      ...f,
      ...(decisionMap[f.column_name] || {}),
      decision: decisionMap[f.column_name]?.decision || 'pending',
    }));

    const summary = decisionsData.summary || {};

    setMain(`
      <div class="page-head">
        <div>
          <h2>原始数据 · 字段挑选</h2>
          <p>SDK 上报数据，两张源表结构一致（27 列），统一为一份字段决策。</p>
        </div>
      </div>

      <div class="stat-grid">
        ${rawSummary.tables.map(t => `
          <div class="stat-box">
            <div class="stat-label">${escapeHtml(t.tag)} 表</div>
            <div class="stat-value">${fmt(t.row_count)}</div>
          </div>
        `).join('')}
        <div class="stat-box"><div class="stat-label">合计</div><div class="stat-value blue">${fmt(rawSummary.total_rows)}</div></div>
        <div class="stat-box"><div class="stat-label">字段数</div><div class="stat-value">${rawSummary.column_count}</div></div>
      </div>

      <div class="card">
        <div class="card-title"><h3>决策进度</h3></div>
        <div class="stat-grid" id="decision-summary">
          ${DECISIONS.map(d => `
            <div class="stat-box"><div class="stat-label">${d.label}</div><div class="stat-value">${summary[d.value] || 0}</div></div>
          `).join('')}
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>原始字段（27 列）</h3>
          <span class="card-subtitle">点击字段名查看详情；在"决策"列选择处置方式</span>
        </div>
        ${renderTable(
          [
            { key: 'ordinal_position', label: '#', className: 'num' },
            {
              key: 'column_name', label: '字段名',
              render: v => `<a href="#" onclick="viewRawFieldDetail('${escapeHtml(v)}'); return false;"><strong>${escapeHtml(v)}</strong></a>`,
            },
            { key: 'category', label: '分类', render: v => categoryTag(v) },
            { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v || '—')}</span>` },
            { key: 'data_type', label: '类型', render: v => `<code style="font-size:11px">${escapeHtml(v)}</code>` },
            { key: 'null_frac', label: '空值率', className: 'num', render: v => nullRateBar(v) },
            { key: 'decision', label: '决策', render: (v, row) => decisionSelect(row.column_name, v) },
          ],
          merged,
        )}
      </div>
    `);
  } catch (error) {
    setMain(pageError('原始数据总览加载失败', error));
  }
}
