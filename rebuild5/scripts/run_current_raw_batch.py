#!/usr/bin/env python3
"""Run one Step 1 -> Step 5 batch against the current rb5.raw_gps contents."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "REBUILD5_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5488/yangca",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchone
from rebuild5.backend.app.core.settings import settings
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
from rebuild5.backend.app.profile.pipeline import relation_exists, run_profile_pipeline


RESET_SQL_PATH = Path(__file__).with_name("reset_step1_to_step5_for_full_rerun_v3.sql")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-batch-id", type=int, required=True)
    parser.add_argument("--skip-reset", action="store_true")
    parser.add_argument("--min-cells", type=int, default=0)
    parser.add_argument("--max-cells", type=int, default=0)
    parser.add_argument("--require-dynamic", action="store_true")
    return parser.parse_args()


def _log(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


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


def main() -> None:
    args = _parse_args()
    if not relation_exists("rb5.raw_gps"):
        raise RuntimeError("rb5.raw_gps does not exist")
    raw_row = fetchone("SELECT COUNT(*) AS cnt FROM rb5.raw_gps")
    raw_count = int(raw_row["cnt"]) if raw_row else 0

    _log(
        {
            "event": "plan",
            "expected_batch_id": args.expected_batch_id,
            "skip_reset": args.skip_reset,
            "raw_count": raw_count,
            "min_cells": args.min_cells,
            "max_cells": args.max_cells,
            "require_dynamic": args.require_dynamic,
            "reset_sql": str(RESET_SQL_PATH.name),
        }
    )

    if not args.skip_reset:
        _run_reset_sql()
        _log({"event": "reset_done", "sql": str(RESET_SQL_PATH.name)})

    batch_started = time.monotonic()
    step1 = run_step1_pipeline()
    _log({"event": "step1_done", "result": step1})

    step3 = run_profile_pipeline()
    if int(step3["batch_id"]) != args.expected_batch_id:
        raise RuntimeError(
            f"step2/3 batch mismatch: expected {args.expected_batch_id}, got {step3['batch_id']}"
        )
    _log({"event": "step2_3_done", "result": step3})

    step4 = run_enrichment_pipeline()
    if int(step4["batch_id"]) != args.expected_batch_id:
        raise RuntimeError(
            f"step4 batch mismatch: expected {args.expected_batch_id}, got {step4['batch_id']}"
        )
    _log({"event": "step4_done", "result": step4})

    _cleanup_after_step4()
    _log({"event": "cleanup_after_step4_done", "batch_id": args.expected_batch_id})

    step5 = run_maintenance_pipeline()
    if int(step5["batch_id"]) != args.expected_batch_id:
        raise RuntimeError(
            f"step5 batch mismatch: expected {args.expected_batch_id}, got {step5['batch_id']}"
        )
    _log({"event": "step5_done", "result": step5})

    validation = _collect_batch_validation(args.expected_batch_id)
    validation["duration_seconds"] = round(time.monotonic() - batch_started, 2)
    _assert_batch(
        validation,
        min_cells=args.min_cells,
        max_cells=args.max_cells,
        require_dynamic=args.require_dynamic,
    )
    _log({"event": "batch_validation", "result": validation})

    _cleanup_after_step5()
    _log({"event": "cleanup_after_step5_done", "batch_id": args.expected_batch_id})


if __name__ == "__main__":
    main()
