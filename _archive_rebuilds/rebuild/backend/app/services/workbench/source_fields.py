"""源字段合规治理、趋势与快照刷新。"""

from __future__ import annotations

from collections import defaultdict
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workbench.base import fetch_all, first, to_json
from app.services.workbench.catalog import (
    latest_completed_run_id,
    latest_run_id,
    previous_completed_run_id,
    resolve_run_parameters,
)
from app.services.workbench.source_field_rules import (
    compile_compliance_predicates,
    resolve_rule_parameter,
    sql_identifier,
)


async def _steps_by_field(db: AsyncSession) -> dict[tuple[str, str], list[str]]:
    step_rows = await fetch_all(
        db,
        "SELECT step_id, input_tables, output_tables FROM workbench.wb_step_registry ORDER BY step_order",
    )
    mapping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in step_rows:
        for table_name in (row["input_tables"] or []) + (row["output_tables"] or []):
            mapping[("pipeline", table_name)].append(row["step_id"])
    return mapping


async def _resolve_refresh_run_id(db: AsyncSession, run_id: int | None) -> int | None:
    latest_run = await latest_completed_run_id(db)
    if latest_run is None:
        return None
    if run_id is not None and run_id != latest_run:
        raise ValueError(f"只允许刷新最新完成的 run（#{latest_run}），历史 run #{run_id} 默认只读。")
    return run_id or latest_run


