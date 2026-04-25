"""Read models for rebuild5 Step 1 ETL pages."""
from __future__ import annotations

from typing import Any

from .definitions import L0_FIELD_DEFINITIONS, RAW_FIELD_DEFINITIONS, get_l0_field_groups, summarize_decisions
from .source_prep import DATASET_KEY
from ..core.database import fetchall, fetchone


FIELD_SAMPLES = {
    'cell_id': '110221443',
    'lac': '58669',
    'bs_id': '430552',
    'operator_code': '46001',
    'tech_norm': '4G',
    'rsrp': '-94',
    'lon_raw': '116.065178',
    'lat_raw': '39.991146',
    'rsrq': '-8',
    'sinr': '8',
    'pressure': '1013.25',
    'wifi_mac': 'AA:BB:CC:DD:EE:FF',
}

FIELD_AUDIT_VIEW = [
    ('cell_id', 'bigint', 'keep'),
    ('lac', 'bigint', 'keep'),
    ('bs_id', 'bigint', 'parse'),
    ('operator_code', 'varchar', 'keep'),
    ('tech_norm', 'varchar', 'parse'),
    ('rsrp', 'int', 'keep'),
    ('lon_raw', 'float8', 'keep'),
    ('lat_raw', 'float8', 'keep'),
    ('rsrq', 'int', 'keep'),
    ('sinr', 'int', 'keep'),
    ('pressure', 'varchar', 'keep'),
    ('wifi_mac', 'varchar', 'drop'),
]


def _missing_relation(exc: Exception) -> bool:
    text = str(exc)
    return 'does not exist' in text or 'UndefinedTable' in text


