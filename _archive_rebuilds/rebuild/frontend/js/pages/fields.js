/**
 * P3 字段治理页 — 统一治理表格 + 同页展开。
 * 原始字段（source）与过程字段（pipeline）合并展示。
 */

import { api, qs } from '../core/api.js';
import { state } from '../core/state.js';
import {
  escapeHtml,
  jsLiteral,
  fmt,
  pct,
  setMain,
  pageError,
  renderMetricTable,
  tableNameLabel,
} from '../ui/common.js';
import { refreshContext } from '../main.js';

// ── 状态 ──────────────────────────────────────────────────────

let mergedRows = [];
let expandedField = null;
let scopeFilter = '';

// ── 合并行 ────────────────────────────────────────────────────

function mergeFieldRows(pipelineItems, sourceItems) {
  const rows = [];
  for (const item of sourceItems) {
    rows.push({
      ...item,
      scope: 'source',
      field_key: `source:${item.field_name}`,
      status_tag: item.status || '待分析',
    });
  }
  for (const item of pipelineItems) {
    rows.push({
      ...item,
      scope: 'pipeline',
      field_key: `pipeline:${item.field_name}:${item.table_name}`,
      status_tag: item.health_status || '待分析',
      compliance_rate: null,
      mapping_targets: item.field_name_cn || item.field_name,
    });
  }
  return rows;
}

function statusTagClass(status) {
  if (status === '正常') return 'tag-green';
  if (status === '关注') return 'tag-orange';
  if (status === '异常') return 'tag-red';
  return 'tag-gray';
}

function scopeBadge(scope) {
  return scope === 'source'
    ? '<span class="scope-badge scope-source">原始</span>'
    : '<span class="scope-badge scope-pipeline">过程</span>';
}

function complianceBar(rate) {
  if (rate == null) return '<span class="compliance-na">—</span>';
  const pctVal = (rate * 100).toFixed(1);
  const color = rate >= 0.95 ? 'var(--green)' : rate >= 0.8 ? 'var(--orange)' : 'var(--red)';
  return `<div class="compliance-bar"><div class="compliance-fill" style="width:${pctVal}%;background:${color}"></div><span>${pctVal}%</span></div>`;
}

// ── 过滤 ──────────────────────────────────────────────────────

function filteredRows() {
  const { search, status, step } = state.fieldFilters;
  return mergedRows.filter(row => {
    if (scopeFilter && row.scope !== scopeFilter) return false;
    if (search && !row.field_name.includes(search) && !(row.field_name_cn || '').includes(search)) return false;
    if (status && row.status_tag !== status) return false;
    if (step && !(row.impacted_steps || []).includes(step)) return false;
    return true;
  });
}

function availableSteps() {
  return [...new Set(mergedRows.flatMap(row => row.impacted_steps || []))].sort();
}

// ── 表格渲染 ──────────────────────────────────────────────────

function renderFieldTable() {
  const rows = filteredRows();
  if (!rows.length) return '<div class="empty-state">暂无匹配字段</div>';

  const header = `
    <table class="compact-table field-governance-table">
      <thead><tr>
        <th>字段</th>
        <th>映射目标</th>
        <th>范围</th>
        <th>类型</th>
        <th>状态</th>
        <th class="num">空值率</th>
        <th class="num">异常率</th>
        <th class="num">合规率</th>
        <th>影响步骤</th>
      </tr></thead>
      <tbody>
  `;

  const body = rows.map(row => {
    const isExpanded = expandedField === row.field_key;
    const rowClass = isExpanded ? 'field-row expanded' : 'field-row';
    const anomalyRate = (row.anomalous_rows != null && row.total_rows)
      ? pct(row.anomalous_rows / row.total_rows)
      : '—';
    const steps = (row.impacted_steps || []).map(s =>
      `<a href="#step/${escapeHtml(s)}" class="step-link">${escapeHtml(s)}</a>`
    ).join(' ') || '—';

    let expandHtml = '';
    if (isExpanded) {
      expandHtml = `<tr class="field-expansion-row"><td colspan="9"><div class="field-expansion" id="field-expansion-${escapeHtml(row.field_key)}"><div class="loading">加载详情...</div></div></td></tr>`;
    }

    return `
      <tr class="${rowClass}" onclick="toggleFieldExpansion(${jsLiteral(row.field_key)}, ${jsLiteral(row.field_name)}, ${jsLiteral(row.scope)})">
        <td>
          ${escapeHtml(row.field_name_cn || row.field_name)}
          <span class="code-subtle">${escapeHtml(row.field_name)}</span>
        </td>
        <td>${escapeHtml(row.mapping_targets || row.field_name_cn || row.field_name || '—')}</td>
        <td>${scopeBadge(row.scope)}</td>
        <td>${escapeHtml(row.data_type || '—')}</td>
        <td><span class="tag ${statusTagClass(row.status_tag)}">${escapeHtml(row.status_tag)}</span></td>
        <td class="num">${pct(row.null_rate)}</td>
        <td class="num">${anomalyRate}</td>
        <td class="num">${complianceBar(row.compliance_rate)}</td>
        <td>${steps}</td>
      </tr>
      ${expandHtml}
    `;
  }).join('');

  return header + body + '</tbody></table>';
}

