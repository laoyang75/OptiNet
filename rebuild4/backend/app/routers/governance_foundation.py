"""ETL 验证 API - 对标 rebuild2 前 4 层（Raw/L0 审计/L0 概览/ODS/可信库）."""
from fastapi import APIRouter, Query
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope
from ..core.context import base_context

# 当前可用 scope 列表
AVAILABLE_SCOPES = ["sample"]  # 未来扩展: "7d", "30d"

router = APIRouter(prefix="/api/governance/foundation", tags=["etl_validation"])

# ============================================================
# 27 列原始字段决策（纯配置，不查数据库）
# ============================================================
RAW_FIELDS = [
    {"seq": 1, "name": "记录数唯一标识", "category": "标识", "decision": "keep", "desc": "原始记录唯一标识", "type": "varchar"},
    {"seq": 2, "name": "数据来源dna或daa", "category": "元数据", "decision": "keep", "desc": "数据来源：DNA 或 DAA", "type": "varchar"},
    {"seq": 3, "name": "did", "category": "标识", "decision": "keep", "desc": "设备唯一标识符", "type": "varchar"},
    {"seq": 4, "name": "ts", "category": "时间", "decision": "keep", "desc": "上报时间（原始文本，unix 毫秒）", "type": "varchar"},
    {"seq": 5, "name": "ip", "category": "标识", "decision": "keep", "desc": "上报 IP 地址", "type": "varchar"},
    {"seq": 6, "name": "pkg_name", "category": "元数据", "decision": "keep", "desc": "上报应用包名", "type": "varchar"},
    {"seq": 7, "name": "wifi_name", "category": "网络", "decision": "keep", "desc": "WiFi SSID 名称", "type": "varchar"},
    {"seq": 8, "name": "wifi_mac", "category": "网络", "decision": "keep", "desc": "WiFi MAC 地址（BSSID）", "type": "varchar"},
    {"seq": 9, "name": "sdk_ver", "category": "元数据", "decision": "keep", "desc": "SDK 版本号", "type": "varchar"},
    {"seq": 10, "name": "gps上报时间", "category": "时间", "decision": "keep", "desc": "GPS 上报时间（原始文本）", "type": "varchar"},
    {"seq": 11, "name": "主卡运营商id", "category": "网络", "decision": "keep", "desc": "主卡运营商 PLMN（如 46000）", "type": "varchar"},
    {"seq": 12, "name": "品牌", "category": "元数据", "decision": "keep", "desc": "手机品牌", "type": "varchar"},
    {"seq": 13, "name": "机型", "category": "元数据", "decision": "keep", "desc": "手机机型", "type": "varchar"},
    {"seq": 14, "name": "gps_info_type", "category": "位置", "decision": "parse", "desc": "GPS 信息类型标识", "type": "varchar"},
    {"seq": 15, "name": "原始上报gps", "category": "位置", "decision": "keep", "desc": "原始 GPS 经纬度字符串", "type": "varchar"},
    {"seq": 16, "name": "cell_infos", "category": "核心", "decision": "parse", "desc": "实时基站扫描 JSON：含 cell_id/lac/plmn/信号/制式", "type": "text"},
    {"seq": 17, "name": "ss1", "category": "核心", "decision": "parse", "desc": "后台采集信号串：含信号强度/时间/GPS/基站/AP", "type": "text"},
    {"seq": 18, "name": "当前数据最终经度", "category": "位置", "decision": "drop", "desc": "最终经度（已处理）", "type": "float8"},
    {"seq": 19, "name": "当前数据最终纬度", "category": "位置", "decision": "drop", "desc": "最终纬度（已处理）", "type": "float8"},
    {"seq": 20, "name": "android_ver", "category": "元数据", "decision": "drop", "desc": "Android 系统版本", "type": "varchar"},
    {"seq": 21, "name": "cpu_info", "category": "元数据", "decision": "keep", "desc": "CPU 信息", "type": "varchar"},
    {"seq": 22, "name": "基带版本信息", "category": "元数据", "decision": "drop", "desc": "基带版本", "type": "varchar"},
    {"seq": 23, "name": "arp_list", "category": "网络", "decision": "drop", "desc": "ARP 列表（JSON/文本）", "type": "text"},
    {"seq": 24, "name": "压力", "category": "元数据", "decision": "keep", "desc": "气压传感器读数", "type": "varchar"},
    {"seq": 25, "name": "imei", "category": "标识", "decision": "drop", "desc": "设备 IMEI", "type": "varchar"},
    {"seq": 26, "name": "oaid", "category": "标识", "decision": "keep", "desc": "开放匿名设备标识（OAID）", "type": "varchar"},
    {"seq": 27, "name": "gps定位北京来源ss1或daa", "category": "元数据", "decision": "drop", "desc": "GPS 表专属：北京来源标记", "type": "varchar"},
]