def _latest_stats() -> dict[str, Any] | None:
    try:
        return fetchone(
            """
            SELECT *
            FROM rb5_meta.step1_run_stats
            WHERE dataset_key = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (DATASET_KEY,),
        )
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise


def _active_sources() -> list[dict[str, Any]]:
    try:
        return fetchall(
            """
            SELECT source_id, source_name, source_table, source_type, row_count, status, imported_at
            FROM rb5_meta.source_registry
            WHERE dataset_key = %s
            ORDER BY source_id
            """,
            (DATASET_KEY,),
        )
    except Exception as exc:
        if _missing_relation(exc):
            return []
        raise


def build_etl_stats_payload(latest_stats: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'source_count': len(sources),
        'raw_record_count': int(latest_stats['raw_record_count']),
        'parsed_record_count': int(latest_stats['parsed_record_count']),
        'cleaned_record_count': int(latest_stats['cleaned_record_count']),
        'filled_record_count': int(latest_stats['filled_record_count']),
        'clean_pass_rate': float(latest_stats['clean_pass_rate']),
        'field_coverage': latest_stats['field_coverage'],
    }


def build_clean_rule_rows(clean_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            'rule_id': rule['id'],
            'rule_name': rule['name'],
            'description': rule['desc'],
            'hit_count': int(rule['violations']),
            'drop_count': int(rule.get('deleted_rows', 0)),
            'pass_rate': float(rule['pass_rate']),
        }
        for rule in clean_rules
    ]


def get_etl_source_payload() -> dict[str, Any]:
    sources = _active_sources()
    summary = {
        'source_count': len(sources),
        'raw_record_count': sum(int(source['row_count']) for source in sources),
        'last_sync': max((source['imported_at'] or '' for source in sources), default=''),
    }
    mapped_sources = [
        {
            'id': source['source_id'],
            'name': source['source_name'],
            'type': source['source_type'],
            'table': source['source_table'],
            'status': source['status'],
            'records': int(source['row_count']),
            'lastSync': source['imported_at'],
            'fields': 27,
        }
        for source in sources
    ]
    return {'sources': mapped_sources, 'summary': summary}


def get_field_audit_payload() -> dict[str, Any]:
    groups = get_l0_field_groups()
    category_summary = {g['category']: g['count'] for g in groups}
    return {
        'total_field_count': len(L0_FIELD_DEFINITIONS),
        'raw_field_count': len(RAW_FIELD_DEFINITIONS),
        'category_summary': category_summary,
        'groups': groups,
        'decision_summary': summarize_decisions(RAW_FIELD_DEFINITIONS),
    }


def get_etl_stats_page_payload() -> dict[str, Any]:
    latest = _latest_stats()
    sources = _active_sources()
    if not latest:
        return {
            'summary': {
                'source_count': len(sources),
                'raw_record_count': sum(int(source['row_count']) for source in sources),
                'parsed_record_count': 0,
                'cleaned_record_count': 0,
                'filled_record_count': 0,
                'clean_pass_rate': 0,
                'field_coverage': {},
            },
            'parse': {'inputRecords': 0, 'outputRecords': 0, 'expansionRatio': 0, 'sources': []},
            'clean': {'inputRecords': 0, 'passedRecords': 0, 'deletedRecords': 0, 'passRate': 0},
            'fill': {'totalRecords': 0},
        }
    parse_details = latest.get('parse_details') or {}
    fill_details = latest.get('fill_details') or {}
    before_coverage = latest.get('field_coverage_before') or {}
    after_coverage = latest.get('field_coverage') or {}

    raw_count = int(latest['raw_record_count'])
    ci_count = int(parse_details.get('ci', parse_details.get('ci_gps', 0)))
    ss1_count = int(parse_details.get('ss1', parse_details.get('ss1_gps', 0)))

    def _ratio(output: int, input_: int) -> float:
        return round(output / input_, 2) if input_ else 0

    return {
        'summary': build_etl_stats_payload(latest, sources),
        'parse': {
            'inputRecords': raw_count,
            'outputRecords': int(latest['parsed_record_count']),
            'expansionRatio': _ratio(int(latest['parsed_record_count']), raw_count),
            'sources': [
                {'name': 'cell_infos', 'inputCount': raw_count, 'outputCount': ci_count, 'ratio': _ratio(ci_count, raw_count)},
                {'name': 'ss1', 'inputCount': raw_count, 'outputCount': ss1_count, 'ratio': _ratio(ss1_count, raw_count)},
            ],
            'coverageChange': [
                {'field': 'cell_id', 'before': 1.0, 'after': float(after_coverage.get('cell_id', 0))},
                {'field': 'lac', 'before': 1.0, 'after': float(after_coverage.get('lac', 0))},
                {'field': 'operator_code', 'before': float(before_coverage.get('operator_code', 0)), 'after': float(after_coverage.get('operator_code', 0))},
                {'field': 'tech_norm', 'before': 0, 'after': float(after_coverage.get('tech_norm', 0))},
                {'field': 'bs_id', 'before': 0, 'after': float(after_coverage.get('bs_id', 0))},
                {'field': 'rsrp', 'before': float(before_coverage.get('rsrp', 0)), 'after': float(after_coverage.get('rsrp', 0))},
                {'field': 'lon / lat', 'before': float(before_coverage.get('lon_raw', 0)), 'after': float(after_coverage.get('lon_raw', 0))},
            ],
        },
        'clean': {
            'inputRecords': int(latest['parsed_record_count']),
            'passedRecords': int(latest['cleaned_record_count']),
            'deletedRecords': int(latest['clean_deleted_count']),
            'passRate': float(latest['clean_pass_rate']),
        },
        'fill': fill_details,
    }


def get_etl_coverage_payload() -> dict[str, Any]:
    latest = _latest_stats() or {}
    before = latest.get('field_coverage_before') or {}
    after = latest.get('field_coverage') or {}

    # Read from cached fill_details in step1_run_stats (avoid full-table scan on 45M+ rows)
    fill_details = latest.get('fill_details') or {}
    fill_after = fill_details.get('after') or {}
    fill_before = fill_details.get('before') or {}
    total = int(fill_after.get('total', 0)) or int(latest.get('cleaned_record_count', 0))

    # GPS source distribution from cached fill_details
    gps_raw = int(fill_after.get('gps_raw_gps', 0))
    gps_ss1 = int(fill_after.get('gps_ss1_own', 0))
    gps_same_cell = total - gps_raw - gps_ss1 - int(fill_after.get('gps_none', 0))
    if gps_same_cell < 0:
        gps_same_cell = 0
    gps_none = int(fill_after.get('gps_none', 0))

    def _count_and_pct(count: int, total_: int) -> dict[str, Any]:
        return {'count': count, 'rate': round(count / total_, 4) if total_ else 0}

    return {
        'fields': [
            {
                'field': 'GPS（lon/lat）',
                'before': float(before.get('lon_raw', 0)),
                'after': float(after.get('lon_filled', 0)),
                'before_count': int(fill_before.get('has_gps', 0)),
                'filled_count': int(fill_after.get('gps_filled', 0)),
                'source': 'same_cell / ss1_own',
                'note': '同报文内 GPS 互补，时间差 ≤ 60s',
            },
            {
                'field': 'RSRP',
                'before': float(before.get('rsrp', 0)),
                'after': float(after.get('rsrp_filled', 0)),
                'before_count': int(fill_before.get('has_rsrp', 0)),
                'filled_count': int(fill_after.get('rsrp_filled', 0)),
                'source': 'same_cell',
                'note': '同报文内信号互补，时间差 ≤ 60s',
            },
            {
                'field': '运营商编码',
                'before': float(before.get('operator_code', 0)),
                'after': float(after.get('operator_filled', 0)),
                'before_count': int(fill_before.get('has_operator', 0)),
                'filled_count': int(fill_after.get('operator_filled', 0)),
                'source': 'same_cell',
                'note': '总是可补（不受时间约束）',
            },
            {
                'field': 'LAC',
                'before': float(before.get('lac', 0)),
                'after': float(after.get('lac_filled', 0)),
                'before_count': int(fill_before.get('has_lac', 0)),
                'filled_count': int(fill_after.get('lac_filled', 0)),
                'source': 'same_cell',
                'note': '总是可补（不受时间约束）',
            },
        ],
        'source_distribution': {
            'raw_gps': _count_and_pct(gps_raw, total),
            'ss1_own': _count_and_pct(gps_ss1, total),
            'same_cell': _count_and_pct(gps_same_cell, total),
            'none': _count_and_pct(gps_none, total),
        },
        'total_records': total,
        'time_window_seconds': 60,
    }


def get_clean_rules_payload() -> dict[str, Any]:
    latest = _latest_stats() or {
        'clean_rules': [], 'parsed_record_count': 0, 'cleaned_record_count': 0,
        'clean_deleted_count': 0, 'clean_pass_rate': 0, 'parse_details': {},
    }
    rows = build_clean_rule_rows(latest.get('clean_rules') or [])

    # ODS-019 is enforced during parse (cell_infos JSON expansion), not in
    # clean.ODS_RULES. Surface its drop count here so the UI shows the full
    # 20-rule ODS set for the latest run. See rule doc: 01b_数据源接入_处理规则.md
    parse_details = latest.get('parse_details') or {}
    ods_019 = parse_details.get('ods_019') if isinstance(parse_details, dict) else None
    if ods_019:
        total = int(ods_019.get('total_connected_objects') or 0)
        dropped = int(ods_019.get('dropped_stale_count') or 0)
        max_age = ods_019.get('max_age_sec', 300)
        rows.append({
            'rule_id': 'ODS-019',
            'rule_name': 'CellInfos 陈旧缓存过滤',
            'description': (
                f'past_time - timeStamp/1000 > {max_age}s 的对象视为设备启动后的历史缓存，'
                f'解析阶段直接丢弃；字段缺失时按 KEEP'
            ),
            'hit_count': dropped,
            'drop_count': dropped,
            'pass_rate': round((total - dropped) / total, 4) if total else 1.0,
        })

    # SS1 解析规则（ODS-020 批内锚点时间过滤 / ODS-021 INNER JOIN tech 匹配 / ODS-022 全 -1 sig 过滤）
    ss1_rules = parse_details.get('ss1_rules') if isinstance(parse_details, dict) else None
    if ss1_rules:
        max_age = ss1_rules.get('max_age_from_anchor_sec', 3600)
        ods_020 = ss1_rules.get('ods_020') or {}
        total_sub = int(ods_020.get('total_subrec') or 0)
        dropped_sub = int(ods_020.get('dropped_subrec') or 0)
        rows.append({
            'rule_id': 'ODS-020',
            'rule_name': 'SS1 批内锚点陈旧过滤',
            'description': (
                f'ss1 子记录按批内 max(ts_sec) 为锚点，age > {max_age}s 的子记录视为 SDK 历史残留丢弃'
            ),
            'hit_count': dropped_sub,
            'drop_count': dropped_sub,
            'pass_rate': round((total_sub - dropped_sub) / total_sub, 4) if total_sub else 1.0,
        })
        # ODS-021 走 INNER JOIN，丢 cell 的量级需要对 cells×sigs 联合估算，
        # 这里只提示规则存在（drop 量在下游 emit 差值里体现）。
        rows.append({
            'rule_id': 'ODS-021',
            'rule_name': 'SS1 无信号 Cell 过滤（tech 匹配）',
            'description': (
                'INNER JOIN 要求 sig_tech = cell_tech；无配套信号的 cell（SDK 缓存 cell_id）不 emit'
            ),
            'hit_count': 0,
            'drop_count': 0,
            'pass_rate': 1.0,
        })
        ods_022 = ss1_rules.get('ods_022') or {}
        total_sigs = int(ods_022.get('total_sigs') or 0)
        dropped_sigs = int(ods_022.get('dropped_sigs') or 0)
        rows.append({
            'rule_id': 'ODS-022',
            'rule_name': 'SS1 全 -1 Sig 条目过滤',
            'description': 'ss/rsrp/rsrq/sinr 四个值全为 -1 的 sig 条目视为无效，丢弃整条 sig',
            'hit_count': dropped_sigs,
            'drop_count': dropped_sigs,
            'pass_rate': round((total_sigs - dropped_sigs) / total_sigs, 4) if total_sigs else 1.0,
        })

    return {
        'rules': rows,
        'summary': {
            'inputRecords': int(latest.get('parsed_record_count', 0)),
            'passedRecords': int(latest.get('cleaned_record_count', 0)),
            'deletedRecords': int(latest.get('clean_deleted_count', 0)),
            'passRate': float(latest.get('clean_pass_rate', 0)),
        },
    }
