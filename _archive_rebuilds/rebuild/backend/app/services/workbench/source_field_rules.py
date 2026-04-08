"""源字段合规规则编译。"""

from __future__ import annotations

import re
from typing import Any

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sql_identifier(value: str) -> str:
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"非法字段名: {value}")
    return value


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def walk_param_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def resolve_rule_parameter(parameters: dict[str, Any], refs: list[str]) -> Any:
    for ref in refs:
        value = walk_param_path(parameters, ref)
        if value not in (None, {}, []):
            return value
    return None


def compile_compliance_predicates(
    field_name: str,
    rule_type: str,
    rule_config: dict[str, Any],
    parameter_values: Any,
) -> dict[str, str]:
    field = sql_identifier(field_name)

    if rule_type == "whitelist":
        values = as_list(parameter_values if rule_config.get("values_from_param") else rule_config.get("values"))
        if not values:
            raise ValueError(f"{field_name} 的白名单规则缺少参数值。")
        membership = f"{field} IN ({', '.join(sql_literal(value) for value in values)})"
        return {
            "compliant": f"{field} IS NOT NULL AND {membership}",
            "invalid": f"{field} IS NOT NULL AND NOT ({membership})",
            "out_of_range": "FALSE",
        }

    if rule_type == "numeric_range":
        min_val = rule_config.get("min")
        max_val = rule_config.get("max")
        invalid_values = as_list(
            parameter_values if rule_config.get("invalid_from_param") else rule_config.get("invalid_values")
        )
        invalid_expr = (
            f"{field} IS NOT NULL AND {field} IN ({', '.join(sql_literal(value) for value in invalid_values)})"
            if invalid_values
            else "FALSE"
        )
        bounds = []
        if min_val is not None:
            bounds.append(f"{field} >= {sql_literal(min_val)}")
        if max_val is not None:
            bounds.append(f"{field} <= {sql_literal(max_val)}")
        range_ok = " AND ".join(bounds) if bounds else "TRUE"
        return {
            "compliant": f"{field} IS NOT NULL AND NOT ({invalid_expr}) AND ({range_ok})",
            "invalid": invalid_expr,
            "out_of_range": f"{field} IS NOT NULL AND NOT ({invalid_expr}) AND NOT ({range_ok})",
        }

    if rule_type == "range_by_tech":
        min_val = rule_config.get("min", 1)
        max_4g = rule_config.get("max_4g")
        max_5g = rule_config.get("max_5g")
        if max_4g is None and max_5g is None:
            raise ValueError(f"{field_name} 的按制式范围规则缺少上界。")
        tech_expr = "COALESCE(NULLIF(tech_norm, ''), NULLIF(tech, ''), '')"
        upper_bound = (
            f"(CASE WHEN {tech_expr} IN ('5G', 'NR') THEN {sql_literal(max_5g)} ELSE {sql_literal(max_4g)} END)"
            if max_4g is not None and max_5g is not None
            else sql_literal(max_4g if max_4g is not None else max_5g)
        )
        overflow_values = as_list(
            parameter_values if rule_config.get("overflow_from_param") else rule_config.get("overflow_values")
        )
        invalid_expr = (
            f"{field} IS NOT NULL AND {field} IN ({', '.join(sql_literal(value) for value in overflow_values)})"
            if overflow_values
            else "FALSE"
        )
        range_ok = f"{field} >= {sql_literal(min_val)} AND {field} <= {upper_bound}"
        return {
            "compliant": f"{field} IS NOT NULL AND NOT ({invalid_expr}) AND ({range_ok})",
            "invalid": invalid_expr,
            "out_of_range": f"{field} IS NOT NULL AND NOT ({invalid_expr}) AND NOT ({range_ok})",
        }

    if rule_type == "bbox_pair":
        pair_field = sql_identifier(rule_config.get("pair_field", ""))
        bbox = parameter_values if isinstance(parameter_values, dict) else {}
        lon_min = bbox.get("lon_min", 73.0)
        lon_max = bbox.get("lon_max", 136.0)
        lat_min = bbox.get("lat_min", 3.0)
        lat_max = bbox.get("lat_max", 54.0)
        lon_field = field if "lon" in field_name else pair_field
        lat_field = field if "lat" in field_name else pair_field
        pair_ready = f"{field} IS NOT NULL AND {pair_field} IS NOT NULL"
        inside_bbox = (
            f"{lon_field} >= {sql_literal(lon_min)} AND {lon_field} <= {sql_literal(lon_max)} "
            f"AND {lat_field} >= {sql_literal(lat_min)} AND {lat_field} <= {sql_literal(lat_max)}"
        )
        return {
            "compliant": f"{pair_ready} AND ({inside_bbox})",
            "invalid": "FALSE",
            "out_of_range": f"{field} IS NOT NULL AND NOT ({pair_ready} AND ({inside_bbox}))",
        }

    raise ValueError(f"未知合规规则类型: {rule_type}")
