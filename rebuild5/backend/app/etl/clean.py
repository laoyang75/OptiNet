"""Step 1.2: Clean parsed records."""
from __future__ import annotations

from typing import Any

from ..core.database import execute, fetchone

CLEAN_STAGE_TABLE = 'rebuild5.etl_clean_stage'
FINAL_ROW_FILTER = "cell_id IS NULL OR event_time_std IS NULL"

ODS_RULES = [
    {"id": "ODS-001", "name": "垃圾运营商编码置空", "field": "operator_code", "action": "nullify", "where": "operator_code IS NOT NULL AND (BTRIM(operator_code) = '' OR BTRIM(operator_code) IN ('00000','0','000000','(null)(null)'))", "desc": "明确的垃圾运营商编码"},
    {"id": "ODS-002", "name": "非白名单运营商置空", "field": "operator_code", "action": "nullify", "where": "operator_code IS NOT NULL AND operator_code NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020')", "desc": "运营商编码不在有效白名单内"},
    {"id": "ODS-003", "name": "LAC=0 置空", "field": "lac", "action": "nullify", "where": "lac = 0", "desc": "LAC=0 表示无效"},
    {"id": "ODS-004", "name": "4G LAC 保留值置空", "field": "lac", "action": "nullify", "where": "lac IN (65534, 65535) AND tech_norm = '4G'", "desc": "4G 16bit 保留值 0xFFFE/0xFFFF"},
    {"id": "ODS-004b", "name": "5G LAC 保留值置空", "field": "lac", "action": "nullify", "where": "lac IN (16777214, 16777215) AND tech_norm = '5G'", "desc": "5G 24bit 保留值 0xFFFFFE/0xFFFFFF"},
    {"id": "ODS-005", "name": "LAC 溢出值置空", "field": "lac", "action": "nullify", "where": "lac IN (268435455, 2147483647)", "desc": "LAC 28bit/INT_MAX 溢出值"},
    {"id": "ODS-006", "name": "CellID<=0 删行", "field": "cell_id", "action": "delete", "where": "cell_id <= 0", "desc": "无有效小区标识（0 或负值，负值如 -1 会被下游派生出 bs_id=0 污染 BS/LAC 聚合）"},
    {"id": "ODS-007", "name": "5G CellID 溢出值删行", "field": "cell_id", "action": "delete", "where": "cell_id = 268435455 AND tech_norm = '5G'", "desc": "5G CellID 溢出值"},
    {"id": "ODS-008", "name": "4G CellID 溢出值删行", "field": "cell_id", "action": "delete", "where": "cell_id = 2147483647 AND tech_norm = '4G'", "desc": "4G CellID 溢出值"},
    {"id": "ODS-006a", "name": "4G CellID 过小删行", "field": "cell_id", "action": "delete", "where": "cell_id > 0 AND cell_id < 1000 AND tech_norm = '4G'", "desc": "4G CellID 最小合法值 1000（bs_id=cell_id/256，cell_id<1000 会得到 bs_id<4 的非法基站）"},
    {"id": "ODS-006b", "name": "5G CellID 过小删行", "field": "cell_id", "action": "delete", "where": "cell_id > 0 AND cell_id < 4096 AND tech_norm = '5G'", "desc": "5G CellID 最小合法值 4096（bs_id=cell_id/4096，cell_id<4096 会得到 bs_id=0 的非法基站）"},
    {"id": "ODS-005a", "name": "LAC 过小置空", "field": "lac", "action": "nullify", "where": "lac IS NOT NULL AND lac > 0 AND lac < 100", "desc": "LAC 最小合法值 100（真实 LAC 最少 4 位数，1-99 为垃圾数据）"},
    {"id": "ODS-009", "name": "RSRP 越界置空", "field": "rsrp", "action": "nullify", "where": "rsrp IS NOT NULL AND (rsrp > 0 OR rsrp = 0 OR rsrp < -156)", "desc": "RSRP 合理范围 -156~-1"},
    {"id": "ODS-010", "name": "RSRQ 越界置空", "field": "rsrq", "action": "nullify", "where": "rsrq IS NOT NULL AND (rsrq > 10 OR rsrq < -34)", "desc": "RSRQ 合理范围 -34~10"},
    {"id": "ODS-011", "name": "SINR 越界置空", "field": "sinr", "action": "nullify", "where": "sinr IS NOT NULL AND (sinr > 40 OR sinr < -23)", "desc": "SINR 合理范围 -23~40"},
    {"id": "ODS-012", "name": "Dbm 越界置空", "field": "dbm", "action": "nullify", "where": "dbm IS NOT NULL AND (dbm > 0 OR dbm = 0)", "desc": "Dbm 应为负数"},
    {"id": "ODS-013", "name": "非原生 GPS 标记无效", "field": "gps_valid", "action": "flag_gps", "where": "gps_info_type IS NULL OR gps_info_type NOT IN ('gps', '1')", "desc": "仅信任原生 GPS"},
    {"id": "ODS-014", "name": "非原生 GPS 经纬度置空", "field": "lon_raw", "action": "nullify_pair", "where": "gps_valid = false AND lon_raw IS NOT NULL", "desc": "无效 GPS 坐标不参与空间计算"},
    {"id": "ODS-015", "name": "经度越界标记", "field": "gps_valid", "action": "flag_gps", "where": "lon_raw IS NOT NULL AND (lon_raw < 73 OR lon_raw > 135)", "desc": "经度有效范围 73~135"},
    {"id": "ODS-016", "name": "纬度越界标记", "field": "gps_valid", "action": "flag_gps", "where": "lat_raw IS NOT NULL AND (lat_raw < 3 OR lat_raw > 54)", "desc": "纬度有效范围 3~54"},
    {"id": "ODS-017", "name": "无效 WiFi 名称置空", "field": "wifi_name", "action": "nullify", "where": "wifi_name IN ('<unknown ssid>', 'unknown', '')", "desc": "占位符 WiFi 名称无价值"},
    {"id": "ODS-018", "name": "无效 WiFi MAC 置空", "field": "wifi_mac", "action": "nullify", "where": "wifi_mac IN ('02:00:00:00:00:00', '00:00:00:00:00:00', '')", "desc": "全零或随机化 MAC 无价值"},
]


