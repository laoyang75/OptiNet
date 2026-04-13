#!/usr/bin/env python3
"""Run the full rebuild5 chain day by day: Step 1 -> Step 5.

Workflow:
1. Prepare the configured dataset into full raw_gps.
2. Keep the full raw table as a backup source.
3. For each configured day:
   - materialize that day's raw_gps slice using raw_gps.ts
   - run Step 1 on the slice
   - append the day's etl_cleaned into a cumulative table
   - run Step 2 -> Step 5 for that day
4. Restore rebuild5.raw_gps to the full prepared dataset and rebuild5.etl_cleaned
   to the cumulative 7-day output.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchone
from rebuild5.backend.app.etl.fill import COMPAT_FILLED_VIEW
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.etl.source_prep import prepare_current_dataset
from rebuild5.backend.app.profile.pipeline import relation_exists
from rebuild5.scripts.run_daily_increment_batch_loop import _load_dataset_day_range, _iter_days, run_daily_batches


os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2',
)


FULL_RAW_BACKUP = 'rebuild5.raw_gps_full_backup'
CUMULATIVE_ETL = 'rebuild5.etl_cleaned_daily_cumulative'
RESET_SQL_PATH = Path(__file__).with_name('reset_step1_to_step5_for_full_rerun_v3.sql')


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-day', help='inclusive day bucket, e.g. 2025-12-01')
    parser.add_argument('--end-day', help='inclusive day bucket, e.g. 2025-12-07')
    parser.add_argument(
        '--skip-prepare',
        action='store_true',
        help='reuse existing full raw data instead of calling prepare_current_dataset',
    )
    parser.add_argument(
        '--skip-reset-step2-5',
        action='store_true',
        help='do not clear existing Step 1-5 derived state before the run',
    )
    parser.add_argument(
        '--plan-only',
        action='store_true',
        help='print the selected day range and exit without changing data',
    )
    return parser.parse_args()


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _iso_day_bounds(day: date) -> tuple[str, str]:
    start = day.isoformat()
    end = (day + timedelta(days=1)).isoformat()
    return start, end


def _reset_full_rerun_state() -> None:
    sql = RESET_SQL_PATH.read_text(encoding='utf-8')
    statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
    for stmt in statements:
        execute(stmt)


def _ensure_full_raw_backup(*, prepare_dataset_flag: bool) -> dict[str, object] | None:
    if prepare_dataset_flag:
        _log({'event': 'prepare_dataset_start'})
        prepare_result = prepare_current_dataset()
        _log({'event': 'prepare_dataset_done', 'result': prepare_result})
        if relation_exists(FULL_RAW_BACKUP):
            execute(f'DROP TABLE IF EXISTS {FULL_RAW_BACKUP}')
        execute(f'ALTER TABLE rebuild5.raw_gps RENAME TO raw_gps_full_backup')
        return prepare_result

    if relation_exists(FULL_RAW_BACKUP):
        row = fetchone(f'SELECT COUNT(*) AS cnt FROM {FULL_RAW_BACKUP}')
        return {'reused_backup_rows': int(row["cnt"]) if row else 0}

    if not relation_exists('rebuild5.raw_gps'):
        raise RuntimeError('skip-prepare requires rebuild5.raw_gps or rebuild5.raw_gps_full_backup to exist')

    execute(f'ALTER TABLE rebuild5.raw_gps RENAME TO raw_gps_full_backup')
    row = fetchone(f'SELECT COUNT(*) AS cnt FROM {FULL_RAW_BACKUP}')
    return {'reused_backup_rows': int(row["cnt"]) if row else 0}


def _materialize_raw_gps_day(day: date) -> int:
    start_ts, end_ts = _iso_day_bounds(day)
    execute('DROP TABLE IF EXISTS rebuild5.raw_gps')
    execute(
        """
        CREATE TABLE rebuild5.raw_gps AS
        SELECT *
        FROM rebuild5.raw_gps_full_backup
        WHERE ts >= %s
          AND ts < %s
        """,
        (start_ts, end_ts),
    )
    execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_record_id ON rebuild5.raw_gps ("记录数唯一标识")')
    execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rebuild5.raw_gps (ts)')
    row = fetchone('SELECT COUNT(*) AS cnt FROM rebuild5.raw_gps')
    return int(row['cnt']) if row else 0


def _append_day_etl_to_cumulative() -> int:
    if not relation_exists(CUMULATIVE_ETL):
        execute(f'CREATE TABLE {CUMULATIVE_ETL} AS SELECT * FROM rebuild5.etl_cleaned WHERE false')
    execute(f'INSERT INTO {CUMULATIVE_ETL} SELECT * FROM rebuild5.etl_cleaned')
    row = fetchone(f'SELECT COUNT(*) AS cnt FROM {CUMULATIVE_ETL}')
    return int(row['cnt']) if row else 0


def _finalize_cumulative_outputs() -> None:
    execute('DROP TABLE IF EXISTS rebuild5.raw_gps')
    execute(f'ALTER TABLE {FULL_RAW_BACKUP} RENAME TO raw_gps')

    execute(f'DROP VIEW IF EXISTS {COMPAT_FILLED_VIEW}')
    execute('DROP TABLE IF EXISTS rebuild5.etl_cleaned')
    execute(f'ALTER TABLE {CUMULATIVE_ETL} RENAME TO etl_cleaned')
    execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std ON rebuild5.etl_cleaned (event_time_std)')
    execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rebuild5.etl_cleaned (record_id)')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_etl_cleaned_path_lookup
        ON rebuild5.etl_cleaned (operator_filled, lac_filled, bs_id, cell_id, tech_norm)
        """
    )
    execute(f'CREATE VIEW {COMPAT_FILLED_VIEW} AS SELECT * FROM rebuild5.etl_cleaned')
    execute('ANALYZE rebuild5.raw_gps')
    execute('ANALYZE rebuild5.etl_cleaned')


