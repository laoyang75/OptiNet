"""根据 run 参数渲染 SQL 资产。"""

from __future__ import annotations

import re
from typing import Any

ALIAS_PARAMETER_MAP: dict[str, dict[str, str]] = {
    "s4": {
        "active_days_threshold": "step4.active_days_threshold",
        "min_device_count": "step4.min_device_count",
        "min_device_count_5g": "step4.min_device_count_5g",
        "report_count_percentile": "step4.report_count_percentile",
    },
    "s30": {
        "outlier_remove_if_dist_m_gt": "step30.outlier_dist_m",
        "collision_if_p90_dist_m_gt": "step30.collision_p90_dist_m",
        "signal_keep_top50_n": "step30.signal_top_n",
        "center_bin_scale": "step30.center_bin_scale",
    },
    "s31": {"drift_if_dist_m_gt": "step31.drift_dist_m"},
    "s35": {
        "min_half_major_dist_km": "step35.min_half_major_dist_km",
        "min_day_major_share": "step35.min_day_major_share",
    },
    "s40": {
        "city_dist_threshold_4g_m": "step40.gps_dist_threshold_4g",
        "city_dist_threshold_5g_m": "step40.gps_dist_threshold_5g",
        "china_lon_min": "global.china_bbox.lon_min",
        "china_lon_max": "global.china_bbox.lon_max",
        "china_lat_min": "global.china_bbox.lat_min",
        "china_lat_max": "global.china_bbox.lat_max",
    },
    "s50": {
        "min_rows_for_profile": "step50.min_rows",
        "lac_gps_p90_warn_m": "step50.gps_p90_warn_m",
    },
    "s51": {
        "min_rows_for_profile": "step51.min_rows",
        "bs_gps_p90_warn_4g_m": "step51.gps_p90_warn_4g_m",
        "bs_gps_p90_warn_5g_m": "step51.gps_p90_warn_5g_m",
    },
    "s52": {
        "min_rows_for_profile": "step52.min_rows",
        "cell_gps_p90_warn_4g_m": "step52.gps_p90_warn_4g_m",
        "cell_gps_p90_warn_5g_m": "step52.gps_p90_warn_5g_m",
    },
}

_LITERAL_WITH_CAST_RE = re.compile(
    r"^\s*(?P<literal>'[^']*'|[-+]?\d+(?:\.\d+)?|TRUE|FALSE)(?P<cast>::[A-Za-z0-9_ ()]+)?\s*$",
    re.IGNORECASE,
)


def _walk_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_sql_with_parameters(
    content: str,
    *,
    step_id: str,
    run_id: int | None,
    parameter_set: str | None,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """把 run 绑定参数渲染到 params CTE 的字面量里。"""
    alias_map = ALIAS_PARAMETER_MAP.get(step_id, {})
    if not alias_map:
        return {
            "resolved_content": content,
            "resolved_parameters": [],
            "resolution_status": "static_asset",
        }

    rendered_lines: list[str] = []
    resolved_parameters: list[dict[str, Any]] = []
    alias_values = {alias: _walk_path(parameters, path) for alias, path in alias_map.items()}

    for line in content.splitlines():
        replaced = False
        for alias, path in alias_map.items():
            marker = f" AS {alias}"
            if marker not in line:
                continue
            value = alias_values.get(alias)
            if value is None:
                continue
            prefix, suffix = line.split(marker, 1)
            indent = prefix[: len(prefix) - len(prefix.lstrip())]
            expr = prefix.strip()
            match = _LITERAL_WITH_CAST_RE.match(expr)
            cast = match.group("cast") if match else ""
            rendered_expr = f"{_sql_literal(value)}{cast}"
            rendered_lines.append(f"{indent}{rendered_expr}{marker}{suffix}")
            resolved_parameters.append({"alias": alias, "path": path, "value": value})
            replaced = True
            break
        if not replaced:
            rendered_lines.append(line)

    if not resolved_parameters:
        return {
            "resolved_content": content,
            "resolved_parameters": [],
            "resolution_status": "static_asset",
        }

    header_lines = [
        f"-- resolved for run #{run_id or '—'} / parameter_set {parameter_set or '—'}",
        "-- bound parameters:",
    ]
    for item in resolved_parameters:
        header_lines.append(f"--   {item['alias']} <= {item['path']} = {item['value']}")
    header_lines.append("")
    return {
        "resolved_content": "\n".join(header_lines + rendered_lines),
        "resolved_parameters": resolved_parameters,
        "resolution_status": "resolved_from_run_parameters",
    }