def step1_clean() -> dict[str, Any]:
    """Apply ODS cleaning rules to etl_parsed → etl_clean_stage."""
    input_count_row = fetchone('SELECT COUNT(*) AS cnt FROM rebuild5.etl_parsed')
    input_count = int(input_count_row['cnt']) if input_count_row else 0

    execute(f'DROP TABLE IF EXISTS {CLEAN_STAGE_TABLE}')
    execute(f'CREATE TABLE {CLEAN_STAGE_TABLE} AS SELECT * FROM rebuild5.etl_parsed')
    execute(f'ALTER TABLE {CLEAN_STAGE_TABLE} SET (autovacuum_enabled = false)')

    rule_stats: list[dict[str, Any]] = []
    deleted_rows_total = 0
    for rule in ODS_RULES:
        count_row = fetchone(f"SELECT COUNT(*) AS cnt FROM {CLEAN_STAGE_TABLE} WHERE {rule['where']}")
        violations = int(count_row['cnt']) if count_row else 0
        if violations > 0:
            if rule['action'] == 'nullify':
                execute(f"UPDATE {CLEAN_STAGE_TABLE} SET {rule['field']} = NULL WHERE {rule['where']}")
            elif rule['action'] == 'delete':
                execute(f"DELETE FROM {CLEAN_STAGE_TABLE} WHERE {rule['where']}")
                deleted_rows_total += violations
            elif rule['action'] == 'nullify_pair':
                execute(f"UPDATE {CLEAN_STAGE_TABLE} SET lon_raw = NULL, lat_raw = NULL WHERE {rule['where']}")
            elif rule['action'] == 'flag_gps':
                execute(f"UPDATE {CLEAN_STAGE_TABLE} SET gps_valid = false WHERE {rule['where']}")
        rule_stats.append({
            'id': rule['id'],
            'name': rule['name'],
            'desc': rule['desc'],
            'violations': violations,
            'deleted_rows': violations if rule['action'] == 'delete' else 0,
            'pass_rate': round((input_count - violations) / input_count, 4) if input_count else 0,
        })

    execute(
        """
        ALTER TABLE rebuild5.etl_clean_stage
            ADD COLUMN IF NOT EXISTS bs_id bigint,
            ADD COLUMN IF NOT EXISTS sector_id bigint,
            ADD COLUMN IF NOT EXISTS operator_cn text,
            ADD COLUMN IF NOT EXISTS report_ts timestamptz,
            ADD COLUMN IF NOT EXISTS cell_ts_std timestamptz,
            ADD COLUMN IF NOT EXISTS gps_ts timestamptz,
            ADD COLUMN IF NOT EXISTS event_time_std timestamptz,
            ADD COLUMN IF NOT EXISTS event_time_source text,
            ADD COLUMN IF NOT EXISTS has_cell_id boolean
        """
    )
    execute(
        """
        UPDATE rebuild5.etl_clean_stage SET
            bs_id = CASE
                WHEN cell_id IS NOT NULL AND tech_norm = '5G' THEN cell_id / 4096
                WHEN cell_id IS NOT NULL THEN cell_id / 256
            END,
            sector_id = CASE
                WHEN cell_id IS NOT NULL AND tech_norm = '5G' THEN cell_id % 4096
                WHEN cell_id IS NOT NULL THEN cell_id % 256
            END,
            operator_cn = CASE operator_code
                WHEN '46000' THEN '中国移动' WHEN '46002' THEN '中国移动' WHEN '46007' THEN '中国移动'
                WHEN '46001' THEN '中国联通' WHEN '46006' THEN '中国联通' WHEN '46009' THEN '中国联通'
                WHEN '46003' THEN '中国电信' WHEN '46005' THEN '中国电信' WHEN '46011' THEN '中国电信'
                WHEN '46015' THEN '中国广电' WHEN '46020' THEN '中国铁路'
            END,
            has_cell_id = (cell_id IS NOT NULL AND cell_id != 0)
        """
    )
    execute(f"UPDATE {CLEAN_STAGE_TABLE} SET report_ts = CASE WHEN ts_raw ~ '^\\d{{4}}-' THEN ts_raw::timestamptz END")
    execute(f"UPDATE {CLEAN_STAGE_TABLE} SET cell_ts_std = CASE WHEN cell_origin = 'ss1' AND cell_ts_raw ~ '^\\d{{10}}$' THEN to_timestamp(cell_ts_raw::bigint) END")
    execute(f"UPDATE {CLEAN_STAGE_TABLE} SET gps_ts = CASE WHEN gps_ts_raw ~ '^\\d{{13}}$' THEN to_timestamp(gps_ts_raw::bigint / 1000.0) END")
    execute(
        """
        UPDATE rebuild5.etl_clean_stage SET
            event_time_std = COALESCE(cell_ts_std, report_ts, gps_ts),
            event_time_source = CASE
                WHEN cell_ts_std IS NOT NULL THEN 'cell_ts'
                WHEN report_ts IS NOT NULL THEN 'report_ts'
                WHEN gps_ts IS NOT NULL THEN 'gps_ts'
            END
        """
    )

    deleted = fetchone(f"WITH d AS (DELETE FROM {CLEAN_STAGE_TABLE} WHERE {FINAL_ROW_FILTER} RETURNING 1) SELECT COUNT(*) AS cnt FROM d")
    filtered_count = deleted_rows_total + (int(deleted['cnt']) if deleted else 0)
    output_count_row = fetchone(f'SELECT COUNT(*) AS cnt FROM {CLEAN_STAGE_TABLE}')
    output_count = int(output_count_row['cnt']) if output_count_row else 0

    return {
        'input_count': input_count,
        'output_count': output_count,
        'filtered_count': filtered_count,
        'rules': rule_stats,
    }
