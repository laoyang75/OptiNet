"""引导数据初始化、字段注册同步、run/version 上下文与版本历史。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.labels import FIELD_LABELS, STEP_PURPOSES, field_label, run_mode_label, status_label, table_label
from app.services.workbench.base import (
    DEFAULT_CONTRACT_VERSION,
    DEFAULT_RULE_SET,
    DEFAULT_RULE_SET_VERSION,
    DEFAULT_SAMPLE_SETS,
    DEFAULT_SQL_BUNDLE_VERSION,
    TABLE_LABELS,
    _BOOTSTRAP_LOCK,
    fetch_all,
    first,
    format_duration,
    now_iso,
    resolve_sql_candidates,
    scalar,
    to_json,
)


# ── 引导数据 ──────────────────────────────────────────────────────

_REFERENCE_DATA_READY = False


async def ensure_reference_data(db: AsyncSession) -> dict[str, Any]:
    """确保规则集、SQL 包、契约、样本集等引用数据已初始化。"""
    global _REFERENCE_DATA_READY
    if _REFERENCE_DATA_READY:
        current = await first(
            db,
            "SELECT id, version_tag FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1",
        )
        return {
            "parameter_set_id": current["id"] if current else None,
            "parameter_set_version": current["version_tag"] if current else None,
        }

    async with _BOOTSTRAP_LOCK:
        if _REFERENCE_DATA_READY:
            current = await first(
                db,
                "SELECT id, version_tag FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1",
            )
            return {
                "parameter_set_id": current["id"] if current else None,
                "parameter_set_version": current["version_tag"] if current else None,
            }

        current = await first(
            db,
            "SELECT id, version_tag FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1",
        )

        if await scalar(db, "SELECT count(*) FROM workbench.wb_rule_set WHERE version_tag = :tag", {"tag": DEFAULT_RULE_SET_VERSION}) == 0:
            await db.execute(
                text("""
                    INSERT INTO workbench.wb_rule_set (version_tag, description, rules)
                    VALUES (:version_tag, :description, CAST(:rules AS jsonb))
                """),
                {
                    "version_tag": DEFAULT_RULE_SET_VERSION,
                    "description": "工作台默认规则集（由步骤级规则目录初始化）",
                    "rules": to_json(DEFAULT_RULE_SET),
                },
            )

        if await scalar(db, "SELECT count(*) FROM workbench.wb_sql_bundle WHERE version_tag = :tag", {"tag": DEFAULT_SQL_BUNDLE_VERSION}) == 0:
            step_rows = await fetch_all(db, "SELECT step_id, sql_file FROM workbench.wb_step_registry ORDER BY step_order")
            manifest = [
                {
                    "step_id": row["step_id"],
                    "sql_file": row["sql_file"],
                    "candidates": resolve_sql_candidates(row["sql_file"]),
                }
                for row in step_rows
            ]
            await db.execute(
                text("""
                    INSERT INTO workbench.wb_sql_bundle (version_tag, description, file_manifest)
                    VALUES (:version_tag, :description, CAST(:file_manifest AS jsonb))
                """),
                {
                    "version_tag": DEFAULT_SQL_BUNDLE_VERSION,
                    "description": "工作台默认 SQL 资源版本（自动扫描 lac_enbid_project）",
                    "file_manifest": to_json(manifest),
                },
            )

        if await scalar(db, "SELECT count(*) FROM workbench.wb_contract WHERE version_tag = :tag", {"tag": DEFAULT_CONTRACT_VERSION}) == 0:
            contract_fields = {
                "schemas": ["pipeline", "workbench", "meta"],
                "table_count": len(TABLE_LABELS),
                "field_labels": FIELD_LABELS,
            }
            await db.execute(
                text("""
                    INSERT INTO workbench.wb_contract (version_tag, description, contract_fields)
                    VALUES (:version_tag, :description, CAST(:contract_fields AS jsonb))
                """),
                {
                    "version_tag": DEFAULT_CONTRACT_VERSION,
                    "description": "工作台默认字段契约版本（基于 Doc02/Doc05 初始化）",
                    "contract_fields": to_json(contract_fields),
                },
            )

        step_updates = [
            {"step_id": step_id, "description": description}
            for step_id, description in STEP_PURPOSES.items()
        ]
        await db.execute(
            text("""
                UPDATE workbench.wb_step_registry
                SET description = :description
                WHERE step_id = :step_id AND (description IS NULL OR description = '')
            """),
            step_updates,
        )

        if await scalar(db, "SELECT count(*) FROM workbench.wb_sample_set") == 0:
            await db.execute(
                text("""
                    INSERT INTO workbench.wb_sample_set (name, description, sample_type, filter_criteria, object_ids, created_by)
                    VALUES (:name, :description, :sample_type, CAST(:filter_criteria AS jsonb), CAST(:object_ids AS jsonb), :created_by)
                """),
                [
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "sample_type": item["sample_type"],
                        "filter_criteria": to_json(item["filter_criteria"]),
                        "object_ids": to_json([]),
                        "created_by": "system",
                    }
                    for item in DEFAULT_SAMPLE_SETS
                ],
            )

        ref_ids = await first(
            db,
            """
            SELECT
                (SELECT id FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1) AS parameter_set_id,
                (SELECT id FROM workbench.wb_rule_set WHERE version_tag = :rule_tag LIMIT 1) AS rule_set_id,
                (SELECT id FROM workbench.wb_sql_bundle WHERE version_tag = :sql_tag LIMIT 1) AS sql_bundle_id,
                (SELECT id FROM workbench.wb_contract WHERE version_tag = :contract_tag LIMIT 1) AS contract_id
            """,
            {
                "rule_tag": DEFAULT_RULE_SET_VERSION,
                "sql_tag": DEFAULT_SQL_BUNDLE_VERSION,
                "contract_tag": DEFAULT_CONTRACT_VERSION,
            },
        )
        if ref_ids:
            await db.execute(
                text("""
                    UPDATE workbench.wb_run
                    SET
                        parameter_set_id = COALESCE(parameter_set_id, :parameter_set_id),
                        rule_set_id = COALESCE(rule_set_id, :rule_set_id),
                        sql_bundle_id = COALESCE(sql_bundle_id, :sql_bundle_id),
                        contract_id = COALESCE(contract_id, :contract_id)
                    WHERE
                        parameter_set_id IS NULL
                        OR rule_set_id IS NULL
                        OR sql_bundle_id IS NULL
                        OR contract_id IS NULL
                """),
                ref_ids,
            )

        await db.commit()
        _REFERENCE_DATA_READY = True
        return {
            "parameter_set_id": current["id"] if current else None,
            "parameter_set_version": current["version_tag"] if current else None,
        }


# ── 字段注册表同步 ───────────────────────────────────────────────

async def ensure_field_registry(db: AsyncSession, *, force: bool = False) -> int:
    """从 information_schema 同步 pipeline schema 的字段到 meta.meta_field_registry。

    跳过条件：registry 已有 > 50 行且最近 10 分钟内同步过（除非 force=True）。
    """
    if not force:
        freshness = await first(
            db,
            """
            SELECT count(*) AS cnt,
                   max(updated_at) AS last_sync
            FROM meta.meta_field_registry
            WHERE schema_name = 'pipeline'
            """,
        )
        if freshness and int(freshness["cnt"] or 0) > 50:
            last_sync = freshness.get("last_sync")
            if last_sync is not None:
                from datetime import UTC, datetime, timedelta
                if isinstance(last_sync, str):
                    from datetime import datetime as dt
                    try:
                        last_sync = dt.fromisoformat(last_sync)
                    except (ValueError, TypeError):
                        last_sync = None
                if last_sync and (datetime.now(tz=UTC) - last_sync.replace(tzinfo=UTC)) < timedelta(minutes=10):
                    return int(freshness["cnt"])

    rows = await fetch_all(
        db,
        """
        SELECT
            c.table_schema,
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable = 'YES' AS is_nullable,
            pgd.description AS comment
        FROM information_schema.columns c
        LEFT JOIN pg_catalog.pg_class cls
            ON cls.relname = c.table_name
        LEFT JOIN pg_catalog.pg_namespace nsp
            ON nsp.oid = cls.relnamespace AND nsp.nspname = c.table_schema
        LEFT JOIN pg_catalog.pg_attribute attr
            ON attr.attrelid = cls.oid AND attr.attname = c.column_name
        LEFT JOIN pg_catalog.pg_description pgd
            ON pgd.objoid = cls.oid AND pgd.objsubid = attr.attnum
        WHERE c.table_schema = 'pipeline'
        ORDER BY c.table_name, c.ordinal_position
        """,
    )
    if not rows:
        return 0

    payload = [
        {
            "field_name": row["column_name"],
            "field_name_cn": field_label(row["column_name"]),
            "table_name": row["table_name"],
            "schema_name": row["table_schema"],
            "data_type": row["data_type"],
            "is_nullable": row["is_nullable"],
            "source_field": row["column_name"],
            "source_table": row["table_name"],
            "description": row["comment"] or "",
        }
        for row in rows
    ]
    await db.execute(
        text("""
            INSERT INTO meta.meta_field_registry (
                field_name, field_name_cn, table_name, schema_name, data_type, is_nullable,
                source_field, source_table, description
            )
            VALUES (
                :field_name, :field_name_cn, :table_name, :schema_name, :data_type, :is_nullable,
                :source_field, :source_table, :description
            )
            ON CONFLICT (schema_name, table_name, field_name)
            DO UPDATE SET
                field_name_cn = EXCLUDED.field_name_cn,
                data_type = EXCLUDED.data_type,
                is_nullable = EXCLUDED.is_nullable,
                source_field = EXCLUDED.source_field,
                source_table = EXCLUDED.source_table,
                description = COALESCE(NULLIF(EXCLUDED.description, ''), meta.meta_field_registry.description),
                updated_at = now()
        """),
        payload,
    )
    await db.commit()
    return len(payload)


# ── run_id 查询 ──────────────────────────────────────────────────

async def latest_run_id(db: AsyncSession) -> int | None:
    return await scalar(
        db,
        "SELECT run_id FROM workbench.wb_run ORDER BY started_at DESC, run_id DESC LIMIT 1",
    )


async def latest_completed_run_id(db: AsyncSession) -> int | None:
    return await scalar(
        db,
        "SELECT run_id FROM workbench.wb_run WHERE status = 'completed' ORDER BY started_at DESC, run_id DESC LIMIT 1",
    )


async def previous_completed_run_id(db: AsyncSession, current_run_id: int) -> int | None:
    return await scalar(
        db,
        """
        WITH current_run AS (
            SELECT run_id, started_at
            FROM workbench.wb_run
            WHERE run_id = :run_id
        )
        SELECT candidate.run_id
        FROM current_run current
        JOIN workbench.wb_run candidate
            ON candidate.status = 'completed'
           AND candidate.run_id <> current.run_id
           AND (
                candidate.started_at < current.started_at
                OR (candidate.started_at = current.started_at AND candidate.run_id < current.run_id)
           )
        ORDER BY candidate.started_at DESC, candidate.run_id DESC
        LIMIT 1
        """,
        {"run_id": current_run_id},
    )


async def resolve_run_parameters(db: AsyncSession, run_id: int) -> dict[str, Any]:
    """通过 run_id -> parameter_set_id 追溯参数，严禁读取 is_active。"""
    row = await first(
        db,
        """
        SELECT ps.parameters
        FROM workbench.wb_run r
        JOIN workbench.wb_parameter_set ps ON ps.id = r.parameter_set_id
        WHERE r.run_id = :run_id
        """,
        {"run_id": run_id},
    )
    return row["parameters"] if row else {}


# ── run 摘要 ─────────────────────────────────────────────────────

async def _run_row(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    return await first(
        db,
        """
        SELECT
            r.*,
            p.version_tag AS parameter_version,
            rs.version_tag AS rule_version,
            sb.version_tag AS sql_version,
            c.version_tag AS contract_version,
            b.version_tag AS baseline_version
        FROM workbench.wb_run r
        LEFT JOIN workbench.wb_parameter_set p ON p.id = r.parameter_set_id
        LEFT JOIN workbench.wb_rule_set rs ON rs.id = r.rule_set_id
        LEFT JOIN workbench.wb_sql_bundle sb ON sb.id = r.sql_bundle_id
        LEFT JOIN workbench.wb_contract c ON c.id = r.contract_id
        LEFT JOIN workbench.wb_baseline b ON b.id = r.baseline_id
        WHERE r.run_id = :run_id
        """,
        {"run_id": run_id},
    )


async def _run_layer_counts(db: AsyncSession, run_id: int | None) -> dict[str, int]:
    if not run_id:
        return {}
    rows = await fetch_all(
        db,
        "SELECT layer_id, row_count FROM workbench.wb_layer_snapshot WHERE run_id = :run_id",
        {"run_id": run_id},
    )
    return {row["layer_id"]: int(row["row_count"] or 0) for row in rows}


async def _fallback_pipeline_counts(db: AsyncSession) -> dict[str, int]:
    rows = await fetch_all(
        db,
        """
        SELECT relname, n_live_tup::bigint AS row_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'pipeline' AND relname IN ('raw_records', 'fact_final')
        """,
    )
    return {row["relname"]: int(row["row_count"] or 0) for row in rows}


async def build_run_summary(db: AsyncSession, run_id: int | None) -> dict[str, Any] | None:
    """构建 run 摘要信息，用于版本上下文展示。"""
    if not run_id:
        return None
    row = await _run_row(db, run_id)
    if not row:
        return None
    layer_counts = await _run_layer_counts(db, run_id)
    fallback = await _fallback_pipeline_counts(db) if not layer_counts else {}
    input_rows = layer_counts.get("L0_raw", fallback.get("raw_records"))
    final_rows = layer_counts.get("L4_final", fallback.get("fact_final"))
    return {
        "run_id": row["run_id"],
        "run_mode": row["run_mode"],
        "run_mode_label": run_mode_label(row["run_mode"]),
        "status": row["status"],
        "status_label": status_label(row["status"]),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "duration_seconds": row["duration_seconds"],
        "duration_pretty": format_duration(row["duration_seconds"]),
        "compare_run_id": row["compare_run_id"],
        "parameter_set": row.get("parameter_version") or "—",
        "rule_set": row.get("rule_version") or "—",
        "sql_bundle": row.get("sql_version") or "—",
        "contract": row.get("contract_version") or "—",
        "baseline": row.get("baseline_version") or "—",
        "note": row.get("note"),
        "input_window_start": row.get("input_window_start"),
        "input_window_end": row.get("input_window_end"),
        "input_rows": input_rows,
        "final_rows": final_rows,
        "rerun_from_step": row.get("rerun_from_step"),
        "sample_set_id": row.get("sample_set_id"),
    }


# ── 版本上下文 ───────────────────────────────────────────────────

async def get_version_context(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    """获取当前版本上下文，包含 current_run 和 compare_run。"""
    await ensure_reference_data(db)

    current_run_id = run_id or await latest_run_id(db)
    current = await build_run_summary(db, current_run_id)
    if current is None:
        return {"current_run": None, "compare_run": None, "generated_at": now_iso()}

    selected_compare = compare_run_id or current.get("compare_run_id") or await previous_completed_run_id(db, current_run_id)
    compare = await build_run_summary(db, selected_compare)

    return {
        "generated_at": now_iso(),
        "current_run": current,
        "compare_run": compare,
        "versions": {
            "parameter_set": current.get("parameter_set"),
            "rule_set": current.get("rule_set"),
            "sql_bundle": current.get("sql_bundle"),
            "contract": current.get("contract"),
            "baseline": current.get("baseline"),
        },
    }


async def get_version_history(db: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    """获取最近 N 次 run 的版本历史摘要。"""
    await ensure_reference_data(db)
    rows = await fetch_all(
        db,
        """
        SELECT
            r.run_id, r.run_mode, r.status, r.started_at, r.finished_at, r.duration_seconds,
            p.version_tag AS parameter_version,
            rs.version_tag AS rule_version,
            sb.version_tag AS sql_version,
            c.version_tag AS contract_version,
            b.version_tag AS baseline_version
        FROM workbench.wb_run r
        LEFT JOIN workbench.wb_parameter_set p ON p.id = r.parameter_set_id
        LEFT JOIN workbench.wb_rule_set rs ON rs.id = r.rule_set_id
        LEFT JOIN workbench.wb_sql_bundle sb ON sb.id = r.sql_bundle_id
        LEFT JOIN workbench.wb_contract c ON c.id = r.contract_id
        LEFT JOIN workbench.wb_baseline b ON b.id = r.baseline_id
        ORDER BY r.started_at DESC, r.run_id DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    return [
        {
            **row,
            "run_mode_label": run_mode_label(row["run_mode"]),
            "status_label": status_label(row["status"]),
            "duration_pretty": format_duration(row["duration_seconds"]),
        }
        for row in rows
    ]


