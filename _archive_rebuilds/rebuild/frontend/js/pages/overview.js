/**
 * P1 治理链路总览页。
 */

import { api, qs } from '../core/api.js';
import { PRIMARY_METRIC_CODES, state } from '../core/state.js';
import {
  escapeHtml,
  fmt,
  fmtDelta,
  pct,
  diffClass,
  setMain,
  pageError,
  renderMetricTable,
  runSummaryCard,
  tableNameLabel,
} from '../ui/common.js';
import { refreshContext } from '../main.js';

function metricValue(summaryRows, stepId, code) {
  const row = summaryRows.find(item => item.step_id === stepId);
  return row ? row[code] : null;
}

function layerRow(layers, layerId) {
  return layers.find(item => item.layer_id === layerId);
}

function primaryStepValue(stepId, summaryRows, layers) {
  if (stepId === 's5') return layerRow(layers, 'L2_cell_stats')?.row_count ?? null;
  if (stepId === 's52-group') {
    return ['s50', 's51', 's52']
      .map(id => Number(metricValue(summaryRows, id, PRIMARY_METRIC_CODES[id]) || 0))
      .reduce((acc, value) => acc + value, 0);
  }
  const metricCode = PRIMARY_METRIC_CODES[stepId];
  return metricCode ? metricValue(summaryRows, stepId, metricCode) : null;
}

export function buildOverviewDiffRows(currentSteps, compareSteps, currentLayers, compareLayers) {
  const nodes = [
    { id: 's0', label: '数据起点' },
    { id: 's4', label: '可信LAC' },
    { id: 's5', label: 'Cell统计' },
    { id: 's30', label: '可信BS' },
    { id: 's31', label: 'GPS修正' },
    { id: 's33', label: '信号补齐' },
    { id: 's41', label: '完整回归' },
    { id: 's52-group', label: '画像/基线' },
  ];
  return nodes.map(node => {
    const current = Number(primaryStepValue(node.id, currentSteps, currentLayers) || 0);
    const compare = Number(primaryStepValue(node.id, compareSteps, compareLayers) || 0);
    const delta = compare ? current - compare : null;
    return { ...node, current, compare, delta, ratio: compare ? delta / compare : null };
  });
}

export function buildFocusItems(diffRows, anomalies, context, sourceFields = {}, changeLog = {}) {
  const items = [];
  if (diffRows.length) {
    const biggestDiff = [...diffRows]
      .filter(row => row.delta != null)
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
    if (biggestDiff) {
      items.push({
        tag: '步骤变化',
        tagClass: biggestDiff.delta >= 0 ? 'tag-green' : 'tag-red',
        title: `${biggestDiff.label} 变化最大`,
        detail: `当前 ${fmt(biggestDiff.current)}，对比 ${fmt(biggestDiff.compare)}，差值 ${fmtDelta(biggestDiff.delta)}。`,
      });
    }
  }
  if (anomalies.length) {
    const topAnomaly = [...anomalies]
      .sort((a, b) => Number(b.anomaly_ratio) - Number(a.anomaly_ratio))[0];
    if (topAnomaly) {
      items.push({
        tag: '异常分布',
        tagClass: 'tag-orange',
        title: `${topAnomaly.object_level_label} / ${topAnomaly.anomaly_type_cn}`,
        detail: `异常占比 ${pct(topAnomaly.anomaly_ratio)}，异常数 ${fmt(topAnomaly.anomaly_count)}。`,
      });
    }
  }
  // 字段治理摘要
  const sfSummary = sourceFields?.summary;
  if (sfSummary && sfSummary.anomalous > 0) {
    items.push({
      tag: '字段异常',
      tagClass: 'tag-red',
      title: `${sfSummary.anomalous} 个源字段合规异常`,
      detail: `共 ${sfSummary.total} 个源字段，正常 ${sfSummary.normal}，关注 ${sfSummary.attention}，异常 ${sfSummary.anomalous}。`,
      href: '#fields',
    });
  }
  // 版本变化
  const versionChanges = (changeLog?.version_changes || []).filter(c => c.changed);
  if (versionChanges.length) {
    items.push({
      tag: '版本变化',
      tagClass: 'tag-blue',
      title: `${versionChanges.length} 项版本标识变化`,
      detail: versionChanges.map(c => `${c.category}: ${c.compare || '—'} → ${c.current || '—'}`).join('；'),
    });
  }
  if (context?.current_run) {
    items.push({
      tag: '运行上下文',
      tagClass: 'tag-blue',
      title: `当前批次 #${context.current_run.run_id}`,
      detail: `${context.current_run.run_mode_label}，状态 ${context.current_run.status_label}，参数集 ${context.current_run.parameter_set}。`,
    });
  }
  return items;
}

