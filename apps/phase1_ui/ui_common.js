(function () {
  const BUILTIN_SNAPSHOT = {
    "meta": {
      "project": "Phase1 可视化研究平台",
      "db_name": "ip_loc2",
      "snapshot_ts_utc": "2026-02-26T04:54:17.520Z",
      "run_id": "phase1_20260226_125354",
      "status": "s0_completed"
    },
    "row_counts": {
      "l0_rows": 118519386,
      "l2_rows": 21788648,
      "l3_bs_rows": 138121,
      "l4_final_rows": 30491963,
      "l5_lac_rows": 878,
      "l5_bs_rows": 163778,
      "l5_cell_rows": 493651
    },
    "gps_metrics": {
      "row_cnt": 30491963,
      "gps_fill_from_bs_cnt": 3959928,
      "gps_fill_from_bs_severe_collision_cnt": 2867,
      "gps_fill_from_risk_bs_cnt": 82255,
      "gps_not_filled_cnt": 119427
    },
    "signal_metrics": {
      "missing_field_before_sum": 73150482,
      "missing_field_after_sum": 63561699,
      "filled_field_sum": 9588783,
      "filled_by_cell_nearest_row_cnt": 30140602,
      "filled_by_bs_top_cell_row_cnt": 166068
    },
    "anomaly_counts": {
      "bs": { "collision": 8277, "severe_collision": 21, "dynamic_cell": 5, "bs_id_lt_256": 36, "multi_operator_shared": 51387 },
      "cell": { "collision": 36244, "severe_collision": 51, "dynamic_cell": 5, "bs_id_lt_256": 36, "multi_operator_shared": 163667 }
    },
    "gate_results": [
      { "gate_name": "行数守恒：Step40 vs Final", "pass": true, "actual_value": 30491963, "expected_value": 30491963, "diff_value": 0 },
      { "gate_name": "对账：Not_Filled 指标一致", "pass": true, "actual_value": 119427, "expected_value": 119427, "diff_value": 0 },
      { "gate_name": "对账：Severe Fill 指标一致", "pass": true, "actual_value": 2867, "expected_value": 2867, "diff_value": 0 },
      { "gate_name": "对账：bs_id_lt_256 指标一致", "pass": true, "actual_value": 2102, "expected_value": 2102, "diff_value": 0 },
      { "gate_name": "无效LAC泄漏（L5三表）", "pass": true, "actual_value": 0, "expected_value": 0, "diff_value": 0 },
      { "gate_name": "Layer5字段存在性：中文底表", "pass": true, "actual_value": 8, "expected_value": 8, "diff_value": 0 },
      { "gate_name": "Layer5字段存在性：EN视图", "pass": true, "actual_value": 8, "expected_value": 8, "diff_value": 0 }
    ],
    "closure_note": {
      "dynamic_all_scope_l4": 7,
      "dynamic_filtered_scope_l4": 5,
      "dynamic_l5": 5,
      "explain": "按 Step52 过滤口径（运营商+制式+有效键）闭环一致。"
    }
  };

  const termReplacements = [
    ["is_multi_operator_shared", "多运营商共享标记"],
    ["is_bs_id_lt_256", "基站ID小于256标记"],
    ["multi_operator_shared", "多运营商共享（multi_operator_shared）"],
    ["Not_Filled", "未补齐（Not_Filled）"],
    ["Severe Fill", "严重碰撞补齐（Severe Fill）"],
    ["bs_id_lt_256", "基站ID小于256（bs_id_lt_256）"],
    ["EN视图", "英文视图（EN）"],
    ["Step40", "Step40（位置补齐）"],
    ["Step41", "Step41（信号补齐）"],
    ["Step43", "Step43（指标汇总）"],
    ["Step52", "Step52（CELL画像）"],
    ["Final", "Final（最终输出）"]
  ];
  const orderedReplacements = [...termReplacements].sort((a, b) => b[0].length - a[0].length);

  const nf = (n) => new Intl.NumberFormat("en-US").format(Number(n || 0));
  const pct = (n, total) => total > 0 ? ((100 * n) / total).toFixed(2) + "%" : "0.00%";
  const toInt = (v, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
  };

  function paginateRows(rows, page, pageSize) {
    const p = toInt(page, 1);
    const ps = toInt(pageSize, 100);
    const all = Array.isArray(rows) ? rows : [];
    const total = all.length;
    const totalPages = total === 0 ? 0 : Math.ceil(total / ps);
    const start = (p - 1) * ps;
    return {
      page: p,
      page_size: ps,
      total,
      total_pages: totalPages,
      items: all.slice(start, start + ps)
    };
  }

  function localizeTerms(text) {
    let out = String(text || "");
    orderedReplacements.forEach(([src, dst]) => {
      out = out.split(src).join(dst);
    });
    return out;
  }

  function buildQuery(params) {
    const q = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        q.set(k, String(v).trim());
      }
    });
    const s = q.toString();
    return s ? ("?" + s) : "";
  }

  function getApiCandidates(pathWithQuery) {
    const path = String(pathWithQuery || "");
    const urls = [];
    if (window.location.protocol.startsWith("http")) {
      urls.push(window.location.origin + path);
    }
    urls.push("http://127.0.0.1:8508" + path);
    return urls;
  }

  async function tryFetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("fetch failed: " + url);
    return await res.json();
  }

  async function fetchFromApi(path, params) {
    const urlPath = path + buildQuery(params);
    for (const url of getApiCandidates(urlPath)) {
      try {
        return await tryFetchJson(url);
      } catch (e) {}
    }
    return null;
  }

  async function requestApi(method, path, params, body) {
    const urlPath = path + buildQuery(params);
    for (const url of getApiCandidates(urlPath)) {
      try {
        const res = await fetch(url, {
          method: String(method || "GET").toUpperCase(),
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          body: body == null ? undefined : JSON.stringify(body)
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          return { ok: false, status: res.status, data };
        }
        return { ok: true, status: res.status, data };
      } catch (e) {}
    }
    return { ok: false, status: 0, data: null };
  }

  async function loadLocalSnapshot() {
    try {
      return await tryFetchJson("./dashboard_data.json");
    } catch (e) {
      return BUILTIN_SNAPSHOT;
    }
  }

  function snapshotRunId(snapshot, runId) {
    if (runId) return runId;
    return (snapshot && snapshot.meta && snapshot.meta.run_id) ? snapshot.meta.run_id : "snapshot";
  }

  function snapshotToLayer(snapshot, layerId, runId, page, pageSize) {
    if (!snapshot) return null;
    const rows = snapshot.row_counts || {};
    const normalizedLayer = String(layerId || "");
    const layers = {
      "L0": { input_rows: null, output_rows: rows.l0_rows, pass_flag: true, payload: {} },
      "L2": { input_rows: rows.l0_rows, output_rows: rows.l2_rows, pass_flag: true, payload: {} },
      "L3": { input_rows: rows.l2_rows, output_rows: rows.l3_bs_rows, pass_flag: true, payload: { object_level: "BS" } },
      "L4": { input_rows: rows.l2_rows, output_rows: rows.l4_final_rows, pass_flag: true, payload: {} },
      "L4_Final": { input_rows: rows.l2_rows, output_rows: rows.l4_final_rows, pass_flag: true, payload: {} },
      "L5_LAC": { input_rows: rows.l4_final_rows, output_rows: rows.l5_lac_rows, pass_flag: true, payload: {} },
      "L5_BS": { input_rows: rows.l4_final_rows, output_rows: rows.l5_bs_rows, pass_flag: true, payload: {} },
      "L5_CELL": { input_rows: rows.l4_final_rows, output_rows: rows.l5_cell_rows, pass_flag: true, payload: {} }
    };
    const snap = layers[normalizedLayer];
    if (!snap) return null;

    const metrics = [];
    if (normalizedLayer === "L4" || normalizedLayer === "L4_Final") {
      Object.entries(snapshot.gps_metrics || {}).forEach(([k, v]) => {
        metrics.push({ metric_code: k, metric_value: v, unit: "rows", payload: {} });
      });
      Object.entries(snapshot.signal_metrics || {}).forEach(([k, v]) => {
        metrics.push({ metric_code: k, metric_value: v, unit: k.endsWith("_cnt") ? "rows" : "fields", payload: {} });
      });
    }
    const metricPage = paginateRows(metrics, page, pageSize);
    const rulePage = paginateRows([], page, pageSize);
    return {
      run_id: snapshotRunId(snapshot, runId),
      layer_id: normalizedLayer,
      snapshot: snap,
      quality_metrics: metricPage.items,
      rule_hits: rulePage.items,
      page: metricPage.page,
      page_size: metricPage.page_size,
      quality_metric_total: metricPage.total,
      quality_metric_total_pages: metricPage.total_pages,
      rule_hit_total: rulePage.total,
      rule_hit_total_pages: rulePage.total_pages
    };
  }

  function snapshotToReconciliation(snapshot, runId, page, pageSize) {
    if (!snapshot) return null;
    const allRows = (snapshot.gate_results || []).map((g, idx) => ({
      check_code: g.gate_code || ("gate_" + (idx + 1)),
      check_name: g.gate_name || "",
      lhs_value: g.actual_value,
      rhs_value: g.expected_value,
      diff_value: g.diff_value,
      pass_flag: Boolean(g.pass),
      details: {}
    }));
    const paged = paginateRows(allRows, page, pageSize);
    return {
      run_id: snapshotRunId(snapshot, runId),
      checks: paged.items,
      page: paged.page,
      page_size: paged.page_size,
      total: paged.total,
      total_pages: paged.total_pages
    };
  }

  function snapshotToExposure(snapshot, runId, objectLevel, page, pageSize) {
    if (!snapshot) return null;
    const bs = (snapshot.anomaly_counts && snapshot.anomaly_counts.bs) || {};
    const cell = (snapshot.anomaly_counts && snapshot.anomaly_counts.cell) || {};
    const rowCounts = snapshot.row_counts || {};
    let rows = [
      { object_level: "BS", field_code: "is_bs_id_lt_256", exposed_flag: true, true_obj_cnt: bs.bs_id_lt_256 || 0, total_obj_cnt: rowCounts.l5_bs_rows || 0, note: "from Layer5_BS_Profile" },
      { object_level: "BS", field_code: "is_multi_operator_shared", exposed_flag: true, true_obj_cnt: bs.multi_operator_shared || 0, total_obj_cnt: rowCounts.l5_bs_rows || 0, note: "from Layer5_BS_Profile" },
      { object_level: "CELL", field_code: "is_bs_id_lt_256", exposed_flag: true, true_obj_cnt: cell.bs_id_lt_256 || 0, total_obj_cnt: rowCounts.l5_cell_rows || 0, note: "from Layer5_Cell_Profile" },
      { object_level: "CELL", field_code: "is_multi_operator_shared", exposed_flag: true, true_obj_cnt: cell.multi_operator_shared || 0, total_obj_cnt: rowCounts.l5_cell_rows || 0, note: "from Layer5_Cell_Profile" }
    ];
    if (objectLevel === "BS" || objectLevel === "CELL") {
      rows = rows.filter((r) => r.object_level === objectLevel);
    }
    const paged = paginateRows(rows, page, pageSize);
    return {
      run_id: snapshotRunId(snapshot, runId),
      rows: paged.items,
      page: paged.page,
      page_size: paged.page_size,
      total: paged.total,
      total_pages: paged.total_pages
    };
  }

  function snapshotToIssues(snapshot, runId, status, severity, page, pageSize) {
    let rows = [];
    if (status) rows = rows.filter((x) => x.status === status);
    if (severity) rows = rows.filter((x) => x.severity === severity);
    const paged = paginateRows(rows, page, pageSize);
    return {
      run_id: snapshotRunId(snapshot || {}, runId),
      items: paged.items,
      page: paged.page,
      page_size: paged.page_size,
      total: paged.total,
      total_pages: paged.total_pages
    };
  }

  function snapshotToPatches(snapshot, runId, issueId, verifiedFlag, page, pageSize) {
    let rows = [];
    if (issueId != null && issueId !== "") {
      const n = Number(issueId);
      rows = rows.filter((x) => Number(x.issue_id) === n);
    }
    if (verifiedFlag === true || verifiedFlag === false) {
      rows = rows.filter((x) => Boolean(x.verified_flag) === verifiedFlag);
    }
    const paged = paginateRows(rows, page, pageSize);
    return {
      run_id: snapshotRunId(snapshot || {}, runId),
      items: paged.items,
      page: paged.page,
      page_size: paged.page_size,
      total: paged.total,
      total_pages: paged.total_pages
    };
  }

  function readQuery() {
    return Object.fromEntries(new URLSearchParams(window.location.search).entries());
  }

  function writeQuery(params) {
    const q = buildQuery(params || {});
    const next = window.location.pathname + q;
    window.history.replaceState(null, "", next);
  }

  function updateNavLinks(params) {
    const q = buildQuery(params || {});
    document.querySelectorAll("a.link-btn").forEach((a) => {
      const base = String(a.getAttribute("href") || "").split("?")[0];
      if (!base) return;
      a.setAttribute("href", base + q);
    });
  }

  window.Phase1UI = {
    nf,
    pct,
    localizeTerms,
    buildQuery,
    fetchFromApi,
    requestApi,
    loadLocalSnapshot,
    snapshotToLayer,
    snapshotToReconciliation,
    snapshotToExposure,
    snapshotToIssues,
    snapshotToPatches,
    readQuery,
    writeQuery,
    updateNavLinks
  };
})();
