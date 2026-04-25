"""Query helpers for Step 5 maintenance pages."""
from __future__ import annotations

from typing import Any

from ..core.database import fetchall, fetchone, paginate


def _attach_admin_area(items: list[dict[str, Any]]) -> None:
    """In-place attach province_name / city_name / district_name to each item
    by nearest centroid lookup against rebuild2.dim_admin_area.

    Uses a single SQL call that expands items via UNNEST + LATERAL, so cost
    is O(N rows × 2874 candidates) instead of the full-table cost that
    LATERAL inside a paginate() SQL would incur (COUNT(*) forces every row).
    """
    if not items:
        return
    idx_arr: list[int] = []
    lon_arr: list[float | None] = []
    lat_arr: list[float | None] = []
    for i, it in enumerate(items):
        lon = it.get('center_lon')
        lat = it.get('center_lat')
        idx_arr.append(i)
        lon_arr.append(float(lon) if lon is not None else None)
        lat_arr.append(float(lat) if lat is not None else None)

    rows = fetchall(
        """
        SELECT p.idx, loc.province_name, loc.city_name, loc.district_name
        FROM unnest(%s::int[], %s::double precision[], %s::double precision[])
             WITH ORDINALITY AS p(idx, lon, lat, ord)
        LEFT JOIN LATERAL (
            SELECT a.province_name, a.city_name, a.name AS district_name
            FROM rebuild2.dim_admin_area a
            WHERE p.lon IS NOT NULL AND p.lat IS NOT NULL
            ORDER BY (a.center_lon - p.lon) * (a.center_lon - p.lon)
                   + (a.center_lat - p.lat) * (a.center_lat - p.lat)
            LIMIT 1
        ) loc ON true
        """,
        (idx_arr, lon_arr, lat_arr),
    )
    admin_by_idx = {int(r['idx']): r for r in rows}
    for i, it in enumerate(items):
        row = admin_by_idx.get(i) or {}
        it['province_name'] = row.get('province_name')
        it['city_name'] = row.get('city_name')
        it['district_name'] = row.get('district_name')


DRIFT_KEYS = (
    'insufficient',
    'stable',
    'large_coverage',
    'dual_cluster',
    'migration',
    'collision',       # 本阶段搁置，暂显 0；重跑后若有 >100km 双点会填充
    'dynamic',
    'uncertain',
    'oversize_single',
)


def _missing_relation(exc: Exception) -> bool:
    text = str(exc)
    return 'does not exist' in text or 'UndefinedTable' in text


