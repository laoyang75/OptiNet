/**
 * P4 / D3 共用样本渲染。
 */

import { escapeHtml, fmt, jsLiteral, renderMetricTable } from './common.js';

const COMPARE_STATE_META = {
  same: { label: '无变化', className: 'tag-gray' },
  added: { label: '当前新增', className: 'tag-green' },
  changed: { label: '对象变化', className: 'tag-orange' },
  removed: { label: '对比独有', className: 'tag-red' },
};

function formatCell(value) {
  if (value == null || value === '') return '—';
  if (Array.isArray(value) || (value && typeof value === 'object')) {
    return JSON.stringify(value);
  }
  return String(value);
}

function payloadPreview(payload, limit = 3) {
  const entries = Object.entries(payload || {});
  if (!entries.length) return '—';
  const preview = entries.slice(0, limit)
    .map(([key, value]) => `${key}=${formatCell(value)}`)
    .join('；');
  return entries.length > limit ? `${preview} …` : preview;
}

function detailButton(sampleSetId, objectKey, runId, compareRunId) {
  return `
    <button
      class="btn btn-ghost"
      onclick="openSampleObjectDrawer(${sampleSetId}, ${jsLiteral(objectKey)}, ${runId ?? 'null'}, ${compareRunId ?? 'null'})"
    >对象详情</button>
  `;
}

export function sampleCompareTag(compareState) {
  const meta = COMPARE_STATE_META[compareState] || COMPARE_STATE_META.same;
  return `<span class="tag ${meta.className}">${escapeHtml(meta.label)}</span>`;
}

export function renderRuleHitChips(ruleHits) {
  const items = Array.isArray(ruleHits) ? ruleHits : [];
  if (!items.length) return '<span class="muted">—</span>';
  return items.map(rule => `<span class="chip">${escapeHtml(rule)}</span>`).join('');
}

export function renderChangedFieldSummary(changedFields, limit = 3) {
  const items = Array.isArray(changedFields) ? changedFields : [];
  if (!items.length) return '—';
  const names = items.slice(0, limit).map(item => item.field);
  return items.length > limit ? `${names.join('、')} 等 ${fmt(items.length)} 项` : names.join('、');
}

export function renderSampleItemsTable(
  items,
  {
    sampleSetId,
    runId,
    compareRunId,
    emptyText = '暂无对象样本',
    includeAction = true,
  } = {},
) {
  if (!items || items.length === 0) {
    return `<div class="empty-state">${escapeHtml(emptyText)}</div>`;
  }

  const columns = [
    { key: 'rank_order', label: '序号', className: 'num', render: value => escapeHtml(value == null ? '—' : value) },
    { key: 'object_label', label: '对象' },
    { key: 'compare_state', label: '对比状态', render: value => sampleCompareTag(value) },
    { key: 'rule_hits', label: '命中规则', render: value => `<div class="chips">${renderRuleHitChips(value)}</div>` },
    { key: 'changed_fields', label: '变化字段', render: value => escapeHtml(renderChangedFieldSummary(value)) },
    { key: 'payload', label: '对象摘要', render: (_, row) => escapeHtml(payloadPreview(row.payload || row.current_payload || row.compare_payload)) },
  ];
  if (includeAction && sampleSetId != null) {
    columns.push({
      key: 'object_key',
      label: '详情',
      render: value => detailButton(sampleSetId, value, runId, compareRunId),
    });
  }
  return renderMetricTable(columns, items);
}

export function renderSampleRemovedTable(
  items,
  { sampleSetId, runId, compareRunId, emptyText = '对比批次没有独有对象' } = {},
) {
  if (!items || items.length === 0) {
    return `<div class="empty-state">${escapeHtml(emptyText)}</div>`;
  }
  return renderMetricTable(
    [
      { key: 'object_label', label: '对象' },
      { key: 'rule_hits', label: '命中规则', render: value => `<div class="chips">${renderRuleHitChips(value)}</div>` },
      { key: 'payload', label: '对比摘要', render: (_, row) => escapeHtml(payloadPreview(row.payload || row.compare_payload)) },
      {
        key: 'object_key',
        label: '详情',
        render: value => detailButton(sampleSetId, value, runId, compareRunId),
      },
    ],
    items,
  );
}

export function renderPayloadDiffTable(currentPayload, comparePayload) {
  const keys = [...new Set([
    ...Object.keys(currentPayload || {}),
    ...Object.keys(comparePayload || {}),
  ])].sort();
  if (!keys.length) return '<div class="empty-state">暂无字段载荷</div>';

  return renderMetricTable(
    [
      { key: 'field', label: '字段' },
      { key: 'current', label: '当前值', render: value => escapeHtml(formatCell(value)) },
      { key: 'compare', label: '对比值', render: value => escapeHtml(formatCell(value)) },
      {
        key: 'changed',
        label: '是否变化',
        render: value => value ? '<span class="tag tag-orange">有变化</span>' : '<span class="tag tag-gray">一致</span>',
      },
    ],
    keys.map(key => ({
      field: key,
      current: currentPayload?.[key],
      compare: comparePayload?.[key],
      changed: currentPayload?.[key] !== comparePayload?.[key],
    })),
  );
}

export function renderDisplayPairsTable(displayPairs) {
  if (!displayPairs || displayPairs.length === 0) {
    return '<div class="empty-state">当前样本没有“原始值 vs 处理后值”对照字段</div>';
  }
  return renderMetricTable(
    [
      { key: 'label', label: '字段组' },
      { key: 'current_raw', label: '当前原始值', render: value => escapeHtml(formatCell(value)) },
      { key: 'current_corrected', label: '当前处理后', render: value => escapeHtml(formatCell(value)) },
      { key: 'compare_raw', label: '对比原始值', render: value => escapeHtml(formatCell(value)) },
      { key: 'compare_corrected', label: '对比处理后', render: value => escapeHtml(formatCell(value)) },
    ],
    displayPairs,
  );
}
