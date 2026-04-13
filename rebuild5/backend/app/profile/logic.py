"""Pure business logic for rebuild5 Step 2/3 evaluation."""
from __future__ import annotations

from math import sqrt
from pathlib import Path
from typing import Any

import yaml

from ..core.settings import settings


STATE_RANK = {
    'waiting': 0,
    'observing': 1,
    'qualified': 2,
    'excellent': 3,
    'dormant': 4,
    'retired': 5,
}


def load_profile_params(path: Path | None = None) -> dict[str, Any]:
    target = path or settings.profile_params_path
    if not target.exists():
        return {}
    with target.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def load_antitoxin_params(path: Path | None = None) -> dict[str, Any]:
    target = path or settings.antitoxin_params_path
    if not target.exists():
        return {}
    with target.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def load_retention_params(path: Path | None = None) -> dict[str, Any]:
    target = path or settings.retention_params_path
    if not target.exists():
        return {}
    with target.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def flatten_profile_thresholds(params: dict[str, Any] | None = None) -> dict[str, float]:
    payload = params or load_profile_params()
    cell = payload.get('cell', {})
    waiting = cell.get('waiting', {})
    qualified = cell.get('qualified', {})
    excellent = cell.get('excellent', {})
    anchorable = cell.get('anchorable', {})
    bs = payload.get('bs', {})
    lac = payload.get('lac', {})
    return {
        'waiting_min_obs': float(waiting.get('min_independent_obs', 1)),
        'qualified_min_obs': float(qualified.get('min_independent_obs', 10)),
        'excellent_min_obs': float(excellent.get('min_independent_obs', 30)),
        'anchorable_min_gps_valid_count': float(anchorable.get('min_gps_valid_count', 10)),
        'anchorable_min_distinct_devices': float(anchorable.get('min_distinct_devices', 2)),
        'anchorable_max_p90': float(anchorable.get('max_p90_radius_m') or 0),
        'anchorable_min_span_hours': float(anchorable.get('min_observed_span_hours', 24)),
        'bs_observing_min_cells_with_gps': float(bs.get('observing', {}).get('min_cells_with_gps', 1)),
        'bs_excellent_min_excellent_cells': float(bs.get('excellent', {}).get('min_excellent_cells', 1)),
        'bs_qualified_min_qualified_cells': float(bs.get('qualified', {}).get('min_qualified_cells', 2)),
        'lac_observing_min_non_waiting_bs': float(lac.get('observing', {}).get('min_non_waiting_bs', 1)),
        'lac_excellent_min_excellent_bs': float(lac.get('excellent', {}).get('min_excellent_bs', 30)),
        'lac_qualified_min_excellent_bs': float(lac.get('qualified', {}).get('min_excellent_bs', 10)),
        # gps_confidence (count-based per 00_全局约定)
        'gps_confidence_high_min_gps': float(payload.get('gps_confidence', {}).get('high', {}).get('min_gps_valid', 20)),
        'gps_confidence_high_min_devs': float(payload.get('gps_confidence', {}).get('high', {}).get('min_devs', 3)),
        'gps_confidence_medium_min_gps': float(payload.get('gps_confidence', {}).get('medium', {}).get('min_gps_valid', 10)),
        'gps_confidence_medium_min_devs': float(payload.get('gps_confidence', {}).get('medium', {}).get('min_devs', 2)),
        'gps_confidence_low_min_gps': float(payload.get('gps_confidence', {}).get('low', {}).get('min_gps_valid', 1)),
        # signal_confidence (count-based per 00_全局约定)
        'signal_confidence_high_min_signal': float(payload.get('signal_confidence', {}).get('high', {}).get('min_signal_original', 20)),
        'signal_confidence_medium_min_signal': float(payload.get('signal_confidence', {}).get('medium', {}).get('min_signal_original', 5)),
        'signal_confidence_low_min_signal': float(payload.get('signal_confidence', {}).get('low', {}).get('min_signal_original', 1)),
    }


