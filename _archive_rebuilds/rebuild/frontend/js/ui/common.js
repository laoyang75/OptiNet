/**
 * HTML escape、格式化、表格/卡片/徽标、toast、drawer shell。
 */

import { TABLE_LABELS } from '../core/state.js';

export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function jsLiteral(value) {
  return `'${String(value ?? '')
    .replaceAll('\\', '\\\\')
    .replaceAll("'", "\\'")}'`;
}

export function fmt(value) {
  if (value == null || value === '') return '—';
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString('zh-CN');
}

export function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function fmtDelta(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const num = Number(value);
  const sign = num > 0 ? '+' : '';
  return `${sign}${fmt(num)}`;
}

export function timeAgo(value) {
  if (!value) return '—';
  const diffMs = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diffMs)) return '—';
  const seconds = Math.max(0, Math.floor(diffMs / 1000));
  if (seconds < 60) return `${seconds}s 前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m 前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h 前`;
  const days = Math.floor(hours / 24);
  return `${days}d 前`;
}

export function setMain(html) {
  document.getElementById('main-content').innerHTML = html;
}

export function showToast(message, ttl = 2600) {
  const node = document.getElementById('toast');
  node.textContent = message;
  node.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => node.classList.add('hidden'), ttl);
}

export function pageError(title, error) {
  return `
    <div class="error-card">
      <h3>${escapeHtml(title)}</h3>
      <p style="margin-top:8px">${escapeHtml(error?.message || String(error))}</p>
    </div>
  `;
}

export function tableNameLabel(name) {
  return TABLE_LABELS[name] || name || '—';
}

export function diffClass(delta) {
  if (delta == null || Number.isNaN(Number(delta)) || Number(delta) === 0) return '';
  return Number(delta) > 0 ? 'diff-positive' : 'diff-negative';
}

export function renderMetricTable(columns, rows) {
  if (!rows || rows.length === 0) {
    return '<div class="empty-state">暂无数据</div>';
  }
  return `
    <table class="compact-table">
      <thead><tr>${columns.map(col => `<th>${escapeHtml(col.label)}</th>`).join('')}</tr></thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            ${columns.map(col => {
              const value = row[col.key];
              const html = col.render ? col.render(value, row) : escapeHtml(value == null ? '—' : value);
              return `<td class="${col.className || ''}">${html}</td>`;
            }).join('')}
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

export function openDrawer({ title, kicker = '详情', body }) {
  document.getElementById('drawer-title').textContent = title;
  document.getElementById('drawer-kicker').textContent = kicker;
  document.getElementById('drawer-body').innerHTML = body;
  document.getElementById('drawer').classList.remove('hidden');
  document.getElementById('drawer-backdrop').classList.remove('hidden');
}

export function closeDrawer() {
  document.getElementById('drawer').classList.add('hidden');
  document.getElementById('drawer-backdrop').classList.add('hidden');
}

export function settled(result, fallback) {
  return result?.status === 'fulfilled' ? result.value : fallback;
}

export function runSummaryCard(title, run) {
  if (!run) {
    return `
      <div class="card">
        <div class="card-title"><h3>${escapeHtml(title)}</h3></div>
        <div class="empty-state">暂无可用批次</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-title">
        <h3>${escapeHtml(title)} #${escapeHtml(run.run_id)}</h3>
        <span class="tag ${run.status === 'completed' ? 'tag-green' : run.status === 'running' ? 'tag-blue' : 'tag-red'}">${escapeHtml(run.status_label)}</span>
      </div>
      <table class="compact-table">
        <tbody>
          <tr><th>类型</th><td>${escapeHtml(run.run_mode_label)}</td></tr>
          <tr><th>输入窗口</th><td>${escapeHtml(run.input_window_start || '—')} ~ ${escapeHtml(run.input_window_end || '—')}</td></tr>
          <tr><th>原始记录</th><td class="num">${fmt(run.input_rows)}</td></tr>
          <tr><th>最终明细</th><td class="num">${fmt(run.final_rows)}</td></tr>
          <tr><th>参数集</th><td>${escapeHtml(run.parameter_set || '—')}</td></tr>
          <tr><th>规则集</th><td>${escapeHtml(run.rule_set || '—')}</td></tr>
          <tr><th>SQL版本</th><td>${escapeHtml(run.sql_bundle || '—')}</td></tr>
          <tr><th>契约版本</th><td>${escapeHtml(run.contract || '—')}</td></tr>
          <tr><th>耗时</th><td>${escapeHtml(run.duration_pretty || '—')}</td></tr>
        </tbody>
      </table>
    </div>
  `;
}

export function renderParametersTable(parameters) {
  const entries = Object.entries(parameters || {});
  if (!entries.length) return '<div class="empty-state">当前步骤无专属参数</div>';
  return renderMetricTable(
    [
      { key: 'key', label: '参数名' },
      { key: 'value', label: '值', render: value => escapeHtml(typeof value === 'object' ? JSON.stringify(value) : value) },
    ],
    entries.map(([key, value]) => ({ key, value })),
  );
}

export function renderJsonMetrics(jsonMetrics) {
  const entries = Object.entries(jsonMetrics || {});
  if (!entries.length) return '<div class="empty-state">暂无结构化指标</div>';
  return entries.map(([code, value]) => `
    <div class="card">
      <div class="card-title"><h4>${escapeHtml(code)}</h4></div>
      ${Array.isArray(value)
        ? renderMetricTable(
            Object.keys(value[0] || {}).map(key => ({
              key,
              label: key,
              render: cell => typeof cell === 'number' ? fmt(cell) : escapeHtml(cell),
            })),
            value,
          )
        : `<div class="json-block"><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></div>`}
    </div>
  `).join('');
}
