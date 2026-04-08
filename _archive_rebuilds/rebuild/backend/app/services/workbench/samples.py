"""P4 样本集、run 绑定样本快照与 D3 对象详情。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.labels import table_label
from app.services.workbench.base import SAMPLE_TABLE_CONFIG, fetch_all, first, scalar, to_json
from app.services.workbench.catalog import ensure_reference_data, latest_completed_run_id, latest_run_id, previous_completed_run_id
from app.services.workbench.object_snapshots import ensure_snapshot_tables
from app.services.workbench.sample_support import (
    build_sample_sql,
    changed_fields,
    display_pairs,
    row_object_key,
    row_object_label,
    sample_rule_hits,
)


async def refresh_sample_snapshots(
    db: AsyncSession,
    run_id: int,
    *,
    force: bool = False,
    limit: int = 120,
) -> dict[str, Any]:
    """将活跃样本集的 top-N 结果固化到 run 绑定快照表。"""
    await ensure_snapshot_tables(db)
    await ensure_reference_data(db)
    if force:
        await db.execute(text("DELETE FROM workbench.wb_sample_snapshot WHERE run_id = :run_id"), {"run_id": run_id})

    rows = await fetch_all(
        db,
        """
        SELECT id, name, description, sample_type, filter_criteria, object_ids, is_active, created_at
        FROM workbench.wb_sample_set
        WHERE is_active = true
        ORDER BY id
        """,
    )
    inserted = 0
    for row in rows:
        criteria = row["filter_criteria"] or {}
        sql, params, _, source_table = build_sample_sql(criteria, limit)
        records = await fetch_all(db, sql, params)
        if not records:
            continue
        payload = []
        for index, record in enumerate(records, start=1):
            payload.append(
                {
                    "run_id": run_id,
                    "sample_set_id": row["id"],
                    "source_table": source_table,
                    "rank_order": index,
                    "object_key": row_object_key(source_table, record),
                    "object_label": row_object_label(source_table, record),
                    "record_payload": to_json(record),
                    "rule_hits": to_json(sample_rule_hits(source_table, record)),
                }
            )
        await db.execute(
            text(
                """
                INSERT INTO workbench.wb_sample_snapshot (
                    run_id, sample_set_id, source_table, rank_order, object_key, object_label, record_payload, rule_hits
                ) VALUES (
                    :run_id, :sample_set_id, :source_table, :rank_order, :object_key, :object_label,
                    CAST(:record_payload AS jsonb), CAST(:rule_hits AS jsonb)
                )
                ON CONFLICT (run_id, sample_set_id, object_key)
                DO UPDATE SET
                    source_table = EXCLUDED.source_table,
                    rank_order = EXCLUDED.rank_order,
                    object_label = EXCLUDED.object_label,
                    record_payload = EXCLUDED.record_payload,
                    rule_hits = EXCLUDED.rule_hits,
                    created_at = now()
                """
            ),
            payload,
        )
        inserted += len(payload)
    return {"run_id": run_id, "sample_snapshot_count": inserted}


async def list_sample_sets(db: AsyncSession, *, run_id: int | None = None) -> dict[str, Any]:
    """获取活跃样本集和指定 run 下的快照状态。"""
    await ensure_snapshot_tables(db)
    await ensure_reference_data(db)
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    rows = await fetch_all(
        db,
        """
        SELECT id, name, description, sample_type, filter_criteria, object_ids, is_active, created_at
        FROM workbench.wb_sample_set
        WHERE is_active = true
        ORDER BY id
        """,
    )
    counts = {
        row["sample_set_id"]: int(row["sample_count"])
        for row in await fetch_all(
            db,
            """
            SELECT sample_set_id, count(*) AS sample_count
            FROM workbench.wb_sample_snapshot
            WHERE run_id = :run_id
            GROUP BY sample_set_id
            """,
            {"run_id": selected_run_id},
        )
    } if selected_run_id else {}

    items = []
    for row in rows:
        criteria = row["filter_criteria"] or {}
        items.append(
            {
                **row,
                "source_table": criteria.get("source_table"),
                "source_table_cn": table_label(criteria.get("source_table", "")),
                "step_ids": criteria.get("step_ids", []),
                "sample_count": counts.get(row["id"], 0),
                "snapshot_ready": counts.get(row["id"], 0) > 0,
            }
        )
    return {"run_id": selected_run_id, "items": items}


async def get_sample_set_detail(
    db: AsyncSession,
    sample_set_id: int,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any] | None:
    """获取样本集详情、当前/对比 run 的样本快照与 compare 概览。"""
    await ensure_snapshot_tables(db)
    row = await first(
        db,
        """
        SELECT id, name, description, sample_type, filter_criteria, object_ids, is_active, created_at
        FROM workbench.wb_sample_set
        WHERE id = :sample_set_id
        """,
        {"sample_set_id": sample_set_id},
    )
    if not row:
        return None

    criteria = row["filter_criteria"] or {}
    source_table = criteria.get("source_table")
    columns = SAMPLE_TABLE_CONFIG[source_table]["columns"] if source_table in SAMPLE_TABLE_CONFIG else []
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    target_compare_run_id = compare_run_id or (
        await previous_completed_run_id(db, selected_run_id) if selected_run_id else None
    )

    current_rows = await fetch_all(
        db,
        """
        SELECT rank_order, object_key, object_label, record_payload, rule_hits
        FROM workbench.wb_sample_snapshot
        WHERE run_id = :run_id AND sample_set_id = :sample_set_id
        ORDER BY rank_order
        LIMIT :limit
        """,
        {"run_id": selected_run_id, "sample_set_id": sample_set_id, "limit": limit},
    ) if selected_run_id else []
    compare_preview_rows = await fetch_all(
        db,
        """
        SELECT rank_order, object_key, object_label, record_payload, rule_hits
        FROM workbench.wb_sample_snapshot
        WHERE run_id = :run_id AND sample_set_id = :sample_set_id
        ORDER BY rank_order
        LIMIT :limit
        """,
        {"run_id": target_compare_run_id, "sample_set_id": sample_set_id, "limit": limit},
    ) if target_compare_run_id else []
    current_keys = [row["object_key"] for row in current_rows]
    compare_rows = await fetch_all(
        db,
        """
        SELECT rank_order, object_key, object_label, record_payload, rule_hits
        FROM workbench.wb_sample_snapshot
        WHERE run_id = :run_id
          AND sample_set_id = :sample_set_id
          AND object_key = ANY(:object_keys)
        """,
        {"run_id": target_compare_run_id, "sample_set_id": sample_set_id, "object_keys": current_keys},
    ) if target_compare_run_id and current_keys else []

    compare_map = {row["object_key"]: row for row in compare_rows}
    current_records = [row["record_payload"] or {} for row in current_rows]
    compare_records = [row["record_payload"] or {} for row in compare_preview_rows]
    current_keys = set(current_keys)
    items = []
    for current_row in current_rows:
        compare_row = compare_map.get(current_row["object_key"])
        payload = current_row["record_payload"] or {}
        compare_payload = (compare_row or {}).get("record_payload") or {}
        compare_state = "same"
        if compare_row is None:
            compare_state = "added"
        elif payload != compare_payload:
            compare_state = "changed"
        items.append(
            {
                "rank_order": current_row["rank_order"],
                "object_key": current_row["object_key"],
                "object_label": current_row["object_label"],
                "payload": payload,
                "compare_payload": compare_payload,
                "compare_state": compare_state,
                "rule_hits": current_row.get("rule_hits") or [],
                "changed_fields": changed_fields(payload, compare_payload),
            }
        )

    removed_rows = await fetch_all(
        db,
        """
        SELECT p.object_key, p.object_label, p.record_payload, p.rule_hits
        FROM workbench.wb_sample_snapshot p
        LEFT JOIN workbench.wb_sample_snapshot c
          ON c.run_id = :current_run_id
         AND c.sample_set_id = :sample_set_id
         AND c.object_key = p.object_key
        WHERE p.run_id = :compare_run_id
          AND p.sample_set_id = :sample_set_id
          AND c.object_key IS NULL
        ORDER BY p.rank_order
        LIMIT :limit
        """,
        {
            "current_run_id": selected_run_id,
            "compare_run_id": target_compare_run_id,
            "sample_set_id": sample_set_id,
            "limit": limit,
        },
    ) if target_compare_run_id else []
    removed_items = [
        {
            "object_key": row["object_key"],
            "object_label": row["object_label"],
            "payload": row["record_payload"] or {},
            "rule_hits": row.get("rule_hits") or [],
        }
        for row in removed_rows
    ]

    current_count = int(
        await scalar(
            db,
            "SELECT count(*) FROM workbench.wb_sample_snapshot WHERE run_id = :run_id AND sample_set_id = :sample_set_id",
            {"run_id": selected_run_id, "sample_set_id": sample_set_id},
        )
        or 0
    ) if selected_run_id else 0
    compare_count = int(
        await scalar(
            db,
            "SELECT count(*) FROM workbench.wb_sample_snapshot WHERE run_id = :run_id AND sample_set_id = :sample_set_id",
            {"run_id": target_compare_run_id, "sample_set_id": sample_set_id},
        )
        or 0
    ) if target_compare_run_id else 0
    summary_rows = (
        await first(
            db,
            """
            WITH current_rows AS (
                SELECT object_key, record_payload
                FROM workbench.wb_sample_snapshot
                WHERE run_id = :current_run_id AND sample_set_id = :sample_set_id
            ),
            compare_rows AS (
                SELECT object_key, record_payload
                FROM workbench.wb_sample_snapshot
                WHERE run_id = :compare_run_id AND sample_set_id = :sample_set_id
            ),
            joined AS (
                SELECT
                    COALESCE(c.object_key, p.object_key) AS object_key,
                    c.record_payload AS current_payload,
                    p.record_payload AS compare_payload
                FROM current_rows c
                FULL OUTER JOIN compare_rows p USING (object_key)
            )
            SELECT
                count(*) FILTER (WHERE current_payload IS NOT NULL AND compare_payload IS NULL) AS added_count,
                count(*) FILTER (WHERE current_payload IS NULL AND compare_payload IS NOT NULL) AS removed_count,
                count(*) FILTER (WHERE current_payload IS NOT NULL AND compare_payload IS NOT NULL AND current_payload IS DISTINCT FROM compare_payload) AS changed_count
            FROM joined
            """,
            {
                "current_run_id": selected_run_id,
                "compare_run_id": target_compare_run_id,
                "sample_set_id": sample_set_id,
            },
        )
        if target_compare_run_id
        else {"added_count": current_count, "removed_count": 0, "changed_count": 0}
    )

    return {
        "sample_set": {
            **row,
            "source_table": source_table,
            "source_table_cn": table_label(source_table),
            "step_ids": criteria.get("step_ids", []),
        },
        "run_id": selected_run_id,
        "compare_run_id": target_compare_run_id,
        "columns": columns,
        "records": current_records,
        "compare_records": compare_records,
        "items": items,
        "removed_items": removed_items,
        "summary": {
            "current_count": current_count,
            "compare_count": compare_count,
            "added_count": int(summary_rows["added_count"] or 0),
            "removed_count": int(summary_rows["removed_count"] or 0),
            "changed_count": int(summary_rows["changed_count"] or 0),
        },
        "snapshot_ready": bool(current_rows),
    }


async def get_step_samples(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """获取与指定步骤关联的样本集快照。"""
    data = await list_sample_sets(db, run_id=run_id)
    matching = [item for item in data["items"] if step_id in item.get("step_ids", [])]
    detailed = []
    for item in matching:
        detail = await get_sample_set_detail(
            db,
            item["id"],
            run_id=data["run_id"],
            compare_run_id=compare_run_id,
            limit=limit,
        )
        if detail:
            detailed.append(detail)
    return {"step_id": step_id, "run_id": data["run_id"], "sample_sets": detailed}


async def get_sample_object_detail(
    db: AsyncSession,
    sample_set_id: int,
    object_key: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any] | None:
    """获取单个样本对象的当前值 / 对比值 / 命中规则。"""
    await ensure_snapshot_tables(db)
    sample_set = await first(
        db,
        """
        SELECT id, name, description, sample_type, filter_criteria, is_active
        FROM workbench.wb_sample_set
        WHERE id = :sample_set_id
        """,
        {"sample_set_id": sample_set_id},
    )
    if not sample_set:
        return None

    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    target_compare_run_id = compare_run_id or (
        await previous_completed_run_id(db, selected_run_id) if selected_run_id else None
    )
    current_row = await first(
        db,
        """
        SELECT object_key, object_label, source_table, record_payload, rule_hits
        FROM workbench.wb_sample_snapshot
        WHERE run_id = :run_id AND sample_set_id = :sample_set_id AND object_key = :object_key
        """,
        {"run_id": selected_run_id, "sample_set_id": sample_set_id, "object_key": object_key},
    )
    compare_row = await first(
        db,
        """
        SELECT object_key, object_label, source_table, record_payload, rule_hits
        FROM workbench.wb_sample_snapshot
        WHERE run_id = :run_id AND sample_set_id = :sample_set_id AND object_key = :object_key
        """,
        {"run_id": target_compare_run_id, "sample_set_id": sample_set_id, "object_key": object_key},
    ) if target_compare_run_id else None
    if current_row is None and compare_row is None:
        return None

    source_table = (current_row or compare_row)["source_table"]
    current_payload = (current_row or {}).get("record_payload") or {}
    compare_payload = (compare_row or {}).get("record_payload") or {}
    compare_state = "same"
    if current_row is None:
        compare_state = "removed"
    elif compare_row is None:
        compare_state = "added"
    elif current_payload != compare_payload:
        compare_state = "changed"

    return {
        "sample_set": {
            **sample_set,
            "source_table": source_table,
            "source_table_cn": table_label(source_table),
            "step_ids": (sample_set["filter_criteria"] or {}).get("step_ids", []),
        },
        "run_id": selected_run_id,
        "compare_run_id": target_compare_run_id,
        "object_key": object_key,
        "object_label": (current_row or compare_row)["object_label"],
        "compare_state": compare_state,
        "rule_hits": (current_row or compare_row).get("rule_hits") or [],
        "current_payload": current_payload,
        "compare_payload": compare_payload,
        "changed_fields": changed_fields(current_payload, compare_payload),
        "display_pairs": display_pairs(source_table, current_payload, compare_payload),
    }
