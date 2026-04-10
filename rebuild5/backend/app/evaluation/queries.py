"""Query helpers for rebuild5 Step 3 evaluation pages."""
from __future__ import annotations

from typing import Any

from ..core.database import paginate
from ..profile.logic import flatten_profile_thresholds, load_profile_params
from ..profile.queries import _empty_distribution, _latest_step3_row, _safe_fetchall, _safe_fetchone


def get_batches_payload() -> dict[str, Any]:
    rows = _safe_fetchall(
        """
        SELECT batch_id, snapshot_version, dataset_key, run_id, finished_at
        FROM rebuild5_meta.step3_run_stats
        ORDER BY batch_id DESC
        """
    )
    return {
        'batches': [
            {
                'batch_id': int(r['batch_id']),
                'snapshot_version': r['snapshot_version'],
                'dataset_key': r['dataset_key'],
                'run_id': r['run_id'],
                'run_at': str(r['finished_at']) if r.get('finished_at') else None,
            }
            for r in rows
        ],
    }


def _step3_row_for_batch(batch_id: int | None = None) -> dict[str, Any] | None:
    if batch_id is not None:
        return _safe_fetchone(
            'SELECT * FROM rebuild5_meta.step3_run_stats WHERE batch_id = %s',
            (batch_id,),
        )
    return _latest_step3_row()


def get_evaluation_overview_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return {
            'dataset_key': 'sample_6lac',
            'run_id': '',
            'snapshot_version': 'v0',
            'snapshot_version_prev': 'v0',
            'cell_distribution': _empty_distribution(),
            'bs_distribution': _empty_distribution(),
            'lac_distribution': _empty_distribution(),
            'diff_summary': {
                'new': 0,
                'promoted': 0,
                'demoted': 0,
                'eligibility_changed': 0,
                'geometry_changed': 0,
                'unchanged': 0,
            },
            'counts': {
                'cell_total': 0,
                'bs_total': 0,
                'lac_total': 0,
                'anchor_eligible_cells': 0,
            },
        }

    unchanged_row = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.snapshot_diff_cell WHERE batch_id = %s AND diff_kind = %s',
        (step3['batch_id'], 'unchanged'),
    )
    return {
        'dataset_key': step3['dataset_key'],
        'run_id': step3['run_id'],
        'snapshot_version': step3['snapshot_version'],
        'snapshot_version_prev': step3['trusted_snapshot_version_prev'],
        'cell_distribution': {
            'waiting': int(step3['waiting_cell_count']),
            'observing': int(step3['observing_cell_count']),
            'qualified': int(step3['qualified_cell_count']),
            'excellent': int(step3['excellent_cell_count']),
            'dormant': 0,
            'retired': 0,
        },
        'bs_distribution': {
            'waiting': int(step3['bs_waiting_count']),
            'observing': int(step3['bs_observing_count']),
            'qualified': int(step3['bs_qualified_count']),
            'excellent': 0,
            'dormant': 0,
            'retired': 0,
        },
        'lac_distribution': {
            'waiting': int(step3['lac_waiting_count']),
            'observing': int(step3['lac_observing_count']),
            'qualified': int(step3['lac_qualified_count']),
            'excellent': 0,
            'dormant': 0,
            'retired': 0,
        },
        'diff_summary': {
            'new': int(step3['snapshot_new_count']),
            'promoted': int(step3['snapshot_promoted_count']),
            'demoted': int(step3['snapshot_demoted_count']),
            'eligibility_changed': int(step3['snapshot_eligibility_changed_count']),
            'geometry_changed': int(step3['snapshot_geometry_changed_count']),
            'unchanged': int(unchanged_row['cnt']) if unchanged_row else 0,
        },
        'counts': {
            'cell_total': int(step3['evaluated_cell_count']),
            'bs_total': int(step3['bs_waiting_count']) + int(step3['bs_observing_count']) + int(step3['bs_qualified_count']),
            'lac_total': int(step3['lac_waiting_count']) + int(step3['lac_observing_count']) + int(step3['lac_qualified_count']),
            'anchor_eligible_cells': int(step3['anchor_eligible_cell_count']),
        },
    }


