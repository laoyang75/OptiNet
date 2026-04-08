"""Workbench service layer for snapshots, versions, fields, SQL assets, and samples."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.labels import (
    ANOMALY_LABELS,
    FIELD_LABELS,
    OBJECT_LEVEL_LABELS,
    PRIMARY_STEP_METRICS,
    STATUS_LABELS,
    STEP_PURPOSES,
    TABLE_LABELS,
    anomaly_label,
    field_label,
    layer_label,
    object_level_label,
    run_mode_label,
    status_label,
    table_label,
)

REBUILD_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REBUILD_ROOT.parent
SQL_ASSET_ROOT = WORKSPACE_ROOT / "lac_enbid_project"

DEFAULT_RULE_SET_VERSION = "R-001"
DEFAULT_SQL_BUNDLE_VERSION = "S-001"
DEFAULT_CONTRACT_VERSION = "C-001"

DEFAULT_RULE_SET: dict[str, list[dict[str, Any]]] = {
    "s4": [
        {"rule_code": "active_days_threshold", "rule_name": "活跃天数阈值", "rule_purpose": "剔除活跃天数不足的 LAC。", "param_keys": ["active_days_threshold"]},
        {"rule_code": "min_device_count", "rule_name": "设备数阈值", "rule_purpose": "剔除设备数过少的 LAC。", "param_keys": ["min_device_count", "min_device_count_5g"]},
        {"rule_code": "report_count_percentile", "rule_name": "上报分位阈值", "rule_purpose": "保留高置信度 LAC。", "param_keys": ["report_count_percentile"]},
    ],
    "s30": [
        {"rule_code": "gps_valid_level", "rule_name": "GPS有效级别", "rule_purpose": "按 GPS 稳定性给 BS 分级。", "param_keys": ["collision_p90_dist_m"]},
        {"rule_code": "collision_detection", "rule_name": "碰撞检测", "rule_purpose": "识别疑似碰撞 BS。", "param_keys": ["collision_p90_dist_m"]},
        {"rule_code": "outlier_removal", "rule_name": "离群点移除", "rule_purpose": "移除超远距离噪点。", "param_keys": ["outlier_dist_m"]},
    ],
    "s31": [
        {"rule_code": "gps_drift", "rule_name": "GPS漂移识别", "rule_purpose": "识别与 BS 中心点距离过大的记录。", "param_keys": ["drift_dist_m"]},
        {"rule_code": "gps_fill", "rule_name": "BS回填", "rule_purpose": "对缺失或漂移 GPS 做回填。", "param_keys": ["drift_dist_m"]},
    ],
    "s33": [
        {"rule_code": "fill_by_cell", "rule_name": "按 Cell 聚合补齐", "rule_purpose": "优先用 Cell 聚合值补齐信号字段。", "param_keys": []},
        {"rule_code": "fill_by_bs", "rule_name": "按 BS 聚合补齐", "rule_purpose": "Cell 不足时退化到 BS 聚合值。", "param_keys": []},
        {"rule_code": "fill_none", "rule_name": "无法补齐", "rule_purpose": "识别补齐失败样本。", "param_keys": []},
    ],
    "s35": [
        {"rule_code": "dynamic_cell", "rule_name": "动态Cell识别", "rule_purpose": "识别覆盖范围过大的移动 Cell。", "param_keys": ["min_half_major_dist_km", "min_day_major_share"]},
    ],
    "s50": [
        {"rule_code": "min_rows", "rule_name": "LAC最小样本数", "rule_purpose": "识别样本不足的 LAC。", "param_keys": ["min_rows"]},
    ],
    "s51": [
        {"rule_code": "min_rows", "rule_name": "BS最小样本数", "rule_purpose": "识别样本不足的 BS。", "param_keys": ["min_rows"]},
        {"rule_code": "gps_p90_warn", "rule_name": "BS画像距离告警", "rule_purpose": "识别 GPS 扩散过大的 BS。", "param_keys": ["gps_p90_warn_4g_m", "gps_p90_warn_5g_m"]},
    ],
    "s52": [
        {"rule_code": "min_rows", "rule_name": "Cell最小样本数", "rule_purpose": "识别样本不足的 Cell。", "param_keys": ["min_rows"]},
        {"rule_code": "gps_p90_warn", "rule_name": "Cell画像距离告警", "rule_purpose": "识别 GPS 扩散过大的 Cell。", "param_keys": ["gps_p90_warn_4g_m", "gps_p90_warn_5g_m"]},
    ],
}

DEFAULT_SAMPLE_SETS: list[dict[str, Any]] = [
    {
        "name": "碰撞BS样本",
        "description": "聚焦疑似碰撞和严重碰撞的 BS。",
        "sample_type": "bs",
        "filter_criteria": {
            "source_table": "profile_bs",
            "filters": {"is_collision_suspect": True},
            "step_ids": ["s30", "s36", "s37", "s51"],
            "order_by": "gps_dist_p90_m DESC NULLS LAST",
        },
    },
    {
        "name": "动态Cell样本",
        "description": "聚焦动态 Cell 与大范围移动样本。",
        "sample_type": "cell",
        "filter_criteria": {
            "source_table": "profile_cell",
            "filters": {"is_dynamic_cell": True},
            "step_ids": ["s35", "s52"],
            "order_by": "half_major_dist_km DESC NULLS LAST",
        },
    },
    {
        "name": "GPS漂移记录样本",
        "description": "聚焦被判定为 GPS 漂移的记录。",
        "sample_type": "record",
        "filter_criteria": {
            "source_table": "fact_gps_corrected",
            "filters": {"gps_status": "Drift"},
            "step_ids": ["s31", "s40"],
            "order_by": "gps_dist_to_bs_m DESC NULLS LAST",
        },
    },
    {
        "name": "信号未补齐样本",
        "description": "聚焦信号补齐失败样本。",
        "sample_type": "record",
        "filter_criteria": {
            "source_table": "fact_signal_filled",
            "filters": {"signal_fill_source": "none"},
            "step_ids": ["s33", "s41"],
            "order_by": "signal_missing_before_cnt DESC NULLS LAST",
        },
    },
]

SAMPLE_TABLE_CONFIG: dict[str, dict[str, Any]] = {
    "profile_bs": {
        "columns": ["operator_id_cn", "tech_norm", "lac_dec", "bs_id", "record_count", "gps_dist_p90_m", "is_collision_suspect", "is_severe_collision", "is_gps_unstable", "is_insufficient_sample"],
        "allowed_filters": {"is_collision_suspect", "is_severe_collision", "is_gps_unstable", "is_insufficient_sample"},
        "object_id_columns": ["bs_id"],
    },
    "profile_cell": {
        "columns": ["operator_id_cn", "tech_norm", "lac_dec", "bs_id", "cell_id_dec", "record_count", "gps_dist_p90_m", "half_major_dist_km", "is_dynamic_cell", "is_collision_suspect", "is_insufficient_sample"],
        "allowed_filters": {"is_dynamic_cell", "is_collision_suspect", "is_insufficient_sample"},
        "object_id_columns": ["cell_id_dec"],
    },
    "fact_gps_corrected": {
        "columns": ["src_record_id", "operator_id_raw", "tech_norm", "bs_id", "cell_id_dec", "gps_status", "gps_status_final", "gps_source", "gps_dist_to_bs_m", "report_date"],
        "allowed_filters": {"gps_status", "gps_status_final", "gps_source"},
        "object_id_columns": ["src_record_id"],
    },
    "fact_signal_filled": {
        "columns": ["src_record_id", "operator_id_raw", "tech_norm", "bs_id", "cell_id_dec", "signal_fill_source", "signal_missing_before_cnt", "signal_missing_after_cnt", "report_date"],
        "allowed_filters": {"signal_fill_source"},
        "object_id_columns": ["src_record_id"],
    },
}

_BOOTSTRAP_LOCK = asyncio.Lock()
_SNAPSHOT_LOCKS: dict[int, asyncio.Lock] = {}


def _snapshot_lock(run_id: int) -> asyncio.Lock:
    lock = _SNAPSHOT_LOCKS.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _SNAPSHOT_LOCKS[run_id] = lock
    return lock


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    return value


def _mappings_to_dicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _metric_row(
    run_id: int,
    step_id: str,
    metric_code: str,
    metric_name: str,
    *,
    value_num: int | float | None = None,
    value_text: str | None = None,
    value_json: Any | None = None,
    unit: str | None = None,
    dimension_key: str = "ALL",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "step_id": step_id,
        "metric_code": metric_code,
        "metric_name": metric_name,
        "dimension_key": dimension_key,
        "value_num": value_num,
        "value_text": value_text,
        "value_json": _json(value_json) if value_json is not None else None,
        "unit": unit,
    }


async def _scalar(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> Any:
    result = await db.execute(text(sql), params or {})
    return result.scalar()


async def _first(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = await db.execute(text(sql), params or {})
    row = result.mappings().first()
    return dict(row) if row else None


async def _all(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params or {})
    return _mappings_to_dicts(result.mappings().all())


def _resolve_sql_candidates(sql_file: str | None) -> list[dict[str, str]]:
    if not sql_file or not SQL_ASSET_ROOT.exists():
        return []
    paths = sorted(SQL_ASSET_ROOT.rglob(sql_file))
    return [
        {
            "path": str(path),
            "rel_path": str(path.relative_to(WORKSPACE_ROOT)),
        }
        for path in paths
    ]


def _step_rule_catalog(step_id: str) -> list[dict[str, Any]]:
    return DEFAULT_RULE_SET.get(step_id, [])


async def ensure_reference_data(db: AsyncSession) -> dict[str, Any]:
    async with _BOOTSTRAP_LOCK:
        current = await _first(
            db,
            "SELECT id, version_tag FROM workbench.wb_parameter_set WHERE is_active = true ORDER BY id DESC LIMIT 1",
        )

        if await _scalar(db, "SELECT count(*) FROM workbench.wb_rule_set WHERE version_tag = :tag", {"tag": DEFAULT_RULE_SET_VERSION}) == 0:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_rule_set (version_tag, description, rules)
                    VALUES (:version_tag, :description, CAST(:rules AS jsonb))
                    """
                ),
                {
                    "version_tag": DEFAULT_RULE_SET_VERSION,
                    "description": "工作台默认规则集（由步骤级规则目录初始化）",
                    "rules": _json(DEFAULT_RULE_SET),
                },
            )

        if await _scalar(db, "SELECT count(*) FROM workbench.wb_sql_bundle WHERE version_tag = :tag", {"tag": DEFAULT_SQL_BUNDLE_VERSION}) == 0:
            step_rows = await _all(db, "SELECT step_id, sql_file FROM workbench.wb_step_registry ORDER BY step_order")
            manifest = [
                {
                    "step_id": row["step_id"],
                    "sql_file": row["sql_file"],
                    "candidates": _resolve_sql_candidates(row["sql_file"]),
                }
                for row in step_rows
            ]
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_sql_bundle (version_tag, description, file_manifest)
                    VALUES (:version_tag, :description, CAST(:file_manifest AS jsonb))
                    """
                ),
                {
                    "version_tag": DEFAULT_SQL_BUNDLE_VERSION,
                    "description": "工作台默认 SQL 资源版本（自动扫描 lac_enbid_project）",
                    "file_manifest": _json(manifest),
                },
            )

        if await _scalar(db, "SELECT count(*) FROM workbench.wb_contract WHERE version_tag = :tag", {"tag": DEFAULT_CONTRACT_VERSION}) == 0:
            contract_fields = {
                "schemas": ["pipeline", "workbench", "meta"],
                "table_count": len(TABLE_LABELS),
                "field_labels": FIELD_LABELS,
            }
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_contract (version_tag, description, contract_fields)
                    VALUES (:version_tag, :description, CAST(:contract_fields AS jsonb))
                    """
                ),
                {
                    "version_tag": DEFAULT_CONTRACT_VERSION,
                    "description": "工作台默认字段契约版本（基于 Doc02/Doc05 初始化）",
                    "contract_fields": _json(contract_fields),
                },
            )

        step_updates = [
            {"step_id": step_id, "description": description}
            for step_id, description in STEP_PURPOSES.items()
        ]
        await db.execute(
            text(
                """
                UPDATE workbench.wb_step_registry
                SET description = :description
                WHERE step_id = :step_id AND (description IS NULL OR description = '')
                """
            ),
            step_updates,
        )

        if await _scalar(db, "SELECT count(*) FROM workbench.wb_sample_set") == 0:
            await db.execute(
                text(
                    """
                    INSERT INTO workbench.wb_sample_set (name, description, sample_type, filter_criteria, object_ids, created_by)
                    VALUES (:name, :description, :sample_type, CAST(:filter_criteria AS jsonb), CAST(:object_ids AS jsonb), :created_by)
                    """
                ),
                [
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "sample_type": item["sample_type"],
                        "filter_criteria": _json(item["filter_criteria"]),
                        "object_ids": _json([]),
                        "created_by": "system",
                    }
                    for item in DEFAULT_SAMPLE_SETS
                ],
            )

        ref_ids = await _first(
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
                text(
                    """
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
                    """
                ),
                ref_ids,
            )

        await db.commit()
        return {
            "parameter_set_id": current["id"] if current else None,
            "parameter_set_version": current["version_tag"] if current else None,
        }


