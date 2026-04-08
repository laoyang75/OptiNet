from __future__ import annotations

from fastapi import APIRouter

from app.api.common import (
    ISSUE_HEALTH_STATES,
    compare_label,
    compare_membership,
    fetch_all,
    fetch_one,
    now_iso,
    operator_name,
    safe_float,
    safe_int,
    ttl_cache,
)
from app.api.run_shared import (
    BASELINE_PRINCIPLE,
    FULL_BATCH_ID,
    SAMPLE_BATCH_ID,
    DATA_ORIGIN_REAL,
    _anomaly_totals,
    _baseline_refresh,
    _batch_context,
    _decision_summary,
    _real_baseline_versions,
    _record_anomaly_counts,
    _snapshot_map,
    apply_subject_contract,
)

router = APIRouter(prefix='/api/v1/runs', tags=['runs'])


@router.get('/observation-workspace')
@ttl_cache(ttl_seconds=30)
def get_observation_workspace():
    rows = fetch_all(
        """
        SELECT
          o.object_id,
          o.operator_code,
          o.tech_norm,
          o.lac,
          o.bs_id,
          o.cell_id,
          o.lifecycle_state,
          o.health_state,
          o.record_count,
          o.gps_count,
          o.device_count,
          o.active_days,
          o.gps_p90_dist_m,
          o.signal_original_ratio,
          o.existence_eligible,
          o.anchorable,
          o.baseline_eligible,
          o.created_at,
          p.center_lat,
          p.center_lon
        FROM rebuild3.obj_cell o
        LEFT JOIN rebuild3.stg_cell_profile p
          ON p.operator_code = o.operator_code
         AND p.tech_norm = o.tech_norm
         AND p.lac = o.lac
         AND p.bs_id = o.bs_id
         AND p.cell_id = o.cell_id
        WHERE o.lifecycle_state IN ('waiting', 'observing')
        ORDER BY o.record_count DESC, o.gps_count DESC, o.active_days DESC
        LIMIT 24
        """
    )

    cards = []
    reasons = {'existence': 0, 'anchor': 0, 'baseline': 0, 'issue': 0}
    waiting_count = 0
    observing_count = 0
    near_anchor = 0
    recommend_issue = 0
    sample_decisions = _decision_summary('rebuild3_sample_meta', SAMPLE_BATCH_ID).get('lifecycle_distribution', {})
    full_decisions = _decision_summary('rebuild3_meta', FULL_BATCH_ID).get('lifecycle_distribution', {})

    for row in rows:
        record_count = safe_int(row['record_count'])
        gps_count = safe_int(row['gps_count'])
        device_count = safe_int(row['device_count'])
        active_days = safe_int(row['active_days'])
        p90 = safe_float(row['gps_p90_dist_m'])
        signal_ratio = safe_float(row['signal_original_ratio'])
        existence_progress = min(100, round((min(record_count / 5, 1) + min(device_count / 1, 1) + min(active_days / 1, 1)) / 3 * 100))
        anchor_progress = min(100, round((min(gps_count / 10, 1) + min(device_count / 2, 1) + min(active_days / 1, 1) + min((1500 / p90) if p90 else 1, 1)) / 4 * 100))
        baseline_progress = min(100, round((min(gps_count / 20, 1) + min(device_count / 2, 1) + min(active_days / 3, 1) + min(signal_ratio / 0.5 if signal_ratio else 0, 1)) / 4 * 100))

        if row['lifecycle_state'] == 'waiting':
            waiting_count += 1
        if row['lifecycle_state'] == 'observing':
            observing_count += 1
        if anchor_progress >= 80 and not row['anchorable']:
            near_anchor += 1

        if row['health_state'] in ISSUE_HEALTH_STATES or p90 > 1500:
            suggested_action = '建议转问题池'
            reasons['issue'] += 1
            recommend_issue += 1
            trend = 'risk'
        elif not row['existence_eligible']:
            suggested_action = '继续积累存在资格'
            reasons['existence'] += 1
            trend = 'new'
        elif not row['anchorable']:
            suggested_action = '继续观察，推进锚点资格'
            reasons['anchor'] += 1
            trend = 'approaching' if anchor_progress >= 70 else 'steady'
        elif not row['baseline_eligible']:
            suggested_action = '继续观察，推进基线资格'
            reasons['baseline'] += 1
            trend = 'approaching' if baseline_progress >= 70 else 'steady'
        else:
            suggested_action = '已满足三层资格，等待批末晋升'
            trend = 'ready'

        cards.append(
            {
                'object_id': row['object_id'],
                'object_type': 'cell',
                'title': f"{operator_name(row['operator_code'])} · {row['tech_norm']} · Cell {row['cell_id']}",
                'subtitle': f"LAC {row['lac']} · BS {row['bs_id']}",
                'lifecycle_state': row['lifecycle_state'],
                'health_state': row['health_state'],
                'existence_progress': existence_progress,
                'anchor_progress': anchor_progress,
                'baseline_progress': baseline_progress,
                'existence_details': [
                    {'label': '记录数', 'ratio': min(record_count / 5, 1), 'display': f'{record_count}/5'},
                    {'label': '设备数', 'ratio': min(device_count / 1, 1), 'display': f'{device_count}/1'},
                    {'label': '活跃天数', 'ratio': min(active_days / 1, 1), 'display': f'{active_days}/1天'},
                ],
                'anchor_details': [
                    {'label': 'GPS 点数', 'ratio': min(gps_count / 10, 1), 'display': f'{gps_count}/10'},
                    {'label': '设备数', 'ratio': min(device_count / 2, 1), 'display': f'{device_count}/2'},
                    {'label': '活跃天数', 'ratio': min(active_days / 1, 1), 'display': f'{active_days}/1天'},
                    {'label': 'P90 半径', 'ratio': min((1500 / p90) if p90 else 1, 1), 'display': f'{p90:.1f}m / 1500m' if p90 else '—'},
                ],
                'baseline_details': [
                    {'label': 'GPS 点数', 'ratio': min(gps_count / 20, 1), 'display': f'{gps_count}/20'},
                    {'label': '设备数', 'ratio': min(device_count / 2, 1), 'display': f'{device_count}/2'},
                    {'label': '活跃天数', 'ratio': min(active_days / 3, 1), 'display': f'{active_days}/3天'},
                    {'label': '信号原始率', 'ratio': min(signal_ratio / 0.5 if signal_ratio else 0, 1), 'display': f'{signal_ratio * 100:.1f}% / 50%' if signal_ratio is not None else '—'},
                ],
                'record_count': record_count,
                'gps_count': gps_count,
                'device_count': device_count,
                'active_days': active_days,
                'p90_m': p90,
                'signal_original_ratio': signal_ratio,
                'trend': trend,
                'trend_values': f"记录 {record_count} · GPS {gps_count} · 活跃 {active_days} 天",
                'suggested_action': suggested_action,
                'centroid_lat': safe_float(row.get('center_lat')) if row.get('center_lat') is not None else None,
                'centroid_lon': safe_float(row.get('center_lon')) if row.get('center_lon') is not None else None,
                'first_seen': str(row.get('created_at')).split(' ')[0] if row.get('created_at') else None,
                'stalled_batches': 0 if trend in {'new', 'ready', 'approaching'} else 1,
                'missing_layer': 'existence' if not row['existence_eligible'] else ('anchorable' if not row['anchorable'] else ('baseline' if not row['baseline_eligible'] else 'complete')),
            }
        )

    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'summary': {
            'total_candidates': len(cards),
            'waiting_count': waiting_count,
            'observing_count': observing_count,
            'near_anchor_count': near_anchor,
            'recommend_issue_count': recommend_issue,
            'waiting_batch_delta': 0,
            'observing_batch_delta': 0,
            'waiting_vs_delta': waiting_count - safe_int(sample_decisions.get('cell:waiting')),
            'observing_vs_delta': observing_count - safe_int(sample_decisions.get('cell:observing')),
            'promoted_count': sum(1 for card in cards if card['baseline_progress'] >= 100),
            'rejected_count': 0,
            'backlog_warning': f"建议转问题对象 {recommend_issue} 个" if recommend_issue else '',
        },
        'cards': cards,
        'backlog_analysis': [
            {'label': '存在资格不足', 'type': 'existence', 'count': reasons['existence']},
            {'label': '锚点资格不足', 'type': 'anchorable', 'count': reasons['anchor']},
            {'label': '基线资格不足', 'type': 'baseline', 'count': reasons['baseline']},
            {'label': '建议转问题', 'type': 'issue', 'count': reasons['issue']},
        ],
        'backlog_trend': [
            {'label': '样本', 'value': safe_int(sample_decisions.get('cell:observing'))},
            {'label': '正式', 'value': safe_int(full_decisions.get('cell:observing'))},
        ],
        'note': '当前正式库仅有一批初始化结果，因此推进趋势采用资格接近度派生，而非真实多批增量斜率。',
    }


