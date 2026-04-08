/**
 * L1 ODS 标准化页：清洗规则审核 + 执行结果。
 * 两个 Tab：规则审核 / 执行结果
 */

import { api } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, showToast, renderTable,
} from '../ui/common.js';

let currentTab = 'rules';

function severityTag(s) {
  const m = { high: 'tag-red', medium: 'tag-orange', low: 'tag-gray' };
  return `<span class="tag ${m[s] || 'tag-gray'}">${escapeHtml(s)}</span>`;
}

function ruleTypeTag(t) {
  const m = { delete: ['tag-red', '删除行'], nullify: ['tag-orange', '置空'], convert: ['tag-blue', '转换'] };
  const [cls, label] = m[t] || ['tag-gray', t];
  return `<span class="tag ${cls}">${label}</span>`;
}

function categoryTag(c) {
  const m = { '网络': 'tag-blue', '信号': 'tag-orange', '时间': 'tag-green', '位置': 'tag-green' };
  return `<span class="tag ${m[c] || 'tag-gray'}">${escapeHtml(c)}</span>`;
}

function affectBar(rate) {
  if (rate == null || rate < 0) return '<span style="color:var(--text-dim)">—</span>';
  const v = (rate * 100).toFixed(2);
  const color = rate < 0.01 ? 'var(--green)' : rate < 0.05 ? 'var(--orange)' : 'var(--red)';
  return `<div class="compliance-bar"><div class="compliance-fill" style="width:${Math.min(parseFloat(v), 100)}%;background:${color}"></div><span>${v}%</span></div>`;
}

function switchTab(tab) {
  currentTab = tab;
  loadOds(true);
}
window.switchOdsTab = switchTab;

