from __future__ import annotations

from fastapi import HTTPException

from app.api.common import compare_membership, operator_name, safe_float, safe_int, watch_flag

OBJECT_CONFIG = {
    'cell': {
        'table': 'rebuild3.obj_cell',
        'profile_table': 'rebuild3.stg_cell_profile',
        'compare_table': 'rebuild3_meta.r2_full_cell_state',
        'compare_profile_table': 'rebuild3_meta.r2_full_profile_cell',
        'label': 'Cell',
        'key_columns': ['lac', 'bs_id', 'cell_id'],
        'sort_map': {
            'record_count': 'record_count',
            'active_days': 'active_days',
            'gps_p90_dist_m': 'gps_p90_dist_m',
            'cell_id': 'cell_id',
        },
    },
    'bs': {
        'table': 'rebuild3.obj_bs',
        'profile_table': 'rebuild3.stg_bs_profile',
        'compare_table': 'rebuild3_meta.r2_full_bs_state',
        'compare_profile_table': 'rebuild3_meta.r2_full_profile_bs',
        'label': 'BS',
        'key_columns': ['lac', 'bs_id'],
        'sort_map': {
            'record_count': 'record_count',
            'active_days': 'active_days',
            'gps_p90_dist_m': 'gps_p90_dist_m',
            'bs_id': 'bs_id',
        },
    },
    'lac': {
        'table': 'rebuild3.obj_lac',
        'profile_table': 'rebuild3.stg_lac_profile',
        'compare_table': 'rebuild3_meta.r2_full_lac_state',
        'compare_profile_table': 'rebuild3_meta.r2_full_profile_lac',
        'label': 'LAC',
        'key_columns': ['lac'],
        'sort_map': {
            'record_count': 'record_count',
            'active_days': 'active_days',
            'lac': 'lac',
            'bs_count': 'bs_count',
        },
    },
}

REGION_QUALITY_LABELS = {
    'coverage_insufficient': '覆盖不足',
    'issue_present': '存在问题',
}


def require_object_type(object_type: str) -> dict:
    config = OBJECT_CONFIG.get(object_type)
    if not config:
        raise HTTPException(status_code=400, detail='仅支持 cell / bs / lac')
    return config


def search_clause(object_type: str) -> str:
    if object_type == 'cell':
        return "(o.object_id ILIKE %(pattern)s OR o.lac ILIKE %(pattern)s OR cast(o.bs_id as text) ILIKE %(pattern)s OR cast(o.cell_id as text) ILIKE %(pattern)s)"
    if object_type == 'bs':
        return "(o.object_id ILIKE %(pattern)s OR o.lac ILIKE %(pattern)s OR cast(o.bs_id as text) ILIKE %(pattern)s)"
    return "(o.object_id ILIKE %(pattern)s OR o.lac ILIKE %(pattern)s)"


def build_filters(
    object_type: str,
    query: str | None,
    operator_code: str | None,
    tech_norm: str | None,
    lifecycle_state: str | None,
    health_state: str | None,
    qualification: str | None,
) -> tuple[list[str], dict]:
    where = ['1=1']
    params: dict[str, object] = {}
    if query:
        where.append(search_clause(object_type))
        params['pattern'] = f'%{query}%'
    if operator_code and operator_code != 'all':
        where.append('o.operator_code = %(operator_code)s')
        params['operator_code'] = operator_code
    if tech_norm and tech_norm != 'all':
        where.append('o.tech_norm = %(tech_norm)s')
        params['tech_norm'] = tech_norm
    if lifecycle_state and lifecycle_state != 'all':
        where.append('o.lifecycle_state = %(lifecycle_state)s')
        params['lifecycle_state'] = lifecycle_state
    if health_state and health_state != 'all':
        where.append('o.health_state = %(health_state)s')
        params['health_state'] = health_state
    if qualification == 'anchorable':
        where.append('o.anchorable')
    elif qualification == 'not_anchorable':
        where.append('NOT o.anchorable')
    elif qualification == 'baseline':
        where.append('o.baseline_eligible')
    elif qualification == 'not_baseline':
        where.append('NOT o.baseline_eligible')
    return where, params


