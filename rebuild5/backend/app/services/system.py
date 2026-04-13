"""System metadata services for rebuild5."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from ..core.database import fetchall
from ..core.settings import settings

FetchAll = Callable[[str, tuple[Any, ...] | None], list[dict[str, Any]]]


def _missing_relation(exc: Exception) -> bool:
    text = str(exc)
    return 'does not exist' in text or 'UndefinedTable' in text


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def load_rule_configs() -> dict[str, Any]:
    return {
        "profile": load_yaml_config(settings.profile_params_path),
        "antitoxin": load_yaml_config(settings.antitoxin_params_path),
        "retention": load_yaml_config(settings.retention_params_path),
    }


def build_system_config_payload(
    datasets: list[dict[str, Any]],
    rules: dict[str, Any],
) -> dict[str, Any]:
    current = next((row for row in datasets if row.get("is_current")), datasets[0] if datasets else None)
    current_version = {
        "dataset_key": current.get("dataset_key", "") if current else "",
        "run_id": current.get("last_run_id", "run_bootstrap") if current else "run_bootstrap",
        "snapshot_version": current.get("last_snapshot_version", "v0") if current else "v0",
        "status": current.get("last_run_status", "completed") if current else "completed",
        "updated_at": current.get("last_updated_at", "") if current else "",
    }
    return {
        "current_version": current_version,
        "dataset_mode": {
            "key": "single_active",
            "label": "单活数据集",
            "switch_supported": False,
            "message": "当前版本仅支持 config/dataset.yaml 指定的单活数据集；页面不支持在线切换，切换能力留待后续开发。",
            "plan_doc": "rebuild5/docs/dev/05_多数据集切换方案.md",
        },
        "datasets": datasets,
        "params": rules,
    }


def list_datasets(fetchall_fn: FetchAll = fetchall) -> list[dict[str, Any]]:
    try:
        return fetchall_fn(
            """
            SELECT
                dataset_key,
                source_desc,
                imported_at,
                record_count,
                lac_scope,
                time_range,
                status,
                is_current,
                last_run_id,
                last_snapshot_version,
                last_run_status,
                last_updated_at
            FROM rebuild5_meta.dataset_registry
            ORDER BY is_current DESC, imported_at DESC NULLS LAST, dataset_key
            """,
            None,
        )
    except Exception as exc:
        if _missing_relation(exc):
            return []
        raise


def list_run_logs(fetchall_fn: FetchAll = fetchall) -> list[dict[str, Any]]:
    try:
        return fetchall_fn(
            """
            SELECT
                run_id,
                run_type,
                dataset_key,
                snapshot_version,
                status,
                started_at,
                finished_at,
                step_chain,
                result_summary
            FROM rebuild5_meta.run_log
            ORDER BY started_at DESC NULLS LAST, run_id DESC
            """,
            None,
        )
    except Exception as exc:
        if _missing_relation(exc):
            return []
        raise


def get_system_config(fetchall_fn: FetchAll = fetchall) -> dict[str, Any]:
    return build_system_config_payload(list_datasets(fetchall_fn=fetchall_fn), load_rule_configs())
