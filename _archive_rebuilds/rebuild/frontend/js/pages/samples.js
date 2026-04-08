/**
 * P4 样本研究页 + D3 入口。
 * 支持问题类型、来源步骤与运行批次筛选。
 */

import { api, qs } from '../core/api.js';
import { SAMPLE_TYPE_LABELS, state } from '../core/state.js';
import {
  escapeHtml,
  jsLiteral,
  fmt,
  setMain,
  pageError,
} from '../ui/common.js';
import { renderSampleItemsTable } from '../ui/sample_views.js';
import { refreshContext } from '../main.js';

let allDetails = [];
let sampleFilters = { type: '', step: '' };

function filteredSamples() {
  return allDetails.filter(detail => {
    const ss = detail.sample_set;
    if (sampleFilters.type && ss.sample_type !== sampleFilters.type) return false;
    if (sampleFilters.step && !(ss.step_ids || []).includes(sampleFilters.step)) return false;
    return true;
  });
}

function renderSampleCards(details, context) {
  if (!details.length) return '<div class="empty-state">没有匹配的样本集</div>';
  return details.map(detail => {
    const ss = detail.sample_set;
    const summary = detail.summary || {};
    return `
      <div class="sample-card">
        <div class="card-title">
          <div>
            <h4>${escapeHtml(ss.name)}</h4>
            <p>${escapeHtml(ss.description || '')}</p>
          </div>
          <div class="chips">
            <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[ss.sample_type] || ss.sample_type)}</span>
            <span class="chip">${escapeHtml(ss.source_table_cn || ss.source_table || '—')}</span>
            ${(ss.step_ids || []).map(s => `<a href="#step/${escapeHtml(s)}" class="step-link">${escapeHtml(s)}</a>`).join(' ')}
          </div>
        </div>
        <div class="sample-stats" style="margin:8px 0">
          <span class="chip">当前对象 ${fmt(summary.current_count || 0)}</span>
          <span class="chip">对比对象 ${fmt(summary.compare_count || 0)}</span>
          <span class="chip">新增 ${fmt(summary.added_count || 0)}</span>
          <span class="chip">变化 ${fmt(summary.changed_count || 0)}</span>
          <span class="chip">消失 ${fmt(summary.removed_count || 0)}</span>
          <span class="chip">当前批次 #${escapeHtml(detail.run_id || '—')}</span>
          ${detail.compare_run_id ? `<span class="chip">对比批次 #${escapeHtml(detail.compare_run_id)}</span>` : ''}
        </div>
        <div class="sample-preview">
          ${renderSampleItemsTable(detail.items, {
            sampleSetId: ss.id,
            runId: detail.run_id,
            compareRunId: detail.compare_run_id,
            emptyText: '当前批次暂无对象样本',
          })}
        </div>
        <div class="inline-actions" style="margin-top:12px">
          <button class="btn btn-ghost" onclick="openSampleDrawer(${ss.id}, ${detail.run_id || 'null'}, ${detail.compare_run_id || 'null'})">详情抽屉</button>
          <button class="btn btn-secondary" onclick="createRun('sample_rerun', { sample_set_id: ${ss.id}, note: ${jsLiteral(`样本重跑: ${ss.name}`)} })">以此样本重跑</button>
        </div>
      </div>
    `;
  }).join('');
}

async function applySampleFilters() {
  const nextRunId = Number(document.getElementById('sample-run-filter')?.value || '') || null;
  if ((nextRunId || null) !== (state.sampleRunId || null)) {
    state.sampleRunId = nextRunId;
    await loadSamples(false);
    return;
  }
  sampleFilters = {
    type: document.getElementById('sample-type-filter')?.value || '',
    step: document.getElementById('sample-step-filter')?.value || '',
  };
  const wrapper = document.getElementById('sample-list-wrapper');
  if (wrapper) wrapper.innerHTML = renderSampleCards(filteredSamples());
}
window.applySampleFilters = () => { void applySampleFilters(); };

export async function loadSamples(force = false) {
  setMain('<div class="loading">加载样本研究...</div>');
  try {
    const context = await refreshContext(force);
    const history = await api('/version/history?limit=30', { ttl: 120000, force });
    state.versionHistory = history.items || [];

    const selectedRunId = state.sampleRunId || context?.current_run?.run_id || state.versionHistory[0]?.run_id || null;
    state.sampleRunId = selectedRunId;

    const list = await api(`/samples${qs({ run_id: selectedRunId })}`, { ttl: 300000, force });
    allDetails = await Promise.all(
      (list.items || []).map(item => api(`/samples/${item.id}${qs({ run_id: selectedRunId })}`, { ttl: 300000, force })),
    );
    state.samples = allDetails;

    const types = [...new Set(allDetails.map(d => d.sample_set.sample_type))];
    const steps = [...new Set(allDetails.flatMap(d => d.sample_set.step_ids || []))].sort();

    setMain(`
      <div class="page-head">
        <div>
          <h2>P4 样本研究</h2>
          <p>碰撞BS、动态Cell、GPS漂移和信号未补齐四类系统样本集，支持按问题类型、来源步骤和运行批次筛选。</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-secondary" onclick="createRun('sample_rerun', { note: '从样本研究页发起样本重跑' })">登记样本重跑</button>
        </div>
      </div>

      <div class="toolbar">
        <label class="control">运行批次
          <select id="sample-run-filter" onchange="applySampleFilters()">
            ${(state.versionHistory || []).map(run => `
              <option value="${escapeHtml(run.run_id)}" ${Number(run.run_id) === Number(selectedRunId) ? 'selected' : ''}>
                #${escapeHtml(run.run_id)} · ${escapeHtml(run.run_mode_label)} · ${escapeHtml(run.status_label)}
              </option>
            `).join('')}
          </select>
        </label>
        <label class="control">问题类型
          <select id="sample-type-filter" onchange="applySampleFilters()">
            <option value="">全部</option>
            ${types.map(t => `<option value="${escapeHtml(t)}" ${sampleFilters.type === t ? 'selected' : ''}>${escapeHtml(SAMPLE_TYPE_LABELS[t] || t)}</option>`).join('')}
          </select>
        </label>
        <label class="control">来源步骤
          <select id="sample-step-filter" onchange="applySampleFilters()">
            <option value="">全部</option>
            ${steps.map(s => `<option value="${escapeHtml(s)}" ${sampleFilters.step === s ? 'selected' : ''}>${escapeHtml(s)}</option>`).join('')}
          </select>
        </label>
      </div>

      <div id="sample-list-wrapper" class="sample-list">
        ${renderSampleCards(filteredSamples())}
      </div>
    `);
  } catch (error) {
    setMain(pageError('样本研究加载失败', error));
  }
}