def profile_join_sql(object_type: str) -> str:
    if object_type == 'cell':
        return """
        LEFT JOIN rebuild3.stg_cell_profile p
          ON p.operator_code = o.operator_code AND p.tech_norm = o.tech_norm AND p.lac = o.lac AND p.bs_id = o.bs_id AND p.cell_id = o.cell_id
        LEFT JOIN rebuild3_meta.r2_full_cell_state c
          ON c.object_id = o.object_id
        LEFT JOIN rebuild3.stg_bs_classification_ref bcr
          ON bcr.operator_code = o.operator_code AND bcr.tech_norm = o.tech_norm AND bcr.lac = o.lac AND bcr.bs_id = o.bs_id
        """
    if object_type == 'bs':
        return """
        LEFT JOIN rebuild3.stg_bs_profile p
          ON p.operator_code = o.operator_code AND p.tech_norm = o.tech_norm AND p.lac = o.lac AND p.bs_id = o.bs_id
        LEFT JOIN rebuild3_meta.r2_full_bs_state c
          ON c.object_id = o.object_id
        LEFT JOIN rebuild3_meta.r2_full_profile_bs cp
          ON cp.operator_code = o.operator_code AND cp.tech_norm = o.tech_norm AND cp.lac = o.lac AND cp.bs_id = o.bs_id
        LEFT JOIN rebuild3.stg_bs_classification_ref bcr
          ON bcr.operator_code = o.operator_code AND bcr.tech_norm = o.tech_norm AND bcr.lac = o.lac AND bcr.bs_id = o.bs_id
        """
    return """
    LEFT JOIN rebuild3.stg_lac_profile p
      ON p.operator_code = o.operator_code AND p.tech_norm = o.tech_norm AND p.lac = o.lac
    LEFT JOIN rebuild3_meta.r2_full_lac_state c
      ON c.object_id = o.object_id
    """


def select_fields(object_type: str, include_total: bool = True) -> str:
    common = """
      o.object_id,
      o.operator_code,
      o.tech_norm,
      o.lac,
      o.lifecycle_state,
      o.health_state,
      o.existence_eligible,
      o.anchorable,
      o.baseline_eligible,
      o.record_count,
      o.gps_count,
      o.active_days,
      o.gps_original_ratio,
      o.signal_original_ratio,
      o.anomaly_tags,
      c.health_state AS r2_health_state,
      c.baseline_eligible AS r2_baseline_eligible
    """
    if include_total:
        common += ', count(*) OVER() AS total_count'
    if object_type == 'cell':
        return common + ', o.bs_id, o.cell_id, o.device_count, o.gps_p50_dist_m, o.gps_p90_dist_m, o.centroid_lon AS center_lon, o.centroid_lat AS center_lat, p.center_lon AS profile_center_lon, p.center_lat AS profile_center_lat, p.gps_max_dist_m, p.rsrp_avg, p.bs_gps_quality AS bs_gps_quality_reference, p.gps_anomaly, p.dist_to_bs_m, bcr.classification_v2'
    if object_type == 'bs':
        return common + ', o.bs_id, o.device_count, o.cell_count, o.active_cell_count, o.center_lon, o.center_lat, o.gps_p50_dist_m, o.gps_p90_dist_m, p.gps_max_dist_m, p.rsrp_avg, cp.classification_v2, p.gps_quality AS gps_quality_reference'
    return common + ', o.bs_count, o.active_bs_count, o.cell_count, o.center_lon, o.center_lat, o.region_quality_label'