def _diff_reason(row: dict[str, Any]) -> str:
    diff_kind = row.get('diff_kind')
    prev_state = row.get('prev_lifecycle_state')
    curr_state = row.get('curr_lifecycle_state')
    if diff_kind == 'new':
        return '首次进入本批冻结快照'
    if diff_kind == 'promoted':
        return f'状态由 {prev_state} 晋升为 {curr_state}'
    if diff_kind == 'demoted':
        return f'状态由 {prev_state} 降为 {curr_state}'
    if diff_kind == 'eligibility_changed':
        return '锚点或基线资格发生变化'
    if diff_kind == 'geometry_changed':
        shift = float(row.get('centroid_shift_m') or 0)
        return f'质心偏移 {shift:.1f}m'
    return '无显著变化'


def get_snapshot_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return {
            'snapshot_version': 'v0',
            'snapshot_version_prev': 'v0',
            'summary': {'new': 0, 'promoted': 0, 'demoted': 0, 'unchanged': 0},
            'items': [],
        }
    diff_rows = _safe_fetchall(
        """
        SELECT operator_code, lac, bs_id, cell_id, diff_kind,
               prev_lifecycle_state, curr_lifecycle_state, centroid_shift_m
        FROM rebuild5.snapshot_diff_cell
        WHERE batch_id = %s AND diff_kind <> 'unchanged'
        ORDER BY CASE diff_kind
            WHEN 'promoted' THEN 1
            WHEN 'new' THEN 2
            WHEN 'demoted' THEN 3
            WHEN 'eligibility_changed' THEN 4
            WHEN 'geometry_changed' THEN 5
            ELSE 9
        END, cell_id
        LIMIT 200
        """,
        (step3['batch_id'],),
    )
    unchanged_row = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.snapshot_diff_cell WHERE batch_id = %s AND diff_kind = %s',
        (step3['batch_id'], 'unchanged'),
    )
    return {
        'snapshot_version': step3['snapshot_version'],
        'snapshot_version_prev': step3['trusted_snapshot_version_prev'],
        'summary': {
            'new': int(step3['snapshot_new_count']),
            'promoted': int(step3['snapshot_promoted_count']),
            'demoted': int(step3['snapshot_demoted_count']),
            'eligibility_changed': int(step3['snapshot_eligibility_changed_count']),
            'geometry_changed': int(step3['snapshot_geometry_changed_count']),
            'unchanged': int(unchanged_row['cnt']) if unchanged_row else 0,
        },
        'items': [
            {
                'cell_id': row['cell_id'],
                'lac': row['lac'],
                'operator_code': row['operator_code'],
                'prev': row['prev_lifecycle_state'],
                'curr': row['curr_lifecycle_state'],
                'diff_kind': row['diff_kind'],
                'reason': _diff_reason(row),
            }
            for row in diff_rows
        ],
    }


def _watch_gap(row: dict[str, Any], thresholds: dict[str, float]) -> str:
    gaps: list[str] = []
    obs_gap = int(max(0, thresholds['qualified_min_obs'] - float(row['independent_obs'])))
    dev_gap = int(max(0, thresholds['qualified_min_devs'] - float(row['distinct_dev_id'])))
    span_gap = max(0.0, thresholds['qualified_min_span_hours'] - float(row['observed_span_hours'] or 0))
    p90 = float(row['p90_radius_m'] or 0)
    p90_gap = max(0.0, p90 - thresholds['qualified_max_p90'])
    if obs_gap > 0:
        gaps.append(f'观测量差 {obs_gap}')
    if dev_gap > 0:
        gaps.append(f'设备数差 {dev_gap}')
    if span_gap > 0:
        gaps.append(f'跨度差 {span_gap:.0f}h')
    if row.get('is_collision_id'):
        gaps.append('碰撞阻断中')
    elif p90_gap > 0:
        gaps.append(f'P90 高 {p90_gap:.0f}m')
    return '，'.join(gaps) if gaps else '已接近 qualified 门槛'


def get_watchlist_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    thresholds = flatten_profile_thresholds(load_profile_params())
    if not step3:
        return {'items': [], 'rules': thresholds}
    rows = _safe_fetchall(
        """
        SELECT operator_code, lac, cell_id, lifecycle_state,
               independent_obs, distinct_dev_id, p90_radius_m, observed_span_hours, is_collision_id
        FROM rebuild5.trusted_snapshot_cell
        WHERE batch_id = %s AND lifecycle_state IN ('waiting', 'observing')
        ORDER BY lifecycle_state DESC, independent_obs DESC, distinct_dev_id DESC
        LIMIT 200
        """,
        (step3['batch_id'],),
    )
    return {
        'items': [
            {
                'cell_id': row['cell_id'],
                'lac': row['lac'],
                'op': row['operator_code'],
                'state': row['lifecycle_state'],
                'obs': int(row['independent_obs']),
                'devs': int(row['distinct_dev_id']),
                'p90': round(float(row['p90_radius_m'] or 0), 1),
                'span_h': round(float(row['observed_span_hours'] or 0), 1),
                'gap': _watch_gap(row, thresholds),
            }
            for row in rows
        ],
        'rules': thresholds,
    }


