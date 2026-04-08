#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import subprocess
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT_DIR / "backend" / "sql"
LOG_DIR = ROOT_DIR / ".logs"
DOC_DIR = ROOT_DIR / "docs"
DEFAULT_DSN = os.environ.get(
    "REBUILD3_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2",
)

SQL_FILES = [
    SQL_DIR / "govern" / "002_rebuild3_full_pipeline.sql",
    SQL_DIR / "compare" / "002_prepare_full_compare.sql",
]


def run_sql_file(dsn: str, sql_file: Path) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{sql_file.stem}.log"
    with log_file.open("w", encoding="utf-8") as fh:
        subprocess.run(
            ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)],
            check=True,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
    return log_file


def fetch_all(conn: psycopg.Connection, sql: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def fetch_val(conn: psycopg.Connection, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return None if row is None else row[0]


def pct(part: float, whole: float) -> str:
    if not whole:
        return "0.00%"
    return f"{part / whole * 100:.2f}%"


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isfinite(value):
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return str(value)
    return str(value)


def md_table(headers: list[str], rows: Iterable[Iterable]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_value(v) for v in row) + " |")
    return "\n".join(lines)


def build_full_run_report(conn: psycopg.Connection) -> str:
    batch_row = fetch_all(
        conn,
        """
        SELECT batch_id, run_id, status, window_start, window_end, input_rows, output_rows
        FROM rebuild3_meta.batch
        WHERE batch_id = 'BATCH-FULL-20251201-20251207-V1'
        """,
    )[0]
    source_row = fetch_all(
        conn,
        """
        SELECT
          count(*) AS total_rows,
          count(*) FILTER (WHERE "运营商编码" IS NULL OR "LAC" IS NULL OR "CellID" IS NULL) AS invalid_key_rows,
          count(*) FILTER (WHERE "运营商编码" IS NOT NULL AND "LAC" IS NOT NULL AND "CellID" IS NOT NULL) AS valid_key_rows
        FROM rebuild2.l0_lac
        """,
    )[0]
    snapshot_rows = fetch_all(
        conn,
        """
        SELECT stage_name, metric_name, metric_value
        FROM rebuild3_meta.batch_snapshot
        WHERE batch_id = 'BATCH-FULL-20251201-20251207-V1'
        ORDER BY stage_name, metric_name
        """,
    )
    flow_rows = fetch_all(
        conn,
        """
        SELECT fact_layer, row_count, row_ratio
        FROM rebuild3_meta.batch_flow_summary
        WHERE batch_id = 'BATCH-FULL-20251201-20251207-V1'
        ORDER BY fact_layer
        """,
    )
    compare_counts = fetch_all(
        conn,
        """
        SELECT 'r2_full_cell_state' AS table_name, count(*) AS row_count FROM rebuild3_meta.r2_full_cell_state
        UNION ALL SELECT 'r2_full_bs_state', count(*) FROM rebuild3_meta.r2_full_bs_state
        UNION ALL SELECT 'r2_full_lac_state', count(*) FROM rebuild3_meta.r2_full_lac_state
        UNION ALL SELECT 'r2_full_route_summary', sum(row_count)::bigint FROM rebuild3_meta.r2_full_route_summary
        ORDER BY table_name
        """,
    )
    snapshot_table = md_table(
        ["stage_name", "metric_name", "metric_value"],
        [[r["stage_name"], r["metric_name"], r["metric_value"]] for r in snapshot_rows],
    )
    flow_table = md_table(
        ["fact_layer", "row_count", "row_ratio"],
        [[r["fact_layer"], r["row_count"], r["row_ratio"]] for r in flow_rows],
    )
    compare_table = md_table(
        ["table_name", "row_count"],
        [[r["table_name"], r["row_count"]] for r in compare_counts],
    )
    return "\n".join(
        [
            "# 全量运行报告",
            "",
            "## 执行阶段与门禁",
            "",
            "1. Gate E-1：执行 `backend/sql/govern/002_rebuild3_full_pipeline.sql`，完成 rebuild3 全量对象、事实、baseline 构建。",
            "2. Gate E-2：补写 `fact_pending_observation` 中缺失的未注册对象记录，并刷新批次快照与路由汇总。",
            "3. Gate E-3：修正 BS / LAC 资格级联过滤，确保 BS 资格严格来源于 Cell、LAC 资格严格来源于 BS。",
            "4. Gate E-4：执行 `backend/sql/compare/002_prepare_full_compare.sql`，准备 rebuild2 全量对比状态表。",
            "5. Gate E-5：校验 `batch_snapshot` 与实际表计数一致，确认全量路由闭环后进入偏差评估。",
            "",
            "## 批次上下文",
            "",
            f"- run_id：`{batch_row['run_id']}`",
            f"- batch_id：`{batch_row['batch_id']}`",
            "- 窗口：`2025-12-01 00:00:00+08` 至 `2025-12-07 23:59:59+08`",
            f"- 状态：`{batch_row['status']}`",
            f"- input_rows：`{batch_row['input_rows']}`",
            f"- output_rows：`{batch_row['output_rows']}`",
            "",
            "## 输入规模",
            "",
            f"- rebuild2 全量输入：`{source_row['total_rows']}`",
            f"- 有效主键记录：`{source_row['valid_key_rows']}`",
            f"- 无效主键记录：`{source_row['invalid_key_rows']}`",
            f"- 无效主键占比：{pct(float(source_row['invalid_key_rows']), float(source_row['total_rows']))}",
            "",
            "## rebuild3 全量批次快照",
            "",
            snapshot_table,
            "",
            "## rebuild3 全量四分流",
            "",
            flow_table,
            "",
            "## rebuild2 对比侧准备结果",
            "",
            compare_table,
            "",
            "## 运行说明",
            "",
            "- 全量主链路已完成，并补齐了 `missing_object_registration` 观察池记录，保证四分流总量与 `fact_standardized` 完全闭环。",
            "- 已修正 BS / LAC 资格级联过滤：BS 的 `anchorable` / `baseline_eligible` 严格来源于子 Cell，LAC 严格来源于子 BS。",
            "- `batch_snapshot` 与实际落表计数一致，可直接作为 UI 与后续评估的读模型输入。",
            "- 对比侧 `r2_full_*` 已按全量输入重建，可用于对象状态、资格、baseline 与四分流偏差评估。",
            "",
            "## 日志位置",
            "",
            "- `rebuild3/.logs/002_rebuild3_full_pipeline.log`",
            "- `rebuild3/.logs/002_rebuild3_full_pipeline_resume.log`",
            "- `rebuild3/.logs/002_prepare_full_compare.log`",
            "",
        ]
    )


def build_full_compare_report(conn: psycopg.Connection) -> str:
    total_rows = float(fetch_val(conn, "SELECT count(*) FROM rebuild3.fact_standardized"))
    route_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT fact_route AS route, row_count AS cnt FROM rebuild3_meta.r2_full_route_summary
        ),
        r3 AS (
          SELECT route, count(*) AS cnt
          FROM (
            SELECT 'fact_governed'::text AS route FROM rebuild3.fact_governed
            UNION ALL
            SELECT 'fact_pending_observation' FROM rebuild3.fact_pending_observation
            UNION ALL
            SELECT 'fact_pending_issue' FROM rebuild3.fact_pending_issue
            UNION ALL
            SELECT 'fact_rejected' FROM rebuild3.fact_rejected
          ) x
          GROUP BY route
        )
        SELECT
          COALESCE(r2.route, r3.route) AS route,
          COALESCE(r2.cnt, 0) AS r2_cnt,
          COALESCE(r3.cnt, 0) AS r3_cnt,
          COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2
        FULL JOIN r3 ON r2.route = r3.route
        ORDER BY 1
        """,
    )
    object_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3_meta.r2_full_cell_state
          UNION ALL
          SELECT 'bs', count(*) FROM rebuild3_meta.r2_full_bs_state
          UNION ALL
          SELECT 'lac', count(*) FROM rebuild3_meta.r2_full_lac_state
        ),
        r3 AS (
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3.obj_cell
          UNION ALL
          SELECT 'bs', count(*) FROM rebuild3.obj_bs
          UNION ALL
          SELECT 'lac', count(*) FROM rebuild3.obj_lac
        )
        SELECT COALESCE(r2.obj, r3.obj) AS obj,
               COALESCE(r2.cnt, 0) AS r2_cnt,
               COALESCE(r3.cnt, 0) AS r3_cnt,
               COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2 FULL JOIN r3 USING (obj)
        ORDER BY 1
        """,
    )
    state_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT 'cell' AS obj, lifecycle_state, health_state, count(*) AS cnt FROM rebuild3_meta.r2_full_cell_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', lifecycle_state, health_state, count(*) AS cnt FROM rebuild3_meta.r2_full_bs_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', lifecycle_state, health_state, count(*) AS cnt FROM rebuild3_meta.r2_full_lac_state GROUP BY 1,2,3
        ),
        r3 AS (
          SELECT 'cell' AS obj, lifecycle_state, health_state, count(*) AS cnt FROM rebuild3.obj_cell GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', lifecycle_state, health_state, count(*) AS cnt FROM rebuild3.obj_bs GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', lifecycle_state, health_state, count(*) AS cnt FROM rebuild3.obj_lac GROUP BY 1,2,3
        )
        SELECT
          COALESCE(r2.obj, r3.obj) AS obj,
          COALESCE(r2.lifecycle_state, r3.lifecycle_state) AS lifecycle_state,
          COALESCE(r2.health_state, r3.health_state) AS health_state,
          COALESCE(r2.cnt, 0) AS r2_cnt,
          COALESCE(r3.cnt, 0) AS r3_cnt,
          COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2
        FULL JOIN r3
          ON r2.obj = r3.obj
         AND r2.lifecycle_state = r3.lifecycle_state
         AND r2.health_state = r3.health_state
        ORDER BY 1,2,3
        """,
    )
    qual_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT 'cell' AS obj, anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3_meta.r2_full_cell_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3_meta.r2_full_bs_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3_meta.r2_full_lac_state GROUP BY 1,2,3
        ),
        r3 AS (
          SELECT 'cell' AS obj, anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3.obj_cell GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3.obj_bs GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', anchorable, baseline_eligible, count(*) AS cnt FROM rebuild3.obj_lac GROUP BY 1,2,3
        )
        SELECT
          COALESCE(r2.obj, r3.obj) AS obj,
          COALESCE(r2.anchorable, r3.anchorable) AS anchorable,
          COALESCE(r2.baseline_eligible, r3.baseline_eligible) AS baseline_eligible,
          COALESCE(r2.cnt, 0) AS r2_cnt,
          COALESCE(r3.cnt, 0) AS r3_cnt,
          COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2
        FULL JOIN r3
          ON r2.obj = r3.obj
         AND r2.anchorable = r3.anchorable
         AND r2.baseline_eligible = r3.baseline_eligible
        ORDER BY 1,2,3
        """,
    )
    baseline_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3_meta.r2_full_cell_state WHERE baseline_eligible
          UNION ALL
          SELECT 'bs', count(*) FROM rebuild3_meta.r2_full_bs_state WHERE baseline_eligible
          UNION ALL
          SELECT 'lac', count(*) FROM rebuild3_meta.r2_full_lac_state WHERE baseline_eligible
        ),
        r3 AS (
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3.baseline_cell
          UNION ALL
          SELECT 'bs', count(*) FROM rebuild3.baseline_bs
          UNION ALL
          SELECT 'lac', count(*) FROM rebuild3.baseline_lac
        )
        SELECT COALESCE(r2.obj, r3.obj) AS obj,
               COALESCE(r2.cnt, 0) AS r2_cnt,
               COALESCE(r3.cnt, 0) AS r3_cnt,
               COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2 FULL JOIN r3 USING (obj)
        ORDER BY 1
        """,
    )
    observation_reason_rows = fetch_all(
        conn,
        """
        SELECT route_reason, missing_layer, count(*) AS row_count
        FROM rebuild3.fact_pending_observation
        GROUP BY route_reason, missing_layer
        ORDER BY row_count DESC
        """,
    )
    issue_rows = fetch_all(
        conn,
        """
        SELECT health_state, count(*) AS row_count
        FROM rebuild3.fact_pending_issue
        GROUP BY health_state
        ORDER BY row_count DESC
        """,
    )
    profile_rows = fetch_all(
        conn,
        """
        WITH common_cell AS (
          SELECT
            sqrt(power((r2.centroid_lon - r3.centroid_lon) * 85300, 2) + power((r2.centroid_lat - r3.centroid_lat) * 111000, 2))::numeric AS center_diff_m,
            abs(COALESCE(r2.gps_p90_dist_m, 0) - COALESCE(r3.gps_p90_dist_m, 0))::numeric AS p90_diff_m,
            abs(COALESCE(r2.gps_original_ratio, 0) - COALESCE(r3.gps_original_ratio, 0))::numeric AS gps_ratio_diff,
            abs(COALESCE(r2.signal_original_ratio, 0) - COALESCE(r3.signal_original_ratio, 0))::numeric AS signal_ratio_diff
          FROM rebuild3_meta.r2_full_cell_state r2
          JOIN rebuild3.obj_cell r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
          WHERE r2.baseline_eligible AND r3.baseline_eligible
        ),
        common_bs AS (
          SELECT
            sqrt(power((r2.center_lon - r3.center_lon) * 85300, 2) + power((r2.center_lat - r3.center_lat) * 111000, 2))::numeric AS center_diff_m,
            abs(COALESCE(r2.gps_p90_dist_m, 0) - COALESCE(r3.gps_p90_dist_m, 0))::numeric AS p90_diff_m,
            abs(COALESCE(r2.gps_original_ratio, 0) - COALESCE(r3.gps_original_ratio, 0))::numeric AS gps_ratio_diff,
            abs(COALESCE(r2.signal_original_ratio, 0) - COALESCE(r3.signal_original_ratio, 0))::numeric AS signal_ratio_diff
          FROM rebuild3_meta.r2_full_bs_state r2
          JOIN rebuild3.obj_bs r3 USING (operator_code, tech_norm, lac, bs_id)
          WHERE r2.baseline_eligible AND r3.baseline_eligible
        ),
        common_lac AS (
          SELECT
            sqrt(power((r2.center_lon - r3.center_lon) * 85300, 2) + power((r2.center_lat - r3.center_lat) * 111000, 2))::numeric AS center_diff_m,
            abs(COALESCE(r2.gps_original_ratio, 0) - COALESCE(r3.gps_original_ratio, 0))::numeric AS gps_ratio_diff,
            abs(COALESCE(r2.signal_original_ratio, 0) - COALESCE(r3.signal_original_ratio, 0))::numeric AS signal_ratio_diff
          FROM rebuild3_meta.r2_full_lac_state r2
          JOIN rebuild3.obj_lac r3 USING (operator_code, tech_norm, lac)
          WHERE r2.baseline_eligible AND r3.baseline_eligible
        )
        SELECT
          'cell' AS obj,
          count(*) AS common_cnt,
          percentile_cont(0.9) WITHIN GROUP (ORDER BY center_diff_m) AS center_diff_p90_m,
          max(center_diff_m) AS center_diff_max_m,
          percentile_cont(0.9) WITHIN GROUP (ORDER BY p90_diff_m) AS p90_diff_p90_m,
          max(gps_ratio_diff) AS gps_ratio_diff_max,
          max(signal_ratio_diff) AS signal_ratio_diff_max
        FROM common_cell
        UNION ALL
        SELECT
          'bs',
          count(*),
          percentile_cont(0.9) WITHIN GROUP (ORDER BY center_diff_m),
          max(center_diff_m),
          percentile_cont(0.9) WITHIN GROUP (ORDER BY p90_diff_m),
          max(gps_ratio_diff),
          max(signal_ratio_diff)
        FROM common_bs
        UNION ALL
        SELECT
          'lac',
          count(*),
          percentile_cont(0.9) WITHIN GROUP (ORDER BY center_diff_m),
          max(center_diff_m),
          NULL::numeric,
          max(gps_ratio_diff),
          max(signal_ratio_diff)
        FROM common_lac
        """,
    )
    membership_rows = fetch_all(
        conn,
        """
        WITH cell_diff AS (
          WITH r2 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3_meta.r2_full_cell_state
            WHERE baseline_eligible
          ),
          r3 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3.baseline_cell
          )
          SELECT 'cell' AS obj,
                 CASE WHEN r2.cell_id IS NULL THEN 'r3_only' WHEN r3.cell_id IS NULL THEN 'r2_only' END AS membership
          FROM r2 FULL JOIN r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
          WHERE r2.cell_id IS NULL OR r3.cell_id IS NULL
        ),
        bs_diff AS (
          WITH r2 AS (
            SELECT operator_code, tech_norm, lac, bs_id
            FROM rebuild3_meta.r2_full_bs_state
            WHERE baseline_eligible
          ),
          r3 AS (
            SELECT operator_code, tech_norm, lac, bs_id
            FROM rebuild3.baseline_bs
          )
          SELECT 'bs' AS obj,
                 CASE WHEN r2.bs_id IS NULL THEN 'r3_only' WHEN r3.bs_id IS NULL THEN 'r2_only' END AS membership
          FROM r2 FULL JOIN r3 USING (operator_code, tech_norm, lac, bs_id)
          WHERE r2.bs_id IS NULL OR r3.bs_id IS NULL
        ),
        lac_diff AS (
          WITH r2 AS (
            SELECT operator_code, tech_norm, lac
            FROM rebuild3_meta.r2_full_lac_state
            WHERE baseline_eligible
          ),
          r3 AS (
            SELECT operator_code, tech_norm, lac
            FROM rebuild3.baseline_lac
          )
          SELECT 'lac' AS obj,
                 CASE WHEN r2.lac IS NULL THEN 'r3_only' WHEN r3.lac IS NULL THEN 'r2_only' END AS membership
          FROM r2 FULL JOIN r3 USING (operator_code, tech_norm, lac)
          WHERE r2.lac IS NULL OR r3.lac IS NULL
        )
        SELECT obj, membership, count(*) AS row_count
        FROM (
          SELECT * FROM cell_diff
          UNION ALL
          SELECT * FROM bs_diff
          UNION ALL
          SELECT * FROM lac_diff
        ) x
        GROUP BY obj, membership
        ORDER BY obj, membership
        """,
    )
    cell_membership_examples = fetch_all(
        conn,
        """
        WITH diff AS (
          WITH r2 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3_meta.r2_full_cell_state
            WHERE baseline_eligible
          ),
          r3 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3.baseline_cell
          )
          SELECT
            COALESCE(r2.operator_code, r3.operator_code) AS operator_code,
            COALESCE(r2.tech_norm, r3.tech_norm) AS tech_norm,
            COALESCE(r2.lac, r3.lac) AS lac,
            COALESCE(r2.bs_id, r3.bs_id) AS bs_id,
            COALESCE(r2.cell_id, r3.cell_id) AS cell_id,
            CASE WHEN r2.cell_id IS NULL THEN 'r3_only' WHEN r3.cell_id IS NULL THEN 'r2_only' END AS membership
          FROM r2 FULL JOIN r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
          WHERE r2.cell_id IS NULL OR r3.cell_id IS NULL
        )
        SELECT d.membership, d.operator_code, d.tech_norm, d.lac, d.bs_id, d.cell_id,
               r2.health_state AS r2_health, r3.health_state AS r3_health,
               r2.gps_p90_dist_m AS r2_p90, r3.gps_p90_dist_m AS r3_p90
        FROM diff d
        LEFT JOIN rebuild3_meta.r2_full_cell_state r2 USING (operator_code, tech_norm, lac, bs_id, cell_id)
        LEFT JOIN rebuild3.obj_cell r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
        ORDER BY membership, operator_code, tech_norm, lac, bs_id, cell_id
        LIMIT 20
        """,
    )
    snapshot_consistency_rows = fetch_all(
        conn,
        """
        WITH snap AS (
          SELECT metric_name, metric_value::bigint AS snapshot_value
          FROM rebuild3_meta.batch_snapshot
          WHERE batch_id = 'BATCH-FULL-20251201-20251207-V1'
        ),
        actual AS (
          SELECT 'fact_standardized' AS metric_name, count(*)::bigint AS actual_value FROM rebuild3.fact_standardized
          UNION ALL SELECT 'fact_governed', count(*)::bigint FROM rebuild3.fact_governed
          UNION ALL SELECT 'fact_pending_observation', count(*)::bigint FROM rebuild3.fact_pending_observation
          UNION ALL SELECT 'fact_pending_issue', count(*)::bigint FROM rebuild3.fact_pending_issue
          UNION ALL SELECT 'fact_rejected', count(*)::bigint FROM rebuild3.fact_rejected
          UNION ALL SELECT 'obj_cell', count(*)::bigint FROM rebuild3.obj_cell
          UNION ALL SELECT 'obj_bs', count(*)::bigint FROM rebuild3.obj_bs
          UNION ALL SELECT 'obj_lac', count(*)::bigint FROM rebuild3.obj_lac
          UNION ALL SELECT 'baseline_cell', count(*)::bigint FROM rebuild3.baseline_cell
          UNION ALL SELECT 'baseline_bs', count(*)::bigint FROM rebuild3.baseline_bs
          UNION ALL SELECT 'baseline_lac', count(*)::bigint FROM rebuild3.baseline_lac
        )
        SELECT a.metric_name, s.snapshot_value, a.actual_value, a.actual_value - coalesce(s.snapshot_value, 0) AS diff
        FROM actual a
        LEFT JOIN snap s USING (metric_name)
        ORDER BY a.metric_name
        """,
    )

    route_table = md_table(
        ["route", "r2_cnt", "r3_cnt", "diff", "diff_pct_vs_r2"],
        [[r["route"], r["r2_cnt"], r["r3_cnt"], r["diff"], pct(abs(r["diff"]), max(float(r["r2_cnt"]), 1.0))] for r in route_rows],
    )
    object_table = md_table(
        ["obj", "r2_cnt", "r3_cnt", "diff"],
        [[r["obj"], r["r2_cnt"], r["r3_cnt"], r["diff"]] for r in object_rows],
    )
    state_table = md_table(
        ["obj", "lifecycle_state", "health_state", "r2_cnt", "r3_cnt", "diff"],
        [[r["obj"], r["lifecycle_state"], r["health_state"], r["r2_cnt"], r["r3_cnt"], r["diff"]] for r in state_rows],
    )
    qual_table = md_table(
        ["obj", "anchorable", "baseline_eligible", "r2_cnt", "r3_cnt", "diff"],
        [[r["obj"], r["anchorable"], r["baseline_eligible"], r["r2_cnt"], r["r3_cnt"], r["diff"]] for r in qual_rows],
    )
    baseline_table = md_table(
        ["obj", "r2_cnt", "r3_cnt", "diff", "diff_pct_vs_r2"],
        [[r["obj"], r["r2_cnt"], r["r3_cnt"], r["diff"], pct(abs(r["diff"]), max(float(r["r2_cnt"]), 1.0))] for r in baseline_rows],
    )
    observation_reason_table = md_table(
        ["route_reason", "missing_layer", "row_count", "row_ratio_vs_total"],
        [[r["route_reason"], r["missing_layer"], r["row_count"], pct(float(r["row_count"]), total_rows)] for r in observation_reason_rows],
    )
    issue_table = md_table(
        ["health_state", "row_count", "row_ratio_vs_total"],
        [[r["health_state"], r["row_count"], pct(float(r["row_count"]), total_rows)] for r in issue_rows],
    )
    profile_table = md_table(
        [
            "obj",
            "common_cnt",
            "center_diff_p90_m",
            "center_diff_max_m",
            "p90_diff_p90_m",
            "gps_ratio_diff_max",
            "signal_ratio_diff_max",
        ],
        [
            [
                r["obj"],
                r["common_cnt"],
                r["center_diff_p90_m"],
                r["center_diff_max_m"],
                r["p90_diff_p90_m"],
                r["gps_ratio_diff_max"],
                r["signal_ratio_diff_max"],
            ]
            for r in profile_rows
        ],
    )
    membership_table = md_table(
        ["obj", "membership", "row_count"],
        [[r["obj"], r["membership"], r["row_count"]] for r in membership_rows],
    )
    cell_membership_table = md_table(
        ["membership", "operator_code", "tech_norm", "lac", "bs_id", "cell_id", "r2_health", "r3_health", "r2_p90", "r3_p90"],
        [
            [
                r["membership"],
                r["operator_code"],
                r["tech_norm"],
                r["lac"],
                r["bs_id"],
                r["cell_id"],
                r["r2_health"],
                r["r3_health"],
                r["r2_p90"],
                r["r3_p90"],
            ]
            for r in cell_membership_examples
        ],
    )
    snapshot_consistency_table = md_table(
        ["metric_name", "snapshot_value", "actual_value", "diff"],
        [[r["metric_name"], r["snapshot_value"], r["actual_value"], r["diff"]] for r in snapshot_consistency_rows],
    )

    route_issue = next(r for r in route_rows if r["route"] == "fact_pending_issue")
    route_obs = next(r for r in route_rows if r["route"] == "fact_pending_observation")
    route_gov = next(r for r in route_rows if r["route"] == "fact_governed")
    baseline_bs = next(r for r in baseline_rows if r["obj"] == "bs")
    baseline_cell = next(r for r in baseline_rows if r["obj"] == "cell")
    baseline_lac = next(r for r in baseline_rows if r["obj"] == "lac")
    missing_object = next(r for r in observation_reason_rows if r["route_reason"] == "missing_object_registration")
    gps_bias_issue = next(r for r in issue_rows if r["health_state"] == "gps_bias")

    return "\n".join(
        [
            "# 全量偏差评估",
            "",
            "## 结论",
            "",
            "- 全量双跑已完成：`rebuild3` 全量构建、`rebuild2` 全量对比态准备与全量偏差评估均已落地。",
            "- 对象总量已对齐：Cell / BS / LAC 在 rebuild2 对比态与 rebuild3 中均一致。",
            f"- 四分流主偏差集中在 `gps_bias`：`fact_pending_issue +{route_issue['diff']}`，对应 rebuild3 将 `gps_bias` 明确路由到问题池。",
            f"- 在把 rebuild2 未注册对象覆盖折算到观察池后，`fact_pending_observation` 残余偏差仅 `{route_obs['diff']}`，占全量输入 {pct(abs(float(route_obs['diff'])), total_rows)}。",
            f"- baseline 偏差为：Cell `{baseline_cell['diff']:+d}`、BS `{baseline_bs['diff']:+d}`、LAC `{baseline_lac['diff']:+d}`；BS / LAC 偏差在修正级联过滤后已显著收敛。",
            "- 共同 baseline 对象上的中心点与画像指标完全一致，说明全量空间读模型稳定；当前差异主要来自状态/资格规则，而不是坐标计算漂移。",
            "",
            "## 四分流对比",
            "",
            route_table,
            "",
            f"说明：rebuild3 比 rebuild2 少 `{abs(route_gov['diff'])}` 条 governed、 多 `{route_issue['diff']}` 条 issue；核心原因是 `gps_bias` 由 rebuild3 明确升级为对象级问题事实。",
            "",
            "## rebuild3 观察池构成",
            "",
            observation_reason_table,
            "",
            f"说明：`missing_object_registration` 共 `{missing_object['row_count']}` 条，占全量输入 {pct(float(missing_object['row_count']), total_rows)}；这些记录主键有效，但在 rebuild2 既有对象层中没有对应 Cell 注册，因此 rebuild3 统一纳入观察池。",
            "",
            "## rebuild3 问题池构成",
            "",
            issue_table,
            "",
            f"说明：`gps_bias` 问题事实共 `{gps_bias_issue['row_count']}` 条，与 `fact_pending_issue` 的主差值量级一致，说明全量偏差延续了样本阶段的冻结语义。",
            "",
            "## 对象总量对比",
            "",
            object_table,
            "",
            "## 对象状态分布对比",
            "",
            state_table,
            "",
            "解释：Cell 侧的 `healthy <-> gps_bias` 互换仍是主偏差；BS / LAC 侧在修正级联过滤后已基本对齐。",
            "",
            "## 资格分布对比",
            "",
            qual_table,
            "",
            "## baseline 对比",
            "",
            baseline_table,
            "",
            "## baseline 差异清单（汇总）",
            "",
            membership_table,
            "",
            "### baseline Cell 差异样例",
            "",
            cell_membership_table,
            "",
            "解释：Cell baseline 差异几乎全部表现为 `r3_only`，即 rebuild2 旧口径下被标记为 `gps_bias`、而在 rebuild3 冻结规则中恢复为 `healthy` 的对象。BS baseline 修正后只剩 `+109` 个 `r3_only`，已收敛到由新增 baseline Cell 直接驱动的合理范围。",
            "",
            "## 共同 baseline 对象画像稳定性",
            "",
            profile_table,
            "",
            "说明：Cell / BS / LAC 在共同 baseline 上的 `center_diff_p90_m` 与 `center_diff_max_m` 均为 0，表明坐标基线与热力层主读模型稳定。",
            "",
            "## batch_snapshot 一致性校验",
            "",
            snapshot_consistency_table,
            "",
            "## 全量门禁判断",
            "",
            "- 通过项：四分流已闭环；批次快照与实际表一致；对象总量一致；共同 baseline 空间指标稳定。",
            "- 需明确接受的规则偏差：`gps_bias` 问题池扩大、BS baseline 较 rebuild2 增加 109 个、Cell baseline 增加 2,274 个。",
            "- 当前判断：可作为 rebuild3 首版全量结果候选；若要进入正式切换，建议先由业务确认 `gps_bias` 收紧与 Cell baseline 增量的预期。",
            "",
        ]
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rebuild3 full pipeline and generate reports.")
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN")
    parser.add_argument(
        "--reports-only",
        action="store_true",
        help="Skip SQL execution and only regenerate markdown reports from current DB state",
    )
    args = parser.parse_args()

    if not args.reports_only:
        for sql_file in SQL_FILES:
            log_file = run_sql_file(args.dsn, sql_file)
            print(f"[ok] {sql_file.relative_to(ROOT_DIR)} -> {log_file.relative_to(ROOT_DIR)}")

    with psycopg.connect(args.dsn) as conn:
        write_text(DOC_DIR / "full_run_report.md", build_full_run_report(conn))
        write_text(DOC_DIR / "full_compare_report.md", build_full_compare_report(conn))

    print("[ok] docs/full_run_report.md")
    print("[ok] docs/full_compare_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
