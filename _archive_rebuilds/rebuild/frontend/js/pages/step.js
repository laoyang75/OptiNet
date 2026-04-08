/**
 * P2 步骤工作台页。
 */

import { api, qs } from '../core/api.js';
import { SAMPLE_TYPE_LABELS, state } from '../core/state.js';
import {
  escapeHtml,
  jsLiteral,
  fmt,
  pct,
  fmtDelta,
  diffClass,
  setMain,
  pageError,
  renderMetricTable,
  renderParametersTable,
  renderJsonMetrics,
  settled,
  tableNameLabel,
} from '../ui/common.js';
import { renderRuleHitChips, renderSampleItemsTable } from '../ui/sample_views.js';
import { refreshContext } from '../main.js';

function sqlResolutionTag(status) {
  return status === 'resolved_from_run_parameters'
    ? '<span class="tag tag-blue">按批次参数解析</span>'
    : '<span class="tag tag-gray">静态 SQL 资产</span>';
}

function payloadPreview(payload, limit = 3) {
  const entries = Object.entries(payload || {});
  if (!entries.length) return '—';
  const preview = entries.slice(0, limit)
    .map(([key, value]) => `${key}=${value == null ? '—' : value}`)
    .join('；');
  return entries.length > limit ? `${preview} …` : preview;
}

function renderObjectDiffSection(objectDiff) {
  const summary = objectDiff.summary || {};
  if (!summary.added_count && !summary.removed_count && !summary.changed_count) {
    return '<div class="empty-state">当前没有对象级差异。</div>';
  }
  return `
    <div class="section-stack">
      <div class="chips">
        <span class="chip">新增 ${fmt(summary.added_count || 0)}</span>
        <span class="chip">变化 ${fmt(summary.changed_count || 0)}</span>
        <span class="chip">消失 ${fmt(summary.removed_count || 0)}</span>
        <span class="chip">当前批次 #${escapeHtml(objectDiff.current_run_id || '—')}</span>
        <span class="chip">对比批次 #${escapeHtml(objectDiff.compare_run_id || '—')}</span>
      </div>
      <div class="detail-panel">
        <h4>变化对象</h4>
        ${objectDiff.changed?.length ? renderMetricTable(
          [
            { key: 'object_label', label: '对象' },
            { key: 'rule_hits', label: '命中规则', render: value => `<div class="chips">${renderRuleHitChips(value)}</div>` },
            { key: 'changed_fields', label: '变化字段数', className: 'num', render: value => fmt(value?.length || 0) },
            { key: 'changed_fields', label: '变化摘要', render: value => escapeHtml((value || []).slice(0, 3).map(item => item.field).join('、') || '—') },
          ],
          objectDiff.changed,
        ) : '<div class="empty-state">没有字段变化对象</div>'}
      </div>
      <div class="grid-2">
        <div class="detail-panel">
          <h4>当前新增对象</h4>
          ${objectDiff.added?.length ? renderMetricTable(
            [
              { key: 'object_label', label: '对象' },
              { key: 'rule_hits', label: '命中规则', render: value => `<div class="chips">${renderRuleHitChips(value)}</div>` },
              { key: 'current_payload', label: '对象摘要', render: value => escapeHtml(payloadPreview(value)) },
            ],
            objectDiff.added,
          ) : '<div class="empty-state">没有新增对象</div>'}
        </div>
        <div class="detail-panel">
          <h4>对比批次独有对象</h4>
          ${objectDiff.removed?.length ? renderMetricTable(
            [
              { key: 'object_label', label: '对象' },
              { key: 'rule_hits', label: '命中规则', render: value => `<div class="chips">${renderRuleHitChips(value)}</div>` },
              { key: 'compare_payload', label: '对象摘要', render: value => escapeHtml(payloadPreview(value)) },
            ],
            objectDiff.removed,
          ) : '<div class="empty-state">没有消失对象</div>'}
        </div>
      </div>
    </div>
  `;
}