def get_cell_evaluation_payload(page: int = 1, page_size: int = 50, batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return {'distribution': _empty_distribution(), 'items': [], 'summary': {}, '_page_info': None}
    result = paginate(
        """
        SELECT operator_code, lac, cell_id, bs_id, tech_norm,
               lifecycle_state, position_grade, anchor_eligible, baseline_eligible,
               independent_obs, distinct_dev_id, gps_valid_count,
               observed_span_hours, p50_radius_m, p90_radius_m,
               center_lon, center_lat, active_days, rsrp_avg,
               is_collision_id
        FROM rebuild5.trusted_snapshot_cell
        WHERE batch_id = %s
        ORDER BY independent_obs DESC, cell_id
        """,
        (step3['batch_id'],),
        page=page,
        page_size=page_size,
    )
    return {
        'distribution': {
            'waiting': int(step3['waiting_cell_count']),
            'observing': int(step3['observing_cell_count']),
            'qualified': int(step3['qualified_cell_count']),
            'excellent': int(step3['excellent_cell_count']),
            'dormant': 0,
            'retired': 0,
        },
        'summary': {
            'total': int(step3['evaluated_cell_count']),
            'anchor_eligible': int(step3['anchor_eligible_cell_count']),
        },
        'items': result['items'],
        '_page_info': result,
    }


def get_bs_evaluation_payload(page: int = 1, page_size: int = 50, batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return {'distribution': _empty_distribution(), 'items': [], 'summary': {}, '_page_info': None}
    result = paginate(
        """
        SELECT operator_code, lac, bs_id, lifecycle_state,
               anchor_eligible, baseline_eligible,
               cell_count AS total_cells,
               qualified_cell_count AS qualified_cells,
               excellent_cell_count AS excellent_cells,
               center_lon, center_lat,
               (classification = 'large_spread') AS large_spread,
               classification
        FROM rebuild5.trusted_snapshot_bs
        WHERE batch_id = %s
        ORDER BY cell_count DESC, bs_id
        """,
        (step3['batch_id'],),
        page=page,
        page_size=page_size,
    )
    return {
        'distribution': {
            'waiting': int(step3['bs_waiting_count']),
            'observing': int(step3['bs_observing_count']),
            'qualified': int(step3['bs_qualified_count']),
            'excellent': 0,
            'dormant': 0,
            'retired': 0,
        },
        'summary': {
            'total': int(step3['bs_waiting_count']) + int(step3['bs_observing_count']) + int(step3['bs_qualified_count']),
        },
        'items': result['items'],
        '_page_info': result,
    }


def get_lac_evaluation_payload(page: int = 1, page_size: int = 50, batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return {'distribution': _empty_distribution(), 'items': [], 'summary': {}, '_page_info': None}
    result = paginate(
        """
        SELECT operator_code, lac, lifecycle_state,
               anchor_eligible,
               bs_count AS total_bs,
               qualified_bs_count AS qualified_bs,
               COALESCE(qualified_bs_count::double precision / NULLIF(bs_count, 0), 0) AS qualified_bs_ratio,
               area_km2, anomaly_bs_ratio
        FROM rebuild5.trusted_snapshot_lac
        WHERE batch_id = %s
        ORDER BY bs_count DESC, lac
        """,
        (step3['batch_id'],),
        page=page,
        page_size=page_size,
    )
    return {
        'distribution': {
            'waiting': int(step3['lac_waiting_count']),
            'observing': int(step3['lac_observing_count']),
            'qualified': int(step3['lac_qualified_count']),
            'excellent': 0,
            'dormant': 0,
            'retired': 0,
        },
        'summary': {
            'total': int(step3['lac_waiting_count']) + int(step3['lac_observing_count']) + int(step3['lac_qualified_count']),
        },
        'items': result['items'],
        '_page_info': result,
    }


def get_trend_payload() -> dict[str, Any]:
    rows = _safe_fetchall(
        """
        SELECT batch_id, snapshot_version, dataset_key,
               waiting_cell_count, observing_cell_count, qualified_cell_count, excellent_cell_count,
               evaluated_cell_count, anchor_eligible_cell_count,
               bs_waiting_count, bs_observing_count, bs_qualified_count,
               lac_waiting_count, lac_observing_count, lac_qualified_count
        FROM rebuild5_meta.step3_run_stats
        ORDER BY batch_id
        """
    )
    return {
        'batches': [
            {
                'batch_id': int(r['batch_id']),
                'snapshot_version': r['snapshot_version'],
                'cell': {
                    'waiting': int(r['waiting_cell_count']),
                    'observing': int(r['observing_cell_count']),
                    'qualified': int(r['qualified_cell_count']),
                    'excellent': int(r['excellent_cell_count']),
                    'total': int(r['evaluated_cell_count']),
                },
                'bs': {
                    'waiting': int(r['bs_waiting_count']),
                    'observing': int(r['bs_observing_count']),
                    'qualified': int(r['bs_qualified_count']),
                },
                'lac': {
                    'waiting': int(r['lac_waiting_count']),
                    'observing': int(r['lac_observing_count']),
                    'qualified': int(r['lac_qualified_count']),
                },
            }
            for r in rows
        ],
    }


def get_cell_detail_payload(cell_id: int, batch_id: int | None = None) -> dict[str, Any] | None:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return None
    row = _safe_fetchone(
        """
        SELECT operator_code, lac, cell_id, bs_id, tech_norm,
               lifecycle_state, position_grade, anchor_eligible, baseline_eligible,
               independent_obs, distinct_dev_id, gps_valid_count,
               observed_span_hours, p50_radius_m, p90_radius_m,
               center_lon, center_lat, active_days, rsrp_avg,
               is_collision_id
        FROM rebuild5.trusted_snapshot_cell
        WHERE batch_id = %s AND cell_id = %s
        """,
        (step3['batch_id'], cell_id),
    )
    return row


def get_bs_detail_payload(bs_id: int, batch_id: int | None = None) -> dict[str, Any] | None:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return None
    bs_row = _safe_fetchone(
        """
        SELECT operator_code, lac, bs_id, lifecycle_state,
               anchor_eligible, baseline_eligible,
               cell_count AS total_cells,
               qualified_cell_count AS qualified_cells,
               excellent_cell_count AS excellent_cells,
               center_lon, center_lat, classification
        FROM rebuild5.trusted_snapshot_bs
        WHERE batch_id = %s AND bs_id = %s
        """,
        (step3['batch_id'], bs_id),
    )
    if not bs_row:
        return None
    child_cells = _safe_fetchall(
        """
        SELECT cell_id, lifecycle_state, position_grade, independent_obs, p90_radius_m
        FROM rebuild5.trusted_snapshot_cell
        WHERE batch_id = %s AND bs_id = %s
        ORDER BY independent_obs DESC
        """,
        (step3['batch_id'], bs_id),
    )
    return {**bs_row, 'cells': child_cells}


def get_lac_detail_payload(lac: int, batch_id: int | None = None) -> dict[str, Any] | None:
    step3 = _step3_row_for_batch(batch_id)
    if not step3:
        return None
    lac_row = _safe_fetchone(
        """
        SELECT operator_code, lac, lifecycle_state, anchor_eligible,
               bs_count AS total_bs, qualified_bs_count AS qualified_bs,
               area_km2, anomaly_bs_ratio
        FROM rebuild5.trusted_snapshot_lac
        WHERE batch_id = %s AND lac = %s
        """,
        (step3['batch_id'], lac),
    )
    if not lac_row:
        return None
    child_bs = _safe_fetchall(
        """
        SELECT bs_id, lifecycle_state, cell_count AS total_cells,
               qualified_cell_count AS qualified_cells, classification
        FROM rebuild5.trusted_snapshot_bs
        WHERE batch_id = %s AND lac = %s
        ORDER BY cell_count DESC
        """,
        (step3['batch_id'], lac),
    )
    return {**lac_row, 'base_stations': child_bs}


def get_cell_rule_impact_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    thresholds = flatten_profile_thresholds(load_profile_params())
    if not step3:
        return {'rules': thresholds, 'impact': []}
    bid = step3['batch_id']
    blocked_obs = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_cell WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND independent_obs < %s',
        (bid, 'waiting', 'observing', thresholds['qualified_min_obs']),
    )
    blocked_devs = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_cell WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND distinct_dev_id < %s',
        (bid, 'waiting', 'observing', thresholds['qualified_min_devs']),
    )
    blocked_p90 = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_cell WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND COALESCE(p90_radius_m, 1e9) >= %s',
        (bid, 'waiting', 'observing', thresholds['qualified_max_p90']),
    )
    blocked_span = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_cell WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND COALESCE(observed_span_hours, 0) < %s',
        (bid, 'waiting', 'observing', thresholds['qualified_min_span_hours']),
    )
    blocked_collision = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_cell WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND is_collision_id = true',
        (bid, 'waiting', 'observing'),
    )
    return {
        'rules': thresholds,
        'impact': [
            {'rule': 'independent_obs >= N', 'threshold': thresholds['qualified_min_obs'], 'blocked': int(blocked_obs['cnt']) if blocked_obs else 0, 'desc': '观测量不足'},
            {'rule': 'distinct_dev_id >= N', 'threshold': thresholds['qualified_min_devs'], 'blocked': int(blocked_devs['cnt']) if blocked_devs else 0, 'desc': '设备数不足'},
            {'rule': 'p90_radius_m < N', 'threshold': thresholds['qualified_max_p90'], 'blocked': int(blocked_p90['cnt']) if blocked_p90 else 0, 'desc': '空间质量不足'},
            {'rule': 'observed_span_hours >= N', 'threshold': thresholds['qualified_min_span_hours'], 'blocked': int(blocked_span['cnt']) if blocked_span else 0, 'desc': '观测跨度不足'},
            {'rule': 'is_collision_id = false', 'threshold': 'true', 'blocked': int(blocked_collision['cnt']) if blocked_collision else 0, 'desc': '碰撞阻断'},
        ],
    }


