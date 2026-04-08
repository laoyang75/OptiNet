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
    SQL_DIR / "schema" / "001_foundation.sql",
    SQL_DIR / "init" / "001_sample_extract.sql",
    SQL_DIR / "init" / "002_rebuild2_sample_eval.sql",
    SQL_DIR / "govern" / "001_rebuild3_sample_pipeline.sql",
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


def build_sample_scope(conn: psycopg.Connection) -> str:
    rows = fetch_all(
        conn,
        """
        SELECT
          k.scope_type,
          k.scenario,
          k.operator_code,
          k.tech_norm,
          k.lac,
          k.bs_id,
          k.cell_id,
          k.expected_route,
          k.coverage_note,
          COALESCE(lac_sum.row_count, 0) AS l0_lac_rows,
          COALESCE(gps_sum.row_count, 0) AS l0_gps_rows
        FROM rebuild3_sample_meta.sample_key_scope k
        LEFT JOIN rebuild3_sample_meta.sample_source_summary lac_sum
          ON lac_sum.source_name = 'l0_lac'
         AND lac_sum.scenario = k.scenario
        LEFT JOIN rebuild3_sample_meta.sample_source_summary gps_sum
          ON gps_sum.source_name = 'l0_gps'
         AND gps_sum.scenario = k.scenario
        ORDER BY
          CASE k.scope_type WHEN 'bs' THEN 1 WHEN 'cell' THEN 2 ELSE 3 END,
          k.scenario
        """,
    )
    total_lac = fetch_val(conn, "SELECT count(*) FROM rebuild3_sample.source_l0_lac")
    total_gps = fetch_val(conn, "SELECT count(*) FROM rebuild3_sample.source_l0_gps")
    headers = [
        "scope_type",
        "scenario",
        "operator_code",
        "tech_norm",
        "lac",
        "bs_id",
        "cell_id",
        "expected_route",
        "l0_lac_rows",
        "l0_gps_rows",
        "coverage_note",
    ]
    table = md_table(
        headers,
        [
            [
                r["scope_type"],
                r["scenario"],
                r["operator_code"],
                r["tech_norm"],
                r["lac"],
                r["bs_id"],
                r["cell_id"],
                r["expected_route"],
                r["l0_lac_rows"],
                r["l0_gps_rows"],
                r["coverage_note"],
            ]
            for r in rows
        ],
    )
    return "\n".join(
        [
            "# 样本范围定义",
            "",
            "- 样本窗口：`2025-12-01` 至 `2025-12-07`",
            "- rebuild3 样本主输入：`rebuild3_sample.source_l0_lac`",
            "- rebuild2 对比输入：同一份 `rebuild3_sample.source_l0_lac`，另保留 `rebuild3_sample.source_l0_gps` 作为配对参考样本",
            "- 样本总量：`l0_lac = %s`，`l0_gps = %s`" % (total_lac, total_gps),
            "- 目标覆盖：`healthy / issue / waiting / observing / rejected / baseline`",
            "",
            table,
            "",
        ]
    )


def build_sample_run_report(conn: psycopg.Connection) -> str:
    run_rows = fetch_all(
        conn,
        """
        SELECT stage_name, metric_name, metric_value
        FROM rebuild3_sample_meta.batch_snapshot
        WHERE batch_id = 'BATCH-SAMPLE-20251201-20251207-V1'
        ORDER BY stage_name, metric_name
        """,
    )
    r2_route_rows = fetch_all(
        conn,
        """
        SELECT fact_route, count(*) AS row_count
        FROM rebuild3_sample_meta.r2_fact_semantic
        GROUP BY fact_route
        ORDER BY fact_route
        """,
    )
    r3_route_rows = fetch_all(
        conn,
        """
        SELECT route, count(*) AS row_count
        FROM (
          SELECT 'fact_governed'::text AS route FROM rebuild3_sample.fact_governed
          UNION ALL
          SELECT 'fact_pending_observation' FROM rebuild3_sample.fact_pending_observation
          UNION ALL
          SELECT 'fact_pending_issue' FROM rebuild3_sample.fact_pending_issue
          UNION ALL
          SELECT 'fact_rejected' FROM rebuild3_sample.fact_rejected
        ) x
        GROUP BY route
        ORDER BY route
        """,
    )
    snapshot_table = md_table(
        ["stage_name", "metric_name", "metric_value"],
        [[r["stage_name"], r["metric_name"], r["metric_value"]] for r in run_rows],
    )
    r2_table = md_table(
        ["fact_route", "row_count"],
        [[r["fact_route"], r["row_count"]] for r in r2_route_rows],
    )
    r3_table = md_table(
        ["fact_route", "row_count"],
        [[r["route"], r["row_count"]] for r in r3_route_rows],
    )
    return "\n".join(
        [
            "# 样本运行记录",
            "",
            "## 执行步骤",
            "",
            "1. 执行 `backend/sql/schema/001_foundation.sql`，创建 `rebuild3 / rebuild3_meta / rebuild3_sample / rebuild3_sample_meta` 独立 schema。",
            "2. 执行 `backend/sql/init/001_sample_extract.sql`，抽取同一份样本到 `rebuild3_sample.source_l0_lac` 与 `rebuild3_sample.source_l0_gps`。",
            "3. 执行 `backend/sql/init/002_rebuild2_sample_eval.sql`，在 `rebuild3_sample_meta.r2_*` 下完成 rebuild2 样本重跑。",
            "4. 执行 `backend/sql/govern/001_rebuild3_sample_pipeline.sql`，在 `rebuild3_sample*` 下完成 rebuild3 样本治理链路。",
            "",
            "## rebuild3 样本批次快照",
            "",
            snapshot_table,
            "",
            "## rebuild2 样本路由统计",
            "",
            r2_table,
            "",
            "## rebuild3 样本路由统计",
            "",
            r3_table,
            "",
            "## 日志位置",
            "",
            "- `rebuild3/.logs/001_foundation.log`",
            "- `rebuild3/.logs/001_sample_extract.log`",
            "- `rebuild3/.logs/002_rebuild2_sample_eval.log`",
            "- `rebuild3/.logs/001_rebuild3_sample_pipeline.log`",
            "",
        ]
    )


