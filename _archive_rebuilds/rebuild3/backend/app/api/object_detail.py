from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.common import (
    ISSUE_HEALTH_STATES,
    compare_label,
    fetch_all,
    fetch_one,
    health_label,
    now_iso,
    safe_int,
    ttl_cache,
)
from app.api.object_common import profile_join_sql, require_object_type, select_fields, serialize_row

router = APIRouter(prefix='/api/v1/objects', tags=['objects'])


def _detail_scope_params(
    object_type: str,
    operator_code: str,
    tech_norm: str,
    lac: str,
    bs_id: int | None = None,
    cell_id: int | None = None,
) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        'operator_code': operator_code,
        'tech_norm': tech_norm,
        'lac': lac,
    }
    clauses = [
        'operator_code = %(operator_code)s',
        'tech_norm = %(tech_norm)s',
        'lac = %(lac)s',
    ]
    if object_type in {'cell', 'bs'}:
        clauses.append('bs_id = %(bs_id)s')
        params['bs_id'] = bs_id
    if object_type == 'cell':
        clauses.append('cell_id = %(cell_id)s')
        params['cell_id'] = cell_id
    return ' AND '.join(clauses), params


@ttl_cache(ttl_seconds=30)
def _fact_counts(
    object_type: str,
    operator_code: str,
    tech_norm: str,
    lac: str,
    bs_id: int | None = None,
    cell_id: int | None = None,
) -> list[dict]:
    where, params = _detail_scope_params(object_type, operator_code, tech_norm, lac, bs_id, cell_id)
    rows = fetch_all(
        f"""
        SELECT route, cnt
        FROM (
          SELECT 'fact_governed' AS route, count(*)::bigint AS cnt FROM rebuild3.fact_governed WHERE {where}
          UNION ALL
          SELECT 'fact_pending_observation' AS route, count(*)::bigint AS cnt FROM rebuild3.fact_pending_observation WHERE {where}
          UNION ALL
          SELECT 'fact_pending_issue' AS route, count(*)::bigint AS cnt FROM rebuild3.fact_pending_issue WHERE {where}
          UNION ALL
          SELECT 'fact_rejected' AS route, count(*)::bigint AS cnt FROM rebuild3.fact_rejected WHERE {where}
        ) counts
        """,
        params,
    )
    return [{'route': row['route'], 'count': safe_int(row['cnt'])} for row in rows]


@ttl_cache(ttl_seconds=30)
def _source_mixes(
    object_type: str,
    operator_code: str,
    tech_norm: str,
    lac: str,
    bs_id: int | None = None,
    cell_id: int | None = None,
) -> dict[str, list[dict]]:
    where, params = _detail_scope_params(object_type, operator_code, tech_norm, lac, bs_id, cell_id)
    rows = fetch_all(
        f"""
        WITH scoped AS MATERIALIZED (
          SELECT gps_source, signal_source
          FROM rebuild3.fact_governed
          WHERE {where}
        ),
        gps_mix AS (
          SELECT 'gps_source_mix' AS bucket, coalesce(gps_source, '<null>') AS label, count(*)::bigint AS cnt
          FROM scoped
          GROUP BY coalesce(gps_source, '<null>')
          ORDER BY cnt DESC, label ASC
          LIMIT 6
        ),
        signal_mix AS (
          SELECT 'signal_source_mix' AS bucket, coalesce(signal_source, '<null>') AS label, count(*)::bigint AS cnt
          FROM scoped
          GROUP BY coalesce(signal_source, '<null>')
          ORDER BY cnt DESC, label ASC
          LIMIT 6
        )
        SELECT bucket, label, cnt FROM gps_mix
        UNION ALL
        SELECT bucket, label, cnt FROM signal_mix
        """,
        params,
    )
    payload = {'gps_source_mix': [], 'signal_source_mix': []}
    for row in rows:
        payload[row['bucket']].append({'label': row['label'], 'count': safe_int(row['cnt'])})
    return payload


def _qualification_reasons(object_type: str, snapshot: dict) -> list[dict]:
    reasons = []
    reasons.append(
        {
            'label': '存在资格',
            'passed': snapshot['existence_eligible'],
            'items': [
                f"record_count={snapshot['record_count']}",
                f"active_days={snapshot['active_days']}",
                '对象已进入注册层' if snapshot['existence_eligible'] else '对象仍处于初始积累阶段',
            ],
        }
    )
    reasons.append(
        {
            'label': '锚点资格',
            'passed': snapshot['anchorable'],
            'items': [
                f"gps_count={snapshot['gps_count']}",
                f"health_state={health_label(snapshot['health_state'])}",
                '当前可参与空间锚点' if snapshot['anchorable'] else '当前不允许参与锚点',
            ],
        }
    )
    reasons.append(
        {
            'label': '基线资格',
            'passed': snapshot['baseline_eligible'],
            'items': [
                f"gps_original_ratio={snapshot.get('gps_original_ratio', 0):.2f}",
                f"signal_original_ratio={snapshot.get('signal_original_ratio', 0):.2f}",
                '当前可进入 baseline / profile' if snapshot['baseline_eligible'] else '当前未满足 baseline 资格',
            ],
        }
    )
    if object_type == 'lac' and snapshot.get('region_quality_label'):
        reasons.append(
            {
                'label': '区域质量标签',
                'passed': snapshot['health_state'] == 'healthy',
                'items': [snapshot['region_quality_label']],
            }
        )
    return reasons


