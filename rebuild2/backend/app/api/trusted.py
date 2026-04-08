"""Phase 2 可信库构建 API：可信 LAC → Cell → BS。

数据源：rebuild2.lac_daily_stats（LAC 每日统计表，从 l0_gps 预聚合）

可信 LAC 过滤链：
  1. 仅 4G/5G，运营商 46000/46001/46011/46015
  2. active_days = 7（满窗口）
  3. LAC ID 合规性：
     - 4G TAC (16-bit): 有效范围 256~65533，排除 0~255, 65534(0xFFFE), 65535(0xFFFF)
     - 5G TAC (24-bit): 有效范围 256~16777213，排除 0~255, 16777214(0xFFFFFE), 16777215(0xFFFFFF), 2147483647(INT_MAX)
  4. 日均上报量门槛：以移动日均 3500 为基准，按各组上报量占比等比换算
     广电全量保留
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/trusted", tags=["trusted"])

# ─── 门槛配置 ───────────────────────────────────────────────

CMCC_BASE_DAILY = 3500  # 移动基准日均上报量

# 各组相对移动的上报量占比
RATIOS = {
    ("46000", "4G"): 1.0,
    ("46000", "5G"): 1.0,
    ("46001", "4G"): 0.5841,
    ("46001", "5G"): 0.5532,
    ("46011", "4G"): 0.3245,
    ("46011", "5G"): 0.2297,
}

def get_thresholds():
    """返回各组的日均上报量门槛。"""
    return {k: round(CMCC_BASE_DAILY * v) for k, v in RATIOS.items()}

# LAC ID 合规性条件（SQL 片段）
# 4G TAC: 16-bit, 有效 256~65533
# 5G TAC: 24-bit, 有效 256~16777213
_LAC_COMPLIANCE_SQL = """
    CASE d.tech_norm
        WHEN '4G' THEN d.lac::bigint BETWEEN 256 AND 65533
        WHEN '5G' THEN d.lac::bigint BETWEEN 256 AND 16777213
        ELSE false
    END
"""

# 完整过滤 SQL
_TRUSTED_LAC_SQL = """
WITH thresholds(operator_code, tech_norm, min_daily) AS (
    VALUES
        ('46000', '4G', {t_46000_4G}),
        ('46000', '5G', {t_46000_5G}),
        ('46001', '4G', {t_46001_4G}),
        ('46001', '5G', {t_46001_5G}),
        ('46011', '4G', {t_46011_4G}),
        ('46011', '5G', {t_46011_5G})
)
SELECT d.*, t.min_daily AS threshold,
       true AS is_trusted
FROM rebuild2.lac_daily_stats d
JOIN thresholds t ON d.operator_code = t.operator_code AND d.tech_norm = t.tech_norm
WHERE d.active_days = 7
  AND (CASE d.tech_norm
        WHEN '4G' THEN d.lac::bigint BETWEEN 256 AND 65533
        WHEN '5G' THEN d.lac::bigint BETWEEN 256 AND 16777213
        ELSE false END)
  AND d.avg_daily_records >= t.min_daily

UNION ALL

-- 广电全量保留（active_days=7 + LAC 合规）
SELECT d.*, 0 AS threshold, true AS is_trusted
FROM rebuild2.lac_daily_stats d
WHERE d.operator_code = '46015'
  AND d.active_days = 7
  AND (CASE d.tech_norm
        WHEN '4G' THEN d.lac::bigint BETWEEN 256 AND 65533
        WHEN '5G' THEN d.lac::bigint BETWEEN 256 AND 16777213
        ELSE false END)
