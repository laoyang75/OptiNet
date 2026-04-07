"""ETL Pipeline: 解析 → 清洗 → 补齐。

每一步是独立的简单 SQL，Python 只做编排和统计。
SQL 设计原则：单一、简单、易迁移，不用复杂嵌套 CTE。
"""
from dataclasses import dataclass, field
from typing import Optional
from ..core.database import execute, fetchone, fetchall


@dataclass
class StepResult:
    """单步执行结果。"""
    step: str
    input_count: int = 0
    output_count: int = 0
    filtered_count: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class EtlResult:
    """完整 ETL 结果。"""
    scope: str
    steps: list = field(default_factory=list)

    @property
    def summary(self):
        return {s.step: {"in": s.input_count, "out": s.output_count, "filtered": s.filtered_count} for s in self.steps}


def run_etl(scope: str = "sample") -> EtlResult:
    """运行完整 ETL 管道：解析 → 清洗 → 补齐。"""
    result = EtlResult(scope=scope)

    if scope == "sample":
        raw_gps = "rebuild4.sample_raw_gps"
        raw_lac = "rebuild4.sample_raw_lac"
    else:
        raise ValueError(f"Unknown scope: {scope}")

    # Step 1: 解析
    r1 = step1_parse(raw_gps, raw_lac)
    result.steps.append(r1)

    # Step 2: 清洗
    r2 = step2_clean()
    result.steps.append(r2)

    # Step 3: 补齐
    r3 = step3_fill()
    result.steps.append(r3)

    # 写入统计表
    _save_stats(result)

    return result


def _save_stats(result: EtlResult):
    """将 ETL 结果写入 rebuild4_meta.etl_run_stats。"""
    import json
    r1 = result.steps[0]  # parse
    r2 = result.steps[1]  # clean
    r3 = result.steps[2]  # fill
    execute("""
        INSERT INTO rebuild4_meta.etl_run_stats (
            scope, raw_input_count, parsed_output_count,
            ci_gps_count, ci_lac_count, ss1_gps_count, ss1_lac_count,
            clean_input_count, clean_output_count, clean_deleted_count, clean_rules,
            fill_total, fill_before_gps, fill_before_rsrp,
            fill_gps_original, fill_gps_filled, fill_gps_none, fill_gps_rate,
            fill_rsrp_original, fill_rsrp_filled, fill_rsrp_none, fill_rsrp_rate
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """, (
        result.scope, r1.input_count, r1.output_count,
        r1.details.get("ci_gps", 0), r1.details.get("ci_lac", 0),
        r1.details.get("ss1_gps", 0), r1.details.get("ss1_lac", 0),
        r2.input_count, r2.output_count, r2.filtered_count,
        json.dumps(r2.details.get("rules", []), ensure_ascii=False),
        r3.output_count,
        r3.details.get("before", {}).get("has_gps", 0),
        r3.details.get("before", {}).get("has_rsrp", 0),
        r3.details.get("after", {}).get("gps_original", 0),
        r3.details.get("after", {}).get("gps_filled", 0),
        r3.details.get("after", {}).get("gps_none", 0),
        r3.details.get("after", {}).get("gps_rate", 0),
        r3.details.get("after", {}).get("rsrp_original", 0),
        r3.details.get("after", {}).get("rsrp_filled", 0),
        r3.details.get("after", {}).get("rsrp_none", 0),
        r3.details.get("after", {}).get("rsrp_rate", 0),
    ))


# ============================================================
# Step 1: 解析（炸开）
# ============================================================

def step1_parse(raw_gps: str, raw_lac: str) -> StepResult:
    """解析原始数据：cell_infos JSON + ss1 文本 → etl_parsed。"""
    result = StepResult(step="parse")

    # 统计原始行数
    raw_count = fetchone(f"""
        SELECT
            (SELECT COUNT(*) FROM {raw_gps}) +
            (SELECT COUNT(*) FROM {raw_lac}) as total
    """)
    result.input_count = raw_count["total"]

    # 1a: cell_infos 解析（GPS 表）
    _parse_cell_infos(raw_gps, "rebuild4.etl_ci_gps")
    # 1b: cell_infos 解析（LAC 表）
    _parse_cell_infos(raw_lac, "rebuild4.etl_ci_lac")
    # 1c: ss1 解析（GPS 表）
    _parse_ss1(raw_gps, "rebuild4.etl_ss1_gps")
    # 1d: ss1 解析（LAC 表）
    _parse_ss1(raw_lac, "rebuild4.etl_ss1_lac")

    # 1e: 合并四张表 → etl_parsed
    execute("DROP TABLE IF EXISTS rebuild4.etl_parsed")
    execute("""
        CREATE TABLE rebuild4.etl_parsed AS
        SELECT * FROM rebuild4.etl_ci_gps
        UNION ALL
        SELECT * FROM rebuild4.etl_ci_lac
        UNION ALL
        SELECT * FROM rebuild4.etl_ss1_gps
        UNION ALL
        SELECT * FROM rebuild4.etl_ss1_lac
    """)

    # 统计产出
    counts = fetchone("""
        SELECT
            (SELECT COUNT(*) FROM rebuild4.etl_ci_gps) as ci_gps,
            (SELECT COUNT(*) FROM rebuild4.etl_ci_lac) as ci_lac,
            (SELECT COUNT(*) FROM rebuild4.etl_ss1_gps) as ss1_gps,
            (SELECT COUNT(*) FROM rebuild4.etl_ss1_lac) as ss1_lac,
            (SELECT COUNT(*) FROM rebuild4.etl_parsed) as total
    """)
    result.output_count = counts["total"]
    result.details = {
        "ci_gps": counts["ci_gps"],
        "ci_lac": counts["ci_lac"],
        "ss1_gps": counts["ss1_gps"],
        "ss1_lac": counts["ss1_lac"],
    }

    return result