def _safe_fetchone(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    try:
        return fetchone(sql, params)
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise


def _safe_fetchall(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    try:
        return fetchall(sql, params)
    except Exception as exc:
        if _missing_relation(exc):
            return []
        raise


def build_maintenance_stats_payload(summary: dict[str, Any] | None, drift_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row = summary or {}
    distribution = {key: 0 for key in DRIFT_KEYS}
    for item in drift_rows:
        key = str(item.get('drift_pattern') or '')
        if key in distribution:
            distribution[key] = int(item.get('count') or 0)
    return {
        'version': {
            'run_id': row.get('run_id', ''),
            'dataset_key': row.get('dataset_key', ''),
            'snapshot_version': row.get('snapshot_version', 'v0'),
            'snapshot_version_prev': row.get('snapshot_version_prev', 'v0'),
        },
        'summary': {
            'published_cell_count': int(row.get('published_cell_count') or 0),
            'published_bs_count': int(row.get('published_bs_count') or 0),
            'published_lac_count': int(row.get('published_lac_count') or 0),
            'collision_cell_count': int(row.get('collision_cell_count') or 0),
            'multi_centroid_cell_count': int(row.get('multi_centroid_cell_count') or 0),
            'dynamic_cell_count': int(row.get('dynamic_cell_count') or 0),
            'anomaly_bs_count': int(row.get('anomaly_bs_count') or 0),
        },
        'drift_distribution': distribution,
    }


def get_maintenance_stats_payload() -> dict[str, Any]:
    summary = _safe_fetchone(
        """
        SELECT *
        FROM rb5_meta.step5_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )
    drift_rows = _safe_fetchall(
        """
        SELECT drift_pattern, COUNT(*) AS count
        FROM rb5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
        GROUP BY drift_pattern
        """
    )
    return build_maintenance_stats_payload(summary, drift_rows)


def get_maintenance_cells_payload(kind: str = 'all', page: int = 1, page_size: int = 50) -> dict[str, Any]:
    where_clauses = []
    if kind == 'collision':
        # 新规则：collision 标签本阶段搁置（需要 >100km 双点，数据不足）
        # UI 若查此 kind，用新 drift_pattern 字段（当前为 0），不再用旧 is_collision
        where_clauses.append("drift_pattern = 'collision'")
    elif kind == 'migration':
        where_clauses.append("drift_pattern = 'migration'")
    elif kind == 'dual_cluster':
        where_clauses.append("drift_pattern = 'dual_cluster'")
    elif kind == 'dynamic':
        where_clauses.append("drift_pattern = 'dynamic'")
    elif kind == 'uncertain':
        where_clauses.append("drift_pattern = 'uncertain'")
    elif kind == 'multi_centroid':
        # 与 UI "多质心" tab 对齐：uncertain（k_eff>=3 且未识别为动态）
        where_clauses.append("drift_pattern = 'uncertain'")
    elif kind == 'large_coverage':
        where_clauses.append("drift_pattern = 'large_coverage'")
    elif kind == 'oversize_single':
        where_clauses.append("drift_pattern = 'oversize_single'")
    elif kind == 'stable':
        where_clauses.append("drift_pattern = 'stable'")
    elif kind == 'insufficient':
        where_clauses.append("drift_pattern = 'insufficient'")
    elif kind == 'anomaly':
        # "全部异常" = 非 stable 且非 insufficient 的所有 cell
        where_clauses.append(
            "drift_pattern IN ('large_coverage', 'dual_cluster', 'migration', 'dynamic', "
            "'uncertain', 'oversize_single', 'collision')"
        )
    elif kind == 'dormant':
        where_clauses.append("lifecycle_state = 'dormant'")
    elif kind == 'retired':
        where_clauses.append("lifecycle_state = 'retired'")
    elif kind == 'has_ta':
        # 有效 TA 观测 > 0（TA 估距有数据，但样本少的可能不可信）
        where_clauses.append("ta_n_obs > 0")
    elif kind == 'ta_reliable':
        # TA 样本 >= 10，估距可用于研究结论
        where_clauses.append("ta_n_obs >= 10")

    where_sql = ''
    if where_clauses:
        where_sql = ' AND ' + ' AND '.join(where_clauses)

    result = paginate(
        f"""
        SELECT
            t.operator_code, t.operator_cn, t.lac, t.bs_id, t.cell_id, t.tech_norm,
            t.lifecycle_state, t.position_grade, t.anchor_eligible, t.baseline_eligible,
            t.p50_radius_m, t.p90_radius_m, t.center_lon, t.center_lat,
            t.drift_pattern, t.centroid_pattern, t.max_spread_m, t.net_drift_m, t.drift_ratio,
            t.gps_anomaly_type, t.is_collision, t.is_dynamic, t.is_multi_centroid,
            t.antitoxin_hit, t.cell_scale, t.window_obs_count, t.last_observed_at, t.independent_obs, t.distinct_dev_id,
            t.rsrp_avg, t.rsrq_avg, t.sinr_avg, t.pressure_avg,
            t.ta_n_obs, t.ta_p50, t.ta_p90, t.ta_dist_p90_m, t.freq_band, t.ta_verification,
            t.gps_valid_count, t.gps_confidence, t.signal_confidence, t.observed_span_hours, t.active_days,
            t.active_days_30d, t.consecutive_inactive_days
        FROM rb5.trusted_cell_library t
        WHERE t.batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
        {where_sql}
        ORDER BY t.is_collision DESC, t.is_multi_centroid DESC, t.p90_radius_m DESC NULLS LAST, t.cell_id
        """,
        page=page,
        page_size=page_size,
    )
    # Attach centroid details for multi-centroid and pattern-based multi-cluster cells.
    # 旧字段 is_multi_centroid 与新 drift_pattern 不同步（is_multi_centroid=false 但
    # drift_pattern='dual_cluster' 的情况下 cell_centroid_detail 里确有多簇），所以两个条件都取。
    _multi_drifts = {'dual_cluster', 'collision', 'migration', 'uncertain'}
    multi_ids = [
        r['cell_id'] for r in result['items']
        if r.get('is_multi_centroid') or r.get('drift_pattern') in _multi_drifts
    ]
    centroids_by_cell: dict[int, list[dict]] = {}
    if multi_ids:
        centroid_rows = _safe_fetchall(
            """
            SELECT cell_id, tech_norm, cluster_id, center_lon, center_lat, obs_count, dev_count, share_ratio
            FROM rb5.cell_centroid_detail
            WHERE cell_id = ANY(%s) AND batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.cell_centroid_detail)
            ORDER BY cell_id, cluster_id
            """,
            (multi_ids,),
        )
        for row in centroid_rows:
            key = f"{row['cell_id']}|{row.get('tech_norm') or ''}"
            centroids_by_cell.setdefault(key, []).append(row)

    for item in result['items']:
        key = f"{item['cell_id']}|{item.get('tech_norm') or ''}"
        item['centroids'] = centroids_by_cell.get(key, [])

    _attach_admin_area(result['items'])
    return {'items': result['items'], 'kind': kind, '_page_info': result}


def get_maintenance_bs_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT
            t.operator_code, t.operator_cn, t.lac, t.bs_id, t.lifecycle_state,
            t.anchor_eligible, t.baseline_eligible, t.total_cells, t.qualified_cells, t.excellent_cells,
            t.normal_cells, t.anomaly_cells, t.insufficient_cells,
            t.center_lon, t.center_lat, t.gps_p50_dist_m, t.gps_p90_dist_m,
            t.classification, t.position_grade, t.anomaly_cell_ratio,
            t.is_multi_centroid, t.window_active_cell_count,
            (t.classification != 'normal' AND t.classification != 'insufficient') AS is_anomaly_bs
        FROM rb5.trusted_bs_library t
        WHERE t.batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_bs_library)
        ORDER BY is_anomaly_bs DESC, t.anomaly_cells DESC NULLS LAST, t.total_cells DESC, t.bs_id
        """,
        page=page,
        page_size=page_size,
    )
    _attach_admin_area(result['items'])
    return {'items': result['items'], '_page_info': result}


def get_maintenance_lac_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT
            t.operator_code, t.operator_cn, t.lac, t.lifecycle_state,
            t.anchor_eligible, t.baseline_eligible,
            t.total_bs, t.normal_bs, t.anomaly_bs, t.insufficient_bs,
            t.qualified_bs, t.qualified_bs_ratio,
            t.center_lon, t.center_lat,
            t.area_km2, t.anomaly_bs_ratio,
            t.boundary_stability_score, t.active_bs_count, t.retired_bs_count,
            t.trend
        FROM rb5.trusted_lac_library t
        WHERE t.batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_lac_library)
        ORDER BY t.anomaly_bs_ratio DESC, t.total_bs DESC, t.lac
        """,
        page=page,
        page_size=page_size,
    )
    _attach_admin_area(result['items'])
    return {'items': result['items'], '_page_info': result}


def get_collision_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT batch_id, snapshot_version, cell_id, is_collision_id,
               collision_combo_count, dominant_combo, combo_keys_json
        FROM rb5.collision_id_list
        ORDER BY collision_combo_count DESC, cell_id
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}


def get_drift_payload() -> dict[str, Any]:
    rows = _safe_fetchall(
        """
        SELECT drift_pattern, COUNT(*) AS count
        FROM rb5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
        GROUP BY drift_pattern
        ORDER BY count DESC, drift_pattern
        """
    )
    distribution = {key: 0 for key in DRIFT_KEYS}
    for row in rows:
        key = str(row.get('drift_pattern') or '')
        if key in distribution:
            distribution[key] = int(row.get('count') or 0)
    return {'distribution': distribution}


def get_maintenance_cell_detail_payload(cell_id: int) -> dict[str, Any] | None:
    row = _safe_fetchone(
        """
        SELECT
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, position_grade, anchor_eligible, baseline_eligible,
            p50_radius_m, p90_radius_m, center_lon, center_lat,
            drift_pattern, centroid_pattern, max_spread_m, net_drift_m, drift_ratio,
            gps_anomaly_type, is_collision, is_dynamic, is_multi_centroid,
            antitoxin_hit, cell_scale, window_obs_count, last_observed_at,
            independent_obs, distinct_dev_id,
            rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
            active_days_30d, consecutive_inactive_days
        FROM rb5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
          AND cell_id = %s
        """,
        (cell_id,),
    )
    if not row:
        return None
    centroids = _safe_fetchall(
        """
        SELECT cluster_id, center_lon, center_lat, obs_count, radius_m
        FROM rb5.cell_centroid_detail
        WHERE cell_id = %s
          AND tech_norm IS NOT DISTINCT FROM %s
        ORDER BY obs_count DESC
        """,
        (cell_id, row.get('tech_norm')),
    )
    return {**row, 'centroids': centroids}


def get_maintenance_bs_detail_payload(bs_id: int) -> dict[str, Any] | None:
    row = _safe_fetchone(
        """
        SELECT
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            anchor_eligible, baseline_eligible, total_cells, qualified_cells, excellent_cells,
            normal_cells, anomaly_cells, insufficient_cells,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade, anomaly_cell_ratio,
            is_multi_centroid, window_active_cell_count
        FROM rb5.trusted_bs_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_bs_library)
          AND bs_id = %s
        """,
        (bs_id,),
    )
    if not row:
        return None
    child_cells = _safe_fetchall(
        """
        SELECT cell_id, lifecycle_state, position_grade, p90_radius_m, drift_pattern, is_collision
        FROM rb5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
          AND bs_id = %s
        ORDER BY independent_obs DESC
        """,
        (bs_id,),
    )
    return {**row, 'cells': child_cells}


def get_antitoxin_hits_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Cells with antitoxin_hit=true, with trigger dimension details."""
    result = paginate(
        """
        WITH curr AS (
            SELECT operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                   lifecycle_state, antitoxin_hit,
                   center_lon, center_lat, p90_radius_m, distinct_dev_id,
                   max_spread_m, drift_pattern, active_days_30d
            FROM rb5.trusted_cell_library
            WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
              AND antitoxin_hit = true
        ),
        prev AS (
            SELECT operator_code, lac, cell_id, tech_norm,
                   center_lon, center_lat, p90_radius_m, distinct_dev_id
            FROM rb5.trusted_cell_library
            WHERE batch_id = (
                SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library
                WHERE batch_id < (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
            )
        )
        SELECT
            c.operator_code, c.operator_cn, c.lac, c.bs_id, c.cell_id, c.tech_norm,
            c.lifecycle_state, c.drift_pattern, c.max_spread_m,
            -- centroid shift
            CASE WHEN p.center_lon IS NOT NULL AND c.center_lon IS NOT NULL
                 THEN SQRT(POWER((c.center_lon - p.center_lon) * 85300, 2)
                         + POWER((c.center_lat - p.center_lat) * 111000, 2))
                 ELSE NULL END AS centroid_shift_m,
            -- p90 ratio
            CASE WHEN p.p90_radius_m IS NOT NULL AND p.p90_radius_m > 0
                 THEN c.p90_radius_m / p.p90_radius_m
                 ELSE NULL END AS p90_ratio,
            p.p90_radius_m AS prev_p90_radius_m,
            c.p90_radius_m AS curr_p90_radius_m,
            -- dev ratio
            CASE WHEN p.distinct_dev_id IS NOT NULL AND p.distinct_dev_id > 0
                 THEN c.distinct_dev_id::double precision / p.distinct_dev_id
                 ELSE NULL END AS dev_ratio,
            p.distinct_dev_id AS prev_distinct_dev_id,
            c.distinct_dev_id AS curr_distinct_dev_id
        FROM curr c
        LEFT JOIN prev p
          ON p.operator_code = c.operator_code AND p.lac = c.lac AND p.cell_id = c.cell_id
         AND p.tech_norm IS NOT DISTINCT FROM c.tech_norm
        ORDER BY
            COALESCE(CASE WHEN p.center_lon IS NOT NULL AND c.center_lon IS NOT NULL
                THEN SQRT(POWER((c.center_lon - p.center_lon) * 85300, 2)
                        + POWER((c.center_lat - p.center_lat) * 111000, 2))
                ELSE 0 END, 0) DESC,
            c.cell_id
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}


def get_exit_warnings_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """Cells approaching dormant based on density-aware inactive days."""
    result = paginate(
        """
        SELECT
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, active_days_30d, consecutive_inactive_days,
            window_obs_count, last_observed_at,
            CASE WHEN active_days_30d >= 20 THEN 'high'
                 WHEN active_days_30d >= 10 THEN 'mid'
                 ELSE 'low' END AS density_level,
            CASE WHEN active_days_30d >= 20 THEN 3
                 WHEN active_days_30d >= 10 THEN 7
                 ELSE 14 END AS dormant_threshold_days,
            CASE WHEN active_days_30d >= 20
                     THEN ROUND(consecutive_inactive_days / 3.0, 2)
                 WHEN active_days_30d >= 10
                     THEN ROUND(consecutive_inactive_days / 7.0, 2)
                 ELSE ROUND(consecutive_inactive_days / 14.0, 2)
            END AS urgency_ratio
        FROM rb5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)
          AND lifecycle_state NOT IN ('dormant', 'retired')
          AND consecutive_inactive_days > 0
        ORDER BY
            CASE WHEN active_days_30d >= 20 THEN consecutive_inactive_days / 3.0
                 WHEN active_days_30d >= 10 THEN consecutive_inactive_days / 7.0
                 ELSE consecutive_inactive_days / 14.0 END DESC,
            cell_id
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}
