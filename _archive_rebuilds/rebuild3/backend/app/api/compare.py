from __future__ import annotations

from fastapi import APIRouter

from app.api.common import now_iso
from app.api.run_shared import fallback_contract

router = APIRouter(prefix='/api/v1/compare', tags=['compare'])


SAMPLE_OVERVIEW = {
    'scope': 'sample',
    'title': '样本双跑偏差（fallback）',
    'gate': '仅供参考，不代表实时对比结果',
    'summary': [
        {'label': 'fact_pending_issue 差值', 'value': 206},
        {'label': 'Cell baseline 差值', 'value': 8},
        {'label': '共同 baseline 稳定性', 'value': 'P90=0m'},
    ],
    'routes': [
        {'route': 'fact_governed', 'r2': 21273, 'r3': 21067, 'diff': -206},
        {'route': 'fact_pending_issue', 'r2': 13475, 'r3': 13681, 'diff': 206},
        {'route': 'fact_pending_observation', 'r2': 50, 'r3': 50, 'diff': 0},
        {'route': 'fact_rejected', 'r2': 200, 'r3': 200, 'diff': 0},
    ],
    'notes': [
        '样本阶段主偏差集中在 gps_bias 语义收紧。',
        '当前页面仍使用历史报告 fallback，需与实时 compare 结果区分。',
    ],
}

FULL_OVERVIEW = {
    'scope': 'full',
    'title': '全量偏差评估（fallback）',
    'gate': '仅供参考，不代表实时对比结果',
    'summary': [
        {'label': 'fact_pending_issue 差值', 'value': 2036318},
        {'label': 'Cell baseline 差值', 'value': 2274},
        {'label': 'BS baseline 差值', 'value': 109},
    ],
    'routes': [
        {'route': 'fact_governed', 'r2': 26775722, 'r3': 24855605, 'diff': -1920117},
        {'route': 'fact_pending_issue', 'r2': 1789244, 'r3': 3825562, 'diff': 2036318},
        {'route': 'fact_pending_observation', 'r2': 10706939, 'r3': 10590738, 'diff': -116201},
        {'route': 'fact_rejected', 'r2': 4499401, 'r3': 4499401, 'diff': 0},
    ],
    'notes': [
        '共同 baseline 对象上的空间指标完全一致，主差异来自状态/资格规则。',
        'gps_bias 问题池扩大是当前全量偏差主因。',
    ],
}

SAMPLE_DIFFS = [
    {
        'object_id': 'cell|46001|5G|98310|140755|576533513',
        'diff_type': 'baseline_membership',
        'scope': 'sample',
        'title': 'r2_only baseline Cell',
        'left_value': 'rebuild2=healthy / baseline',
        'right_value': 'rebuild3=gps_bias / not baseline',
        'explanation': 'rebuild3 用对象自身空间稳定性替代旧 Cell-BS 硬阈值。',
    },
    {
        'object_id': 'cell|46011|5G|409602|417849|1711509512',
        'diff_type': 'baseline_membership',
        'scope': 'sample',
        'title': 'r3_only baseline Cell',
        'left_value': 'rebuild2=gps_bias / not baseline',
        'right_value': 'rebuild3=healthy / baseline',
        'explanation': '在 rebuild3 画像 P90 口径下恢复为 healthy。',
    },
]

FULL_DIFFS = [
    {
        'object_id': 'cell|46000|4G|4116|358983|91899852',
        'diff_type': 'baseline_membership',
        'scope': 'full',
        'title': 'r3_only baseline Cell',
        'left_value': 'rebuild2=gps_bias / not baseline',
        'right_value': 'rebuild3=healthy / baseline',
        'explanation': '共同空间指标稳定，差异来自 gps_bias 规则收敛。',
    },
    {
        'object_id': 'fact_pending_issue',
        'diff_type': 'route_distribution',
        'scope': 'full',
        'title': '问题池扩大',
        'left_value': 'rebuild2=1789244',
        'right_value': 'rebuild3=3825562',
        'explanation': 'rebuild3 明确把 gps_bias 路由到问题池。',
    },
]


@router.get('/overview')
def get_compare_overview():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **fallback_contract('report_fallback', 'validation_reference', '当前为 fallback 对照结果，仅供参考，不代表实时比对结果'),
        'scopes': [SAMPLE_OVERVIEW, FULL_OVERVIEW],
    }


@router.get('/diffs')
def get_compare_diffs():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **fallback_contract('report_fallback', 'validation_reference', '当前为 fallback 对照结果，仅供参考，不代表实时比对结果'),
        'sample': SAMPLE_DIFFS,
        'full': FULL_DIFFS,
    }