def get_bs_rule_impact_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    thresholds = flatten_profile_thresholds(load_profile_params())
    if not step3:
        return {'rules': thresholds, 'impact': []}
    bid = step3['batch_id']
    blocked_excellent = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_bs WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND excellent_cell_count < %s',
        (bid, 'waiting', 'observing', thresholds['bs_qualified_min_excellent_cells']),
    )
    blocked_qualified = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_bs WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND qualified_cell_count < %s',
        (bid, 'waiting', 'observing', thresholds['bs_qualified_min_qualified_cells']),
    )
    return {
        'rules': thresholds,
        'impact': [
            {'rule': 'excellent Cell >= N', 'threshold': thresholds['bs_qualified_min_excellent_cells'], 'blocked': int(blocked_excellent['cnt']) if blocked_excellent else 0, 'desc': '缺少 excellent Cell'},
            {'rule': 'qualified+ Cell >= N', 'threshold': thresholds['bs_qualified_min_qualified_cells'], 'blocked': int(blocked_qualified['cnt']) if blocked_qualified else 0, 'desc': 'qualified+ Cell 不足'},
        ],
    }


def get_lac_rule_impact_payload(batch_id: int | None = None) -> dict[str, Any]:
    step3 = _step3_row_for_batch(batch_id)
    thresholds = flatten_profile_thresholds(load_profile_params())
    if not step3:
        return {'rules': thresholds, 'impact': []}
    bid = step3['batch_id']
    blocked_count = _safe_fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_lac WHERE batch_id = %s AND lifecycle_state IN (%s,%s) AND qualified_bs_count < %s',
        (bid, 'waiting', 'observing', thresholds['lac_qualified_min_qualified_bs']),
    )
    blocked_ratio = _safe_fetchone(
        """SELECT COUNT(*) AS cnt FROM rebuild5.trusted_snapshot_lac
           WHERE batch_id = %s AND lifecycle_state IN (%s,%s)
             AND COALESCE(qualified_bs_count::double precision / NULLIF(bs_count, 0), 0) < %s""",
        (bid, 'waiting', 'observing', thresholds['lac_qualified_min_qualified_bs_ratio']),
    )
    return {
        'rules': thresholds,
        'impact': [
            {'rule': 'qualified BS >= N', 'threshold': thresholds['lac_qualified_min_qualified_bs'], 'blocked': int(blocked_count['cnt']) if blocked_count else 0, 'desc': 'qualified BS 数量不足'},
            {'rule': 'qualified BS 占比 >= N', 'threshold': thresholds['lac_qualified_min_qualified_bs_ratio'], 'blocked': int(blocked_ratio['cnt']) if blocked_ratio else 0, 'desc': 'qualified BS 占比不足'},
        ],
    }
