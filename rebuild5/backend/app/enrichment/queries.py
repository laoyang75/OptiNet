"""Query helpers for Step 4 enrichment pages."""
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


def get_enrichment_stats_payload() -> dict[str, Any]:
    row = _safe_fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step4_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )
    if not row:
        return {
            'version': {'run_id': '', 'dataset_key': 'sample_6lac', 'snapshot_version': 'v0', 'snapshot_version_prev': 'v0'},
            'summary': {
                'total_path_a': 0, 'donor_matched_count': 0,
                'gps_filled': 0, 'rsrp_filled': 0, 'rsrq_filled': 0, 'sinr_filled': 0,
                'operator_filled': 0, 'lac_filled': 0, 'tech_filled': 0,
                'gps_anomaly_count': 0, 'collision_skip_anomaly_count': 0,
                'donor_excellent_count': 0, 'donor_qualified_count': 0,
                'remaining_none_gps': 0, 'remaining_none_signal': 0,
            },
            'coverage': {'gps_fill_rate': 0, 'signal_fill_rate': 0, 'operator_fill_rate': 0},
        }
    return {
        'version': {
            'run_id': row['run_id'],
            'dataset_key': row['dataset_key'],
            'snapshot_version': row['snapshot_version'],
            'snapshot_version_prev': row['snapshot_version_prev'],
        },
        'summary': {
            'total_path_a': int(row['total_path_a']),
            'donor_matched_count': int(row['donor_matched_count']),
            'gps_filled': int(row['gps_filled']),
            'rsrp_filled': int(row['rsrp_filled']),
            'rsrq_filled': int(row['rsrq_filled']),
            'sinr_filled': int(row['sinr_filled']),
            'operator_filled': int(row['operator_filled']),
            'lac_filled': int(row['lac_filled']),
            'tech_filled': int(row['tech_filled']),
            'gps_anomaly_count': int(row['gps_anomaly_count']),
            'collision_skip_anomaly_count': int(row['collision_skip_anomaly_count']),
            'donor_excellent_count': int(row['donor_excellent_count']),
            'donor_qualified_count': int(row['donor_qualified_count']),
            'remaining_none_gps': int(row['remaining_none_gps']),
            'remaining_none_signal': int(row['remaining_none_signal']),
        },
        'coverage': {
            'gps_fill_rate': float(row['gps_fill_rate']),
            'signal_fill_rate': float(row['signal_fill_rate']),
            'operator_fill_rate': float(row['operator_fill_rate']),
        },
    }


def get_enrichment_coverage_payload() -> dict[str, Any]:
    rows = _safe_fetchall(
        """
        SELECT
            field_name,
            filled_count,
            fill_rate,
            donor_source
        FROM rebuild5.step4_fill_coverage
        WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.step4_fill_coverage)
        ORDER BY field_name
        """
    )
    return {'items': rows}


def get_enrichment_anomalies_payload(page: int = 1, page_size: int = 50) -> dict[str, Any]:
    result = paginate(
        """
        SELECT
            batch_id, record_id, operator_code, lac, bs_id, cell_id, dev_id,
            event_time_std,
            lon_raw, lat_raw, donor_center_lon, donor_center_lat,
            distance_to_donor_m, anomaly_type, anomaly_threshold_m,
            anomaly_source, is_collision_id, donor_snapshot_version
        FROM rebuild5.gps_anomaly_log
        ORDER BY distance_to_donor_m DESC NULLS LAST, event_time_std DESC
        """,
        page=page,
        page_size=page_size,
    )
    return {'items': result['items'], '_page_info': result}
