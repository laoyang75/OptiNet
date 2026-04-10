"""Query helpers for rebuild5 Step 2 routing page."""
from __future__ import annotations

from typing import Any

from ..core.database import fetchall, fetchone
from ..services.system import load_rule_configs
from .logic import flatten_antitoxin_thresholds, flatten_profile_thresholds, load_antitoxin_params, load_profile_params


def _missing_relation(exc: Exception) -> bool:
    text = str(exc)
    return 'does not exist' in text or 'UndefinedTable' in text


def _empty_distribution() -> dict[str, int]:
    return {
        'waiting': 0,
        'observing': 0,
        'qualified': 0,
        'excellent': 0,
        'dormant': 0,
        'retired': 0,
    }


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


def _latest_step2_row() -> dict[str, Any] | None:
    return _safe_fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step2_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )


def _latest_step3_row() -> dict[str, Any] | None:
    return _safe_fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step3_run_stats
        ORDER BY batch_id DESC, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )


def _rule_payload() -> dict[str, Any]:
    rules = load_rule_configs()
    profile_thresholds = flatten_profile_thresholds(load_profile_params())
    antitoxin_thresholds = flatten_antitoxin_thresholds(load_antitoxin_params())
    return {
        'collision_match_gps_threshold_m': antitoxin_thresholds['collision_min_spread_m'],
        'obs_dedup_window_minutes': 1,
        'centroid_algorithm': 'median',
        'cell': profile_thresholds,
        'profile': rules.get('profile', {}),
        'retention': rules.get('retention', {}),
    }


def get_routing_payload() -> dict[str, Any]:
    step2 = _latest_step2_row()
    step3 = _latest_step3_row()
    if not step2:
        return {
            'summary': {
                'input_record_count': 0,
                'path_a_record_count': 0,
                'path_b_record_count': 0,
                'path_b_cell_count': 0,
                'path_c_drop_count': 0,
                'collision_candidate_count': 0,
                'collision_path_a_match_count': 0,
                'collision_pending_count': 0,
                'collision_drop_count': 0,
            },
            'path_b_metrics': {
                'avg_independent_obs': 0,
                'avg_independent_devs': 0,
                'avg_observed_span_hours': 0,
                'avg_p50_radius_m': 0,
                'avg_p90_radius_m': 0,
                'avg_gps_original_ratio': 0,
                'avg_signal_original_ratio': 0,
                'path_b_complete_cell_count': 0,
                'path_b_partial_cell_count': 0,
            },
            'rules': _rule_payload(),
            'version': {
                'dataset_key': 'sample_6lac',
                'run_id': '',
                'snapshot_version_prev': 'v0',
                'snapshot_version': 'v0',
            },
        }

    return {
        'summary': {
            'input_record_count': int(step2['input_record_count']),
            'path_a_record_count': int(step2['path_a_record_count']),
            'path_b_record_count': int(step2['path_b_record_count']),
            'path_b_cell_count': int(step2['path_b_cell_count']),
            'path_c_drop_count': int(step2['path_c_drop_count']),
            'collision_candidate_count': int(step2['collision_candidate_count']),
            'collision_path_a_match_count': int(step2['collision_path_a_match_count']),
            'collision_pending_count': int(step2['collision_pending_count']),
            'collision_drop_count': int(step2['collision_drop_count']),
        },
        'path_b_metrics': {
            'avg_independent_obs': float(step2['avg_independent_obs']),
            'avg_independent_devs': float(step2['avg_independent_devs']),
            'avg_observed_span_hours': float(step2['avg_observed_span_hours']),
            'avg_p50_radius_m': float(step2['avg_p50_radius_m']),
            'avg_p90_radius_m': float(step2['avg_p90_radius_m']),
            'avg_gps_original_ratio': float(step2['path_b_avg_gps_original_ratio']),
            'avg_signal_original_ratio': float(step2['path_b_avg_signal_original_ratio']),
            'path_b_complete_cell_count': int(step2['path_b_complete_cell_count']),
            'path_b_partial_cell_count': int(step2['path_b_partial_cell_count']),
        },
        'rules': _rule_payload(),
        'version': {
            'dataset_key': step2['dataset_key'],
            'run_id': step2['run_id'],
            'snapshot_version_prev': step2['trusted_snapshot_version'],
            'snapshot_version': step3['snapshot_version'] if step3 else step2['trusted_snapshot_version'],
        },
    }
