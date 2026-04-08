"""L0 数据概览 API：从预算缓存表读取统计，毫秒级响应。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/l0", tags=["l0"])

L0_TABLES = [
    ("l0_gps", "GPS定位表", "用于构建可信库"),
    ("l0_lac", "LAC定位表", "全局表，可信库确定后从中提取最终数据"),
]


@router.get("/summary")
async def l0_summary(db: AsyncSession = Depends(get_db)):
    """两张 L0 表的总览（读缓存表）。"""
    tables = []
    for tbl, label, note in L0_TABLES:
        r = await db.execute(text("""
            SELECT stat_value FROM rebuild2_meta.l0_stats_cache
            WHERE table_name = :tbl AND stat_type = 'summary' AND stat_key = 'all'
        """), {"tbl": tbl})
        row = r.mappings().first()
        if not row:
            continue
        v = row["stat_value"]
        total = int(v.get("total", 0))
        tables.append({
            "table": tbl,
            "label": label,
            "note": note,
            "total": total,
            "records": int(v.get("records", 0)),
            "has_cellid": int(v.get("has_cellid", 0)),
            "has_cellid_rate": round(int(v.get("has_cellid", 0)) / total, 4) if total else 0,
            "gps_valid": int(v.get("gps_valid", 0)),
            "gps_valid_rate": round(int(v.get("gps_valid", 0)) / total, 4) if total else 0,
            "has_coord": int(v.get("has_coord", 0)),
            "has_rsrp": int(v.get("has_rsrp", 0)),
            "has_rsrp_rate": round(int(v.get("has_rsrp", 0)) / total, 4) if total else 0,
            "has_dbm": int(v.get("has_dbm", 0)),
        })
    return {"tables": tables}


@router.get("/distribution/{table}")
async def l0_distribution(table: str, db: AsyncSession = Depends(get_db)):
    """来源/制式/运营商/连接状态分布（读缓存表）。"""
    if table not in ("l0_gps", "l0_lac"):
        return {"error": "无效表名"}

    def _load(stat_type):
        return db.execute(text("""
            SELECT stat_value FROM rebuild2_meta.l0_stats_cache
            WHERE table_name = :tbl AND stat_type = :st
            ORDER BY stat_key
        """), {"tbl": table, "st": stat_type})

    origin_r = await _load("by_origin_tech")
    operator_r = await _load("by_operator")

    return {
        "table": table,
        "by_origin_tech": [r["stat_value"] for r in origin_r.mappings().all()],
        "by_operator": [r["stat_value"] for r in operator_r.mappings().all()],
    }


@router.get("/quality/{table}")
async def l0_quality(table: str, db: AsyncSession = Depends(get_db)):
    """字段空值率（读缓存表）。"""
    if table not in ("l0_gps", "l0_lac"):
        return {"error": "无效表名"}

    r = await db.execute(text("""
        SELECT stat_value FROM rebuild2_meta.l0_stats_cache
        WHERE table_name = :tbl AND stat_type = 'field_quality' AND stat_key = 'all'
    """), {"tbl": table})
    row = r.mappings().first()
    if not row:
        return {"table": table, "total": 0, "fields": []}

    v = row["stat_value"]
    total = int(v.get("total", 0))
    fields = [
        {"field": "RSRP", "null_rate": float(v.get("rsrp_null", 0))},
        {"field": "RSRQ", "null_rate": float(v.get("rsrq_null", 0))},
        {"field": "SINR", "null_rate": float(v.get("sinr_null", 0))},
        {"field": "RSSI", "null_rate": float(v.get("rssi_null", 0))},
        {"field": "Dbm", "null_rate": float(v.get("dbm_null", 0))},
        {"field": "ASU等级", "null_rate": float(v.get("asu_null", 0))},
        {"field": "信号等级", "null_rate": float(v.get("level_null", 0))},
        {"field": "运营商编码", "null_rate": float(v.get("operator_null", 0))},
        {"field": "LAC", "null_rate": float(v.get("lac_null", 0))},
        {"field": "CellID", "null_rate": float(v.get("cellid_null", 0))},
        {"field": "经度/纬度", "null_rate": float(v.get("gps_null", 0))},
        {"field": "上报时间", "null_rate": float(v.get("ts_null", 0))},
        {"field": "基站时间", "null_rate": float(v.get("cell_ts_null", 0))},
    ]
    return {"table": table, "total": total, "fields": fields}
