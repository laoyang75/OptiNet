/**
 * L0 数据概览页：展示 l0_gps 和 l0_lac 的统计、分布、质量。
 */

import { api } from '../core/api.js';
import {
  escapeHtml, fmt, pct, setMain, pageError, renderTable,
} from '../ui/common.js';

let currentTable = 'l0_gps';

function nullBar(rate) {
  if (rate == null) return '—';
  const v = (rate * 100).toFixed(1);
  const color = rate < 0.1 ? 'var(--green)' : rate < 0.3 ? 'var(--orange)' : 'var(--red)';
  return `<div class="compliance-bar"><div class="compliance-fill" style="width:${Math.min(parseFloat(v),100)}%;background:${color}"></div><span>${v}%</span></div>`;
}

function fillBar(rate) {
  if (rate == null) return '—';
  const v = (rate * 100).toFixed(1);
  const color = rate > 0.9 ? 'var(--green)' : rate > 0.7 ? 'var(--orange)' : 'var(--red)';
  return `<div class="compliance-bar"><div class="compliance-fill" style="width:${v}%;background:${color}"></div><span>${v}%</span></div>`;
}

function switchL0Table(tbl) {
  currentTable = tbl;
  loadL0Data(true);
}
window.switchL0Table = switchL0Table;

export async function loadL0Data(force = false) {
  setMain('<div class="loading">加载 L0 数据概览...</div>');
  try {
    const [summary, dist, quality] = await Promise.all([
      api('/l0/summary', { ttl: 300000, force }),
      api(`/l0/distribution/${currentTable}`, { ttl: 300000, force }),
      api(`/l0/quality/${currentTable}`, { ttl: 300000, force }),
    ]);

    const tables = summary.tables || [];
    const currentInfo = tables.find(t => t.table === currentTable) || {};

    setMain(`
      <div class="page-head">
        <div>
          <h2>L0 数据概览</h2>
          <p>从原始 SDK 数据解析 + ODS 清洗后的 Layer0 产出。两张表分别用于可信库构建和全局回写。</p>
        </div>
        <div class="page-actions">
          ${tables.map(t => `
            <button class="btn ${t.table === currentTable ? 'btn-primary' : 'btn-ghost'}"
                    onclick="switchL0Table('${t.table}')">
              ${escapeHtml(t.label)}
            </button>
          `).join('')}
        </div>
      </div>

      <!-- 总览卡片 -->
      <div class="stat-grid">
        ${tables.map(t => `
          <div class="stat-box">
            <div class="stat-label">${escapeHtml(t.label)}</div>
            <div class="stat-value ${t.table === currentTable ? 'blue' : ''}">${fmt(t.total)}</div>
          </div>
        `).join('')}
        <div class="stat-box"><div class="stat-label">原始记录数</div><div class="stat-value">${fmt(currentInfo.records)}</div></div>
        <div class="stat-box"><div class="stat-label">有CellID</div><div class="stat-value green">${fmt(currentInfo.has_cellid)}</div></div>
        <div class="stat-box"><div class="stat-label">GPS有效</div><div class="stat-value">${fmt(currentInfo.gps_valid)}</div></div>
        <div class="stat-box"><div class="stat-label">有RSRP</div><div class="stat-value">${fmt(currentInfo.has_rsrp)}</div></div>
      </div>

      <!-- 当前表信息 -->
      <div class="card">
        <div class="card-title">
          <h3>${escapeHtml(currentInfo.label || currentTable)}</h3>
          <span class="card-subtitle">${escapeHtml(currentInfo.note || '')}</span>
        </div>
        <div class="stat-grid">
          <div class="stat-box"><div class="stat-label">总行数</div><div class="stat-value blue">${fmt(currentInfo.total)}</div></div>
          <div class="stat-box"><div class="stat-label">原始记录</div><div class="stat-value">${fmt(currentInfo.records)}</div></div>
          <div class="stat-box"><div class="stat-label">展开倍率</div><div class="stat-value">${currentInfo.records ? (currentInfo.total / currentInfo.records).toFixed(1) + 'x' : '—'}</div></div>
          <div class="stat-box"><div class="stat-label">CellID 覆盖率</div><div class="stat-value">${fillBar(currentInfo.has_cellid_rate)}</div></div>
          <div class="stat-box"><div class="stat-label">GPS 有效率</div><div class="stat-value">${fillBar(currentInfo.gps_valid_rate)}</div></div>
          <div class="stat-box"><div class="stat-label">RSRP 覆盖率</div><div class="stat-value">${fillBar(currentInfo.has_rsrp_rate)}</div></div>
        </div>
      </div>

      <!-- 来源 × 制式分布 -->
      <div class="card">
        <div class="card-title"><h3>来源 × 制式分布</h3></div>
        ${renderTable(
          [
            { key: 'cell_origin', label: '来源', render: v => `<span class="tag ${v === 'cell_infos' ? 'tag-blue' : 'tag-orange'}">${escapeHtml(v)}</span>` },
            { key: 'tech_norm', label: '制式', render: v => `<span class="tag tag-gray">${escapeHtml(v)}</span>` },
            { key: 'cnt', label: '行数', className: 'num', render: v => fmt(v) },
          ],
          (dist.by_origin_tech || []).sort((a, b) => (b.cnt || 0) - (a.cnt || 0)),
        )}
      </div>

      <div class="grid-2" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <!-- 运营商分布 -->
        <div class="card">
          <div class="card-title"><h3>运营商分布</h3></div>
          ${renderTable(
            [
              { key: 'operator_cn', label: '运营商' },
              { key: 'cnt', label: '行数', className: 'num', render: v => fmt(v) },
            ],
            (dist.by_operator || []).sort((a, b) => (b.cnt || 0) - (a.cnt || 0)),
          )}
        </div>

        <!-- 数据来源 -->
        <div class="card">
          <div class="card-title"><h3>Cell 来源</h3><span class="card-subtitle">cell_infos（前台）vs ss1（后台）</span></div>
          ${(() => {
            const byOrigin = {};
            (dist.by_origin_tech || []).forEach(r => {
              const k = r.cell_origin;
              byOrigin[k] = (byOrigin[k] || 0) + (r.cnt || 0);
            });
            return renderTable(
              [
                { key: 'origin', label: '来源', render: v => `<span class="tag ${v === 'cell_infos' ? 'tag-blue' : 'tag-orange'}">${escapeHtml(v)}</span>` },
                { key: 'cnt', label: '行数', className: 'num', render: v => fmt(v) },
              ],
              Object.entries(byOrigin).map(([k, v]) => ({ origin: k, cnt: v })).sort((a, b) => b.cnt - a.cnt),
            );
          })()}
        </div>
      </div>

      <!-- 字段质量 -->
      <div class="card">
        <div class="card-title"><h3>字段空值率（清洗后）</h3><span class="card-subtitle">低空值率 = 数据质量好</span></div>
        ${renderTable(
          [
            { key: 'field', label: '字段' },
            { key: 'null_rate', label: '空值率', className: 'num', render: v => nullBar(v) },
          ],
          quality.fields || [],
        )}
      </div>
    `);
  } catch (error) {
    setMain(pageError('L0 数据概览加载失败', error));
  }
}
