#!/usr/bin/env python3
"""Run standard rebuild5 batches sequentially.

This script encodes the current standard runbook:

1. Step 2/3
2. Step 4
3. Drop Step 2 large tables
4. Step 5
5. Drop Step 4/5 intermediate tables

It must be executed from a real file path so multiprocessing-based steps can
spawn child workers correctly. Do not replace it with a `python - <<'PY'`
inline launcher for production reruns.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import sys

os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2',
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline


def _cleanup_after_step4() -> None:
    for rel in (
        'rebuild5.path_a_records',
        'rebuild5.profile_obs',
        'rebuild5.profile_base',
    ):
        execute(f'DROP TABLE IF EXISTS {rel}')


def _cleanup_after_step5() -> None:
    for rel in (
        'rebuild5.cell_daily_centroid',
        'rebuild5.cell_metrics_window',
        'rebuild5.cell_anomaly_summary',
    ):
        execute(f'DROP TABLE IF EXISTS {rel}')


def _log(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _phase_order(phase: str) -> int:
    return {'step2_3': 0, 'step4': 1, 'step5': 2}[phase]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-batch', type=int, required=True)
    parser.add_argument('--end-batch', type=int, required=True)
    parser.add_argument(
        '--start-phase',
        choices=('step2_3', 'step4', 'step5'),
        default='step2_3',
        help='Resume phase for start-batch only; later batches always start from step2_3.',
    )
    args = parser.parse_args()

    if args.end_batch < args.start_batch:
        raise SystemExit('end-batch must be >= start-batch')

    for batch in range(args.start_batch, args.end_batch + 1):
        phase = args.start_phase if batch == args.start_batch else 'step2_3'
        _log({'batch': batch, 'event': 'start', 'phase': phase, 'at': datetime.now().isoformat()})

        if _phase_order(phase) <= _phase_order('step2_3'):
            step3 = run_profile_pipeline()
            _log({'batch': batch, 'event': 'step2_3_done', 'result': step3})
            if int(step3['batch_id']) != batch:
                raise RuntimeError(f'batch mismatch after step2/3: expected {batch}, got {step3["batch_id"]}')

        if _phase_order(phase) <= _phase_order('step4'):
            step4 = run_enrichment_pipeline()
            _log({'batch': batch, 'event': 'step4_done', 'result': step4})
            if int(step4['batch_id']) != batch:
                raise RuntimeError(f'batch mismatch after step4: expected {batch}, got {step4["batch_id"]}')

        # Whether Step 4 was just run or already completed before resume, enforce
        # the same runbook cleanup before Step 5.
        _cleanup_after_step4()
        _log({'batch': batch, 'event': 'cleanup_after_step4_done'})

        step5 = run_maintenance_pipeline()
        _log({'batch': batch, 'event': 'step5_done', 'result': step5})
        if int(step5['batch_id']) != batch:
            raise RuntimeError(f'batch mismatch after step5: expected {batch}, got {step5["batch_id"]}')

        _cleanup_after_step5()
        _log({'batch': batch, 'event': 'cleanup_after_step5_done'})
        _log({'batch': batch, 'event': 'done', 'at': datetime.now().isoformat()})


if __name__ == '__main__':
    main()
