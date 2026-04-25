#!/usr/bin/env python3
"""Rerun Step5 from existing Step3/Step4 outputs without rerunning Step2-4."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5488/yangca',
)

from rebuild5.backend.app.core.database import execute, fetchall
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline_for_batch


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-batch-id', type=int, default=1)
    parser.add_argument('--end-batch-id', type=int)
    parser.add_argument('--skip-reset', action='store_true')
    return parser.parse_args()


def _reset_step5_outputs() -> None:
    statements = (
        'DELETE FROM rb5_meta.step5_run_stats',
        "DELETE FROM rb5_meta.run_log WHERE run_type = 'maintenance'",
        'TRUNCATE TABLE rb5.trusted_cell_library',
        'TRUNCATE TABLE rb5.trusted_bs_library',
        'TRUNCATE TABLE rb5.trusted_lac_library',
        'TRUNCATE TABLE rb5.collision_id_list',
        'TRUNCATE TABLE rb5.cell_centroid_detail',
        'TRUNCATE TABLE rb5.bs_centroid_detail',
        'TRUNCATE TABLE rb5.cell_sliding_window',
    )
    for stmt in statements:
        execute(stmt)


def _available_batches() -> list[int]:
    rows = fetchall(
        """
        SELECT DISTINCT batch_id
        FROM rb5_meta.step3_run_stats
        WHERE batch_id IS NOT NULL
        ORDER BY batch_id
        """
    )
    return [int(row['batch_id']) for row in rows]


def main() -> None:
    args = _parse_args()
    batches = [b for b in _available_batches() if b >= args.start_batch_id]
    if args.end_batch_id is not None:
        batches = [b for b in batches if b <= args.end_batch_id]
    if not batches:
        raise RuntimeError('no Step3 batches available in the requested range')

    _log({'event': 'step5_rerun_plan', 'batches': batches, 'skip_reset': args.skip_reset})
    if not args.skip_reset:
        _reset_step5_outputs()
        _log({'event': 'step5_reset_done'})

    for batch_id in batches:
        result = run_maintenance_pipeline_for_batch(batch_id=batch_id)
        _log({'event': 'step5_rerun_done', 'batch_id': batch_id, 'result': result})


if __name__ == '__main__':
    main()
