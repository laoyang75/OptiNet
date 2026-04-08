/**
 * 入口、路由、全局事件挂载。
 */

import { api, clearApiCache } from './core/api.js';
import { state } from './core/state.js';
import { escapeHtml, setMain, showToast, pageError, timeAgo, closeDrawer } from './ui/common.js';
import {
  openVersionDrawer,
  openSqlDrawer,
  openSampleDrawer,
  openSampleObjectDrawer,
  openFieldDrawer,
} from './ui/drawers.js';
import { loadOverview } from './pages/overview.js';
import { loadStep } from './pages/step.js';
import { loadFields, applyFieldFilters } from './pages/fields.js';
import { loadSamples } from './pages/samples.js';

function routeFromHash() {
  const raw = (window.location.hash || '#overview').replace(/^#/, '');
  if (!raw || raw === 'overview') return { page: 'overview' };
  if (raw === 'fields') return { page: 'fields' };
  if (raw === 'samples') return { page: 'samples' };
  if (raw.startsWith('step/')) return { page: 'step', stepId: raw.split('/')[1] };
  return { page: 'overview' };
}

function setActiveNav(route) {
  document.querySelectorAll('.nav-item').forEach(node => node.classList.remove('active'));
  if (route.page === 'step' && route.stepId) {
    const stepEl = document.querySelector(`.nav-item[data-step-id="${route.stepId}"]`);
    if (stepEl) stepEl.classList.add('active');
    return;
  }
  const pageEl = document.querySelector(`.nav-item[data-page="${route.page}"]`);
  if (pageEl) pageEl.classList.add('active');
}

export async function refreshContext(force = false) {
  state.context = await api('/version/current', { ttl: 60000, force });
  const current = state.context?.current_run;
  const compare = state.context?.compare_run;
  if (state.sampleRunId == null && current?.run_id != null) {
    state.sampleRunId = current.run_id;
  }
  document.getElementById('ctx-run').textContent = current ? `当前批次: #${current.run_id}` : '当前批次: —';
  document.getElementById('ctx-compare').textContent = compare ? `对比批次: #${compare.run_id}` : '对比批次: —';
  document.getElementById('ctx-params').textContent = `参数集: ${state.context?.versions?.parameter_set || '—'}`;
  document.getElementById('ctx-rules').textContent = `规则集: ${state.context?.versions?.rule_set || '—'}`;
  document.getElementById('ctx-sql').textContent = `SQL包: ${state.context?.versions?.sql_bundle || '—'}`;
  document.getElementById('ctx-contract').textContent = `契约: ${state.context?.versions?.contract || '—'}`;
  document.getElementById('ctx-baseline').textContent = `基线: ${state.context?.versions?.baseline || '—'}`;
  document.getElementById('ctx-refresh').textContent = `刷新: ${timeAgo(state.context?.generated_at)}`;
  return state.context;
}

async function renderSidebar() {
  const steps = await api('/steps?main_chain_only=true', { ttl: 1800000 });
  state.steps = steps;
  const nav = document.getElementById('nav-steps');
  nav.innerHTML = steps.map(step => `
    <a class="nav-item" data-step-id="${escapeHtml(step.step_id)}" href="#step/${escapeHtml(step.step_id)}">
      <span class="step-dot ${step.layer === 'L2' ? 'dot-green' : step.layer === 'L3' ? 'dot-blue' : step.layer === 'L4' ? 'dot-orange' : 'dot-red'}"></span>
      <span>${escapeHtml(step.step_name)}</span>
      <span class="step-count">${escapeHtml(step.layer)}</span>
    </a>
  `).join('');
}

async function createRun(runMode, extra = {}) {
  const payload = {
    run_mode: runMode,
    note: extra.note || `由工作台创建: ${runMode}`,
    ...extra,
  };
  const result = await api('/runs', { method: 'POST', body: payload, ttl: 0 });
  clearApiCache();
  await refreshContext(true);
  showToast(`已登记批次 #${result.run_id}`);
}

async function refreshWorkbench(forceRecompute = false) {
  try {
    if (forceRecompute) {
      setMain('<div class="loading">正在强制重算快照与元数据，请稍候...</div>');
      await api('/cache/refresh', { method: 'POST', ttl: 0 });
      showToast('快照与字段注册表已刷新');
    }
    clearApiCache();
    await refreshContext(true);
    await renderRoute(true);
  } catch (error) {
    setMain(pageError('刷新失败', error));
  }
}

async function renderRoute(force = false) {
  const route = routeFromHash();
  state.currentPage = route.page;
  state.currentStepId = route.stepId || null;
  setActiveNav(route);
  if (route.page === 'fields') return loadFields(force);
  if (route.page === 'samples') return loadSamples(force);
  if (route.page === 'step' && route.stepId) return loadStep(route.stepId, force);
  return loadOverview(force);
}

async function init() {
  document.getElementById('btn-refresh').addEventListener('click', () => refreshWorkbench(false));
  document.getElementById('btn-force-refresh').addEventListener('click', () => refreshWorkbench(true));
  document.getElementById('btn-version-drawer').addEventListener('click', openVersionDrawer);
  document.getElementById('drawer-close').addEventListener('click', closeDrawer);
  document.getElementById('drawer-backdrop').addEventListener('click', closeDrawer);
  window.addEventListener('hashchange', () => renderRoute(false));

  await renderSidebar();
  await refreshContext(false);
  await renderRoute(false);
}

// 暴露给 onclick 使用的全局函数
window.createRun = createRun;
window.refreshWorkbench = refreshWorkbench;
window.openVersionDrawer = openVersionDrawer;
window.openSqlDrawer = openSqlDrawer;
window.openSampleDrawer = openSampleDrawer;
window.openSampleObjectDrawer = openSampleObjectDrawer;
window.openFieldDrawer = openFieldDrawer;
window.applyFieldFilters = applyFieldFilters;

init().catch(error => {
  setMain(pageError('工作台初始化失败', error));
});
