/**
 * D1/D2/D3 抽屉内容与交互。
 */

import { api, qs } from '../core/api.js';
import { SAMPLE_TYPE_LABELS, state } from '../core/state.js';
import {
  escapeHtml,
  openDrawer,
  fmt,
  renderMetricTable,
  showToast,
} from './common.js';
import {
  renderDisplayPairsTable,
  renderPayloadDiffTable,
  renderRuleHitChips,
  renderSampleItemsTable,
  renderSampleRemovedTable,
  sampleCompareTag,
} from './sample_views.js';

function sqlResolutionTag(status) {
  if (status === 'resolved_from_run_parameters') {
    return '<span class="tag tag-blue">已按批次参数解析</span>';
  }
  return '<span class="tag tag-gray">静态 SQL 资产</span>';
}

export async function openVersionDrawer() {
  const [history, changeLog] = await Promise.all([
    api('/version/history', { ttl: 120000 }),
    api('/version/change-log', { ttl: 120000 }),
  ]);

  const changeSection = (changeLog.version_changes || []).some(c => c.changed)
    ? `
      <div class="detail-panel" style="margin-bottom:16px">
        <h4>版本变化摘要</h4>
        ${renderMetricTable(
          [
            { key: 'category', label: '类别' },
            { key: 'current', label: '当前' },
            { key: 'compare', label: '对比' },
            { key: 'changed', label: '变化', render: v => v ? '<span class="tag tag-orange">已变</span>' : '<span class="tag tag-gray">不变</span>' },
          ],
          changeLog.version_changes.filter(c => c.changed),
        )}
      </div>
      ${(changeLog.parameter_changes || []).length ? `
        <div class="detail-panel" style="margin-bottom:16px">
          <h4>参数变化详情</h4>
          ${renderMetricTable(
            [
              { key: 'section', label: '参数区' },
              { key: 'current', label: '当前值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : v) },
              { key: 'compare', label: '对比值', render: v => escapeHtml(typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : v) },
            ],
            changeLog.parameter_changes,
          )}
        </div>
      ` : ''}
    `
    : '<div class="detail-panel" style="margin-bottom:16px"><p>当前批次与对比批次的版本标识无变化。</p></div>';

  openDrawer({
    title: '版本与运行抽屉',
    kicker: 'D1',
    body: `
      ${changeSection}
      <div class="detail-panel">
        <h4>运行历史</h4>
        ${renderMetricTable(
          [
            { key: 'run_id', label: '批次', render: value => `#${escapeHtml(value)}` },
            { key: 'run_mode_label', label: '类型' },
            { key: 'status_label', label: '状态' },
            { key: 'parameter_version', label: '参数集' },
            { key: 'rule_version', label: '规则集' },
            { key: 'sql_version', label: 'SQL包' },
            { key: 'contract_version', label: '契约' },
            { key: 'duration_pretty', label: '耗时' },
          ],
          history.items || [],
        )}
      </div>
    `,
  });
}

export async function openSqlDrawer(stepId, index = 0) {
  const sqlInfo = state.sqlCache.get(stepId) || await api(`/steps/${stepId}/sql`, { ttl: 1800000 });
  const file = sqlInfo.files?.[index];
  const compareFile = sqlInfo.compare_files?.[index];
  if (!file) {
    showToast('未找到 SQL 文件');
    return;
  }
  const compareChanged = compareFile && (
    (compareFile.resolved_content || compareFile.content || '') !== (file.resolved_content || file.content || '')
  );
  openDrawer({
    title: file.rel_path,
    kicker: 'D2 SQL 查看',
    body: `
      <div class="section-stack">
        <div class="detail-panel">
          <div class="chips">
            <span class="chip">步骤顺序 #${escapeHtml(sqlInfo.step_order || '—')}</span>
            <span class="chip">当前批次 #${escapeHtml(sqlInfo.run_id || '—')}</span>
            <span class="chip">当前参数集 ${escapeHtml(sqlInfo.parameter_set_version || '—')}</span>
            <span class="chip">当前 SQL包 ${escapeHtml(sqlInfo.sql_bundle_version || '—')}</span>
            ${sqlInfo.compare_run_id ? `<span class="chip">对比批次 #${escapeHtml(sqlInfo.compare_run_id)}</span>` : ''}
            ${sqlInfo.compare_parameter_set_version ? `<span class="chip">对比参数集 ${escapeHtml(sqlInfo.compare_parameter_set_version)}</span>` : ''}
            ${sqlInfo.compare_sql_bundle_version ? `<span class="chip">对比 SQL包 ${escapeHtml(sqlInfo.compare_sql_bundle_version)}</span>` : ''}
          </div>
          <div class="chips" style="margin-top:10px">${sqlResolutionTag(file.resolution_status)}</div>
        </div>
        ${file.resolved_parameters?.length ? `
          <div class="detail-panel">
            <h4>当前参数绑定</h4>
            ${renderMetricTable(
              [
                { key: 'alias', label: 'SQL别名' },
                { key: 'path', label: '参数路径' },
                { key: 'value', label: '生效值', render: value => escapeHtml(value == null ? '—' : value) },
              ],
              file.resolved_parameters,
            )}
          </div>
        ` : ''}
        <div class="detail-panel">
          <h4>当前 SQL</h4>
          <div class="sql-block"><pre>${escapeHtml(file.resolved_content || file.content || '')}</pre></div>
        </div>
        ${compareChanged ? `
          <div class="detail-panel">
            <div class="chips" style="margin-bottom:12px">${sqlResolutionTag(compareFile.resolution_status)}</div>
            ${compareFile.resolved_parameters?.length ? renderMetricTable(
              [
                { key: 'alias', label: 'SQL别名' },
                { key: 'path', label: '参数路径' },
                { key: 'value', label: '生效值', render: value => escapeHtml(value == null ? '—' : value) },
              ],
              compareFile.resolved_parameters,
            ) : '<div class="empty-state">对比批次没有额外参数绑定</div>'}
          </div>
          <div class="detail-panel">
            <h4>对比 SQL</h4>
            <div class="sql-block"><pre>${escapeHtml(compareFile.resolved_content || compareFile.content || '')}</pre></div>
          </div>
        ` : ''}
      </div>
    `,
  });
}

export async function openSampleDrawer(sampleSetId, runId = state.sampleRunId, compareRunId = null) {
  const detail = await api(`/samples/${sampleSetId}${qs({ run_id: runId, compare_run_id: compareRunId })}`, { ttl: 300000 });
  const ss = detail.sample_set;
  const summary = detail.summary || {};

  openDrawer({
    title: ss.name,
    kicker: 'D3 样本详情',
    body: `
      <div class="section-stack">
        <div class="detail-panel">
          <h4>${escapeHtml(ss.description || '')}</h4>
          <div class="chips" style="margin-bottom:12px">
            <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[ss.sample_type] || ss.sample_type)}</span>
            <span class="chip">${escapeHtml(ss.source_table_cn || ss.source_table || '—')}</span>
            <span class="chip">当前批次 #${escapeHtml(detail.run_id || '—')}</span>
            ${detail.compare_run_id ? `<span class="chip">对比批次 #${escapeHtml(detail.compare_run_id)}</span>` : ''}
            <span class="chip">当前对象 ${fmt(summary.current_count || 0)}</span>
            <span class="chip">对比对象 ${fmt(summary.compare_count || 0)}</span>
            <span class="chip">新增 ${fmt(summary.added_count || 0)}</span>
            <span class="chip">变化 ${fmt(summary.changed_count || 0)}</span>
            <span class="chip">消失 ${fmt(summary.removed_count || 0)}</span>
            ${(ss.step_ids || []).map(s => `<span class="chip">${escapeHtml(s)}</span>`).join('')}
          </div>
        </div>
        <div class="detail-panel">
          <h4>当前批次对象</h4>
          ${renderSampleItemsTable(detail.items, {
            sampleSetId,
            runId: detail.run_id,
            compareRunId: detail.compare_run_id,
            emptyText: '当前批次暂无对象样本',
          })}
        </div>
        <div class="detail-panel">
          <h4>对比批次独有对象</h4>
          ${renderSampleRemovedTable(detail.removed_items, {
            sampleSetId,
            runId: detail.run_id,
            compareRunId: detail.compare_run_id,
          })}
        </div>
      </div>
    `,
  });
}

export async function openSampleObjectDrawer(sampleSetId, objectKey, runId = state.sampleRunId, compareRunId = null) {
  const detail = await api(
    `/samples/${sampleSetId}/objects/${encodeURIComponent(objectKey)}${qs({ run_id: runId, compare_run_id: compareRunId })}`,
    { ttl: 300000 },
  );
  openDrawer({
    title: detail.object_label || detail.object_key,
    kicker: 'D3 对象详情',
    body: `
      <div class="section-stack">
        <div class="detail-panel">
          <div class="chips">
            <span class="chip">${escapeHtml(detail.sample_set.source_table_cn || detail.sample_set.source_table || '—')}</span>
            <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[detail.sample_set.sample_type] || detail.sample_set.sample_type)}</span>
            <span class="chip">当前批次 #${escapeHtml(detail.run_id || '—')}</span>
            ${detail.compare_run_id ? `<span class="chip">对比批次 #${escapeHtml(detail.compare_run_id)}</span>` : ''}
          </div>
          <div class="chips" style="margin-top:10px">
            ${sampleCompareTag(detail.compare_state)}
          </div>
          <div class="chips" style="margin-top:10px">
            ${renderRuleHitChips(detail.rule_hits)}
          </div>
        </div>
        <div class="detail-panel">
          <h4>原始值与处理后值</h4>
          ${renderDisplayPairsTable(detail.display_pairs)}
        </div>
        <div class="detail-panel">
          <h4>变化字段</h4>
          ${detail.changed_fields?.length ? renderMetricTable(
            [
              { key: 'field', label: '字段' },
              { key: 'current', label: '当前值', render: value => escapeHtml(value == null ? '—' : value) },
              { key: 'compare', label: '对比值', render: value => escapeHtml(value == null ? '—' : value) },
            ],
            detail.changed_fields,
          ) : '<div class="empty-state">当前对象与对比对象没有字段变化</div>'}
        </div>
        <div class="detail-panel">
          <h4>当前值 / 对比值全量载荷</h4>
          ${renderPayloadDiffTable(detail.current_payload, detail.compare_payload)}
        </div>
      </div>
    `,
  });
}

export async function openFieldDrawer(fieldName, tableName) {
  const { qs } = await import('../core/api.js');
  const detail = await api(`/fields/${encodeURIComponent(fieldName)}${qs({ table_name: tableName })}`, { ttl: 600000 });
  openDrawer({
    title: `${detail.field.field_name_cn || detail.field.field_name}`,
    kicker: '字段详情',
    body: `
      <div class="section-stack">
        <div class="detail-panel">
          <h4>基础信息</h4>
          <p>${escapeHtml(detail.field.description || '暂无描述')}</p>
          <div class="chips">
            <span class="chip">${escapeHtml(detail.field.table_name_cn || detail.field.table_name)}</span>
            <span class="chip">${escapeHtml(detail.field.data_type)}</span>
            <span class="chip">${escapeHtml(detail.field.health_status)}</span>
          </div>
        </div>
        <div class="detail-panel">
          <h4>健康度</h4>
          <div class="chips">
            <span class="chip">空值率 ${escapeHtml(pct(detail.health.null_rate))}</span>
            <span class="chip">近似基数 ${escapeHtml(fmt(detail.health.distinct_estimate))}</span>
          </div>
        </div>
        <div class="detail-panel">
          <h4>影响步骤</h4>
          <p>${escapeHtml((detail.related_steps || []).join(', ') || '—')}</p>
        </div>
        <div class="detail-panel">
          <h4>映射规则</h4>
          ${detail.mapping_rules?.length
            ? renderMetricTable(
                [
                  { key: 'rule_code', label: '规则编码' },
                  { key: 'rule_name', label: '规则名' },
                  { key: 'source_expression', label: '来源表达式' },
                  { key: 'target_expression', label: '目标表达式' },
                ],
                detail.mapping_rules,
              )
            : '<div class="empty-state">暂无映射规则</div>'}
        </div>
      </div>
    `,
  });
}
