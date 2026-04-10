"""Read-only Step 6 service queries."""
from __future__ import annotations

from typing import Any

from ..core.database import fetchall, fetchone, paginate


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


def _latest_version() -> dict[str, Any]:
    row = _safe_fetchone(
        """
        SELECT run_id, dataset_key, snapshot_version, snapshot_version_prev
        FROM rebuild5_meta.step5_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )
    return row or {'run_id': '', 'dataset_key': 'sample_6lac', 'snapshot_version': 'v0', 'snapshot_version_prev': 'v0'}


def _latest_batch_filter(table_name: str) -> str:
    return f"batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM {table_name})"


def search_service_payload(q: str | None = None, level: str = 'cell', operator_code: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    query = (q or '').strip()
    normalized_level = level if level in {'cell', 'bs', 'lac'} else 'cell'
    params: list[Any] = []
    filters: list[str] = []

    if normalized_level == 'cell':
        filters.append(_latest_batch_filter('rebuild5.trusted_cell_library'))
        if operator_code:
            filters.append('operator_code = %s')
            params.append(operator_code)
        if query:
            like = f'%{query}%'
            filters.append('(CAST(cell_id AS text) ILIKE %s OR CAST(bs_id AS text) ILIKE %s OR CAST(lac AS text) ILIKE %s OR operator_cn ILIKE %s OR operator_code ILIKE %s)')
            params.extend([like, like, like, like, like])
        sql = f"""
            SELECT
                'cell'::text AS level,
                operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                lifecycle_state, position_grade, center_lon, center_lat,
                p90_radius_m, anchor_eligible, baseline_eligible,
                drift_pattern, is_collision, is_dynamic, is_multi_centroid
            FROM rebuild5.trusted_cell_library
            WHERE {' AND '.join(filters)}
            ORDER BY p90_radius_m ASC NULLS LAST, cell_id
            """
    elif normalized_level == 'bs':
        filters.append(_latest_batch_filter('rebuild5.trusted_bs_library'))
        if operator_code:
            filters.append('operator_code = %s')
            params.append(operator_code)
        if query:
            like = f'%{query}%'
            filters.append('(CAST(bs_id AS text) ILIKE %s OR CAST(lac AS text) ILIKE %s OR operator_cn ILIKE %s OR operator_code ILIKE %s)')
            params.extend([like, like, like, like])
        sql = f"""
            SELECT
                'bs'::text AS level,
                operator_code, operator_cn, lac, bs_id, NULL::bigint AS cell_id, NULL::text AS tech_norm,
                lifecycle_state, classification AS position_grade, center_lon, center_lat,
                gps_p90_dist_m AS p90_radius_m, anchor_eligible, baseline_eligible,
                classification AS drift_pattern, FALSE AS is_collision, FALSE AS is_dynamic, FALSE AS is_multi_centroid,
                total_cells, qualified_cells, excellent_cells
            FROM rebuild5.trusted_bs_library
            WHERE {' AND '.join(filters)}
            ORDER BY gps_p90_dist_m ASC NULLS LAST, total_cells DESC, bs_id
            """
    else:
        filters.append(_latest_batch_filter('rebuild5.trusted_lac_library'))
        if operator_code:
            filters.append('operator_code = %s')
            params.append(operator_code)
        if query:
            like = f'%{query}%'
            filters.append('(CAST(lac AS text) ILIKE %s OR operator_cn ILIKE %s OR operator_code ILIKE %s)')
            params.extend([like, like, like])
        sql = f"""
            SELECT
                'lac'::text AS level,
                operator_code, operator_cn, lac, NULL::bigint AS bs_id, NULL::bigint AS cell_id, NULL::text AS tech_norm,
                lifecycle_state, trend AS position_grade, NULL::double precision AS center_lon, NULL::double precision AS center_lat,
                NULL::double precision AS p90_radius_m, anchor_eligible, baseline_eligible,
                trend AS drift_pattern, FALSE AS is_collision, FALSE AS is_dynamic, FALSE AS is_multi_centroid,
                total_bs, qualified_bs, qualified_bs_ratio
            FROM rebuild5.trusted_lac_library
            WHERE {' AND '.join(filters)}
            ORDER BY qualified_bs_ratio DESC NULLS LAST, total_bs DESC, lac
            """

    result = paginate(sql, tuple(params) if params else None, page=page, page_size=page_size)
    return {'version': _latest_version(), 'query': {'q': query, 'level': level, 'operator_code': operator_code}, 'items': result['items'], '_page_info': result}


def get_service_cell_payload(cell_id: int) -> dict[str, Any]:
    row = _safe_fetchone(
        """
        SELECT *
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
          AND cell_id = %s
        ORDER BY p90_radius_m ASC NULLS LAST, operator_code, lac
        LIMIT 1
        """,
        (cell_id,),
    )
    return row or {'cell_id': cell_id}


def get_service_bs_payload(bs_id: int) -> dict[str, Any]:
    row = _safe_fetchone(
        """
        SELECT *
        FROM rebuild5.trusted_bs_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_bs_library)
          AND bs_id = %s
        ORDER BY total_cells DESC, operator_code, lac
        LIMIT 1
        """,
        (bs_id,),
    )
    if not row:
        return {'bs_id': bs_id, 'cells': []}
    row['cells'] = _safe_fetchall(
        """
        SELECT cell_id, lifecycle_state, position_grade, p90_radius_m, drift_pattern, is_collision, is_multi_centroid
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
          AND operator_code = %s AND lac = %s AND bs_id = %s
        ORDER BY p90_radius_m ASC NULLS LAST, cell_id
        LIMIT 200
        """,
        (row['operator_code'], row['lac'], row['bs_id']),
    )
    return row


def get_service_lac_payload(lac: int) -> dict[str, Any]:
    row = _safe_fetchone(
        """
        SELECT *
        FROM rebuild5.trusted_lac_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_lac_library)
          AND lac = %s
        ORDER BY total_bs DESC, operator_code
        LIMIT 1
        """,
        (lac,),
    )
    if not row:
        return {'lac': lac, 'bs_items': []}
    row['bs_items'] = _safe_fetchall(
        """
        SELECT bs_id, lifecycle_state, classification, total_cells, qualified_cells, excellent_cells, anomaly_cell_ratio
        FROM rebuild5.trusted_bs_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_bs_library)
          AND operator_code = %s AND lac = %s
        ORDER BY anomaly_cell_ratio DESC, total_cells DESC, bs_id
        LIMIT 300
        """,
        (row['operator_code'], row['lac']),
    )
    return row


def get_service_coverage_payload() -> dict[str, Any]:
    operator_rows = _safe_fetchall(
        """
        SELECT
            operator_code,
            MAX(operator_cn) AS operator_cn,
            COUNT(*) AS cells,
            COALESCE(AVG(CASE WHEN lifecycle_state IN ('qualified', 'excellent') THEN 1 ELSE 0 END), 0) AS qualified_pct,
            COALESCE(AVG(CASE WHEN lifecycle_state = 'excellent' THEN 1 ELSE 0 END), 0) AS excellent_pct,
            COALESCE(AVG(p90_radius_m), 0) AS avg_p90
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
        GROUP BY operator_code
        ORDER BY cells DESC, operator_code
        """
    )
    summary = _safe_fetchone(
        """
        SELECT
            COUNT(*) AS trusted_cell_total,
            COUNT(DISTINCT lac) AS lac_total,
            COALESCE(AVG(p90_radius_m), 0) AS avg_p90
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)
        """
    ) or {'trusted_cell_total': 0, 'lac_total': 0, 'avg_p90': 0}
    return {'version': _latest_version(), 'summary': summary, 'operators': operator_rows}


def get_service_report_payload() -> dict[str, Any]:
    rows = _safe_fetchall(
        """
        WITH latest_batch AS (
            SELECT COALESCE(MAX(batch_id), 0) AS batch_id
            FROM rebuild5.trusted_lac_library
        ),
        lac_rows AS (
            SELECT operator_code, operator_cn, lac, batch_id
            FROM rebuild5.trusted_lac_library
            WHERE batch_id = (SELECT batch_id FROM latest_batch)
        ),
        cell_agg AS (
            SELECT
                operator_code,
                lac,
                COUNT(*) AS cell_total,
                COUNT(*) FILTER (WHERE lifecycle_state IN ('qualified', 'excellent')) AS qualified_cell_total,
                COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_cell_total,
                COALESCE(AVG(p90_radius_m), 0) AS avg_p90
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = (SELECT batch_id FROM latest_batch)
            GROUP BY operator_code, lac
        ),
        bs_agg AS (
            SELECT
                operator_code,
                lac,
                COUNT(*) AS bs_total,
                COUNT(*) FILTER (WHERE lifecycle_state = 'qualified') AS qualified_bs_total
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = (SELECT batch_id FROM latest_batch)
            GROUP BY operator_code, lac
        )
        SELECT
            l.operator_code,
            l.operator_cn,
            l.lac,
            COALESCE(c.cell_total, 0) AS cell_total,
            COALESCE(c.qualified_cell_total, 0) AS qualified_cell_total,
            COALESCE(c.excellent_cell_total, 0) AS excellent_cell_total,
            COALESCE(b.bs_total, 0) AS bs_total,
            COALESCE(b.qualified_bs_total, 0) AS qualified_bs_total,
            COALESCE(c.avg_p90, 0) AS avg_p90
        FROM lac_rows l
        LEFT JOIN cell_agg c
          ON c.operator_code = l.operator_code AND c.lac = l.lac
        LEFT JOIN bs_agg b
          ON b.operator_code = l.operator_code AND b.lac = l.lac
        ORDER BY cell_total DESC, l.lac
        """
    )
    return {'version': _latest_version(), 'rows': rows}