async function loadRulesTab() {
  const data = await api('/ods/rules/preview', { ttl: 60000, force: true });
  const rules = data.rules || [];
  const total = data.total_rows;

  const deleteRules = rules.filter(r => r.rule_type === 'delete');
  const nullifyRules = rules.filter(r => r.rule_type === 'nullify');
  const convertRules = rules.filter(r => r.rule_type === 'convert');

  const totalAffected = deleteRules.reduce((s, r) => s + (r.affected_rows > 0 ? r.affected_rows : 0), 0);

  return `
    <div class="stat-grid">
      <div class="stat-box"><div class="stat-label">样本行数</div><div class="stat-value blue">${fmt(total)}</div></div>
      <div class="stat-box"><div class="stat-label">规则总数</div><div class="stat-value">${rules.length}</div></div>
      <div class="stat-box"><div class="stat-label">删除规则</div><div class="stat-value red">${deleteRules.length}</div></div>
      <div class="stat-box"><div class="stat-label">置空规则</div><div class="stat-value orange">${nullifyRules.length}</div></div>
      <div class="stat-box"><div class="stat-label">转换规则</div><div class="stat-value blue">${convertRules.length}</div></div>
      <div class="stat-box"><div class="stat-label">预计删除行</div><div class="stat-value red">${fmt(totalAffected)}</div></div>
    </div>

    ${deleteRules.length ? `
    <div class="card">
      <div class="card-title"><h3>删除行规则</h3><span class="card-subtitle">满足条件的整行删除</span></div>
      ${renderTable([
        { key: 'rule_code', label: '规则编码', render: v => `<code style="font-size:11px">${escapeHtml(v)}</code>` },
        { key: 'field_name_cn', label: '字段' },
        { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v)}</span>` },
        { key: 'affected_rows', label: '影响行数', className: 'num', render: v => fmt(v) },
        { key: 'affect_rate', label: '占比', className: 'num', render: v => affectBar(v) },
        { key: 'severity', label: '严重度', render: v => severityTag(v) },
      ], deleteRules)}
    </div>` : ''}

    <div class="card">
      <div class="card-title"><h3>置空规则（${nullifyRules.length} 条）</h3><span class="card-subtitle">满足条件的字段值置为 NULL</span></div>
      ${renderTable([
        { key: 'field_name_cn', label: '字段' },
        { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v)}</span>` },
        { key: 'condition_sql', label: '条件', render: v => `<code style="font-size:10px">${escapeHtml(v?.slice(0, 80))}</code>` },
        { key: 'affected_rows', label: '影响行数', className: 'num', render: v => fmt(v) },
        { key: 'affect_rate', label: '占比', className: 'num', render: v => affectBar(v) },
        { key: 'severity', label: '严重度', render: v => severityTag(v) },
      ], nullifyRules)}
    </div>

    <div class="card">
      <div class="card-title"><h3>转换规则（${convertRules.length} 条）</h3><span class="card-subtitle">时间格式统一</span></div>
      ${renderTable([
        { key: 'field_name_cn', label: '字段' },
        { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v)}</span>` },
        { key: 'action', label: '转换表达式', render: v => `<code style="font-size:10px">${escapeHtml(v)}</code>` },
        { key: 'affected_rows', label: '匹配行数', className: 'num', render: v => fmt(v) },
        { key: 'affect_rate', label: '占比', className: 'num', render: v => affectBar(v) },
      ], convertRules)}
    </div>
  `;
}

function renderResultTable(label, info) {
  if (!info || !info.rules?.length) return '';
  const rules = info.rules;
  const deleteRules = rules.filter(r => r.rule_type === 'delete');
  const nullifyRules = rules.filter(r => r.rule_type === 'nullify');
  const convertRules = rules.filter(r => r.rule_type === 'convert');
  const totalDeleted = deleteRules.reduce((s, r) => s + (r.affected_rows > 0 ? Number(r.affected_rows) : 0), 0);
  const totalNullified = nullifyRules.reduce((s, r) => s + (r.affected_rows > 0 ? Number(r.affected_rows) : 0), 0);

  const cols = [
    { key: 'field_name_cn', label: '字段' },
    { key: 'rule_type', label: '类型', render: v => ruleTypeTag(v) },
    { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v)}</span>` },
    { key: 'affected_rows', label: '影响行数', className: 'num', render: v => fmt(v) },
    { key: 'affect_rate', label: '占比', className: 'num', render: v => affectBar(v) },
    { key: 'severity', label: '严重度', render: v => severityTag(v) },
  ];

  return `
    <div class="card">
      <div class="card-title"><h3>${escapeHtml(label)}</h3><span class="card-subtitle">总行数 ${fmt(info.total_rows)}</span></div>
      <div class="stat-grid">
        <div class="stat-box"><div class="stat-label">总行数</div><div class="stat-value blue">${fmt(info.total_rows)}</div></div>
        <div class="stat-box"><div class="stat-label">删除行数</div><div class="stat-value red">${fmt(totalDeleted)}</div></div>
        <div class="stat-box"><div class="stat-label">置空次数</div><div class="stat-value orange">${fmt(totalNullified)}</div></div>
        <div class="stat-box"><div class="stat-label">规则数</div><div class="stat-value">${rules.length}</div></div>
      </div>
      ${renderTable(cols, rules)}
    </div>
  `;
}

async function loadResultsTab() {
  const data = await api('/ods/results', { ttl: 30000, force: true });
  const tables = data.tables || {};
  if (!Object.keys(tables).length) {
    return '<div class="card"><div class="empty-state">尚未执行清洗，请先在"规则审核"确认后执行</div></div>';
  }
  return `
    ${renderResultTable('L0 GPS 表清洗结果', tables.l0_gps)}
    ${renderResultTable('L0 LAC 表清洗结果', tables.l0_lac)}
  `;
}

export async function loadOds(force = false) {
  setMain('<div class="loading">加载 ODS 标准化...</div>');
  try {
    const tabContent = currentTab === 'rules'
      ? await loadRulesTab()
      : await loadResultsTab();

    setMain(`
      <div class="page-head">
        <div>
          <h2>L1 ODS 标准化</h2>
          <p>审核清洗规则，确认后执行。所有异常值将被置空或删除，时间字段统一为 timestamptz。</p>
        </div>
      </div>

      <div class="toolbar" style="margin-bottom:16px">
        <button class="btn ${currentTab === 'rules' ? 'btn-primary' : 'btn-ghost'}" onclick="switchOdsTab('rules')">规则审核</button>
        <button class="btn ${currentTab === 'results' ? 'btn-primary' : 'btn-ghost'}" onclick="switchOdsTab('results')">执行结果</button>
      </div>

      ${tabContent}
    `);
  } catch (error) {
    setMain(pageError('ODS 标准化加载失败', error));
  }
}
