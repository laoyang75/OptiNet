from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.api.common import fetch_all, format_window, safe_float, safe_int, ttl_cache
from app.api.run_shared import DATA_ORIGIN_REAL, _batch_context, _batch_contract, _snapshot_rows, apply_subject_contract

STAGE_META: dict[str, dict[str, Any]] = {
    'meta': {'label': '批次上下文', 'order': 0},
    'input': {'label': '输入与标准化', 'order': 10},
    'matching': {'label': '对象与基线匹配', 'order': 20},
    'routing': {'label': '四分流结果（本批次事件分配）', 'order': 30},
    'evidence': {'label': '证据累计与对象更新', 'order': 40},
    'decision': {'label': '批末统一决策', 'order': 50},
    'anomaly': {'label': '异常检测', 'order': 60},
    'system': {'label': '系统累计状态（批次结束后）', 'order': 70},
    'objects': {'label': '系统累计状态（批次结束后）', 'order': 70},
    'baseline': {'label': '基线覆盖 / 输出状态', 'order': 80},
}

KNOWN_METRICS: list[dict[str, Any]] = [
    {'metric_name': 'batch_input_rows', 'stage_name': 'input', 'label': '批次输入', 'subtitle': '原始记录', 'order': 1, 'percent_base': None},
    {'metric_name': 'fact_standardized', 'stage_name': 'input', 'label': '标准化事件', 'subtitle': 'fact_standardized', 'order': 2, 'percent_base': 'batch_input_rows'},
    {'metric_name': 'fact_governed', 'stage_name': 'routing', 'label': '已治理事实', 'subtitle': 'fact_governed', 'order': 11, 'percent_base': 'fact_standardized'},
    {'metric_name': 'fact_pending_observation', 'stage_name': 'routing', 'label': '观察事实', 'subtitle': 'fact_pending_observation', 'order': 12, 'percent_base': 'fact_standardized'},
    {'metric_name': 'fact_pending_issue', 'stage_name': 'routing', 'label': '问题事实', 'subtitle': 'fact_pending_issue', 'order': 13, 'percent_base': 'fact_standardized'},
    {'metric_name': 'fact_rejected', 'stage_name': 'routing', 'label': '拒收事实', 'subtitle': 'fact_rejected', 'order': 14, 'percent_base': 'fact_standardized'},
    {'metric_name': 'obj_cell', 'stage_name': 'objects', 'label': 'Cell 对象', 'subtitle': '累计对象', 'order': 21, 'percent_base': None},
    {'metric_name': 'obj_bs', 'stage_name': 'objects', 'label': 'BS 对象', 'subtitle': '累计对象', 'order': 22, 'percent_base': None},
    {'metric_name': 'obj_lac', 'stage_name': 'objects', 'label': 'LAC 对象', 'subtitle': '累计对象', 'order': 23, 'percent_base': None},
    {'metric_name': 'baseline_cell', 'stage_name': 'baseline', 'label': 'Cell baseline', 'subtitle': '冻结基线', 'order': 31, 'percent_base': None},
    {'metric_name': 'baseline_bs', 'stage_name': 'baseline', 'label': 'BS baseline', 'subtitle': '冻结基线', 'order': 32, 'percent_base': None},
    {'metric_name': 'baseline_lac', 'stage_name': 'baseline', 'label': 'LAC baseline', 'subtitle': '冻结基线', 'order': 33, 'percent_base': None},
]

KNOWN_METRIC_MAP = {item['metric_name']: item for item in KNOWN_METRICS}
INIT_BATCH_TYPES = ('init', 'initialization', 'full_init', 'sample_init')
COLUMN_SPECS = [
    {'id': 'init', 'label': '初始化完成后', 'badge': '固定', 'tone': 'init'},
    {'id': 'time_a', 'label': '时间点 A', 'badge': '自定义 1', 'tone': 't1'},
    {'id': 'time_b', 'label': '时间点 B', 'badge': '自定义 2', 'tone': 't2'},
]


def _format_scalar(value: Any) -> str:
    if value is None or value == '':
        return '—'
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f'{value:,}'
    if isinstance(value, float):
        if value.is_integer():
            return f'{int(value):,}'
        return f'{value:,.2f}'
    return str(value)


def _coerce_numeric(value: Any) -> int | float | None:
    if value is None or value == '':
        return None
    number = safe_float(value, default=float('nan'))
    if number != number:
        return None
    if float(number).is_integer():
        return int(number)
    return number


def _short_snapshot_time(value: Any) -> str:
    if not value:
        return '未记录快照时间'
    return str(value)[:16].replace('T', ' ')


