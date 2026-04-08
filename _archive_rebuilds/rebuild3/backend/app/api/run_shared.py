from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.common import (
    fetch_all,
    fetch_one,
    format_window,
    safe_float,
    safe_int,
    ttl_cache,
)

FULL_BATCH_ID = 'BATCH-FULL-20251201-20251207-V1'
SAMPLE_BATCH_ID = 'BATCH-SAMPLE-20251201-20251207-V1'
BASELINE_PRINCIPLE = '当前批次只读取上一版冻结 baseline，新版仅供下一批次使用。'

DATA_ORIGIN_REAL = 'real'
DATA_ORIGIN_SYNTHETIC = 'synthetic'
DATA_ORIGIN_FALLBACK = 'fallback'


def build_subject_contract(
    data_origin: str,
    subject_scope: str,
    subject_note: str = '',
    origin_detail: str = '',
) -> dict[str, str]:
    return {
        'data_origin': data_origin,
        'origin_detail': origin_detail,
        'subject_scope': subject_scope,
        'subject_note': subject_note,
    }


def apply_subject_contract(
    payload: dict[str, Any],
    *,
    data_origin: str,
    subject_scope: str,
    subject_note: str = '',
    origin_detail: str = '',
) -> dict[str, Any]:
    return {
        **payload,
        **build_subject_contract(
            data_origin=data_origin,
            subject_scope=subject_scope,
            subject_note=subject_note,
            origin_detail=origin_detail,
        ),
    }


def synthetic_contract(origin_detail: str, subject_scope: str, subject_note: str) -> dict[str, str]:
    return build_subject_contract(
        DATA_ORIGIN_SYNTHETIC,
        subject_scope=subject_scope,
        subject_note=subject_note,
        origin_detail=origin_detail,
    )


def fallback_contract(origin_detail: str, subject_scope: str, subject_note: str) -> dict[str, str]:
    return build_subject_contract(
        DATA_ORIGIN_FALLBACK,
        subject_scope=subject_scope,
        subject_note=subject_note,
        origin_detail=origin_detail,
    )


def _sample_validation_contract(subject_scope: str) -> dict[str, str]:
    return build_subject_contract(
        DATA_ORIGIN_REAL,
        subject_scope=subject_scope,
        subject_note='当前对象来自 sample validation，仅供验证参考，不代表正式主流程结果。',
        origin_detail='sample_validation',
    )