def serialize_row(object_type: str, row: dict) -> dict:
    item = {
        'object_id': row['object_id'],
        'object_type': object_type,
        'object_label': OBJECT_CONFIG[object_type]['label'],
        'operator_code': row['operator_code'],
        'operator_name': operator_name(row['operator_code']),
        'tech_norm': row['tech_norm'],
        'lac': row['lac'],
        'lifecycle_state': row['lifecycle_state'],
        'health_state': row['health_state'],
        'existence_eligible': bool(row['existence_eligible']),
        'anchorable': bool(row['anchorable']),
        'baseline_eligible': bool(row['baseline_eligible']),
        'record_count': safe_int(row['record_count']),
        'gps_count': safe_int(row['gps_count']),
        'active_days': safe_int(row['active_days']),
        'gps_original_ratio': safe_float(row.get('gps_original_ratio')),
        'signal_original_ratio': safe_float(row.get('signal_original_ratio')),
        'watch': watch_flag(row['lifecycle_state'], row['health_state']),
        'compare_membership': compare_membership(bool(row['baseline_eligible']), bool(row.get('r2_baseline_eligible'))),
    }
    if object_type == 'cell':
        item.update(
            {
                'bs_id': safe_int(row.get('bs_id')),
                'cell_id': safe_int(row.get('cell_id')),
                'device_count': safe_int(row.get('device_count')),
                'center_lon': safe_float(row.get('center_lon')) if row.get('center_lon') is not None else None,
                'center_lat': safe_float(row.get('center_lat')) if row.get('center_lat') is not None else None,
                'profile_center_lon': safe_float(row.get('profile_center_lon')) if row.get('profile_center_lon') is not None else None,
                'profile_center_lat': safe_float(row.get('profile_center_lat')) if row.get('profile_center_lat') is not None else None,
                'gps_p50_dist_m': safe_float(row.get('gps_p50_dist_m')),
                'gps_p90_dist_m': safe_float(row.get('gps_p90_dist_m')),
                'gps_max_dist_m': safe_float(row.get('gps_max_dist_m')),
                'rsrp_avg': safe_float(row.get('rsrp_avg')) if row.get('rsrp_avg') is not None else None,
                'classification_v2': row.get('classification_v2'),
                'bs_gps_quality_reference': row.get('bs_gps_quality_reference'),
                'legacy_gps_anomaly': bool(row.get('gps_anomaly')),
                'dist_to_bs_m': safe_float(row.get('dist_to_bs_m')),
                'coordinate_source_note': '对象快照质心来自 obj_cell.centroid_*；画像表中心点仅作为参考字段。',
            }
        )
    elif object_type == 'bs':
        item.update(
            {
                'bs_id': safe_int(row.get('bs_id')),
                'cell_count': safe_int(row.get('cell_count')),
                'active_cell_count': safe_int(row.get('active_cell_count')),
                'device_count': safe_int(row.get('device_count')),
                'center_lon': safe_float(row.get('center_lon')) if row.get('center_lon') is not None else None,
                'center_lat': safe_float(row.get('center_lat')) if row.get('center_lat') is not None else None,
                'gps_p50_dist_m': safe_float(row.get('gps_p50_dist_m')),
                'gps_p90_dist_m': safe_float(row.get('gps_p90_dist_m')),
                'gps_max_dist_m': safe_float(row.get('gps_max_dist_m')),
                'rsrp_avg': safe_float(row.get('rsrp_avg')) if row.get('rsrp_avg') is not None else None,
                'classification_v2': row.get('classification_v2'),
                'gps_quality_reference': row.get('gps_quality_reference'),
            }
        )
    else:
        item.update(
            {
                'bs_count': safe_int(row.get('bs_count')),
                'active_bs_count': safe_int(row.get('active_bs_count')),
                'cell_count': safe_int(row.get('cell_count')),
                'center_lon': safe_float(row.get('center_lon')) if row.get('center_lon') is not None else None,
                'center_lat': safe_float(row.get('center_lat')) if row.get('center_lat') is not None else None,
                'region_quality_code': row.get('region_quality_label'),
                'region_quality_label': REGION_QUALITY_LABELS.get(row.get('region_quality_label'), row.get('region_quality_label')),
            }
        )
    return item
