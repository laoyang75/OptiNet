#!/usr/bin/env python3
"""Run rebuild5 Step 1 and Step 2-5 with a conservative Citus pipeline.

The pipeline overlaps Step 1 for day N+1 with Step 2-5 for day N.  It keeps
the serial runner's data contract: for the same day, Step 1 completes first,
then ``rb5.step2_batch_input`` is materialized, then Step 2-5 starts.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "REBUILD5_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5488/yangca",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchall
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
from rebuild5.scripts.run_citus_serial_batches import (
    RESET_SQL_PATH,
    _assert_batch,
    _cleanup_after_step4,
    _cleanup_after_step5,
    _collect_batch_validation,
    _count_source_rows,
    _iter_days,
    _load_raw_day,
    _log,
    _run_reset_sql,
    _safe_insert_note,
)
from rebuild5.scripts.run_daily_increment_batch_loop import materialize_step2_scope


SERIAL_RUNNER = Path(__file__).with_name("run_citus_serial_batches.py")


@dataclass(frozen=True)
class Step25Job:
    day: date
    batch_id: int
    raw_count: int
    batch_started: float
    sentinels_done: threading.Event


@dataclass
class PipelineState:
    stop_event: threading.Event
    first_error: BaseException | None = None
    first_traceback: str | None = None
    failed_day: date | None = None
    failed_batch_id: int | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-day", required=True, help="inclusive day bucket, e.g. 2025-12-01")
    parser.add_argument("--end-day", required=True, help="inclusive day bucket, e.g. 2025-12-07")
    parser.add_argument(
        "--start-batch-id",
        type=int,
        default=1,
        help="expected batch id for start-day; use when resuming a partial run",
    )
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="reuse current Step 1-5 state instead of executing the reset SQL first",
    )
    parser.add_argument(
        "--max-pipeline-depth",
        type=int,
        default=2,
        help="maximum in-flight day jobs; values above 2 are capped because Step 2-5 is serial-stateful",
    )
    parser.add_argument(
        "--fallback-on-error",
        action="store_true",
        help="if pipelined execution fails, invoke the serial runner from the failed batch with --skip-reset",
    )
    parser.add_argument(
        "--source-relation",
        default="rb5.raw_gps_full_backup",
        help="source relation used to refill rb5.raw_gps",
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


def _record_error(
    state: PipelineState,
    *,
    exc: BaseException,
    day: date | None,
    batch_id: int | None,
) -> None:
    if state.first_error is None:
        state.first_error = exc
        state.first_traceback = traceback.format_exc()
        state.failed_day = day
        state.failed_batch_id = batch_id
    state.stop_event.set()


def _raise_if_failed(state: PipelineState) -> None:
    if state.first_error is not None:
        raise state.first_error


def _run_batch_sentinels(*, batch_id: int, day: date) -> list[dict[str, Any]]:
    rows = fetchall(
        """
        WITH params AS (
          SELECT %s::int AS bid, %s::date AS expected_day
        ),
        enriched AS (
          SELECT
            p.bid,
            p.expected_day,
            COUNT(e.*) AS rows,
            MIN(e.event_time_std)::date AS min_day,
            MAX(e.event_time_std)::date AS max_day,
            COUNT(e.*) FILTER (
              WHERE e.event_time_std::date IS DISTINCT FROM p.expected_day
            ) AS off_day_rows
          FROM params p
          LEFT JOIN rb5.enriched_records e ON e.batch_id = p.bid
          GROUP BY p.bid, p.expected_day
        ),
        sliding AS (
          SELECT
            p.bid,
            MIN(s.event_time_std)::date AS min_day,
            MAX(s.event_time_std)::date AS max_day,
            MAX(s.event_time_std) - MIN(s.event_time_std) AS span,
            COUNT(*) FILTER (WHERE s.event_time_std < DATE '2025-01-01') AS old_rows,
            COUNT(*) FILTER (WHERE s.event_time_std >= DATE '2025-12-08') AS future_rows
          FROM params p
          LEFT JOIN rb5.cell_sliding_window s ON s.batch_id = p.bid
          GROUP BY p.bid
        ),
        scope_rel AS (
          SELECT to_regclass('rb5._step2_cell_input') AS fallback_rel,
                 to_regclass('rb5.step2_batch_input') AS scope_rel
        ),
        scope_max AS (
          SELECT CASE
            WHEN (SELECT scope_rel FROM scope_rel) IS NULL THEN NULL::date
            ELSE (SELECT MAX(event_time_std)::date FROM rb5.step2_batch_input)
          END AS max_day
        ),
        tcl AS (
          SELECT p.bid, COUNT(t.*) AS rows
          FROM params p
          LEFT JOIN rb5.trusted_cell_library t ON t.batch_id = p.bid
          GROUP BY p.bid
        ),
        prev_tcl AS (
          SELECT p.bid, COUNT(t.*) AS rows
          FROM params p
          LEFT JOIN rb5.trusted_cell_library t ON t.batch_id = p.bid - 1
          GROUP BY p.bid
        )
        SELECT
          'enriched_single_day' AS check_name,
          (rows = 0 OR (min_day = expected_day AND max_day = expected_day AND off_day_rows = 0)) AS ok,
          format('rows=%%s min=%%s max=%%s off_day=%%s expected=%%s', rows, min_day, max_day, off_day_rows, expected_day) AS detail
        FROM enriched
        UNION ALL
        SELECT
          'sliding_span_no_old_future',
          (span <= INTERVAL '14 days' AND old_rows = 0 AND future_rows = 0),
          format('min=%%s max=%%s span=%%s old=%%s future=%%s', min_day, max_day, span, old_rows, future_rows)
        FROM sliding
        UNION ALL
        SELECT
          'step2_scope_clean_or_today',
          (
            (SELECT fallback_rel FROM scope_rel) IS NULL
            AND ((SELECT scope_rel FROM scope_rel) IS NULL OR (SELECT max_day FROM scope_max) = (SELECT expected_day FROM params))
          ),
          format('fallback=%%s scope=%%s scope_max=%%s', (SELECT fallback_rel FROM scope_rel), (SELECT scope_rel FROM scope_rel), (SELECT max_day FROM scope_max))
        UNION ALL
        SELECT
          'tcl_monotonic',
          (tcl.rows > 0 AND (tcl.bid = 1 OR tcl.rows > prev_tcl.rows)),
          format('batch=%%s rows=%%s prev_rows=%%s', tcl.bid, tcl.rows, prev_tcl.rows)
        FROM tcl JOIN prev_tcl USING (bid)
        """,
        (batch_id, day.isoformat()),
    )
    failed = [row for row in rows if not row.get("ok")]
    _log({"event": "batch_sentinels", "batch_id": batch_id, "day": day.isoformat(), "results": rows})
    if failed:
        raise RuntimeError(f"batch {batch_id} sentinel failed: {failed}")
    return rows


def _run_step1_producer(
    *,
    jobs: "queue.Queue[Step25Job | None]",
    state: PipelineState,
    days: list[date],
    start_batch_id: int,
    source_relation: str,
) -> None:
    previous_sentinels_done: threading.Event | None = None
    try:
        for offset, day in enumerate(days):
            if state.stop_event.is_set():
                break
            batch_id = start_batch_id + offset
            batch_started = time.monotonic()

            raw_count = _load_raw_day(source_relation=source_relation, day=day)
            _log(
                {
                    "event": "raw_day_loaded",
                    "day": day.isoformat(),
                    "expected_batch_id": batch_id,
                    "raw_count": raw_count,
                    "runner": "pipelined",
                }
            )

            step1 = run_step1_pipeline()
            _log({"event": "step1_done", "day": day.isoformat(), "result": step1, "runner": "pipelined"})

            if previous_sentinels_done is not None:
                _log({"event": "scope_barrier_wait_start", "day": day.isoformat(), "batch_id": batch_id})
                while not previous_sentinels_done.wait(timeout=5):
                    if state.stop_event.is_set():
                        _raise_if_failed(state)
                _log({"event": "scope_barrier_released", "day": day.isoformat(), "batch_id": batch_id})

            execute("DROP TABLE IF EXISTS rb5._step2_cell_input")
            scope_rows = materialize_step2_scope(day=day, input_relation="rb5.etl_cleaned")
            _log(
                {
                    "event": "step2_scope_materialized",
                    "day": day.isoformat(),
                    "batch_id": batch_id,
                    "rows": scope_rows,
                    "runner": "pipelined",
                }
            )
            if scope_rows <= 0:
                raise RuntimeError(f"no records found for day {day.isoformat()}")

            sentinels_done = threading.Event()
            jobs.put(
                Step25Job(
                    day=day,
                    batch_id=batch_id,
                    raw_count=raw_count,
                    batch_started=batch_started,
                    sentinels_done=sentinels_done,
                )
            )
            previous_sentinels_done = sentinels_done
    except BaseException as exc:
        _record_error(state, exc=exc, day=locals().get("day"), batch_id=locals().get("batch_id"))
    finally:
        jobs.put(None)


def _run_step25_consumer(
    *,
    jobs: "queue.Queue[Step25Job | None]",
    state: PipelineState,
    batch_results: list[dict[str, Any]],
    min_cells: int,
    max_cells: int,
    require_dynamic: bool,
) -> None:
    while True:
        job = jobs.get()
        if job is None:
            return
        if state.stop_event.is_set():
            job.sentinels_done.set()
            return
        try:
            step3 = run_profile_pipeline()
            if int(step3["batch_id"]) != job.batch_id:
                raise RuntimeError(
                    f"step2/3 batch mismatch for {job.day.isoformat()}: "
                    f"expected {job.batch_id}, got {step3['batch_id']}"
                )
            _log({"event": "step2_3_done", "day": job.day.isoformat(), "result": step3, "runner": "pipelined"})

            step4 = run_enrichment_pipeline()
            if int(step4["batch_id"]) != job.batch_id:
                raise RuntimeError(
                    f"step4 batch mismatch for {job.day.isoformat()}: "
                    f"expected {job.batch_id}, got {step4['batch_id']}"
                )
            _log({"event": "step4_done", "day": job.day.isoformat(), "result": step4, "runner": "pipelined"})

            _cleanup_after_step4()
            _log({"event": "cleanup_after_step4_done", "day": job.day.isoformat(), "batch_id": job.batch_id})

            step5 = run_maintenance_pipeline()
            if int(step5["batch_id"]) != job.batch_id:
                raise RuntimeError(
                    f"step5 batch mismatch for {job.day.isoformat()}: "
                    f"expected {job.batch_id}, got {step5['batch_id']}"
                )
            _log({"event": "step5_done", "day": job.day.isoformat(), "result": step5, "runner": "pipelined"})

            validation = _collect_batch_validation(job.batch_id)
            validation["duration_seconds"] = round(time.monotonic() - job.batch_started, 2)
            validation["day"] = job.day.isoformat()
            validation["raw_count"] = job.raw_count
            _assert_batch(
                validation,
                min_cells=min_cells,
                max_cells=max_cells,
                require_dynamic=require_dynamic,
            )
            _log({"event": "batch_validation", "day": job.day.isoformat(), "result": validation})
            _run_batch_sentinels(batch_id=job.batch_id, day=job.day)

            _safe_insert_note(
                f"gate3_batch_{job.batch_id}_complete",
                "info",
                json.dumps(validation, ensure_ascii=False, sort_keys=True),
            )
            batch_results.append(validation)

            _cleanup_after_step5()
            _log({"event": "cleanup_after_step5_done", "day": job.day.isoformat(), "batch_id": job.batch_id})
            job.sentinels_done.set()
        except BaseException as exc:
            job.sentinels_done.set()
            _record_error(state, exc=exc, day=job.day, batch_id=job.batch_id)
            _safe_insert_note(
                f"fix6_03_pipelined_blocker_batch_{job.batch_id}",
                "blocker",
                f"pipelined batch {job.batch_id} ({job.day.isoformat()}) stopped: {type(exc).__name__}: {exc}",
            )
            return


def _run_serial_fallback(
    *,
    failed_day: date,
    failed_batch_id: int,
    end_day: date,
    args: argparse.Namespace,
) -> None:
    cmd = [
        sys.executable,
        str(SERIAL_RUNNER),
        "--start-day",
        failed_day.isoformat(),
        "--end-day",
        end_day.isoformat(),
        "--start-batch-id",
        str(failed_batch_id),
        "--skip-reset",
        "--source-relation",
        args.source_relation,
    ]
    if args.min_cells:
        cmd.extend(["--min-cells", str(args.min_cells)])
    if args.max_cells:
        cmd.extend(["--max-cells", str(args.max_cells)])
    if args.require_dynamic:
        cmd.append("--require-dynamic")

    _log(
        {
            "event": "serial_fallback_start",
            "failed_day": failed_day.isoformat(),
            "failed_batch_id": failed_batch_id,
            "cmd": cmd,
        }
    )
    _safe_insert_note(
        "fix6_03_pipelined_fallback",
        "warn",
        f"pipelined failed at batch {failed_batch_id} day {failed_day}; starting serial fallback",
    )
    subprocess.run(cmd, cwd=str(REPO_ROOT), env=os.environ.copy(), check=True)
    _log({"event": "serial_fallback_done", "failed_batch_id": failed_batch_id})


def _run_pipeline(args: argparse.Namespace) -> tuple[list[dict[str, Any]], float]:
    start_day = date.fromisoformat(args.start_day)
    end_day = date.fromisoformat(args.end_day)
    days = _iter_days(start_day, end_day)

    max_depth = max(1, min(int(args.max_pipeline_depth), 2))
    source_counts = [
        {"day": day.isoformat(), "source_rows": _count_source_rows(source_relation=args.source_relation, day=day)}
        for day in days
    ]
    _log(
        {
            "event": "plan",
            "runner": "pipelined",
            "start_day": start_day.isoformat(),
            "end_day": end_day.isoformat(),
            "days": [day.isoformat() for day in days],
            "source_relation": args.source_relation,
            "skip_reset": args.skip_reset,
            "start_batch_id": args.start_batch_id,
            "max_pipeline_depth": max_depth,
            "fallback_on_error": args.fallback_on_error,
            "reset_sql": str(RESET_SQL_PATH.name),
        }
    )
    _log({"event": "source_counts", "days": source_counts})
    if args.plan_only:
        return [], 0.0

    if not args.skip_reset:
        _run_reset_sql()
        _log({"event": "reset_done", "sql": str(RESET_SQL_PATH.name), "runner": "pipelined"})

    _safe_insert_note(
        "fix6_03_pipelined_start",
        "info",
        json.dumps(
            {
                "event": "pipelined_7_batch_start",
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
                "source_counts": source_counts,
                "skip_reset": args.skip_reset,
                "max_pipeline_depth": max_depth,
            },
            ensure_ascii=False,
        ),
    )

    state = PipelineState(stop_event=threading.Event())
    jobs: queue.Queue[Step25Job | None] = queue.Queue(maxsize=max_depth)
    batch_results: list[dict[str, Any]] = []
    overall_started = time.monotonic()
    producer = threading.Thread(
        target=_run_step1_producer,
        kwargs={
            "jobs": jobs,
            "state": state,
            "days": days,
            "start_batch_id": args.start_batch_id,
            "source_relation": args.source_relation,
        },
        name="fix6-step1-producer",
    )
    consumer = threading.Thread(
        target=_run_step25_consumer,
        kwargs={
            "jobs": jobs,
            "state": state,
            "batch_results": batch_results,
            "min_cells": args.min_cells,
            "max_cells": args.max_cells,
            "require_dynamic": args.require_dynamic,
        },
        name="fix6-step25-consumer",
    )
    producer.start()
    consumer.start()
    producer.join()
    consumer.join()
    total_seconds = time.monotonic() - overall_started

    if state.first_error is not None:
        _log(
            {
                "event": "pipelined_failed",
                "failed_day": state.failed_day.isoformat() if state.failed_day else None,
                "failed_batch_id": state.failed_batch_id,
                "error": f"{type(state.first_error).__name__}: {state.first_error}",
                "traceback": state.first_traceback,
            }
        )
        if args.fallback_on_error and state.failed_day is not None and state.failed_batch_id is not None:
            _run_serial_fallback(
                failed_day=state.failed_day,
                failed_batch_id=state.failed_batch_id,
                end_day=end_day,
                args=args,
            )
            return batch_results, total_seconds
        raise state.first_error

    planned_batch_ids = list(range(args.start_batch_id, args.start_batch_id + len(days)))
    _log(
        {
            "event": "pipelined_complete",
            "planned_batch_ids": planned_batch_ids,
            "total_seconds": round(total_seconds, 2),
            "batch_results": batch_results,
        }
    )
    return batch_results, total_seconds


def main() -> None:
    args = _parse_args()
    _run_pipeline(args)


if __name__ == "__main__":
    main()