"""

def _build_sql():
    t = get_thresholds()
    return _TRUSTED_LAC_SQL.format(
        t_46000_4G=t[("46000","4G")], t_46000_5G=t[("46000","5G")],
        t_46001_4G=t[("46001","4G")], t_46001_5G=t[("46001","5G")],
        t_46011_4G=t[("46011","4G")], t_46011_5G=t[("46011","5G")],
    )


# ─── LAC 统计 ──────────────────────────────────────────────

@router.get("/lac/stats")
async def lac_stats(db: AsyncSession = Depends(get_db)):
    """从 lac_daily_stats 读取统计，按占比门槛过滤。"""

    thresholds = get_thresholds()

    # 漏斗
    funnel_result = await db.execute(text("""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE active_days = 7) AS days7,
            count(*) FILTER (WHERE active_days >= 5 AND active_days < 7) AS days5_6,
            count(*) FILTER (WHERE active_days >= 3 AND active_days < 5) AS days3_4,
            count(*) FILTER (WHERE active_days < 3) AS days_lt3
        FROM rebuild2.lac_daily_stats
        WHERE operator_code IN ('46000','46001','46011','46015')
          AND tech_norm IN ('4G','5G')
    """))
    funnel = dict(funnel_result.mappings().first())

    # LAC ID 合规性淘汰数
    compliance_result = await db.execute(text("""
        SELECT count(*) AS cnt FROM rebuild2.lac_daily_stats
        WHERE active_days = 7
          AND operator_code IN ('46000','46001','46011','46015') AND tech_norm IN ('4G','5G')
          AND NOT (CASE tech_norm
                WHEN '4G' THEN lac::bigint BETWEEN 256 AND 65533
                WHEN '5G' THEN lac::bigint BETWEEN 256 AND 16777213
                ELSE false END)
    """))
    funnel["compliance_filtered"] = dict(compliance_result.mappings().first())["cnt"]

    # 完整过滤结果
    sql = _build_sql()
    full_result = await db.execute(text(sql))
    trusted = [dict(r) for r in full_result.mappings().all()]

    # 日均门槛淘汰数 = 7天 - 合规淘汰 - trusted
    funnel["threshold_filtered"] = funnel["days7"] - funnel["compliance_filtered"] - len(trusted)

    # 按运营商+制式分组
    by_group = _group_stats(trusted, thresholds)

    # 与上一轮对比
    legacy_result = await db.execute(text("""
        SELECT operator_id_raw AS operator_code, tech_norm,
               count(*) AS lac_count, sum(record_count) AS total_records
        FROM legacy."Y_codex_Layer2_Step04_Master_Lac_Lib"
        WHERE is_trusted_lac GROUP BY operator_id_raw, tech_norm ORDER BY total_records DESC
    """))
    legacy_groups = [dict(r) for r in legacy_result.mappings().all()]

    # 逐条重叠
    current_keys = {f"{r['operator_code']}|{r['tech_norm']}|{r['lac']}" for r in trusted}
    legacy_keys_result = await db.execute(text("""
        SELECT operator_id_raw || '|' || tech_norm || '|' || lac_dec::text AS k
        FROM legacy."Y_codex_Layer2_Step04_Master_Lac_Lib" WHERE is_trusted_lac
    """))
    legacy_keys = {r["k"] for r in legacy_keys_result.mappings().all()}

    return {
        "funnel": funnel,
        "cmcc_base_daily": CMCC_BASE_DAILY,
        "thresholds": {f"{k[0]}|{k[1]}": v for k, v in thresholds.items()},
        "trusted_count": len(trusted),
        "by_group": by_group,
        "legacy_groups": legacy_groups,
        "comparison": {
            "current": len(current_keys),
            "legacy": len(legacy_keys),
            "overlap": len(current_keys & legacy_keys),
            "only_current": len(current_keys - legacy_keys),
            "only_legacy": len(legacy_keys - current_keys),
        },
        "items": trusted,
    }


def _group_stats(rows, thresholds):
    by_group = {}
    for r in rows:
        key = f"{r['operator_code']}|{r['tech_norm']}"
        g = by_group.setdefault(key, {
            "operator_code": r["operator_code"], "operator_cn": r["operator_cn"],
            "tech_norm": r["tech_norm"], "lac_count": 0, "total_records": 0,
            "total_cells": 0, "total_devices": 0,
            "min_daily_avg": None, "max_daily_avg": None,
            "threshold": r.get("threshold", 0),
        })
        g["lac_count"] += 1
        g["total_records"] += int(r.get("total_records") or 0)
        g["total_cells"] += int(r.get("avg_daily_cells") or 0) * 7
        g["total_devices"] += int(r.get("total_devices_sum") or 0)
        adv = int(r.get("avg_daily_records") or 0)
        if g["min_daily_avg"] is None or adv < g["min_daily_avg"]:
            g["min_daily_avg"] = adv
        if g["max_daily_avg"] is None or adv > g["max_daily_avg"]:
            g["max_daily_avg"] = adv
    return sorted(by_group.values(), key=lambda x: x["total_records"], reverse=True)


# ─── 构建 dim_lac_trusted ──────────────────────────────────

@router.post("/lac/build")
async def build_trusted_lac(db: AsyncSession = Depends(get_db)):
    """按占比门槛构建 dim_lac_trusted。"""
    sql = _build_sql()

    await db.execute(text("DROP TABLE IF EXISTS rebuild2.dim_lac_trusted"))
    await db.execute(text(f"""
        CREATE TABLE rebuild2.dim_lac_trusted AS
        SELECT operator_code, operator_cn, tech_norm, lac,
               total_records AS record_count,
               avg_daily_records, min_daily_records, max_daily_records,
               stddev_daily_records, cv,
               avg_daily_devices, min_daily_devices,
               avg_daily_cells, min_daily_cells,
               active_days, threshold,
               now() AS created_at
        FROM ({sql}) t
        ORDER BY total_records DESC
    """))
    await db.execute(text("""
        CREATE UNIQUE INDEX idx_dim_lac_trusted_key
        ON rebuild2.dim_lac_trusted(operator_code, tech_norm, lac)
    """))
    await db.execute(text("""
        CREATE INDEX idx_dim_lac_trusted_op
        ON rebuild2.dim_lac_trusted(operator_code, tech_norm)
    """))
    await db.commit()

    cnt_result = await db.execute(text("""
        SELECT operator_code, operator_cn, tech_norm,
               count(*) AS lac_count, sum(record_count) AS total_records
        FROM rebuild2.dim_lac_trusted
        GROUP BY operator_code, operator_cn, tech_norm
        ORDER BY total_records DESC
    """))
    by_group = [dict(r) for r in cnt_result.mappings().all()]
    total = sum(g["lac_count"] for g in by_group)

    await db.execute(text("""
        INSERT INTO rebuild2_meta.trusted_build_result (step_code, run_label, stat_key, stat_value)
        VALUES ('lac', 'build', 'summary', CAST(:val AS jsonb))
    """), {"val": f'{{"total_lac": {total}, "cmcc_base_daily": {CMCC_BASE_DAILY}}}'})
    await db.commit()

    return {"ok": True, "trusted_lac_count": total, "by_group": by_group}


@router.get("/lac/built")
async def get_built_lac(db: AsyncSession = Depends(get_db)):
    """读取已构建的 dim_lac_trusted。"""
    check = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'rebuild2' AND table_name = 'dim_lac_trusted'
        ) AS ok
    """))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False, "count": 0, "items": []}

    result = await db.execute(text("""
        SELECT * FROM rebuild2.dim_lac_trusted ORDER BY record_count DESC
    """))
    rows = [dict(r) for r in result.mappings().all()]

    by_group = {}
    for r in rows:
        key = f"{r['operator_cn']}|{r['tech_norm']}"
        g = by_group.setdefault(key, {
            "operator_cn": r["operator_cn"], "tech_norm": r["tech_norm"],
            "lac_count": 0, "total_records": 0,
        })
        g["lac_count"] += 1
        g["total_records"] += int(r.get("record_count") or 0)

    return {
        "exists": True,
        "count": len(rows),
        "by_group": sorted(by_group.values(), key=lambda x: x["total_records"], reverse=True),
        "items": rows,
    }