export async function loadOverview(force = false) {
  setMain('<div class="loading">加载治理链路总览...</div>');
  try {
    const context = await refreshContext(force);
    const currentRunId = context?.current_run?.run_id;
    const compareRunId = context?.compare_run?.run_id;

    const [overview, currentSteps, currentLayers, anomalies, compareSteps, compareLayers, sourceFields, changeLog] = await Promise.all([
      api('/pipeline/overview', { ttl: 300000, force }),
      api(`/metrics/step-summary${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/metrics/layer-snapshot${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/metrics/anomaly-summary${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      compareRunId ? api(`/metrics/step-summary${qs({ run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve([]),
      compareRunId ? api(`/metrics/layer-snapshot${qs({ run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve([]),
      api('/source-fields', { ttl: 300000, force }).catch(() => ({ items: [], summary: {} })),
      api('/version/change-log', { ttl: 120000, force }).catch(() => ({ version_changes: [], parameter_changes: [] })),
    ]);

    const rawRows = layerRow(currentLayers, 'L0_raw')?.row_count;
    const filteredRows = layerRow(currentLayers, 'L2_filtered')?.row_count;
    const cellRows = layerRow(currentLayers, 'L2_cell_stats')?.row_count;
    const finalRows = layerRow(currentLayers, 'L4_final')?.row_count;
    const focusItems = buildFocusItems(buildOverviewDiffRows(currentSteps, compareSteps, currentLayers, compareLayers), anomalies, context, sourceFields, changeLog);

    const flowRows = buildOverviewDiffRows(currentSteps, compareSteps, currentLayers, compareLayers);
    const flowNodes = [
      { label: '数据起点', value: rawRows, delta: flowRows.find(row => row.id === 's0')?.delta, href: '#step/s0', state: 'done' },
      { label: '可信LAC', value: metricValue(currentSteps, 's4', 'trusted_lac_cnt'), delta: flowRows.find(row => row.id === 's4')?.delta, href: '#step/s4', state: 'done' },
      { label: 'Cell统计', value: cellRows, delta: flowRows.find(row => row.id === 's5')?.delta, href: '#step/s5', state: 'done' },
      { label: '可信BS', value: metricValue(currentSteps, 's30', 'total_bs'), delta: flowRows.find(row => row.id === 's30')?.delta, href: '#step/s30', state: 'done' },
      { label: 'GPS修正', value: metricValue(currentSteps, 's31', 'filled_from_bs'), delta: flowRows.find(row => row.id === 's31')?.delta, href: '#step/s31', state: 'current' },
      { label: '信号补齐', value: metricValue(currentSteps, 's33', 'by_cell'), delta: flowRows.find(row => row.id === 's33')?.delta, href: '#step/s33', state: 'done' },
      { label: '完整回归', value: finalRows, delta: flowRows.find(row => row.id === 's41')?.delta, href: '#step/s41', state: 'done' },
      { label: '画像/基线', value: primaryStepValue('s52-group', currentSteps, currentLayers), delta: flowRows.find(row => row.id === 's52-group')?.delta, href: '#step/s50', state: 'done' },
      { label: '伪日更', value: null, delta: null, href: '#overview', state: 'pending' },
    ];

    const anomalyTable = renderMetricTable(
      [
        { key: 'object_level_label', label: '对象' },
        { key: 'anomaly_type_cn', label: '异常类型' },
        { key: 'anomaly_count', label: '异常数', className: 'num', render: value => fmt(value) },
        { key: 'total', label: '总数', className: 'num', render: value => fmt(value) },
        { key: 'anomaly_ratio', label: '占比', className: 'num', render: value => pct(value) },
      ],
      anomalies.slice(0, 8),
    );

    const diffTable = renderMetricTable(
      [
        { key: 'label', label: '步骤' },
        { key: 'current', label: `当前 #${context?.current_run?.run_id || '—'}`, className: 'num', render: value => fmt(value) },
        { key: 'compare', label: `对比 #${context?.compare_run?.run_id || '—'}`, className: 'num', render: value => fmt(value) },
        { key: 'delta', label: '变化', className: 'num', render: value => `<span class="${diffClass(value)}">${escapeHtml(fmtDelta(value))}</span>` },
        { key: 'ratio', label: '变化率', className: 'num', render: value => pct(value) },
      ],
      flowRows,
    );

    setMain(`
      <div class="page-head">
        <div>
          <h2>P1 治理链路总览</h2>
          <p>默认读取快照表与缓存，只有手动强制重算时才刷新工作台快照。</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-secondary" onclick="createRun('full_rerun')">全链路重跑登记</button>
          <button class="btn btn-ghost" onclick="window.location.hash='#fields'">查看字段治理</button>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat-box"><div class="stat-label">原始记录</div><div class="stat-value blue">${fmt(rawRows)}</div></div>
        <div class="stat-box"><div class="stat-label">合规过滤后</div><div class="stat-value">${fmt(filteredRows)}</div></div>
        <div class="stat-box"><div class="stat-label">Cell统计对象</div><div class="stat-value">${fmt(cellRows)}</div></div>
        <div class="stat-box"><div class="stat-label">最终明细</div><div class="stat-value green">${fmt(finalRows)}</div></div>
        <div class="stat-box"><div class="stat-label">GPS回填成功</div><div class="stat-value blue">${fmt(metricValue(currentSteps, 's31', 'filled_from_bs'))}</div></div>
        <div class="stat-box"><div class="stat-label">信号Cell补齐</div><div class="stat-value orange">${fmt(metricValue(currentSteps, 's33', 'by_cell'))}</div></div>
        <div class="stat-box"><div class="stat-label">疑似碰撞BS</div><div class="stat-value red">${fmt(metricValue(currentSteps, 's30', 'collision_suspect'))}</div></div>
        <div class="stat-box"><div class="stat-label">异常最高占比</div><div class="stat-value">${anomalies[0] ? pct([...anomalies].sort((a, b) => b.anomaly_ratio - a.anomaly_ratio)[0].anomaly_ratio) : '—'}</div></div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>链路节点</h3>
          <span class="card-subtitle">当前批次与对比批次的关键输出差异</span>
        </div>
        <div class="pipeline-flow">
          ${flowNodes.map((node, index) => `
            ${index > 0 ? '<div class="flow-arrow">→</div>' : ''}
            <a class="flow-node ${node.state}" href="${escapeHtml(node.href)}">
              <strong>${escapeHtml(node.label)}</strong>
              <span class="flow-count">${fmt(node.value)}</span>
              ${node.delta != null ? `<span class="flow-delta ${Number(node.delta) >= 0 ? 'up' : 'down'}">${escapeHtml(fmtDelta(node.delta))}</span>` : '<span class="flow-delta">—</span>'}
            </a>
          `).join('')}
        </div>
      </div>

      <div class="grid-2">
        ${runSummaryCard('当前批次', context?.current_run)}
        ${runSummaryCard('对比批次', context?.compare_run)}
      </div>

      <div class="card">
        <div class="card-title"><h3>步骤差异摘要</h3></div>
        ${diffTable}
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-title"><h3>重点关注</h3></div>
          <div class="focus-list">
            ${focusItems.map(item => `
              <div class="focus-item detail-panel">
                <span class="tag ${item.tagClass}">${escapeHtml(item.tag)}</span>
                <h4>${escapeHtml(item.title)}</h4>
                <p>${escapeHtml(item.detail)}</p>
              </div>
            `).join('')}
          </div>
        </div>
        <div class="card">
          <div class="card-title"><h3>异常摘要</h3></div>
          ${anomalyTable}
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-title"><h3>层级快照</h3></div>
          ${renderMetricTable(
            [
              { key: 'layer_label', label: '层级' },
              { key: 'row_count', label: '行数', className: 'num', render: value => fmt(value) },
              { key: 'pass_note', label: '说明' },
            ],
            currentLayers,
          )}
        </div>
        <div class="card">
          <div class="card-title"><h3>表空间概况</h3></div>
          ${renderMetricTable(
            [
              { key: 'table_name_cn', label: '表名', render: (value, row) => `${escapeHtml(value || row.table_name)}<span class="code-subtle">pipeline.${escapeHtml(row.table_name)}</span>` },
              { key: 'row_count', label: '行数', className: 'num', render: value => fmt(value) },
              { key: 'size_pretty', label: '大小', className: 'num' },
            ],
            overview.tables.slice(0, 12),
          )}
        </div>
      </div>
    `);
  } catch (error) {
    setMain(pageError('治理链路总览加载失败', error));
  }
}
