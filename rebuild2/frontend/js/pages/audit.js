/**
 * L0 字段审计页：展示 L0 目标表的字段定义（从 rebuild2_meta.target_field 读取）。
 * 按分类分组显示，包含来源类型、数据类型、说明。
 */

import { api, qs } from '../core/api.js';
import { state } from '../core/state.js';
import {
  escapeHtml, fmt, setMain, pageError, renderTable,
} from '../ui/common.js';

function sourceTypeTag(t) {
  const m = {
    direct: ['tag-green', '直接映射'],
    parsed: ['tag-orange', '解析提取'],
    derived: ['tag-blue', '计算派生'],
    tag: ['tag-gray', '标签'],
    generated: ['tag-gray', '自动生成'],
  };
  const [cls, label] = m[t] || ['tag-gray', t];
  return `<span class="tag ${cls}">${label}</span>`;
}

function categoryTag(cat) {
  const colors = { '标识': 'tag-blue', '来源': 'tag-gray', '解析': 'tag-orange', '补齐': 'tag-orange', '网络': 'tag-blue', '信号': 'tag-orange', '时间': 'tag-green', '位置': 'tag-green', '元数据': 'tag-gray' };
  return `<span class="tag ${colors[cat] || 'tag-gray'}">${escapeHtml(cat)}</span>`;
}

export async function loadAudit(force = false) {
  setMain('<div class="loading">加载 L0 目标字段定义...</div>');
  try {
    const data = await api('/audit/l0-fields', { ttl: 300000, force });
    const items = data.items || [];
    const cats = data.categories || {};

    setMain(`
      <div class="page-head">
        <div>
          <h2>L0 目标字段定义</h2>
          <p>从 RAW 层 27 列解析、展开、补齐后的目标表结构。共 ${data.total} 个字段，按 cell_id 拆行。</p>
        </div>
      </div>

      <div class="stat-grid">
        ${Object.entries(cats).map(([cat, cnt]) => `
          <div class="stat-box"><div class="stat-label">${cat}</div><div class="stat-value">${cnt}</div></div>
        `).join('')}
      </div>

      ${Object.entries(cats).map(([cat]) => {
        const catItems = items.filter(i => i.category === cat);
        return `
          <div class="card">
            <div class="card-title"><h3>${categoryTag(cat)} ${cat}字段（${catItems.length}）</h3></div>
            ${renderTable(
              [
                { key: 'field_name', label: '字段名', render: v => `<code><strong>${escapeHtml(v)}</strong></code>` },
                { key: 'field_name_cn', label: '中文名' },
                { key: 'data_type', label: '类型', render: v => `<code style="font-size:11px">${escapeHtml(v)}</code>` },
                { key: 'source_type', label: '来源', render: v => sourceTypeTag(v) },
                { key: 'description', label: '说明', render: v => `<span style="font-size:12px">${escapeHtml(v || '—')}</span>` },
              ],
              catItems,
            )}
          </div>
        `;
      }).join('')}
    `);
  } catch (error) {
    setMain(pageError('L0 字段定义加载失败', error));
  }
}