def flatten_antitoxin_thresholds(params: dict[str, Any] | None = None) -> dict[str, float]:
    payload = params or load_antitoxin_params()
    collision = payload.get('collision', {})
    migration = payload.get('migration', {})
    bs = payload.get('bs', {})
    drift = payload.get('drift', {})
    multi = payload.get('multi_centroid', {})
    return {
        'collision_min_spread_m': float(collision.get('min_spread_m') or 0),
        'absolute_collision_min_distance_m': float(collision.get('absolute_collision_min_distance_m') or 20000),
        'migration_min_spread_m': float(migration.get('min_spread_m') or 0),
        'bs_max_cell_to_bs_distance_m': float(bs.get('max_cell_to_bs_distance_m') or 0),
        'stable_max_spread_m': float(drift.get('stable_max_spread_m') or 500),
        'insufficient_min_days': float(drift.get('insufficient_min_days') or 2),
        'multi_centroid_trigger_min_p90_m': float(multi.get('trigger_min_p90_m') or 800),
        'is_dynamic_min_spread_m': float(payload.get('is_dynamic', {}).get('min_spread_m', 1500)),
        # cell_scale thresholds (per 00_全局约定)
        'cell_scale_major_min_obs': float(payload.get('cell_scale', {}).get('major', {}).get('min_obs', 50)),
        'cell_scale_major_min_devs': float(payload.get('cell_scale', {}).get('major', {}).get('min_devs', 10)),
        'cell_scale_large_min_obs': float(payload.get('cell_scale', {}).get('large', {}).get('min_obs', 20)),
        'cell_scale_large_min_devs': float(payload.get('cell_scale', {}).get('large', {}).get('min_devs', 5)),
        'cell_scale_medium_min_obs': float(payload.get('cell_scale', {}).get('medium', {}).get('min_obs', 10)),
        'cell_scale_medium_min_devs': float(payload.get('cell_scale', {}).get('medium', {}).get('min_devs', 3)),
        'cell_scale_small_min_obs': float(payload.get('cell_scale', {}).get('small', {}).get('min_obs', 3)),
        # drift classification ratios
        'drift_collision_max_ratio': float(payload.get('drift_classification', {}).get('collision_max_ratio', 0.3)),
        'drift_migration_min_ratio': float(payload.get('drift_classification', {}).get('migration_min_ratio', 0.7)),
        'drift_large_coverage_max_spread_m': float(payload.get('drift_classification', {}).get('large_coverage_max_spread_m', 2200)),
        # antitoxin comparison
        'antitoxin_max_centroid_shift_m': float(payload.get('antitoxin_compare', {}).get('max_centroid_shift_m', 500)),
        'antitoxin_max_p90_ratio': float(payload.get('antitoxin_compare', {}).get('max_p90_ratio', 2.0)),
        'antitoxin_max_dev_ratio': float(payload.get('antitoxin_compare', {}).get('max_dev_ratio', 3.0)),
        # exit management
        'exit_dormant_days_high': float(payload.get('exit', {}).get('dormant_inactive_days_high_density', 3)),
        'exit_dormant_days_mid': float(payload.get('exit', {}).get('dormant_inactive_days_mid_density', 7)),
        'exit_dormant_days_low': float(payload.get('exit', {}).get('dormant_inactive_days_low_density', 14)),
        'exit_high_density_min_30d': float(payload.get('exit', {}).get('high_density_min_active_days_30d', 20)),
        'exit_mid_density_min_30d': float(payload.get('exit', {}).get('mid_density_min_active_days_30d', 10)),
        'exit_retired_after_dormant_days': float(payload.get('exit', {}).get('retired_after_dormant_days', 30)),
    }


def classify_cell_state(
    *,
    independent_obs: float,
    distinct_dev_id: float,
    p90_radius_m: float | None,
    observed_span_hours: float | None,
    is_collision_id: bool,
    params: dict[str, float],
) -> str:
    del distinct_dev_id, p90_radius_m, observed_span_hours, is_collision_id
    if independent_obs < params['waiting_min_obs']:
        return 'waiting'
    if independent_obs >= params['excellent_min_obs']:
        return 'excellent'
    if independent_obs >= params['qualified_min_obs']:
        return 'qualified'
    return 'observing'


def position_grade_for_state(lifecycle_state: str) -> str:
    if lifecycle_state == 'excellent':
        return 'excellent'
    if lifecycle_state == 'qualified':
        return 'good'
    if lifecycle_state == 'observing':
        return 'qualified'
    return 'unqualified'


def classify_diff_kind(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> str:
    if previous is None and current is not None:
        return 'new'
    if previous is not None and current is None:
        return 'removed'
    if previous is None or current is None:
        return 'unchanged'

    prev_state = str(previous.get('lifecycle_state') or 'waiting')
    curr_state = str(current.get('lifecycle_state') or 'waiting')
    if STATE_RANK.get(curr_state, 0) > STATE_RANK.get(prev_state, 0):
        return 'promoted'
    if STATE_RANK.get(curr_state, 0) < STATE_RANK.get(prev_state, 0):
        return 'demoted'

    prev_anchor = bool(previous.get('anchor_eligible'))
    curr_anchor = bool(current.get('anchor_eligible'))
    prev_baseline = bool(previous.get('baseline_eligible'))
    curr_baseline = bool(current.get('baseline_eligible'))
    if prev_anchor != curr_anchor or prev_baseline != curr_baseline:
        return 'eligibility_changed'

    shift = centroid_shift_m(
        previous.get('center_lon'),
        previous.get('center_lat'),
        current.get('center_lon'),
        current.get('center_lat'),
    )
    if shift >= 50:
        return 'geometry_changed'
    return 'unchanged'


def centroid_shift_m(prev_lon: Any, prev_lat: Any, curr_lon: Any, curr_lat: Any) -> float:
    if None in {prev_lon, prev_lat, curr_lon, curr_lat}:
        return 0.0
    dx_m = (float(curr_lon) - float(prev_lon)) * 85300
    dy_m = (float(curr_lat) - float(prev_lat)) * 111000
    return sqrt(dx_m * dx_m + dy_m * dy_m)