# ─── Cell 统计 ──────────────────────────────────────────────

def _table_exists(name: str) -> str:
    return f"""SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'rebuild2' AND table_name = '{name}'
    ) AS ok"""


@router.get("/cell/stats")
async def cell_stats(db: AsyncSession = Depends(get_db)):
    """读取 dim_cell_stats 统计概览。"""
    check = await db.execute(text(_table_exists("dim_cell_stats")))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False}

    # 按运营商+制式分组
    group_result = await db.execute(text("""
        SELECT operator_cn, tech_norm,
               count(*) AS cell_count,
               count(DISTINCT bs_id) AS bs_count,
               sum(record_count) AS total_records,
               sum(distinct_device_count) AS total_devices,
               count(*) FILTER (WHERE active_days = 7) AS cells_7day,
               avg(record_count)::int AS avg_records,
               count(*) FILTER (WHERE valid_gps_count > 0) AS cells_with_gps
        FROM rebuild2.dim_cell_stats
        GROUP BY operator_cn, tech_norm
        ORDER BY total_records DESC
    """))
    by_group = [dict(r) for r in group_result.mappings().all()]

    # 总计
    total_result = await db.execute(text("""
        SELECT count(*) AS total_cells,
               count(DISTINCT bs_id) AS total_bs,
               sum(record_count) AS total_records,
               count(*) FILTER (WHERE active_days = 7) AS cells_7day
        FROM rebuild2.dim_cell_stats
    """))
    totals = dict(total_result.mappings().first())

    # 与上一轮对比
    legacy_result = await db.execute(text("""
        SELECT operator_id_raw AS operator_code, tech_norm,
               count(*) AS cell_count, sum(record_count) AS total_records
        FROM legacy."Y_codex_Layer2_Step05_CellId_Stats_DB"
        GROUP BY operator_id_raw, tech_norm
        ORDER BY total_records DESC
    """))
    legacy_groups = [dict(r) for r in legacy_result.mappings().all()]

    # 明细 top 30
    detail = await db.execute(text("""
        SELECT operator_cn, tech_norm, lac, cell_id, bs_id, sector_id,
               record_count, distinct_device_count, active_days,
               gps_center_lon, gps_center_lat, valid_gps_count
        FROM rebuild2.dim_cell_stats ORDER BY record_count DESC LIMIT 30
    """))
    items = [dict(r) for r in detail.mappings().all()]

    return {
        "exists": True, **totals, "by_group": by_group,
        "legacy_groups": legacy_groups, "items": items,
    }


