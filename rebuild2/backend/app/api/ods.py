"""ODS 标准化 API：清洗规则管理 + 执行统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/ods", tags=["ods"])


@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db)):
    """获取全部 ODS 清洗规则。"""
    result = await db.execute(text("""
        SELECT id, field_name, field_name_cn, rule_code, rule_type,
               condition_sql, action, severity, category,
               description, is_active, sort_order
        FROM rebuild2_meta.ods_clean_rule
        ORDER BY sort_order, id
    """))
    rows = [dict(r) for r in result.mappings().all()]

    summary = {
        "total": len(rows),
        "active": sum(1 for r in rows if r["is_active"]),
        "delete": sum(1 for r in rows if r["rule_type"] == "delete" and r["is_active"]),
        "nullify": sum(1 for r in rows if r["rule_type"] == "nullify" and r["is_active"]),
        "convert": sum(1 for r in rows if r["rule_type"] == "convert" and r["is_active"]),
    }
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r)
    return {"summary": summary, "categories": {k: len(v) for k, v in cats.items()}, "items": rows}


@router.get("/rules/preview")
async def preview_rules(db: AsyncSession = Depends(get_db)):
    """在样本表上预估每条规则的影响行数。"""
    rules = await db.execute(text("""
        SELECT rule_code, field_name_cn, rule_type, condition_sql, action, description
        FROM rebuild2_meta.ods_clean_rule
        WHERE is_active = true
        ORDER BY sort_order
    """))
    rule_rows = [dict(r) for r in rules.mappings().all()]

    # 从 ods_clean_result 读取预算结果（不再实时查大表）
    cached = await db.execute(text("""
        SELECT rule_code, total_rows, affected_rows, affect_rate
        FROM rebuild2_meta.ods_clean_result
        WHERE run_label = 'l0_gps'
    """))
    cache_map = {r["rule_code"]: dict(r) for r in cached.mappings().all()}
    total = int(cache_map[next(iter(cache_map))]["total_rows"]) if cache_map else 0

    results = []
    for rule in rule_rows:
        c = cache_map.get(rule["rule_code"], {})
        affected = int(c.get("affected_rows", 0))
        rate = float(c.get("affect_rate", 0))

        results.append({
            **rule,
            "total_rows": total,
            "affected_rows": affected,
            "affect_rate": rate if rate else (round(affected / total, 4) if total > 0 else None),
        })

    return {"total_rows": total, "rules": results}


@router.get("/results")
async def list_results(db: AsyncSession = Depends(get_db)):
    """获取两张 L0 表的清洗统计结果。"""
    tables = {}
    for run_label in ("l0_gps", "l0_lac"):
        result = await db.execute(text("""
            SELECT r.rule_code, c.field_name_cn, c.rule_type, c.description, c.category, c.severity,
                   r.total_rows, r.affected_rows, r.affect_rate, r.executed_at
            FROM rebuild2_meta.ods_clean_result r
            JOIN rebuild2_meta.ods_clean_rule c ON c.rule_code = r.rule_code
            WHERE r.run_label = :label
            ORDER BY c.sort_order
        """), {"label": run_label})
        rows = [dict(r) for r in result.mappings().all()]
        if rows:
            tables[run_label] = {
                "total_rows": int(rows[0]["total_rows"]) if rows else 0,
                "rules": rows,
            }
    return {"tables": tables}
