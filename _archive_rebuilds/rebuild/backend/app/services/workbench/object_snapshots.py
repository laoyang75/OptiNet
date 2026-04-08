"""对象快照与对象级 diff。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workbench.base import fetch_all, first, scalar
from app.services.workbench.catalog import latest_completed_run_id, latest_run_id, previous_completed_run_id

_SNAPSHOT_DDL = [
    """
    CREATE TABLE IF NOT EXISTS workbench.wb_object_snapshot (
        id          bigserial PRIMARY KEY,
        run_id      integer NOT NULL REFERENCES workbench.wb_run(run_id),
        step_id     text NOT NULL REFERENCES workbench.wb_step_registry(step_id),
        object_level text NOT NULL,
        object_key  text NOT NULL,
        object_id   text NOT NULL,
        object_label text,
        payload     jsonb NOT NULL,
        rule_hits   jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at  timestamptz NOT NULL DEFAULT now(),
        UNIQUE(run_id, step_id, object_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_wb_object_snapshot_run_step
        ON workbench.wb_object_snapshot(run_id, step_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS workbench.wb_sample_snapshot (
        id           bigserial PRIMARY KEY,
        run_id       integer NOT NULL REFERENCES workbench.wb_run(run_id),
        sample_set_id integer NOT NULL REFERENCES workbench.wb_sample_set(id),
        source_table text NOT NULL,
        rank_order   integer NOT NULL,
        object_key   text NOT NULL,
        object_label text,
        record_payload jsonb NOT NULL,
        rule_hits    jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at   timestamptz NOT NULL DEFAULT now(),
        UNIQUE(run_id, sample_set_id, object_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_wb_sample_snapshot_run_set
        ON workbench.wb_sample_snapshot(run_id, sample_set_id, rank_order)
    """,
]

OBJECT_SNAPSHOT_CONFIG: dict[str, dict[str, str]] = {
    "s30": {
        "object_level": "BS",
        "table_name": "pipeline.dim_bs_trusted",
        "object_key": "concat_ws('|', tech_norm, bs_id::text, lac_dec_final::text)",
        "object_id": "bs_id::text",
        "object_label": "concat_ws(' / ', tech_norm, bs_id::text, lac_dec_final::text)",
        "payload": """
            jsonb_strip_nulls(jsonb_build_object(
                'tech_norm', tech_norm,
                'bs_id', bs_id,
                'lac_dec_final', lac_dec_final,
                'wuli_fentong_bs_key', wuli_fentong_bs_key,
                'shared_operator_cnt', shared_operator_cnt,
                'shared_operator_list', shared_operator_list,
                'gps_valid_level', gps_valid_level,
                'bs_center_lon', bs_center_lon,
                'bs_center_lat', bs_center_lat,
                'gps_p50_dist_m', gps_p50_dist_m,
                'gps_p90_dist_m', gps_p90_dist_m,
                'gps_max_dist_m', gps_max_dist_m,
                'outlier_removed_cnt', outlier_removed_cnt,
                'is_collision_suspect', is_collision_suspect,
                'collision_reason', collision_reason,
                'anomaly_cell_cnt', anomaly_cell_cnt,
                'active_days', active_days
            ))
        """,
        "rule_hits": """
            to_jsonb(array_remove(ARRAY[
                CASE WHEN gps_valid_level = 'Risk' THEN 'risk_bs' END,
                CASE WHEN gps_valid_level = 'Unusable' THEN 'unusable_bs' END,
                CASE WHEN is_collision_suspect THEN 'collision_suspect' END,
                CASE WHEN is_multi_operator_shared THEN 'multi_operator_shared' END
            ], NULL))
        """,
    },
    "s50": {
        "object_level": "LAC",
        "table_name": "pipeline.profile_lac",
        "object_key": "concat_ws('|', operator_id_cn, tech_norm, lac_dec::text)",
        "object_id": "lac_dec::text",
        "object_label": "concat_ws(' / ', operator_id_cn, tech_norm, lac_dec::text)",
        "payload": """
            jsonb_strip_nulls(jsonb_build_object(
                'operator_id_cn', operator_id_cn,
                'tech_norm', tech_norm,
                'lac_dec', lac_dec,
                'record_count', record_count,
                'active_days', active_days,
                'distinct_bs_count', distinct_bs_count,
                'distinct_cell_count', distinct_cell_count,
                'gps_valid_ratio', gps_valid_ratio,
                'gps_dist_p90_m', gps_dist_p90_m,
                'multi_operator_bs_count', multi_operator_bs_count,
                'has_multi_operator_bs', has_multi_operator_bs,
                'is_insufficient_sample', is_insufficient_sample,
                'is_gps_unstable', is_gps_unstable
            ))
        """,
        "rule_hits": """
            to_jsonb(array_remove(ARRAY[
                CASE WHEN is_insufficient_sample THEN 'insufficient_sample' END,
                CASE WHEN is_gps_unstable THEN 'gps_unstable' END,
                CASE WHEN has_multi_operator_bs THEN 'multi_operator_bs' END
            ], NULL))
        """,
    },
    "s51": {
        "object_level": "BS",
        "table_name": "pipeline.profile_bs",
        "object_key": "concat_ws('|', operator_id_cn, tech_norm, lac_dec::text, bs_id::text)",
        "object_id": "bs_id::text",
        "object_label": "concat_ws(' / ', operator_id_cn, tech_norm, bs_id::text, lac_dec::text)",
        "payload": """
            jsonb_strip_nulls(jsonb_build_object(
                'operator_id_cn', operator_id_cn,
                'tech_norm', tech_norm,
                'lac_dec', lac_dec,
                'bs_id', bs_id,
                'record_count', record_count,
                'active_days', active_days,
                'distinct_cell_count', distinct_cell_count,
                'gps_valid_ratio', gps_valid_ratio,
                'gps_dist_p90_m', gps_dist_p90_m,
                'gps_drift_count', gps_drift_count,
                'dynamic_cell_count', dynamic_cell_count,
                'is_collision_suspect', is_collision_suspect,
                'is_severe_collision', is_severe_collision,
                'is_insufficient_sample', is_insufficient_sample,
                'is_gps_unstable', is_gps_unstable,
                'is_bs_id_lt_256', is_bs_id_lt_256,
                'is_multi_operator_shared', is_multi_operator_shared
            ))
        """,
        "rule_hits": """
            to_jsonb(array_remove(ARRAY[
                CASE WHEN is_collision_suspect THEN 'collision_suspect' END,
                CASE WHEN is_severe_collision THEN 'severe_collision' END,
                CASE WHEN is_gps_unstable THEN 'gps_unstable' END,
                CASE WHEN is_insufficient_sample THEN 'insufficient_sample' END,
                CASE WHEN is_bs_id_lt_256 THEN 'bs_id_lt_256' END,
                CASE WHEN is_multi_operator_shared THEN 'multi_operator_shared' END
            ], NULL))
        """,
    },
    "s52": {
        "object_level": "CELL",
        "table_name": "pipeline.profile_cell",
        "object_key": "concat_ws('|', operator_id_cn, tech_norm, lac_dec::text, cell_id_dec::text)",
        "object_id": "cell_id_dec::text",
        "object_label": "concat_ws(' / ', operator_id_cn, tech_norm, cell_id_dec::text, lac_dec::text)",
        "payload": """
            jsonb_strip_nulls(jsonb_build_object(
                'operator_id_cn', operator_id_cn,
                'tech_norm', tech_norm,
                'lac_dec', lac_dec,
                'bs_id', bs_id,
                'cell_id_dec', cell_id_dec,
                'record_count', record_count,
                'active_days', active_days,
                'gps_valid_ratio', gps_valid_ratio,
                'gps_dist_p90_m', gps_dist_p90_m,
                'half_major_dist_km', half_major_dist_km,
                'is_dynamic_cell', is_dynamic_cell,
                'is_collision_suspect', is_collision_suspect,
                'is_insufficient_sample', is_insufficient_sample,
                'is_gps_unstable', is_gps_unstable
            ))
        """,
        "rule_hits": """
            to_jsonb(array_remove(ARRAY[
                CASE WHEN is_dynamic_cell THEN 'dynamic_cell' END,
                CASE WHEN is_collision_suspect THEN 'collision_suspect' END,
                CASE WHEN is_insufficient_sample THEN 'insufficient_sample' END,
                CASE WHEN is_gps_unstable THEN 'gps_unstable' END
            ], NULL))
        """,
    },
}


async def ensure_snapshot_tables(db: AsyncSession) -> None:
    for statement in _SNAPSHOT_DDL:
        await db.execute(text(statement))


async def object_snapshot_count(db: AsyncSession, run_id: int | None) -> int:
    if run_id is None:
        return 0
    await ensure_snapshot_tables(db)
    return int(
        await scalar(
            db,
            "SELECT count(*) FROM workbench.wb_object_snapshot WHERE run_id = :run_id",
            {"run_id": run_id},
        )
        or 0
    )


async def sample_snapshot_count(db: AsyncSession, run_id: int | None) -> int:
    if run_id is None:
        return 0
    await ensure_snapshot_tables(db)
    return int(
        await scalar(
            db,
            "SELECT count(*) FROM workbench.wb_sample_snapshot WHERE run_id = :run_id",
            {"run_id": run_id},
        )
        or 0
    )


async def refresh_object_snapshots(db: AsyncSession, run_id: int, *, force: bool = False) -> dict[str, Any]:
    await ensure_snapshot_tables(db)
    if force:
        await db.execute(text("DELETE FROM workbench.wb_object_snapshot WHERE run_id = :run_id"), {"run_id": run_id})

    for step_id, config in OBJECT_SNAPSHOT_CONFIG.items():
        await db.execute(
            text(
                f"""
                INSERT INTO workbench.wb_object_snapshot (
                    run_id, step_id, object_level, object_key, object_id, object_label, payload, rule_hits
                )
                SELECT
                    :run_id,
                    :step_id,
                    :object_level,
                    {config['object_key']},
                    {config['object_id']},
                    {config['object_label']},
                    {config['payload']},
                    COALESCE({config['rule_hits']}, '[]'::jsonb)
                FROM {config['table_name']}
                ON CONFLICT (run_id, step_id, object_key)
                DO UPDATE SET
                    object_id = EXCLUDED.object_id,
                    object_label = EXCLUDED.object_label,
                    payload = EXCLUDED.payload,
                    rule_hits = EXCLUDED.rule_hits,
                    created_at = now()
                """
            ),
            {"run_id": run_id, "step_id": step_id, "object_level": config["object_level"]},
        )

    return {
        "run_id": run_id,
        "object_snapshot_count": await object_snapshot_count(db, run_id),
    }


def _changed_fields(current_payload: dict[str, Any], compare_payload: dict[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(current_payload) | set(compare_payload))
    changed = []
    for key in keys:
        current_value = current_payload.get(key)
        compare_value = compare_payload.get(key)
        if current_value != compare_value:
            changed.append({"field": key, "current": current_value, "compare": compare_value})
    return changed


async def load_step_object_diff(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    await ensure_snapshot_tables(db)
    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    target_compare = compare_run_id or (await previous_completed_run_id(db, current_run_id) if current_run_id else None)
    empty = {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare,
        "step_id": step_id,
        "snapshot_ready": False,
        "summary": {"added_count": 0, "removed_count": 0, "changed_count": 0},
        "added": [],
        "removed": [],
        "changed": [],
    }
    if not current_run_id or not target_compare:
        return empty

    params = {"current_run_id": current_run_id, "compare_run_id": target_compare, "step_id": step_id, "limit": limit}
    added_count = int(
        await scalar(
            db,
            """
            SELECT count(*)
            FROM workbench.wb_object_snapshot c
            LEFT JOIN workbench.wb_object_snapshot p
              ON p.run_id = :compare_run_id
             AND p.step_id = :step_id
             AND p.object_key = c.object_key
            WHERE c.run_id = :current_run_id
              AND c.step_id = :step_id
              AND p.object_key IS NULL
            """,
            params,
        )
        or 0
    )
    removed_count = int(
        await scalar(
            db,
            """
            SELECT count(*)
            FROM workbench.wb_object_snapshot p
            LEFT JOIN workbench.wb_object_snapshot c
              ON c.run_id = :current_run_id
             AND c.step_id = :step_id
             AND c.object_key = p.object_key
            WHERE p.run_id = :compare_run_id
              AND p.step_id = :step_id
              AND c.object_key IS NULL
            """,
            params,
        )
        or 0
    )
    changed_count = int(
        await scalar(
            db,
            """
            SELECT count(*)
            FROM workbench.wb_object_snapshot c
            JOIN workbench.wb_object_snapshot p
              ON p.run_id = :compare_run_id
             AND p.step_id = :step_id
             AND p.object_key = c.object_key
            WHERE c.run_id = :current_run_id
              AND c.step_id = :step_id
              AND c.payload IS DISTINCT FROM p.payload
            """,
            params,
        )
        or 0
    )

    def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            current_payload = row.get("current_payload") or {}
            compare_payload = row.get("compare_payload") or {}
            result.append(
                {
                    "object_key": row["object_key"],
                    "object_id": row.get("object_id"),
                    "object_label": row.get("object_label") or row["object_key"],
                    "rule_hits": row.get("rule_hits") or [],
                    "current_payload": current_payload,
                    "compare_payload": compare_payload,
                    "changed_fields": _changed_fields(current_payload, compare_payload),
                }
            )
        return result

    added = await fetch_all(
        db,
        """
        SELECT
            c.object_key,
            c.object_id,
            c.object_label,
            c.rule_hits,
            c.payload AS current_payload,
            NULL::jsonb AS compare_payload
        FROM workbench.wb_object_snapshot c
        LEFT JOIN workbench.wb_object_snapshot p
          ON p.run_id = :compare_run_id
         AND p.step_id = :step_id
         AND p.object_key = c.object_key
        WHERE c.run_id = :current_run_id
          AND c.step_id = :step_id
          AND p.object_key IS NULL
        ORDER BY c.object_key
        LIMIT :limit
        """,
        params,
    )
    removed = await fetch_all(
        db,
        """
        SELECT
            p.object_key,
            p.object_id,
            p.object_label,
            p.rule_hits,
            NULL::jsonb AS current_payload,
            p.payload AS compare_payload
        FROM workbench.wb_object_snapshot p
        LEFT JOIN workbench.wb_object_snapshot c
          ON c.run_id = :current_run_id
         AND c.step_id = :step_id
         AND c.object_key = p.object_key
        WHERE p.run_id = :compare_run_id
          AND p.step_id = :step_id
          AND c.object_key IS NULL
        ORDER BY p.object_key
        LIMIT :limit
        """,
        params,
    )
    changed = await fetch_all(
        db,
        """
        SELECT
            c.object_key,
            c.object_id,
            c.object_label,
            c.rule_hits,
            c.payload AS current_payload,
            p.payload AS compare_payload
        FROM workbench.wb_object_snapshot c
        JOIN workbench.wb_object_snapshot p
          ON p.run_id = :compare_run_id
         AND p.step_id = :step_id
         AND p.object_key = c.object_key
        WHERE c.run_id = :current_run_id
          AND c.step_id = :step_id
          AND c.payload IS DISTINCT FROM p.payload
        ORDER BY c.object_key
        LIMIT :limit
        """,
        params,
    )

    return {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare,
        "step_id": step_id,
        "snapshot_ready": True,
        "summary": {
            "added_count": added_count,
            "removed_count": removed_count,
            "changed_count": changed_count,
        },
        "added": _normalize(added),
        "removed": _normalize(removed),
        "changed": _normalize(changed),
    }