async def list_source_fields(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    search: str | None = None,
    logical_domain: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """获取源字段列表及最新合规率。"""
    resolved_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    field_rows = await fetch_all(
        db,
        """
        SELECT r.id, r.field_name, r.field_name_cn, r.table_name, r.schema_name,
               r.data_type, r.field_scope, r.logical_domain, r.unit, r.description,
               c.rule_type, c.severity, c.business_definition,
               s.compliance_rate, s.null_rate, s.anomalous_rows, s.total_rows, s.run_id AS snapshot_run_id,
               map.mapping_targets
        FROM meta.meta_field_registry r
        LEFT JOIN meta.meta_source_field_compliance c ON c.field_id = r.id AND c.is_active = true
        LEFT JOIN meta.meta_source_field_compliance_snapshot s
            ON s.field_id = r.id AND s.run_id = :run_id AND s.dimension_key = 'ALL'
        LEFT JOIN LATERAL (
            SELECT string_agg(rule_expression, '；' ORDER BY priority, id) AS mapping_targets
            FROM meta.meta_field_mapping_rule m
            WHERE m.field_id = r.id AND m.is_active = true
        ) map ON true
        WHERE r.field_scope = 'source'
        ORDER BY r.logical_domain, r.field_name
        """,
        {"run_id": resolved_run_id},
    )

    step_map = await _steps_by_field(db)
    items = []
    for row in field_rows:
        if search and search not in row["field_name"] and search not in (row["field_name_cn"] or ""):
            continue
        if logical_domain and row["logical_domain"] != logical_domain:
            continue

        compliance_rate = float(row["compliance_rate"]) if row.get("compliance_rate") is not None else None
        null_rate = float(row["null_rate"]) if row.get("null_rate") is not None else None
        status = "正常"
        if compliance_rate is not None and compliance_rate < 0.9:
            status = "异常" if compliance_rate < 0.7 else "关注"
        elif null_rate is not None and null_rate > 0.5:
            status = "关注"

        impacted_steps = step_map.get(("pipeline", row["table_name"]), [])
        items.append(
            {
                "field_name": row["field_name"],
                "field_name_cn": row["field_name_cn"],
                "logical_domain": row["logical_domain"],
                "data_type": row["data_type"],
                "unit": row["unit"],
                "rule_type": row["rule_type"],
                "severity": row["severity"],
                "compliance_rate": compliance_rate,
                "null_rate": null_rate,
                "anomalous_rows": int(row["anomalous_rows"]) if row.get("anomalous_rows") is not None else None,
                "total_rows": int(row["total_rows"]) if row.get("total_rows") is not None else None,
                "status": status,
                "impacted_steps": impacted_steps,
                "mapping_targets": row.get("mapping_targets"),
                "has_snapshot": row.get("snapshot_run_id") is not None,
            }
        )

    summary = {
        "total": len(items),
        "normal": sum(1 for i in items if i["status"] == "正常"),
        "attention": sum(1 for i in items if i["status"] == "关注"),
        "anomalous": sum(1 for i in items if i["status"] == "异常"),
    }
    return {"run_id": resolved_run_id, "summary": summary, "items": items}


async def get_source_field_detail(
    db: AsyncSession,
    field_name: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any] | None:
    """获取单个源字段详情，包含当前/对比快照。"""
    row = await first(
        db,
        """
        SELECT *
        FROM meta.meta_field_registry
        WHERE field_scope = 'source' AND field_name = :field_name
        ORDER BY table_name
        LIMIT 1
        """,
        {"field_name": field_name},
    )
    if not row:
        return None

    compliance_rule = await first(
        db,
        """
        SELECT *
        FROM meta.meta_source_field_compliance
        WHERE field_id = :field_id AND is_active = true
        ORDER BY id DESC
        LIMIT 1
        """,
        {"field_id": row["id"]},
    )
    resolved_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    target_compare_run_id = compare_run_id or (
        await previous_completed_run_id(db, resolved_run_id) if resolved_run_id else None
    )

    latest_snapshot = await first(
        db,
        """
        SELECT *
        FROM meta.meta_source_field_compliance_snapshot
        WHERE field_id = :field_id AND run_id = :run_id AND dimension_key = 'ALL'
        ORDER BY id DESC
        LIMIT 1
        """,
        {"field_id": row["id"], "run_id": resolved_run_id},
    )
    compare_snapshot = await first(
        db,
        """
        SELECT *
        FROM meta.meta_source_field_compliance_snapshot
        WHERE field_id = :field_id AND run_id = :run_id AND dimension_key = 'ALL'
        ORDER BY id DESC
        LIMIT 1
        """,
        {"field_id": row["id"], "run_id": target_compare_run_id},
    ) if target_compare_run_id else None

    trend = await fetch_all(
        db,
        """
        SELECT run_id, compliance_rate, null_rate,
               anomalous_rows, total_rows, created_at
        FROM meta.meta_source_field_compliance_snapshot
        WHERE field_id = :field_id AND dimension_key = 'ALL'
        ORDER BY run_id DESC
        LIMIT 10
        """,
        {"field_id": row["id"]},
    )
    mappings = await fetch_all(
        db,
        """
        SELECT rule_type, rule_expression, source_field, source_table
        FROM meta.meta_field_mapping_rule
        WHERE field_id = :field_id AND is_active = true
        ORDER BY priority
        """,
        {"field_id": row["id"]},
    )
    step_map = await _steps_by_field(db)
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

    compare_delta = None
    if latest_snapshot and compare_snapshot:
        compare_delta = {
            "compliance_rate_delta": (
                float(latest_snapshot["compliance_rate"]) - float(compare_snapshot["compliance_rate"])
                if latest_snapshot.get("compliance_rate") is not None and compare_snapshot.get("compliance_rate") is not None
                else None
            ),
            "null_rate_delta": (
                float(latest_snapshot["null_rate"]) - float(compare_snapshot["null_rate"])
                if latest_snapshot.get("null_rate") is not None and compare_snapshot.get("null_rate") is not None
                else None
            ),
            "anomalous_rows_delta": int(latest_snapshot["anomalous_rows"]) - int(compare_snapshot["anomalous_rows"]),
        }

    return {
        "field": {
            "field_name": row["field_name"],
            "field_name_cn": row["field_name_cn"],
            "logical_domain": row["logical_domain"],
            "data_type": row["data_type"],
            "unit": row["unit"],
            "description": row["description"],
            "field_scope": row["field_scope"],
        },
        "run_id": resolved_run_id,
        "compare_run_id": target_compare_run_id,
        "compliance_rule": dict(compliance_rule) if compliance_rule else None,
        "latest_snapshot": dict(latest_snapshot) if latest_snapshot else None,
        "compare_snapshot": dict(compare_snapshot) if compare_snapshot else None,
        "compare_delta": compare_delta,
        "trend": trend,
        "mappings": mappings,
        "related_steps": step_map.get(("pipeline", row["table_name"]), []),
        "change_log": change_log,
    }


async def list_source_field_trend(
    db: AsyncSession,
    field_name: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    row = await first(
        db,
        """
        SELECT id
        FROM meta.meta_field_registry
        WHERE field_scope = 'source' AND field_name = :field_name
        ORDER BY table_name
        LIMIT 1
        """,
        {"field_name": field_name},
    )
    if not row:
        return {"field_name": field_name, "history": []}

    history = await fetch_all(
        db,
        """
        SELECT run_id, compliance_rate, null_rate,
               anomalous_rows, total_rows, created_at
        FROM meta.meta_source_field_compliance_snapshot
        WHERE field_id = :field_id AND dimension_key = 'ALL'
        ORDER BY run_id DESC
        LIMIT :limit
        """,
        {"field_id": row["id"], "limit": limit},
    )
    return {"field_name": field_name, "history": history}


def compile_compliance_sql(
    field_name: str,
    rule_type: str,
    rule_config: dict[str, Any],
    parameter_values: Any,
) -> str:
    return compile_compliance_predicates(field_name, rule_type, rule_config, parameter_values)["compliant"]


async def refresh_source_field_snapshots(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """对所有活跃源字段合规规则运行全量计算，写入快照表。"""
    resolved_run_id = await _resolve_refresh_run_id(db, run_id)
    if resolved_run_id is None:
        return {"run_id": None, "refreshed_fields": 0, "snapshot_rows": 0, "duration_seconds": 0}

    start = time.monotonic()
    params = await resolve_run_parameters(db, resolved_run_id)
    rules = await fetch_all(
        db,
        """
        SELECT c.id, c.field_id, r.field_name, c.version_tag,
               c.rule_type, c.rule_config, c.parameter_refs, r.table_name
        FROM meta.meta_source_field_compliance c
        JOIN meta.meta_field_registry r ON r.id = c.field_id
        WHERE c.is_active = true AND r.field_scope = 'source'
        ORDER BY r.field_name
        """,
    )
    if not rules:
        return {"run_id": resolved_run_id, "refreshed_fields": 0, "snapshot_rows": 0, "duration_seconds": 0}

    if force:
        await db.execute(
            text("DELETE FROM meta.meta_source_field_compliance_snapshot WHERE run_id = :run_id"),
            {"run_id": resolved_run_id},
        )

    refreshed = 0
    snapshot_rows = 0
    for rule in rules:
        rule_config = rule["rule_config"] or {}
        param_refs = [str(item) for item in (rule["parameter_refs"] or [])]
        param_value = resolve_rule_parameter(params, param_refs)
        predicates = compile_compliance_predicates(rule["field_name"], rule["rule_type"], rule_config, param_value)
        field = sql_identifier(rule["field_name"])
        table_name = sql_identifier(rule["table_name"] or "fact_filtered")
        anomalous_expr = f"{field} IS NOT NULL AND NOT ({predicates['compliant']})"
        stats = await fetch_all(
            db,
            f"""
            SELECT
                CASE
                    WHEN GROUPING(operator_id_raw) = 1 AND GROUPING(tech_norm) = 1 THEN 'ALL'
                    WHEN GROUPING(operator_id_raw) = 0 AND GROUPING(tech_norm) = 1 THEN 'operator:' || COALESCE(operator_id_raw, 'NULL')
                    WHEN GROUPING(operator_id_raw) = 1 AND GROUPING(tech_norm) = 0 THEN 'tech:' || COALESCE(tech_norm, 'NULL')
                    ELSE 'operator:' || COALESCE(operator_id_raw, 'NULL') || '|tech:' || COALESCE(tech_norm, 'NULL')
                END AS dimension_key,
                count(*) AS total_rows,
                count({field}) AS nonnull_rows,
                count(*) - count({field}) AS null_rows,
                count(*) FILTER (WHERE {predicates['invalid']}) AS invalid_value_rows,
                count(*) FILTER (WHERE {predicates['out_of_range']}) AS out_of_range_rows,
                count(*) FILTER (WHERE {predicates['compliant']}) AS compliant_rows,
                count(*) FILTER (WHERE {anomalous_expr}) AS anomalous_rows
            FROM pipeline.{table_name}
            GROUP BY GROUPING SETS ((), (operator_id_raw), (tech_norm), (operator_id_raw, tech_norm))
            """,
        )
        if not stats:
            continue

        payload = []
        for stat in stats:
            total = int(stat["total_rows"])
            nonnull = int(stat["nonnull_rows"])
            null_cnt = int(stat["null_rows"])
            invalid_rows = int(stat["invalid_value_rows"])
            out_of_range_rows = int(stat["out_of_range_rows"])
            compliant = int(stat["compliant_rows"])
            anomalous = int(stat["anomalous_rows"])
            payload.append(
                {
                    "field_id": rule["field_id"],
                    "run_id": resolved_run_id,
                    "compliance_version": rule["version_tag"],
                    "source_table": f"pipeline.{table_name}",
                    "batch_label": f"run-{resolved_run_id}",
                    "dimension_key": stat["dimension_key"],
                    "total_rows": total,
                    "nonnull_rows": nonnull,
                    "compliant_rows": compliant,
                    "anomalous_rows": anomalous,
                    "null_rows": null_cnt,
                    "invalid_value_rows": invalid_rows,
                    "out_of_range_rows": out_of_range_rows,
                    "compliance_rate": round(compliant / nonnull, 4) if nonnull > 0 else None,
                    "null_rate": round(null_cnt / total, 4) if total > 0 else None,
                    "parameter_values": to_json(param_value),
                }
            )

        await db.execute(
            text(
                """
                INSERT INTO meta.meta_source_field_compliance_snapshot (
                    field_id, run_id, compliance_version, source_table, batch_label, dimension_key,
                    total_rows, nonnull_rows, compliant_rows, anomalous_rows,
                    null_rows, invalid_value_rows, out_of_range_rows,
                    compliance_rate, null_rate, parameter_values
                ) VALUES (
                    :field_id, :run_id, :compliance_version, :source_table, :batch_label, :dimension_key,
                    :total_rows, :nonnull_rows, :compliant_rows, :anomalous_rows,
                    :null_rows, :invalid_value_rows, :out_of_range_rows,
                    :compliance_rate, :null_rate, CAST(:parameter_values AS jsonb)
                )
                ON CONFLICT (field_id, run_id, dimension_key, compliance_version)
                DO UPDATE SET
                    source_table = EXCLUDED.source_table,
                    batch_label = EXCLUDED.batch_label,
                    total_rows = EXCLUDED.total_rows,
                    nonnull_rows = EXCLUDED.nonnull_rows,
                    compliant_rows = EXCLUDED.compliant_rows,
                    anomalous_rows = EXCLUDED.anomalous_rows,
                    null_rows = EXCLUDED.null_rows,
                    invalid_value_rows = EXCLUDED.invalid_value_rows,
                    out_of_range_rows = EXCLUDED.out_of_range_rows,
                    compliance_rate = EXCLUDED.compliance_rate,
                    null_rate = EXCLUDED.null_rate,
                    parameter_values = EXCLUDED.parameter_values,
                    created_at = now()
                """
            ),
            payload,
        )
        refreshed += 1
        snapshot_rows += len(payload)

    await db.commit()
    return {
        "run_id": resolved_run_id,
        "refreshed_fields": refreshed,
        "snapshot_rows": snapshot_rows,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