def _scenario_label(row: dict[str, Any]) -> str:
    scenario_key = str(row.get('scenario_key') or '').strip()
    smoke_prefix = '[SMOKE] ' if 'SMOKE' in scenario_key.upper() else ''
    if scenario_key:
        return f"{smoke_prefix}{scenario_key}"
    if row.get('scenario_label'):
        return f"{smoke_prefix}{str(row['scenario_label']).replace('_', ' ')}".strip()
    if row.get('note'):
        return f"{smoke_prefix}{str(row['note'])}".strip()
    return f"{smoke_prefix}{str(row['run_type']).replace('_', ' ')}".strip()


@ttl_cache(ttl_seconds=30)
def _run_catalog() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
          r.run_id,
          r.run_type,
          r.status,
          r.window_start,
          r.window_end,
          r.contract_version,
          r.rule_set_version,
          r.baseline_version,
          r.note,
          r.scenario_key,
          r.scenario_label,
          r.init_days,
          r.step_hours,
          r.snapshot_source,
          r.created_at,
          count(*) FILTER (WHERE b.status = 'completed')::bigint AS completed_batch_count,
          count(*)::bigint AS batch_count,
          max(coalesce(ss.snapshot_recorded_at, b.created_at)) AS last_snapshot_time
        FROM rebuild3_meta.run r
        LEFT JOIN rebuild3_meta.batch b
          ON b.run_id = r.run_id
        LEFT JOIN (
          SELECT batch_id, max(created_at) AS snapshot_recorded_at
          FROM rebuild3_meta.batch_snapshot
          GROUP BY batch_id
        ) ss
          ON ss.batch_id = b.batch_id
        WHERE r.run_type = 'scenario_replay'
        GROUP BY r.run_id, r.run_type, r.status, r.window_start, r.window_end,
                 r.contract_version, r.rule_set_version, r.baseline_version, r.note,
                 r.scenario_key, r.scenario_label, r.init_days, r.step_hours, r.snapshot_source,
                 r.created_at
        HAVING count(*) FILTER (WHERE b.status = 'completed') > 0
        ORDER BY max(coalesce(ss.snapshot_recorded_at, b.created_at)) DESC NULLS LAST,
                 r.created_at DESC,
                 r.run_id DESC
        """
    )
    catalog: list[dict[str, Any]] = []
    for row in rows:
        contract = _batch_contract(
            'rebuild3_meta',
            {
                'run_type': row['run_type'],
                'batch_type': 'scenario_roll_2h',
                'scenario_key': row.get('scenario_key'),
            },
            subject_scope='timepoint_snapshot',
        )
        catalog.append(
            {
                'run_id': row['run_id'],
                'label': _scenario_label(row),
                'subtitle': format_window(row['window_start'], row['window_end']),
                'run_type': row['run_type'],
                'status': row['status'],
                'baseline_version': row['baseline_version'],
                'rule_set_version': row['rule_set_version'],
                'contract_version': row['contract_version'],
                'note': row['note'],
                'scenario_key': row.get('scenario_key'),
                'scenario_label': row.get('scenario_label'),
                'init_days': safe_int(row.get('init_days')),
                'step_hours': safe_int(row.get('step_hours')),
                'snapshot_source': row.get('snapshot_source'),
                'batch_count': safe_int(row['batch_count']),
                'completed_batch_count': safe_int(row['completed_batch_count']),
                'last_snapshot_time': row['last_snapshot_time'],
                **contract,
            }
        )
    return catalog


@ttl_cache(ttl_seconds=30)
def _run_batches(run_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
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
          count(bs.metric_name)::bigint AS snapshot_metric_count
        FROM rebuild3_meta.batch b
        LEFT JOIN rebuild3_meta.batch_snapshot bs
          ON bs.batch_id = b.batch_id
        LEFT JOIN (
          SELECT batch_id, max(created_at) AS snapshot_recorded_at
          FROM rebuild3_meta.batch_snapshot
          GROUP BY batch_id
        ) ss
          ON ss.batch_id = b.batch_id
        WHERE b.run_id = %(run_id)s
          AND b.status = 'completed'
        GROUP BY b.batch_id, b.run_id, b.batch_type, b.status, b.window_start, b.window_end,
                 b.input_rows, b.output_rows, b.contract_version, b.rule_set_version,
                 b.baseline_version, b.is_rerun, b.rerun_source_batch, b.scenario_key,
                 b.timepoint_role, b.batch_seq, b.snapshot_at, b.created_at, ss.snapshot_recorded_at
        ORDER BY coalesce(b.batch_seq, 999999) ASC,
                 coalesce(b.snapshot_at, b.window_end, b.created_at) ASC,
                 coalesce(ss.snapshot_recorded_at, b.created_at) ASC,
                 b.batch_id ASC
        """,
        {'run_id': run_id},
    )
    batches: list[dict[str, Any]] = []
    for row in rows:
        batches.append(
            {
                'batch_id': row['batch_id'],
                'run_id': row['run_id'],
                'batch_type': row['batch_type'],
                'status': row['status'],
                'window_start': row['window_start'],
                'window_end': row['window_end'],
                'window': format_window(row['window_start'], row['window_end']),
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
                'snapshot_metric_count': safe_int(row['snapshot_metric_count']),
            }
        )
    return batches


