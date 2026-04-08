"""工作台快照构建函数。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workbench.base import fetch_all, first, scalar, to_json
from app.services.workbench.catalog import resolve_run_parameters
from app.services.workbench.step_metric_builders import compute_step_metrics


async def compute_layer_snapshot(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """从 pg_stat_user_tables 读取 pipeline 各层行数。"""
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
    rows = await fetch_all(
        db,
        """
        SELECT relname, n_live_tup::bigint AS row_count
        FROM pg_stat_user_tables
        WHERE schemaname = 'pipeline' AND relname = ANY(:tables)
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

async def compute_anomaly_stats(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    rows = await fetch_all(
        db,
        """
        SELECT 'BS' AS object_level, 'collision_suspect' AS anomaly_type,
               count(*) AS total_count, count(*) FILTER (WHERE is_collision_suspect=true) AS anomaly_count
        FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'severe_collision', count(*), count(*) FILTER (WHERE is_severe_collision=true) FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'gps_unstable', count(*), count(*) FILTER (WHERE is_gps_unstable=true) FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'bs_id_lt_256', count(*), count(*) FILTER (WHERE is_bs_id_lt_256=true) FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'multi_operator_shared', count(*), count(*) FILTER (WHERE is_multi_operator_shared=true) FROM pipeline.profile_bs
        UNION ALL
        SELECT 'BS', 'insufficient_sample', count(*), count(*) FILTER (WHERE is_insufficient_sample=true) FROM pipeline.profile_bs
        UNION ALL
        SELECT 'CELL', 'dynamic_cell', count(*), count(*) FILTER (WHERE is_dynamic_cell=true) FROM pipeline.profile_cell
        UNION ALL
        SELECT 'CELL', 'collision_suspect', count(*), count(*) FILTER (WHERE is_collision_suspect=true) FROM pipeline.profile_cell
        UNION ALL
        SELECT 'CELL', 'insufficient_sample', count(*), count(*) FILTER (WHERE is_insufficient_sample=true) FROM pipeline.profile_cell
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


def _step_params(parameters: dict[str, Any], step_id: str) -> dict[str, Any]:
    return parameters.get(step_id.replace("s", "step"), {})


async def compute_rule_hits(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """根据 run 绑定的参数集和 pipeline 数据计算各步骤规则命中统计。"""
    params = await resolve_run_parameters(db, run_id)
    step4 = _step_params(params, "s4")
    step30 = _step_params(params, "s30")
    step31 = _step_params(params, "s31")
    step35 = _step_params(params, "s35")
    step50 = _step_params(params, "s50")
    step51 = _step_params(params, "s51")
    step52 = _step_params(params, "s52")

    rows: list[dict[str, Any]] = []

    s4 = await first(
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
                    "key_params": to_json({"active_days_threshold": step4.get("active_days_threshold", 7)}),
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
                    "key_params": to_json(
                        {
                            "min_device_count": step4.get("min_device_count", 5),
                            "min_device_count_5g": step4.get("min_device_count_5g", 3),
                        }
                    ),
                    "dimension_key": "ALL",
                },
            ]
        )

    s30 = await first(
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
                    "key_params": to_json({"collision_p90_dist_m": step30.get("collision_p90_dist_m", 1500)}),
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
                    "key_params": to_json({"outlier_dist_m": step30.get("outlier_dist_m", 2500)}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s31 = await first(
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
                    "key_params": to_json({"drift_dist_m": step31.get("drift_dist_m", 1500)}),
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
                    "key_params": to_json({"drift_dist_m": step31.get("drift_dist_m", 1500)}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s33 = await first(
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
                    "key_params": to_json({}),
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
                    "key_params": to_json({}),
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
                    "key_params": to_json({}),
                    "dimension_key": "ALL",
                },
            ]
        )

    s35 = await first(
        db,
        """
        SELECT count(*) FILTER (WHERE is_dynamic_cell = true) AS dynamic_hit,
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
                "key_params": to_json(
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
        stats = await first(
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
                    "key_params": to_json({"min_rows": params_key.get("min_rows", 500)}),
                    "dimension_key": "ALL",
                }
            )

    return rows


GATE_DEFINITIONS: list[dict[str, Any]] = [
    {"gate_code": "G01", "gate_name": "原始记录非空", "severity": "critical", "sql": "SELECT count(*) FROM pipeline.raw_records", "op": ">", "threshold": 0},
    {"gate_code": "G02", "gate_name": "可信LAC产出", "severity": "critical", "sql": "SELECT count(*) FROM pipeline.dim_lac_trusted", "op": ">", "threshold": 0},
    {
        "gate_code": "G03",
        "gate_name": "合规过滤保留率 > 50%",
        "severity": "high",
        "sql": "SELECT count(*)::float / NULLIF((SELECT count(*) FROM pipeline.raw_records), 0) FROM pipeline.fact_filtered",
        "op": ">",
        "threshold": 0.5,
    },
    {"gate_code": "G04", "gate_name": "可信BS产出", "severity": "critical", "sql": "SELECT count(*) FROM pipeline.dim_bs_trusted", "op": ">", "threshold": 0},
    {
        "gate_code": "G05",
        "gate_name": "GPS修正覆盖率 > 80%",
        "severity": "high",
        "sql": "SELECT count(*) FILTER (WHERE gps_status_final != 'Not_Filled')::float / NULLIF(count(*), 0) FROM pipeline.fact_gps_corrected",
        "op": ">",
        "threshold": 0.8,
    },
    {
        "gate_code": "G06",
        "gate_name": "信号补齐率 > 70%",
        "severity": "high",
        "sql": "SELECT count(*) FILTER (WHERE signal_fill_source NOT IN ('none','none_filled'))::float / NULLIF(count(*), 0) FROM pipeline.fact_signal_filled",
        "op": ">",
        "threshold": 0.7,
    },
    {"gate_code": "G07", "gate_name": "最终明细非空", "severity": "critical", "sql": "SELECT count(*) FROM pipeline.fact_final", "op": ">", "threshold": 0},
    {
        "gate_code": "G08",
        "gate_name": "碰撞BS占比 < 15%",
        "severity": "medium",
        "sql": "SELECT count(*) FILTER (WHERE is_collision_suspect)::float / NULLIF(count(*), 0) FROM pipeline.profile_bs",
        "op": "<",
        "threshold": 0.15,
    },
    {
        "gate_code": "G09",
        "gate_name": "动态Cell占比 < 10%",
        "severity": "medium",
        "sql": "SELECT count(*) FILTER (WHERE is_dynamic_cell)::float / NULLIF(count(*), 0) FROM pipeline.profile_cell",
        "op": "<",
        "threshold": 0.10,
    },
    {"gate_code": "G10", "gate_name": "LAC画像产出", "severity": "high", "sql": "SELECT count(*) FROM pipeline.profile_lac", "op": ">", "threshold": 0},
]


async def compute_gate_results(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """根据 Gate 定义计算各门控是否通过。"""
    results = []
    for gate in GATE_DEFINITIONS:
        try:
            value = await scalar(db, gate["sql"])
            value = float(value or 0)
            op = gate["op"]
            threshold = gate["threshold"]
            if op == ">":
                passed = value > threshold
            elif op == "<":
                passed = value < threshold
            elif op == ">=":
                passed = value >= threshold
            else:
                passed = value == threshold

            results.append(
                {
                    "run_id": run_id,
                    "gate_code": gate["gate_code"],
                    "gate_name": gate["gate_name"],
                    "severity": gate["severity"],
                    "expected_rule": f"{op} {threshold}",
                    "actual_value": round(value, 6),
                    "pass_flag": passed,
                    "remark": "通过" if passed else "未通过",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "run_id": run_id,
                    "gate_code": gate["gate_code"],
                    "gate_name": gate["gate_name"],
                    "severity": gate["severity"],
                    "expected_rule": f"{gate['op']} {gate['threshold']}",
                    "actual_value": None,
                    "pass_flag": False,
                    "remark": f"计算失败: {exc}",
                }
            )
    return results