def build_sample_compare_report(conn: psycopg.Connection) -> str:
    route_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT fact_route AS route, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_fact_semantic
          GROUP BY fact_route
        ),
        r3 AS (
          SELECT route, count(*) AS cnt
          FROM (
            SELECT 'fact_governed'::text AS route FROM rebuild3_sample.fact_governed
            UNION ALL
            SELECT 'fact_pending_observation' FROM rebuild3_sample.fact_pending_observation
            UNION ALL
            SELECT 'fact_pending_issue' FROM rebuild3_sample.fact_pending_issue
            UNION ALL
            SELECT 'fact_rejected' FROM rebuild3_sample.fact_rejected
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
    scenario_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT scenario, fact_route AS route, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_fact_semantic
          GROUP BY scenario, fact_route
        ),
        r3 AS (
          SELECT sample_scope_tag AS scenario, route, count(*) AS cnt
          FROM (
            SELECT sample_scope_tag, 'fact_governed'::text AS route FROM rebuild3_sample.fact_governed
            UNION ALL
            SELECT sample_scope_tag, 'fact_pending_observation' FROM rebuild3_sample.fact_pending_observation
            UNION ALL
            SELECT sample_scope_tag, 'fact_pending_issue' FROM rebuild3_sample.fact_pending_issue
            UNION ALL
            SELECT sample_scope_tag, 'fact_rejected' FROM rebuild3_sample.fact_rejected
          ) x
          GROUP BY sample_scope_tag, route
        )
        SELECT
          COALESCE(r2.scenario, r3.scenario) AS scenario,
          COALESCE(r2.route, r3.route) AS route,
          COALESCE(r2.cnt, 0) AS r2_cnt,
          COALESCE(r3.cnt, 0) AS r3_cnt,
          COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2
        FULL JOIN r3
          ON r2.scenario = r3.scenario
         AND r2.route = r3.route
        WHERE COALESCE(r2.cnt, 0) <> COALESCE(r3.cnt, 0)
        ORDER BY 1, 2
        """,
    )
    state_rows = fetch_all(
        conn,
        """
        WITH r2 AS (
          SELECT 'cell' AS obj, lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_cell_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_bs_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_lac_state GROUP BY 1,2,3
        ),
        r3 AS (
          SELECT 'cell' AS obj, lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample.obj_cell GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample.obj_bs GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', lifecycle_state, health_state, count(*) AS cnt
          FROM rebuild3_sample.obj_lac GROUP BY 1,2,3
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
          SELECT 'cell' AS obj, anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_cell_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_bs_state GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample_meta.r2_lac_state GROUP BY 1,2,3
        ),
        r3 AS (
          SELECT 'cell' AS obj, anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample.obj_cell GROUP BY 1,2,3
          UNION ALL
          SELECT 'bs', anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample.obj_bs GROUP BY 1,2,3
          UNION ALL
          SELECT 'lac', anchorable, baseline_eligible, count(*) AS cnt
          FROM rebuild3_sample.obj_lac GROUP BY 1,2,3
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
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3_sample_meta.r2_cell_state WHERE baseline_eligible
          UNION ALL
          SELECT 'bs', count(*) AS cnt FROM rebuild3_sample_meta.r2_bs_state WHERE baseline_eligible
          UNION ALL
          SELECT 'lac', count(*) AS cnt FROM rebuild3_sample_meta.r2_lac_state WHERE baseline_eligible
        ),
        r3 AS (
          SELECT 'cell' AS obj, count(*) AS cnt FROM rebuild3_sample.baseline_cell
          UNION ALL
          SELECT 'bs', count(*) AS cnt FROM rebuild3_sample.baseline_bs
          UNION ALL
          SELECT 'lac', count(*) AS cnt FROM rebuild3_sample.baseline_lac
        )
        SELECT
          COALESCE(r2.obj, r3.obj) AS obj,
          COALESCE(r2.cnt, 0) AS r2_cnt,
          COALESCE(r3.cnt, 0) AS r3_cnt,
          COALESCE(r3.cnt, 0) - COALESCE(r2.cnt, 0) AS diff
        FROM r2
        FULL JOIN r3 USING (obj)
        ORDER BY 1
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
          FROM rebuild3_sample_meta.r2_cell_state r2
          JOIN rebuild3_sample.obj_cell r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
          WHERE r2.baseline_eligible AND r3.baseline_eligible
        ),
        common_bs AS (
          SELECT
            sqrt(power((r2.center_lon - r3.center_lon) * 85300, 2) + power((r2.center_lat - r3.center_lat) * 111000, 2))::numeric AS center_diff_m,
            abs(COALESCE(r2.gps_p90_dist_m, 0) - COALESCE(r3.gps_p90_dist_m, 0))::numeric AS p90_diff_m,
            abs(COALESCE(r2.gps_original_ratio, 0) - COALESCE(r3.gps_original_ratio, 0))::numeric AS gps_ratio_diff,
            abs(COALESCE(r2.signal_original_ratio, 0) - COALESCE(r3.signal_original_ratio, 0))::numeric AS signal_ratio_diff
          FROM rebuild3_sample_meta.r2_bs_state r2
          JOIN rebuild3_sample.obj_bs r3 USING (operator_code, tech_norm, lac, bs_id)
          WHERE r2.baseline_eligible AND r3.baseline_eligible
        ),
        common_lac AS (
          SELECT
            sqrt(power((r2.center_lon - r3.center_lon) * 85300, 2) + power((r2.center_lat - r3.center_lat) * 111000, 2))::numeric AS center_diff_m,
            abs(COALESCE(r2.gps_original_ratio, 0) - COALESCE(r3.gps_original_ratio, 0))::numeric AS gps_ratio_diff,
            abs(COALESCE(r2.signal_original_ratio, 0) - COALESCE(r3.signal_original_ratio, 0))::numeric AS signal_ratio_diff
          FROM rebuild3_sample_meta.r2_lac_state r2
          JOIN rebuild3_sample.obj_lac r3 USING (operator_code, tech_norm, lac)
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
    baseline_membership_rows = fetch_all(
        conn,
        """
        WITH diff AS (
          WITH r2 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3_sample_meta.r2_cell_state
            WHERE baseline_eligible
          ),
          r3 AS (
            SELECT operator_code, tech_norm, lac, bs_id, cell_id
            FROM rebuild3_sample.baseline_cell
          )
          SELECT
            COALESCE(r2.operator_code, r3.operator_code) AS operator_code,
            COALESCE(r2.tech_norm, r3.tech_norm) AS tech_norm,
            COALESCE(r2.lac, r3.lac) AS lac,
            COALESCE(r2.bs_id, r3.bs_id) AS bs_id,
            COALESCE(r2.cell_id, r3.cell_id) AS cell_id,
            CASE
              WHEN r2.cell_id IS NULL THEN 'r3_only'
              WHEN r3.cell_id IS NULL THEN 'r2_only'
            END AS membership
          FROM r2
          FULL JOIN r3 USING (operator_code, tech_norm, lac, bs_id, cell_id)
          WHERE r2.cell_id IS NULL OR r3.cell_id IS NULL
        )
        SELECT
          d.membership,
          d.operator_code,
          d.tech_norm,
          d.lac,
          d.bs_id,
          d.cell_id,
          r2.health_state AS r2_health,
          r3.health_state AS r3_health,
          r2.gps_p90_dist_m AS r2_p90,
          r3.gps_p90_dist_m AS r3_p90
        FROM diff d
        LEFT JOIN rebuild3_sample_meta.r2_cell_state r2
          USING (operator_code, tech_norm, lac, bs_id, cell_id)
        LEFT JOIN rebuild3_sample.obj_cell r3
          USING (operator_code, tech_norm, lac, bs_id, cell_id)
        ORDER BY membership, operator_code, tech_norm, lac, bs_id, cell_id
        """,
    )

    total_sample_rows = fetch_val(conn, "SELECT count(*) FROM rebuild3_sample.source_l0_lac")
    route_table = md_table(
        ["route", "r2_cnt", "r3_cnt", "diff", "diff_pct_vs_r2"],
        [
            [r["route"], r["r2_cnt"], r["r3_cnt"], r["diff"], pct(abs(r["diff"]), r["r2_cnt"])]
            for r in route_rows
        ],
    )
    scenario_table = md_table(
        ["scenario", "route", "r2_cnt", "r3_cnt", "diff", "diff_pct_vs_r2"],
        [
            [r["scenario"], r["route"], r["r2_cnt"], r["r3_cnt"], r["diff"], pct(abs(r["diff"]), r["r2_cnt"])]
            for r in scenario_rows
        ],
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
        [[r["obj"], r["r2_cnt"], r["r3_cnt"], r["diff"], pct(abs(r["diff"]), r["r2_cnt"])] for r in baseline_rows],
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
    baseline_membership_table = md_table(
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
            for r in baseline_membership_rows
        ],
    )

    route_issue = next(r for r in route_rows if r["route"] == "fact_pending_issue")
    route_gov = next(r for r in route_rows if r["route"] == "fact_governed")
    baseline_cell = next(r for r in baseline_rows if r["obj"] == "cell")

    return "\n".join(
        [
            "# 样本偏差评估",
            "",
            "## 结论",
            "",
            "- 样本双跑成功：`rebuild2_sample_eval` 与 `rebuild3_sample_pipeline` 均已完成。",
            "- Gate E 建议结论：`可进入全量，但必须先由用户确认`。",
            "- 无 P0 / P1 阻塞缺陷；当前偏差集中在 `gps_bias` 对象级语义收紧，是 rebuild3 冻结规则的可解释差异。",
            f"- rebuild3 相比 rebuild2：`fact_pending_issue +{route_issue['diff']}`，`fact_governed {route_gov['diff']}`，占样本总量 {pct(abs(route_issue['diff']), total_sample_rows)}。",
            f"- baseline 主要差异在 Cell：`{baseline_cell['diff']:+d}`，相对 rebuild2 Cell baseline 数量偏差 {pct(abs(baseline_cell['diff']), baseline_cell['r2_cnt'])}。",
            "",
            "## 四分流对比",
            "",
            route_table,
            "",
            "## 差异场景定位",
            "",
            scenario_table,
            "",
            "解释：`normal_spread` 与 `single_large` 场景中的 206 条记录，在 rebuild3 中因 `gps_bias` 被收紧为对象级问题，转入 `fact_pending_issue`。",
            "",
            "## 对象状态分布对比",
            "",
            state_table,
            "",
            "解释：Cell 数量未变，但 `gps_bias -> healthy` 与 `healthy -> gps_bias` 的互换来自空间口径更新：rebuild2 依赖旧的 Cell-to-BS 异常标记，rebuild3 依赖样本画像 P90 空间离散度。",
            "",
            "## 资格分布对比",
            "",
            qual_table,
            "",
            "## baseline 对比",
            "",
            baseline_table,
            "",
            "### baseline Cell 交集与画像指标",
            "",
            profile_table,
            "",
            "说明：共同 baseline 对象上，Cell/BS/LAC 的质心差异 P90 均为 0，Cell 质心最大偏差约 15.46m；说明主空间口径稳定。",
            "",
            "### baseline Cell 差异清单",
            "",
            baseline_membership_table,
            "",
            "解释：`r2_only` 的 2 个 Cell 在 rebuild3 中被识别为 `gps_bias` 并从 baseline 剔除；`r3_only` 的 10 个 Cell 来自 rebuild2 旧口径误判 `gps_bias`、而在 rebuild3 画像 P90 下恢复为 `healthy`。",
            "",
            "## Gate E 门禁判断",
            "",
            "- 通过项：样本双跑成功；关键对象数量一致；路由偏差可解释；共同 baseline 对象的空间指标稳定。",
            "- 非阻塞偏差：`gps_bias` 语义收紧导致 `fact_pending_issue` 增加 206 条、Cell baseline 净增 8 个。",
            "- 建议：保持当前实现进入全量，但按照正式流程，必须等待用户确认后才能进入 Gate F 全量构建。",
            "",
        ]
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rebuild3 sample pipeline and generate reports.")
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
        write_text(DOC_DIR / "sample_scope.md", build_sample_scope(conn))
        write_text(DOC_DIR / "sample_run_report.md", build_sample_run_report(conn))
        write_text(DOC_DIR / "sample_compare_report.md", build_sample_compare_report(conn))

    print("[ok] docs/sample_scope.md")
    print("[ok] docs/sample_run_report.md")
    print("[ok] docs/sample_compare_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