export async function loadStep(stepId, force = false) {
  setMain('<div class="loading">加载步骤工作台...</div>');
  try {
    const context = await refreshContext(force);
    const currentRunId = context?.current_run?.run_id;
    const compareRunId = context?.compare_run?.run_id;

    const [
      stepResult, ioResult, paramsResult, rulesResult,
      metricsResult, sqlResult, diffResult, samplesResult,
      paramDiffResult, objectDiffResult,
    ] = await Promise.allSettled([
      api(`/steps/${stepId}`, { ttl: 1800000, force }),
      api(`/steps/${stepId}/io-summary`, { ttl: 300000, force }),
      api(`/steps/${stepId}/parameters${qs({ run_id: currentRunId })}`, { ttl: 1800000, force }),
      api(`/steps/${stepId}/rules${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/steps/${stepId}/metrics${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/steps/${stepId}/sql${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 1800000, force }),
      compareRunId ? api(`/steps/${stepId}/diff${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve({ items: [] }),
      api(`/steps/${stepId}/samples${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 300000, force }),
      compareRunId ? api(`/steps/${stepId}/parameter-diff${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve({ global_diff: [], step_diff: [] }),
      compareRunId ? api(`/steps/${stepId}/object-diff${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve({ added: [], removed: [], changed: [] }),
    ]);

    if (stepResult.status !== 'fulfilled') throw stepResult.reason;
    if (ioResult.status !== 'fulfilled') throw ioResult.reason;
    if (paramsResult.status !== 'fulfilled') throw paramsResult.reason;
    if (metricsResult.status !== 'fulfilled') throw metricsResult.reason;

    const step = stepResult.value;
    const io = ioResult.value;
    const params = paramsResult.value;
    const rules = settled(rulesResult, { rules: [] });
    const metrics = metricsResult.value;
    const sqlInfo = settled(sqlResult, { files: [] });
    const diff = settled(diffResult, { items: [] });
    const samples = settled(samplesResult, { sample_sets: [] });
    const paramDiff = settled(paramDiffResult, { global_diff: [], step_diff: [] });
    const objectDiff = settled(objectDiffResult, { added: [], removed: [], changed: [] });

    state.sqlCache.set(stepId, sqlInfo);
    const inputTables = (io.tables || []).filter(item => item.direction === 'input');
    const outputTables = (io.tables || []).filter(item => item.direction === 'output');

    const ruleTable = rules.rules?.length
      ? renderMetricTable(
          [
            { key: 'rule_name', label: '规则' },
            { key: 'rule_purpose', label: '目的' },
            { key: 'hit_count', label: '命中数', className: 'num', render: value => fmt(value) },
            { key: 'total_count', label: '总数', className: 'num', render: value => fmt(value) },
            { key: 'hit_ratio', label: '命中率', className: 'num', render: value => pct(value) },
          ],
          rules.rules,
        )
      : '<div class="empty-state">当前步骤暂无规则命中数据</div>';

    const metricCards = metrics.cards?.length
      ? `
          <div class="stat-grid">
            ${metrics.cards.map(card => `
              <div class="stat-box">
                <div class="stat-label">${escapeHtml(card.metric_name)}</div>
                <div class="stat-value ${card.metric_code.includes('collision') ? 'red' : card.metric_code.includes('filled') ? 'blue' : ''}">
                  ${escapeHtml(card.unit === '%' ? pct(card.value) : fmt(card.value))}
                </div>
                <div class="card-subtitle">${escapeHtml(card.metric_code)}${card.unit ? ` · ${escapeHtml(card.unit)}` : ''}</div>
              </div>
            `).join('')}
          </div>
        `
      : '<div class="empty-state">当前步骤暂无快照指标</div>';

    const diffTable = diff.items?.length
      ? renderMetricTable(
          [
            { key: 'metric_name', label: '指标' },
            { key: 'current_value', label: `当前 #${context?.current_run?.run_id || '—'}`, className: 'num', render: value => fmt(value) },
            { key: 'compare_value', label: `对比 #${context?.compare_run?.run_id || '—'}`, className: 'num', render: value => fmt(value) },
            { key: 'delta', label: '差值', className: 'num', render: value => `<span class="${diffClass(value)}">${escapeHtml(fmtDelta(value))}</span>` },
          ],
          diff.items,
        )
      : '<div class="empty-state">当前没有可用的 compare run 差异数据</div>';

    const sampleBlocks = samples.sample_sets?.length
      ? samples.sample_sets.map(sample => `
          <div class="sample-card">
            <h4>${escapeHtml(sample.sample_set.name)}</h4>
            <p>${escapeHtml(sample.sample_set.description || '')}</p>
            <div class="chips">
              <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[sample.sample_set.sample_type] || sample.sample_set.sample_type)}</span>
              <span class="chip">${escapeHtml(sample.sample_set.source_table_cn || sample.sample_set.source_table || '—')}</span>
              <span class="chip">当前对象 ${fmt(sample.summary?.current_count || 0)}</span>
              <span class="chip">变化 ${fmt(sample.summary?.changed_count || 0)}</span>
            </div>
            <div class="sample-preview">
              ${renderSampleItemsTable(sample.items, {
                sampleSetId: sample.sample_set.id,
                runId: sample.run_id,
                compareRunId: sample.compare_run_id,
                emptyText: '当前步骤没有对象样本',
              })}
            </div>
            <div class="inline-actions" style="margin-top:12px">
              <button class="btn btn-ghost" onclick="openSampleDrawer(${sample.sample_set.id}, ${sample.run_id || 'null'}, ${sample.compare_run_id || 'null'})">详情抽屉</button>
              <button class="btn btn-secondary" onclick="createRun('sample_rerun', { sample_set_id: ${sample.sample_set.id}, rerun_from_step: ${jsLiteral(stepId)}, note: ${jsLiteral(`样本重跑: ${sample.sample_set.name}`)} })">样本重跑登记</button>
            </div>
          </div>
        `).join('')
      : '<div class="empty-state">当前步骤未绑定样本集。</div>';

    setMain(`
      <div class="page-head">
        <div>
          <h2>${escapeHtml(step.step_name)}</h2>
          <p>${escapeHtml(step.description || '该步骤暂无补充说明。')}</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-secondary" onclick="createRun('partial_rerun', { rerun_from_step: ${jsLiteral(stepId)}, note: ${jsLiteral(`局部重跑: ${step.step_name}`)} })">从此步骤开始重跑</button>
          <button class="btn btn-ghost" onclick="openVersionDrawer()">查看版本</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><h3>A. 步骤说明</h3></div>
        <div class="grid-2">
          <div class="detail-panel">
            <h4>业务目的</h4>
            <p>${escapeHtml(step.description || '—')}</p>
          </div>
          <div class="detail-panel">
            <h4>技术标识</h4>
            <div class="chips">
              <span class="chip">步骤编号 ${escapeHtml(step.step_id)}</span>
              <span class="chip">层级 ${escapeHtml(step.layer)}</span>
              <span class="chip">${step.is_main_chain ? '主链路' : '附加步骤'}</span>
              <span class="chip">${escapeHtml(step.step_name_en || '—')}</span>
            </div>
            <p style="margin-top:12px">SQL 文件：${escapeHtml(step.sql_file || '—')}</p>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-title"><h3>B. 输入表</h3></div>
          ${renderMetricTable(
            [
              { key: 'table_name', label: '表', render: value => `${escapeHtml(tableNameLabel(value))}<span class="code-subtle">pipeline.${escapeHtml(value)}</span>` },
              { key: 'row_count', label: '行数', className: 'num', render: value => fmt(value) },
            ],
            inputTables,
          )}
        </div>
        <div class="card">
          <div class="card-title"><h3>B. 输出表</h3></div>
          ${renderMetricTable(
            [
              { key: 'table_name', label: '表', render: value => `${escapeHtml(tableNameLabel(value))}<span class="code-subtle">pipeline.${escapeHtml(value)}</span>` },
              { key: 'row_count', label: '行数', className: 'num', render: value => fmt(value) },
            ],
            outputTables,
          )}
        </div>
      </div>

      <div class="card">
        <div class="card-title"><h3>C. 规则区</h3></div>
        ${ruleTable}
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-title"><h3>D. 步骤参数</h3><span class="card-subtitle">${escapeHtml(params.parameter_set || '—')}</span></div>
          ${renderParametersTable(params.step)}
        </div>
        <div class="card">
          <div class="card-title"><h3>D. 全局参数</h3></div>
          ${renderParametersTable(params.global)}
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>E. SQL 资产</h3>
          <span class="card-subtitle">
            当前 SQL包 ${escapeHtml(sqlInfo.sql_bundle_version || '—')}
            ${sqlInfo.compare_sql_bundle_version ? ` · 对比 SQL包 ${escapeHtml(sqlInfo.compare_sql_bundle_version)}` : ''}
          </span>
        </div>
        ${sqlInfo.files?.length ? `
          <div class="sample-list">
            ${sqlInfo.files.map((file, index) => `
              <div class="detail-panel">
                <h4>${escapeHtml(file.rel_path)}</h4>
                <div class="chips">
                  <span class="chip">步骤顺序 #${escapeHtml(sqlInfo.step_order || '—')}</span>
                  <span class="chip">当前批次 #${escapeHtml(sqlInfo.run_id || '—')}</span>
                  <span class="chip">当前参数集 ${escapeHtml(sqlInfo.parameter_set_version || '—')}</span>
                  ${sqlInfo.compare_run_id ? `<span class="chip">对比批次 #${escapeHtml(sqlInfo.compare_run_id)}</span>` : ''}
                  ${sqlInfo.compare_parameter_set_version ? `<span class="chip">对比参数集 ${escapeHtml(sqlInfo.compare_parameter_set_version)}</span>` : ''}
                </div>
                <div class="chips" style="margin-top:10px">
                  ${sqlResolutionTag(file.resolution_status)}
                  <span class="chip">参数绑定 ${fmt(file.resolved_parameters?.length || 0)}</span>
                </div>
                <div class="inline-actions" style="margin-top:12px">
                  <button class="btn btn-ghost" onclick="openSqlDrawer(${jsLiteral(stepId)}, ${index})">查看 SQL</button>
                </div>
              </div>
            `).join('')}
          </div>
        ` : '<div class="empty-state">未找到对应 SQL 文件。</div>'}
      </div>

      <div class="card">
        <div class="card-title"><h3>F. 数据变化</h3></div>
        ${metricCards}
        <div class="section-stack">
          ${renderJsonMetrics(metrics.json_metrics)}
        </div>
      </div>

      <div class="card">
        <div class="card-title"><h3>G. 批次对比差异</h3></div>
        ${diffTable}
      </div>

      ${(paramDiff.step_diff?.some(i => i.changed) || paramDiff.global_diff?.some(i => i.changed)) ? `
      <div class="card">
        <div class="card-title"><h3>G2. 参数变化</h3></div>
        <div class="grid-2">
          <div>
            <h4 style="margin-bottom:8px">步骤参数变化</h4>
            ${paramDiff.step_diff?.filter(i => i.changed).length ? renderMetricTable(
              [
                { key: 'key', label: '参数' },
                { key: 'current', label: '当前值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v) : v) },
                { key: 'compare', label: '对比值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v) : v) },
              ],
              paramDiff.step_diff.filter(i => i.changed),
            ) : '<div class="empty-state">步骤参数无变化</div>'}
          </div>
          <div>
            <h4 style="margin-bottom:8px">全局参数变化</h4>
            ${paramDiff.global_diff?.filter(i => i.changed).length ? renderMetricTable(
              [
                { key: 'key', label: '参数' },
                { key: 'current', label: '当前值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v) : v) },
                { key: 'compare', label: '对比值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v) : v) },
              ],
              paramDiff.global_diff.filter(i => i.changed),
            ) : '<div class="empty-state">全局参数无变化</div>'}
          </div>
        </div>
      </div>
      ` : ''}

      ${objectDiff.changed?.length || objectDiff.added?.length || objectDiff.removed?.length ? `
      <div class="card">
        <div class="card-title"><h3>G3. 对象级差异</h3></div>
        ${renderObjectDiffSection(objectDiff)}
      </div>
      ` : ''}

      <div class="card">
        <div class="card-title"><h3>H. 样本区</h3></div>
        <div class="sample-list">${sampleBlocks}</div>
      </div>

      <div class="card">
        <div class="card-title"><h3>操作区</h3></div>
        <div class="inline-actions">
          <button class="btn btn-primary" onclick="createRun('partial_rerun', { rerun_from_step: ${jsLiteral(stepId)}, note: ${jsLiteral(`从步骤 ${step.step_name} 开始重跑`)} })">从此步骤开始重跑</button>
          <button class="btn btn-secondary" onclick="refreshWorkbench(true)">刷新此步骤快照</button>
          <button class="btn btn-ghost" onclick="window.location.hash='#samples'">转到样本研究</button>
        </div>
      </div>
    `);
  } catch (error) {
    setMain(pageError(`步骤 ${stepId} 加载失败`, error));
  }
}
