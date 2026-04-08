from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.common import fetch_all, now_iso, safe_int, ttl_cache
from app.api.run_snapshot import build_flow_snapshot_payload
from app.api.run_shared import (
    BASELINE_PRINCIPLE,
    FULL_BATCH_ID,
    SAMPLE_BATCH_ID,
    DATA_ORIGIN_REAL,
    _completed_batch_catalog,
    _anomaly_totals,
    _baseline_refresh,
    _batch_context,
    _batch_contract,
    _batch_flow_map,
    _batch_snapshot_maps,
    _decision_summary,
    _flow_rows,
    _latest_full_initialization_batch_id,
    _latest_real_batch_id,
    _previous_real_batch_id,
    _resolve_batch_schema,
    _snapshot_map,
    apply_subject_contract,
    synthetic_contract,
)

router = APIRouter(prefix='/api/v1/runs', tags=['runs'])


@router.get('/current')
@ttl_cache(ttl_seconds=30)
def get_current_run():
    current_batch_id = _latest_full_initialization_batch_id() or FULL_BATCH_ID
    current = _batch_context('rebuild3_meta', current_batch_id, subject_scope='initialization_run')
    validation = _batch_context('rebuild3_sample_meta', SAMPLE_BATCH_ID, subject_scope='validation_reference')
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'current': current,
        'validation': validation,
        'principle': BASELINE_PRINCIPLE,
    }


def _empty_flow_overview(subject_note: str) -> dict[str, Any]:
    return apply_subject_contract(
        {
            'status': 'ok',
            'generated_at': now_iso(),
            'run_id': None,
            'batch_id': None,
            'context': {},
            'principle': BASELINE_PRINCIPLE,
            'flow': [],
            'key_metrics': [],
            'issue_entries': [],
            'compare_callout': None,
            'snapshot_note': '当前页仅接受真实 batch；不会再以 sample / full / scenario synthetic 替代正式主语。',
            'decision_summary': {},
            'baseline_refreshed': False,
            'baseline_next_version': '',
            'anomaly_total': 0,
            'anomaly_new': 0,
            'empty_state': {
                'title': '暂无真实批次',
                'description': subject_note,
            },
        },
        data_origin=DATA_ORIGIN_REAL,
        subject_scope='current_batch',
        subject_note=subject_note,
    )


def _latest_evaluation_batch_id() -> str | None:
    catalog = _completed_batch_catalog('rebuild3_meta')
    if not catalog:
        return None

    predicates = [
        lambda row: row['run_type'] == 'scenario_replay'
        and 'SMOKE' not in str(row.get('scenario_key') or '').upper()
        and row.get('timepoint_role') != 'init',
        lambda row: row['run_type'] == 'scenario_replay' and row.get('timepoint_role') != 'init',
        lambda row: row['run_type'] == 'scenario_replay',
        lambda row: row['run_type'] == 'full_initialization',
        lambda row: True,
    ]
    for predicate in predicates:
        for row in catalog:
            if predicate(row):
                return row['batch_id']
    return None


def _previous_batch_in_run(batch_id: str) -> str | None:
    schema = _resolve_batch_schema(batch_id)
    context = _batch_context(schema, batch_id, subject_scope='current_batch')
    rows = [row for row in _completed_batch_catalog(schema) if row['run_id'] == context['run_id']]
    rows.sort(
        key=lambda item: (
            item['batch_seq'] if item.get('batch_seq') is not None else 999999,
            item.get('snapshot_at') or item.get('window_end') or item.get('snapshot_recorded_at'),
            item['batch_id'],
        )
    )
    for index, row in enumerate(rows):
        if row['batch_id'] == batch_id:
            return rows[index - 1]['batch_id'] if index > 0 else None
    return None


