"""过程字段列表与字段详情。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.labels import table_label
from app.services.workbench.base import fetch_all, first, scalar, to_number
from app.services.workbench.catalog import ensure_field_registry


async def _steps_by_field(db: AsyncSession) -> dict[tuple[str, str], list[str]]:
    """构建 (schema, table) -> [step_id, ...] 映射。"""
    step_rows = await fetch_all(
        db,
        "SELECT step_id, input_tables, output_tables FROM workbench.wb_step_registry ORDER BY step_order",
    )
    mapping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in step_rows:
        for table_name in (row["input_tables"] or []) + (row["output_tables"] or []):
            mapping[("pipeline", table_name)].append(row["step_id"])
    return mapping


def _health_status(lifecycle_status: str, null_rate: float | None) -> str:
    if lifecycle_status in {"missing", "drifted"}:
        return "异常"
    if null_rate is None:
        return "待分析"
    if null_rate >= 0.8:
        return "异常"
    if null_rate >= 0.3:
        return "关注"
    return "正常"


async def list_fields(
    db: AsyncSession,
    *,
    search: str | None = None,
    table_name: str | None = None,
    lifecycle_status: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    """获取过程字段（pipeline schema）注册列表。"""
    await ensure_field_registry(db)  # 内部有跳过条件，非首次几乎无开销
    field_rows = await fetch_all(
        db,
        """
        SELECT id, field_name, field_name_cn, table_name, schema_name, data_type,
               is_nullable, lifecycle_status, field_scope, description
        FROM meta.meta_field_registry
        WHERE schema_name = 'pipeline' AND field_scope = 'pipeline'
        ORDER BY table_name, field_name
        """,
    )
    stats_rows = await fetch_all(
        db,
        """
        SELECT tablename AS table_name, attname AS field_name, null_frac, n_distinct
        FROM pg_stats
        WHERE schemaname = 'pipeline'
        """,
    )
    stats_map = {(row["table_name"], row["field_name"]): row for row in stats_rows}
    step_map = await _steps_by_field(db)

    items = []
    for row in field_rows:
        impacted_steps = step_map.get((row["schema_name"], row["table_name"]), [])
        if search and search not in row["field_name"] and search not in (row["field_name_cn"] or ""):
            continue
        if table_name and row["table_name"] != table_name:
            continue
        if lifecycle_status and row["lifecycle_status"] != lifecycle_status:
            continue
        if step_id and step_id not in impacted_steps:
            continue

        stats = stats_map.get((row["table_name"], row["field_name"]), {})
        null_rate = float(stats["null_frac"]) if stats.get("null_frac") is not None else None
        items.append(
            {
                **row,
                "table_name_cn": table_label(row["table_name"]),
                "null_rate": null_rate,
                "distinct_estimate": to_number(stats.get("n_distinct")),
                "health_status": _health_status(row["lifecycle_status"], null_rate),
                "impacted_steps": impacted_steps,
            }
        )

    summary = {
        "total": len(items),
        "normal": sum(1 for item in items if item["health_status"] == "正常"),
        "attention": sum(1 for item in items if item["health_status"] == "关注"),
        "anomalous": sum(1 for item in items if item["health_status"] == "异常"),
        "pending": sum(1 for item in items if item["health_status"] == "待分析"),
    }
    return {"summary": summary, "items": items}


async def get_field_detail(db: AsyncSession, field_name: str, table_name: str | None = None) -> dict[str, Any] | None:
    """获取单个过程字段详情。"""
    await ensure_field_registry(db)  # 内部有跳过条件
    if not table_name:
        duplicate_count = await scalar(
            db,
            """
            SELECT count(*)
            FROM meta.meta_field_registry
            WHERE field_scope = 'pipeline' AND field_name = :field_name
            """,
            {"field_name": field_name},
        )
        if int(duplicate_count or 0) > 1:
            raise ValueError(f"字段 {field_name} 存在重名，请传 table_name 精确定位。")

    params: dict[str, Any] = {"field_name": field_name}
    where = "field_name = :field_name"
    if table_name:
        where += " AND table_name = :table_name"
        params["table_name"] = table_name
    row = await first(
        db,
        f"""
        SELECT * FROM meta.meta_field_registry
        WHERE {where}
        ORDER BY table_name
        LIMIT 1
        """,
        params,
    )
    if not row:
        return None

    stats = await first(
        db,
        """
        SELECT null_frac, n_distinct
        FROM pg_stats
        WHERE schemaname = :schema_name AND tablename = :table_name AND attname = :field_name
        """,
        {
            "schema_name": row["schema_name"],
            "table_name": row["table_name"],
            "field_name": row["field_name"],
        },
    )
    health_rows = await fetch_all(
        db,
        """
        SELECT total_rows, null_count, null_rate, distinct_count, is_anomalous, anomaly_reason, created_at
        FROM meta.meta_field_health
        WHERE field_id = :field_id
        ORDER BY created_at DESC
        LIMIT 20
        """,
        {"field_id": row["id"]},
    )
    mapping_rules = await fetch_all(
        db,
        """
        SELECT rule_type, rule_expression, source_field, source_table, priority, is_active, version_tag
        FROM meta.meta_field_mapping_rule
        WHERE field_id = :field_id
        ORDER BY priority
        """,
        {"field_id": row["id"]},
    )
    change_log = await fetch_all(
        db,
        """
        SELECT change_type, old_value, new_value, reason, changed_by, created_at
        FROM meta.meta_field_change_log
        WHERE field_id = :field_id
        ORDER BY created_at DESC
        LIMIT 20
        """,
        {"field_id": row["id"]},
    )

    impacted_steps = (await _steps_by_field(db)).get((row["schema_name"], row["table_name"]), [])
    null_rate = float(stats["null_frac"]) if stats and stats.get("null_frac") is not None else None
    return {
        "field": {
            **row,
            "table_name_cn": table_label(row["table_name"]),
            "health_status": _health_status(row["lifecycle_status"], null_rate),
        },
        "health": {
            "null_rate": null_rate,
            "distinct_estimate": to_number(stats.get("n_distinct")) if stats else None,
            "history": health_rows,
        },
        "related_steps": impacted_steps,
        "mapping_rules": mapping_rules,
        "change_log": change_log,
    }
