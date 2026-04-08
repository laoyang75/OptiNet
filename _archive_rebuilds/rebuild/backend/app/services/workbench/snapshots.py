"""快照编排、快照读取与全量刷新。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.labels import anomaly_label, layer_label, object_level_label
from app.services.workbench.base import fetch_all, first, now_iso, snapshot_lock, to_number
from app.services.workbench.catalog import ensure_reference_data, latest_completed_run_id, latest_run_id
from app.services.workbench.object_snapshots import (
    object_snapshot_count,
    refresh_object_snapshots,
    sample_snapshot_count,
)
from app.services.workbench.samples import refresh_sample_snapshots
from app.services.workbench.snapshot_builders import (
    compute_anomaly_stats,
    compute_gate_results,
    compute_layer_snapshot,
    compute_rule_hits,
    compute_step_metrics,
)

SNAPSHOT_COUNT_KEYS = (
    "layer_count",
    "metric_count",
    "anomaly_count",
    "rule_count",
    "gate_count",
    "object_count",
    "sample_count",
)


async def snapshot_bundle_counts(db: AsyncSession, run_id: int | None) -> dict[str, Any]:
    if run_id is None:
        return {}
    base = (
        await first(
            db,
            """
            SELECT
                (SELECT count(*) FROM workbench.wb_layer_snapshot WHERE run_id = :run_id) AS layer_count,
                (SELECT count(*) FROM workbench.wb_step_metric WHERE run_id = :run_id) AS metric_count,
                (SELECT count(*) FROM workbench.wb_anomaly_stats WHERE run_id = :run_id) AS anomaly_count,
                (SELECT count(*) FROM workbench.wb_rule_hit WHERE run_id = :run_id) AS rule_count,
                (SELECT count(*) FROM workbench.wb_gate_result WHERE run_id = :run_id) AS gate_count
            """,
            {"run_id": run_id},
        )
        or {}
    )
    base["object_count"] = await object_snapshot_count(db, run_id)
    base["sample_count"] = await sample_snapshot_count(db, run_id)
    return base


async def ensure_snapshot_bundle(db: AsyncSession, run_id: int | None, *, force: bool = False) -> dict[str, Any]:
    if run_id is None:
        return {"run_id": None, "refreshed": False, "reason": "缺少 run_id"}

    lock = snapshot_lock(run_id)
    async with lock:
        existing = await snapshot_bundle_counts(db, run_id)
        if existing and not force and all(int(existing.get(key) or 0) > 0 for key in SNAPSHOT_COUNT_KEYS):
            return {"run_id": run_id, "refreshed": False, **existing}

        await ensure_reference_data(db)
        await db.execute(text("SET LOCAL statement_timeout = 300000"))

        layer_rows = await compute_layer_snapshot(db, run_id)
        metric_rows = await compute_step_metrics(db, run_id)
        anomaly_rows = await compute_anomaly_stats(db, run_id)
        rule_rows = await compute_rule_hits(db, run_id)
        gate_rows = await compute_gate_results(db, run_id)

        for table_name in [
            "workbench.wb_layer_snapshot",
            "workbench.wb_step_metric",
            "workbench.wb_anomaly_stats",
            "workbench.wb_rule_hit",
            "workbench.wb_gate_result",
        ]:
            await db.execute(text(f"DELETE FROM {table_name} WHERE run_id = :run_id"), {"run_id": run_id})

        if layer_rows:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_layer_snapshot (run_id, layer_id, row_count, pass_flag, pass_note)
                    VALUES (:run_id, :layer_id, :row_count, :pass_flag, :pass_note)
                    """
                ),
                layer_rows,
            )
        if metric_rows:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_step_metric (
                        run_id, step_id, metric_code, metric_name, dimension_key,
                        value_num, value_text, value_json, unit
                    ) VALUES (
                        :run_id, :step_id, :metric_code, :metric_name, :dimension_key,
                        :value_num, :value_text, CAST(:value_json AS jsonb), :unit
                    )
                    """
                ),
                metric_rows,
            )
        if anomaly_rows:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_anomaly_stats (
                        run_id, object_level, anomaly_type, total_count,
                        anomaly_count, anomaly_ratio, dimension_key
                    ) VALUES (
                        :run_id, :object_level, :anomaly_type, :total_count,
                        :anomaly_count, :anomaly_ratio, :dimension_key
                    )
                    """
                ),
                anomaly_rows,
            )
        if rule_rows:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_rule_hit (
                        run_id, step_id, rule_code, rule_name, rule_purpose,
                        hit_count, total_count, hit_ratio, key_params, dimension_key
                    ) VALUES (
                        :run_id, :step_id, :rule_code, :rule_name, :rule_purpose,
                        :hit_count, :total_count, :hit_ratio, CAST(:key_params AS jsonb), :dimension_key
                    )
                    """
                ),
                rule_rows,
            )
        if gate_rows:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_gate_result (
                        run_id, gate_code, gate_name, severity, expected_rule,
                        actual_value, pass_flag, remark
                    ) VALUES (
                        :run_id, :gate_code, :gate_name, :severity, :expected_rule,
                        :actual_value, :pass_flag, :remark
                    )
                    """
                ),
                gate_rows,
            )

        object_result = await refresh_object_snapshots(db, run_id, force=True)
        sample_result = await refresh_sample_snapshots(db, run_id, force=True)
        await db.commit()
        return {
            "run_id": run_id,
            "refreshed": True,
            "layer_count": len(layer_rows),
            "metric_count": len(metric_rows),
            "anomaly_count": len(anomaly_rows),
            "rule_count": len(rule_rows),
            "gate_count": len(gate_rows),
            "object_count": int(object_result.get("object_snapshot_count") or 0),
            "sample_count": int(sample_result.get("sample_snapshot_count") or 0),
        }


