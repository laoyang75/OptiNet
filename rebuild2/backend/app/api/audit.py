"""字段审计 API：RAW 层字段质量、采样、决策 + L0 目标字段定义。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/audit", tags=["audit"])

# 两张原始表结构完全一致，合并为统一 RAW 层
LEGACY_TABLES = [
    ("网优项目_gps定位北京明细数据_20251201_20251207", "gps"),
    ("网优项目_lac定位北京明细数据_20251201_20251207", "lac"),
]
# 采样/字段查询只需要读一张表（结构相同）
SAMPLE_TABLE = LEGACY_TABLES[0][0]
# 决策统一存储在 sdk_raw 下
DECISION_SOURCE = "sdk_raw"


class FieldDecision(BaseModel):
    column_name: str
    decision: str
    ods_name: str | None = None
    ods_type: str | None = None
    description: str | None = None
    notes: str | None = None


# ── RAW 层汇总 ────────────────────────────────────────────────────

@router.get("/raw-summary")
async def raw_summary(db: AsyncSession = Depends(get_db)):
    """RAW 层两张原始表的合并汇总。"""
    tables = []
    total = 0
    for name, tag in LEGACY_TABLES:
        r = await db.execute(text(
            "SELECT n_live_tup::bigint AS row_count FROM pg_stat_user_tables "
            "WHERE schemaname = 'legacy' AND relname = :name"
        ), {"name": name})
        row = r.mappings().first()
        cnt = int(row["row_count"]) if row else 0
        total += cnt
        tables.append({"table_name": name, "tag": tag, "row_count": cnt})

    col_r = await db.execute(text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = 'legacy' AND table_name = :name"
    ), {"name": SAMPLE_TABLE})
    col_count = int(col_r.scalar() or 0)

    return {
        "tables": tables,
        "total_rows": total,
        "column_count": col_count,
        "note": "两表结构完全一致（27 列），合并为统一 RAW 层",
    }


# ── 字段元数据与采样 ──────────────────────────────────────────────

@router.get("/fields")
async def list_fields(db: AsyncSession = Depends(get_db)):
    """RAW 层 27 个字段的元数据和质量统计（两表一致，只查一张）。"""
    columns = await db.execute(text("""
        SELECT column_name, data_type, ordinal_position,
               (is_nullable = 'YES') AS is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'legacy' AND table_name = :table_name
        ORDER BY ordinal_position
    """), {"table_name": SAMPLE_TABLE})
    col_rows = [dict(r) for r in columns.mappings().all()]

    stats = await db.execute(text("""
        SELECT attname AS column_name, null_frac, n_distinct,
               most_common_vals::text AS most_common_vals
        FROM pg_stats
        WHERE schemaname = 'legacy' AND tablename = :table_name
    """), {"table_name": SAMPLE_TABLE})
    stats_map = {r["column_name"]: dict(r) for r in stats.mappings().all()}

    items = []
    for col in col_rows:
        s = stats_map.get(col["column_name"], {})
        items.append({
            **col,
            "null_frac": float(s["null_frac"]) if s.get("null_frac") is not None else None,
            "n_distinct": float(s["n_distinct"]) if s.get("n_distinct") is not None else None,
        })
    return {"fields": items}


@router.get("/fields/{column_name}/sample")
async def field_sample(
    column_name: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """采样字段值（TABLESAMPLE 快速）。"""
    valid = await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'legacy' AND table_name = :t"
    ), {"t": SAMPLE_TABLE})
    if column_name not in {r["column_name"] for r in valid.mappings().all()}:
        return {"error": f"字段 {column_name} 不存在"}

    result = await db.execute(text(f"""
        SELECT "{column_name}" AS value, count(*) AS cnt
        FROM legacy."{SAMPLE_TABLE}" TABLESAMPLE BERNOULLI(0.01)
        WHERE "{column_name}" IS NOT NULL
        GROUP BY "{column_name}" ORDER BY cnt DESC LIMIT :limit
    """), {"limit": limit})
    samples = [{"value": str(r["value"]), "count": int(r["cnt"])} for r in result.mappings().all()]

    stat = await db.execute(text(
        "SELECT null_frac, n_distinct FROM pg_stats "
        "WHERE schemaname = 'legacy' AND tablename = :t AND attname = :c"
    ), {"t": SAMPLE_TABLE, "c": column_name})
    sr = stat.mappings().first()

    return {
        "column_name": column_name,
        "null_frac": float(sr["null_frac"]) if sr and sr["null_frac"] is not None else None,
        "n_distinct": float(sr["n_distinct"]) if sr and sr["n_distinct"] is not None else None,
        "samples": samples,
    }


@router.get("/fields/{column_name}/distribution")
async def field_distribution(
    column_name: str,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """字段值分布 TOP N。"""
    valid = await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'legacy' AND table_name = :t"
    ), {"t": SAMPLE_TABLE})
    if column_name not in {r["column_name"] for r in valid.mappings().all()}:
        return {"error": f"字段 {column_name} 不存在"}

    result = await db.execute(text(f"""
        SELECT "{column_name}"::text AS value, count(*) AS cnt
        FROM legacy."{SAMPLE_TABLE}" TABLESAMPLE BERNOULLI(0.1)
        GROUP BY "{column_name}" ORDER BY cnt DESC LIMIT :limit
    """), {"limit": limit})
    rows = [{"value": r["value"], "count": int(r["cnt"])} for r in result.mappings().all()]
    total = sum(r["count"] for r in rows)
    for r in rows:
        r["ratio"] = round(r["count"] / total, 4) if total else 0
    return {"column_name": column_name, "distribution": rows, "sample_total": total}


# ── 字段决策 ──────────────────────────────────────────────────────

@router.get("/decisions")
async def list_decisions(db: AsyncSession = Depends(get_db)):
    """获取 RAW 层 27 个字段的决策（统一 sdk_raw）。"""
    result = await db.execute(text("""
        SELECT source_table, column_name, ordinal_position, data_type,
               decision, ods_name, ods_type, category, description, notes, updated_at
        FROM rebuild2_meta.field_audit
        WHERE source_table = :src
        ORDER BY ordinal_position
    """), {"src": DECISION_SOURCE})
    rows = [dict(r) for r in result.mappings().all()]
    summary = {}
    for r in rows:
        summary[r["decision"]] = summary.get(r["decision"], 0) + 1
    return {"summary": summary, "items": rows}


@router.put("/decisions")
async def save_decision(body: FieldDecision, db: AsyncSession = Depends(get_db)):
    """保存单个字段的决策。"""
    await db.execute(text("""
        UPDATE rebuild2_meta.field_audit
        SET decision = :decision,
            ods_name = :ods_name, ods_type = :ods_type,
            description = COALESCE(:description, description),
            notes = :notes, updated_by = 'user', updated_at = now()
        WHERE source_table = :src AND column_name = :column_name
    """), {
        "src": DECISION_SOURCE,
        "column_name": body.column_name,
        "decision": body.decision,
        "ods_name": body.ods_name,
        "ods_type": body.ods_type,
        "description": body.description,
        "notes": body.notes,
    })
    await db.commit()
    return {"ok": True, "column_name": body.column_name, "decision": body.decision}


# ── L0 目标字段 ───────────────────────────────────────────────────

@router.get("/l0-fields")
async def list_l0_fields(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """L0 目标字段定义列表。"""
    where = "WHERE category = :category" if category else ""
    params = {"category": category} if category else {}
    result = await db.execute(text(f"""
        SELECT field_name, field_name_cn, data_type, category, source_type, description
        FROM rebuild2_meta.target_field
        {where}
        ORDER BY
          CASE category
            WHEN '标识' THEN 1 WHEN '来源' THEN 2 WHEN '解析' THEN 3 WHEN '补齐' THEN 4
            WHEN '网络' THEN 5 WHEN '信号' THEN 6 WHEN '时间' THEN 7 WHEN '位置' THEN 8
            WHEN '元数据' THEN 9 ELSE 10
          END, field_name
    """), params)
    rows = [dict(r) for r in result.mappings().all()]
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r)
    return {
        "total": len(rows),
        "categories": {k: len(v) for k, v in cats.items()},
        "items": rows,
    }