def main() -> None:
    args = _parse_args()
    dataset_start, dataset_end = _load_dataset_day_range()
    start_day = date.fromisoformat(args.start_day) if args.start_day else dataset_start
    end_day = date.fromisoformat(args.end_day) if args.end_day else dataset_end
    days = _iter_days(start_day, end_day)

    _log({
        'event': 'full_chain_plan',
        'start_day': start_day.isoformat(),
        'end_day': end_day.isoformat(),
        'days': [day.isoformat() for day in days],
        'skip_prepare': args.skip_prepare,
        'skip_reset_step2_5': args.skip_reset_step2_5,
        'reset_sql': str(RESET_SQL_PATH.name),
    })
    if args.plan_only:
        return

    backup_result = _ensure_full_raw_backup(prepare_dataset_flag=not args.skip_prepare)
    _log({'event': 'full_raw_backup_ready', 'result': backup_result or {}})

    if relation_exists(CUMULATIVE_ETL):
        execute(f'DROP TABLE IF EXISTS {CUMULATIVE_ETL}')

    if not args.skip_reset_step2_5:
        _reset_full_rerun_state()
        _log({'event': 'reset_full_rerun_done', 'sql': RESET_SQL_PATH.name})

    try:
        for offset, day in enumerate(days, start=1):
            raw_count = _materialize_raw_gps_day(day)
            _log({'event': 'raw_gps_day_ready', 'day': day.isoformat(), 'batch_id': offset, 'raw_count': raw_count})

            step1 = run_step1_pipeline()
            cumulative_count = _append_day_etl_to_cumulative()
            _log({
                'event': 'step1_done',
                'day': day.isoformat(),
                'batch_id': offset,
                'step1': step1,
                'cumulative_etl_count': cumulative_count,
            })

            run_daily_batches(
                input_relation='rebuild5.etl_cleaned',
                start_day=day,
                end_day=day,
                plan_only=False,
                start_batch_id=offset,
                resume_phase='step2_3',
            )

        _finalize_cumulative_outputs()
        _log({'event': 'finalize_done'})
    finally:
        if relation_exists(FULL_RAW_BACKUP) and not relation_exists('rebuild5.raw_gps'):
            execute(f'ALTER TABLE {FULL_RAW_BACKUP} RENAME TO raw_gps')


if __name__ == '__main__':
    main()