async def ensure_field_registry(db: AsyncSession) -> int:
    rows = await _all(
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
        text(
            """
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
            """
        ),
        payload,
    )
    await db.commit()
    return len(payload)


async def latest_run_id(db: AsyncSession) -> int | None:
    return await _scalar(
        db,
        """
        SELECT run_id
        FROM workbench.wb_run
        ORDER BY started_at DESC, run_id DESC
        LIMIT 1
        """,
    )


async def latest_completed_run_id(db: AsyncSession) -> int | None:
    return await _scalar(
        db,
        """
        SELECT run_id
        FROM workbench.wb_run
        WHERE status = 'completed'
        ORDER BY started_at DESC, run_id DESC
        LIMIT 1
        """,
    )


async def previous_completed_run_id(db: AsyncSession, current_run_id: int) -> int | None:
    return await _scalar(
        db,
        """
        SELECT run_id
        FROM workbench.wb_run
        WHERE status = 'completed' AND run_id <> :run_id
        ORDER BY started_at DESC, run_id DESC
        LIMIT 1
        """,
        {"run_id": current_run_id},
    )


async def _run_row(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    return await _first(
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
    rows = await _all(
        db,
        "SELECT layer_id, row_count FROM workbench.wb_layer_snapshot WHERE run_id = :run_id",
        {"run_id": run_id},
    )
    return {row["layer_id"]: int(row["row_count"] or 0) for row in rows}


async def _fallback_pipeline_counts(db: AsyncSession) -> dict[str, int]:
    rows = await _all(
        db,
        """
        SELECT relname, n_live_tup::bigint AS row_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'pipeline' AND relname IN ('raw_records', 'fact_final')
        """,
    )
    return {row["relname"]: int(row["row_count"] or 0) for row in rows}


async def build_run_summary(db: AsyncSession, run_id: int | None) -> dict[str, Any] | None:
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
        "duration_pretty": _format_duration(row["duration_seconds"]),
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


async def get_version_context(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    await ensure_reference_data(db)

    current_run_id = run_id or await latest_run_id(db)
    current = await build_run_summary(db, current_run_id)
    if current is None:
        return {"current_run": None, "compare_run": None, "generated_at": _now_iso()}

    selected_compare = compare_run_id or current.get("compare_run_id") or await previous_completed_run_id(db, current_run_id)
    compare = await build_run_summary(db, selected_compare)

    return {
        "generated_at": _now_iso(),
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
    await ensure_reference_data(db)
    rows = await _all(
        db,
        """
        SELECT
            r.run_id,
            r.run_mode,
            r.status,
            r.started_at,
            r.finished_at,
            r.duration_seconds,
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
            "duration_pretty": _format_duration(row["duration_seconds"]),
        }
        for row in rows
    ]


async def _compute_layer_snapshot(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    table_map = {
        "raw_records": "L0_raw",
        "fact_filtered": "L2_filtered",
        "dim_lac_trusted": "L2_lac_trusted",
        "dim_cell_stats": "L2_cell_stats",
        "dim_bs_trusted": "L3_bs_trusted",
        "fact_gps_corrected": "L3_gps_corrected",
        "fact_signal_filled": "L3_signal_filled",
        "map_cell_bs": "L3_cell_bs_map",
        "fact_final": "L4_final",
        "profile_lac": "L5_lac_profile",
        "profile_bs": "L5_bs_profile",
        "profile_cell": "L5_cell_profile",
    }
    rows = await _all(
        db,
        """
        SELECT relname, n_live_tup::bigint AS row_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'pipeline'
          AND relname = ANY(:tables)
        """,
        {"tables": list(table_map.keys())},
    )
    count_map = {row["relname"]: int(row["row_count"] or 0) for row in rows}
    return [
        {
            "run_id": run_id,
            "layer_id": layer_id,
            "row_count": count_map.get(table_name, 0),
            "pass_flag": None,
            "pass_note": f"来源: pg_stat_user_tables / {table_name}",
        }
        for table_name, layer_id in table_map.items()
    ]


async def _compute_step_metrics(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []

    s0 = await _first(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE source_table='layer0_lac') AS lac_rows,
               count(*) FILTER (WHERE source_table='layer0_gps_base') AS gps_rows
        FROM pipeline.raw_records
        """,
    )
    if s0:
        metrics.extend(
            [
                _metric_row(run_id, "s0", "total", "原始记录数", value_num=int(s0["total"]), unit="行"),
                _metric_row(run_id, "s0", "lac_rows", "LAC来源记录", value_num=int(s0["lac_rows"]), unit="行"),
                _metric_row(run_id, "s0", "gps_rows", "GPS来源记录", value_num=int(s0["gps_rows"]), unit="行"),
            ]
        )

    s4 = await _first(
        db,
        """
        SELECT count(*) AS trusted_lac_cnt,
               count(*) FILTER (WHERE operator_id_raw IN ('46000','46015','46020')) AS cmcc_cnt,
               count(*) FILTER (WHERE operator_id_raw = '46001') AS cucc_cnt,
               count(*) FILTER (WHERE operator_id_raw = '46011') AS ctcc_cnt
        FROM pipeline.dim_lac_trusted
        """,
    )
    if s4:
        metrics.extend(
            [
                _metric_row(run_id, "s4", "trusted_lac_cnt", "可信LAC数", value_num=int(s4["trusted_lac_cnt"]), unit="个"),
                _metric_row(run_id, "s4", "cmcc_cnt", "移动LAC数", value_num=int(s4["cmcc_cnt"]), unit="个"),
                _metric_row(run_id, "s4", "cucc_cnt", "联通LAC数", value_num=int(s4["cucc_cnt"]), unit="个"),
                _metric_row(run_id, "s4", "ctcc_cnt", "电信LAC数", value_num=int(s4["ctcc_cnt"]), unit="个"),
            ]
        )

    s6 = await _first(
        db,
        """
        SELECT count(*) AS output_rows,
               count(*) FILTER (WHERE lac_enrich_status = 'KEEP_TRUSTED_LAC') AS keep_trusted,
               count(*) FILTER (WHERE lac_enrich_status LIKE 'MULTI_LAC%') AS multi_lac_resolved,
               count(*) FILTER (WHERE lac_enrich_status IN ('BACKFILL_NULL_LAC','REPLACE_UNTRUSTED_LAC')) AS lac_backfilled
        FROM pipeline.fact_filtered
        """,
    )
    if s6:
        metrics.extend(
            [
                _metric_row(run_id, "s6", "output_rows", "合规输出行数", value_num=int(s6["output_rows"]), unit="行"),
                _metric_row(run_id, "s6", "keep_trusted", "保留可信LAC", value_num=int(s6["keep_trusted"]), unit="行"),
                _metric_row(run_id, "s6", "multi_lac_resolved", "多LAC修正", value_num=int(s6["multi_lac_resolved"]), unit="行"),
                _metric_row(run_id, "s6", "lac_backfilled", "LAC回填", value_num=int(s6["lac_backfilled"]), unit="行"),
            ]
        )

    s30 = await _first(
        db,
        """
        SELECT count(*) AS total_bs,
               count(*) FILTER (WHERE gps_valid_level = 'Usable') AS usable,
               count(*) FILTER (WHERE gps_valid_level = 'Risk') AS risk,
               count(*) FILTER (WHERE gps_valid_level = 'Unusable') AS unusable,
               count(*) FILTER (WHERE is_collision_suspect = true) AS collision_suspect
        FROM pipeline.dim_bs_trusted
        """,
    )
    if s30:
        metrics.extend(
            [
                _metric_row(run_id, "s30", "total_bs", "可信BS数", value_num=int(s30["total_bs"]), unit="个"),
                _metric_row(run_id, "s30", "usable", "可用BS", value_num=int(s30["usable"]), unit="个"),
                _metric_row(run_id, "s30", "risk", "风险BS", value_num=int(s30["risk"]), unit="个"),
                _metric_row(run_id, "s30", "unusable", "不可用BS", value_num=int(s30["unusable"]), unit="个"),
                _metric_row(run_id, "s30", "collision_suspect", "碰撞疑似BS", value_num=int(s30["collision_suspect"]), unit="个"),
            ]
        )

    s31 = await _first(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE gps_status = 'Verified') AS verified,
               count(*) FILTER (WHERE gps_status = 'Missing') AS missing,
               count(*) FILTER (WHERE gps_status = 'Drift') AS drift,
               count(*) FILTER (WHERE gps_source = 'Augmented_from_BS') AS filled_from_bs,
               count(*) FILTER (WHERE gps_source = 'Not_Filled') AS not_filled
        FROM pipeline.fact_gps_corrected
        """,
    )
    if s31:
        metrics.extend(
            [
                _metric_row(run_id, "s31", "total", "GPS修正输入", value_num=int(s31["total"]), unit="行"),
                _metric_row(run_id, "s31", "verified", "原生可用GPS", value_num=int(s31["verified"]), unit="行"),
                _metric_row(run_id, "s31", "missing", "GPS缺失", value_num=int(s31["missing"]), unit="行"),
                _metric_row(run_id, "s31", "drift", "GPS漂移", value_num=int(s31["drift"]), unit="行"),
                _metric_row(run_id, "s31", "filled_from_bs", "BS回填成功", value_num=int(s31["filled_from_bs"]), unit="行"),
                _metric_row(run_id, "s31", "not_filled", "无法回填", value_num=int(s31["not_filled"]), unit="行"),
            ]
        )

    gps_distribution = await _all(
        db,
        """
        SELECT gps_source, gps_status, gps_status_final, count(*) AS cnt
        FROM pipeline.fact_gps_corrected
        GROUP BY 1, 2, 3
        ORDER BY cnt DESC
        LIMIT 50
        """,
    )
    if gps_distribution:
        metrics.append(
            _metric_row(run_id, "s31", "gps_status_distribution", "GPS状态分布", value_json=gps_distribution)
        )

    s33 = await _first(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE signal_fill_source IN ('by_cell_median', 'cell_agg')) AS by_cell,
               count(*) FILTER (WHERE signal_fill_source IN ('by_bs_median', 'bs_agg')) AS by_bs,
               count(*) FILTER (WHERE signal_fill_source IN ('none', 'none_filled')) AS none_filled,
               round(avg(signal_missing_before_cnt)::numeric, 2) AS avg_missing_before,
               round(avg(signal_missing_after_cnt)::numeric, 2) AS avg_missing_after
        FROM pipeline.fact_signal_filled
        """,
    )
    if s33:
        metrics.extend(
            [
                _metric_row(run_id, "s33", "total", "信号补齐输入", value_num=int(s33["total"]), unit="行"),
                _metric_row(run_id, "s33", "by_cell", "Cell补齐", value_num=int(s33["by_cell"]), unit="行"),
                _metric_row(run_id, "s33", "by_bs", "BS补齐", value_num=int(s33["by_bs"]), unit="行"),
                _metric_row(run_id, "s33", "none_filled", "未补齐", value_num=int(s33["none_filled"]), unit="行"),
                _metric_row(run_id, "s33", "avg_missing_before", "补齐前平均缺失字段数", value_num=_number(s33["avg_missing_before"]), unit="个"),
                _metric_row(run_id, "s33", "avg_missing_after", "补齐后平均缺失字段数", value_num=_number(s33["avg_missing_after"]), unit="个"),
            ]
        )

    signal_distribution = await _all(
        db,
        """
        SELECT signal_fill_source,
               count(*) AS row_count,
               round(avg(signal_missing_before_cnt)::numeric, 2) AS avg_missing_before,
               round(avg(signal_missing_after_cnt)::numeric, 2) AS avg_missing_after
        FROM pipeline.fact_signal_filled
        GROUP BY 1
        ORDER BY row_count DESC
        """,
    )
    if signal_distribution:
        metrics.append(
            _metric_row(run_id, "s33", "signal_fill_distribution", "信号补齐分布", value_json=signal_distribution)
        )

    s41 = await _first(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE gps_status_final LIKE 'Filled%' OR gps_status_final = 'Verified') AS gps_resolved,
               count(*) FILTER (WHERE signal_fill_source IS NOT NULL) AS signal_filled,
               count(*) FILTER (WHERE is_severe_collision = true) AS severe_collision,
               count(*) FILTER (WHERE is_dynamic_cell = true) AS dynamic_cell
        FROM pipeline.fact_final
        """,
    )
    if s41:
        metrics.extend(
            [
                _metric_row(run_id, "s41", "total", "最终明细行数", value_num=int(s41["total"]), unit="行"),
                _metric_row(run_id, "s41", "gps_resolved", "GPS已解决", value_num=int(s41["gps_resolved"]), unit="行"),
                _metric_row(run_id, "s41", "signal_filled", "信号有补齐来源", value_num=int(s41["signal_filled"]), unit="行"),
                _metric_row(run_id, "s41", "severe_collision", "严重碰撞行数", value_num=int(s41["severe_collision"]), unit="行"),
                _metric_row(run_id, "s41", "dynamic_cell", "动态Cell行数", value_num=int(s41["dynamic_cell"]), unit="行"),
            ]
        )

    operator_tech_distribution = await _all(
        db,
        """
        SELECT operator_id_raw, tech_norm,
               count(*) AS row_count,
               count(*) FILTER (WHERE gps_status_final LIKE 'Filled%') AS gps_filled_count,
               count(*) FILTER (WHERE signal_fill_source IS NOT NULL) AS signal_filled_count,
               count(*) FILTER (WHERE is_collision_suspect = true) AS collision_count
        FROM pipeline.fact_final
        GROUP BY operator_id_raw, tech_norm
        ORDER BY row_count DESC
        """,
    )
    if operator_tech_distribution:
        metrics.append(
            _metric_row(run_id, "s41", "operator_tech_distribution", "运营商制式分布", value_json=operator_tech_distribution)
        )

    s50 = await _first(db, "SELECT count(*) AS lac_profiles FROM pipeline.profile_lac")
    if s50:
        metrics.append(_metric_row(run_id, "s50", "lac_profiles", "LAC画像数", value_num=int(s50["lac_profiles"]), unit="个"))

    s51 = await _first(
        db,
        """
        SELECT count(*) AS bs_profiles,
               count(*) FILTER (WHERE is_collision_suspect = true) AS bs_collision
        FROM pipeline.profile_bs
        """,
    )
    if s51:
        metrics.extend(
            [
                _metric_row(run_id, "s51", "bs_profiles", "BS画像数", value_num=int(s51["bs_profiles"]), unit="个"),
                _metric_row(run_id, "s51", "bs_collision", "BS碰撞样本", value_num=int(s51["bs_collision"]), unit="个"),
            ]
        )

    s52 = await _first(
        db,
        """
        SELECT count(*) AS cell_profiles,
               count(*) FILTER (WHERE is_dynamic_cell = true) AS cell_dynamic
        FROM pipeline.profile_cell
        """,
    )
    if s52:
        metrics.extend(
            [
                _metric_row(run_id, "s52", "cell_profiles", "Cell画像数", value_num=int(s52["cell_profiles"]), unit="个"),
                _metric_row(run_id, "s52", "cell_dynamic", "动态Cell样本", value_num=int(s52["cell_dynamic"]), unit="个"),
            ]
        )

    return metrics


async def _compute_anomaly_stats(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    rows = await _all(
        db,
        """
        SELECT 'BS' AS object_level, 'collision_suspect' AS anomaly_type,
               count(*) AS total_count, count(*) FILTER (WHERE is_collision_suspect=true) AS anomaly_count
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'severe_collision', count(*), count(*) FILTER (WHERE is_severe_collision=true)
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'gps_unstable', count(*), count(*) FILTER (WHERE is_gps_unstable=true)
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'bs_id_lt_256', count(*), count(*) FILTER (WHERE is_bs_id_lt_256=true)
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'multi_operator_shared', count(*), count(*) FILTER (WHERE is_multi_operator_shared=true)
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'insufficient_sample', count(*), count(*) FILTER (WHERE is_insufficient_sample=true)
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'CELL', 'dynamic_cell', count(*), count(*) FILTER (WHERE is_dynamic_cell=true)
        FROM pipeline.profile_cell
        UNION ALL
        SELECT 'CELL', 'collision_suspect', count(*), count(*) FILTER (WHERE is_collision_suspect=true)
        FROM pipeline.profile_cell
        UNION ALL
        SELECT 'CELL', 'insufficient_sample', count(*), count(*) FILTER (WHERE is_insufficient_sample=true)
        FROM pipeline.profile_cell
        """,
    )
    result = []
    for row in rows:
        total_count = int(row["total_count"])
        anomaly_count = int(row["anomaly_count"])
        result.append(
            {
                "run_id": run_id,
                "object_level": row["object_level"],
                "anomaly_type": row["anomaly_type"],
                "total_count": total_count,
                "anomaly_count": anomaly_count,
                "anomaly_ratio": round(anomaly_count / total_count, 4) if total_count else 0,
                "dimension_key": "ALL",
            }
        )
    return result


async def _active_parameter_json(db: AsyncSession) -> dict[str, Any]:
    row = await _first(
        db,
        """
        SELECT parameters
        FROM workbench.wb_parameter_set
        WHERE is_active = true
        ORDER BY id DESC
        LIMIT 1
        """,
    )
    return row["parameters"] if row else {}


def _step_params(parameters: dict[str, Any], step_id: str) -> dict[str, Any]:
    return parameters.get(step_id.replace("s", "step"), {})


async def _compute_rule_hits(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    params = await _active_parameter_json(db)
    step4 = _step_params(params, "s4")
    step30 = _step_params(params, "s30")
    step31 = _step_params(params, "s31")
    step35 = _step_params(params, "s35")
    step50 = _step_params(params, "s50")
    step51 = _step_params(params, "s51")
    step52 = _step_params(params, "s52")

    rows: list[dict[str, Any]] = []

    s4 = await _first(
        db,
        """
        SELECT
            count(*) FILTER (WHERE active_days < :active_days) AS active_days_hit,
            count(*) FILTER (
                WHERE (tech_norm = '5G' AND distinct_device_count < :min_device_count_5g)
                   OR (tech_norm <> '5G' AND distinct_device_count < :min_device_count)
            ) AS device_count_hit,
            count(*) AS total_count
        FROM pipeline.stats_lac
        """,
        {
            "active_days": step4.get("active_days_threshold", 7),
            "min_device_count": step4.get("min_device_count", 5),
            "min_device_count_5g": step4.get("min_device_count_5g", 3),
        },
    )
    if s4:
        total = int(s4["total_count"])
        rows.extend(
            [
                {
                    "run_id": run_id,
                    "step_id": "s4",
                    "rule_code": "active_days_threshold",
                    "rule_name": "活跃天数阈值",
                    "rule_purpose": "活跃天数不足的 LAC 不进入可信库。",
                    "hit_count": int(s4["active_days_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s4["active_days_hit"]) / total, 4) if total else 0,
                    "key_params": _json({"active_days_threshold": step4.get("active_days_threshold", 7)}),
                    "dimension_key": "ALL",
                },
                {
                    "run_id": run_id,
                    "step_id": "s4",
                    "rule_code": "min_device_count",
                    "rule_name": "设备数阈值",
                    "rule_purpose": "设备数过少的 LAC 不进入可信库。",
                    "hit_count": int(s4["device_count_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s4["device_count_hit"]) / total, 4) if total else 0,
                    "key_params": _json(
                        {
                            "min_device_count": step4.get("min_device_count", 5),
                            "min_device_count_5g": step4.get("min_device_count_5g", 3),
                        }
                    ),
                    "dimension_key": "ALL",
                },
            ]
        )

    s30 = await _first(
        db,
        """
        SELECT
            count(*) FILTER (WHERE gps_p90_dist_m > :collision_p90_dist_m) AS collision_hit,
            count(*) FILTER (WHERE gps_max_dist_m > :outlier_dist_m) AS outlier_hit,
            count(*) AS total_count
        FROM pipeline.dim_bs_trusted
        """,
        {
            "collision_p90_dist_m": step30.get("collision_p90_dist_m", 1500),
            "outlier_dist_m": step30.get("outlier_dist_m", 2500),
        },
    )
    if s30:
        total = int(s30["total_count"])
        rows.extend(
            [
                {
                    "run_id": run_id,
                    "step_id": "s30",
                    "rule_code": "collision_detection",
                    "rule_name": "碰撞检测",
                    "rule_purpose": "识别距离扩散异常的 BS。",
                    "hit_count": int(s30["collision_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s30["collision_hit"]) / total, 4) if total else 0,
                    "key_params": _json({"collision_p90_dist_m": step30.get("collision_p90_dist_m", 1500)}),
                    "dimension_key": "ALL",
                },
                {
                    "run_id": run_id,
                    "step_id": "s30",
                    "rule_code": "outlier_removal",
                    "rule_name": "离群点移除",
                    "rule_purpose": "识别超远距离 BS 噪点。",
                    "hit_count": int(s30["outlier_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s30["outlier_hit"]) / total, 4) if total else 0,
                    "key_params": _json({"outlier_dist_m": step30.get("outlier_dist_m", 2500)}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s31 = await _first(
        db,
        """
        SELECT
            count(*) FILTER (WHERE gps_status = 'Drift') AS drift_hit,
            count(*) FILTER (WHERE gps_source = 'Augmented_from_BS') AS fill_hit,
            count(*) AS total_count
        FROM pipeline.fact_gps_corrected
        """,
    )
    if s31:
        total = int(s31["total_count"])
        rows.extend(
            [
                {
                    "run_id": run_id,
                    "step_id": "s31",
                    "rule_code": "gps_drift",
                    "rule_name": "GPS漂移识别",
                    "rule_purpose": "定位偏离 BS 中心点的记录。",
                    "hit_count": int(s31["drift_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s31["drift_hit"]) / total, 4) if total else 0,
                    "key_params": _json({"drift_dist_m": step31.get("drift_dist_m", 1500)}),
                    "dimension_key": "ALL",
                },
                {
                    "run_id": run_id,
                    "step_id": "s31",
                    "rule_code": "gps_fill",
                    "rule_name": "BS回填",
                    "rule_purpose": "用可信 BS 中心点回填缺失或漂移 GPS。",
                    "hit_count": int(s31["fill_hit"]),
                    "total_count": total,
                    "hit_ratio": round(int(s31["fill_hit"]) / total, 4) if total else 0,
                    "key_params": _json({"drift_dist_m": step31.get("drift_dist_m", 1500)}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s33 = await _first(
        db,
        """
        SELECT
            count(*) FILTER (WHERE signal_fill_source IN ('cell_agg', 'by_cell_median')) AS fill_by_cell,
            count(*) FILTER (WHERE signal_fill_source IN ('bs_agg', 'by_bs_median')) AS fill_by_bs,
            count(*) FILTER (WHERE signal_fill_source IN ('none', 'none_filled')) AS fill_none,
            count(*) AS total_count
        FROM pipeline.fact_signal_filled
        """,
    )
    if s33:
        total = int(s33["total_count"])
        rows.extend(
            [
                {
                    "run_id": run_id,
                    "step_id": "s33",
                    "rule_code": "fill_by_cell",
                    "rule_name": "按Cell聚合补齐",
                    "rule_purpose": "优先用 Cell 聚合值补齐信号。",
                    "hit_count": int(s33["fill_by_cell"]),
                    "total_count": total,
                    "hit_ratio": round(int(s33["fill_by_cell"]) / total, 4) if total else 0,
                    "key_params": _json({}),
                    "dimension_key": "ALL",
                },
                {
                    "run_id": run_id,
                    "step_id": "s33",
                    "rule_code": "fill_by_bs",
                    "rule_name": "按BS聚合补齐",
                    "rule_purpose": "当 Cell 聚合不可用时回退到 BS 聚合。",
                    "hit_count": int(s33["fill_by_bs"]),
                    "total_count": total,
                    "hit_ratio": round(int(s33["fill_by_bs"]) / total, 4) if total else 0,
                    "key_params": _json({}),
                    "dimension_key": "ALL",
                },
                {
                    "run_id": run_id,
                    "step_id": "s33",
                    "rule_code": "fill_none",
                    "rule_name": "无法补齐",
                    "rule_purpose": "识别仍然缺失信号的记录。",
                    "hit_count": int(s33["fill_none"]),
                    "total_count": total,
                    "hit_ratio": round(int(s33["fill_none"]) / total, 4) if total else 0,
                    "key_params": _json({}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s35 = await _first(
        db,
        """
        SELECT
            count(*) FILTER (WHERE is_dynamic_cell = true) AS dynamic_hit,
            count(*) AS total_count
        FROM pipeline.profile_cell
        """,
    )
    if s35:
        total = int(s35["total_count"])
        rows.append(
            {
                "run_id": run_id,
                "step_id": "s35",
                "rule_code": "dynamic_cell",
                "rule_name": "动态Cell识别",
                "rule_purpose": "识别空间范围异常扩散的 Cell。",
                "hit_count": int(s35["dynamic_hit"]),
                "total_count": total,
                "hit_ratio": round(int(s35["dynamic_hit"]) / total, 4) if total else 0,
                "key_params": _json(
                    {
                        "min_half_major_dist_km": step35.get("min_half_major_dist_km", 10),
                        "min_day_major_share": step35.get("min_day_major_share", 0.5),
                    }
                ),
                "dimension_key": "ALL",
            }
        )

    for step_id, params_key, table_name, where_clause in [
        ("s50", step50, "pipeline.profile_lac", "record_count < :min_rows"),
        ("s51", step51, "pipeline.profile_bs", "record_count < :min_rows"),
        ("s52", step52, "pipeline.profile_cell", "record_count < :min_rows"),
    ]:
        stats = await _first(
            db,
            f"""
            SELECT count(*) FILTER (WHERE {where_clause}) AS hit_count,
                   count(*) AS total_count
            FROM {table_name}
            """,
            {"min_rows": params_key.get("min_rows", 500)},
        )
        if stats:
            total = int(stats["total_count"])
            rows.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "rule_code": "min_rows",
                    "rule_name": "最小样本数",
                    "rule_purpose": "识别样本不足的画像对象。",
                    "hit_count": int(stats["hit_count"]),
                    "total_count": total,
                    "hit_ratio": round(int(stats["hit_count"]) / total, 4) if total else 0,
                    "key_params": _json({"min_rows": params_key.get("min_rows", 500)}),
                    "dimension_key": "ALL",
                }
            )

    return rows


async def ensure_snapshot_bundle(db: AsyncSession, run_id: int | None, *, force: bool = False) -> dict[str, Any]:
    if run_id is None:
        return {"run_id": None, "refreshed": False}

    lock = _snapshot_lock(run_id)
    async with lock:
        existing = await _first(
            db,
            """
            SELECT
                (SELECT count(*) FROM workbench.wb_layer_snapshot WHERE run_id = :run_id) AS layer_count,
                (SELECT count(*) FROM workbench.wb_step_metric WHERE run_id = :run_id) AS metric_count,
                (SELECT count(*) FROM workbench.wb_anomaly_stats WHERE run_id = :run_id) AS anomaly_count,
                (SELECT count(*) FROM workbench.wb_rule_hit WHERE run_id = :run_id) AS rule_count
            """,
            {"run_id": run_id},
        )
        if existing and not force and all(int(existing[key]) > 0 for key in ["layer_count", "metric_count", "anomaly_count"]):
            return {"run_id": run_id, "refreshed": False, **existing}

        await ensure_reference_data(db)
        await db.execute(text("SET LOCAL statement_timeout = 0"))

        layer_rows = await _compute_layer_snapshot(db, run_id)
        metric_rows = await _compute_step_metrics(db, run_id)
        anomaly_rows = await _compute_anomaly_stats(db, run_id)
        rule_rows = await _compute_rule_hits(db, run_id)

        for table_name in [
            "workbench.wb_layer_snapshot",
            "workbench.wb_step_metric",
            "workbench.wb_anomaly_stats",
            "workbench.wb_rule_hit",
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
                    )
                    VALUES (
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
                    )
                    VALUES (
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
                    )
                    VALUES (
                        :run_id, :step_id, :rule_code, :rule_name, :rule_purpose,
                        :hit_count, :total_count, :hit_ratio, CAST(:key_params AS jsonb), :dimension_key
                    )
                    """
                ),
                rule_rows,
            )

        await db.commit()
        return {
            "run_id": run_id,
            "refreshed": True,
            "layer_count": len(layer_rows),
            "metric_count": len(metric_rows),
            "anomaly_count": len(anomaly_rows),
            "rule_count": len(rule_rows),
        }


async def list_layer_snapshot(db: AsyncSession, run_id: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    rows = await _all(
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
            item["metrics"][row["metric_code"]] = _number(row["value_num"]) if row["value_num"] is not None else row["value_text"]
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
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    step_rows = await _all(
        db,
        "SELECT step_id, step_order, step_name, step_name_en, layer FROM workbench.wb_step_registry ORDER BY step_order",
    )
    metric_rows = await _all(
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
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    rows = await _all(
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
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    row = await _first(
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
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    row = await _first(
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
    await ensure_snapshot_bundle(db, selected_run_id, force=force)
    row = await _first(
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


async def get_step_metrics(db: AsyncSession, step_id: str, run_id: int | None = None) -> dict[str, Any]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    await ensure_snapshot_bundle(db, selected_run_id)
    step = await _first(
        db,
        "SELECT step_id, step_name, step_name_en, layer, description FROM workbench.wb_step_registry WHERE step_id = :step_id",
        {"step_id": step_id},
    )
    rows = await _all(
        db,
        """
        SELECT metric_code, metric_name, value_num, value_text, value_json, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND dimension_key = 'ALL'
        ORDER BY id
        """,
        {"run_id": selected_run_id, "step_id": step_id},
    )
    gates = await _all(
        db,
        """
        SELECT gate_code, gate_name, severity, expected_rule, actual_value, pass_flag, remark
        FROM workbench.wb_gate_result
        WHERE run_id = :run_id
        ORDER BY severity DESC, gate_code
        """,
        {"run_id": selected_run_id},
    )
    cards = []
    json_metrics = {}
    for row in rows:
        if row["value_json"] is not None:
            json_metrics[row["metric_code"]] = row["value_json"]
            continue
        cards.append(
            {
                "metric_code": row["metric_code"],
                "metric_name": row["metric_name"],
                "value": _number(row["value_num"]) if row["value_num"] is not None else row["value_text"],
                "unit": row["unit"],
            }
        )
    return {
        "run_id": selected_run_id,
        "step_id": step_id,
        "step_name": step["step_name"] if step else step_id,
        "step_name_en": step["step_name_en"] if step else step_id,
        "layer": step["layer"] if step else None,
        "description": step["description"] if step else STEP_PURPOSES.get(step_id),
        "cards": cards,
        "json_metrics": json_metrics,
        "gate_results": gates,
    }


async def get_step_rules(db: AsyncSession, step_id: str, run_id: int | None = None) -> dict[str, Any]:
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    await ensure_snapshot_bundle(db, selected_run_id)
    rows = await _all(
        db,
        """
        SELECT rule_code, rule_name, rule_purpose, hit_count, total_count, hit_ratio, key_params, dimension_key
        FROM workbench.wb_rule_hit
        WHERE run_id = :run_id AND step_id = :step_id
        ORDER BY hit_count DESC NULLS LAST, rule_code
        """,
        {"run_id": selected_run_id, "step_id": step_id},
    )
    known = {row["rule_code"]: row for row in rows}
    merged = []
    for item in _step_rule_catalog(step_id):
        row = known.get(item["rule_code"])
        merged.append(
            {
                "rule_code": item["rule_code"],
                "rule_name": row["rule_name"] if row else item["rule_name"],
                "rule_purpose": row["rule_purpose"] if row else item["rule_purpose"],
                "hit_count": int(row["hit_count"]) if row and row["hit_count"] is not None else None,
                "total_count": int(row["total_count"]) if row and row["total_count"] is not None else None,
                "hit_ratio": float(row["hit_ratio"]) if row and row["hit_ratio"] is not None else None,
                "key_params": row["key_params"] if row else {key: None for key in item["param_keys"]},
                "dimension_key": row["dimension_key"] if row else "ALL",
            }
        )
    for row in rows:
        if row["rule_code"] not in {item["rule_code"] for item in _step_rule_catalog(step_id)}:
            merged.append(
                {
                    "rule_code": row["rule_code"],
                    "rule_name": row["rule_name"],
                    "rule_purpose": row["rule_purpose"],
                    "hit_count": int(row["hit_count"]) if row["hit_count"] is not None else None,
                    "total_count": int(row["total_count"]) if row["total_count"] is not None else None,
                    "hit_ratio": float(row["hit_ratio"]) if row["hit_ratio"] is not None else None,
                    "key_params": row["key_params"],
                    "dimension_key": row["dimension_key"],
                }
            )
    return {"run_id": selected_run_id, "step_id": step_id, "rules": merged}


async def get_step_sql(db: AsyncSession, step_id: str) -> dict[str, Any]:
    await ensure_reference_data(db)
    step = await _first(
        db,
        "SELECT step_id, step_name, sql_file FROM workbench.wb_step_registry WHERE step_id = :step_id",
        {"step_id": step_id},
    )
    if not step:
        return {"step_id": step_id, "files": []}

    bundle = await _first(
        db,
        """
        SELECT version_tag, file_manifest
        FROM workbench.wb_sql_bundle
        WHERE version_tag = :tag
        LIMIT 1
        """,
        {"tag": DEFAULT_SQL_BUNDLE_VERSION},
    )
    candidates = _resolve_sql_candidates(step["sql_file"])
    files = []
    for item in candidates:
        path = Path(item["path"])
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""
        files.append(
            {
                "path": item["path"],
                "rel_path": item["rel_path"],
                "content": content,
            }
        )
    return {
        "step_id": step_id,
        "step_name": step["step_name"],
        "sql_file": step["sql_file"],
        "sql_bundle_version": bundle["version_tag"] if bundle else None,
        "files": files,
    }


async def get_step_diff(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    context = await get_version_context(db, run_id=current_run_id, compare_run_id=compare_run_id)
    compare = context.get("compare_run")
    target_compare_run_id = compare["run_id"] if compare else None
    if target_compare_run_id is None:
        return {"current_run_id": current_run_id, "compare_run_id": None, "step_id": step_id, "items": []}

    await ensure_snapshot_bundle(db, current_run_id)
    await ensure_snapshot_bundle(db, target_compare_run_id)

    current_rows = await _all(
        db,
        """
        SELECT metric_code, metric_name, value_num, value_text, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND value_json IS NULL
        """,
        {"run_id": current_run_id, "step_id": step_id},
    )
    compare_rows = await _all(
        db,
        """
        SELECT metric_code, metric_name, value_num, value_text, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND value_json IS NULL
        """,
        {"run_id": target_compare_run_id, "step_id": step_id},
    )
    compare_map = {row["metric_code"]: row for row in compare_rows}
    items = []
    for row in current_rows:
        compare_row = compare_map.get(row["metric_code"])
        current_value = _number(row["value_num"]) if row["value_num"] is not None else row["value_text"]
        compare_value = _number(compare_row["value_num"]) if compare_row and compare_row["value_num"] is not None else (compare_row["value_text"] if compare_row else None)
        delta = None
        if isinstance(current_value, (int, float)) and isinstance(compare_value, (int, float)):
            delta = current_value - compare_value
        items.append(
            {
                "metric_code": row["metric_code"],
                "metric_name": row["metric_name"],
                "unit": row["unit"],
                "current_value": current_value,
                "compare_value": compare_value,
                "delta": delta,
            }
        )
    items.sort(key=lambda item: abs(item["delta"]) if isinstance(item["delta"], (int, float)) else -1, reverse=True)
    return {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare_run_id,
        "step_id": step_id,
        "items": items,
    }


async def _steps_by_field(db: AsyncSession) -> dict[tuple[str, str], list[str]]:
    step_rows = await _all(
        db,
        "SELECT step_id, step_name, input_tables, output_tables FROM workbench.wb_step_registry ORDER BY step_order",
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
    await ensure_field_registry(db)
    field_rows = await _all(
        db,
        """
        SELECT id, field_name, field_name_cn, table_name, schema_name, data_type,
               is_nullable, lifecycle_status, description
        FROM meta.meta_field_registry
        WHERE schema_name = 'pipeline'
        ORDER BY table_name, field_name
        """,
    )
    stats_rows = await _all(
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
                "distinct_estimate": _number(stats.get("n_distinct")),
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
    await ensure_field_registry(db)
    params: dict[str, Any] = {"field_name": field_name}
    where = "field_name = :field_name"
    if table_name:
        where += " AND table_name = :table_name"
        params["table_name"] = table_name
    row = await _first(
        db,
        f"""
        SELECT *
        FROM meta.meta_field_registry
        WHERE {where}
        ORDER BY table_name
        LIMIT 1
        """,
        params,
    )
    if not row:
        return None
    stats = await _first(
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
    health_rows = await _all(
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
    mapping_rules = await _all(
        db,
        """
        SELECT rule_code, rule_name, source_expression, target_expression, applies_to_steps, is_active
        FROM meta.meta_field_mapping_rule
        WHERE field_id = :field_id
        ORDER BY rule_code
        """,
        {"field_id": row["id"]},
    )
    change_log = await _all(
        db,
        """
        SELECT change_type, old_value, new_value, change_reason, changed_by, created_at
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
            "distinct_estimate": _number(stats.get("n_distinct")) if stats else None,
            "history": health_rows,
        },
        "related_steps": impacted_steps,
        "mapping_rules": mapping_rules,
        "change_log": change_log,
    }


def _build_sample_sql(criteria: dict[str, Any], limit: int) -> tuple[str, dict[str, Any], list[str], str]:
    source_table = criteria["source_table"]
    config = SAMPLE_TABLE_CONFIG[source_table]
    filters = criteria.get("filters", {})
    clauses = []
    params: dict[str, Any] = {"limit": limit}
    for key, value in filters.items():
        if key not in config["allowed_filters"]:
            continue
        param_key = f"p_{key}"
        clauses.append(f"{key} = :{param_key}")
        params[param_key] = value

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_by = criteria.get("order_by")
    if not order_by:
        order_by = config["object_id_columns"][0] + " DESC"
    sql = f"""
        SELECT {', '.join(config['columns'])}
        FROM pipeline.{source_table}
        {where_clause}
        ORDER BY {order_by}
        LIMIT :limit
    """
    return sql, params, config["columns"], source_table


async def list_sample_sets(db: AsyncSession) -> dict[str, Any]:
    await ensure_reference_data(db)
    rows = await _all(
        db,
        """
        SELECT id, name, description, sample_type, filter_criteria, object_ids, is_active, created_at
        FROM workbench.wb_sample_set
        WHERE is_active = true
        ORDER BY id
        """,
    )
    items = []
    for row in rows:
        criteria = row["filter_criteria"] or {}
        items.append(
            {
                **row,
                "source_table": criteria.get("source_table"),
                "source_table_cn": table_label(criteria.get("source_table", "")),
                "step_ids": criteria.get("step_ids", []),
            }
        )
    return {"items": items}


async def get_sample_set_detail(db: AsyncSession, sample_set_id: int, limit: int = 50) -> dict[str, Any] | None:
    row = await _first(
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
    sql, params, columns, source_table = _build_sample_sql(criteria, limit)
    records = await _all(db, sql, params)
    return {
        "sample_set": {
            **row,
            "source_table": source_table,
            "source_table_cn": table_label(source_table),
            "step_ids": criteria.get("step_ids", []),
        },
        "columns": columns,
        "records": records,
    }


async def get_step_samples(db: AsyncSession, step_id: str, limit: int = 20) -> dict[str, Any]:
    data = await list_sample_sets(db)
    matching = [
        item
        for item in data["items"]
        if step_id in item.get("step_ids", [])
    ]
    detailed = []
    for item in matching:
        detail = await get_sample_set_detail(db, item["id"], limit=limit)
        if detail:
            detailed.append(
                {
                    **item,
                    "columns": detail["columns"],
                    "records": detail["records"],
                }
            )
    return {"step_id": step_id, "sample_sets": detailed}


async def refresh_all(db: AsyncSession, *, run_id: int | None = None, include_fields: bool = True) -> dict[str, Any]:
    await ensure_reference_data(db)
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    snapshot_result = await ensure_snapshot_bundle(db, selected_run_id, force=True)
    field_count = await ensure_field_registry(db) if include_fields else 0
    return {
        "generated_at": _now_iso(),
        "run_id": selected_run_id,
        "snapshot": snapshot_result,
        "field_registry_rows": field_count,
    }
