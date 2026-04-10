"""Query helpers for Step 5 maintenance pages."""
from __future__ import annotations

from typing import Any

from ..core.database import fetchall, fetchone, paginate


DRIFT_KEYS = ('insufficient', 'stable', 'collision', 'migration', 'large_coverage', 'moderate_drift')


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
            'dataset_key': row.get('dataset_key', 'sample_6lac'),
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
        FROM rebuild5_meta.step5_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )
    drift_rows = _safe_fetchall(
        """
        SELECT drift_pattern, COUNT(*) AS count
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
        GROUP BY drift_pattern
        """
    )
    return build_maintenance_stats_payload(summary, drift_rows)


def get_maintenance_cells_payload(kind: str = 'all', page: int = 1, page_size: int = 50) -> dict[str, Any]:
    where_clauses = []
    if kind == 'collision':
        where_clauses.append('is_collision')
    elif kind == 'migration':
        where_clauses.append("drift_pattern = 'migration'")
    elif kind == 'multi_centroid':
        where_clauses.append('is_multi_centroid')
    elif kind == 'anomaly':
        where_clauses.append('(is_collision OR is_multi_centroid OR is_dynamic OR drift_pattern IN (\'migration\', \'large_coverage\', \'moderate_drift\'))')

    where_sql = ''
    if where_clauses:
        where_sql = ' AND ' + ' AND '.join(where_clauses)

    result = paginate(
        f"""
        SELECT
            t.operator_code, t.operator_cn, t.lac, t.bs_id, t.cell_id, t.tech_norm,
            t.lifecycle_state, t.position_grade, t.anchor_eligible, t.baseline_eligible,
            t.p50_radius_m, t.p90_radius_m, t.center_lon, t.center_lat,
            t.drift_pattern, t.max_spread_m, t.net_drift_m, t.drift_ratio,
            t.gps_anomaly_type, t.is_collision, t.is_dynamic, t.is_multi_centroid,
            t.antitoxin_hit, t.cell_scale, t.window_obs_count, t.last_observed_at, t.independent_obs, t.distinct_dev_id,
            t.rsrp_avg, t.rsrq_avg, t.sinr_avg, t.pressure_avg,
            t.gps_valid_count, t.gps_confidence, t.signal_confidence, t.observed_span_hours, t.active_days,
            t.active_days_30d, t.consecutive_inactive_days,
            geo.province_name, geo.city_name, geo.district_name
        FROM rebuild5.trusted_cell_library t
        LEFT JOIN (
            SELECT cell_id::text AS cell_id, province_name, city_name, district_name
            FROM rebuild4.sample_cell_profile
            WHERE province_name IS NOT NULL
        ) geo ON t.cell_id::text = geo.cell_id
        WHERE t.batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
        {where_sql}
        ORDER BY t.is_collision DESC, t.is_multi_centroid DESC, t.p90_radius_m DESC NULLS LAST, t.cell_id
        """,
        page=page,
        page_size=page_size,
    )
    # Attach centroid details for multi_centroid cells
    multi_ids = [r['cell_id'] for r in result['items'] if r.get('is_multi_centroid')]
    centroids_by_cell: dict[int, list[dict]] = {}
    if multi_ids:
        centroid_rows = _safe_fetchall(
            """
            SELECT cell_id, cluster_id, center_lon, center_lat, obs_count, dev_count, share_ratio
            FROM rebuild5.cell_centroid_detail
            WHERE cell_id = ANY(%s) AND batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.cell_centroid_detail)
            ORDER BY cell_id, cluster_id
            """,
            (multi_ids,),
        )
        for row in centroid_rows:
            centroids_by_cell.setdefault(row['cell_id'], []).append(row)

    for item in result['items']:
        item['centroids'] = centroids_by_cell.get(item['cell_id'], [])

    return {'items': result['items'], 'kind': kind, '_page_info': result}


def get_maintenance_bs_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            anchor_eligible, baseline_eligible, total_cells, qualified_cells, excellent_cells,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade, anomaly_cell_ratio,
            is_multi_centroid, window_active_cell_count,
            (classification = 'large_spread') AS large_spread
        FROM rebuild5.trusted_bs_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_bs_library)
        ORDER BY large_spread DESC, anomaly_cell_ratio DESC, total_cells DESC, bs_id
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}


def get_maintenance_lac_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT
            operator_code, operator_cn, lac, lifecycle_state,
            anchor_eligible, baseline_eligible,
            total_bs, qualified_bs, qualified_bs_ratio,
            area_km2, anomaly_bs_ratio,
            boundary_stability_score, active_bs_count, retired_bs_count,
            trend
        FROM rebuild5.trusted_lac_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_lac_library)
        ORDER BY anomaly_bs_ratio DESC, total_bs DESC, lac
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}


def get_collision_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT batch_id, snapshot_version, cell_id, is_collision_id,
               collision_combo_count, dominant_combo, combo_keys_json
        FROM rebuild5.collision_id_list
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
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
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
            drift_pattern, max_spread_m, net_drift_m, drift_ratio,
            gps_anomaly_type, is_collision, is_dynamic, is_multi_centroid,
            antitoxin_hit, cell_scale, window_obs_count, last_observed_at,
            independent_obs, distinct_dev_id,
            rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
            active_days_30d, consecutive_inactive_days
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
          AND cell_id = %s
        """,
        (cell_id,),
    )
    if not row:
        return None
    centroids = _safe_fetchall(
        """
        SELECT cluster_id, center_lon, center_lat, obs_count, radius_m
        FROM rebuild5.cell_centroid_detail
        WHERE cell_id = %s
        ORDER BY obs_count DESC
        """,
        (cell_id,),
    )
    return {**row, 'centroids': centroids}


def get_maintenance_bs_detail_payload(bs_id: int) -> dict[str, Any] | None:
    row = _safe_fetchone(
        """
        SELECT
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            anchor_eligible, baseline_eligible, total_cells, qualified_cells, excellent_cells,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade, anomaly_cell_ratio,
            is_multi_centroid, window_active_cell_count
        FROM rebuild5.trusted_bs_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_bs_library)
          AND bs_id = %s
        """,
        (bs_id,),
    )
    if not row:
        return None
    child_cells = _safe_fetchall(
        """
        SELECT cell_id, lifecycle_state, position_grade, p90_radius_m, drift_pattern, is_collision
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
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
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
              AND antitoxin_hit = true
        ),
        prev AS (
            SELECT operator_code, lac, cell_id,
                   center_lon, center_lat, p90_radius_m, distinct_dev_id
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = (
                SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library
                WHERE batch_id < (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
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
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
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
