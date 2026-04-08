"""样本快照与 D3 详情辅助函数。"""

from __future__ import annotations

from typing import Any

from app.services.workbench.base import SAMPLE_TABLE_CONFIG

RAW_CORRECTED_PAIRS: dict[str, list[dict[str, str]]] = {
    "fact_gps_corrected": [
        {"label": "经度", "raw": "lon_raw", "corrected": "lon_final"},
        {"label": "纬度", "raw": "lat_raw", "corrected": "lat_final"},
        {"label": "GPS状态", "raw": "gps_status", "corrected": "gps_status_final"},
    ],
    "fact_signal_filled": [
        {"label": "缺失字段数", "raw": "signal_missing_before_cnt", "corrected": "signal_missing_after_cnt"},
        {"label": "补齐来源", "raw": "signal_fill_source", "corrected": "signal_fill_source"},
    ],
}


def build_sample_sql(criteria: dict[str, Any], limit: int) -> tuple[str, dict[str, Any], list[str], str]:
    """根据样本集过滤条件构建查询 SQL。"""
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
    order_by = criteria.get("order_by") or (config["object_id_columns"][0] + " DESC")
    sql = f"""
        SELECT {', '.join(config['columns'])}
        FROM pipeline.{source_table}
        {where_clause}
        ORDER BY {order_by}
        LIMIT :limit
    """
    return sql, params, config["columns"], source_table


def row_object_key(source_table: str, row: dict[str, Any]) -> str:
    columns = SAMPLE_TABLE_CONFIG[source_table]["object_id_columns"]
    return "|".join(str(row.get(column) or "NULL") for column in columns)


def row_object_label(source_table: str, row: dict[str, Any]) -> str:
    columns = SAMPLE_TABLE_CONFIG[source_table]["object_id_columns"]
    return " / ".join(str(row.get(column) or "—") for column in columns)


def sample_rule_hits(source_table: str, row: dict[str, Any]) -> list[str]:
    if source_table == "profile_bs":
        return [
            rule
            for rule, flag in [
                ("collision_suspect", row.get("is_collision_suspect")),
                ("severe_collision", row.get("is_severe_collision")),
                ("gps_unstable", row.get("is_gps_unstable")),
                ("insufficient_sample", row.get("is_insufficient_sample")),
            ]
            if flag
        ]
    if source_table == "profile_cell":
        return [
            rule
            for rule, flag in [
                ("dynamic_cell", row.get("is_dynamic_cell")),
                ("collision_suspect", row.get("is_collision_suspect")),
                ("gps_unstable", row.get("is_gps_unstable")),
                ("insufficient_sample", row.get("is_insufficient_sample")),
            ]
            if flag
        ]
    if source_table == "fact_gps_corrected":
        hits = []
        if row.get("gps_status") == "Drift":
            hits.append("gps_drift")
        if row.get("gps_status") == "Missing":
            hits.append("gps_missing")
        if row.get("gps_source") in {"Augmented_from_BS", "Augmented_from_Risk_BS"}:
            hits.append("gps_filled")
        if row.get("is_from_risk_bs"):
            hits.append("from_risk_bs")
        if row.get("lon_raw") != row.get("lon_final") or row.get("lat_raw") != row.get("lat_final"):
            hits.append("gps_corrected")
        return hits
    if source_table == "fact_signal_filled":
        hits = []
        if row.get("signal_fill_source") in {"cell_agg", "by_cell_median", "cell_nearest"}:
            hits.append("fill_by_cell")
        if row.get("signal_fill_source") in {"bs_agg", "by_bs_median", "bs_top_cell_nearest"}:
            hits.append("fill_by_bs")
        if row.get("signal_fill_source") in {"none", "none_filled"}:
            hits.append("fill_failed")
        if (row.get("signal_missing_after_cnt") or 0) < (row.get("signal_missing_before_cnt") or 0):
            hits.append("signal_filled")
        return hits
    return []


def changed_fields(current_payload: dict[str, Any], compare_payload: dict[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(current_payload) | set(compare_payload))
    changed = []
    for key in keys:
        current_value = current_payload.get(key)
        compare_value = compare_payload.get(key)
        if current_value != compare_value:
            changed.append({"field": key, "current": current_value, "compare": compare_value})
    return changed


def display_pairs(source_table: str, current_payload: dict[str, Any], compare_payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for pair in RAW_CORRECTED_PAIRS.get(source_table, []):
        result.append(
            {
                "label": pair["label"],
                "raw_key": pair["raw"],
                "corrected_key": pair["corrected"],
                "current_raw": current_payload.get(pair["raw"]),
                "current_corrected": current_payload.get(pair["corrected"]),
                "compare_raw": compare_payload.get(pair["raw"]),
                "compare_corrected": compare_payload.get(pair["corrected"]),
            }
        )
    return result
