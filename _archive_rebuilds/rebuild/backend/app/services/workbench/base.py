"""共用 SQL helper、常量、锁和工具函数。"""

from __future__ import annotations

import asyncio
import json
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

# ── 路径常量 ──────────────────────────────────────────────────────

REBUILD_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE_ROOT = REBUILD_ROOT.parent
SQL_ASSET_ROOT = WORKSPACE_ROOT / "lac_enbid_project"

# ── 版本默认值 ────────────────────────────────────────────────────

DEFAULT_RULE_SET_VERSION = "R-001"
DEFAULT_SQL_BUNDLE_VERSION = "S-001"
DEFAULT_CONTRACT_VERSION = "C-001"

# ── 规则目录 ──────────────────────────────────────────────────────

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

# ── 锁 ───────────────────────────────────────────────────────────

_BOOTSTRAP_LOCK = asyncio.Lock()
_SNAPSHOT_LOCKS: dict[int, asyncio.Lock] = {}


def snapshot_lock(run_id: int) -> asyncio.Lock:
    """获取或创建指定 run_id 的快照计算锁。"""
    lock = _SNAPSHOT_LOCKS.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _SNAPSHOT_LOCKS[run_id] = lock
    return lock


# ── 通用工具函数 ──────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def to_number(value: Any) -> int | float | None:
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


def mappings_to_dicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def metric_row(
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
    """构建一条 wb_step_metric 插入行。"""
    return {
        "run_id": run_id,
        "step_id": step_id,
        "metric_code": metric_code,
        "metric_name": metric_name,
        "dimension_key": dimension_key,
        "value_num": value_num,
        "value_text": value_text,
        "value_json": to_json(value_json) if value_json is not None else None,
        "unit": unit,
    }


# ── 通用 DB helper ───────────────────────────────────────────────

async def scalar(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> Any:
    result = await db.execute(text(sql), params or {})
    return result.scalar()


async def first(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = await db.execute(text(sql), params or {})
    row = result.mappings().first()
    return dict(row) if row else None


async def fetch_all(db: AsyncSession, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params or {})
    return mappings_to_dicts(result.mappings().all())


def resolve_sql_candidates(sql_file: str | None) -> list[dict[str, str]]:
    """在 SQL_ASSET_ROOT 下搜索匹配的 SQL 文件。"""
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


def step_rule_catalog(step_id: str) -> list[dict[str, Any]]:
    """获取指定步骤的规则目录。"""
    return DEFAULT_RULE_SET.get(step_id, [])