@ttl_cache(ttl_seconds=60)
def _flow_rows(schema: str, batch_id: str) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT fact_layer, row_count, row_ratio
        FROM {schema}.batch_flow_summary
        WHERE batch_id = %(batch_id)s
        ORDER BY CASE fact_layer
          WHEN 'fact_governed' THEN 1
          WHEN 'fact_pending_observation' THEN 2
          WHEN 'fact_pending_issue' THEN 3
          WHEN 'fact_rejected' THEN 4
          ELSE 9 END;
        """,
        {'batch_id': batch_id},
    )
    descriptions = {
        'fact_governed': '已知且健康或仅记录级异常，进入正式治理层。',
        'fact_pending_observation': '新对象仍在存在/锚点/基线资格推进中。',
        'fact_pending_issue': '对象级问题或高风险异常，等待复核处置。',
        'fact_rejected': '结构不合规，留痕后终止。',
    }
    tones = {
        'fact_governed': 'green',
        'fact_pending_observation': 'amber',
        'fact_pending_issue': 'orange',
        'fact_rejected': 'red',
    }
    return [
        {
            'route': row['fact_layer'],
            'count': safe_int(row['row_count']),
            'ratio': safe_float(row['row_ratio']),
            'description': descriptions.get(row['fact_layer'], ''),
            'tone': tones.get(row['fact_layer'], 'slate'),
        }
        for row in rows
    ]


@ttl_cache(ttl_seconds=60)
def _snapshot_map(schema: str, batch_id: str) -> dict[str, int]:
    rows = fetch_all(
        f"""
        SELECT metric_name, metric_value
        FROM {schema}.batch_snapshot
        WHERE batch_id = %(batch_id)s
        """,
        {'batch_id': batch_id},
    )
    return {row['metric_name']: safe_int(row['metric_value']) for row in rows}


@ttl_cache(ttl_seconds=60)
def _snapshot_rows(schema: str, batch_id: str) -> list[dict]:
    rows = fetch_all(
        f"""
        SELECT stage_name, metric_name, metric_value, created_at
        FROM {schema}.batch_snapshot
        WHERE batch_id = %(batch_id)s
        ORDER BY stage_name ASC, metric_name ASC
        """,
        {'batch_id': batch_id},
    )
    return [
        {
            'stage_name': row['stage_name'],
            'metric_name': row['metric_name'],
            'metric_value': row['metric_value'],
            'created_at': row['created_at'],
        }
        for row in rows
    ]


@ttl_cache(ttl_seconds=60)
def _decision_summary(schema: str, batch_id: str) -> dict[str, dict[str, int]]:
    rows = fetch_all(
        f"""
        SELECT decision_name, object_type, object_count
        FROM {schema}.batch_decision_summary
        WHERE batch_id = %(batch_id)s
        ORDER BY decision_name ASC, object_type ASC
        """,
        {'batch_id': batch_id},
    )
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        decision_name = row['decision_name']
        object_type = row['object_type']
        summary.setdefault(decision_name, {})[object_type] = safe_int(row['object_count'])
    return summary


@ttl_cache(ttl_seconds=60)
def _baseline_refresh(schema: str, batch_id: str) -> dict | None:
    return fetch_one(
        f"""
        SELECT baseline_version, refresh_reason, triggered, created_at
        FROM {schema}.batch_baseline_refresh_log
        WHERE batch_id = %(batch_id)s
        """,
        {'batch_id': batch_id},
    )


@ttl_cache(ttl_seconds=60)
def _anomaly_totals(schema: str, batch_id: str) -> dict[str, int]:
    row = fetch_one(
        f"""
        SELECT
          coalesce(sum(object_count), 0)::bigint AS object_total,
          coalesce(sum(fact_count), 0)::bigint AS fact_total
        FROM {schema}.batch_anomaly_summary
        WHERE batch_id = %(batch_id)s
        """,
        {'batch_id': batch_id},
    )
    return {
        'object_total': safe_int(row.get('object_total')),
        'fact_total': safe_int(row.get('fact_total')),
    }


@ttl_cache(ttl_seconds=60)
def _completed_batch_catalog(schema: str = 'rebuild3_meta') -> list[dict[str, Any]]:
    rows = fetch_all(
        f"""
        SELECT
          b.batch_id,
          b.run_id,
          b.batch_type,
          b.status,
          b.window_start,
          b.window_end,
          b.input_rows,
          b.output_rows,
          b.contract_version,
          b.rule_set_version,
          b.baseline_version,
          b.is_rerun,
          b.rerun_source_batch,
          b.scenario_key,
          b.timepoint_role,
          b.batch_seq,
          b.snapshot_at,
          b.created_at,
          coalesce(ss.snapshot_recorded_at, b.created_at) AS snapshot_recorded_at,
          r.run_type,
          r.status AS run_status,
          r.note,
          r.scenario_label,
          r.init_days,
          r.step_hours,
          r.snapshot_source,
          r.contract_version AS run_contract_version,
          r.rule_set_version AS run_rule_set_version,
          r.baseline_version AS run_baseline_version
        FROM {schema}.batch b
        JOIN {schema}.run r
          ON r.run_id = b.run_id
        LEFT JOIN (
          SELECT batch_id, max(created_at) AS snapshot_recorded_at
          FROM {schema}.batch_snapshot
          GROUP BY batch_id
        ) ss
          ON ss.batch_id = b.batch_id
        WHERE b.status = 'completed'
        ORDER BY coalesce(b.snapshot_at, b.window_end, ss.snapshot_recorded_at, b.created_at) DESC,
                 b.created_at DESC,
                 b.batch_id DESC
        """
    )
    return [dict(row) for row in rows]


@ttl_cache(ttl_seconds=60)
def _real_batch_catalog() -> list[dict[str, Any]]:
    rows = []
    for row in _completed_batch_catalog('rebuild3_meta'):
        contract = _batch_contract('rebuild3_meta', row, subject_scope='current_batch')
        if contract['data_origin'] == DATA_ORIGIN_REAL:
            rows.append({**row, **contract})
    return rows


@ttl_cache(ttl_seconds=60)
def _latest_real_batch_id() -> str | None:
    rows = _real_batch_catalog()
    return rows[0]['batch_id'] if rows else None


@ttl_cache(ttl_seconds=60)
def _previous_real_batch_id(batch_id: str) -> str | None:
    rows = _real_batch_catalog()
    for index, row in enumerate(rows):
        if row['batch_id'] == batch_id:
            return rows[index + 1]['batch_id'] if index + 1 < len(rows) else None
    return None


@ttl_cache(ttl_seconds=60)
def _latest_full_initialization_batch_id() -> str | None:
    row = fetch_one(
        """
        SELECT b.batch_id
        FROM rebuild3_meta.batch b
        JOIN rebuild3_meta.run r
          ON r.run_id = b.run_id
        WHERE b.status = 'completed'
          AND r.run_type = 'full_initialization'
        ORDER BY coalesce(b.snapshot_at, b.window_end, b.created_at) DESC,
                 b.created_at DESC,
                 b.batch_id DESC
        LIMIT 1
        """
    )
    if row:
        return row.get('batch_id')
    fallback = fetch_one(
        "SELECT batch_id FROM rebuild3_meta.batch WHERE batch_id = %(batch_id)s",
        {'batch_id': FULL_BATCH_ID},
    )
    return fallback.get('batch_id') if fallback else None


@ttl_cache(ttl_seconds=60)
def _real_baseline_versions() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
          v.baseline_version,
          v.run_id,
          v.batch_id,
          v.rule_set_version,
          v.refresh_reason,
          v.object_count,
          v.created_at,
          r.run_type,
          r.note
        FROM rebuild3_meta.baseline_version v
        JOIN rebuild3_meta.run r
          ON r.run_id = v.run_id
        WHERE r.run_type <> 'scenario_replay'
        ORDER BY v.created_at DESC, v.baseline_version DESC
        """
    )
    return [dict(row) for row in rows]