def _parse_cell_infos(source_table: str, target_table: str):
    """解析 cell_infos JSON → 每个 isConnected=1 的 cell 一行。完整 55 列。"""
    execute(f"DROP TABLE IF EXISTS {target_table}")
    execute(f"""
        CREATE TABLE {target_table} AS
        SELECT
            r."记录数唯一标识" AS record_id,
            'sdk' AS data_source,
            r."数据来源dna或daa" AS data_source_detail,
            'cell_infos' AS cell_origin,
            -- 网络
            lower(cell->>'type') AS tech_raw,
            CASE lower(cell->>'type')
                WHEN 'lte' THEN '4G' WHEN 'nr' THEN '5G'
                WHEN 'gsm' THEN '2G' WHEN 'wcdma' THEN '3G'
                ELSE lower(cell->>'type')
            END AS tech_norm,
            COALESCE(
                cell->'cell_identity'->>'mno',
                (cell->'cell_identity'->>'mccString') || (cell->'cell_identity'->>'mncString')
            ) AS operator_code,
            COALESCE(
                (cell->'cell_identity'->>'Tac')::bigint,
                (cell->'cell_identity'->>'tac')::bigint,
                (cell->'cell_identity'->>'lac')::bigint,
                (cell->'cell_identity'->>'Lac')::bigint
            ) AS lac,
            COALESCE(
                (cell->'cell_identity'->>'Ci')::bigint,
                (cell->'cell_identity'->>'Nci')::bigint,
                (cell->'cell_identity'->>'nci')::bigint,
                (cell->'cell_identity'->>'cid')::bigint
            ) AS cell_id,
            (cell->'cell_identity'->>'Pci')::int AS pci,
            COALESCE(
                (cell->'cell_identity'->>'Earfcn')::int,
                (cell->'cell_identity'->>'earfcn')::int,
                (cell->'cell_identity'->>'ChannelNumber')::int,
                (cell->'cell_identity'->>'arfcn')::int,
                (cell->'cell_identity'->>'uarfcn')::int
            ) AS freq_channel,
            (cell->'cell_identity'->>'Bwth')::int AS bandwidth,
            -- 信号
            COALESCE((cell->'signal_strength'->>'rsrp')::int, (cell->'signal_strength'->>'SsRsrp')::int) AS rsrp,
            COALESCE((cell->'signal_strength'->>'rsrq')::int, (cell->'signal_strength'->>'SsRsrq')::int) AS rsrq,
            COALESCE((cell->'signal_strength'->>'rssnr')::int, (cell->'signal_strength'->>'SsSinr')::int) AS sinr,
            (cell->'signal_strength'->>'rssi')::int AS rssi,
            (cell->'signal_strength'->>'Dbm')::int AS dbm,
            (cell->'signal_strength'->>'AsuLevel')::int AS asu_level,
            (cell->'signal_strength'->>'Level')::int AS sig_level,
            NULL::int AS sig_ss,
            (cell->'signal_strength'->>'TimingAdvance')::int AS timing_advance,
            (cell->'signal_strength'->>'CsiRsrp')::int AS csi_rsrp,
            (cell->'signal_strength'->>'CsiRsrq')::int AS csi_rsrq,
            (cell->'signal_strength'->>'CsiSinr')::int AS csi_sinr,
            (cell->'signal_strength'->>'cqi')::int AS cqi,
            -- 时间
            r.ts AS ts_raw,
            cell->>'timeStamp' AS cell_ts_raw,
            r."gps上报时间" AS gps_ts_raw,
            -- 位置
            r.gps_info_type,
            CASE WHEN r.gps_info_type IN ('gps','1') THEN true ELSE false END AS gps_valid,
            CASE WHEN r."原始上报gps" IS NOT NULL AND r."原始上报gps" LIKE '%,%'
                THEN split_part(r."原始上报gps", ',', 1)::float8 END AS lon_raw,
            CASE WHEN r."原始上报gps" IS NOT NULL AND r."原始上报gps" LIKE '%,%'
                THEN split_part(r."原始上报gps", ',', 2)::float8 END AS lat_raw,
            'raw_gps' AS gps_filled_from,
            -- 元数据
            r.did AS dev_id,
            r.ip,
            r."主卡运营商id" AS plmn_main,
            r."品牌" AS brand,
            r."机型" AS model,
            r.sdk_ver,
            r.oaid,
            r.pkg_name,
            r.wifi_name,
            r.wifi_mac,
            r.cpu_info,
            r."压力" AS pressure
        FROM {source_table} r,
            jsonb_each(NULLIF(btrim(r.cell_infos), '')::jsonb) e(key, cell)
        WHERE r.cell_infos IS NOT NULL AND length(r.cell_infos) > 5
            AND (e.cell->>'isConnected')::int = 1
            AND COALESCE(
                e.cell->'cell_identity'->>'Ci',
                e.cell->'cell_identity'->>'Nci',
                e.cell->'cell_identity'->>'nci',
                e.cell->'cell_identity'->>'cid'
            ) IS NOT NULL
    """)


