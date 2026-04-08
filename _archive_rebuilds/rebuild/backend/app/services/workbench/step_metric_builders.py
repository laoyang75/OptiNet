"""步骤级指标快照构建。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workbench.base import fetch_all, first, metric_row, to_number


async def compute_step_metrics(db: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """对 pipeline 各层表执行聚合查询，生成步骤级指标。"""
    metrics: list[dict[str, Any]] = []

    s0 = await first(
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
                metric_row(run_id, "s0", "total", "原始记录数", value_num=int(s0["total"]), unit="行"),
                metric_row(run_id, "s0", "lac_rows", "LAC来源记录", value_num=int(s0["lac_rows"]), unit="行"),
                metric_row(run_id, "s0", "gps_rows", "GPS来源记录", value_num=int(s0["gps_rows"]), unit="行"),
            ]
        )

    s4 = await first(
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
                metric_row(run_id, "s4", "trusted_lac_cnt", "可信LAC数", value_num=int(s4["trusted_lac_cnt"]), unit="个"),
                metric_row(run_id, "s4", "cmcc_cnt", "移动LAC数", value_num=int(s4["cmcc_cnt"]), unit="个"),
                metric_row(run_id, "s4", "cucc_cnt", "联通LAC数", value_num=int(s4["cucc_cnt"]), unit="个"),
                metric_row(run_id, "s4", "ctcc_cnt", "电信LAC数", value_num=int(s4["ctcc_cnt"]), unit="个"),
            ]
        )

    s6 = await first(
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
                metric_row(run_id, "s6", "output_rows", "合规输出行数", value_num=int(s6["output_rows"]), unit="行"),
                metric_row(run_id, "s6", "keep_trusted", "保留可信LAC", value_num=int(s6["keep_trusted"]), unit="行"),
                metric_row(run_id, "s6", "multi_lac_resolved", "多LAC修正", value_num=int(s6["multi_lac_resolved"]), unit="行"),
                metric_row(run_id, "s6", "lac_backfilled", "LAC回填", value_num=int(s6["lac_backfilled"]), unit="行"),
            ]
        )

    s30 = await first(
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
                metric_row(run_id, "s30", "total_bs", "可信BS数", value_num=int(s30["total_bs"]), unit="个"),
                metric_row(run_id, "s30", "usable", "可用BS", value_num=int(s30["usable"]), unit="个"),
                metric_row(run_id, "s30", "risk", "风险BS", value_num=int(s30["risk"]), unit="个"),
                metric_row(run_id, "s30", "unusable", "不可用BS", value_num=int(s30["unusable"]), unit="个"),
                metric_row(run_id, "s30", "collision_suspect", "碰撞疑似BS", value_num=int(s30["collision_suspect"]), unit="个"),
            ]
        )

    s31 = await first(
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
                metric_row(run_id, "s31", "total", "GPS修正输入", value_num=int(s31["total"]), unit="行"),
                metric_row(run_id, "s31", "verified", "原生可用GPS", value_num=int(s31["verified"]), unit="行"),
                metric_row(run_id, "s31", "missing", "GPS缺失", value_num=int(s31["missing"]), unit="行"),
                metric_row(run_id, "s31", "drift", "GPS漂移", value_num=int(s31["drift"]), unit="行"),
                metric_row(run_id, "s31", "filled_from_bs", "BS回填成功", value_num=int(s31["filled_from_bs"]), unit="行"),
                metric_row(run_id, "s31", "not_filled", "无法回填", value_num=int(s31["not_filled"]), unit="行"),
            ]
        )

    gps_distribution = await fetch_all(
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
        metrics.append(metric_row(run_id, "s31", "gps_status_distribution", "GPS状态分布", value_json=gps_distribution))

    s33 = await first(
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
                metric_row(run_id, "s33", "total", "信号补齐输入", value_num=int(s33["total"]), unit="行"),
                metric_row(run_id, "s33", "by_cell", "Cell补齐", value_num=int(s33["by_cell"]), unit="行"),
                metric_row(run_id, "s33", "by_bs", "BS补齐", value_num=int(s33["by_bs"]), unit="行"),
                metric_row(run_id, "s33", "none_filled", "未补齐", value_num=int(s33["none_filled"]), unit="行"),
                metric_row(run_id, "s33", "avg_missing_before", "补齐前平均缺失字段数", value_num=to_number(s33["avg_missing_before"]), unit="个"),
                metric_row(run_id, "s33", "avg_missing_after", "补齐后平均缺失字段数", value_num=to_number(s33["avg_missing_after"]), unit="个"),
            ]
        )

    signal_distribution = await fetch_all(
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
        metrics.append(metric_row(run_id, "s33", "signal_fill_distribution", "信号补齐分布", value_json=signal_distribution))

    s41 = await first(
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
                metric_row(run_id, "s41", "total", "最终明细行数", value_num=int(s41["total"]), unit="行"),
                metric_row(run_id, "s41", "gps_resolved", "GPS已解决", value_num=int(s41["gps_resolved"]), unit="行"),
                metric_row(run_id, "s41", "signal_filled", "信号有补齐来源", value_num=int(s41["signal_filled"]), unit="行"),
                metric_row(run_id, "s41", "severe_collision", "严重碰撞行数", value_num=int(s41["severe_collision"]), unit="行"),
                metric_row(run_id, "s41", "dynamic_cell", "动态Cell行数", value_num=int(s41["dynamic_cell"]), unit="行"),
            ]
        )

    operator_tech_distribution = await fetch_all(
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
        metrics.append(metric_row(run_id, "s41", "operator_tech_distribution", "运营商制式分布", value_json=operator_tech_distribution))

    s50 = await first(db, "SELECT count(*) AS lac_profiles FROM pipeline.profile_lac")
    if s50:
        metrics.append(metric_row(run_id, "s50", "lac_profiles", "LAC画像数", value_num=int(s50["lac_profiles"]), unit="个"))

    s51 = await first(
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
                metric_row(run_id, "s51", "bs_profiles", "BS画像数", value_num=int(s51["bs_profiles"]), unit="个"),
                metric_row(run_id, "s51", "bs_collision", "BS碰撞样本", value_num=int(s51["bs_collision"]), unit="个"),
            ]
        )

    s52 = await first(
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
                metric_row(run_id, "s52", "cell_profiles", "Cell画像数", value_num=int(s52["cell_profiles"]), unit="个"),
                metric_row(run_id, "s52", "cell_dynamic", "动态Cell样本", value_num=int(s52["cell_dynamic"]), unit="个"),
            ]
        )

    return metrics