async def list_layer_snapshot(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    rows = await fetch_all(
        db,
        """
        SELECT layer_id, row_count, pass_flag, pass_note, created_at
        FROM workbench.wb_layer_snapshot
        WHERE run_id = :run_id
        ORDER BY id
        """,
        {"run_id": selected_run_id},
    )
    return [
        {
            "run_id": selected_run_id,
            "layer_id": row["layer_id"],
            "layer_label": layer_label(row["layer_id"]),
            "row_count": int(row["row_count"] or 0),
            "pass_flag": row["pass_flag"],
            "pass_note": row["pass_note"],
            "generated_at": row["created_at"],
        }
        for row in rows
    ]


def _group_metrics(rows: list[dict[str, Any]], step_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    step_meta = {row["step_id"]: row for row in step_rows}
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = grouped.setdefault(
            row["step_id"],
            {
                "step_id": row["step_id"],
                "step_name": step_meta.get(row["step_id"], {}).get("step_name", row["step_id"]),
                "step_name_en": step_meta.get(row["step_id"], {}).get("step_name_en", row["step_id"]),
                "layer": step_meta.get(row["step_id"], {}).get("layer"),
                "metrics": {},
                "metric_labels": {},
                "json_metrics": {},
            },
        )
        if row["value_json"] is not None:
            item["json_metrics"][row["metric_code"]] = row["value_json"]
        else:
            item["metrics"][row["metric_code"]] = (
                to_number(row["value_num"]) if row["value_num"] is not None else row["value_text"]
            )
            item["metric_labels"][row["metric_code"]] = {"label": row["metric_name"], "unit": row["unit"]}

    result = []
    for item in grouped.values():
        flat = dict(item["metrics"])
        flat.update(
            {
                "step_id": item["step_id"],
                "step_name": item["step_name"],
                "step_name_en": item["step_name_en"],
                "layer": item["layer"],
                "metric_labels": item["metric_labels"],
                "json_metrics": item["json_metrics"],
            }
        )
        result.append(flat)
    return sorted(result, key=lambda row: step_meta.get(row["step_id"], {}).get("step_order", 9999))


async def list_step_summary(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    step_rows = await fetch_all(
        db,
        "SELECT step_id, step_order, step_name, step_name_en, layer FROM workbench.wb_step_registry ORDER BY step_order",
    )
    metric_rows = await fetch_all(
        db,
        """
        SELECT step_id, metric_code, metric_name, value_num, value_text, value_json, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND dimension_key = 'ALL'
        ORDER BY id
        """,
        {"run_id": selected_run_id},
    )
    return _group_metrics(metric_rows, step_rows)


async def list_anomaly_summary(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    rows = await fetch_all(
        db,
        """
        SELECT object_level, anomaly_type, total_count, anomaly_count, anomaly_ratio, created_at
        FROM workbench.wb_anomaly_stats
        WHERE run_id = :run_id
        ORDER BY object_level, anomaly_type
        """,
        {"run_id": selected_run_id},
    )
    return [
        {
            "run_id": selected_run_id,
            "object_level": row["object_level"],
            "object_level_label": object_level_label(row["object_level"]),
            "anomaly_type": row["anomaly_type"],
            "anomaly_type_cn": anomaly_label(row["anomaly_type"]),
            "total": int(row["total_count"]),
            "anomaly_count": int(row["anomaly_count"]),
            "anomaly_ratio": float(row["anomaly_ratio"] or 0),
            "generated_at": row["created_at"],
        }
        for row in rows
    ]


async def list_operator_tech_distribution(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    row = await first(
        db,
        """
        SELECT value_json
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = 's41' AND metric_code = 'operator_tech_distribution'
        ORDER BY id DESC
        LIMIT 1
        """,
        {"run_id": selected_run_id},
    )
    return row["value_json"] if row and row["value_json"] else []


async def list_gps_status_distribution(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    row = await first(
        db,
        """
        SELECT value_json
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = 's31' AND metric_code = 'gps_status_distribution'
        ORDER BY id DESC
        LIMIT 1
        """,
        {"run_id": selected_run_id},
    )
    return row["value_json"] if row and row["value_json"] else []


async def list_signal_fill_distribution(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    row = await first(
        db,
        """
        SELECT value_json
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = 's33' AND metric_code = 'signal_fill_distribution'
        ORDER BY id DESC
        LIMIT 1
        """,
        {"run_id": selected_run_id},
    )
    return row["value_json"] if row and row["value_json"] else []


async def refresh_all(db: AsyncSession, *, run_id: int | None = None, include_fields: bool = True) -> dict[str, Any]:
    """全量刷新工作台快照，并在需要时刷新字段治理快照。"""
    from app.services.workbench.catalog import ensure_field_registry
    from app.services.workbench.source_fields import refresh_source_field_snapshots

    await ensure_reference_data(db)
    field_count = await ensure_field_registry(db) if include_fields else 0
    selected_run_id = run_id or await latest_completed_run_id(db)
    if selected_run_id is None:
        return {
            "generated_at": now_iso(),
            "run_id": None,
            "snapshot": {"run_id": None, "refreshed": False, "reason": "暂无已完成 run"},
            "source_field_snapshot": None,
            "field_registry_rows": field_count,
        }

    snapshot_result = await ensure_snapshot_bundle(db, selected_run_id, force=True)
    field_snapshot_result = (
        await refresh_source_field_snapshots(db, run_id=selected_run_id, force=True) if include_fields else None
    )
    return {
        "generated_at": now_iso(),
        "run_id": selected_run_id,
        "snapshot": snapshot_result,
        "source_field_snapshot": field_snapshot_result,
        "field_registry_rows": field_count,
    }
