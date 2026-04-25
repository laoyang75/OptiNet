#!/usr/bin/env python3
"""Run rebuild5 Step 1 -> Step 5 in strict day-serial mode on Citus.

This runner is intentionally a real `.py` file so multiprocessing-based steps
can spawn child workers safely. It never renames or drops
`rb5.raw_gps_full_backup`; each batch only truncates and reloads `rb5.raw_gps`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "REBUILD5_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5488/yangca",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchall, fetchone
from rebuild5.backend.app.core.settings import settings
from rebuild5.backend.app.enrichment.pipeline import _insert_snapshot_seed_records, run_enrichment_pipeline
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline, run_maintenance_pipeline_for_batch
from rebuild5.backend.app.profile.pipeline import relation_exists, run_profile_pipeline
from rebuild5.scripts.run_daily_increment_batch_loop import materialize_step2_scope


RESET_SQL_PATH = Path(__file__).with_name("reset_step1_to_step5_for_full_rerun_v3.sql")
RUN_ID = f"gate3_fullrun_{date.today().strftime('%Y%m%d')}"
ROUND2_EXTRAPOLATED_MINUTES = 92.0
LOCAL_BATCH7_XLARGE = 13460


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-day", help="inclusive day bucket, e.g. 2025-12-04")
    parser.add_argument("--end-day", help="inclusive day bucket, e.g. 2025-12-07")
    parser.add_argument(
        "--start-batch-id",
        type=int,
        default=1,
        help="expected batch id for start-day; use 3 when resuming from 2025-12-03",
    )
    parser.add_argument(
        "--repair-batch2-seed-step5",
        action="store_true",
        help="repair batch 2 snapshot seeds after ODS-024b duplicate failure, rerun Step 5, and exit",
    )
    parser.add_argument(
        "--resume-step5-batch-id",
        type=int,
        help="rerun Step 5 only for an already completed Step 3/4 batch, then exit",
    )
    parser.add_argument(
        "--resume-step5-day",
        help="day label for --resume-step5-batch-id notes, e.g. 2025-12-04",
    )
    parser.add_argument(
        "--rerun-step5-batch-id",
        type=int,
        help="rerun Step 5 only for an already-completed Step 3 batch and exit",
    )
    parser.add_argument(
        "--rerun-step5-day",
        help="day label used in validation notes with --rerun-step5-batch-id",
    )
    parser.add_argument(
        "--rewrite-report-only",
        action="store_true",
        help="rebuild the final rb5_bench.report row and markdown from current database state, then exit",
    )
    parser.add_argument(
        "--source-relation",
        default="rb5.raw_gps_full_backup",
        help="source relation used to refill rb5.raw_gps",
    )
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="reuse current Step 1-5 state instead of executing the reset SQL first",
    )
    parser.add_argument(
        "--min-cells",
        type=int,
        default=0,
        help="fail a batch if trusted_cell_library rows are below this threshold",
    )
    parser.add_argument(
        "--max-cells",
        type=int,
        default=0,
        help="fail a batch if trusted_cell_library rows exceed this threshold",
    )
    parser.add_argument(
        "--require-dynamic",
        action="store_true",
        help="fail a batch if drift_pattern='dynamic' stays at 0",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the selected day range and source counts without modifying data",
    )
    return parser.parse_args()


def _log(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _insert_note(topic: str, severity: str, body: str) -> None:
    execute(
        """
        INSERT INTO rb5_bench.notes (run_id, topic, severity, body)
        VALUES (%s, %s, %s, %s)
        """,
        (RUN_ID, topic, severity, body),
    )


def _safe_insert_note(topic: str, severity: str, body: str) -> None:
    try:
        _insert_note(topic, severity, body)
    except Exception as exc:  # keep the main run error visible
        _log({"event": "note_write_failed", "topic": topic, "severity": severity, "error": str(exc)})


def _iter_days(start_day: date, end_day: date) -> list[date]:
    if end_day < start_day:
        raise RuntimeError("end_day must be >= start_day")
    days: list[date] = []
    current = start_day
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def _ensure_raw_gps_exists(source_relation: str) -> None:
    if relation_exists("rb5.raw_gps"):
        return
    execute(f"CREATE TABLE rb5.raw_gps AS SELECT * FROM {source_relation} WHERE false")
    execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_record_id ON rb5.raw_gps ("记录数唯一标识")')
    execute("CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rb5.raw_gps (ts)")


def _run_reset_sql() -> None:
    subprocess.run(
        [
            "psql",
            settings.pg_dsn,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(RESET_SQL_PATH),
        ],
        check=True,
    )


def _count_source_rows(*, source_relation: str, day: date) -> int:
    row = fetchone(
        f"""
        SELECT COUNT(*) AS cnt
        FROM {source_relation}
        WHERE ts::date = %s::date
        """,
        (day.isoformat(),),
    )
    return int(row["cnt"]) if row else 0


def _load_raw_day(*, source_relation: str, day: date) -> int:
    _ensure_raw_gps_exists(source_relation)
    execute("TRUNCATE TABLE rb5.raw_gps")
    execute(
        f"""
        INSERT INTO rb5.raw_gps
        SELECT *
        FROM {source_relation}
        WHERE ts::date = %s::date
        """,
        (day.isoformat(),),
    )
    execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_record_id ON rb5.raw_gps ("记录数唯一标识")')
    execute("CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rb5.raw_gps (ts)")
    execute("ANALYZE rb5.raw_gps")
    row = fetchone("SELECT COUNT(*) AS cnt FROM rb5.raw_gps")
    return int(row["cnt"]) if row else 0


def _cleanup_after_step4() -> None:
    for rel in (
        "rb5.path_a_records",
        "rb5._profile_seed_grid",
        "rb5._profile_primary_seed",
        "rb5._profile_seed_distance",
        "rb5._profile_core_cutoff",
        "rb5._profile_core_points",
        "rb5._profile_core_gps",
        "rb5._profile_counts",
        "rb5.profile_obs",
        "rb5.profile_base",
    ):
        execute(f"DROP TABLE IF EXISTS {rel}")


def _cleanup_after_step5() -> None:
    for rel in (
        "rb5.cell_metrics_base",
        "rb5.cell_radius_stats",
        "rb5.cell_activity_stats",
        "rb5.cell_drift_stats",
        "rb5.cell_daily_centroid",
        "rb5.cell_metrics_window",
        "rb5.cell_anomaly_summary",
        "rb5.cell_core_seed_grid",
        "rb5.cell_core_primary_seed",
        "rb5.cell_core_seed_distance",
        "rb5.cell_core_cutoff",
        "rb5.cell_core_points",
        "rb5.cell_core_gps_stats",
    ):
        execute(f"DROP TABLE IF EXISTS {rel}")


def _collect_batch_validation(batch_id: int) -> dict[str, Any]:
    counts = fetchone(
        """
        SELECT
            COUNT(*) AS n_cells,
            COUNT(*) FILTER (WHERE drift_pattern = 'stable') AS n_stable,
            COUNT(*) FILTER (WHERE drift_pattern = 'large_coverage') AS n_large_coverage,
            COUNT(*) FILTER (WHERE drift_pattern = 'uncertain') AS n_uncertain,
            COUNT(*) FILTER (WHERE drift_pattern = 'dynamic') AS n_dynamic,
            COUNT(*) FILTER (WHERE drift_pattern = 'dual_cluster') AS n_dual,
            COUNT(*) FILTER (WHERE ta_verification = 'xlarge') AS ta_xlarge
        FROM rb5.trusted_cell_library
        WHERE batch_id = %s
        """,
        (batch_id,),
    ) or {}
    dedup = fetchone(
        """
        SELECT
            COUNT(*) AS dup_groups,
            COALESCE(SUM(c - 1), 0) AS extra_rows
        FROM (
            SELECT cell_id, record_id, COUNT(*) AS c
            FROM rb5.cell_sliding_window
            WHERE batch_id = %s
              AND cell_origin = 'cell_infos'
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        ) d
        """,
        (batch_id,),
    ) or {}
    return {
        "batch_id": batch_id,
        "n_cells": int(counts.get("n_cells") or 0),
        "n_stable": int(counts.get("n_stable") or 0),
        "n_large_coverage": int(counts.get("n_large_coverage") or 0),
        "n_uncertain": int(counts.get("n_uncertain") or 0),
        "n_dynamic": int(counts.get("n_dynamic") or 0),
        "n_dual": int(counts.get("n_dual") or 0),
        "ta_xlarge": int(counts.get("ta_xlarge") or 0),
        "dup_groups": int(dedup.get("dup_groups") or 0),
        "dup_extra_rows": int(dedup.get("extra_rows") or 0),
    }


def _assert_batch(validation: dict[str, Any], *, min_cells: int, max_cells: int, require_dynamic: bool) -> None:
    batch_id = int(validation["batch_id"])
    n_cells = int(validation["n_cells"])
    if min_cells and n_cells < min_cells:
        raise RuntimeError(f"batch {batch_id} n_cells={n_cells} < min_cells={min_cells}")
    if max_cells and n_cells > max_cells:
        raise RuntimeError(f"batch {batch_id} n_cells={n_cells} > max_cells={max_cells}")
    if require_dynamic and int(validation["n_dynamic"]) <= 0:
        raise RuntimeError(f"batch {batch_id} dynamic=0 while --require-dynamic is set")
    if int(validation["dup_groups"]) > 0 or int(validation["dup_extra_rows"]) > 0:
        raise RuntimeError(
            f"batch {batch_id} ODS-024b failed: dup_groups={validation['dup_groups']}, "
            f"dup_extra_rows={validation['dup_extra_rows']}"
        )


def _count_snapshot_seed_cell_infos_dups(batch_id: int) -> int:
    row = fetchone(
        """
        SELECT COUNT(*) AS dup_groups
        FROM (
            SELECT record_id, cell_id, COUNT(*) AS c
            FROM rb5.snapshot_seed_records
            WHERE batch_id = %s
              AND cell_origin = 'cell_infos'
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        ) d
        """,
        (batch_id,),
    )
    return int(row["dup_groups"]) if row else 0


def _repair_batch2_seed_and_step5() -> None:
    batch_id = 2
    started = time.monotonic()
    repair_run_id = f"enrich_seed_repair_{date.today().strftime('%Y%m%d')}"
    _log({"event": "repair_start", "batch_id": batch_id, "run_id": repair_run_id})

    execute("DELETE FROM rb5.snapshot_seed_records WHERE batch_id = %s", (batch_id,))
    _insert_snapshot_seed_records(batch_id=batch_id, run_id=repair_run_id)
    execute("ANALYZE rb5.snapshot_seed_records")
    dup_groups = _count_snapshot_seed_cell_infos_dups(batch_id)
    _log({"event": "snapshot_seed_rebuilt", "batch_id": batch_id, "cell_infos_dup_groups": dup_groups})
    if dup_groups:
        _safe_insert_note(
            f"gate3_blocker_batch_{batch_id}",
            "blocker",
            f"batch {batch_id} seed repair still has {dup_groups} cell_infos duplicate groups",
        )
        raise RuntimeError(f"seed repair failed: dup_groups={dup_groups}")

    _safe_insert_note(
        f"gate3_batch_{batch_id}_issue",
        "warn",
        (
            "batch 2 first Step 5 publish completed but extra ODS-024b acceptance failed. "
            "Root cause: snapshot_seed_records replayed duplicate candidate_seed_history evidence across batches. "
            "Patched Step 4 seed bridge with DISTINCT ON(record_id, cell_id, cell_origin), rebuilt batch 2 seeds, "
            "and reran Step 5."
        ),
    )
    step5 = run_maintenance_pipeline_for_batch(batch_id=batch_id)
    _log({"event": "step5_rerun_done", "batch_id": batch_id, "result": step5})
    validation = _collect_batch_validation(batch_id)
    validation["duration_seconds"] = round(time.monotonic() - started, 2)
    validation["day"] = "2025-12-02"
    raw_row = fetchone("SELECT COUNT(*) AS cnt FROM rb5.raw_gps")
    validation["raw_count"] = int(raw_row["cnt"]) if raw_row else 0
    _assert_batch(validation, min_cells=0, max_cells=0, require_dynamic=False)
    _log({"event": "batch_validation", "batch_id": batch_id, "result": validation})
    _safe_insert_note(
        f"gate3_batch_{batch_id}_complete",
        "info",
        json.dumps(validation, ensure_ascii=False, sort_keys=True),
    )
    _cleanup_after_step5()
    _log({"event": "repair_complete", "batch_id": batch_id, "run_id": RUN_ID})


def _resume_step5_batch(*, batch_id: int, day_label: str | None) -> None:
    started = time.monotonic()
    day = day_label or f"batch_{batch_id}"
    _log({"event": "resume_step5_start", "batch_id": batch_id, "day": day})
    step5 = run_maintenance_pipeline_for_batch(batch_id=batch_id)
    _log({"event": "step5_resume_done", "batch_id": batch_id, "day": day, "result": step5})
    validation = _collect_batch_validation(batch_id)
    validation["duration_seconds"] = round(time.monotonic() - started, 2)
    validation["day"] = day
    raw_row = fetchone("SELECT COUNT(*) AS cnt FROM rb5.raw_gps")
    validation["raw_count"] = int(raw_row["cnt"]) if raw_row else 0
    _assert_batch(validation, min_cells=0, max_cells=0, require_dynamic=False)
    _log({"event": "batch_validation", "batch_id": batch_id, "result": validation})
    _safe_insert_note(
        f"gate3_batch_{batch_id}_complete",
        "info",
        json.dumps(validation, ensure_ascii=False, sort_keys=True),
    )
    _cleanup_after_step5()
    _log({"event": "resume_step5_complete", "batch_id": batch_id, "run_id": RUN_ID})


def _rerun_step5_for_batch(*, batch_id: int, day: str | None) -> None:
    started = time.monotonic()
    day_label = day or f"batch-{batch_id}"
    _log({"event": "step5_rerun_start", "batch_id": batch_id, "day": day_label})
    step5 = run_maintenance_pipeline_for_batch(batch_id=batch_id)
    _log({"event": "step5_rerun_done", "batch_id": batch_id, "day": day_label, "result": step5})
    validation = _collect_batch_validation(batch_id)
    validation["duration_seconds"] = round(time.monotonic() - started, 2)
    validation["day"] = day_label
    raw_row = fetchone("SELECT COUNT(*) AS cnt FROM rb5.raw_gps")
    validation["raw_count"] = int(raw_row["cnt"]) if raw_row else 0
    _assert_batch(validation, min_cells=0, max_cells=0, require_dynamic=False)
    _log({"event": "batch_validation", "batch_id": batch_id, "result": validation})
    _safe_insert_note(
        f"gate3_batch_{batch_id}_complete",
        "info",
        json.dumps(validation, ensure_ascii=False, sort_keys=True),
    )
    _cleanup_after_step5()
    _log({"event": "step5_rerun_complete", "batch_id": batch_id, "run_id": RUN_ID})


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
    return "\n".join(lines)


def _collapse_sql(sql: str, *, max_len: int = 240) -> str:
    collapsed = " ".join(str(sql).split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def _collect_final_rows() -> dict[str, list[dict[str, Any]]]:
    return {
        "batch_summary": fetchall(
            """
            SELECT
                batch_id,
                COUNT(*) AS n_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'stable') AS n_stable,
                COUNT(*) FILTER (WHERE drift_pattern = 'large_coverage') AS n_large_coverage,
                COUNT(*) FILTER (WHERE drift_pattern = 'uncertain') AS n_uncertain,
                COUNT(*) FILTER (WHERE drift_pattern = 'dynamic') AS n_dynamic,
                COUNT(*) FILTER (WHERE drift_pattern = 'dual_cluster') AS n_dual,
                COUNT(*) FILTER (WHERE ta_verification = 'xlarge') AS n_xlarge
            FROM rb5.trusted_cell_library
            GROUP BY batch_id
            ORDER BY batch_id
            """
        ),
        "ta_distribution": fetchall(
            """
            SELECT batch_id, COALESCE(ta_verification, '(null)') AS ta_verification, COUNT(*) AS n
            FROM rb5.trusted_cell_library
            GROUP BY batch_id, COALESCE(ta_verification, '(null)')
            ORDER BY batch_id, ta_verification
            """
        ),
        "snapshot_diff": fetchall(
            """
            SELECT batch_id, COUNT(*) AS n
            FROM rb5.snapshot_diff_cell
            GROUP BY batch_id
            ORDER BY batch_id
            """
        ),
        "pg_stat_top20": fetchall(
            """
            SELECT query, calls, ROUND(total_exec_time::numeric, 2) AS total_exec_time_ms
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT 20
            """
        ),
    }


def _load_completion_note_results() -> list[dict[str, Any]]:
    rows = fetchall(
        """
        SELECT topic, body
        FROM rb5_bench.notes
        WHERE run_id = %s
          AND topic LIKE 'gate3_batch_%%_complete'
        ORDER BY id
        """,
        (RUN_ID,),
    )
    latest_by_batch: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(str(row["body"]))
            batch_id = int(payload["batch_id"])
        except Exception:
            continue
        latest_by_batch[batch_id] = payload
    return [latest_by_batch[batch_id] for batch_id in sorted(latest_by_batch)]


def _load_full_source_counts() -> list[dict[str, Any]]:
    rows = fetchall(
        """
        SELECT to_char(ts::date, 'YYYY-MM-DD') AS day, COUNT(*) AS source_rows
        FROM rb5.raw_gps_full_backup
        WHERE ts::date BETWEEN DATE '2025-12-01' AND DATE '2025-12-07'
        GROUP BY 1
        ORDER BY 1
        """
    )
    return [{"day": row["day"], "source_rows": int(row["source_rows"])} for row in rows]


def _formal_elapsed_seconds(fallback_seconds: float) -> float:
    row = fetchone(
        """
        SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) AS seconds
        FROM rb5_bench.notes
        WHERE run_id = %s
          AND topic = 'gate3_observation'
          AND body LIKE '%%formal_7_batch_start%%'
        """,
        (RUN_ID,),
    )
    if row and row.get("seconds") is not None:
        return float(row["seconds"])
    return fallback_seconds


def _build_report(
    *,
    source_counts: list[dict[str, Any]],
    batch_results: list[dict[str, Any]],
    total_seconds: float,
) -> tuple[str, dict[str, Any]]:
    rows = _collect_final_rows()
    batch_summary = rows["batch_summary"]
    batch_ids = [int(row["batch_id"]) for row in batch_summary]
    if batch_ids != list(range(1, 8)):
        raise RuntimeError(f"final batch coverage check failed: found batch_ids={batch_ids}")

    total_seconds_for_report = _formal_elapsed_seconds(total_seconds)
    total_minutes = round(total_seconds_for_report / 60, 2)
    total_cells_across_batches = sum(int(row["n_cells"]) for row in batch_summary)
    dynamic_total = sum(int(row["n_dynamic"]) for row in batch_summary)
    dynamic_start = next((int(row["batch_id"]) for row in batch_summary if int(row["n_dynamic"]) > 0), None)
    batch7 = next(row for row in batch_summary if int(row["batch_id"]) == 7)
    batch7_xlarge = int(batch7["n_xlarge"])
    xlarge_delta = LOCAL_BATCH7_XLARGE - batch7_xlarge
    xlarge_reduction = round(xlarge_delta / LOCAL_BATCH7_XLARGE * 100, 2) if LOCAL_BATCH7_XLARGE else 0.0
    runtime_delta = round(total_minutes - ROUND2_EXTRAPOLATED_MINUTES, 2)
    note_batch_results = _load_completion_note_results()
    merged_results: dict[int, dict[str, Any]] = {
        int(item["batch_id"]): item for item in note_batch_results if item.get("batch_id") is not None
    }
    for item in batch_results:
        merged_results[int(item["batch_id"])] = item
    runtime_rows = [merged_results[batch_id] for batch_id in sorted(merged_results)]
    full_source_counts = _load_full_source_counts()
    top20_has_create_distributed = any(
        "create_distributed_table" in str(row["query"])
        for row in rows["pg_stat_top20"]
    )

    body_parts = [
        f"# OptiNet rebuild5 Citus Gate 3 Full Run {date.today().strftime('%Y-%m-%d')}",
        "",
        "## 1. Runtime",
        "",
        (
            f"7 批 Citus 串行重跑总耗时 {total_minutes} 分钟。"
            f"Round 2 外推为 {ROUND2_EXTRAPOLATED_MINUTES:.0f} 分钟，"
            f"本轮差值 {runtime_delta:+.2f} 分钟。"
            "该耗时按 gate3 正式开始 note 到报告写入时刻的 wall-clock 计算，包含 batch 2 seed 修复重跑时间。"
        ),
        "",
        _table(
            ["batch_id", "day", "raw_rows", "duration_seconds", "n_cells", "dynamic", "xlarge"],
            [
                [
                    item["batch_id"],
                    item["day"],
                    item["raw_count"],
                    item["duration_seconds"],
                    item["n_cells"],
                    item["n_dynamic"],
                    item["ta_xlarge"],
                ]
                for item in runtime_rows
            ],
        ),
        "",
        "Source rows loaded from rb5.raw_gps_full_backup:",
        "",
        _table(
            ["day", "source_rows"],
            [[item["day"], item["source_rows"]] for item in (full_source_counts or source_counts)],
        ),
        "",
        "## 2. Batch Cell And Drift Distribution",
        "",
        _table(
            ["batch_id", "n_cells", "stable", "large_coverage", "uncertain", "dynamic", "dual_cluster", "xlarge"],
            [
                [
                    row["batch_id"],
                    row["n_cells"],
                    row["n_stable"],
                    row["n_large_coverage"],
                    row["n_uncertain"],
                    row["n_dynamic"],
                    row["n_dual"],
                    row["n_xlarge"],
                ]
                for row in batch_summary
            ],
        ),
        "",
        "TA verification distribution:",
        "",
        _table(
            ["batch_id", "ta_verification", "n"],
            [[row["batch_id"], row["ta_verification"], row["n"]] for row in rows["ta_distribution"]],
        ),
        "",
        "## 3. Dynamic",
        "",
        f"dynamic 首次出现 batch: {dynamic_start if dynamic_start is not None else 'none'}；7 批总量: {dynamic_total}。",
        (
            "这与 Gate 3 health signal 中 batch 3/4 起 dynamic > 0 的预期不一致；"
            "本轮未调整 min_total_active_days / min_total_dedup_pts 等业务阈值，已作为 suspect 观察记录。"
            if dynamic_total == 0
            else "dynamic 已出现，符合多日窗口后应产生动态标签的方向。"
        ),
        "",
        "## 4. Xlarge ODS-023b Check",
        "",
        (
            f"batch 7 xlarge={batch7_xlarge}，本地 batch 7 基线={LOCAL_BATCH7_XLARGE}，"
            f"减少 {xlarge_delta}，降幅 {xlarge_reduction}%。"
        ),
        "",
        "## 5. Snapshot Diff And pg_stat_statements Top 20",
        "",
        "snapshot_diff_cell batch counts:",
        "",
        _table(
            ["batch_id", "n"],
            [[row["batch_id"], row["n"]] for row in rows["snapshot_diff"]],
        ),
        "",
        "pg_stat_statements Top 20:",
        "",
        _table(
            ["rank", "calls", "total_exec_time_ms", "query"],
            [
                [idx, row["calls"], row["total_exec_time_ms"], _collapse_sql(row["query"])]
                for idx, row in enumerate(rows["pg_stat_top20"], start=1)
            ],
        ),
        "",
        (
            "Top SQL 中仍出现 create_distributed_table，说明当前 helper 仍会对不少临时/中间表重复做 Citus layout 初始化；"
            "这不是业务 CTAS 回退，但值得收敛表生命周期和 layout 检查。"
            if top20_has_create_distributed
            else "Top SQL 中未出现 create_distributed_table，CTAS 改造在本轮 Top SQL 视角下未回退。"
        ),
        "Step 5 的窗口/半径/label 聚合仍是后半程主要耗时，尤其 _label_input_points 与 collision。",
        "",
        "## 6. Next Optimization Points",
        "",
        "- 继续观察 raw_gps_full_backup 的 did shard 倾斜；本轮接受，但如果 Step 1 成为主耗时，应优先重评分布键或预分桶。",
        "- Step 5 仍是最可能的主要耗时区，建议按 pg_stat_statements Top SQL 对 cell_sliding_window、cell_metrics_window、label stage 做定向 EXPLAIN。",
        "- 如果 CPU 仍未打满，再评估 pool_size / parallel workers；不要先改业务阈值。",
    ]
    body = "\n".join(body_parts) + "\n"
    meta = {
        "run_id": RUN_ID,
        "run_mode": "gate3",
        "batches": 7,
        "total_cells": total_cells_across_batches,
        "batch7_cells": int(batch7["n_cells"]),
        "dynamic_total": dynamic_total,
        "dynamic_start_batch": dynamic_start,
        "batch7_xlarge": batch7_xlarge,
        "runtime_minutes": total_minutes,
        "runtime_seconds": round(total_seconds_for_report, 2),
        "round2_extrapolated_minutes": ROUND2_EXTRAPOLATED_MINUTES,
    }
    return body, meta


def _write_final_report(
    *,
    source_counts: list[dict[str, Any]],
    batch_results: list[dict[str, Any]],
    total_seconds: float,
    update_existing: bool = False,
) -> Path:
    body, meta = _build_report(
        source_counts=source_counts,
        batch_results=batch_results,
        total_seconds=total_seconds,
    )
    report_name = f"optinet_rebuild5_citus_fullrun_{date.today().strftime('%Y%m%d')}"
    if update_existing:
        execute(
            """
            UPDATE rb5_bench.report
            SET body = %s,
                meta = %s::jsonb,
                created_at = NOW()
            WHERE id = (
                SELECT id
                FROM rb5_bench.report
                WHERE report_name = %s
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (body, json.dumps(meta, ensure_ascii=False), report_name),
        )
        exists = fetchone(
            "SELECT id FROM rb5_bench.report WHERE report_name = %s ORDER BY id DESC LIMIT 1",
            (report_name,),
        )
        if not exists:
            execute(
                """
                INSERT INTO rb5_bench.report (report_name, body, meta)
                VALUES (%s, %s, %s::jsonb)
                """,
                (report_name, body, json.dumps(meta, ensure_ascii=False)),
            )
    else:
        execute(
            """
            INSERT INTO rb5_bench.report (report_name, body, meta)
            VALUES (%s, %s, %s::jsonb)
            """,
            (report_name, body, json.dumps(meta, ensure_ascii=False)),
        )
    report_path = REPO_ROOT / f"{report_name}.md"
    report_path.write_text(body, encoding="utf-8")
    return report_path