def _is_init_batch(batch: dict[str, Any]) -> bool:
    if batch.get('timepoint_role') == 'init':
        return True
    batch_type = (batch.get('batch_type') or '').lower()
    return any(token in batch_type for token in INIT_BATCH_TYPES)


def _option_label(batch: dict[str, Any]) -> str:
    suffix = ' ⟳重跑' if batch.get('is_rerun') else ''
    if batch.get('timepoint_role') == 'init':
        return f"初始化批次{suffix}"
    if batch.get('batch_seq'):
        return f"第 {batch['batch_seq']} 个 2 小时快照{suffix}"
    return f"{batch['batch_id']}{suffix}"


def _build_column(spec: dict[str, str], batch_id: str | None) -> dict[str, Any]:
    if not batch_id:
        return {
            **spec,
            'available': False,
            'context': {},
            'values': {},
            'snapshot_rows': [],
            'header_note': '暂无可选批次',
        }

    context = _batch_context('rebuild3_meta', batch_id)
    snapshot_rows = _snapshot_rows('rebuild3_meta', batch_id)
    values = {row['metric_name']: _coerce_numeric(row['metric_value']) for row in snapshot_rows}
    if context.get('input_rows'):
        values['batch_input_rows'] = context['input_rows']

    header_parts = [_option_label(context)]
    if context.get('snapshot_recorded_at'):
        header_parts.append(_short_snapshot_time(context['snapshot_recorded_at']))

    return {
        **spec,
        'available': True,
        'context': context,
        'values': values,
        'snapshot_rows': snapshot_rows,
        'header_note': ' · '.join(header_parts),
    }


def _metric_definition(metric_name: str, stage_name: str) -> dict[str, Any]:
    known = KNOWN_METRIC_MAP.get(metric_name)
    if known:
        return known
    return {
        'metric_name': metric_name,
        'stage_name': stage_name,
        'label': metric_name.replace('_', ' '),
        'subtitle': metric_name,
        'order': 999,
        'percent_base': None,
    }


def _value_percent(column: dict[str, Any], metric_def: dict[str, Any], value: int | float | None) -> str:
    base_key = metric_def.get('percent_base')
    if not base_key or value is None:
        return ''
    base_value = _coerce_numeric(column['values'].get(base_key))
    if base_value in (None, 0):
        return ''
    return f'{(safe_float(value) / safe_float(base_value)) * 100:.1f}%'