// ── 展开区 ────────────────────────────────────────────────────

async function loadFieldExpansion(fieldKey, fieldName, scope) {
  const container = document.getElementById(`field-expansion-${fieldKey}`);
  if (!container) return;

  try {
    if (scope === 'source') {
      const detail = await api(`/source-fields/${encodeURIComponent(fieldName)}`, { ttl: 300000 });
      container.innerHTML = renderSourceExpansion(detail);
    } else {
      const tableName = fieldKey.split(':')[2] || '';
      const detail = await api(`/fields/${encodeURIComponent(fieldName)}${qs({ table_name: tableName })}`, { ttl: 300000 });
      container.innerHTML = renderPipelineExpansion(detail);
    }
  } catch (error) {
    container.innerHTML = `<div class="error-card"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function renderSourceExpansion(detail) {
  const field = detail.field || {};
  const rule = detail.compliance_rule;
  const snapshot = detail.latest_snapshot;
  const trend = detail.trend || [];
  const mappings = detail.mappings || [];
  const steps = detail.related_steps || [];
  const changes = detail.change_log || [];

  return `
    <div class="expansion-grid">
      <div class="expansion-section">
        <h4>基本信息</h4>
        <p>${escapeHtml(field.description || '暂无描述')}</p>
        <div class="chips">
          <span class="chip">${escapeHtml(field.logical_domain || '—')}</span>
          <span class="chip">${escapeHtml(field.data_type)}</span>
          ${field.unit ? `<span class="chip">${escapeHtml(field.unit)}</span>` : ''}
        </div>
      </div>
      <div class="expansion-section">
        <h4>合规规则</h4>
        ${rule ? `
          <p>${escapeHtml(rule.business_definition)}</p>
          <div class="chips">
            <span class="chip">类型: ${escapeHtml(rule.rule_type)}</span>
            <span class="chip">严重性: ${escapeHtml(rule.severity)}</span>
            <span class="chip">修复策略: ${escapeHtml(rule.repair_strategy || '—')}</span>
          </div>
        ` : '<div class="empty-state">暂无合规规则</div>'}
      </div>
      <div class="expansion-section">
        <h4>最新快照</h4>
        ${snapshot ? `
          <div class="chips">
            <span class="chip">合规率 ${pct(snapshot.compliance_rate)}</span>
            <span class="chip">空值率 ${pct(snapshot.null_rate)}</span>
            <span class="chip">异常行 ${fmt(snapshot.anomalous_rows)}</span>
            <span class="chip">总行数 ${fmt(snapshot.total_rows)}</span>
          </div>
        ` : '<div class="empty-state">暂无快照数据，请刷新合规快照</div>'}
      </div>
      <div class="expansion-section">
        <h4>合规趋势（近 ${trend.length} 次批次）</h4>
        ${trend.length ? renderMetricTable(
          [
            { key: 'run_id', label: '批次', render: v => `#${v}` },
            { key: 'compliance_rate', label: '合规率', className: 'num', render: v => pct(v) },
            { key: 'null_rate', label: '空值率', className: 'num', render: v => pct(v) },
            { key: 'anomalous_rows', label: '异常行', className: 'num', render: v => fmt(v) },
          ],
          trend,
        ) : '<div class="empty-state">暂无趋势数据</div>'}
      </div>
      <div class="expansion-section">
        <h4>影响步骤</h4>
        <p>${steps.map(s => `<a href="#step/${escapeHtml(s)}" class="step-link">${escapeHtml(s)}</a>`).join(' ') || '—'}</p>
      </div>
      ${mappings.length ? `
        <div class="expansion-section">
          <h4>映射规则</h4>
          ${renderMetricTable(
            [
              { key: 'rule_type', label: '类型' },
              { key: 'rule_expression', label: '表达式' },
              { key: 'source_field', label: '来源字段' },
            ],
            mappings,
          )}
        </div>
      ` : ''}
      ${changes.length ? `
        <div class="expansion-section">
          <h4>变更历史</h4>
          ${renderMetricTable(
            [
              { key: 'change_type', label: '类型' },
              { key: 'old_value', label: '旧值' },
              { key: 'new_value', label: '新值' },
              { key: 'reason', label: '原因' },
            ],
            changes.slice(0, 5),
          )}
        </div>
      ` : ''}
    </div>
  `;
}

function renderPipelineExpansion(detail) {
  const field = detail.field || {};
  const health = detail.health || {};
  const steps = detail.related_steps || [];
  const mappings = detail.mapping_rules || [];
  const changes = detail.change_log || [];

  return `
    <div class="expansion-grid">
      <div class="expansion-section">
        <h4>基本信息</h4>
        <p>${escapeHtml(field.description || '暂无描述')}</p>
        <div class="chips">
          <span class="chip">${escapeHtml(field.table_name_cn || field.table_name)}</span>
          <span class="chip">${escapeHtml(field.data_type)}</span>
          <span class="chip">${escapeHtml(field.health_status)}</span>
        </div>
      </div>
      <div class="expansion-section">
        <h4>健康度</h4>
        <div class="chips">
          <span class="chip">空值率 ${pct(health.null_rate)}</span>
          <span class="chip">近似基数 ${fmt(health.distinct_estimate)}</span>
        </div>
        ${health.history?.length ? renderMetricTable(
          [
            { key: 'null_rate', label: '空值率', className: 'num', render: v => pct(v) },
            { key: 'distinct_count', label: '基数', className: 'num', render: v => fmt(v) },
            { key: 'is_anomalous', label: '异常', render: v => v ? '是' : '否' },
          ],
          health.history.slice(0, 5),
        ) : ''}
      </div>
      <div class="expansion-section">
        <h4>影响步骤</h4>
        <p>${steps.map(s => `<a href="#step/${escapeHtml(s)}" class="step-link">${escapeHtml(s)}</a>`).join(' ') || '—'}</p>
      </div>
      ${mappings.length ? `
        <div class="expansion-section">
          <h4>映射规则</h4>
          ${renderMetricTable(
            [
              { key: 'rule_type', label: '类型' },
              { key: 'rule_expression', label: '表达式' },
              { key: 'source_field', label: '来源字段' },
            ],
            mappings,
          )}
        </div>
      ` : ''}
      ${changes.length ? `
        <div class="expansion-section">
          <h4>变更历史</h4>
          ${renderMetricTable(
            [
              { key: 'change_type', label: '类型' },
              { key: 'old_value', label: '旧值' },
              { key: 'new_value', label: '新值' },
              { key: 'reason', label: '原因' },
            ],
            changes.slice(0, 5),
          )}
        </div>
      ` : ''}
    </div>
  `;
}

// ── 交互 ──────────────────────────────────────────────────────

function toggleFieldExpansion(fieldKey, fieldName, scope) {
  if (expandedField === fieldKey) {
    expandedField = null;
  } else {
    expandedField = fieldKey;
  }
  const wrapper = document.getElementById('fields-table-wrapper');
  if (wrapper) {
    wrapper.innerHTML = renderFieldTable();
    if (expandedField) {
      loadFieldExpansion(fieldKey, fieldName, scope);
    }
  }
}
window.toggleFieldExpansion = toggleFieldExpansion;

export function applyFieldFilters() {
  state.fieldFilters = {
    search: document.getElementById('field-search')?.value || '',
    table: '',
    status: document.getElementById('field-status')?.value || '',
    step: document.getElementById('field-step')?.value || '',
  };
  scopeFilter = document.getElementById('field-scope')?.value || '';
  expandedField = null;
  const wrapper = document.getElementById('fields-table-wrapper');
  if (wrapper) wrapper.innerHTML = renderFieldTable();
}

// ── 页面加载 ──────────────────────────────────────────────────

export async function loadFields(force = false) {
  setMain('<div class="loading">加载字段治理...</div>');
  try {
    await refreshContext(force);
    const [pipelineData, sourceData] = await Promise.all([
      api('/fields', { ttl: 600000, force }),
      api('/source-fields', { ttl: 300000, force }),
    ]);
    state.fields = pipelineData;
    mergedRows = mergeFieldRows(pipelineData.items || [], sourceData.items || []);
    expandedField = null;

    const pSummary = pipelineData.summary || {};
    const sSummary = sourceData.summary || {};
    const totalNormal = (pSummary.normal || 0) + (sSummary.normal || 0);
    const totalAttention = (pSummary.attention || 0) + (sSummary.attention || 0);
    const totalAnomalous = (pSummary.anomalous || 0) + (sSummary.anomalous || 0);
    const missingSnapshots = (sourceData.items || []).filter(item => !item.has_snapshot).length;
    const stepOptions = availableSteps()
      .map(step => `<option value="${escapeHtml(step)}"${state.fieldFilters.step === step ? ' selected' : ''}>${escapeHtml(step)}</option>`)
      .join('');

    setMain(`
      <div class="page-head">
        <div>
          <h2>P3 字段治理</h2>
          <p>统一展示原始字段合规状态与过程字段健康度，点击行展开详情。</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-secondary" onclick="refreshSourceFields()">刷新合规快照</button>
          <button class="btn btn-ghost" onclick="refreshWorkbench(true)">重建字段注册表</button>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat-box"><div class="stat-label">字段总数</div><div class="stat-value blue">${fmt(mergedRows.length)}</div></div>
        <div class="stat-box"><div class="stat-label">正常</div><div class="stat-value green">${fmt(totalNormal)}</div></div>
        <div class="stat-box"><div class="stat-label">关注</div><div class="stat-value orange">${fmt(totalAttention)}</div></div>
        <div class="stat-box"><div class="stat-label">异常</div><div class="stat-value red">${fmt(totalAnomalous)}</div></div>
        <div class="stat-box"><div class="stat-label">缺快照</div><div class="stat-value">${fmt(missingSnapshots)}</div></div>
      </div>

      <div class="toolbar">
        <label class="control">搜索
          <input id="field-search" value="${escapeHtml(state.fieldFilters.search)}" placeholder="字段名 / 中文名" oninput="applyFieldFilters()">
        </label>
        <label class="control">范围
          <select id="field-scope" onchange="applyFieldFilters()">
            <option value="">全部</option>
            <option value="source">原始字段</option>
            <option value="pipeline">过程字段</option>
          </select>
        </label>
        <label class="control">状态
          <select id="field-status" onchange="applyFieldFilters()">
            <option value="">全部</option>
            <option value="正常">正常</option>
            <option value="关注">关注</option>
            <option value="异常">异常</option>
            <option value="待分析">待分析</option>
          </select>
        </label>
        <label class="control">影响步骤
          <select id="field-step" onchange="applyFieldFilters()">
            <option value="">全部</option>
            ${stepOptions}
          </select>
        </label>
      </div>

      <div class="card" id="fields-table-wrapper">
        ${renderFieldTable()}
      </div>
    `);
  } catch (error) {
    setMain(pageError('字段治理加载失败', error));
  }
}

// 刷新源字段合规快照
async function refreshSourceFields() {
  try {
    setMain('<div class="loading">正在计算源字段合规快照...</div>');
    const result = await api('/source-fields/refresh', { method: 'POST', ttl: 0 });
    const { clearApiCache } = await import('../core/api.js');
    clearApiCache();
    await loadFields(true);
    const { showToast } = await import('../ui/common.js');
    showToast(`已刷新 ${result.refreshed_fields} 个字段，耗时 ${result.duration_seconds}s`);
  } catch (error) {
    setMain(pageError('合规快照刷新失败', error));
  }
}
window.refreshSourceFields = refreshSourceFields;