@router.get('/flow-overview')
@ttl_cache(ttl_seconds=30)
def get_flow_overview(batch_id: str | None = Query(default=None)):
    selected_batch_id = batch_id or _latest_real_batch_id()
    if not selected_batch_id:
        selected_batch_id = _latest_evaluation_batch_id()
    if not selected_batch_id:
        return _empty_flow_overview('当前既没有真实 batch，也没有可用于评估的 synthetic 批次。')

    schema = _resolve_batch_schema(selected_batch_id)
    if schema != 'rebuild3_meta':
        return _empty_flow_overview('当前选择的批次来自 sample validation，流转总览不作为正式或评估主语展示。')
    context = _batch_context(schema, selected_batch_id, subject_scope='current_batch')
    synthetic_overview_note = (
        '当前暂无真实正式 batch，已自动切换到 synthetic scenario 批次用于功能评估；仅供功能验证，不代表正式主流程结果。'
        if context['run_type'] == 'scenario_replay'
        else '当前暂无真实正式 batch，已切换到 synthetic 初始化快照用于功能评估；仅供功能验证，不代表正式主流程结果。'
    )
    subject_note = context['subject_note'] if context['data_origin'] == DATA_ORIGIN_REAL else synthetic_overview_note

    flow = _flow_rows(schema, selected_batch_id)
    snapshot = _snapshot_map(schema, selected_batch_id)
    decision_summary = _decision_summary(schema, selected_batch_id)
    refresh = _baseline_refresh(schema, selected_batch_id)
    anomaly_totals = _anomaly_totals(schema, selected_batch_id)

    if context['data_origin'] == DATA_ORIGIN_REAL:
        previous_batch_id = _previous_real_batch_id(selected_batch_id)
        previous_context = _batch_context('rebuild3_meta', previous_batch_id, subject_scope='current_batch') if previous_batch_id else {}
        previous_snapshot = _snapshot_map('rebuild3_meta', previous_batch_id) if previous_batch_id else {}
        delta_label = 'vs 上一真实批次' if previous_batch_id else '暂无上一真实批次'
    else:
        previous_batch_id = _previous_batch_in_run(selected_batch_id)
        previous_context = _batch_context(schema, previous_batch_id, subject_scope='current_batch') if previous_batch_id else {}
        previous_snapshot = _snapshot_map(schema, previous_batch_id) if previous_batch_id else {}
        delta_label = 'vs 同场景上一批次' if previous_batch_id else '暂无同场景上一批次'

    anomalies = fetch_all(
        """
        SELECT anomaly_level, anomaly_name, object_count, fact_count
        FROM rebuild3_meta.batch_anomaly_summary
        WHERE batch_id = %(batch_id)s
          AND anomaly_name IN ('gps_bias', 'collision_confirmed', 'collision_suspect', 'dynamic')
        ORDER BY coalesce(object_count, 0) DESC, anomaly_name ASC
        LIMIT 8
        """,
        {'batch_id': selected_batch_id},
    )

    key_metrics = []
    metric_defs = [
        ('fact_standardized', '输入事件'),
        ('fact_governed', '已治理'),
        ('fact_pending_observation', '观察池'),
        ('fact_pending_issue', '问题池'),
        ('fact_rejected', '拒收池'),
        ('obj_cell', 'Cell 对象'),
        ('baseline_cell', 'Cell baseline'),
        ('baseline_bs', 'BS baseline'),
    ]
    for metric_name, label in metric_defs:
        current_value = snapshot.get(metric_name, 0)
        previous_value = previous_snapshot.get(metric_name, 0) if previous_batch_id else None
        key_metrics.append(
            {
                'metric_name': metric_name,
                'label': label,
                'value': current_value,
                'delta': current_value - previous_value if previous_value is not None else None,
                'delta_label': delta_label,
                'reference_batch_id': previous_batch_id or '',
            }
        )

    compare_metrics = []
    if previous_batch_id:
        compare_metrics = [
            {'label': 'fact_pending_issue 变化', 'value': snapshot.get('fact_pending_issue', 0) - previous_snapshot.get('fact_pending_issue', 0)},
            {'label': 'fact_pending_observation 变化', 'value': snapshot.get('fact_pending_observation', 0) - previous_snapshot.get('fact_pending_observation', 0)},
            {'label': 'Cell baseline 变化', 'value': snapshot.get('baseline_cell', 0) - previous_snapshot.get('baseline_cell', 0)},
        ]

    issue_entries = [
        {
            'title': '观察池堆积',
            'count': snapshot.get('fact_pending_observation', 0),
            'severity': 'medium',
            'href': '/observation',
            'summary': '等待 / 观察对象仍需推进三层资格。',
        },
        {
            'title': 'GPS 偏差对象',
            'count': next((safe_int(row['object_count']) for row in anomalies if row['anomaly_name'] == 'gps_bias'), 0),
            'severity': 'high',
            'href': '/anomalies',
            'summary': '当前批次最值得优先检查的对象级异常。',
        },
        {
            'title': '碰撞确认对象',
            'count': next((safe_int(row['object_count']) for row in anomalies if row['anomaly_name'] == 'collision_confirmed'), 0),
            'severity': 'high',
            'href': '/anomalies',
            'summary': '对象级碰撞会直接禁止锚点与 baseline。',
        },
        {
            'title': '拒收记录',
            'count': snapshot.get('fact_rejected', 0),
            'severity': 'medium',
            'href': '/runs',
            'summary': '结构不合规记录已进入拒收层并留痕。',
        },
    ]

    payload = {
        'status': 'ok',
        'generated_at': now_iso(),
        'run_id': context['run_id'],
        'batch_id': context['batch_id'],
        'context': context,
        'principle': BASELINE_PRINCIPLE,
        'flow': flow,
        'key_metrics': key_metrics,
        'issue_entries': issue_entries,
        'compare_callout': {
            'title': (
                '相较上一真实批次的关键变化'
                if context['data_origin'] == DATA_ORIGIN_REAL and previous_batch_id
                else '相较同场景上一批次的关键变化（评估模式）'
                if previous_batch_id
                else '暂无上一真实批次'
                if context['data_origin'] == DATA_ORIGIN_REAL
                else '暂无同场景上一批次'
            ),
            'summary': (
                f"当前批次与 {previous_batch_id} 做真实批次对比。"
                if context['data_origin'] == DATA_ORIGIN_REAL and previous_batch_id
                else f"当前批次与 {previous_batch_id} 做同场景 synthetic 批次对比，用于功能评估。"
                if previous_batch_id
                else '当前仅展示当前真实批次累计状态；不再以 sample validation 代替历史对照。'
                if context['data_origin'] == DATA_ORIGIN_REAL
                else '当前仅展示 synthetic 评估批次累计状态；如需正式口径，请等待真实 batch 产出。'
            ),
            'metrics': compare_metrics,
            'reference_batch_id': previous_batch_id or '',
            'reference_window': previous_context.get('window', ''),
        },
        'snapshot_note': (
            f"当前页面指向真实批次 {selected_batch_id}；delta 仅基于上一真实批次计算。"
            if context['data_origin'] == DATA_ORIGIN_REAL and previous_batch_id
            else f"当前页面处于评估模式，指向 synthetic 批次 {selected_batch_id}；delta 仅基于同场景上一批次计算。"
            if previous_batch_id
            else '当前页面指向真实批次；由于暂无上一真实批次，delta 已诚实留空。'
            if context['data_origin'] == DATA_ORIGIN_REAL
            else '当前页面处于评估模式；由于暂无同场景上一批次，delta 已诚实留空。'
        ),
        'decision_summary': decision_summary,
        'baseline_refreshed': bool(refresh.get('triggered')) if refresh else False,
        'baseline_next_version': refresh.get('baseline_version') if refresh and refresh.get('triggered') else '',
        'anomaly_total': anomaly_totals['object_total'],
        'anomaly_new': anomaly_totals['object_total'],
        'empty_state': None,
    }
    return apply_subject_contract(
        payload,
        data_origin=context['data_origin'],
        origin_detail=context['origin_detail'],
        subject_scope=context['subject_scope'],
        subject_note=subject_note,
    )