def _parse_ss1(source_table: str, target_table: str):
    """解析 ss1 文本 → 按 ; 分组，基站继承（forward-fill），信号按制式匹配。

    分 5 个简单步骤，不用复杂嵌套 CTE。
    """
    prefix = target_table.replace(".", "_")

    # Step A: 按 ; 分组拆行
    execute(f"DROP TABLE IF EXISTS {target_table}_groups")
    execute(f"""
        CREATE TABLE {target_table}_groups AS
        SELECT
            r."记录数唯一标识" AS record_id,
            r."数据来源dna或daa" AS data_source_detail,
            r.ts AS ts_raw,
            r."gps上报时间" AS gps_ts_raw,
            r.gps_info_type,
            r.did AS dev_id,
            r.ip,
            r."主卡运营商id" AS plmn_main,
            r."品牌" AS brand,
            r."机型" AS model,
            r.sdk_ver,
            r.oaid,
            r.pkg_name,
            r.wifi_name,
            r.wifi_mac,
            r.cpu_info,
            r."压力" AS pressure,
            grp,
            grp_idx,
            split_part(grp, '&', 1) AS sig_block,
            split_part(grp, '&', 2) AS ts_block,
            split_part(grp, '&', 3) AS gps_block,
            split_part(grp, '&', 4) AS cell_block
        FROM {source_table} r,
        LATERAL unnest(
            string_to_array(trim(trailing ';' FROM NULLIF(btrim(r.ss1), '')), ';')
        ) WITH ORDINALITY AS t(grp, grp_idx)
        WHERE r.ss1 IS NOT NULL AND length(r.ss1) > 5
    """)

    # Step B: 基站继承（forward-fill）
    execute(f"DROP TABLE IF EXISTS {target_table}_carry")
    execute(f"""
        CREATE TABLE {target_table}_carry AS
        SELECT g.*,
            CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]'
                THEN cell_block ELSE NULL END AS cb_own,
            CASE WHEN cell_block = '1' THEN 'inherited'
                WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]' THEN 'own'
                ELSE 'none' END AS cb_source,
            COALESCE(
                CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]'
                    THEN cell_block ELSE NULL END,
                MAX(CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]'
                    THEN cell_block ELSE NULL END)
                    OVER (PARTITION BY record_id ORDER BY grp_idx
                          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            ) AS cell_block_resolved
        FROM {target_table}_groups g
    """)

    # Step C: 拆基站 + 拆信号，按制式匹配
    execute(f"DROP TABLE IF EXISTS {target_table}")
    execute(f"""
        CREATE TABLE {target_table} AS
        WITH cells AS (
            SELECT c.record_id, c.data_source_detail, c.grp_idx, c.cb_source,
                c.ts_raw, c.ts_block, c.gps_block, c.gps_ts_raw, c.gps_info_type,
                c.sig_block, c.dev_id, c.ip, c.plmn_main, c.brand, c.model,
                c.sdk_ver, c.oaid, c.pkg_name, c.wifi_name, c.wifi_mac, c.cpu_info, c.pressure,
                left(cell_entry, 1) AS cell_tech,
                split_part(cell_entry, ',', 2) AS cid_str,
                split_part(cell_entry, ',', 3) AS lac_str,
                split_part(cell_entry, ',', 4) AS plmn_str
            FROM {target_table}_carry c,
                unnest(string_to_array(rtrim(c.cell_block_resolved, '+'), '+')) AS cell_entry
            WHERE c.cell_block_resolved IS NOT NULL AND c.cell_block_resolved != ''
                AND length(cell_entry) > 2 AND cell_entry ~ '^[lnge],'
                AND split_part(cell_entry, ',', 2) != '-1'
                AND split_part(cell_entry, ',', 2) != ''
        ),
        sigs AS (
            SELECT record_id, grp_idx,
                left(sig_entry, 1) AS sig_tech,
                split_part(sig_entry, ',', 2) AS ss_val,
                split_part(sig_entry, ',', 3) AS rsrp_val,
                split_part(sig_entry, ',', 4) AS rsrq_val,
                split_part(sig_entry, ',', 5) AS sinr_val
            FROM (
                SELECT record_id, grp_idx,
                    unnest(string_to_array(rtrim(sig_block, '+'), '+')) AS sig_entry
                FROM {target_table}_carry
                WHERE sig_block IS NOT NULL AND sig_block != ''
            ) sub
            WHERE length(sig_entry) > 2 AND sig_entry ~ '^[lng]'
        )
        SELECT
            c.record_id,
            'sdk' AS data_source,
            c.data_source_detail,
            'ss1' AS cell_origin,
            c.cell_tech AS tech_raw,
            CASE c.cell_tech
                WHEN 'l' THEN '4G' WHEN 'n' THEN '5G' WHEN 'g' THEN '2G'
                ELSE c.cell_tech
            END AS tech_norm,
            NULLIF(c.plmn_str, '') AS operator_code,
            CASE WHEN c.lac_str ~ '^\d+$' THEN c.lac_str::bigint END AS lac,
            CASE WHEN c.cid_str ~ '^\d+$' THEN c.cid_str::bigint END AS cell_id,
            NULL::int AS pci,
            NULL::int AS freq_channel,
            NULL::int AS bandwidth,
            CASE WHEN s.rsrp_val ~ '^-?\d+$' AND s.rsrp_val != '-1' THEN s.rsrp_val::int END AS rsrp,
            CASE WHEN s.rsrq_val ~ '^-?\d+$' AND s.rsrq_val != '-1' THEN s.rsrq_val::int END AS rsrq,
            CASE WHEN s.sinr_val ~ '^-?\d+$' AND s.sinr_val != '-1' THEN s.sinr_val::int END AS sinr,
            NULL::int AS rssi,
            NULL::int AS dbm,
            NULL::int AS asu_level,
            NULL::int AS sig_level,
            CASE WHEN s.ss_val ~ '^-?\d+$' AND s.ss_val != '-1' THEN s.ss_val::int END AS sig_ss,
            NULL::int AS timing_advance,
            NULL::int AS csi_rsrp,
            NULL::int AS csi_rsrq,
            NULL::int AS csi_sinr,
            NULL::int AS cqi,
            c.ts_raw,
            c.ts_block AS cell_ts_raw,
            c.gps_ts_raw,
            c.gps_info_type,
            CASE WHEN c.gps_block != '0' AND c.gps_block ~ '^\d+\.\d+,\d+\.\d+'
                THEN true ELSE false END AS gps_valid,
            CASE WHEN c.gps_block ~ '^\d+\.\d+,'
                THEN split_part(c.gps_block, ',', 1)::float8 END AS lon_raw,
            CASE WHEN c.gps_block ~ '^\d+\.\d+,\d+\.\d+'
                THEN split_part(c.gps_block, ',', 2)::float8 END AS lat_raw,
            CASE WHEN c.gps_block != '0' AND c.gps_block ~ '^\d+\.\d+,'
                THEN 'ss1_own' ELSE 'none' END AS gps_filled_from,
            c.dev_id,
            c.ip,
            c.plmn_main,
            c.brand,
            c.model,
            c.sdk_ver,
            c.oaid,
            c.pkg_name,
            c.wifi_name,
            c.wifi_mac,
            c.cpu_info,
            c.pressure
        FROM cells c
        LEFT JOIN sigs s
            ON s.record_id = c.record_id
            AND s.grp_idx = c.grp_idx
            AND s.sig_tech = c.cell_tech
    """)

    # 清理中间表
    execute(f"DROP TABLE IF EXISTS {target_table}_groups")
    execute(f"DROP TABLE IF EXISTS {target_table}_carry")