@ttl_cache(ttl_seconds=60)
def _resolve_batch_schema(batch_id: str) -> str:
    if fetch_one('SELECT batch_id FROM rebuild3_meta.batch WHERE batch_id = %(batch_id)s', {'batch_id': batch_id}):
        return 'rebuild3_meta'
    if fetch_one('SELECT batch_id FROM rebuild3_sample_meta.batch WHERE batch_id = %(batch_id)s', {'batch_id': batch_id}):
        return 'rebuild3_sample_meta'
    raise HTTPException(status_code=404, detail='未找到批次')


@ttl_cache(ttl_seconds=60)
def _batch_context(schema: str, batch_id: str, subject_scope: str = 'current_batch') -> dict:
    row = fetch_one(
        f"""
        SELECT
          b.batch_id,
          b.run_id,
          b.batch_type,
          b.status,
          b.window_start,
          b.window_end,
          b.input_rows,
          b.output_rows,
          b.contract_version,
          b.rule_set_version,
          b.baseline_version,
          b.scenario_key,
          b.timepoint_role,
          b.batch_seq,
          b.snapshot_at,
          b.is_rerun,
          b.rerun_source_batch,
          b.created_at,
          coalesce(ss.snapshot_recorded_at, b.created_at) AS snapshot_recorded_at,
          r.run_type,
          r.note,
          r.scenario_label,
          r.snapshot_source,
          r.status AS run_status,
          r.contract_version AS run_contract_version,
          r.rule_set_version AS run_rule_set_version,
          r.baseline_version AS run_baseline_version
        FROM {schema}.batch b
        JOIN {schema}.run r
          ON r.run_id = b.run_id
        LEFT JOIN (
          SELECT batch_id, max(created_at) AS snapshot_recorded_at
          FROM {schema}.batch_snapshot
          GROUP BY batch_id
        ) ss ON ss.batch_id = b.batch_id
        WHERE b.batch_id = %(batch_id)s
        LIMIT 1
        """,
        {'batch_id': batch_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail='未找到批次')
    contract = _batch_contract(schema, row, subject_scope=subject_scope)
    return {
        'batch_id': row['batch_id'],
        'run_id': row['run_id'],
        'batch_type': row['batch_type'],
        'run_type': row['run_type'],
        'run_status': row['run_status'],
        'status': row['status'],
        'window': format_window(row['window_start'], row['window_end']),
        'window_start': row['window_start'],
        'window_end': row['window_end'],
        'input_rows': safe_int(row['input_rows']),
        'output_rows': safe_int(row['output_rows']),
        'contract_version': row['contract_version'],
        'rule_set_version': row['rule_set_version'],
        'baseline_version': row['baseline_version'],
        'scenario_key': row.get('scenario_key'),
        'scenario_label': row.get('scenario_label'),
        'timepoint_role': row.get('timepoint_role'),
        'batch_seq': safe_int(row.get('batch_seq')),
        'snapshot_at': row.get('snapshot_at'),
        'is_rerun': bool(row['is_rerun']),
        'rerun_source_batch': row['rerun_source_batch'],
        'created_at': row['created_at'],
        'completed_at': row['snapshot_recorded_at'],
        'snapshot_recorded_at': row['snapshot_recorded_at'],
        'snapshot_source': row.get('snapshot_source'),
        'note': row['note'],
        **contract,
    }


@ttl_cache(ttl_seconds=60)
def _record_anomaly_counts(schema: str, batch_id: str) -> dict[str, int]:
    counts = {
        'normal_spread': 0,
        'single_large': 0,
        'gps_fill': 0,
        'signal_fill': 0,
        'structural_rejected': 0,
    }
    rows = fetch_all(
        f"""
        SELECT anomaly_name, coalesce(fact_count, 0)::bigint AS fact_count
        FROM {schema}.batch_anomaly_summary
        WHERE batch_id = %(batch_id)s AND anomaly_level = 'record'
        """,
        {'batch_id': batch_id},
    )
    for row in rows:
        if row['anomaly_name'] in counts:
            counts[row['anomaly_name']] = safe_int(row['fact_count'])
    if rows:
        return counts

    row = fetch_one(
        """
        SELECT
          count(*) FILTER (WHERE anomaly_tags && ARRAY['normal_spread'])::bigint AS normal_spread,
          count(*) FILTER (WHERE anomaly_tags && ARRAY['single_large'])::bigint AS single_large,
          count(*) FILTER (WHERE coalesce(gps_source, 'original') <> 'original')::bigint AS gps_fill,
          count(*) FILTER (WHERE coalesce(signal_source, 'original') <> 'original')::bigint AS signal_fill
        FROM rebuild3.fact_governed
        """
    )
    counts.update(
        {
            'normal_spread': safe_int(row.get('normal_spread')),
            'single_large': safe_int(row.get('single_large')),
            'gps_fill': safe_int(row.get('gps_fill')),
            'signal_fill': safe_int(row.get('signal_fill')),
            'structural_rejected': safe_int(fetch_one('SELECT count(*)::bigint AS cnt FROM rebuild3.fact_rejected').get('cnt')),
        }
    )
    return counts


@ttl_cache(ttl_seconds=60)
def _batch_flow_map(schema: str = 'rebuild3_meta') -> dict[str, list[dict[str, Any]]]:
    rows = fetch_all(
        f"""
        SELECT batch_id, fact_layer, row_count, row_ratio
        FROM {schema}.batch_flow_summary
        WHERE batch_id IN (
          SELECT batch_id FROM {schema}.batch WHERE status = 'completed'
        )
        ORDER BY batch_id ASC,
                 CASE fact_layer
                   WHEN 'fact_governed' THEN 1
                   WHEN 'fact_pending_observation' THEN 2
                   WHEN 'fact_pending_issue' THEN 3
                   WHEN 'fact_rejected' THEN 4
                   ELSE 9 END
        """
    )
    payload: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload.setdefault(row['batch_id'], []).append(
            {
                'route': row['fact_layer'],
                'count': safe_int(row['row_count']),
                'ratio': safe_float(row['row_ratio']),
            }
        )
    return payload


@ttl_cache(ttl_seconds=60)
def _batch_snapshot_maps(schema: str = 'rebuild3_meta') -> dict[str, dict[str, int]]:
    rows = fetch_all(
        f"""
        SELECT batch_id, metric_name, metric_value
        FROM {schema}.batch_snapshot
        WHERE batch_id IN (
          SELECT batch_id FROM {schema}.batch WHERE status = 'completed'
        )
        ORDER BY batch_id ASC, metric_name ASC
        """
    )
    payload: dict[str, dict[str, int]] = {}
    for row in rows:
        payload.setdefault(row['batch_id'], {})[row['metric_name']] = safe_int(row['metric_value'])
    return payload


@ttl_cache(ttl_seconds=60)
def _run_subject_contract(run_row: dict[str, Any], subject_scope: str) -> dict[str, str]:
    synthetic_row = {
        'run_type': run_row.get('run_type'),
        'batch_type': run_row.get('batch_type'),
        'scenario_key': run_row.get('scenario_key'),
    }
    return _batch_contract('rebuild3_meta', synthetic_row, subject_scope=subject_scope)


@ttl_cache(ttl_seconds=60)
def _batch_contract(schema: str, row: dict[str, Any], subject_scope: str = 'current_batch') -> dict[str, str]:
    if schema == 'rebuild3_sample_meta':
        return _sample_validation_contract(subject_scope)

    run_type = str(row.get('run_type') or '')
    batch_type = str(row.get('batch_type') or '').lower()
    scenario_key = str(row.get('scenario_key') or '').upper()

    if run_type == 'scenario_replay':
        smoke_prefix = '[SMOKE] ' if 'SMOKE' in scenario_key else ''
        return synthetic_contract(
            'scenario_replay',
            subject_scope=subject_scope,
            subject_note=f'当前对象来自 {smoke_prefix}scenario replay，仅供诊断，不代表正式主流程结果。'.strip(),
        )

    if run_type == 'full_initialization' or batch_type == 'full_init':
        return synthetic_contract(
            'full_initialization_estimated_snapshot',
            subject_scope=subject_scope,
            subject_note='当前初始化主语真实存在，但批次汇总快照仍来自估算写入，仅供参考。',
        )

    return build_subject_contract(DATA_ORIGIN_REAL, subject_scope=subject_scope)