@router.get('/detail')
@ttl_cache(ttl_seconds=30)
def get_object_detail(object_type: str = Query(default='cell'), object_id: str = Query(...)):
    config = require_object_type(object_type)
    row = fetch_one(
        f"""
        SELECT {select_fields(object_type, include_total=False)}
        FROM {config['table']} o
        {profile_join_sql(object_type)}
        WHERE o.object_id = %(object_id)s
        LIMIT 1
        """,
        {'object_id': object_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail='未找到对象')
    snapshot = serialize_row(object_type, row)

    history = fetch_all(
        """
        SELECT changed_at, changed_reason, lifecycle_state, health_state, anchorable, baseline_eligible
        FROM rebuild3.obj_state_history
        WHERE object_type = %(object_type)s AND object_id = %(object_id)s
        ORDER BY changed_at DESC
        LIMIT 12
        """,
        {'object_type': object_type, 'object_id': object_id},
    )
    facts = _fact_counts(
        object_type,
        snapshot['operator_code'],
        snapshot['tech_norm'],
        snapshot['lac'],
        snapshot.get('bs_id'),
        snapshot.get('cell_id'),
    )
    mixes = _source_mixes(
        object_type,
        snapshot['operator_code'],
        snapshot['tech_norm'],
        snapshot['lac'],
        snapshot.get('bs_id'),
        snapshot.get('cell_id'),
    )
    compare_context = {
        'membership': snapshot['compare_membership'],
        'membership_label': compare_label(snapshot['compare_membership']),
        'r2_health_state': row.get('r2_health_state'),
        'r3_health_state': snapshot['health_state'],
        'r2_baseline_eligible': bool(row.get('r2_baseline_eligible')),
        'r3_baseline_eligible': snapshot['baseline_eligible'],
        'explanation': '若两侧 baseline 资格不同，则优先以对象自身状态与资格矩阵解释差异。',
    }

    if object_type == 'cell':
        downstream = fetch_one(
            """
            SELECT
              count(*)::bigint AS sibling_count,
              count(*) FILTER (WHERE lifecycle_state = 'active')::bigint AS sibling_active_count,
              count(*) FILTER (WHERE baseline_eligible)::bigint AS sibling_baseline_count
            FROM rebuild3.obj_cell
            WHERE bs_id = %(bs_id)s AND lac = %(lac)s AND tech_norm = %(tech_norm)s AND operator_code = %(operator_code)s
            """,
            snapshot,
        )
        parent = fetch_one('SELECT parent_bs_object_id FROM rebuild3.obj_cell WHERE object_id = %(object_id)s', {'object_id': object_id})
        related = fetch_one(
            """
            SELECT b.object_id AS bs_object_id, b.health_state AS bs_health_state,
                   l.object_id AS lac_object_id, l.health_state AS lac_health_state
            FROM rebuild3.obj_bs b
            LEFT JOIN rebuild3.obj_lac l ON l.object_id = b.parent_lac_object_id
            WHERE b.object_id = %(parent_bs_object_id)s
            """,
            {'parent_bs_object_id': parent.get('parent_bs_object_id')},
        )
        downstream_payload = {
            'bs_object_id': related.get('bs_object_id'),
            'bs_health_state': related.get('bs_health_state'),
            'lac_object_id': related.get('lac_object_id'),
            'lac_health_state': related.get('lac_health_state'),
            'sibling_count': safe_int(downstream.get('sibling_count')),
            'sibling_active_count': safe_int(downstream.get('sibling_active_count')),
            'sibling_baseline_count': safe_int(downstream.get('sibling_baseline_count')),
        }
    elif object_type == 'bs':
        downstream_payload = {
            'child_cell_count': safe_int(snapshot.get('cell_count')),
            'active_child_cell_count': safe_int(snapshot.get('active_cell_count')),
            'lac_object_id': fetch_one(
                'SELECT parent_lac_object_id FROM rebuild3.obj_bs WHERE object_id = %(object_id)s',
                {'object_id': object_id},
            ).get('parent_lac_object_id'),
        }
    else:
        downstream_payload = {
            'child_bs_count': safe_int(snapshot.get('bs_count')),
            'active_child_bs_count': safe_int(snapshot.get('active_bs_count')),
            'child_cell_count': safe_int(snapshot.get('cell_count')),
        }

    anomalies = []
    if snapshot['health_state'] in ISSUE_HEALTH_STATES:
        anomalies.append(
            {
                'type': snapshot['health_state'],
                'severity': 'high' if snapshot['health_state'] in {'collision_confirmed', 'migration_suspect'} else 'medium',
                'detail': f"当前对象 health_state={snapshot['health_state']}。",
            }
        )
    for tag in row.get('anomaly_tags') or []:
        anomalies.append({'type': tag, 'severity': 'info', 'detail': '记录级标签或画像解释层标签。'})

    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'object_type': object_type,
        'snapshot': snapshot,
        'facts': facts,
        'history': [
            {
                'changed_at': item['changed_at'],
                'changed_reason': item['changed_reason'],
                'lifecycle_state': item['lifecycle_state'],
                'health_state': item['health_state'],
                'anchorable': bool(item['anchorable']),
                'baseline_eligible': bool(item['baseline_eligible']),
            }
            for item in history
        ],
        'gps_source_mix': mixes['gps_source_mix'],
        'signal_source_mix': mixes['signal_source_mix'],
        'qualification_reasons': _qualification_reasons(object_type, snapshot),
        'compare_context': compare_context,
        'anomalies': anomalies,
        'downstream': downstream_payload,
        'notes': [
            '对象详情页统一显示 lifecycle_state、health_state、资格与 compare 上下文。',
            '旧分类与旧可信度只保留在解释层，不再回到主状态。',
        ],
    }
