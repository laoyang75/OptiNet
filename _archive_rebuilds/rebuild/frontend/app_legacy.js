const API = `${window.location.origin}/api/v1`;
const CACHE_NS = 'wy-workbench:v2:';

const PRIMARY_METRIC_CODES = {
  s0: 'total',
  s4: 'trusted_lac_cnt',
  s6: 'output_rows',
  s30: 'total_bs',
  s31: 'filled_from_bs',
  s33: 'by_cell',
  s41: 'total',
  s50: 'lac_profiles',
  s51: 'bs_profiles',
  s52: 'cell_profiles',
};

const TABLE_LABELS = {
  raw_records: '原始记录表',
  stats_base_raw: '基础统计表',
  fact_filtered: '合规过滤明细',
  stats_lac: 'LAC统计表',
  dim_lac_trusted: '可信LAC维表',
  dim_cell_stats: 'Cell统计维表',
  dim_bs_trusted: '可信BS维表',
  fact_gps_corrected: 'GPS修正明细',
  compare_gps: 'GPS对比结果',
  fact_signal_filled: '信号补齐明细',
  compare_signal: '信号对比结果',
  detect_anomaly_bs: 'BS异常标记',
  detect_collision: '碰撞不足标记',
  map_cell_bs: 'Cell-BS映射',
  fact_final: '最终回归明细',
  profile_lac: 'LAC画像',
  profile_bs: 'BS画像',
  profile_cell: 'Cell画像',
};

const SAMPLE_TYPE_LABELS = {
  bs: '基站样本',
  cell: 'Cell样本',
  lac: 'LAC样本',
  record: '记录样本',
};

const state = {
  steps: [],
  context: null,
  currentPage: 'overview',
  currentStepId: null,
  fields: null,
  fieldFilters: { search: '', table: '', status: '' },
  samples: null,
  sqlCache: new Map(),
};

const memoryCache = new Map();
const inflight = new Map();

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function jsLiteral(value) {
  return `'${String(value ?? '')
    .replaceAll('\\', '\\\\')
    .replaceAll("'", "\\'")}'`;
}

function fmt(value) {
  if (value == null || value === '') return '—';
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString('zh-CN');
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function fmtDelta(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const num = Number(value);
  const sign = num > 0 ? '+' : '';
  return `${sign}${fmt(num)}`;
}

function timeAgo(value) {
  if (!value) return '—';
  const diffMs = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diffMs)) return '—';
  const seconds = Math.max(0, Math.floor(diffMs / 1000));
  if (seconds < 60) return `${seconds}s 前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m 前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h 前`;
  const days = Math.floor(hours / 24);
  return `${days}d 前`;
}

function routeFromHash() {
  const raw = (window.location.hash || '#overview').replace(/^#/, '');
  if (!raw || raw === 'overview') return { page: 'overview' };
  if (raw === 'fields') return { page: 'fields' };
  if (raw === 'samples') return { page: 'samples' };
  if (raw.startsWith('step/')) return { page: 'step', stepId: raw.split('/')[1] };
  return { page: 'overview' };
}

function setMain(html) {
  document.getElementById('main-content').innerHTML = html;
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

function showToast(message, ttl = 2600) {
  const node = document.getElementById('toast');
  node.textContent = message;
  node.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => node.classList.add('hidden'), ttl);
}

function qs(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && value !== '') query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : '';
}

function sessionKey(key) {
  return `${CACHE_NS}${key}`;
}

function getCached(key, ttl) {
  const mem = memoryCache.get(key);
  if (mem && Date.now() - mem.ts < ttl) return mem.data;
  const raw = sessionStorage.getItem(sessionKey(key));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.ts < ttl) {
      memoryCache.set(key, parsed);
      return parsed.data;
    }
  } catch {}
  return null;
}

function setCached(key, data) {
  const payload = { ts: Date.now(), data };
  memoryCache.set(key, payload);
  try {
    sessionStorage.setItem(sessionKey(key), JSON.stringify(payload));
  } catch {}
}

function clearApiCache() {
  memoryCache.clear();
  Object.keys(sessionStorage)
    .filter(key => key.startsWith(CACHE_NS))
    .forEach(key => sessionStorage.removeItem(key));
}