# ============================================================
# Step 2: 清洗（ODS）
# ============================================================

# ── 清洗规则定义 ──
# 对齐 rebuild2 exec_l0_gps.sql L217-278
# 方式：先"置 NULL"（nullify），最后"删除无效 CellID 行"（delete_row）
# 每条规则独立，方便后续增删

ODS_RULES = [
    # ── 运营商 ──
    {"id": "ODS-001", "cat": "运营商", "name": "垃圾运营商编码置空",
     "field": "operator_code", "action": "nullify",
     "where": "operator_code IN ('00000','0','000000','(null)(null)','')",
     "desc": "明确的垃圾值：00000、0、000000、(null)(null)、空字符串"},
    {"id": "ODS-002", "cat": "运营商", "name": "非白名单运营商置空",
     "field": "operator_code", "action": "nullify",
     "where": "operator_code IS NOT NULL AND operator_code NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020')",
     "desc": "运营商编码不在有效白名单内"},
    # ── LAC ──
    {"id": "ODS-003", "cat": "LAC", "name": "LAC=0 置空",
     "field": "lac", "action": "nullify",
     "where": "lac = 0",
     "desc": "LAC=0 表示未获取到有效 LAC"},
    {"id": "ODS-004", "cat": "LAC", "name": "4G LAC 保留值置空",
     "field": "lac", "action": "nullify",
     "where": "lac IN (65534, 65535) AND tech_norm = '4G'",
     "desc": "4G 的 65534/65535 是保留值"},
    {"id": "ODS-005", "cat": "LAC", "name": "LAC 溢出值置空",
     "field": "lac", "action": "nullify",
     "where": "lac = 268435455",
     "desc": "0xFFFFFFF 溢出值"},
    # ── CellID ──
    {"id": "ODS-006", "cat": "CellID", "name": "CellID=0 置空",
     "field": "cell_id", "action": "nullify",
     "where": "cell_id = 0",
     "desc": "无有效小区标识"},
    {"id": "ODS-007", "cat": "CellID", "name": "5G CellID 溢出值置空",
     "field": "cell_id", "action": "nullify",
     "where": "cell_id = 268435455 AND tech_norm = '5G'",
     "desc": "5G 的 268435455 (0xFFFFFFF) 溢出值"},
    {"id": "ODS-008", "cat": "CellID", "name": "4G CellID 溢出值置空",
     "field": "cell_id", "action": "nullify",
     "where": "cell_id = 2147483647 AND tech_norm = '4G'",
     "desc": "4G 的 2147483647 (Integer.MAX_VALUE) 溢出值"},
    # ── 信号 ──
    {"id": "ODS-009", "cat": "信号", "name": "RSRP 越界置空",
     "field": "rsrp", "action": "nullify",
     "where": "rsrp IS NOT NULL AND (rsrp > 0 OR rsrp = 0 OR rsrp < -156)",
     "desc": "RSRP 合理范围 -156~-1"},
    {"id": "ODS-010", "cat": "信号", "name": "RSRQ 越界置空",
     "field": "rsrq", "action": "nullify",
     "where": "rsrq IS NOT NULL AND (rsrq > 10 OR rsrq < -34)",
     "desc": "RSRQ 合理范围 -34~10"},
    {"id": "ODS-011", "cat": "信号", "name": "SINR 越界置空",
     "field": "sinr", "action": "nullify",
     "where": "sinr IS NOT NULL AND (sinr > 40 OR sinr < -23)",
     "desc": "SINR 合理范围 -23~40"},
    {"id": "ODS-012", "cat": "信号", "name": "Dbm 越界置空",
     "field": "dbm", "action": "nullify",
     "where": "dbm IS NOT NULL AND (dbm > 0 OR dbm = 0)",
     "desc": "Dbm 应为负数"},
    # ── 位置 ──
    {"id": "ODS-013", "cat": "位置", "name": "经度越界标记",
     "field": "gps_valid", "action": "flag_gps",
     "where": "lon_raw IS NOT NULL AND (lon_raw < 73 OR lon_raw > 135)",
     "desc": "经度有效范围 73~135，超出标记为 GPS 无效"},
    {"id": "ODS-014", "cat": "位置", "name": "纬度越界标记",
     "field": "gps_valid", "action": "flag_gps",
     "where": "lat_raw IS NOT NULL AND (lat_raw < 3 OR lat_raw > 54)",
     "desc": "纬度有效范围 3~54，超出标记为 GPS 无效"},
    # ── WiFi ──
    {"id": "ODS-015", "cat": "WiFi", "name": "无效 WiFi 名称置空",
     "field": "wifi_name", "action": "nullify",
     "where": "wifi_name IN ('<unknown ssid>', 'unknown', '')",
     "desc": "SDK 返回的占位符值，无实际意义"},
    {"id": "ODS-016", "cat": "WiFi", "name": "无效 WiFi MAC 置空",
     "field": "wifi_mac", "action": "nullify",
     "where": "wifi_mac IN ('02:00:00:00:00:00', '00:00:00:00:00:00', '')",
     "desc": "Android 隐私保护的伪 MAC 或空值"},
]