def sample_where(alias: str = "") -> str:
    """Generate sample LAC WHERE clause for obj_lac queries."""
    p = f"{alias}." if alias else ""
    return f"""
    ({p}operator_code = '46000' AND {p}lac IN ('4176','2097233'))
    OR ({p}operator_code = '46001' AND {p}lac IN ('6402','73733'))
    OR ({p}operator_code = '46011' AND {p}lac IN ('6411','405512'))
"""


# ============================================================
# 1. 原始数据 · 字段挑选（纯配置页，不查数据库）
# ============================================================
@router.get("/scopes")
def list_scopes():
    """返回当前可用的 scope 列表。"""
    return envelope({
        "scopes": AVAILABLE_SCOPES,
        "current": "sample",
    }, subject_scope="governance", subject_note="可用 scope 列表")


@router.get("/raw-overview")
def raw_overview():
    """原始数据 · 字段挑选: 27 列字段决策 + 原始样本表行数（对标 rebuild2 #raw）。"""
    decision_counts = {}
    for f in RAW_FIELDS:
        d = f["decision"]
        decision_counts[d] = decision_counts.get(d, 0) + 1

    # 原始样本表行数（pre-ETL，从 legacy 表按 record_id 提取）
    sample_counts = fetchone("""
        SELECT
            (SELECT COUNT(*) FROM rebuild4.sample_raw_gps) as raw_gps,
            (SELECT COUNT(*) FROM rebuild4.sample_raw_lac) as raw_lac
    """)

    return envelope({
        "fields": RAW_FIELDS,
        "field_count": len(RAW_FIELDS),
        "decision_summary": decision_counts,
        "source_tables": [
            {"name": "网优项目_gps定位北京明细数据_20251201_20251207", "schema": "legacy", "columns": 27,
             "sample_table": "sample_raw_gps", "sample_rows": sample_counts["raw_gps"]},
            {"name": "网优项目_lac定位北京明细数据_20251201_20251207", "schema": "legacy", "columns": 27,
             "sample_table": "sample_raw_lac", "sample_rows": sample_counts["raw_lac"]},
        ],
        "note": "两张源表结构一致（27 列），统一为一份字段决策。未来对接不同数据源时需重新配置。",
        "scope": "sample",
    }, subject_scope="governance", subject_note="原始数据 · 字段挑选")


