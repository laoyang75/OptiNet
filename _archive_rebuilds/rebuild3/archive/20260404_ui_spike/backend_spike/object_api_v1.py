from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from app.core.database import get_conn

router = APIRouter(prefix='/api/v1/objects', tags=['objects'])

BEIJING_BBOX = {
    'lon_min': 115.0,
    'lon_max': 117.5,
    'lat_min': 39.0,
    'lat_max': 41.0,
}
CHINA_BBOX = {
    'lon_min': 73.0,
    'lon_max': 135.0,
    'lat_min': 3.0,
    'lat_max': 54.0,
}
OPERATOR_NAME_MAP = {
    '46000': '中国移动',
    '46001': '中国联通',
    '46011': '中国电信',
    '46015': '中国广电',
}
ISSUE_HEALTH_STATES = {'collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias', 'migration_suspect'}
CELL_SORT_COLUMNS = {
    'record_count': 'record_count',
    'active_days': 'active_days',
    'device_count': 'device_count',
    'gps_p90_dist_m': 'gps_p90_dist_m',
    'cell_id': 'cell_id',
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _fetch_all(conn, sql: str, params: dict | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params or {})
        return [dict(row) for row in cur.fetchall()]


def _fetch_one(conn, sql: str, params: dict | None = None) -> dict:
    rows = _fetch_all(conn, sql, params)
    return rows[0] if rows else {}


def _operator_name(operator_code: str | None) -> str:
    if not operator_code:
        return '未知运营商'
    return OPERATOR_NAME_MAP.get(operator_code, operator_code)


def _legacy_quality_label(raw_value: str | None) -> str:
    mapping = {
        'Usable': '高',
        'Risk': '中',
        'Unusable': '低',
    }
    return mapping.get(raw_value or '', '无')


def _rule_state(passed: bool) -> str:
    return 'passed' if passed else 'blocked'


def _compare_membership(row: dict) -> str:
    r3_baseline = bool(row.get('baseline_eligible'))
    r2_baseline = bool(row.get('r2_baseline_eligible'))
    if r3_baseline and not r2_baseline:
        return 'r3_only'
    if r2_baseline and not r3_baseline:
        return 'r2_only'
    return 'aligned'


def _is_outside_bbox(lon: float | None, lat: float | None, bbox: dict[str, float]) -> bool:
    if lon is None or lat is None:
        return False
    return not (
        bbox['lon_min'] <= float(lon) <= bbox['lon_max']
        and bbox['lat_min'] <= float(lat) <= bbox['lat_max']
    )


def _base_change_log() -> list[dict]:
    return [
        {
            'label': 'Cell baseline 不再直接继承 legacy gps_anomaly 前置硬门槛',
            'effect': '当前全量对比里，新增 baseline Cell 为 2,274 个。',
            'impact_metric': '+2274 Cell',
            'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:287',
        },
        {
            'label': '北京 bbox 没有在 rebuild3 Cell 基线资格里写成长期硬规则',
            'effect': '当前新增 baseline Cell 里，只有 2 个落在北京研究框外。',
            'impact_metric': '框外 2 个',
            'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:114',
        },
        {
            'label': '2G / 3G 没有在 rebuild3 Cell 对象构建阶段显式写死过滤',
            'effect': '但本次 baseline 增量实测只出现 4G / 5G，没有 2G / 3G。',
            'impact_metric': '2G/3G 增量 0',
            'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:147',
        },
        {
            'label': 'BS 资格改成严格来源于子 Cell',
            'effect': '修复了“无合格子 Cell 的 BS 仍被判可用”的结构性错误。',
            'impact_metric': '异常归零',
            'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:342',
        },
    ]


def _build_cell_transparency_snapshot(error_message: str | None = None) -> dict:
    return {
        'status': 'snapshot',
        'generated_at': _now_iso(),
        'data_origin': 'snapshot',
        'error_message': error_message,
        'headline': {
            'title': 'Cell 规则可见性',
            'subtitle': '把研究期过滤、Cell 资格门槛、legacy 差异和 BS 级联修复同时摆到台面上。',
        },
        'change_log': _base_change_log(),
        'source_scope': [
            {
                'label': '研究期源表',
                'value': '仍是北京一周 GPS / LAC 明细表',
                'detail': '当前 rebuild2 输入源表本身就是北京窗口，rebuild3 复用这套输入。',
                'source_ref': 'rebuild2/sql/exec_l0_gps.sql:19',
            },
            {
                'label': 'GPS 参与计算范围',
                'value': '中国 bbox: 73<=lon<=135, 3<=lat<=54',
                'detail': '当前 rebuild3 用中国范围做 GPS 合法性与距离统计，不是北京 bbox 硬过滤。',
                'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:114',
            },
            {
                'label': '北京 bbox 硬过滤',
                'value': '未在 Cell baseline 资格里显式启用',
                'detail': '研究期北京约束目前主要体现在源表窗口，而不是 Cell baseline SQL 本身。',
                'source_ref': 'docs/rebuild3/01_rebuild3_说明_最终冻结版.md:441',
            },
            {
                'label': '2G / 3G 显式过滤',
                'value': '未在 rebuild3 Cell 构建 SQL 中写死',
                'detail': '但本次新增 baseline Cell 实际只出现 4G / 5G。',
                'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:147',
            },
        ],
        'cell_stages': [
            {
                'stage': '存在资格',
                'summary': 'record_count >= 5, device_count >= 1, active_days >= 1',
                'purpose': '决定 Cell 只是被注册，还是还停留在 waiting / observing。',
                'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:280',
            },
            {
                'stage': '锚点资格',
                'summary': 'gps_count >= 10, device_count >= 2, active_days >= 1, gps_p90_dist_m <= 1500',
                'purpose': '决定 Cell 能否作为可信锚点进入正式治理路径。',
                'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:291',
            },
            {
                'stage': '基线资格',
                'summary': 'gps_count >= 20, device_count >= 2, active_days >= 3, signal_original_ratio >= 0.5, gps_p90_dist_m <= 1500',
                'purpose': '决定 Cell 能否沉淀到 baseline / profile。',
                'source_ref': 'rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql:296',
            },
            {
                'stage': 'legacy 比对门槛',
                'summary': 'rebuild2 compare 侧仍要求 gps_anomaly = false',
                'purpose': '这是当前 Cell baseline 差异的主来源，需要在 UI 上明确告诉用户。',
                'source_ref': 'rebuild3/backend/sql/compare/002_prepare_full_compare.sql:167',
            },
        ],
        'legacy_rule': {
            'label': 'legacy gps_anomaly 定义',
            'summary': 'Cell 中心到 BS 中心距离：5G > 1000m 或 non5G > 2000m 即判异常',
            'source_ref': 'rebuild2/backend/app/api/enrich.py:823',
        },
        'impact': {
            'baseline_delta': 2274,
            'tech_split': [
                {'label': '5G', 'count': 2170},
                {'label': '4G', 'count': 104},
            ],
            'reason_split': [
                {'label': 'cell_to_bs_dist>1000m(5G)', 'count': 2170},
                {'label': 'cell_to_bs_dist>2000m(non5G)', 'count': 104},
            ],
            'p90_split': [
                {'label': '<250m', 'count': 1037},
                {'label': '250-500m', 'count': 542},
                {'label': '500-1000m', 'count': 428},
                {'label': '1000-1500m', 'count': 267},
            ],
            'beijing_bbox': {
                'inside': 2272,
                'outside': 2,
            },
            'active_days_split': [
                {'label': '7天', 'count': 1478},
                {'label': '6天', 'count': 472},
                {'label': '5天', 'count': 204},
                {'label': '4天', 'count': 93},
                {'label': '3天', 'count': 27},
            ],
        },
        'bs_guardrails': [
            {
                'label': 'BS anchorable 但无 anchorable 子 Cell',
                'value': 0,
                'detail': '修复后不再允许 BS 脱离 Cell 独立拿到 anchorable。',
            },
            {
                'label': 'BS baseline_eligible 但无 baseline 子 Cell',
                'value': 0,
                'detail': '修复后不再允许 BS baseline 独立漂移。',
            },
            {
                'label': 'BS active 但无 active 子 Cell',
                'value': 0,
                'detail': '修复后生命周期状态和子 Cell 保持一致。',
            },
        ],
        'notes': [
            '当前 Cell 增量主因不是 2G/3G 泄漏，也不是北京范围漏控，而是旧 gps_anomaly 门槛被替换成对象自身 P90 稳定性门槛。',
            '如果研究期要继续贴近 rebuild2，可把 legacy gps_anomaly 作为 research-mode 可配置开关重新挂到 Cell baseline 资格里。',
            '这些规则应该放在 Cell 页面直接展示，因为 BS / LAC 的可信性都源自 Cell 的状态与资格。',
        ],
    }


def _cell_list_snapshot() -> dict:
    rows = [
        {
            'object_id': 'cell|46011|5G|409602|1711509512',
            'operator_code': '46011',
            'operator_name': '中国电信',
            'tech_norm': '5G',
            'lac': '409602',
            'bs_id': 417849,
            'cell_id': 1711509512,
            'lifecycle_state': 'active',
            'health_state': 'healthy',
            'anchorable': True,
            'baseline_eligible': True,
            'record_count': 186,
            'device_count': 8,
            'active_days': 7,
            'gps_p90_dist_m': 881.95,
            'gps_original_ratio': 0.8123,
            'signal_original_ratio': 0.9032,
            'rsrp_avg': -94.2,
            'legacy_bs_classification': None,
            'legacy_gps_quality': '高',
            'legacy_gps_anomaly': True,
            'legacy_gps_anomaly_reason': 'cell_to_bs_dist>1000m(5G)',
            'compare_membership': 'r3_only',
            'outside_beijing_bbox': False,
            'watch': False,
        },
        {
            'object_id': 'cell|46000|4G|4264|10894519',
            'operator_code': '46000',
            'operator_name': '中国移动',
            'tech_norm': '4G',
            'lac': '4264',
            'bs_id': 42556,
            'cell_id': 10894519,
            'lifecycle_state': 'active',
            'health_state': 'healthy',
            'anchorable': True,
            'baseline_eligible': True,
            'record_count': 54,
            'device_count': 4,
            'active_days': 6,
            'gps_p90_dist_m': 1.13,
            'gps_original_ratio': 0.9444,
            'signal_original_ratio': 0.8889,
            'rsrp_avg': -90.8,
            'legacy_bs_classification': None,
            'legacy_gps_quality': '高',
            'legacy_gps_anomaly': True,
            'legacy_gps_anomaly_reason': 'cell_to_bs_dist>2000m(non5G)',
            'compare_membership': 'r3_only',
            'outside_beijing_bbox': True,
            'watch': False,
        },
        {
            'object_id': 'cell|46000|4G|12525|23732355',
            'operator_code': '46000',
            'operator_name': '中国移动',
            'tech_norm': '4G',
            'lac': '12525',
            'bs_id': 92615,
            'cell_id': 23732355,
            'lifecycle_state': 'observing',
            'health_state': 'healthy',
            'anchorable': False,
            'baseline_eligible': False,
            'record_count': 8,
            'device_count': 1,
            'active_days': 2,
            'gps_p90_dist_m': 34.2,
            'gps_original_ratio': 0.75,
            'signal_original_ratio': 0.63,
            'rsrp_avg': -96.0,
            'legacy_bs_classification': None,
            'legacy_gps_quality': '中',
            'legacy_gps_anomaly': False,
            'legacy_gps_anomaly_reason': None,
            'compare_membership': 'aligned',
            'outside_beijing_bbox': False,
            'watch': False,
        },
    ]
    return {
        'status': 'snapshot',
        'generated_at': _now_iso(),
        'rows': rows,
        'page': 1,
        'page_size': 10,
        'total': len(rows),
        'total_pages': 1,
        'sort_by': 'record_count',
        'sort_dir': 'desc',
    }


def _cell_summary_snapshot() -> dict:
    return {
        'status': 'snapshot',
        'generated_at': _now_iso(),
        'total_objects': 573561,
        'watch_count': 43453,
        'baseline_enabled': 194952,
        'anchorable_enabled': 265299,
        'compare_membership': [
            {'label': 'aligned', 'count': 571287},
            {'label': 'r3_only', 'count': 2274},
        ],
        'lifecycle': [
            {'label': 'active', 'count': 314322},
            {'label': 'observing', 'count': 112984},
            {'label': 'waiting', 'count': 146255},
        ],
        'health': [
            {'label': 'healthy', 'count': 495097},
            {'label': 'gps_bias', 'count': 41843},
            {'label': 'dynamic', 'count': 18085},
            {'label': 'collision_confirmed', 'count': 16743},
            {'label': 'collision_suspect', 'count': 1793},
        ],
        'qualification': [
            {'label': 'anchorable', 'count': 265299},
            {'label': 'baseline_eligible', 'count': 194952},
            {'label': 'legacy_gps_anomaly', 'count': 2274},
        ],
    }


def _cell_detail_snapshot(object_id: str) -> dict:
    list_snapshot = _cell_list_snapshot()
    row = next((item for item in list_snapshot['rows'] if item['object_id'] == object_id), list_snapshot['rows'][0])
    snapshot = {
        **row,
        'gps_anomaly': row['legacy_gps_anomaly'],
        'gps_anomaly_reason': row['legacy_gps_anomaly_reason'],
        'r2_health_state': 'gps_bias' if row['compare_membership'] == 'r3_only' else row['health_state'],
        'r2_baseline_eligible': row['compare_membership'] != 'r3_only',
        'baseline_center_lon': 116.4376,
        'baseline_center_lat': 39.9213,
        'center_shift_m': 23.0,
        'bs_object_id': f"bs|{row['operator_code']}|{row['tech_norm']}|{row['lac']}|{row['bs_id']}",
        'lac_object_id': f"lac|{row['operator_code']}|{row['tech_norm']}|{row['lac']}",
        'bs_health_state': 'healthy',
        'lac_health_state': 'healthy',
        'run_id': 'RUN-FULL-20251201-20251207-V1',
        'batch_id': 'BATCH-FULL-20251201-20251207-V1',
    }
    return {
        'status': 'snapshot',
        'generated_at': _now_iso(),
        'snapshot': snapshot,
        'facts': [
            {'route': 'fact_governed', 'count': 132},
            {'route': 'fact_pending_observation', 'count': 0},
            {'route': 'fact_pending_issue', 'count': 0},
            {'route': 'fact_rejected', 'count': 0},
        ],
        'history': [
            {
                'changed_at': '2026-04-04T19:46:47+08:00',
                'changed_reason': 'full_init_snapshot',
                'lifecycle_state': row['lifecycle_state'],
                'health_state': row['health_state'],
                'anchorable': row['anchorable'],
                'baseline_eligible': row['baseline_eligible'],
            }
        ],
        'gps_source_mix': [
            {'label': 'original', 'count': 108},
            {'label': 'cell_center', 'count': 16},
            {'label': 'bs_center', 'count': 8},
        ],
        'signal_source_mix': [
            {'label': 'original', 'count': 119},
            {'label': 'cell_fill', 'count': 9},
            {'label': 'bs_fill', 'count': 4},
        ],
        'rule_audit': _build_cell_rule_audit(snapshot),
        'qualification_reasons': _build_qualification_reasons(snapshot),
        'downstream': {
            'bs_object_id': f"bs|{row['operator_code']}|{row['tech_norm']}|{row['lac']}|{row['bs_id']}",
            'bs_active_cell_count': 4,
            'lac_object_id': f"lac|{row['operator_code']}|{row['tech_norm']}|{row['lac']}",
            'lac_active_bs_count': 12,
        },
        'anomalies': [],
        'compare_context': _build_compare_context(snapshot),
        'change_log': _base_change_log(),
    }


CELL_SNAPSHOT_SQL = """
SELECT
  c.object_id,
  c.operator_code,
  c.tech_norm,
  c.lac,
  c.bs_id,
  c.cell_id,
  c.lifecycle_state,
  c.health_state,
  c.existence_eligible,
  c.anchorable,
  c.baseline_eligible,
  c.record_count,
  c.gps_count,
  c.device_count,
  c.active_days,
  c.centroid_lon,
  c.centroid_lat,
  c.gps_p50_dist_m,
  c.gps_p90_dist_m,
  c.gps_original_ratio,
  c.signal_original_ratio,
  c.anomaly_tags,
  c.run_id,
  c.batch_id,
  cp.operator_cn,
  cp.rsrp_avg,
  cp.gps_anomaly,
  cp.dist_to_bs_m,
  cp.bs_gps_quality,
  cr.gps_anomaly_reason,
  br.classification_v2 AS legacy_bs_classification,
  r2.lifecycle_state AS r2_lifecycle_state,
  r2.health_state AS r2_health_state,
  r2.baseline_eligible AS r2_baseline_eligible,
  bc.center_lon AS baseline_center_lon,
  bc.center_lat AS baseline_center_lat,
  bc.gps_p50_dist_m AS baseline_gps_p50_dist_m,
  bc.gps_p90_dist_m AS baseline_gps_p90_dist_m,
  bs.object_id AS bs_object_id,
  bs.lifecycle_state AS bs_lifecycle_state,
  bs.health_state AS bs_health_state,
  bs.baseline_eligible AS bs_baseline_eligible,
  bs.active_cell_count AS bs_active_cell_count,
  lac.object_id AS lac_object_id,
  lac.lifecycle_state AS lac_lifecycle_state,
  lac.health_state AS lac_health_state,
  lac.baseline_eligible AS lac_baseline_eligible,
  lac.active_bs_count AS lac_active_bs_count
FROM rebuild3.obj_cell c
LEFT JOIN rebuild3.stg_cell_profile cp
  ON c.operator_code = cp.operator_code
 AND c.tech_norm = cp.tech_norm
 AND c.lac = cp.lac
 AND c.bs_id = cp.bs_id
 AND c.cell_id = cp.cell_id
LEFT JOIN rebuild3.stg_bs_classification_ref br
  ON c.operator_code = br.operator_code
 AND c.tech_norm = br.tech_norm
 AND c.lac = br.lac
 AND c.bs_id = br.bs_id
LEFT JOIN rebuild2.dim_cell_refined cr
  ON c.operator_code = cr.operator_code
 AND c.tech_norm = cr.tech_norm
 AND c.lac = cr.lac
 AND c.bs_id = cr.bs_id
 AND c.cell_id = cr.cell_id
LEFT JOIN rebuild3_meta.r2_full_cell_state r2
  ON c.object_id = r2.object_id
LEFT JOIN rebuild3.baseline_cell bc
  ON c.object_id = bc.object_id
LEFT JOIN rebuild3.obj_bs bs
  ON c.parent_bs_object_id = bs.object_id
LEFT JOIN rebuild3.obj_lac lac
  ON bs.parent_lac_object_id = lac.object_id
WHERE c.object_id = %(object_id)s
"""


def _build_cell_rule_audit(row: dict) -> list[dict]:
    lon = row.get('centroid_lon')
    lat = row.get('centroid_lat')
    p90 = float(row.get('gps_p90_dist_m') or 0)
    signal_ratio = float(row.get('signal_original_ratio') or 0)
    gps_count = int(row.get('gps_count') or 0)
    device_count = int(row.get('device_count') or 0)
    active_days = int(row.get('active_days') or 0)
    tech_norm = row.get('tech_norm')

    return [
        {
            'label': '研究期输入源',
            'state': 'applied',
            'detail': '当前仍以北京一周 GPS / LAC 明细表作为研究期输入窗口。',
        },
        {
            'label': 'GPS 合法性范围',
            'state': 'applied',
            'detail': f"当前使用中国 bbox：{CHINA_BBOX['lon_min']}~{CHINA_BBOX['lon_max']} / {CHINA_BBOX['lat_min']}~{CHINA_BBOX['lat_max']}。",
        },
        {
            'label': '北京 bbox 硬过滤',
            'state': 'not_applied',
            'detail': '没有写进 Cell baseline 硬门槛；页面必须显式告诉用户这一点。',
        },
        {
            'label': '2G / 3G 显式过滤',
            'state': 'not_applied',
            'detail': f"当前对象制式为 {tech_norm}；SQL 没把 2G/3G 写死成过滤条件。",
        },
        {
            'label': 'legacy gps_anomaly',
            'state': 'compare_only',
            'detail': 'rebuild2 compare 侧仍把 gps_anomaly=false 当成 baseline 前置条件。',
        },
        {
            'label': 'Cell P90 1500m 门槛',
            'state': _rule_state(p90 <= 1500),
            'detail': f'当前 gps_p90_dist_m={p90:.2f}m。',
        },
        {
            'label': 'Cell 样本量门槛',
            'state': _rule_state(gps_count >= 20 and device_count >= 2 and active_days >= 3),
            'detail': f'gps_count={gps_count}, device_count={device_count}, active_days={active_days}。',
        },
        {
            'label': 'Cell 信号原始率门槛',
            'state': _rule_state(signal_ratio >= 0.5),
            'detail': f'signal_original_ratio={signal_ratio:.4f}，当前基线门槛为 >=0.5。',
        },
        {
            'label': '北京框定位检查',
            'state': 'warning' if _is_outside_bbox(lon, lat, BEIJING_BBOX) else 'passed',
            'detail': '只做展示，不作为当前 Cell baseline 直接否决条件。',
        },
        {
            'label': 'BS 资格级联',
            'state': 'applied',
            'detail': 'BS 的 anchorable / baseline_eligible 严格来源于子 Cell。',
        },
    ]


def _build_qualification_reasons(row: dict) -> list[dict]:
    reasons: list[dict] = []
    p90 = float(row.get('gps_p90_dist_m') or 0)
    signal_ratio = float(row.get('signal_original_ratio') or 0)
    gps_count = int(row.get('gps_count') or 0)
    device_count = int(row.get('device_count') or 0)
    active_days = int(row.get('active_days') or 0)
    health_state = row.get('health_state') or 'healthy'

    anchor_reasons: list[str] = []
    baseline_reasons: list[str] = []

    if health_state in ISSUE_HEALTH_STATES:
        anchor_reasons.append(f'health_state={health_state}，当前规则禁止锚点。')
    if gps_count < 10:
        anchor_reasons.append(f'gps_count={gps_count}，未达到锚点门槛 10。')
    if device_count < 2:
        anchor_reasons.append(f'device_count={device_count}，未达到锚点门槛 2。')
    if active_days < 1:
        anchor_reasons.append(f'active_days={active_days}，未达到锚点门槛 1 天。')
    if p90 > 1500:
        anchor_reasons.append(f'gps_p90_dist_m={p90:.2f}m，超过 1500m。')

    if not row.get('anchorable') and not anchor_reasons:
        anchor_reasons.append('锚点资格未通过，但当前对象没有命中已展开的显式失败项。')
    if row.get('anchorable'):
        anchor_reasons.append('锚点资格已通过：样本量、设备数、活跃天数和 P90 门槛均满足。')

    if not row.get('anchorable'):
        baseline_reasons.append('锚点禁用对象默认不进入 baseline。')
    if gps_count < 20:
        baseline_reasons.append(f'gps_count={gps_count}，未达到基线门槛 20。')
    if device_count < 2:
        baseline_reasons.append(f'device_count={device_count}，未达到基线门槛 2。')
    if active_days < 3:
        baseline_reasons.append(f'active_days={active_days}，未达到基线门槛 3 天。')
    if signal_ratio < 0.5:
        baseline_reasons.append(f'signal_original_ratio={signal_ratio:.4f}，未达到 0.5。')
    if p90 > 1500:
        baseline_reasons.append(f'gps_p90_dist_m={p90:.2f}m，超过 1500m。')

    compare_membership = _compare_membership(row)
    if bool(row.get('gps_anomaly')):
        baseline_reasons.append('legacy 口径仍会把 gps_anomaly=true 当成 compare 侧否决项。')
    if row.get('baseline_eligible') and compare_membership == 'r3_only':
        baseline_reasons.append('当前对象属于 r3_only：rebuild3 允许进 baseline，但 rebuild2 compare 侧仍会拦掉。')
    if row.get('baseline_eligible') and not baseline_reasons:
        baseline_reasons.append('基线资格已通过：样本量、活跃天数、信号原始率、P90 均满足。')

    reasons.append({'label': '锚点资格', 'passed': bool(row.get('anchorable')), 'items': anchor_reasons})
    reasons.append({'label': '基线资格', 'passed': bool(row.get('baseline_eligible')), 'items': baseline_reasons})
    return reasons


def _build_compare_context(row: dict) -> dict:
    membership = _compare_membership(row)
    explanation = '当前对象在 rebuild2 / rebuild3 的 baseline 资格一致。'
    if membership == 'r3_only':
        explanation = '当前对象在 rebuild3 可进 baseline，但 rebuild2 compare 侧仍因 legacy gps_anomaly 被拦截。'
    elif membership == 'r2_only':
        explanation = '当前对象在 rebuild2 compare 侧仍留在 baseline，但 rebuild3 已收紧资格。'
    return {
        'membership': membership,
        'r2_health_state': row.get('r2_health_state') or row.get('health_state'),
        'r3_health_state': row.get('health_state'),
        'r2_baseline_eligible': bool(row.get('r2_baseline_eligible')),
        'r3_baseline_eligible': bool(row.get('baseline_eligible')),
        'legacy_gps_anomaly': bool(row.get('gps_anomaly')),
        'legacy_gps_anomaly_reason': row.get('gps_anomaly_reason'),
        'explanation': explanation,
    }


def _serialize_cell_snapshot(row: dict) -> dict:
    centroid_lon = row.get('centroid_lon')
    centroid_lat = row.get('centroid_lat')
    baseline_lon = row.get('baseline_center_lon')
    baseline_lat = row.get('baseline_center_lat')
    center_shift_m = None
    if None not in (centroid_lon, centroid_lat, baseline_lon, baseline_lat):
        dx = (float(centroid_lon) - float(baseline_lon)) * 85300
        dy = (float(centroid_lat) - float(baseline_lat)) * 111000
        center_shift_m = round((dx * dx + dy * dy) ** 0.5, 2)

    snapshot = dict(row)
    snapshot['operator_name'] = row.get('operator_cn') or _operator_name(row.get('operator_code'))
    snapshot['legacy_gps_quality'] = _legacy_quality_label(row.get('bs_gps_quality'))
    snapshot['compare_membership'] = _compare_membership(row)
    snapshot['watch'] = row.get('lifecycle_state') == 'active' and row.get('health_state') != 'healthy'
    snapshot['outside_beijing_bbox'] = _is_outside_bbox(centroid_lon, centroid_lat, BEIJING_BBOX)
    snapshot['outside_china_bbox'] = _is_outside_bbox(centroid_lon, centroid_lat, CHINA_BBOX)
    snapshot['center_shift_m'] = center_shift_m
    return snapshot


@router.get('/cell/transparency')
def get_cell_transparency():
    snapshot = _build_cell_transparency_snapshot()
    try:
        with get_conn() as conn:
            delta = _fetch_one(
                conn,
                """
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.object_id
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT count(*)::bigint AS baseline_delta
                FROM r3_only;
                """,
            )
            tech_rows = _fetch_all(
                conn,
                """
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.tech_norm
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT tech_norm AS label, count(*)::bigint AS count
                FROM r3_only
                GROUP BY tech_norm
                ORDER BY count(*) DESC, tech_norm;
                """,
            )
            reason_rows = _fetch_all(
                conn,
                """
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.operator_code, r3.tech_norm, r3.lac, r3.cell_id
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT coalesce(cr.gps_anomaly_reason, '<null>') AS label, count(*)::bigint AS count
                FROM r3_only x
                LEFT JOIN rebuild2.dim_cell_refined cr
                  ON x.operator_code = cr.operator_code
                 AND x.tech_norm = cr.tech_norm
                 AND x.lac = cr.lac
                 AND x.cell_id = cr.cell_id
                GROUP BY coalesce(cr.gps_anomaly_reason, '<null>')
                ORDER BY count(*) DESC, label;
                """,
            )
            p90_rows = _fetch_all(
                conn,
                """
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.gps_p90_dist_m
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT
                  CASE
                    WHEN gps_p90_dist_m < 250 THEN '<250m'
                    WHEN gps_p90_dist_m < 500 THEN '250-500m'
                    WHEN gps_p90_dist_m < 1000 THEN '500-1000m'
                    WHEN gps_p90_dist_m <= 1500 THEN '1000-1500m'
                    ELSE '>1500m'
                  END AS label,
                  count(*)::bigint AS count
                FROM r3_only
                GROUP BY 1
                ORDER BY min(gps_p90_dist_m);
                """,
            )
            day_rows = _fetch_all(
                conn,
                """
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.active_days
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT (active_days::text || '天') AS label, count(*)::bigint AS count
                FROM r3_only
                GROUP BY active_days
                ORDER BY active_days DESC;
                """,
            )
            bbox = _fetch_one(
                conn,
                f"""
                WITH r2 AS (
                  SELECT object_id, baseline_eligible
                  FROM rebuild3_meta.r2_full_cell_state
                ),
                r3_only AS (
                  SELECT r3.centroid_lon, r3.centroid_lat
                  FROM rebuild3.obj_cell r3
                  LEFT JOIN r2 USING (object_id)
                  WHERE r3.baseline_eligible
                    AND coalesce(r2.baseline_eligible, false) = false
                )
                SELECT
                  count(*) FILTER (
                    WHERE centroid_lon BETWEEN {BEIJING_BBOX['lon_min']} AND {BEIJING_BBOX['lon_max']}
                      AND centroid_lat BETWEEN {BEIJING_BBOX['lat_min']} AND {BEIJING_BBOX['lat_max']}
                  )::bigint AS inside,
                  count(*) FILTER (
                    WHERE NOT (
                      centroid_lon BETWEEN {BEIJING_BBOX['lon_min']} AND {BEIJING_BBOX['lon_max']}
                      AND centroid_lat BETWEEN {BEIJING_BBOX['lat_min']} AND {BEIJING_BBOX['lat_max']}
                    )
                  )::bigint AS outside
                FROM r3_only;
                """,
            )
            bs_guard = _fetch_one(
                conn,
                """
                WITH bs AS (
                  SELECT
                    b.object_id,
                    b.anchorable,
                    b.baseline_eligible,
                    b.lifecycle_state,
                    coalesce(sum(CASE WHEN c.anchorable THEN 1 ELSE 0 END), 0) AS anchorable_cell_cnt,
                    coalesce(sum(CASE WHEN c.baseline_eligible THEN 1 ELSE 0 END), 0) AS baseline_cell_cnt,
                    coalesce(sum(CASE WHEN c.lifecycle_state = 'active' THEN 1 ELSE 0 END), 0) AS active_cell_cnt
                  FROM rebuild3.obj_bs b
                  LEFT JOIN rebuild3.obj_cell c
                    ON c.parent_bs_object_id = b.object_id
                  GROUP BY 1,2,3,4
                )
                SELECT
                  count(*) FILTER (WHERE anchorable AND anchorable_cell_cnt = 0)::bigint AS anchorable_without_child,
                  count(*) FILTER (WHERE baseline_eligible AND baseline_cell_cnt = 0)::bigint AS baseline_without_child,
                  count(*) FILTER (WHERE lifecycle_state = 'active' AND active_cell_cnt = 0)::bigint AS active_without_child
                FROM bs;
                """,
            )

        snapshot['status'] = 'ok'
        snapshot['data_origin'] = 'live'
        snapshot['error_message'] = None
        snapshot['generated_at'] = _now_iso()
        snapshot['impact']['baseline_delta'] = int(delta.get('baseline_delta', 0))
        snapshot['impact']['tech_split'] = tech_rows
        snapshot['impact']['reason_split'] = reason_rows
        snapshot['impact']['p90_split'] = p90_rows
        snapshot['impact']['active_days_split'] = day_rows
        snapshot['impact']['beijing_bbox'] = {
            'inside': int(bbox.get('inside', 0)),
            'outside': int(bbox.get('outside', 0)),
        }
        snapshot['bs_guardrails'] = [
            {
                'label': 'BS anchorable 但无 anchorable 子 Cell',
                'value': int(bs_guard.get('anchorable_without_child', 0)),
                'detail': '修复后不再允许 BS 脱离 Cell 独立拿到 anchorable。',
            },
            {
                'label': 'BS baseline_eligible 但无 baseline 子 Cell',
                'value': int(bs_guard.get('baseline_without_child', 0)),
                'detail': '修复后不再允许 BS baseline 独立漂移。',
            },
            {
                'label': 'BS active 但无 active 子 Cell',
                'value': int(bs_guard.get('active_without_child', 0)),
                'detail': '修复后生命周期状态和子 Cell 保持一致。',
            },
        ]
        return snapshot
    except Exception as exc:  # pragma: no cover
        return _build_cell_transparency_snapshot(str(exc))


@router.get('/cell/summary')
def get_cell_summary():
    try:
        with get_conn() as conn:
            base = _fetch_one(
                conn,
                """
                SELECT
                  count(*)::bigint AS total_objects,
                  count(*) FILTER (WHERE lifecycle_state = 'active' AND health_state <> 'healthy')::bigint AS watch_count,
                  count(*) FILTER (WHERE baseline_eligible)::bigint AS baseline_enabled,
                  count(*) FILTER (WHERE anchorable)::bigint AS anchorable_enabled
                FROM rebuild3.obj_cell;
                """,
            )
            lifecycle_rows = _fetch_all(
                conn,
                """
                SELECT lifecycle_state AS label, count(*)::bigint AS count
                FROM rebuild3.obj_cell
                GROUP BY lifecycle_state
                ORDER BY count(*) DESC, lifecycle_state;
                """,
            )
            health_rows = _fetch_all(
                conn,
                """
                SELECT health_state AS label, count(*)::bigint AS count
                FROM rebuild3.obj_cell
                GROUP BY health_state
                ORDER BY count(*) DESC, health_state;
                """,
            )
            compare_rows = _fetch_all(
                conn,
                """
                WITH joined AS (
                  SELECT
                    CASE
                      WHEN c.baseline_eligible AND NOT coalesce(r2.baseline_eligible, false) THEN 'r3_only'
                      WHEN NOT c.baseline_eligible AND coalesce(r2.baseline_eligible, false) THEN 'r2_only'
                      ELSE 'aligned'
                    END AS label
                  FROM rebuild3.obj_cell c
                  LEFT JOIN rebuild3_meta.r2_full_cell_state r2
                    ON c.object_id = r2.object_id
                )
                SELECT label, count(*)::bigint AS count
                FROM joined
                GROUP BY label
                ORDER BY count(*) DESC, label;
                """,
            )
            qualification_rows = _fetch_all(
                conn,
                """
                SELECT 'anchorable' AS label, count(*) FILTER (WHERE anchorable)::bigint AS count
                FROM rebuild3.obj_cell
                UNION ALL
                SELECT 'baseline_eligible', count(*) FILTER (WHERE baseline_eligible)::bigint
                FROM rebuild3.obj_cell
                UNION ALL
                SELECT 'legacy_gps_anomaly', count(*) FILTER (WHERE gps_anomaly)::bigint
                FROM rebuild3.stg_cell_profile;
                """,
            )
        return {
            'status': 'ok',
            'generated_at': _now_iso(),
            'total_objects': int(base.get('total_objects', 0)),
            'watch_count': int(base.get('watch_count', 0)),
            'baseline_enabled': int(base.get('baseline_enabled', 0)),
            'anchorable_enabled': int(base.get('anchorable_enabled', 0)),
            'compare_membership': compare_rows,
            'lifecycle': lifecycle_rows,
            'health': health_rows,
            'qualification': qualification_rows,
        }
    except Exception:
        return _cell_summary_snapshot()


@router.get('/cell/list')
def get_cell_list(
    query: str | None = Query(default=None),
    operator_code: str | None = Query(default=None),
    tech_norm: str | None = Query(default=None),
    lifecycle_state: str = Query(default='all'),
    health_state: str = Query(default='all'),
    qualification: str = Query(default='all'),
    membership: str = Query(default='all'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    sort_by: str = Query(default='record_count'),
    sort_dir: str = Query(default='desc'),
):
    sort_column = CELL_SORT_COLUMNS.get(sort_by, 'record_count')
    sort_direction = 'ASC' if sort_dir.lower() == 'asc' else 'DESC'
    where_clauses = ['1 = 1']
    params: dict[str, object] = {
        'limit': page_size,
        'offset': (page - 1) * page_size,
    }

    if query:
        where_clauses.append(
            """
            (
              c.object_id ILIKE %(query)s
              OR c.lac ILIKE %(query)s
              OR c.bs_id::text ILIKE %(query)s
              OR c.cell_id::text ILIKE %(query)s
            )
            """
        )
        params['query'] = f'%{query.strip()}%'
    if operator_code:
        where_clauses.append('c.operator_code = %(operator_code)s')
        params['operator_code'] = operator_code
    if tech_norm and tech_norm != 'all':
        where_clauses.append('c.tech_norm = %(tech_norm)s')
        params['tech_norm'] = tech_norm
    if lifecycle_state != 'all':
        where_clauses.append('c.lifecycle_state = %(lifecycle_state)s')
        params['lifecycle_state'] = lifecycle_state
    if health_state != 'all':
        where_clauses.append('c.health_state = %(health_state)s')
        params['health_state'] = health_state
    if qualification == 'anchorable':
        where_clauses.append('c.anchorable = true')
    elif qualification == 'not_anchorable':
        where_clauses.append('c.anchorable = false')
    elif qualification == 'baseline':
        where_clauses.append('c.baseline_eligible = true')
    elif qualification == 'not_baseline':
        where_clauses.append('c.baseline_eligible = false')

    if membership == 'r3_only':
        where_clauses.append('c.baseline_eligible = true AND NOT coalesce(r2.baseline_eligible, false)')
    elif membership == 'r2_only':
        where_clauses.append('c.baseline_eligible = false AND coalesce(r2.baseline_eligible, false)')
    elif membership == 'aligned':
        where_clauses.append('c.baseline_eligible = coalesce(r2.baseline_eligible, c.baseline_eligible)')

    sql = f"""
    WITH filtered AS (
      SELECT
        c.object_id,
        c.operator_code,
        c.tech_norm,
        c.lac,
        c.bs_id,
        c.cell_id,
        c.lifecycle_state,
        c.health_state,
        c.anchorable,
        c.baseline_eligible,
        c.record_count,
        c.device_count,
        c.active_days,
        c.gps_p90_dist_m,
        c.gps_original_ratio,
        c.signal_original_ratio,
        c.centroid_lon,
        c.centroid_lat,
        cp.operator_cn,
        cp.rsrp_avg,
        cp.gps_anomaly,
        cr.gps_anomaly_reason,
        cp.bs_gps_quality,
        br.classification_v2 AS legacy_bs_classification,
        r2.baseline_eligible AS r2_baseline_eligible,
        CASE
          WHEN c.baseline_eligible AND NOT coalesce(r2.baseline_eligible, false) THEN 'r3_only'
          WHEN NOT c.baseline_eligible AND coalesce(r2.baseline_eligible, false) THEN 'r2_only'
          ELSE 'aligned'
        END AS compare_membership,
        count(*) OVER()::bigint AS total_count
      FROM rebuild3.obj_cell c
      LEFT JOIN rebuild3_meta.r2_full_cell_state r2
        ON c.object_id = r2.object_id
      LEFT JOIN rebuild3.stg_cell_profile cp
        ON c.operator_code = cp.operator_code
       AND c.tech_norm = cp.tech_norm
       AND c.lac = cp.lac
       AND c.bs_id = cp.bs_id
       AND c.cell_id = cp.cell_id
      LEFT JOIN rebuild3.stg_bs_classification_ref br
        ON c.operator_code = br.operator_code
       AND c.tech_norm = br.tech_norm
       AND c.lac = br.lac
       AND c.bs_id = br.bs_id
      LEFT JOIN rebuild2.dim_cell_refined cr
        ON c.operator_code = cr.operator_code
       AND c.tech_norm = cr.tech_norm
       AND c.lac = cr.lac
       AND c.bs_id = cr.bs_id
       AND c.cell_id = cr.cell_id
      WHERE {' AND '.join(where_clauses)}
    ),
    page_rows AS (
      SELECT *
      FROM filtered
      ORDER BY {sort_column} {sort_direction}, object_id ASC
      LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT *
    FROM page_rows
    ORDER BY {sort_column} {sort_direction}, object_id ASC;
    """

    try:
        with get_conn() as conn:
            rows = _fetch_all(conn, sql, params)
        total = int(rows[0]['total_count']) if rows else 0
        result_rows = []
        for row in rows:
            result_rows.append(
                {
                    'object_id': row['object_id'],
                    'operator_code': row['operator_code'],
                    'operator_name': row.get('operator_cn') or _operator_name(row.get('operator_code')),
                    'tech_norm': row['tech_norm'],
                    'lac': row['lac'],
                    'bs_id': row['bs_id'],
                    'cell_id': row['cell_id'],
                    'lifecycle_state': row['lifecycle_state'],
                    'health_state': row['health_state'],
                    'anchorable': bool(row['anchorable']),
                    'baseline_eligible': bool(row['baseline_eligible']),
                    'record_count': int(row['record_count']),
                    'device_count': int(row['device_count']),
                    'active_days': int(row['active_days']),
                    'gps_p90_dist_m': float(row['gps_p90_dist_m'] or 0),
                    'gps_original_ratio': float(row['gps_original_ratio'] or 0),
                    'signal_original_ratio': float(row['signal_original_ratio'] or 0),
                    'rsrp_avg': float(row['rsrp_avg']) if row.get('rsrp_avg') is not None else None,
                    'legacy_bs_classification': row.get('legacy_bs_classification'),
                    'legacy_gps_quality': _legacy_quality_label(row.get('bs_gps_quality')),
                    'legacy_gps_anomaly': bool(row.get('gps_anomaly')),
                    'legacy_gps_anomaly_reason': row.get('gps_anomaly_reason'),
                    'compare_membership': row['compare_membership'],
                    'outside_beijing_bbox': _is_outside_bbox(row.get('centroid_lon'), row.get('centroid_lat'), BEIJING_BBOX),
                    'watch': row['lifecycle_state'] == 'active' and row['health_state'] != 'healthy',
                }
            )
        return {
            'status': 'ok',
            'generated_at': _now_iso(),
            'rows': result_rows,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': max(1, (total + page_size - 1) // page_size),
            'sort_by': sort_by,
            'sort_dir': sort_direction.lower(),
        }
    except Exception:
        return _cell_list_snapshot()


@router.get('/cell/{object_id}/detail')
def get_cell_detail(object_id: str):
    try:
        with get_conn() as conn:
            row = _fetch_one(conn, CELL_SNAPSHOT_SQL, {'object_id': object_id})
            if not row:
                raise HTTPException(status_code=404, detail='未找到该 Cell 对象')
            snapshot = _serialize_cell_snapshot(row)
            facts = _fetch_all(
                conn,
                """
                SELECT route, count(*)::bigint AS count
                FROM (
                  SELECT 'fact_governed'::text AS route FROM rebuild3.fact_governed WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                  UNION ALL
                  SELECT 'fact_pending_observation' FROM rebuild3.fact_pending_observation WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                  UNION ALL
                  SELECT 'fact_pending_issue' FROM rebuild3.fact_pending_issue WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                  UNION ALL
                  SELECT 'fact_rejected' FROM rebuild3.fact_rejected WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                ) x
                GROUP BY route
                ORDER BY route;
                """,
                row,
            )
            history = _fetch_all(
                conn,
                """
                SELECT changed_at, changed_reason, lifecycle_state, health_state, anchorable, baseline_eligible
                FROM rebuild3.obj_state_history
                WHERE object_type = 'cell'
                  AND object_id = %(object_id)s
                ORDER BY changed_at DESC
                LIMIT 12;
                """,
                {'object_id': object_id},
            )
            gps_source_mix = _fetch_all(
                conn,
                """
                SELECT coalesce(gps_source, '<null>') AS label, count(*)::bigint AS count
                FROM rebuild3.fact_governed
                WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                GROUP BY coalesce(gps_source, '<null>')
                ORDER BY count(*) DESC, label;
                """,
                row,
            )
            signal_source_mix = _fetch_all(
                conn,
                """
                SELECT coalesce(signal_source, '<null>') AS label, count(*)::bigint AS count
                FROM rebuild3.fact_governed
                WHERE operator_code = %(operator_code)s AND tech_norm = %(tech_norm)s AND lac = %(lac)s AND cell_id = %(cell_id)s
                GROUP BY coalesce(signal_source, '<null>')
                ORDER BY count(*) DESC, label;
                """,
                row,
            )
            sibling_counts = _fetch_one(
                conn,
                """
                SELECT
                  count(*)::bigint AS sibling_cell_count,
                  count(*) FILTER (WHERE lifecycle_state = 'active')::bigint AS sibling_active_cell_count,
                  count(*) FILTER (WHERE baseline_eligible)::bigint AS sibling_baseline_cell_count
                FROM rebuild3.obj_cell
                WHERE parent_bs_object_id = %(bs_object_id)s;
                """,
                {'bs_object_id': row.get('bs_object_id')},
            )
        anomalies: list[dict] = []
        if snapshot['health_state'] != 'healthy':
            anomalies.append(
                {
                    'type': snapshot['health_state'],
                    'severity': 'medium' if snapshot['health_state'] == 'gps_bias' else 'high',
                    'detail': f"对象当前 health_state={snapshot['health_state']}。",
                }
            )
        if snapshot['legacy_gps_anomaly']:
            anomalies.append(
                {
                    'type': 'legacy_gps_anomaly',
                    'severity': 'compare_only',
                    'detail': snapshot.get('legacy_gps_anomaly_reason') or 'legacy compare 侧命中 gps_anomaly。',
                }
            )
        return {
            'status': 'ok',
            'generated_at': _now_iso(),
            'snapshot': snapshot,
            'facts': facts,
            'history': history,
            'gps_source_mix': gps_source_mix,
            'signal_source_mix': signal_source_mix,
            'rule_audit': _build_cell_rule_audit(snapshot),
            'qualification_reasons': _build_qualification_reasons(snapshot),
            'downstream': {
                'bs_object_id': snapshot.get('bs_object_id'),
                'bs_health_state': snapshot.get('bs_health_state'),
                'bs_active_cell_count': int(snapshot.get('bs_active_cell_count') or 0),
                'sibling_cell_count': int(sibling_counts.get('sibling_cell_count', 0)),
                'sibling_active_cell_count': int(sibling_counts.get('sibling_active_cell_count', 0)),
                'sibling_baseline_cell_count': int(sibling_counts.get('sibling_baseline_cell_count', 0)),
                'lac_object_id': snapshot.get('lac_object_id'),
                'lac_health_state': snapshot.get('lac_health_state'),
                'lac_active_bs_count': int(snapshot.get('lac_active_bs_count') or 0),
            },
            'anomalies': anomalies,
            'compare_context': _build_compare_context(snapshot),
            'change_log': _base_change_log(),
        }
    except HTTPException:
        raise
    except Exception:
        return _cell_detail_snapshot(object_id)


@router.get('/cell/{object_id}/profile')
def get_cell_profile(object_id: str):
    detail = get_cell_detail(object_id)
    if detail.get('status') == 'ok' or detail.get('status') == 'snapshot':
        snapshot = detail['snapshot']
        profile_notes = []
        if detail['compare_context']['membership'] == 'r3_only':
            profile_notes.append('该 Cell 属于 r3_only：rebuild3 已允许进入 baseline，但 rebuild2 compare 侧仍会拦截。')
        if snapshot.get('legacy_gps_anomaly'):
            profile_notes.append('legacy gps_anomaly 仍被命中，说明旧口径更偏向用 Cell-BS 距离硬阈值。')
        if snapshot.get('outside_beijing_bbox'):
            profile_notes.append('当前质心落在北京研究框外；这在 UI 上必须直接可见。')
        return {
            'status': detail['status'],
            'generated_at': detail['generated_at'],
            'snapshot': snapshot,
            'gps_source_mix': detail['gps_source_mix'],
            'signal_source_mix': detail['signal_source_mix'],
            'facts': detail['facts'],
            'rule_audit': detail['rule_audit'],
            'compare_context': detail['compare_context'],
            'profile_notes': profile_notes,
        }
    return detail


@router.get('/{object_type}')
def get_objects(object_type: str):
    return {'object_type': object_type, 'message': 'connect to obj_* read models in runtime deployment'}