# 最终行过滤条件（删除无有效 CellID 的行）
FINAL_ROW_FILTER = "cell_id IS NULL OR cell_id = 0 OR (cell_id = 268435455 AND tech_norm = '5G') OR (cell_id = 2147483647 AND tech_norm = '4G')"


def step2_clean() -> StepResult:
    """清洗：对齐 rebuild2 的方式——先置 NULL，最后删除无效 CellID 行。"""
    result = StepResult(step="clean")

    input_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4.etl_parsed")["cnt"]
    result.input_count = input_count

    # 创建清洗表（复制 etl_parsed）
    execute("DROP TABLE IF EXISTS rebuild4.etl_cleaned")
    execute("CREATE TABLE rebuild4.etl_cleaned AS SELECT * FROM rebuild4.etl_parsed")

    # 逐条规则执行 + 统计
    rule_stats = []
    for rule in ODS_RULES:
        cnt = 0
        if rule["action"] == "nullify":
            cnt = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.etl_cleaned WHERE {rule['where']}")["cnt"]
            if cnt > 0:
                execute(f"UPDATE rebuild4.etl_cleaned SET {rule['field']} = NULL WHERE {rule['where']}")
        elif rule["action"] == "flag_gps":
            cnt = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.etl_cleaned WHERE {rule['where']}")["cnt"]
            if cnt > 0:
                execute(f"UPDATE rebuild4.etl_cleaned SET gps_valid = false WHERE {rule['where']}")
        rule_stats.append({
            "id": rule["id"], "cat": rule["cat"], "name": rule["name"],
            "field": rule["field"], "action": rule["action"],
            "violations": cnt, "rate": round(cnt / input_count, 6) if input_count else 0,
            "desc": rule["desc"],
        })

    # 派生字段：基站ID、扇区ID、运营商中文、时间转换、标记
    execute("""
        ALTER TABLE rebuild4.etl_cleaned
            ADD COLUMN IF NOT EXISTS bs_id bigint,
            ADD COLUMN IF NOT EXISTS sector_id bigint,
            ADD COLUMN IF NOT EXISTS operator_cn text,
            ADD COLUMN IF NOT EXISTS ts_std timestamptz,
            ADD COLUMN IF NOT EXISTS cell_ts_std timestamptz,
            ADD COLUMN IF NOT EXISTS gps_ts timestamptz,
            ADD COLUMN IF NOT EXISTS has_cell_id boolean
    """)
    # 基站ID + 扇区ID + 运营商中文
    execute("""
        UPDATE rebuild4.etl_cleaned SET
            bs_id = CASE
                WHEN cell_id IS NOT NULL AND tech_norm = '5G' THEN cell_id / 4096
                WHEN cell_id IS NOT NULL THEN cell_id / 256
            END,
            sector_id = CASE
                WHEN cell_id IS NOT NULL AND tech_norm = '5G' THEN cell_id % 4096
                WHEN cell_id IS NOT NULL THEN cell_id % 256
            END,
            operator_cn = CASE operator_code
                WHEN '46000' THEN '移动' WHEN '46002' THEN '移动' WHEN '46007' THEN '移动'
                WHEN '46001' THEN '联通' WHEN '46006' THEN '联通' WHEN '46009' THEN '联通'
                WHEN '46003' THEN '电信' WHEN '46005' THEN '电信' WHEN '46011' THEN '电信'
                WHEN '46015' THEN '广电' WHEN '46020' THEN '铁路'
            END,
            has_cell_id = (cell_id IS NOT NULL AND cell_id != 0)
    """)
    # 时间转换：ts_raw → ts_std（上报时间）
    execute(r"""
        UPDATE rebuild4.etl_cleaned SET
            ts_std = CASE WHEN ts_raw ~ '^\d{4}-' THEN ts_raw::timestamptz END
    """)
    # 时间转换：cell_ts_raw → cell_ts_std（ss1 的基站扫描时间，unix 秒）
    execute(r"""
        UPDATE rebuild4.etl_cleaned SET
            cell_ts_std = CASE
                WHEN cell_origin = 'ss1' AND cell_ts_raw ~ '^\d{10}$'
                THEN to_timestamp(cell_ts_raw::bigint)
            END
    """)
    # 时间转换：gps_ts_raw → gps_ts（GPS 采集时间，unix 毫秒）
    execute(r"""
        UPDATE rebuild4.etl_cleaned SET
            gps_ts = CASE
                WHEN gps_ts_raw ~ '^\d{13}$'
                THEN to_timestamp(gps_ts_raw::bigint / 1000.0)
            END
    """)

    # 最终过滤：删除无有效 CellID 的行
    deleted = fetchone(f"""
        WITH d AS (DELETE FROM rebuild4.etl_cleaned WHERE {FINAL_ROW_FILTER} RETURNING 1)
        SELECT COUNT(*) as cnt FROM d
    """)["cnt"]
    result.filtered_count = deleted

    output_count = fetchone("SELECT COUNT(*) as cnt FROM rebuild4.etl_cleaned")["cnt"]
    result.output_count = output_count
    result.details = {"rules": rule_stats, "deleted_invalid_cellid": deleted}

    return result