# ─── BS 统计 ────────────────────────────────────────────────

@router.post("/bs/build")
async def build_bs_stats(db: AsyncSession = Depends(get_db)):
    """从 dim_cell_stats 聚合生成 dim_bs_stats。"""
    check = await db.execute(text(_table_exists("dim_cell_stats")))
    if not dict(check.mappings().first())["ok"]:
        return {"ok": False, "error": "请先构建 dim_cell_stats"}

    await db.execute(text("DROP TABLE IF EXISTS rebuild2.dim_bs_stats"))
    await db.execute(text("""
        CREATE TABLE rebuild2.dim_bs_stats AS
        SELECT
            operator_code, operator_cn, tech_norm, lac, bs_id,
            count(*) AS cell_count,
            sum(record_count) AS record_count,
            sum(distinct_device_count) AS distinct_device_count,
            max(active_days) AS max_active_days,
            min(first_seen) AS first_seen,
            max(last_seen) AS last_seen,
            -- BS GPS 中心点 = 下属 Cell 的 GPS 中位数（加权）
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gps_center_lon)
                FILTER (WHERE gps_center_lon IS NOT NULL) AS gps_center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gps_center_lat)
                FILTER (WHERE gps_center_lat IS NOT NULL) AS gps_center_lat,
            sum(valid_gps_count) AS valid_gps_count
        FROM rebuild2.dim_cell_stats
        GROUP BY operator_code, operator_cn, tech_norm, lac, bs_id
        ORDER BY record_count DESC
    """))
    await db.execute(text("""
        CREATE INDEX idx_bs_stats_key ON rebuild2.dim_bs_stats(operator_code, tech_norm, lac, bs_id)
    """))
    await db.commit()

    # 统计
    result = await db.execute(text("""
        SELECT count(*) AS total_bs, sum(record_count) AS total_records,
               sum(cell_count) AS total_cells
        FROM rebuild2.dim_bs_stats
    """))
    totals = dict(result.mappings().first())

    return {"ok": True, **totals}