@router.get('/anomaly-workspace')
@ttl_cache(ttl_seconds=30)
def get_anomaly_workspace():
    object_rows = fetch_all(
        """
        SELECT 'cell' AS object_type, object_id, operator_code, tech_norm, lac, bs_id, cell_id,
               health_state, batch_id, record_count, anchorable, baseline_eligible,
               0::bigint AS impact_count
        FROM rebuild3.obj_cell
        WHERE health_state IN ('gps_bias', 'collision_suspect', 'collision_confirmed', 'dynamic', 'migration_suspect')
        UNION ALL
        SELECT 'bs' AS object_type, object_id, operator_code, tech_norm, lac, bs_id, NULL::bigint AS cell_id,
               health_state, batch_id, record_count, anchorable, baseline_eligible,
               active_cell_count AS impact_count
        FROM rebuild3.obj_bs
        WHERE health_state IN ('gps_bias', 'collision_suspect', 'collision_confirmed', 'dynamic', 'migration_suspect')
        ORDER BY record_count DESC
        LIMIT 30
        """
    )

    def severity(health_state: str) -> str:
        if health_state in {'collision_confirmed', 'migration_suspect'}:
            return 'high'
        if health_state in {'gps_bias', 'dynamic'}:
            return 'medium'
        return 'low'

    object_stats = fetch_all(
        """
        SELECT anomaly_name, sum(coalesce(object_count, 0))::bigint AS object_count
        FROM rebuild3_meta.batch_anomaly_summary
        WHERE batch_id = %(batch_id)s
          AND anomaly_name IN ('gps_bias', 'collision_suspect', 'collision_confirmed', 'dynamic')
        GROUP BY anomaly_name
        ORDER BY object_count DESC
        """,
        {'batch_id': FULL_BATCH_ID},
    )

    record_counts = _record_anomaly_counts('rebuild3_meta', FULL_BATCH_ID)

    record_rows = [
        {
            'anomaly_type': 'normal_spread',
            'count': record_counts['normal_spread'],
            'batch_new': record_counts['normal_spread'],
            'route': 'fact_governed',
            'anchor_impact': '不影响锚点',
            'baseline_impact': '解释层降级',
            'description': 'GPS 噪声记录保留到 governed，并在画像里降级解释。',
            'type_class': 'normal-spread',
        },
        {
            'anomaly_type': 'single_large',
            'count': record_counts['single_large'],
            'batch_new': record_counts['single_large'],
            'route': 'fact_governed',
            'anchor_impact': '有条件影响',
            'baseline_impact': '由质量标签解释',
            'description': '面积大对象保留事实，但通过质量标签暴露风险。',
            'type_class': 'single-large',
        },
        {
            'anomaly_type': '结构不合规',
            'count': record_counts['structural_rejected'],
            'batch_new': record_counts['structural_rejected'],
            'route': 'fact_rejected',
            'anchor_impact': '不参与',
            'baseline_impact': '不参与',
            'description': '主键或结构异常直接留痕拒收。',
            'type_class': 'structural',
        },
        {
            'anomaly_type': 'GPS 缺失回填',
            'count': record_counts['gps_fill'],
            'batch_new': record_counts['gps_fill'],
            'route': 'fact_governed',
            'anchor_impact': '不影响锚点判断',
            'baseline_impact': '由 gps_source 解释',
            'description': 'GPS 来源不是原始值时，在 facts 中显式标注来源。',
            'type_class': 'gps-fill',
        },
        {
            'anomaly_type': 'donor 信号补齐',
            'count': record_counts['signal_fill'],
            'batch_new': record_counts['signal_fill'],
            'route': 'fact_governed',
            'anchor_impact': '不影响',
            'baseline_impact': '由 signal_source 解释',
            'description': '信号值补齐后继续进入 governed，但解释层需可见。',
            'type_class': 'signal-fill',
        },
    ]

    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'object_tab': {
            'stats': [{'label': row['anomaly_name'], 'count': safe_int(row['object_count'])} for row in object_stats],
            'batch_new': len(object_rows),
            'rows': [
                {
                    'object_type': row['object_type'],
                    'object_id': row['object_id'],
                    'title': f"{operator_name(row['operator_code'])} · {row['tech_norm']} · {row['object_type'].upper()}",
                    'subtitle': f"LAC {row['lac']} · BS {row['bs_id']}" + (f" · Cell {row['cell_id']}" if row.get('cell_id') else ''),
                    'health_state': row['health_state'],
                    'severity': severity(row['health_state']),
                    'fact_route': 'fact_pending_issue',
                    'anchorable': bool(row['anchorable']),
                    'baseline_eligible': bool(row['baseline_eligible']),
                    'impact_count': safe_int(row['impact_count']),
                    'batch_id': row['batch_id'],
                    'evidence_trend': 'worsening' if row['health_state'] in {'collision_confirmed', 'migration_suspect'} else 'stable',
                    'collision_group': f"碰撞组 {row['bs_id']}" if row['health_state'].startswith('collision') else '无碰撞组',
                    'affected_cells': safe_int(row['impact_count']) if row['object_type'] == 'bs' else 1,
                    'fact_explanation': '对象级异常统一进入 fact_pending_issue，并禁止误入 governed。',
                }
                for row in object_rows
            ],
        },
        'record_tab': {
            'batch_new': sum(row['count'] for row in record_rows),
            'rows': record_rows,
            'rules': [
                '记录级异常不直接改变对象 lifecycle_state，但必须在事实层保留去向与来源。',
                '对象级异常统一进入 fact_pending_issue，并禁止误入 governed。',
            ],
        },
    }