# ============================================================
# Step 3: 补齐（同报文）
# ============================================================

def step3_fill() -> StepResult:
    """同报文补齐：同 record_id + 同 cell_id 内互补。

    规则：
    - cell_infos 行之间（时间相同）：全字段可补（lac/rsrp/GPS/wifi 等）
    - ss1 行时间差 ≤ 1分钟：全字段可补
    - ss1 行时间差 > 1分钟：只补运营商和 lac（信号/GPS/wifi 不补）
    - 同报文内 cell 碰撞概率极低，所以用 cell_id 做匹配键
    """
    result = StepResult(step="fill")

    # 补齐前统计
    before = fetchone("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE lon_raw IS NOT NULL AND gps_valid) as has_gps,
            COUNT(*) FILTER (WHERE rsrp IS NOT NULL) as has_rsrp,
            COUNT(*) FILTER (WHERE operator_code IS NOT NULL) as has_operator,
            COUNT(*) FILTER (WHERE lac IS NOT NULL) as has_lac,
            COUNT(*) FILTER (WHERE wifi_name IS NOT NULL) as has_wifi
        FROM rebuild4.etl_cleaned
    """)
    result.input_count = before["total"]

    # ── 补齐 SQL ──
    # 捐赠者：同 record_id + 同 cell_id 内，优先 cell_infos 行
    # 补齐规则：
    #   cell_infos 行之间 → 全补（同 JSON，同时间）
    #   cell_infos → ss1 → 全补（同一次上报，时间差很小）
    #   ss1 → ss1 → 比较 ts_block 差异：≤60秒全补，>60秒只补运营商+LAC
    execute("DROP TABLE IF EXISTS rebuild4.etl_filled")
    execute(r"""
        CREATE TABLE rebuild4.etl_filled AS
        WITH
        donor AS (
            SELECT DISTINCT ON (record_id, cell_id)
                record_id, cell_id,
                cell_origin AS d_origin,
                operator_code AS d_operator,
                lac AS d_lac,
                lon_raw AS d_lon, lat_raw AS d_lat, gps_valid AS d_gps_valid,
                rsrp AS d_rsrp, rsrq AS d_rsrq, sinr AS d_sinr, dbm AS d_dbm,
                wifi_name AS d_wifi_name, wifi_mac AS d_wifi_mac,
                cell_ts_raw AS d_ts
            FROM rebuild4.etl_cleaned
            WHERE cell_id IS NOT NULL
            ORDER BY record_id, cell_id,
                CASE cell_origin WHEN 'cell_infos' THEN 1 ELSE 2 END,
                CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END
        ),
        filled AS (
            SELECT c.*,
                -- 判断是否允许全字段补齐
                -- true = 全补, false = 只补运营商+LAC
                CASE
                    -- cell_infos 行 → 总是全补
                    WHEN c.cell_origin = 'cell_infos' THEN true
                    -- 捐赠者是 cell_infos → 同报文，全补
                    WHEN d.d_origin = 'cell_infos' THEN true
                    -- ss1 ← ss1：比较 ts_block（都是 unix 秒），≤60秒全补
                    WHEN c.cell_ts_raw ~ '^\d{10}$' AND d.d_ts ~ '^\d{10}$'
                         AND ABS(c.cell_ts_raw::bigint - d.d_ts::bigint) <= 60 THEN true
                    -- 其他情况（时间差>60s 或时间格式不对）→ 只补运营商+LAC
                    ELSE false
                END AS allow_full_fill,
                d.d_operator, d.d_lac, d.d_lon, d.d_lat, d.d_gps_valid,
                d.d_rsrp, d.d_rsrq, d.d_sinr, d.d_dbm,
                d.d_wifi_name, d.d_wifi_mac
            FROM rebuild4.etl_cleaned c
            LEFT JOIN donor d ON d.record_id = c.record_id AND d.cell_id = c.cell_id
        )
        SELECT
            record_id, data_source, data_source_detail, cell_origin,
            tech_raw, tech_norm, operator_code, lac, cell_id,
            pci, freq_channel, bandwidth,
            rsrp, rsrq, sinr, rssi, dbm, asu_level, sig_level, sig_ss,
            timing_advance, csi_rsrp, csi_rsrq, csi_sinr, cqi,
            ts_raw, ts_std, cell_ts_raw, cell_ts_std, gps_ts_raw, gps_ts,
            gps_info_type, gps_valid, lon_raw, lat_raw, gps_filled_from,
            has_cell_id,
            dev_id, ip, plmn_main, brand, model, sdk_ver, oaid, pkg_name,
            wifi_name, wifi_mac, cpu_info, pressure,
            bs_id, sector_id, operator_cn,
            allow_full_fill,
            -- 运营商补齐（总是可补，不受时间约束）
            COALESCE(operator_code, d_operator) AS operator_filled,
            CASE WHEN operator_code IS NOT NULL THEN 'original'
                 WHEN d_operator IS NOT NULL THEN 'same_cell' ELSE 'none' END AS operator_fill_source,
            -- LAC 补齐（总是可补，不受时间约束）
            COALESCE(lac, d_lac) AS lac_filled,
            CASE WHEN lac IS NOT NULL THEN 'original'
                 WHEN d_lac IS NOT NULL THEN 'same_cell' ELSE 'none' END AS lac_fill_source,
            -- GPS 补齐（需 allow_full_fill）
            CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN lon_raw
                 WHEN allow_full_fill AND d_lon IS NOT NULL AND d_gps_valid THEN d_lon END AS lon_filled,
            CASE WHEN lat_raw IS NOT NULL AND gps_valid THEN lat_raw
                 WHEN allow_full_fill AND d_lat IS NOT NULL AND d_gps_valid THEN d_lat END AS lat_filled,
            CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN gps_filled_from
                 WHEN allow_full_fill AND d_lon IS NOT NULL AND d_gps_valid THEN 'same_cell'
                 ELSE 'none' END AS gps_fill_source,
            -- RSRP 补齐（需 allow_full_fill）
            COALESCE(rsrp, CASE WHEN allow_full_fill THEN d_rsrp END) AS rsrp_filled,
            CASE WHEN rsrp IS NOT NULL THEN 'original'
                 WHEN allow_full_fill AND d_rsrp IS NOT NULL THEN 'same_cell'
                 ELSE 'none' END AS rsrp_fill_source,
            -- RSRQ 补齐（需 allow_full_fill）
            COALESCE(rsrq, CASE WHEN allow_full_fill THEN d_rsrq END) AS rsrq_filled,
            -- SINR 补齐（需 allow_full_fill）
            COALESCE(sinr, CASE WHEN allow_full_fill THEN d_sinr END) AS sinr_filled,
            -- WiFi 补齐（需 allow_full_fill）
            COALESCE(wifi_name, CASE WHEN allow_full_fill THEN d_wifi_name END) AS wifi_name_filled,
            COALESCE(wifi_mac, CASE WHEN allow_full_fill THEN d_wifi_mac END) AS wifi_mac_filled
        FROM filled
    """)

    # 补齐后统计
    after = fetchone("""
        SELECT
            COUNT(*) as total,
            -- GPS
            COUNT(*) FILTER (WHERE gps_fill_source IN ('raw_gps','ss1_own')) as gps_original,
            COUNT(*) FILTER (WHERE gps_fill_source = 'same_cell') as gps_filled,
            COUNT(*) FILTER (WHERE gps_fill_source = 'none') as gps_none,
            -- RSRP
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'original') as rsrp_original,
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'same_cell') as rsrp_filled,
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'none') as rsrp_none,
            -- 运营商
            COUNT(*) FILTER (WHERE operator_fill_source = 'same_cell') as operator_filled_cnt,
            -- LAC
            COUNT(*) FILTER (WHERE lac_fill_source = 'same_cell') as lac_filled_cnt,
            -- WiFi
            COUNT(*) FILTER (WHERE wifi_name_filled IS NOT NULL) as wifi_after,
            COUNT(*) FILTER (WHERE wifi_name IS NULL AND wifi_name_filled IS NOT NULL) as wifi_filled_cnt
        FROM rebuild4.etl_filled
    """)

    total = after["total"]
    result.output_count = total
    result.details = {
        "before": {
            "total": before["total"],
            "has_gps": before["has_gps"],
            "has_rsrp": before["has_rsrp"],
            "has_operator": before["has_operator"],
            "has_lac": before["has_lac"],
            "has_wifi": before["has_wifi"],
        },
        "after": {
            "total": total,
            "gps_original": after["gps_original"],
            "gps_filled": after["gps_filled"],
            "gps_none": after["gps_none"],
            "gps_rate": round((total - after["gps_none"]) / total, 4) if total else 0,
            "rsrp_original": after["rsrp_original"],
            "rsrp_filled": after["rsrp_filled"],
            "rsrp_none": after["rsrp_none"],
            "rsrp_rate": round((total - after["rsrp_none"]) / total, 4) if total else 0,
            "operator_filled": after["operator_filled_cnt"],
            "lac_filled": after["lac_filled_cnt"],
            "wifi_after": after["wifi_after"],
            "wifi_filled": after["wifi_filled_cnt"],
        },
    }

    return result
