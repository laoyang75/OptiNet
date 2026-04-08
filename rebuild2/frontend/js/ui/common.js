/**
 * 公共 UI 工具函数。
 */

export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
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
  return `<div class="error-card"><h3>${escapeHtml(title)}</h3><p style="margin-top:8px">${escapeHtml(error?.message || String(error))}</p></div>`;
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

export function renderTable(columns, rows) {
  if (!rows || !rows.length) return '<div class="empty-state">暂无数据</div>';
  return `
    <table class="compact-table">
      <thead><tr>${columns.map(c => `<th class="${c.className || ''}">${escapeHtml(c.label)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(row => `<tr>${columns.map(c => {
        const v = row[c.key];
        const html = c.render ? c.render(v, row) : escapeHtml(v == null ? '—' : v);
        return `<td class="${c.className || ''}">${html}</td>`;
      }).join('')}</tr>`).join('')}</tbody>
    </table>`;
}