async def get_version_change_log(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    """对比两次 run 的参数/规则/SQL/契约版本差异。"""
    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    if current_run_id is None:
        return {"current_run_id": None, "compare_run_id": None, "changes": []}

    target_compare = compare_run_id or await previous_completed_run_id(db, current_run_id)
    if target_compare is None:
        return {"current_run_id": current_run_id, "compare_run_id": None, "changes": []}

    current_row = await _run_row(db, current_run_id)
    compare_row = await _run_row(db, target_compare)
    if not current_row or not compare_row:
        return {"current_run_id": current_run_id, "compare_run_id": target_compare, "changes": []}

    changes = []
    version_keys = [
        ("parameter_version", "参数集"),
        ("rule_version", "规则集"),
        ("sql_version", "SQL版本"),
        ("contract_version", "契约版本"),
        ("baseline_version", "基线版本"),
    ]
    for key, label in version_keys:
        cv = current_row.get(key)
        pv = compare_row.get(key)
        if cv != pv:
            changes.append({"category": label, "current": cv, "compare": pv, "changed": True})
        else:
            changes.append({"category": label, "current": cv, "compare": pv, "changed": False})

    # 参数级 diff
    current_params = await resolve_run_parameters(db, current_run_id)
    compare_params = await resolve_run_parameters(db, target_compare)
    param_changes = []
    all_param_keys = sorted(set(list(current_params.keys()) + list(compare_params.keys())))
    for pk in all_param_keys:
        cv = current_params.get(pk)
        pv = compare_params.get(pk)
        if cv != pv:
            param_changes.append({"section": pk, "current": cv, "compare": pv})

    return {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare,
        "version_changes": changes,
        "parameter_changes": param_changes,
    }