@router.get('/flow-snapshots')
@ttl_cache(ttl_seconds=30)
def get_flow_snapshots(
    run_id: str | None = Query(default=None),
    time_a: str | None = Query(default=None),
    time_b: str | None = Query(default=None),
):
    payload = build_flow_snapshot_payload(run_id=run_id, time_a=time_a, time_b=time_b)
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **payload,
    }


@router.get('/batches')
@ttl_cache(ttl_seconds=30)
def get_batches():
    catalog = _batch_snapshot_maps('rebuild3_meta')
    flow_map = _batch_flow_map('rebuild3_meta')

    run_rows: dict[str, dict[str, Any]] = {}
    for row in _completed_batch_catalog('rebuild3_meta'):
        run_id = row['run_id']
        run_entry = run_rows.setdefault(
            run_id,
            {
                'run_id': run_id,
                'run_type': row['run_type'],
                'status': row['run_status'],
                'scenario_key': row.get('scenario_key'),
                'label': row.get('scenario_key') or row.get('scenario_label') or run_id,
                'note': row.get('note') or '',
                'contract_version': row.get('run_contract_version') or row.get('contract_version'),
                'rule_set_version': row.get('run_rule_set_version') or row.get('rule_set_version'),
                'baseline_version': row.get('run_baseline_version') or row.get('baseline_version'),
                'last_snapshot_time': row['snapshot_recorded_at'],
                'batch_count': 0,
                'completed_batch_count': 0,
                'batches': [],
            },
        )
        run_entry['batch_count'] += 1
        run_entry['completed_batch_count'] += 1
        run_entry['last_snapshot_time'] = max(run_entry['last_snapshot_time'], row['snapshot_recorded_at'])
        batch_contract = _batch_contract('rebuild3_meta', row, subject_scope='current_batch')
        snapshot = catalog.get(row['batch_id'], {})
        flow = flow_map.get(row['batch_id'], [])
        run_entry['batches'].append(
            {
                'batch_id': row['batch_id'],
                'batch_type': row['batch_type'],
                'status': row['status'],
                'window': _batch_context('rebuild3_meta', row['batch_id'], subject_scope='current_batch')['window'],
                'window_start': row['window_start'],
                'window_end': row['window_end'],
                'input_rows': safe_int(row['input_rows']),
                'output_rows': safe_int(row['output_rows']),
                'baseline_version': row['baseline_version'],
                'contract_version': row['contract_version'],
                'rule_set_version': row['rule_set_version'],
                'is_rerun': bool(row['is_rerun']),
                'rerun_source_batch': row['rerun_source_batch'],
                'scenario_key': row.get('scenario_key'),
                'timepoint_role': row.get('timepoint_role'),
                'batch_seq': safe_int(row.get('batch_seq')),
                'snapshot_at': row.get('snapshot_at'),
                'snapshot_recorded_at': row['snapshot_recorded_at'],
                'flow': flow,
                'snapshot': snapshot,
                'headline_metric': snapshot.get('fact_pending_issue', 0),
                'headline_label': '问题池',
                **batch_contract,
            }
        )

    rows = []
    for run_entry in sorted(run_rows.values(), key=lambda item: (item['last_snapshot_time'], item['run_id']), reverse=True):
        run_entry['batches'].sort(
            key=lambda item: (
                item['batch_seq'] if item['batch_seq'] is not None else 999999,
                item['snapshot_at'] or item['window_end'] or item['snapshot_recorded_at'],
                item['batch_id'],
            )
        )
        trend_points_issue = []
        trend_points_baseline = []
        for batch in run_entry['batches']:
            label = 'init' if batch['timepoint_role'] == 'init' else (f"#{batch['batch_seq']}" if batch['batch_seq'] is not None else batch['batch_id'])
            trend_points_issue.append({'label': label, 'value': batch['snapshot'].get('fact_pending_issue', 0)})
            trend_points_baseline.append({'label': label, 'value': batch['snapshot'].get('baseline_cell', 0)})
        run_contract = _batch_contract(
            'rebuild3_meta',
            {
                'run_type': run_entry['run_type'],
                'batch_type': run_entry['batches'][0]['batch_type'] if run_entry['batches'] else '',
                'scenario_key': run_entry.get('scenario_key'),
            },
            subject_scope='current_batch',
        )
        run_entry.update(
            {
                'trend': {
                    'available': len(run_entry['batches']) > 1,
                    'label': (
                        '真实批次不足，无法形成趋势。'
                        if len(run_entry['batches']) <= 1
                        else '趋势基于该 run 下已完成批次的真实注册行；如为 synthetic run，会显式标识。'
                    ),
                    'series': [
                        {'metric': 'fact_pending_issue', 'points': trend_points_issue},
                        {'metric': 'baseline_cell', 'points': trend_points_baseline},
                    ],
                },
                **run_contract,
            }
        )
        rows.append(run_entry)

    return apply_subject_contract(
        {
            'status': 'ok',
            'generated_at': now_iso(),
            'rows': rows,
            'selected_run_id': rows[0]['run_id'] if rows else '',
            'empty_state': None if rows else {'title': '暂无运行批次', 'description': '当前正式库尚未记录任何运行批次。'},
        },
        data_origin=DATA_ORIGIN_REAL,
        subject_scope='current_batch',
        subject_note='运行/批次中心改为直接读取 rebuild3_meta.run 与 rebuild3_meta.batch，不再使用 sample/full 两条硬编码伪主语。',
    )


