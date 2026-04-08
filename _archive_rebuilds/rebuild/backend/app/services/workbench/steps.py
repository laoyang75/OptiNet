"""P2 步骤页读模型：步骤指标、规则命中、SQL 资产、diff 对比。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.labels import STEP_PURPOSES
from app.services.workbench.object_snapshots import load_step_object_diff
from app.services.workbench.base import (
    DEFAULT_SQL_BUNDLE_VERSION,
    fetch_all,
    first,
    resolve_sql_candidates,
    step_rule_catalog,
    to_json,
    to_number,
)
from app.services.workbench.catalog import (
    ensure_reference_data,
    get_version_context,
    latest_completed_run_id,
    latest_run_id,
    previous_completed_run_id,
    resolve_run_parameters,
)
from app.services.workbench.sql_render import render_sql_with_parameters

from sqlalchemy.ext.asyncio import AsyncSession


async def _bundle_for_run(db: AsyncSession, run_id: int | None) -> dict[str, Any] | None:
    if run_id is None:
        return None
    return await first(
        db,
        """
        SELECT sb.version_tag, sb.file_manifest
        FROM workbench.wb_run r
        LEFT JOIN workbench.wb_sql_bundle sb ON sb.id = r.sql_bundle_id
        WHERE r.run_id = :run_id
        """,
        {"run_id": run_id},
    )


def _bundle_candidates(bundle: dict[str, Any] | None, step_id: str, sql_file: str | None) -> list[dict[str, str]]:
    manifest = bundle.get("file_manifest") if bundle else None
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except json.JSONDecodeError:
            manifest = None
    if isinstance(manifest, list):
        for item in manifest:
            if item.get("step_id") == step_id and item.get("sql_file") == sql_file:
                candidates = item.get("candidates") or []
                if candidates:
                    return candidates
    return resolve_sql_candidates(sql_file)


async def _parameter_context_for_run(db: AsyncSession, run_id: int | None) -> dict[str, Any]:
    if run_id is None:
        return {"version_tag": None, "parameters": {}}
    row = await first(
        db,
        """
        SELECT ps.version_tag, ps.parameters
        FROM workbench.wb_run r
        LEFT JOIN workbench.wb_parameter_set ps ON ps.id = r.parameter_set_id
        WHERE r.run_id = :run_id
        """,
        {"run_id": run_id},
    )
    return row or {"version_tag": None, "parameters": {}}


def _load_sql_files(
    candidates: list[dict[str, str]],
    *,
    step_id: str,
    run_id: int | None,
    parameter_set: str | None,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    files = []
    for item in candidates:
        path = Path(item["path"])
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""
        rendered = render_sql_with_parameters(
            content,
            step_id=step_id,
            run_id=run_id,
            parameter_set=parameter_set,
            parameters=parameters,
        )
        files.append({
            "path": item["path"],
            "rel_path": item["rel_path"],
            "content": content,
            "resolved_content": rendered["resolved_content"],
            "resolution_status": rendered["resolution_status"],
            "resolved_parameters": rendered["resolved_parameters"],
        })
    return files


async def get_step_metrics(db: AsyncSession, step_id: str, run_id: int | None = None) -> dict[str, Any]:
    """获取指定步骤在某次 run 下的指标卡片和 gate 结果。"""
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    step = await first(
        db,
        "SELECT step_id, step_name, step_name_en, layer, description FROM workbench.wb_step_registry WHERE step_id = :step_id",
        {"step_id": step_id},
    )
    rows = await fetch_all(db, """
        SELECT metric_code, metric_name, value_num, value_text, value_json, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND dimension_key = 'ALL'
        ORDER BY id
    """, {"run_id": selected_run_id, "step_id": step_id})
    gates = await fetch_all(db, """
        SELECT gate_code, gate_name, severity, expected_rule, actual_value, pass_flag, remark
        FROM workbench.wb_gate_result
        WHERE run_id = :run_id
        ORDER BY severity DESC, gate_code
    """, {"run_id": selected_run_id})

    cards = []
    json_metrics = {}
    for row in rows:
        if row["value_json"] is not None:
            json_metrics[row["metric_code"]] = row["value_json"]
            continue
        cards.append({
            "metric_code": row["metric_code"],
            "metric_name": row["metric_name"],
            "value": to_number(row["value_num"]) if row["value_num"] is not None else row["value_text"],
            "unit": row["unit"],
        })
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
        "snapshot_ready": bool(rows or gates),
    }


async def get_step_rules(db: AsyncSession, step_id: str, run_id: int | None = None) -> dict[str, Any]:
    """获取指定步骤的规则命中详情。"""
    selected_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    rows = await fetch_all(db, """
        SELECT rule_code, rule_name, rule_purpose, hit_count, total_count, hit_ratio, key_params, dimension_key
        FROM workbench.wb_rule_hit
        WHERE run_id = :run_id AND step_id = :step_id
        ORDER BY hit_count DESC NULLS LAST, rule_code
    """, {"run_id": selected_run_id, "step_id": step_id})

    known = {row["rule_code"]: row for row in rows}
    merged = []
    for item in step_rule_catalog(step_id):
        row = known.get(item["rule_code"])
        merged.append({
            "rule_code": item["rule_code"],
            "rule_name": row["rule_name"] if row else item["rule_name"],
            "rule_purpose": row["rule_purpose"] if row else item["rule_purpose"],
            "hit_count": int(row["hit_count"]) if row and row["hit_count"] is not None else None,
            "total_count": int(row["total_count"]) if row and row["total_count"] is not None else None,
            "hit_ratio": float(row["hit_ratio"]) if row and row["hit_ratio"] is not None else None,
            "key_params": row["key_params"] if row else {key: None for key in item["param_keys"]},
            "dimension_key": row["dimension_key"] if row else "ALL",
        })
    for row in rows:
        if row["rule_code"] not in {item["rule_code"] for item in step_rule_catalog(step_id)}:
            merged.append({
                "rule_code": row["rule_code"],
                "rule_name": row["rule_name"],
                "rule_purpose": row["rule_purpose"],
                "hit_count": int(row["hit_count"]) if row["hit_count"] is not None else None,
                "total_count": int(row["total_count"]) if row["total_count"] is not None else None,
                "hit_ratio": float(row["hit_ratio"]) if row["hit_ratio"] is not None else None,
                "key_params": row["key_params"],
                "dimension_key": row["dimension_key"],
            })
    return {"run_id": selected_run_id, "step_id": step_id, "rules": merged}


async def get_step_sql(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    """获取指定步骤的 SQL 资产文件内容，并绑定当前 / 对比 run 的 SQL bundle。"""
    await ensure_reference_data(db)
    step = await first(
        db,
        """
        SELECT step_id, step_order, step_name, sql_file
        FROM workbench.wb_step_registry
        WHERE step_id = :step_id
        """,
        {"step_id": step_id},
    )
    if not step:
        return {"step_id": step_id, "files": []}

    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    context = await get_version_context(db, run_id=current_run_id, compare_run_id=compare_run_id)
    compare = context.get("compare_run")
    target_compare_run_id = compare["run_id"] if compare else None

    bundle = await _bundle_for_run(db, current_run_id)
    compare_bundle = await _bundle_for_run(db, target_compare_run_id)
    current_param_context = await _parameter_context_for_run(db, current_run_id)
    compare_param_context = await _parameter_context_for_run(db, target_compare_run_id)
    if bundle is None:
        bundle = await first(
            db,
            """
            SELECT version_tag, file_manifest FROM workbench.wb_sql_bundle
            WHERE version_tag = :tag LIMIT 1
            """,
            {"tag": DEFAULT_SQL_BUNDLE_VERSION},
        )

    files = _load_sql_files(
        _bundle_candidates(bundle, step_id, step["sql_file"]),
        step_id=step_id,
        run_id=current_run_id,
        parameter_set=current_param_context.get("version_tag"),
        parameters=current_param_context.get("parameters") or {},
    )
    compare_files = (
        _load_sql_files(
            _bundle_candidates(compare_bundle, step_id, step["sql_file"]),
            step_id=step_id,
            run_id=target_compare_run_id,
            parameter_set=compare_param_context.get("version_tag"),
            parameters=compare_param_context.get("parameters") or {},
        )
        if compare_bundle
        else []
    )
    return {
        "step_id": step_id,
        "step_order": step["step_order"],
        "step_name": step["step_name"],
        "sql_file": step["sql_file"],
        "run_id": current_run_id,
        "compare_run_id": target_compare_run_id,
        "sql_bundle_version": bundle["version_tag"] if bundle else None,
        "compare_sql_bundle_version": compare_bundle["version_tag"] if compare_bundle else None,
        "parameter_set_version": current_param_context.get("version_tag"),
        "compare_parameter_set_version": compare_param_context.get("version_tag"),
        "files": files,
        "compare_files": compare_files,
    }


async def get_step_diff(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    """对比两次 run 在某步骤上的数值指标差异。"""
    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    context = await get_version_context(db, run_id=current_run_id, compare_run_id=compare_run_id)
    compare = context.get("compare_run")
    target_compare_run_id = compare["run_id"] if compare else None
    if target_compare_run_id is None:
        return {"current_run_id": current_run_id, "compare_run_id": None, "step_id": step_id, "items": []}

    current_rows = await fetch_all(db, """
        SELECT metric_code, metric_name, value_num, value_text, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND value_json IS NULL
    """, {"run_id": current_run_id, "step_id": step_id})
    compare_rows = await fetch_all(db, """
        SELECT metric_code, metric_name, value_num, value_text, unit
        FROM workbench.wb_step_metric
        WHERE run_id = :run_id AND step_id = :step_id AND value_json IS NULL
    """, {"run_id": target_compare_run_id, "step_id": step_id})

    compare_map = {row["metric_code"]: row for row in compare_rows}
    items = []
    for row in current_rows:
        compare_row = compare_map.get(row["metric_code"])
        current_value = to_number(row["value_num"]) if row["value_num"] is not None else row["value_text"]
        compare_value = to_number(compare_row["value_num"]) if compare_row and compare_row["value_num"] is not None else (compare_row["value_text"] if compare_row else None)
        delta = None
        if isinstance(current_value, (int, float)) and isinstance(compare_value, (int, float)):
            delta = current_value - compare_value
        items.append({
            "metric_code": row["metric_code"],
            "metric_name": row["metric_name"],
            "unit": row["unit"],
            "current_value": current_value,
            "compare_value": compare_value,
            "delta": delta,
        })
    items.sort(key=lambda item: abs(item["delta"]) if isinstance(item["delta"], (int, float)) else -1, reverse=True)
    return {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare_run_id,
        "step_id": step_id,
        "items": items,
    }


async def get_step_parameter_diff(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any]:
    """对比两次 run 在某步骤上的参数差异。"""
    current_run_id = run_id or await latest_completed_run_id(db) or await latest_run_id(db)
    if current_run_id is None:
        return {"current_run_id": None, "compare_run_id": None, "step_id": step_id, "global_diff": [], "step_diff": []}

    target_compare = compare_run_id or await previous_completed_run_id(db, current_run_id)
    if target_compare is None:
        return {"current_run_id": current_run_id, "compare_run_id": None, "step_id": step_id, "global_diff": [], "step_diff": []}

    current_params = await resolve_run_parameters(db, current_run_id)
    compare_params = await resolve_run_parameters(db, target_compare)
    step_key = step_id.replace("s", "step")

    def _diff_dict(curr: dict, comp: dict) -> list[dict[str, Any]]:
        all_keys = sorted(set(list(curr.keys()) + list(comp.keys())))
        items = []
        for key in all_keys:
            cv = curr.get(key)
            pv = comp.get(key)
            if cv != pv:
                items.append({"key": key, "current": cv, "compare": pv, "changed": True})
            else:
                items.append({"key": key, "current": cv, "compare": pv, "changed": False})
        return items

    return {
        "current_run_id": current_run_id,
        "compare_run_id": target_compare,
        "step_id": step_id,
        "global_diff": _diff_dict(current_params.get("global", {}), compare_params.get("global", {})),
        "step_diff": _diff_dict(current_params.get(step_key, {}), compare_params.get(step_key, {})),
    }


async def get_step_object_diff(
    db: AsyncSession,
    step_id: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """基于 run 绑定对象快照返回真实对象级 diff。"""
    return await load_step_object_diff(
        db,
        step_id,
        run_id=run_id,
        compare_run_id=compare_run_id,
        limit=limit,
    )