def _stage_groups(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    present_metrics: dict[str, dict[str, Any]] = {}
    for metric in KNOWN_METRICS:
        if any(metric['metric_name'] in column['values'] for column in columns if column['available']):
            present_metrics[metric['metric_name']] = metric

    for column in columns:
        if not column['available']:
            continue
        for row in column['snapshot_rows']:
            metric_name = row['metric_name']
            present_metrics.setdefault(metric_name, _metric_definition(metric_name, row['stage_name']))

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for metric_name, metric_def in present_metrics.items():
        grouped[metric_def['stage_name']].append(metric_def)

    groups: list[dict[str, Any]] = []
    for stage_name, metrics in grouped.items():
        stage_meta = STAGE_META.get(stage_name, {'label': stage_name.replace('_', ' '), 'order': 999})
        rows = []
        for metric_def in sorted(metrics, key=lambda item: (item['order'], item['label'])):
            cells = []
            has_any_value = False
            for column in columns:
                value = _coerce_numeric(column['values'].get(metric_def['metric_name'])) if column['available'] else None
                if value is not None:
                    has_any_value = True
                cells.append(
                    {
                        'value': value,
                        'display_value': _format_scalar(value),
                        'percent': _value_percent(column, metric_def, value),
                        'available': column['available'],
                    }
                )
            if has_any_value:
                rows.append(
                    {
                        'metric_name': metric_def['metric_name'],
                        'label': metric_def['label'],
                        'subtitle': metric_def['subtitle'],
                        'cells': cells,
                    }
                )
        if rows:
            groups.append(
                {
                    'stage_name': stage_name,
                    'label': stage_meta['label'],
                    'order': stage_meta['order'],
                    'rows': rows,
                }
            )

    return sorted(groups, key=lambda item: (item['order'], item['label']))


@ttl_cache(ttl_seconds=30)
def build_flow_snapshot_payload(run_id: str | None = None, time_a: str | None = None, time_b: str | None = None) -> dict[str, Any]:
    real_run_options = [item for item in _run_catalog() if item['data_origin'] == DATA_ORIGIN_REAL]
    synthetic_run_options = _run_catalog()
    evaluation_subject_note = '当前暂无真实时间点快照，已自动切换到 synthetic scenario 评估模式；仅供功能验证，不代表正式主流程结果。'

    if real_run_options:
        run_options = real_run_options
        subject_note = ''
    else:
        run_options = synthetic_run_options
        subject_note = evaluation_subject_note

    if not run_options:
        subject_note = '当前尚无真实时间点快照；scenario replay 仍为 synthetic，暂不作为正式快照展示。'
        return apply_subject_contract(
            {
                'run_options': [],
                'selected_run_id': '',
                'timepoint_options': [],
                'selected_time_a': '',
                'selected_time_b': '',
                'columns': [_build_column(spec, None) for spec in COLUMN_SPECS],
                'groups': [],
                'warnings': [subject_note],
                'storage_tables': ['rebuild3_meta.run', 'rebuild3_meta.batch', 'rebuild3_meta.batch_snapshot'],
                'empty_state': {
                    'title': '暂无真实时间点快照',
                    'description': subject_note,
                },
            },
            data_origin=DATA_ORIGIN_REAL,
            subject_scope='timepoint_snapshot',
            subject_note=subject_note,
        )

    available_run_ids = {item['run_id'] for item in run_options}
    selected_run_id = run_id if run_id in available_run_ids else run_options[0]['run_id']
    batches = _run_batches(selected_run_id)
    init_batch = next((batch for batch in batches if _is_init_batch(batch)), batches[0] if batches else None)
    timepoint_options = [batch for batch in batches if not init_batch or batch['batch_id'] != init_batch['batch_id']]

    available_time_ids = [batch['batch_id'] for batch in timepoint_options]
    selected_time_a = time_a if time_a in available_time_ids else (available_time_ids[0] if available_time_ids else '')

    if time_b in available_time_ids:
        selected_time_b = time_b
    elif len(available_time_ids) >= 2:
        selected_time_b = available_time_ids[-1]
        if selected_time_b == selected_time_a:
            selected_time_b = available_time_ids[0]
    else:
        selected_time_b = ''

    columns = [
        _build_column(COLUMN_SPECS[0], init_batch['batch_id'] if init_batch else None),
        _build_column(COLUMN_SPECS[1], selected_time_a or None),
        _build_column(COLUMN_SPECS[2], selected_time_b or None),
    ]

    warnings: list[str] = []
    if subject_note:
        warnings.append(subject_note)
    if not init_batch:
        warnings.append('当前运行场景尚未记录初始化完成批次，无法固定左侧对照列。')
    if not timepoint_options:
        warnings.append('当前运行场景只有初始化批次，尚未产出后续 2 小时快照。')
    elif len(timepoint_options) == 1:
        warnings.append('当前运行场景仅有 1 个后续时间点，时间点 B 暂不可选。')

    selected_summary = next(item for item in run_options if item['run_id'] == selected_run_id)
    return apply_subject_contract(
        {
            'run_options': run_options,
            'selected_run_id': selected_run_id,
            'timepoint_options': [
                {
                    'batch_id': batch['batch_id'],
                    'label': _option_label(batch),
                    'window': batch['window'],
                    'batch_type': batch['batch_type'],
                    'baseline_version': batch['baseline_version'],
                    'is_rerun': batch['is_rerun'],
                    'snapshot_recorded_at': batch['snapshot_recorded_at'],
                }
                for batch in timepoint_options
            ],
            'selected_time_a': selected_time_a,
            'selected_time_b': selected_time_b,
            'columns': columns,
            'groups': _stage_groups(columns),
            'warnings': warnings,
            'storage_tables': ['rebuild3_meta.run', 'rebuild3_meta.batch', 'rebuild3_meta.batch_snapshot'],
            'selected_run_summary': selected_summary,
            'empty_state': None,
        },
        data_origin=selected_summary['data_origin'],
        origin_detail=selected_summary['origin_detail'],
        subject_scope='timepoint_snapshot',
        subject_note=subject_note or selected_summary['subject_note'],
    )