def main() -> None:
    args = _parse_args()
    if args.repair_batch2_seed_step5:
        _repair_batch2_seed_and_step5()
        return
    if args.resume_step5_batch_id:
        _resume_step5_batch(batch_id=args.resume_step5_batch_id, day_label=args.resume_step5_day)
        return
    if args.rerun_step5_batch_id is not None:
        _rerun_step5_for_batch(batch_id=args.rerun_step5_batch_id, day=args.rerun_step5_day)
        return
    if args.rewrite_report_only:
        report_path = _write_final_report(
            source_counts=_load_full_source_counts(),
            batch_results=_load_completion_note_results(),
            total_seconds=0,
            update_existing=True,
        )
        _log({"event": "report_rewritten", "run_id": RUN_ID, "report_path": str(report_path)})
        return
    if not args.start_day or not args.end_day:
        raise RuntimeError("--start-day and --end-day are required unless --repair-batch2-seed-step5 is used")
    start_day = date.fromisoformat(args.start_day)
    end_day = date.fromisoformat(args.end_day)
    days = _iter_days(start_day, end_day)

    _log(
        {
            "event": "plan",
            "start_day": start_day.isoformat(),
            "end_day": end_day.isoformat(),
            "days": [day.isoformat() for day in days],
            "source_relation": args.source_relation,
            "skip_reset": args.skip_reset,
            "min_cells": args.min_cells,
            "max_cells": args.max_cells,
            "require_dynamic": args.require_dynamic,
            "start_batch_id": args.start_batch_id,
            "reset_sql": str(RESET_SQL_PATH.name),
        }
    )

    source_counts = [
        {"day": day.isoformat(), "source_rows": _count_source_rows(source_relation=args.source_relation, day=day)}
        for day in days
    ]
    _log({"event": "source_counts", "days": source_counts})
    if args.plan_only:
        return

    if not args.skip_reset:
        _run_reset_sql()
        _log({"event": "reset_done", "sql": str(RESET_SQL_PATH.name)})

    _safe_insert_note(
        "gate3_observation",
        "info",
        json.dumps(
            {
                "event": "formal_7_batch_start",
                "run_id": RUN_ID,
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
                "source_counts": source_counts,
                "skip_reset": args.skip_reset,
            },
            ensure_ascii=False,
        ),
    )

    batch_results: list[dict[str, Any]] = []
    overall_started = time.monotonic()
    current_batch_id = 0
    for expected_batch_id, day in enumerate(days, start=args.start_batch_id):
        current_batch_id = expected_batch_id
        batch_started = time.monotonic()
        try:
            raw_count = _load_raw_day(source_relation=args.source_relation, day=day)
            _log(
                {
                    "event": "raw_day_loaded",
                    "day": day.isoformat(),
                    "expected_batch_id": expected_batch_id,
                    "raw_count": raw_count,
                }
            )

            step1 = run_step1_pipeline()
            _log({"event": "step1_done", "day": day.isoformat(), "result": step1})

            execute("DROP TABLE IF EXISTS rb5._step2_cell_input")
            scope_rows = materialize_step2_scope(day=day, input_relation="rb5.etl_cleaned")
            _log({"event": "step2_scope_materialized", "day": day.isoformat(), "rows": scope_rows})

            step3 = run_profile_pipeline()
            if int(step3["batch_id"]) != expected_batch_id:
                raise RuntimeError(
                    f"step2/3 batch mismatch for {day.isoformat()}: "
                    f"expected {expected_batch_id}, got {step3['batch_id']}"
                )
            _log({"event": "step2_3_done", "day": day.isoformat(), "result": step3})

            step4 = run_enrichment_pipeline()
            if int(step4["batch_id"]) != expected_batch_id:
                raise RuntimeError(
                    f"step4 batch mismatch for {day.isoformat()}: "
                    f"expected {expected_batch_id}, got {step4['batch_id']}"
                )
            _log({"event": "step4_done", "day": day.isoformat(), "result": step4})

            _cleanup_after_step4()
            _log({"event": "cleanup_after_step4_done", "day": day.isoformat(), "batch_id": expected_batch_id})

            step5 = run_maintenance_pipeline()
            if int(step5["batch_id"]) != expected_batch_id:
                raise RuntimeError(
                    f"step5 batch mismatch for {day.isoformat()}: "
                    f"expected {expected_batch_id}, got {step5['batch_id']}"
                )
            _log({"event": "step5_done", "day": day.isoformat(), "result": step5})

            validation = _collect_batch_validation(expected_batch_id)
            validation["duration_seconds"] = round(time.monotonic() - batch_started, 2)
            validation["day"] = day.isoformat()
            validation["raw_count"] = raw_count
            _assert_batch(
                validation,
                min_cells=args.min_cells,
                max_cells=args.max_cells,
                require_dynamic=args.require_dynamic,
            )
            _log({"event": "batch_validation", "day": day.isoformat(), "result": validation})

            _safe_insert_note(
                f"gate3_batch_{expected_batch_id}_complete",
                "info",
                json.dumps(validation, ensure_ascii=False, sort_keys=True),
            )
            batch_results.append(validation)

            _cleanup_after_step5()
            _log({"event": "cleanup_after_step5_done", "day": day.isoformat(), "batch_id": expected_batch_id})
        except Exception as exc:
            _safe_insert_note(
                f"gate3_blocker_batch_{current_batch_id}",
                "blocker",
                f"batch {current_batch_id} ({day.isoformat()}) stopped: {type(exc).__name__}: {exc}",
            )
            raise

    total_seconds = time.monotonic() - overall_started
    planned_batch_ids = list(range(args.start_batch_id, args.start_batch_id + len(days)))
    if planned_batch_ids != list(range(1, 8)):
        _log(
            {
                "event": "partial_run_no_final_report",
                "planned_batch_ids": planned_batch_ids,
                "total_seconds": round(total_seconds, 2),
            }
        )
        return

    report_path = _write_final_report(
        source_counts=source_counts,
        batch_results=batch_results,
        total_seconds=total_seconds,
    )
    _safe_insert_note(
        "FULLRUN_COMPLETE",
        "info",
        (
            "7 批 Citus 全量重跑完成，产出 rb5.trusted_cell_library batch_id=1..7。"
            f"详见 rb5_bench.report 最新一行；markdown 副本: {report_path.name}。"
        ),
    )
    _log({"event": "fullrun_complete", "run_id": RUN_ID, "report_path": str(report_path)})


if __name__ == "__main__":
    main()