@router.get('/batch/{batch_id}')
@ttl_cache(ttl_seconds=30)
def get_batch_detail(batch_id: str):
    schema = _resolve_batch_schema(batch_id)
    context = _batch_context(schema, batch_id, subject_scope='current_batch')
    flow = _flow_rows(schema, batch_id)
    snapshot = _snapshot_map(schema, batch_id)
    decision_summary = _decision_summary(schema, batch_id)
    anomalies = fetch_all(
        f"""
        SELECT anomaly_level, anomaly_name, object_count, fact_count
        FROM {schema}.batch_anomaly_summary
        WHERE batch_id = %(batch_id)s
        ORDER BY coalesce(object_count, fact_count, 0) DESC, anomaly_name ASC
        LIMIT 12
        """,
        {'batch_id': batch_id},
    )
    refresh = _baseline_refresh(schema, batch_id)
    payload = {
        'status': 'ok',
        'generated_at': now_iso(),
        'context': context,
        'flow': flow,
        'snapshot': snapshot,
        'anomalies': [
            {
                'level': row['anomaly_level'],
                'name': row['anomaly_name'],
                'count': safe_int(row.get('object_count') or row.get('fact_count')),
            }
            for row in anomalies
        ],
        'baseline_refresh': refresh,
        'decision_summary': decision_summary,
        'principle': BASELINE_PRINCIPLE,
        'cascade_summary': None,
    }
    return apply_subject_contract(
        payload,
        data_origin=context['data_origin'],
        origin_detail=context['origin_detail'],
        subject_scope=context['subject_scope'],
        subject_note=context['subject_note'],
    )