@router.get("/bs/stats")
async def bs_stats(db: AsyncSession = Depends(get_db)):
    """读取 dim_bs_stats 统计概览。"""
    check = await db.execute(text(_table_exists("dim_bs_stats")))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False}

    group_result = await db.execute(text("""
        SELECT operator_cn, tech_norm,
               count(*) AS bs_count,
               sum(cell_count) AS cell_count,
               sum(record_count) AS total_records,
               avg(cell_count)::numeric(5,1) AS avg_cells_per_bs
        FROM rebuild2.dim_bs_stats
        GROUP BY operator_cn, tech_norm
        ORDER BY total_records DESC
    """))
    by_group = [dict(r) for r in group_result.mappings().all()]

    total_result = await db.execute(text("""
        SELECT count(*) AS total_bs, sum(cell_count) AS total_cells,
               sum(record_count) AS total_records
        FROM rebuild2.dim_bs_stats
    """))
    totals = dict(total_result.mappings().first())

    # 与上一轮对比
    legacy_result = await db.execute(text("""
        SELECT count(*) AS total_bs FROM legacy."Y_codex_Layer3_Step30_Master_BS_Library"
    """))
    legacy_bs = dict(legacy_result.mappings().first())["total_bs"]

    detail = await db.execute(text("""
        SELECT operator_cn, tech_norm, lac, bs_id, cell_count,
               record_count, distinct_device_count, max_active_days,
               gps_center_lon, gps_center_lat
        FROM rebuild2.dim_bs_stats ORDER BY record_count DESC LIMIT 30
    """))
    items = [dict(r) for r in detail.mappings().all()]

    return {
        "exists": True, **totals, "by_group": by_group,
        "legacy_bs_count": legacy_bs, "items": items,
    }


# ─── 各层级汇总 ─────────────────────────────────────────────

@router.get("/summary")
async def pipeline_summary(db: AsyncSession = Depends(get_db)):
    """Phase 2 各层级行数汇总。"""
    layers = {}

    # L0
    for tbl in ("l0_gps", "l0_lac"):
        r = await db.execute(text(f'SELECT count(*) AS cnt FROM rebuild2."{tbl}"'))
        layers[tbl] = dict(r.mappings().first())["cnt"]

    # dim tables
    for tbl in ("dim_lac_trusted", "dim_cell_stats", "dim_bs_stats"):
        check = await db.execute(text(_table_exists(tbl)))
        if dict(check.mappings().first())["ok"]:
            r = await db.execute(text(f"SELECT count(*) AS cnt FROM rebuild2.{tbl}"))
            layers[tbl] = dict(r.mappings().first())["cnt"]
            if tbl == "dim_cell_stats":
                r2 = await db.execute(text("SELECT count(DISTINCT bs_id) AS cnt FROM rebuild2.dim_cell_stats"))
                layers["distinct_bs_from_cells"] = dict(r2.mappings().first())["cnt"]

    return {"layers": layers}
