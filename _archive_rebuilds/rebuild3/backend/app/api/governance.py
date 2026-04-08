from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.common import now_iso
from app.api.run_shared import fallback_contract

router = APIRouter(prefix='/api/v1/governance', tags=['governance'])

OVERVIEW = {
    'table_count': 16,
    'field_count': 28,
    'usage_count': 23,
    'migration_pending': 6,
    'core_tables': 10,
    'reference_assets': 4,
    'core_field_count': 8,
    'direct_reuse_count': 8,
}

FIELDS = [
    {'asset_name': 'obj_cell', 'field_name': 'lifecycle_state', 'layer': '对象', 'type': 'text', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'obj_cell', 'field_name': 'health_state', 'layer': '对象', 'type': 'text', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'obj_cell', 'field_name': 'anchorable', 'layer': '对象', 'type': 'boolean', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'obj_cell', 'field_name': 'baseline_eligible', 'layer': '对象', 'type': 'boolean', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'fact_governed', 'field_name': 'gps_source', 'layer': '事实', 'type': 'text', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'fact_governed', 'field_name': 'signal_source', 'layer': '事实', 'type': 'text', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'batch_snapshot', 'field_name': 'metric_name', 'layer': '元数据', 'type': 'text', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'batch_snapshot', 'field_name': 'metric_value', 'layer': '元数据', 'type': 'numeric', 'is_core': True, 'migration': 'direct'},
    {'asset_name': 'r2_full_profile_bs', 'field_name': 'classification_v2', 'layer': '参考', 'type': 'text', 'is_core': False, 'migration': 'reference'},
    {'asset_name': 'obj_lac', 'field_name': 'region_quality_label', 'layer': '对象', 'type': 'text', 'is_core': False, 'migration': 'restructure'},
]

TABLES = [
    {'table_name': 'rebuild3.obj_cell', 'table_type': '对象快照表', 'migration': 'direct_reuse', 'usage': '对象浏览 / 详情 / 画像'},
    {'table_name': 'rebuild3.obj_bs', 'table_type': '对象快照表', 'migration': 'direct_reuse', 'usage': '对象浏览 / 详情 / BS 画像'},
    {'table_name': 'rebuild3.obj_lac', 'table_type': '对象快照表', 'migration': 'direct_reuse', 'usage': '对象浏览 / LAC 画像'},
    {'table_name': 'rebuild3.fact_governed', 'table_type': '事实表', 'migration': 'direct_reuse', 'usage': '流转总览 / 详情 / 异常解释'},
    {'table_name': 'rebuild3.fact_pending_observation', 'table_type': '事实表', 'migration': 'direct_reuse', 'usage': '等待 / 观察工作台'},
    {'table_name': 'rebuild3.fact_pending_issue', 'table_type': '事实表', 'migration': 'direct_reuse', 'usage': '异常工作台'},
    {'table_name': 'rebuild3.fact_rejected', 'table_type': '事实表', 'migration': 'direct_reuse', 'usage': '异常工作台 / 运行中心'},
    {'table_name': 'rebuild3_meta.batch_snapshot', 'table_type': '元数据表', 'migration': 'direct_reuse', 'usage': '流转总览 / 运行中心'},
    {'table_name': 'rebuild3_meta.batch_anomaly_summary', 'table_type': '元数据表', 'migration': 'restructure', 'usage': '异常工作台'},
    {'table_name': 'rebuild3_meta.compare_result', 'table_type': '元数据表', 'migration': 'restructure', 'usage': '验证 / 对照（当前为空）'},
    {'table_name': 'rebuild3_meta.r2_full_profile_bs', 'table_type': '研究表', 'migration': 'reference_only', 'usage': 'BS / Cell 解释层'},
    {'table_name': 'rebuild3_sample_meta.batch_snapshot', 'table_type': '元数据表', 'migration': 'direct_reuse', 'usage': '初始化页'},
]

USAGE = {
    'rebuild3.obj_cell': {
        'consumers': [
            {'consumer_type': 'page', 'consumer_name': '对象浏览', 'role': '主列表'},
            {'consumer_type': 'page', 'consumer_name': '对象详情', 'role': '主快照'},
            {'consumer_type': 'page', 'consumer_name': 'Cell 画像', 'role': '统一状态源'},
            {'consumer_type': 'api', 'consumer_name': '/api/v1/objects/*', 'role': '读模型主表'},
        ],
        'upstream': ['rebuild3.fact_*', 'rebuild3.stg_cell_profile'],
        'notes': ['当前是正式对象层主表。'],
    },
    'rebuild3_meta.batch_snapshot': {
        'consumers': [
            {'consumer_type': 'page', 'consumer_name': '流转总览', 'role': '关键指标'},
            {'consumer_type': 'page', 'consumer_name': '运行 / 批次中心', 'role': '批次详情'},
        ],
        'upstream': ['rebuild3/backend/sql/govern/*.sql'],
        'notes': ['当前已灌数，可直接使用。'],
    },
}

MIGRATION = {
    'direct_reuse': ['obj_cell', 'obj_bs', 'obj_lac', 'fact_governed', 'fact_pending_observation', 'fact_pending_issue', 'fact_rejected', 'batch_snapshot'],
    'restructure': ['batch_anomaly_summary', 'compare_result', 'asset_table_catalog', 'asset_field_catalog', 'asset_usage_map', 'asset_migration_decision'],
    'reference_only': ['r2_full_profile_bs', 'r2_full_profile_cell', 'r2_full_profile_lac', 'stg_bs_classification_ref'],
    'retire': ['frontend Cell spike 页面', 'launcher/README 占位'],
}

CONTRACT = fallback_contract('fallback_catalog', 'asset_catalog', '当前为 fallback 资产目录，仅供梳理，不代表已接入实时元数据注册表')


@router.get('/overview')
def get_governance_overview():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **CONTRACT,
        'overview': OVERVIEW,
    }


@router.get('/fields')
def get_governance_fields():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **CONTRACT,
        'rows': FIELDS,
    }


@router.get('/tables')
def get_governance_tables():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **CONTRACT,
        'rows': TABLES,
    }


@router.get('/usage/{table_name:path}')
def get_governance_usage(table_name: str):
    if table_name not in USAGE:
        table_row = next((row for row in TABLES if row['table_name'] == table_name), None)
        if not table_row:
            raise HTTPException(status_code=404, detail='未收录该表的使用信息')
        usage_text = [part.strip() for part in str(table_row['usage']).split('/')]
        detail = {
            'consumers': [
                {'consumer_type': 'page', 'consumer_name': name, 'role': '登记用途'}
                for name in usage_text
                if name
            ],
            'upstream': ['待补充登记'],
            'notes': ['当前来自 fallback_catalog 自动生成，待元数据注册表补完。'],
        }
    else:
        detail = USAGE[table_name]
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **CONTRACT,
        'table_name': table_name,
        'detail': detail,
    }


@router.get('/migration')
def get_governance_migration():
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        **CONTRACT,
        'groups': MIGRATION,
    }