async function api(path, {
  ttl = 300000,
  force = false,
  method = 'GET',
  body = null,
} = {}) {
  const key = `${method}:${path}`;
  const isCacheable = method === 'GET' && ttl > 0;
  if (isCacheable && !force) {
    const cached = getCached(key, ttl);
    if (cached != null) return cached;
  }
  if (inflight.has(key)) return inflight.get(key);

  const job = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${API}${path}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`${method} ${path} 失败: ${response.status} ${detail}`);
      }
      const data = await response.json();
      if (isCacheable) setCached(key, data);
      return data;
    } finally {
      clearTimeout(timeout);
      inflight.delete(key);
    }
  })();

  inflight.set(key, job);
  return job;
}

function pageError(title, error) {
  return `
    <div class="error-card">
      <h3>${escapeHtml(title)}</h3>
      <p style="margin-top:8px">${escapeHtml(error?.message || String(error))}</p>
    </div>
  `;
}

function tableNameLabel(name) {
  return TABLE_LABELS[name] || name || '—';
}

function metricValue(summaryRows, stepId, code) {
  const row = summaryRows.find(item => item.step_id === stepId);
  return row ? row[code] : null;
}

function metricLabel(summaryRows, stepId, code) {
  const row = summaryRows.find(item => item.step_id === stepId);
  return row?.metric_labels?.[code]?.label || code;
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

function toMapByStep(rows) {
  return new Map((rows || []).map(row => [row.step_id, row]));
}

function diffClass(delta) {
  if (delta == null || Number.isNaN(Number(delta)) || Number(delta) === 0) return '';
  return Number(delta) > 0 ? 'diff-positive' : 'diff-negative';
}

function renderMetricTable(columns, rows) {
  if (!rows || rows.length === 0) {
    return '<div class="empty-state">暂无数据</div>';
  }
  return `
    <table class="compact-table">
      <thead><tr>${columns.map(col => `<th>${escapeHtml(col.label)}</th>`).join('')}</tr></thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            ${columns.map(col => {
              const value = row[col.key];
              const html = col.render ? col.render(value, row) : escapeHtml(value == null ? '—' : value);
              return `<td class="${col.className || ''}">${html}</td>`;
            }).join('')}
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function openDrawer({ title, kicker = '详情', body }) {
  document.getElementById('drawer-title').textContent = title;
  document.getElementById('drawer-kicker').textContent = kicker;
  document.getElementById('drawer-body').innerHTML = body;
  document.getElementById('drawer').classList.remove('hidden');
  document.getElementById('drawer-backdrop').classList.remove('hidden');
}

function closeDrawer() {
  document.getElementById('drawer').classList.add('hidden');
  document.getElementById('drawer-backdrop').classList.add('hidden');
}

async function refreshContext(force = false) {
  state.context = await api('/version/current', { ttl: 60000, force });
  const current = state.context?.current_run;
  const compare = state.context?.compare_run;
  document.getElementById('ctx-run').textContent = current ? `Run: #${current.run_id}` : 'Run: —';
  document.getElementById('ctx-compare').textContent = compare ? `Compare: #${compare.run_id}` : 'Compare: —';
  document.getElementById('ctx-params').textContent = `参数集: ${state.context?.versions?.parameter_set || '—'}`;
  document.getElementById('ctx-rules').textContent = `规则集: ${state.context?.versions?.rule_set || '—'}`;
  document.getElementById('ctx-sql').textContent = `SQL: ${state.context?.versions?.sql_bundle || '—'}`;
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
  showToast(`已登记 Run #${result.run_id}`);
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

function runSummaryCard(title, run) {
  if (!run) {
    return `
      <div class="card">
        <div class="card-title"><h3>${escapeHtml(title)}</h3></div>
        <div class="empty-state">暂无可用 Run</div>
      </div>
    `;
  }
  return `
    <div class="card">
      <div class="card-title">
        <h3>${escapeHtml(title)} #${escapeHtml(run.run_id)}</h3>
        <span class="tag ${run.status === 'completed' ? 'tag-green' : run.status === 'running' ? 'tag-blue' : 'tag-red'}">${escapeHtml(run.status_label)}</span>
      </div>
      <table class="compact-table">
        <tbody>
          <tr><th>类型</th><td>${escapeHtml(run.run_mode_label)}</td></tr>
          <tr><th>输入窗口</th><td>${escapeHtml(run.input_window_start || '—')} ~ ${escapeHtml(run.input_window_end || '—')}</td></tr>
          <tr><th>原始记录</th><td class="num">${fmt(run.input_rows)}</td></tr>
          <tr><th>最终明细</th><td class="num">${fmt(run.final_rows)}</td></tr>
          <tr><th>参数集</th><td>${escapeHtml(run.parameter_set || '—')}</td></tr>
          <tr><th>规则集</th><td>${escapeHtml(run.rule_set || '—')}</td></tr>
          <tr><th>SQL版本</th><td>${escapeHtml(run.sql_bundle || '—')}</td></tr>
          <tr><th>契约版本</th><td>${escapeHtml(run.contract || '—')}</td></tr>
          <tr><th>耗时</th><td>${escapeHtml(run.duration_pretty || '—')}</td></tr>
        </tbody>
      </table>
    </div>
  `;
}

function buildOverviewDiffRows(currentSteps, compareSteps, currentLayers, compareLayers) {
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

function buildFocusItems(diffRows, anomalies, context) {
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
  if (context?.current_run) {
    items.push({
      tag: '运行上下文',
      tagClass: 'tag-blue',
      title: `当前 Run #${context.current_run.run_id}`,
      detail: `${context.current_run.run_mode_label}，状态 ${context.current_run.status_label}，参数集 ${context.current_run.parameter_set}。`,
    });
  }
  return items;
}

async function loadOverview(force = false) {
  setMain('<div class="loading">加载治理链路总览...</div>');
  try {
    const context = await refreshContext(force);
    const currentRunId = context?.current_run?.run_id;
    const compareRunId = context?.compare_run?.run_id;

    const [overview, currentSteps, currentLayers, anomalies, compareSteps, compareLayers] = await Promise.all([
      api('/pipeline/overview', { ttl: 300000, force }),
      api(`/metrics/step-summary${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/metrics/layer-snapshot${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/metrics/anomaly-summary${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      compareRunId ? api(`/metrics/step-summary${qs({ run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve([]),
      compareRunId ? api(`/metrics/layer-snapshot${qs({ run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve([]),
    ]);

    const rawRows = layerRow(currentLayers, 'L0_raw')?.row_count;
    const filteredRows = layerRow(currentLayers, 'L2_filtered')?.row_count;
    const cellRows = layerRow(currentLayers, 'L2_cell_stats')?.row_count;
    const finalRows = layerRow(currentLayers, 'L4_final')?.row_count;
    const focusItems = buildFocusItems(buildOverviewDiffRows(currentSteps, compareSteps, currentLayers, compareLayers), anomalies, context);

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
          <span class="card-subtitle">当前 Run 与 Compare Run 的关键输出差异</span>
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
        ${runSummaryCard('当前 Run', context?.current_run)}
        ${runSummaryCard('对比 Run', context?.compare_run)}
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

function renderParametersTable(parameters) {
  const entries = Object.entries(parameters || {});
  if (!entries.length) return '<div class="empty-state">当前步骤无专属参数</div>';
  return renderMetricTable(
    [
      { key: 'key', label: '参数名' },
      { key: 'value', label: '值', render: value => escapeHtml(typeof value === 'object' ? JSON.stringify(value) : value) },
    ],
    entries.map(([key, value]) => ({ key, value })),
  );
}

function renderJsonMetrics(jsonMetrics) {
  const entries = Object.entries(jsonMetrics || {});
  if (!entries.length) return '<div class="empty-state">暂无结构化指标</div>';
  return entries.map(([code, value]) => `
    <div class="card">
      <div class="card-title"><h4>${escapeHtml(code)}</h4></div>
      ${Array.isArray(value)
        ? renderMetricTable(
            Object.keys(value[0] || {}).map(key => ({
              key,
              label: key,
              render: cell => typeof cell === 'number' ? fmt(cell) : escapeHtml(cell),
            })),
            value,
          )
        : `<div class="json-block"><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></div>`}
    </div>
  `).join('');
}

function settled(result, fallback) {
  return result?.status === 'fulfilled' ? result.value : fallback;
}

async function loadStep(stepId, force = false) {
  setMain('<div class="loading">加载步骤工作台...</div>');
  try {
    const context = await refreshContext(force);
    const currentRunId = context?.current_run?.run_id;
    const compareRunId = context?.compare_run?.run_id;

    const [
      stepResult,
      ioResult,
      paramsResult,
      rulesResult,
      metricsResult,
      sqlResult,
      diffResult,
      samplesResult,
    ] = await Promise.allSettled([
      api(`/steps/${stepId}`, { ttl: 1800000, force }),
      api(`/steps/${stepId}/io-summary`, { ttl: 300000, force }),
      api(`/steps/${stepId}/parameters`, { ttl: 1800000, force }),
      api(`/steps/${stepId}/rules${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/steps/${stepId}/metrics${qs({ run_id: currentRunId })}`, { ttl: 300000, force }),
      api(`/steps/${stepId}/sql`, { ttl: 1800000, force }),
      compareRunId ? api(`/steps/${stepId}/diff${qs({ run_id: currentRunId, compare_run_id: compareRunId })}`, { ttl: 300000, force }) : Promise.resolve({ items: [] }),
      api(`/steps/${stepId}/samples`, { ttl: 300000, force }),
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
            <h4>${escapeHtml(sample.name)}</h4>
            <p>${escapeHtml(sample.description || '')}</p>
            <div class="chips">
              <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[sample.sample_type] || sample.sample_type)}</span>
              <span class="chip">${escapeHtml(sample.source_table_cn || sample.source_table || '—')}</span>
            </div>
            <div class="sample-preview">
              ${sample.records?.length
                ? renderMetricTable(
                    (sample.columns || Object.keys(sample.records[0] || {})).map(key => ({
                      key,
                      label: key,
                      render: value => escapeHtml(value == null ? '—' : value),
                    })),
                    sample.records,
                  )
                : '<div class="empty-state">暂无样本预览</div>'}
            </div>
            <div class="inline-actions" style="margin-top:12px">
              <button class="btn btn-ghost" onclick="openSampleDrawer(${sample.id})">详情抽屉</button>
              <button class="btn btn-secondary" onclick="createRun('sample_rerun', { sample_set_id: ${sample.id}, rerun_from_step: ${jsLiteral(stepId)}, note: ${jsLiteral(`样本重跑: ${sample.name}`)} })">样本重跑登记</button>
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
        <div class="card-title"><h3>E. SQL 资产</h3></div>
        ${sqlInfo.files?.length ? `
          <div class="sample-list">
            ${sqlInfo.files.map((file, index) => `
              <div class="detail-panel">
                <h4>${escapeHtml(file.rel_path)}</h4>
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
        <div class="card-title"><h3>G. Compare Run 差异</h3></div>
        ${diffTable}
      </div>

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

function filteredFields() {
  const items = state.fields?.items || [];
  const { search, table, status } = state.fieldFilters;
  return items.filter(item => {
    const matchedSearch = !search || item.field_name.includes(search) || (item.field_name_cn || '').includes(search);
    const matchedTable = !table || item.table_name === table;
    const matchedStatus = !status || item.health_status === status;
    return matchedSearch && matchedTable && matchedStatus;
  });
}

function renderFieldsTable() {
  const rows = filteredFields();
  return renderMetricTable(
    [
      {
        key: 'field_name_cn',
        label: '字段',
        render: (value, row) => `
            <a href="#" onclick="openFieldDrawer(${jsLiteral(row.field_name)}, ${jsLiteral(row.table_name)}); return false;">
            ${escapeHtml(value || row.field_name)}
          </a>
          <span class="code-subtle">${escapeHtml(row.field_name)}</span>
        `,
      },
      {
        key: 'table_name_cn',
        label: '所属表',
        render: (value, row) => `${escapeHtml(value || row.table_name)}<span class="code-subtle">pipeline.${escapeHtml(row.table_name)}</span>`,
      },
      { key: 'data_type', label: '类型' },
      { key: 'null_rate', label: '空值率', className: 'num', render: value => pct(value) },
      { key: 'health_status', label: '健康度', render: value => `<span class="tag ${value === '正常' ? 'tag-green' : value === '关注' ? 'tag-orange' : value === '异常' ? 'tag-red' : 'tag-gray'}">${escapeHtml(value)}</span>` },
      { key: 'impacted_steps', label: '影响步骤', render: value => (value || []).join(', ') || '—' },
    ],
    rows,
  );
}

async function loadFields(force = false) {
  setMain('<div class="loading">加载字段治理...</div>');
  try {
    await refreshContext(force);
    state.fields = await api('/fields', { ttl: 600000, force });
    const tables = [...new Set((state.fields.items || []).map(item => item.table_name))];
    const summary = state.fields.summary || {};
    setMain(`
      <div class="page-head">
        <div>
          <h2>P3 字段治理</h2>
          <p>字段注册表来自 meta registry + pg_stats 近似健康指标。</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-ghost" onclick="refreshWorkbench(true)">重建字段注册表</button>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat-box"><div class="stat-label">字段总数</div><div class="stat-value blue">${fmt(summary.total)}</div></div>
        <div class="stat-box"><div class="stat-label">正常</div><div class="stat-value green">${fmt(summary.normal)}</div></div>
        <div class="stat-box"><div class="stat-label">关注</div><div class="stat-value orange">${fmt(summary.attention)}</div></div>
        <div class="stat-box"><div class="stat-label">异常</div><div class="stat-value red">${fmt(summary.anomalous)}</div></div>
      </div>

      <div class="toolbar">
        <label class="control">搜索
          <input id="field-search" value="${escapeHtml(state.fieldFilters.search)}" placeholder="字段名 / 中文名" oninput="applyFieldFilters()">
        </label>
        <label class="control">表
          <select id="field-table" onchange="applyFieldFilters()">
            <option value="">全部</option>
            ${tables.map(table => `<option value="${escapeHtml(table)}">${escapeHtml(tableNameLabel(table))}</option>`).join('')}
          </select>
        </label>
        <label class="control">健康度
          <select id="field-status" onchange="applyFieldFilters()">
            <option value="">全部</option>
            <option value="正常">正常</option>
            <option value="关注">关注</option>
            <option value="异常">异常</option>
            <option value="待分析">待分析</option>
          </select>
        </label>
      </div>

      <div class="card" id="fields-table-wrapper">
        ${renderFieldsTable()}
      </div>
    `);

    document.getElementById('field-table').value = state.fieldFilters.table;
    document.getElementById('field-status').value = state.fieldFilters.status;
  } catch (error) {
    setMain(pageError('字段治理加载失败', error));
  }
}

function applyFieldFilters() {
  state.fieldFilters = {
    search: document.getElementById('field-search')?.value || '',
    table: document.getElementById('field-table')?.value || '',
    status: document.getElementById('field-status')?.value || '',
  };
  const wrapper = document.getElementById('fields-table-wrapper');
  if (wrapper) wrapper.innerHTML = renderFieldsTable();
}

async function loadSamples(force = false) {
  setMain('<div class="loading">加载样本研究...</div>');
  try {
    await refreshContext(force);
    const list = await api('/samples', { ttl: 300000, force });
    const details = await Promise.all((list.items || []).map(item => api(`/samples/${item.id}`, { ttl: 300000, force })));
    state.samples = details;
    setMain(`
      <div class="page-head">
        <div>
          <h2>P4 样本研究</h2>
          <p>当前提供碰撞BS、动态Cell、GPS漂移和信号未补齐四类系统样本集。</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-secondary" onclick="createRun('sample_rerun', { note: '从样本研究页发起样本重跑' })">登记样本重跑</button>
        </div>
      </div>

      <div class="sample-list">
        ${details.map(detail => `
          <div class="sample-card">
            <div class="card-title">
              <div>
                <h4>${escapeHtml(detail.sample_set.name)}</h4>
                <p>${escapeHtml(detail.sample_set.description || '')}</p>
              </div>
              <div class="chips">
                <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[detail.sample_set.sample_type] || detail.sample_set.sample_type)}</span>
                <span class="chip">${escapeHtml(detail.sample_set.source_table_cn || detail.sample_set.source_table || '—')}</span>
              </div>
            </div>
            <div class="sample-preview">
              ${detail.records?.length
                ? renderMetricTable(
                    detail.columns.map(key => ({
                      key,
                      label: key,
                      render: value => escapeHtml(value == null ? '—' : value),
                    })),
                    detail.records,
                  )
                : '<div class="empty-state">暂无样本预览</div>'}
            </div>
            <div class="inline-actions" style="margin-top:12px">
              <button class="btn btn-ghost" onclick="openSampleDrawer(${detail.sample_set.id})">详情抽屉</button>
              <button class="btn btn-secondary" onclick="createRun('sample_rerun', { sample_set_id: ${detail.sample_set.id}, note: ${jsLiteral(`样本重跑: ${detail.sample_set.name}`)} })">以此样本重跑</button>
            </div>
          </div>
        `).join('')}
      </div>
    `);
  } catch (error) {
    setMain(pageError('样本研究加载失败', error));
  }
}

async function openVersionDrawer() {
  const data = await api('/version/history', { ttl: 120000 });
  openDrawer({
    title: '版本与运行抽屉',
    kicker: 'D1',
    body: renderMetricTable(
      [
        { key: 'run_id', label: 'Run', render: value => `#${escapeHtml(value)}` },
        { key: 'run_mode_label', label: '类型' },
        { key: 'status_label', label: '状态' },
        { key: 'parameter_version', label: '参数集' },
        { key: 'rule_version', label: '规则集' },
        { key: 'sql_version', label: 'SQL' },
        { key: 'contract_version', label: '契约' },
        { key: 'duration_pretty', label: '耗时' },
      ],
      data.items || [],
    ),
  });
}

async function openSqlDrawer(stepId, index = 0) {
  const sqlInfo = state.sqlCache.get(stepId) || await api(`/steps/${stepId}/sql`, { ttl: 1800000 });
  const file = sqlInfo.files?.[index];
  if (!file) {
    showToast('未找到 SQL 文件');
    return;
  }
  openDrawer({
    title: file.rel_path,
    kicker: 'D2 SQL 查看',
    body: `<div class="sql-block"><pre>${escapeHtml(file.content || '')}</pre></div>`,
  });
}

async function openSampleDrawer(sampleSetId) {
  const detail = await api(`/samples/${sampleSetId}`, { ttl: 300000 });
  openDrawer({
    title: detail.sample_set.name,
    kicker: 'D3 样本详情',
    body: `
      <div class="detail-panel">
        <h4>${escapeHtml(detail.sample_set.description || '')}</h4>
        <div class="chips" style="margin-bottom:12px">
          <span class="chip">${escapeHtml(SAMPLE_TYPE_LABELS[detail.sample_set.sample_type] || detail.sample_set.sample_type)}</span>
          <span class="chip">${escapeHtml(detail.sample_set.source_table_cn || detail.sample_set.source_table || '—')}</span>
        </div>
        ${detail.records?.length
          ? renderMetricTable(
              detail.columns.map(key => ({
                key,
                label: key,
                render: value => escapeHtml(value == null ? '—' : value),
              })),
              detail.records,
            )
          : '<div class="empty-state">暂无样本记录</div>'}
      </div>
    `,
  });
}

async function openFieldDrawer(fieldName, tableName) {
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

window.createRun = createRun;
window.refreshWorkbench = refreshWorkbench;
window.openVersionDrawer = openVersionDrawer;
window.openSqlDrawer = openSqlDrawer;
window.openSampleDrawer = openSampleDrawer;
window.openFieldDrawer = openFieldDrawer;
window.applyFieldFilters = applyFieldFilters;

init().catch(error => {
  setMain(pageError('工作台初始化失败', error));
});
