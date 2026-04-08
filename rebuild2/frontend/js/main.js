/**
 * 入口、路由、全局事件。
 */

import { state } from './core/state.js';
import { setMain, pageError, closeDrawer } from './ui/common.js';
import { loadRaw } from './pages/raw.js';
import { loadAudit } from './pages/audit.js';
import { loadOds } from './pages/ods.js';
import { loadL0Data } from './pages/l0data.js';
import { loadTrusted } from './pages/trusted.js';
import { loadEnrich } from './pages/enrich.js';
import { loadAnomaly } from './pages/anomaly.js';
import { loadProfile } from './pages/profile.js';
import { loadProfileBs } from './pages/profile_bs.js';
import { loadProfileCell } from './pages/profile_cell.js';

function routeFromHash() {
  const hash = (window.location.hash || '#raw').replace(/^#/, '');
  return { page: hash || 'raw' };
}

function setActiveNav(route) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const el = document.querySelector(`.nav-item[data-page="${route.page}"]`);
  if (el) el.classList.add('active');
}

const layerLabel = {
  raw: '原始数据 · 字段挑选',
  audit: 'L0 字段审计',
  ods: 'L1 ODS 标准化',
  l0data: 'L0 数据概览',
  trusted: 'L2 可信库',
  'bs-gps': 'L3 BS+GPS+信号',
  'anomaly': 'L3 问题数据研究',
  profile: 'L4 LAC 画像',
  'profile-bs': 'L4 BS 画像',
  'profile-cell': 'L4 Cell 画像',
};

async function renderRoute(force = false) {
  const route = routeFromHash();
  state.currentPage = route.page;
  setActiveNav(route);
  document.getElementById('ctx-layer').textContent = `当前层: ${layerLabel[route.page] || route.page}`;

  switch (route.page) {
    case 'raw': return loadRaw(force);
    case 'audit': return loadAudit(force);
    case 'ods': return loadOds(force);
    case 'l0data': return loadL0Data(force);
    case 'trusted': return loadTrusted(force);
    case 'bs-gps': return loadEnrich(force);
    case 'anomaly': return loadAnomaly(force);
    case 'profile': return loadProfile(force);
    case 'profile-bs': return loadProfileBs(force);
    case 'profile-cell': return loadProfileCell(force);
    default:
      setMain(`
        <div class="page-head"><div><h2>${layerLabel[route.page] || route.page}</h2><p>该层级尚未实现，请先完成前置层级。</p></div></div>
        <div class="card"><div class="empty-state">等待前置层级完成后解锁</div></div>
      `);
  }
}

async function init() {
  document.getElementById('drawer-close').addEventListener('click', closeDrawer);
  document.getElementById('drawer-backdrop').addEventListener('click', closeDrawer);
  window.addEventListener('hashchange', () => renderRoute(false));
  await renderRoute(false);
}

init().catch(error => {
  setMain(pageError('工作台初始化失败', error));
});