@router.get('/initialization')
@ttl_cache(ttl_seconds=30)
def get_initialization():
    batch_id = _latest_full_initialization_batch_id()
    if not batch_id:
        return apply_subject_contract(
            {
                'status': 'ok',
                'generated_at': now_iso(),
                'run_id': None,
                'batch_id': None,
                'context': {},
                'steps': [],
                'summary_cards': [],
                'flow_summary': [],
                'notes': [],
                'empty_state': {
                    'title': '暂无真实 initialization run',
                    'description': '当前尚未发现可作为初始化页主语的真实 full initialization run/batch。',
                },
            },
            data_origin=DATA_ORIGIN_REAL,
            subject_scope='initialization_run',
            subject_note='当前尚未发现可作为初始化页主语的真实 full initialization run/batch。',
        )

    context = _batch_context('rebuild3_meta', batch_id, subject_scope='initialization_run')
    snapshot = _snapshot_map('rebuild3_meta', batch_id)
    standardized = snapshot.get('fact_standardized', 0)
    flow_summary = _flow_rows('rebuild3_meta', batch_id)
    steps = [
        {'index': 1, 'label': '冻结 run 与版本上下文', 'status': 'completed'},
        {
            'index': 2,
            'label': '全量标准化事件',
            'status': 'completed',
            'input': context.get('input_rows'),
            'output': standardized,
            'pass_rate': (standardized / context['input_rows']) if context.get('input_rows') else None,
        },
        {'index': 3, 'label': '记录级结构校验', 'status': 'completed', 'input': standardized, 'output': standardized},
        {'index': 4, 'label': '研究期 LAC / GPS 约束', 'status': 'completed'},
        {'index': 5, 'label': 'Cell 候选累计与晋升', 'status': 'completed'},
        {'index': 6, 'label': '由 Cell 派生 BS', 'status': 'completed'},
        {'index': 7, 'label': '由 BS 派生 LAC', 'status': 'completed'},
        {
            'index': 8,
            'label': '首轮事实治理',
            'status': 'completed',
            'input': standardized,
            'output': snapshot.get('fact_governed', 0),
            'pass_rate': (snapshot.get('fact_governed', 0) / standardized) if standardized else None,
        },
        {'index': 9, 'label': '异常检测与资格收敛', 'status': 'completed'},
        {'index': 10, 'label': '生成首版 baseline', 'status': 'completed'},
        {'index': 11, 'label': '切入后续增量治理', 'status': 'completed'},
    ]
    payload = {
        'status': 'ok',
        'generated_at': now_iso(),
        'run_id': context['run_id'],
        'batch_id': context['batch_id'],
        'context': context,
        'steps': steps,
        'summary_cards': [
            {'label': '标准化事件', 'value': standardized},
            {'label': '已治理', 'value': snapshot.get('fact_governed', 0)},
            {'label': '观察池', 'value': snapshot.get('fact_pending_observation', 0)},
            {'label': '问题池', 'value': snapshot.get('fact_pending_issue', 0)},
            {'label': '拒收', 'value': snapshot.get('fact_rejected', 0)},
            {'label': 'Cell 对象', 'value': snapshot.get('obj_cell', 0)},
            {'label': 'BS 对象', 'value': snapshot.get('obj_bs', 0)},
            {'label': 'LAC 对象', 'value': snapshot.get('obj_lac', 0)},
            {'label': 'Cell baseline', 'value': snapshot.get('baseline_cell', 0)},
            {'label': '基线版本', 'value': context['baseline_version']},
        ],
        'flow_summary': flow_summary,
        'notes': [
            '当前页面已切回真实 full initialization run/batch，不再使用 sample validation 结果作为初始化主语。',
            '步骤级细粒度 detail 仍未完整落表；本页保留“步骤已完成 + 明细缺失”的诚实表达。',
            '当前初始化批次的汇总快照仍来自估算写入，因此页面会显式标记为 synthetic。',
        ],
        'empty_state': None,
    }
    synthetic = synthetic_contract(
        'full_initialization_estimated_snapshot',
        subject_scope='initialization_run',
        subject_note='当前页面已切回真实 initialization run，但汇总快照仍来自估算写入，仅供参考。',
    )
    return {**payload, **synthetic}
