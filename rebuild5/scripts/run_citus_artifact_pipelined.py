#!/usr/bin/env python3
"""Run rebuild5 with immutable Step 2 input artifacts.

Producer runs Step 1 day by day, freezes rb5_stage.step2_input_* artifacts,
and consumer runs Step 2-5 serially from ready artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
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
os.environ.setdefault("PGOPTIONS", "-c auto_explain.log_analyze=off")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchone
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
from rebuild5.scripts.run_citus_pipelined_batches import _run_batch_sentinels
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
from rebuild5.scripts.run_daily_increment_batch_loop import freeze_step2_input_artifact


@dataclass(frozen=True)
class ArtifactJob:
    batch_id: int
    day: date
    raw_count: int
    batch_started: float


@dataclass
class ArtifactPipelineState:
    stop_event: threading.Event
    producer_done: threading.Event
    first_error: BaseException | None = None
    first_traceback: str | None = None
    failed_day: date | None = None
    failed_batch_id: int | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-day", required=True, help="inclusive day bucket, e.g. 2025-12-01")
    parser.add_argument("--end-day", required=True, help="inclusive day bucket, e.g. 2025-12-07")
    parser.add_argument("--start-batch-id", type=int, default=1)
    parser.add_argument("--skip-reset", action="store_true")
    parser.add_argument("--source-relation", default="rb5.raw_gps_full_backup")
    parser.add_argument("--artifact-source-relation", default="rb5.etl_cleaned")
    parser.add_argument("--producer-fail-fast", action="store_true")
    parser.add_argument("--min-cells", type=int, default=0)
    parser.add_argument("--max-cells", type=int, default=0)
    parser.add_argument("--require-dynamic", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def _record_error(
    state: ArtifactPipelineState,
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


def _ready_artifact_relation(batch_id: int) -> str:
    row = fetchone(
        """
        SELECT artifact_relation, status
        FROM rb5_meta.pipeline_artifacts
        WHERE batch_id = %s
        """,
        (batch_id,),
    )
    if not row:
        raise RuntimeError(f"artifact state missing for batch {batch_id}")
    if row["status"] != "ready":
        raise RuntimeError(f"artifact for batch {batch_id} is not ready: {row['status']}")
    return str(row["artifact_relation"])


def _mark_artifact(batch_id: int, status: str, error: str | None = None) -> None:
    execute(
        """
        UPDATE rb5_meta.pipeline_artifacts
        SET status = %s,
            error = %s,
            finished_at = NOW()
        WHERE batch_id = %s
        """,
        (status, error[:500] if error else None, batch_id),
    )


def _run_step1_artifact_producer(
    *,
    jobs: "queue.Queue[ArtifactJob | None]",
    state: ArtifactPipelineState,
    days: list[date],
    start_batch_id: int,
    source_relation: str,
    artifact_source_relation: str,
    producer_fail_fast: bool,
) -> None:
    try:
        for offset, day in enumerate(days):
            if state.stop_event.is_set():
                break
            batch_id = start_batch_id + offset
            batch_started = time.monotonic()
            raw_count = _load_raw_day(source_relation=source_relation, day=day)
            _log({"event": "raw_day_loaded", "day": day.isoformat(), "batch_id": batch_id, "raw_count": raw_count})

            step1 = run_step1_pipeline()
            _log({"event": "step1_done", "day": day.isoformat(), "batch_id": batch_id, "result": step1})

            artifact, row_count = freeze_step2_input_artifact(
                batch_id=batch_id,
                day=day,
                source_relation=artifact_source_relation,
            )
            _log(
                {
                    "event": "artifact_ready",
                    "day": day.isoformat(),
                    "batch_id": batch_id,
                    "artifact": artifact,
                    "rows": row_count,
                }
            )
            if row_count <= 0:
                raise RuntimeError(f"artifact {artifact} has no rows for {day.isoformat()}")
            jobs.put(ArtifactJob(batch_id=batch_id, day=day, raw_count=raw_count, batch_started=batch_started))
            if producer_fail_fast and state.stop_event.is_set():
                break
    except BaseException as exc:
        _record_error(state, exc=exc, day=locals().get("day"), batch_id=locals().get("batch_id"))
        _safe_insert_note(
            f"loop_optim_02_artifact_producer_failed_batch_{locals().get('batch_id')}",
            "blocker",
            f"producer stopped: {type(exc).__name__}: {exc}",
        )
    finally:
        state.producer_done.set()
        jobs.put(None)


def _run_artifact_consumer(
    *,
    jobs: "queue.Queue[ArtifactJob | None]",
    state: ArtifactPipelineState,
    batch_results: list[dict[str, Any]],
    min_cells: int,
    max_cells: int,
    require_dynamic: bool,
) -> None:
    while True:
        try:
            job = jobs.get(timeout=5)
        except queue.Empty:
            if state.producer_done.is_set():
                return
            continue
        if job is None:
            return
        if state.stop_event.is_set():
            return

        try:
            artifact_relation = _ready_artifact_relation(job.batch_id)
            step3 = run_profile_pipeline(input_relation=artifact_relation)
            if int(step3["batch_id"]) != job.batch_id:
                raise RuntimeError(f"step2/3 batch mismatch: expected {job.batch_id}, got {step3['batch_id']}")
            _log({"event": "step2_3_done", "day": job.day.isoformat(), "batch_id": job.batch_id, "result": step3})

            step4 = run_enrichment_pipeline()
            if int(step4["batch_id"]) != job.batch_id:
                raise RuntimeError(f"step4 batch mismatch: expected {job.batch_id}, got {step4['batch_id']}")
            _log({"event": "step4_done", "day": job.day.isoformat(), "batch_id": job.batch_id, "result": step4})

            _cleanup_after_step4()
            step5 = run_maintenance_pipeline()
            if int(step5["batch_id"]) != job.batch_id:
                raise RuntimeError(f"step5 batch mismatch: expected {job.batch_id}, got {step5['batch_id']}")
            _log({"event": "step5_done", "day": job.day.isoformat(), "batch_id": job.batch_id, "result": step5})

            validation = _collect_batch_validation(job.batch_id)
            validation["duration_seconds"] = round(time.monotonic() - job.batch_started, 2)
            validation["day"] = job.day.isoformat()
            validation["raw_count"] = job.raw_count
            validation["artifact_relation"] = artifact_relation
            _assert_batch(validation, min_cells=min_cells, max_cells=max_cells, require_dynamic=require_dynamic)
            execute("DROP VIEW IF EXISTS rb5.step2_batch_input")
            execute(f"CREATE VIEW rb5.step2_batch_input AS SELECT * FROM {artifact_relation}")
            _run_batch_sentinels(batch_id=job.batch_id, day=job.day)
            _mark_artifact(job.batch_id, "consumed")
            batch_results.append(validation)

            _cleanup_after_step5()
            _safe_insert_note(
                f"loop_optim_artifact_batch_{job.batch_id}_complete",
                "info",
                json.dumps(validation, ensure_ascii=False, sort_keys=True),
            )
        except BaseException as exc:
            _mark_artifact(job.batch_id, "failed", str(exc))
            _record_error(state, exc=exc, day=job.day, batch_id=job.batch_id)
            _safe_insert_note(
                f"loop_optim_02_artifact_consumer_failed_batch_{job.batch_id}",
                "blocker",
                f"consumer stopped at batch {job.batch_id} ({job.day.isoformat()}): {type(exc).__name__}: {exc}",
            )
            return


def _run_pipeline(args: argparse.Namespace) -> tuple[list[dict[str, Any]], float]:
    start_day = date.fromisoformat(args.start_day)
    end_day = date.fromisoformat(args.end_day)
    days = _iter_days(start_day, end_day)
    source_counts = [
        {"day": day.isoformat(), "source_rows": _count_source_rows(source_relation=args.source_relation, day=day)}
        for day in days
    ]
    _log(
        {
            "event": "plan",
            "runner": "artifact_pipelined",
            "start_day": start_day.isoformat(),
            "end_day": end_day.isoformat(),
            "days": [day.isoformat() for day in days],
            "source_relation": args.source_relation,
            "artifact_source_relation": args.artifact_source_relation,
            "skip_reset": args.skip_reset,
            "start_batch_id": args.start_batch_id,
        }
    )
    _log({"event": "source_counts", "days": source_counts})
    if args.plan_only:
        return [], 0.0

    if not args.skip_reset:
        _run_reset_sql()
        _log({"event": "reset_done", "sql": str(RESET_SQL_PATH.name), "runner": "artifact_pipelined"})

    state = ArtifactPipelineState(stop_event=threading.Event(), producer_done=threading.Event())
    jobs: queue.Queue[ArtifactJob | None] = queue.Queue(maxsize=10)
    batch_results: list[dict[str, Any]] = []
    started = time.monotonic()
    producer = threading.Thread(
        target=_run_step1_artifact_producer,
        kwargs={
            "jobs": jobs,
            "state": state,
            "days": days,
            "start_batch_id": args.start_batch_id,
            "source_relation": args.source_relation,
            "artifact_source_relation": args.artifact_source_relation,
            "producer_fail_fast": args.producer_fail_fast,
        },
        name="artifact-step1-producer",
    )
    consumer = threading.Thread(
        target=_run_artifact_consumer,
        kwargs={
            "jobs": jobs,
            "state": state,
            "batch_results": batch_results,
            "min_cells": args.min_cells,
            "max_cells": args.max_cells,
            "require_dynamic": args.require_dynamic,
        },
        name="artifact-step25-consumer",
    )
    producer.start()
    consumer.start()
    producer.join()
    consumer.join()
    elapsed = time.monotonic() - started

    if state.first_error is not None:
        _log(
            {
                "event": "artifact_pipelined_failed",
                "failed_day": state.failed_day.isoformat() if state.failed_day else None,
                "failed_batch_id": state.failed_batch_id,
                "error": f"{type(state.first_error).__name__}: {state.first_error}",
                "traceback": state.first_traceback,
            }
        )
        raise state.first_error

    _log(
        {
            "event": "artifact_pipelined_complete",
            "total_seconds": round(elapsed, 2),
            "batch_results": batch_results,
        }
    )
    return batch_results, elapsed


def main() -> None:
    args = _parse_args()
    _run_pipeline(args)


if __name__ == "__main__":
    main()