@router.get('/baseline-profile')
@ttl_cache(ttl_seconds=30)
def get_baseline_profile():
    history = _real_baseline_versions()
    if not history:
        return apply_subject_contract(
            {
                'status': 'ok',
                'generated_at': now_iso(),
                'context': {},
                'current_version': None,
                'previous_version': None,
                'trigger_detail': {},
                'coverage_cards': [],
                'quality': {},
                'risk_factors': [],
                'version_history': [],
                'diff_samples': [],
                'diff_notice': '尚未生成正式 baseline，请先完成初始化。',
                'empty_state': {
                    'title': '尚未生成正式 baseline',
                    'description': '当前正式库尚未产出 baseline 版本。初始化完成后页面会自动切回正式版本视角。',
                },
            },
            data_origin=DATA_ORIGIN_REAL,
            subject_scope='baseline_version',
            subject_note='当前正式库尚未产出 baseline 版本。',
        )

    current_version = history[0]
    previous_version = history[1] if len(history) > 1 else None
    context = _batch_context('rebuild3_meta', current_version['batch_id'], subject_scope='baseline_version')
    refresh = _baseline_refresh('rebuild3_meta', current_version['batch_id'])
    full_snapshot = _snapshot_map('rebuild3_meta', current_version['batch_id'])
    anomaly_totals = _anomaly_totals('rebuild3_meta', current_version['batch_id'])

    baseline_counts = {
        'cell': safe_int(fetch_one('SELECT count(*) AS cnt FROM rebuild3.baseline_cell').get('cnt')),
        'bs': safe_int(fetch_one('SELECT count(*) AS cnt FROM rebuild3.baseline_bs').get('cnt')),
        'lac': safe_int(fetch_one('SELECT count(*) AS cnt FROM rebuild3.baseline_lac').get('cnt')),
    }
    quality = fetch_one(
        """
        SELECT
          avg(gps_original_ratio)::numeric(10,4) AS gps_ratio,
          avg(signal_original_ratio)::numeric(10,4) AS signal_ratio,
          avg(gps_p90_dist_m)::numeric(10,2) AS cell_p90
        FROM rebuild3.obj_cell
        WHERE baseline_eligible
        """
    )
    gps_ratio = safe_float(quality.get('gps_ratio'))
    signal_ratio = safe_float(quality.get('signal_ratio'))
    stability_score = 88
    if gps_ratio < 0.7:
        stability_score -= 8
    if signal_ratio < 0.6:
        stability_score -= 5
    stability_score = max(60, stability_score)

    payload = {
        'status': 'ok',
        'generated_at': now_iso(),
        'context': context,
        'current_version': {
            'baseline_version': current_version['baseline_version'],
            'run_id': current_version['run_id'],
            'batch_id': current_version['batch_id'],
            'rule_set_version': current_version['rule_set_version'],
            'refresh_reason': current_version['refresh_reason'],
            'created_at': current_version['created_at'],
            'triggered': True,
            'object_count': safe_int(current_version['object_count']),
        },
        'previous_version': (
            {
                'baseline_version': previous_version['baseline_version'],
                'run_id': previous_version['run_id'],
                'batch_id': previous_version['batch_id'],
                'rule_set_version': previous_version['rule_set_version'],
                'refresh_reason': previous_version['refresh_reason'],
                'created_at': previous_version['created_at'],
                'object_count': safe_int(previous_version['object_count']),
            }
            if previous_version
            else None
        ),
        'trigger_detail': {
            'condition': '首版全量 baseline 生成' if refresh and refresh.get('refresh_reason') == 'full_initial_baseline' else current_version['refresh_reason'],
            'type': '批次触发' if refresh and refresh.get('triggered') else '版本生成',
            'waiting_contribution': full_snapshot.get('fact_pending_observation', 0),
            'anomaly_contribution': anomaly_totals['object_total'],
        },
        'coverage_cards': [
            {'label': 'Cell baseline', 'value': baseline_counts['cell']},
            {'label': 'BS baseline', 'value': baseline_counts['bs']},
            {'label': 'LAC baseline', 'value': baseline_counts['lac']},
            {'label': 'Cell 平均 P90', 'value': safe_float(quality.get('cell_p90'))},
        ],
        'quality': {
            'gps_original_ratio': gps_ratio,
            'signal_original_ratio': signal_ratio,
            'stability_score': stability_score,
            'baseline_principle': BASELINE_PRINCIPLE,
        },
        'risk_factors': [
            '当前页面只回答正式 baseline 版本，不再用 rebuild2 或 sample validation 代替版本差异。',
            '当前覆盖与质量指标直接来自 rebuild3 正式 baseline 表。',
            '暂无上一版 baseline 时，差异区会进入诚实空状态。',
        ],
        'version_history': [
            {
                'scope': '正式',
                'baseline_version': row['baseline_version'],
                'run_id': row['run_id'],
                'batch_id': row['batch_id'],
                'rule_set_version': row['rule_set_version'],
                'refresh_reason': row['refresh_reason'],
                'object_count': safe_int(row['object_count']),
                'created_at': row['created_at'],
            }
            for row in history
        ],
        'diff_samples': [],
        'diff_notice': (
            '暂无上一版 baseline，无法比较版本差异。'
            if not previous_version
            else '上一版 baseline 已登记，但当前尚未接入实时版本差异读模型。'
        ),
        'empty_state': None,
    }
    return apply_subject_contract(
        payload,
        data_origin=DATA_ORIGIN_REAL,
        subject_scope='baseline_version',
        subject_note='当前页面仅展示正式 baseline 版本，不再把 rebuild2 对照结果伪装成版本差异。',
    )