# ============================================================
# 2. L0 字段审计（对标 rebuild2 #audit）
# ============================================================
@router.get("/l0-audit")
def l0_audit():
    """L0 字段审计: 解析后 55 列目标字段定义（对标 rebuild2 #audit）。"""
    fields = fetchall("""
        SELECT field_name, field_name_cn, data_type, category, source_type, description
        FROM rebuild2_meta.target_field
        ORDER BY id
    """)

    # 按 category 分组统计
    category_counts = {}
    source_type_counts = {}
    for f in fields:
        cat = f["category"]
        st = f["source_type"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        source_type_counts[st] = source_type_counts.get(st, 0) + 1

    return envelope({
        "fields": fields,
        "field_count": len(fields),
        "category_summary": category_counts,
        "source_type_summary": source_type_counts,
        "note": "27 列原始字段经 JSON 解析、字段映射、标记生成后产出 55 列 L0 结构化数据。",
    }, subject_scope="governance", subject_note="L0 字段审计")


# ============================================================
# 3. L0 数据概览（对标 rebuild2 #l0data，版本相关）
# ============================================================
@router.get("/l0-overview")
def l0_overview():
    """L0 数据概览: 从原始数据解析后的 pre-ODS 统计（对标 rebuild2 #l0data）。"""
    ctx = base_context()

    # 数据来源: sample_l0_raw_gps/lac — 从 legacy 原始表解析但未清洗
    gps_stats = fetchone("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_connected = 1) as connected,
            COUNT(DISTINCT operator_code) as operator_count,
            COUNT(*) FILTER (WHERE raw_lon IS NOT NULL) as has_gps,
            COUNT(*) FILTER (WHERE raw_lon IS NULL) as no_gps,
            COUNT(*) FILTER (WHERE rsrp IS NULL) as rsrp_null,
            COUNT(*) FILTER (WHERE cell_id IS NULL OR cell_id = 0) as cellid_null
        FROM rebuild4.sample_l0_raw_gps
    """)

    lac_stats = fetchone("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_connected = 1) as connected,
            COUNT(DISTINCT operator_code) as operator_count,
            COUNT(*) FILTER (WHERE rsrp IS NULL) as rsrp_null,
            COUNT(*) FILTER (WHERE cell_id IS NULL OR cell_id = 0) as cellid_null
        FROM rebuild4.sample_l0_raw_lac
    """)

    # 制式分布（全部记录，含未连接）
    by_tech = fetchall("""
        SELECT tech_norm, COUNT(*) as cnt,
            ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER (), 4) as ratio
        FROM rebuild4.sample_l0_raw_gps
        GROUP BY tech_norm ORDER BY cnt DESC
    """)

    # 运营商分布
    by_operator = fetchall("""
        SELECT operator_code, COUNT(*) as cnt,
            ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER (), 4) as ratio
        FROM rebuild4.sample_l0_raw_gps
        GROUP BY operator_code ORDER BY cnt DESC
        LIMIT 20
    """)

    # Cell 来源分布
    by_source = fetchall("""
        SELECT cell_origin, COUNT(*) as cnt,
            ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER (), 4) as ratio
        FROM rebuild4.sample_l0_raw_gps
        GROUP BY cell_origin ORDER BY cnt DESC
    """)

    # LAC 明细（Top 20）
    by_lac = fetchall("""
        SELECT operator_code, lac::text as lac,
            COUNT(*) as cnt,
            COUNT(DISTINCT tech_norm) as tech_count,
            STRING_AGG(DISTINCT tech_norm, '/' ORDER BY tech_norm) as techs
        FROM rebuild4.sample_l0_raw_gps
        WHERE is_connected = 1
        GROUP BY operator_code, lac ORDER BY cnt DESC
        LIMIT 20
    """)

    # 原始表行数（pre-parse）
    raw_counts = fetchone("""
        SELECT
            (SELECT COUNT(*) FROM rebuild4.sample_raw_gps) as raw_gps,
            (SELECT COUNT(*) FROM rebuild4.sample_raw_lac) as raw_lac
    """)

    return envelope({
        "scope": "sample",
        "available_scopes": AVAILABLE_SCOPES,
        "raw_counts": raw_counts,
        "gps_stats": gps_stats,
        "lac_stats": lac_stats,
        "by_tech": by_tech,
        "by_operator": by_operator,
        "by_source": by_source,
        "by_lac": by_lac,
        "note": "数据来源: sample_raw_gps/lac 原始解析（pre-ODS，含脏数据）",
    }, subject_scope="governance", subject_note="L0 数据概览", context=ctx)


# ============================================================
# 4. ODS 清洗规则 + 执行结果（对标 rebuild2 #ods）
# ============================================================
@router.get("/ods-rules")
def ods_rules():
    """ODS 清洗规则: 在 pre-ODS 解析表上检查（对标 rebuild2 #ods）。"""
    ctx = base_context()

    # 数据来源: sample_l0_raw_gps/lac — 从原始数据解析但未清洗，包含脏数据
    gps_checks = fetchone("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE operator_code NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020')) as bad_operator,
            COUNT(*) FILTER (WHERE lac = 0) as bad_lac_zero,
            COUNT(*) FILTER (WHERE lac IN (65534, 65535) AND tech_norm = '4G') as bad_lac_reserved_4g,
            COUNT(*) FILTER (WHERE lac = 268435455) as bad_lac_max,
            COUNT(*) FILTER (WHERE cell_id = 0) as bad_cell_zero,
            COUNT(*) FILTER (WHERE cell_id = 268435455 AND tech_norm = '5G') as bad_cell_max_5g,
            COUNT(*) FILTER (WHERE raw_lon IS NOT NULL AND (raw_lon < 73 OR raw_lon > 135)) as bad_lon,
            COUNT(*) FILTER (WHERE raw_lat IS NOT NULL AND (raw_lat < 3 OR raw_lat > 54)) as bad_lat,
            COUNT(*) FILTER (WHERE rsrp IS NOT NULL AND (rsrp < -156 OR rsrp > 0)) as bad_rsrp
        FROM rebuild4.sample_l0_raw_gps
    """)

    lac_checks = fetchone("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE operator_code NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020')) as bad_operator,
            COUNT(*) FILTER (WHERE lac = 0) as bad_lac_zero,
            COUNT(*) FILTER (WHERE lac IN (65534, 65535) AND tech_norm = '4G') as bad_lac_reserved_4g,
            COUNT(*) FILTER (WHERE lac = 268435455) as bad_lac_max,
            COUNT(*) FILTER (WHERE cell_id = 0) as bad_cell_zero,
            COUNT(*) FILTER (WHERE cell_id = 268435455 AND tech_norm = '5G') as bad_cell_max_5g,
            COUNT(*) FILTER (WHERE raw_lon IS NOT NULL AND (raw_lon < 73 OR raw_lon > 135)) as bad_lon,
            COUNT(*) FILTER (WHERE raw_lat IS NOT NULL AND (raw_lat < 3 OR raw_lat > 54)) as bad_lat,
            COUNT(*) FILTER (WHERE rsrp IS NOT NULL AND (rsrp < -156 OR rsrp > 0)) as bad_rsrp
        FROM rebuild4.sample_l0_raw_lac
    """)

    def build_rules(checks, table_name):
        total = checks["total"]
        rules = [
            {"id": 1, "category": "运营商", "rule": "排除无效运营商编码", "field": "operator_code",
             "condition": "NOT IN ('46000','46001',...,'46020')", "violations": checks["bad_operator"]},
            {"id": 2, "category": "LAC", "rule": "LAC 不为 0", "field": "lac",
             "condition": "lac = 0", "violations": checks["bad_lac_zero"]},
            {"id": 3, "category": "LAC", "rule": "4G LAC 不为 65534/65535", "field": "lac",
             "condition": "lac IN (65534,65535) AND tech_norm='4G'", "violations": checks["bad_lac_reserved_4g"]},
            {"id": 4, "category": "LAC", "rule": "LAC 不为 268435455", "field": "lac",
             "condition": "lac = 268435455", "violations": checks["bad_lac_max"]},
            {"id": 5, "category": "CellID", "rule": "CellID 不为 0", "field": "cell_id",
             "condition": "cell_id = 0", "violations": checks["bad_cell_zero"]},
            {"id": 6, "category": "CellID", "rule": "5G CellID 不为 268435455", "field": "cell_id",
             "condition": "cell_id = 268435455 AND tech_norm='5G'", "violations": checks["bad_cell_max_5g"]},
            {"id": 7, "category": "位置", "rule": "经度范围 73~135", "field": "raw_lon",
             "condition": "raw_lon < 73 OR raw_lon > 135", "violations": checks["bad_lon"]},
            {"id": 8, "category": "位置", "rule": "纬度范围 3~54", "field": "raw_lat",
             "condition": "raw_lat < 3 OR raw_lat > 54", "violations": checks["bad_lat"]},
            {"id": 9, "category": "信号", "rule": "RSRP 范围 -156~0", "field": "rsrp",
             "condition": "rsrp < -156 OR rsrp > 0", "violations": checks["bad_rsrp"]},
        ]
        total_violations = sum(r["violations"] for r in rules)
        return {
            "table": table_name,
            "total_records": total,
            "rules": rules,
            "total_violations": total_violations,
            "pass_rate": round(1 - total_violations / total, 6) if total > 0 else 1,
        }

    return envelope({
        "scope": "sample",
        "available_scopes": AVAILABLE_SCOPES,
        "gps": build_rules(gps_checks, "sample_l0_raw_gps"),
        "lac": build_rules(lac_checks, "sample_l0_raw_lac"),
    }, subject_scope="governance", subject_note="ODS 清洗规则", context=ctx)


# ============================================================
# 5. ETL 统计（从 etl_run_stats 表读取，不实时计算）
# ============================================================

def _latest_etl(scope: str = "sample"):
    """获取指定 scope 最新一次 ETL 运行统计。"""
    return fetchone(f"""
        SELECT * FROM rebuild4_meta.etl_run_stats
        WHERE scope = '{scope}'
        ORDER BY run_at DESC LIMIT 1
    """)


@router.get("/etl/parse-stats")
def etl_parse_stats(scope: str = "sample"):
    """解析统计（从统计表读取）。"""
    row = _latest_etl(scope)
    if not row:
        return envelope(None, subject_scope="governance", subject_note="ETL 未执行")
    return envelope({
        "scope": row["scope"],
        "run_at": row["run_at"],
        "raw_input": row["raw_input_count"],
        "parsed_output": row["parsed_output_count"],
        "expansion_ratio": round(row["parsed_output_count"] / row["raw_input_count"], 2) if row["raw_input_count"] else 0,
        "ci_gps": row["ci_gps_count"],
        "ci_lac": row["ci_lac_count"],
        "ss1_gps": row["ss1_gps_count"],
        "ss1_lac": row["ss1_lac_count"],
    }, subject_scope="governance", subject_note="解析统计")


@router.get("/etl/parse-fields")
def etl_parse_fields():
    """解析后字段覆盖率（直接查 etl_parsed）。"""
    try:
        row = fetchone("""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE operator_code IS NOT NULL) as operator_code,
                COUNT(*) FILTER (WHERE lac IS NOT NULL) as lac,
                COUNT(*) FILTER (WHERE cell_id IS NOT NULL AND cell_id != 0) as cell_id,
                COUNT(*) FILTER (WHERE pci IS NOT NULL) as pci,
                COUNT(*) FILTER (WHERE freq_channel IS NOT NULL) as freq_channel,
                COUNT(*) FILTER (WHERE bandwidth IS NOT NULL) as bandwidth,
                COUNT(*) FILTER (WHERE rsrp IS NOT NULL) as rsrp,
                COUNT(*) FILTER (WHERE rsrq IS NOT NULL) as rsrq,
                COUNT(*) FILTER (WHERE sinr IS NOT NULL) as sinr,
                COUNT(*) FILTER (WHERE rssi IS NOT NULL) as rssi,
                COUNT(*) FILTER (WHERE dbm IS NOT NULL) as dbm,
                COUNT(*) FILTER (WHERE asu_level IS NOT NULL) as asu_level,
                COUNT(*) FILTER (WHERE sig_ss IS NOT NULL) as sig_ss,
                COUNT(*) FILTER (WHERE timing_advance IS NOT NULL) as timing_advance,
                COUNT(*) FILTER (WHERE csi_rsrp IS NOT NULL) as csi_rsrp,
                COUNT(*) FILTER (WHERE lon_raw IS NOT NULL) as lon_raw,
                COUNT(*) FILTER (WHERE lat_raw IS NOT NULL) as lat_raw,
                COUNT(*) FILTER (WHERE gps_valid) as gps_valid,
                COUNT(*) FILTER (WHERE ts_raw IS NOT NULL) as ts_raw,
                COUNT(*) FILTER (WHERE wifi_name IS NOT NULL) as wifi_name,
                COUNT(*) FILTER (WHERE wifi_mac IS NOT NULL) as wifi_mac,
                COUNT(*) FILTER (WHERE ip IS NOT NULL) as ip,
                COUNT(*) FILTER (WHERE cpu_info IS NOT NULL) as cpu_info,
                COUNT(*) FILTER (WHERE pressure IS NOT NULL) as pressure
            FROM rebuild4.etl_parsed
        """)
        total = row.pop("total")
        fields = []
        for name, cnt in row.items():
            fields.append({"field": name, "count": cnt, "rate": round(cnt / total, 4) if total else 0})
        fields.sort(key=lambda x: -x["rate"])
        return envelope({"total": total, "fields": fields}, subject_scope="governance", subject_note="解析字段覆盖率")
    except Exception:
        return envelope(None, subject_scope="governance", subject_note="数据未生成")


@router.get("/etl/clean-stats")
def etl_clean_stats(scope: str = "sample"):
    """清洗统计（从统计表读取）。"""
    row = _latest_etl(scope)
    if not row:
        return envelope(None, subject_scope="governance", subject_note="ETL 未执行")
    return envelope({
        "scope": row["scope"],
        "run_at": row["run_at"],
        "input": row["clean_input_count"],
        "output": row["clean_output_count"],
        "deleted": row["clean_deleted_count"],
        "rules": row["clean_rules"],
    }, subject_scope="governance", subject_note="清洗统计")


@router.get("/etl/fill-stats")
def etl_fill_stats(scope: str = "sample"):
    """补齐统计（直接查 etl_cleaned + etl_filled）。"""
    try:
        before = fetchone("""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE lon_raw IS NOT NULL AND gps_valid) as has_gps,
                COUNT(*) FILTER (WHERE rsrp IS NOT NULL) as has_rsrp,
                COUNT(*) FILTER (WHERE operator_code IS NOT NULL) as has_operator,
                COUNT(*) FILTER (WHERE lac IS NOT NULL) as has_lac,
                COUNT(*) FILTER (WHERE wifi_name IS NOT NULL) as has_wifi
            FROM rebuild4.etl_cleaned
        """)
        after = fetchone("""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE gps_fill_source IN ('raw_gps','ss1_own')) as gps_original,
                COUNT(*) FILTER (WHERE gps_fill_source = 'same_cell') as gps_filled,
                COUNT(*) FILTER (WHERE gps_fill_source = 'none') as gps_none,
                COUNT(*) FILTER (WHERE rsrp_fill_source = 'original') as rsrp_original,
                COUNT(*) FILTER (WHERE rsrp_fill_source = 'same_cell') as rsrp_filled,
                COUNT(*) FILTER (WHERE rsrp_fill_source = 'none') as rsrp_none,
                COUNT(*) FILTER (WHERE operator_fill_source = 'same_cell') as operator_filled,
                COUNT(*) FILTER (WHERE lac_fill_source = 'same_cell') as lac_filled,
                COUNT(*) FILTER (WHERE wifi_name IS NULL AND wifi_name_filled IS NOT NULL) as wifi_filled
            FROM rebuild4.etl_filled
        """)
        t = after["total"]
        row = _latest_etl(scope)
        return envelope({
            "scope": scope,
            "run_at": row["run_at"] if row else None,
            "before_total": before["total"],
            "before_gps": before["has_gps"],
            "before_rsrp": before["has_rsrp"],
            "before_operator": before["has_operator"],
            "before_lac": before["has_lac"],
            "before_wifi": before["has_wifi"],
            "gps_original": after["gps_original"],
            "gps_filled": after["gps_filled"],
            "gps_none": after["gps_none"],
            "gps_rate": round((t - after["gps_none"]) / t, 4) if t else 0,
            "rsrp_original": after["rsrp_original"],
            "rsrp_filled": after["rsrp_filled"],
            "rsrp_none": after["rsrp_none"],
            "rsrp_rate": round((t - after["rsrp_none"]) / t, 4) if t else 0,
            "operator_filled": after["operator_filled"],
            "lac_filled": after["lac_filled"],
            "wifi_filled": after["wifi_filled"],
        }, subject_scope="governance", subject_note="补齐统计")
    except Exception:
        return envelope(None, subject_scope="governance", subject_note="补齐数据未生成")
