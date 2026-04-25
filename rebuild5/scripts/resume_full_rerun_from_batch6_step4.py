#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5488/yangca',
)

from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.scripts import run_daily_increment_batch_loop as step25_loop
from rebuild5.scripts.run_step1_to_step5_daily_loop import (
    _append_day_etl_to_cumulative,
    _finalize_cumulative_outputs,
    _materialize_raw_gps_day,
)


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def main() -> None:
    day6 = date(2025, 12, 6)
    day7 = date(2025, 12, 7)

    _log({'event': 'resume_batch6_step4_start'})
    step25_loop.run_daily_batches(
        input_relation='rb5.etl_cleaned',
        start_day=day6,
        end_day=day6,
        plan_only=False,
        start_batch_id=6,
        resume_phase='step4',
    )
    _log({'event': 'resume_batch6_step4_done'})

    raw_count = _materialize_raw_gps_day(day7)
    _log({'event': 'raw_gps_day_ready', 'day': day7.isoformat(), 'batch_id': 7, 'raw_count': raw_count})

    step1 = run_step1_pipeline()
    cumulative_count = _append_day_etl_to_cumulative()
    _log({
        'event': 'step1_done',
        'day': day7.isoformat(),
        'batch_id': 7,
        'step1': step1,
        'cumulative_etl_count': cumulative_count,
    })

    step25_loop.run_daily_batches(
        input_relation='rb5.etl_cleaned',
        start_day=day7,
        end_day=day7,
        plan_only=False,
        start_batch_id=7,
        resume_phase='step2_3',
    )
    _log({'event': 'batch7_full_done'})

    _finalize_cumulative_outputs()
    _log({'event': 'finalize_done'})


if __name__ == '__main__':
    main()
