#!/usr/bin/env python3
"""Run rebuild5 batches in true daily-increment semantics.

This driver reuses the existing Step 1 output (`rb5.etl_cleaned`) and
replays Step 2 -> Step 5 day by day by materializing one stored `event_time_std`
day into `rb5.step2_batch_input` for each batch.

Important constraints:
1. This script assumes Step 1 has already completed.
2. It refuses to run if Step 2-5 state from an earlier run still exists.
3. It cuts by the stored `event_time_std` day buckets as-is; it does not apply
   additional timezone conversion.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

import yaml

os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5488/yangca',
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rebuild5.backend.app.core.database import execute, fetchall, fetchone
from rebuild5.backend.app.core.settings import settings
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
from rebuild5.backend.app.profile.pipeline import (
    STEP2_INPUT_SCOPE_RELATION,
    get_latest_batch_id,
    get_latest_published_batch_id,
    relation_exists,
    run_profile_pipeline,
)


RESET_SQL_PATH = Path(__file__).with_name('reset_step2_to_step5_for_daily_rebaseline.sql')


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _load_dataset_day_range() -> tuple[date, date]:
    cfg_path = settings.config_dir / 'dataset.yaml'
    with cfg_path.open('r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}
    time_range = str(cfg.get('time_range', '')).strip()
    match = re.match(r'^\s*(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})\s*$', time_range)
    if not match:
        raise RuntimeError(f'cannot parse dataset time_range: {time_range!r}')
    return date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))


def _iter_days(start_day: date, end_day: date) -> list[date]:
    if end_day < start_day:
        raise RuntimeError('end_day must be >= start_day')
    days: list[date] = []
    current = start_day
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def _day_start_ts(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def ensure_daily_indices(*, input_relation: str) -> None:
    if relation_exists(input_relation):
        execute(f'ANALYZE {input_relation}')
    if input_relation == 'rb5.etl_cleaned':
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std ON rb5.etl_cleaned (event_time_std)')
    if input_relation == 'rb5.etl_cleaned' and relation_exists('rb5.raw_gps'):
        execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rb5.raw_gps (ts)')
        execute('ANALYZE rb5.raw_gps')


def summarize_day_counts(*, input_relation: str, start_day: date, end_day: date) -> list[dict[str, object]]:
    start_ts = _day_start_ts(start_day)
    end_ts = _day_start_ts(end_day + timedelta(days=1))
    rows = fetchall(
        f"""
        SELECT
            to_char(event_time_std, 'YYYY-MM-DD') AS batch_day,
            COUNT(*) AS record_count
        FROM {input_relation}
        WHERE event_time_std >= %s
          AND event_time_std < %s
        GROUP BY 1
        ORDER BY 1
        """,
        (start_ts.isoformat(), end_ts.isoformat()),
    )
    return [
        {'day': str(row['batch_day']), 'record_count': int(row['record_count'])}
        for row in rows
    ]


def _assert_ready_for_daily_rebaseline(*, input_relation: str, allow_existing_state: bool) -> None:
    if not relation_exists(input_relation):
        raise RuntimeError(f'{input_relation} does not exist; prepare Step 1 output or a sample input first')

    state_checks = [
        ('trusted_snapshot_cell', get_latest_batch_id()),
        ('trusted_cell_library', get_latest_published_batch_id()),
    ]
    if relation_exists('rb5_meta.step2_run_stats'):
        row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5_meta.step2_run_stats')
        state_checks.append(('step2_run_stats', int(row['batch_id']) if row else 0))
    if relation_exists('rb5_meta.step3_run_stats'):
        row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5_meta.step3_run_stats')
        state_checks.append(('step3_run_stats', int(row['batch_id']) if row else 0))
    if relation_exists('rb5_meta.step4_run_stats'):
        row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5_meta.step4_run_stats')
        state_checks.append(('step4_run_stats', int(row['batch_id']) if row else 0))
    if relation_exists('rb5_meta.step5_run_stats'):
        row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5_meta.step5_run_stats')
        state_checks.append(('step5_run_stats', int(row['batch_id']) if row else 0))

    dirty = {name: batch_id for name, batch_id in state_checks if batch_id > 0}
    if allow_existing_state:
        return
    if dirty:
        raise RuntimeError(
            'existing Step 2-5 state detected; reset downstream state before daily rebaseline. '
            f'Use {RESET_SQL_PATH}. Found: {dirty}'
        )


def _drop_step2_scope() -> None:
    execute(f'DROP TABLE IF EXISTS {STEP2_INPUT_SCOPE_RELATION}')


def materialize_step2_scope(*, day: date, input_relation: str) -> int:
    start_ts = _day_start_ts(day)
    end_ts = _day_start_ts(day + timedelta(days=1))
    _drop_step2_scope()
    execute(
        f"""
        CREATE UNLOGGED TABLE {STEP2_INPUT_SCOPE_RELATION} AS
        SELECT *
        FROM {input_relation}
        WHERE event_time_std >= %s
          AND event_time_std < %s
        """,
        (start_ts.isoformat(), end_ts.isoformat()),
    )
    execute(f'ALTER TABLE {STEP2_INPUT_SCOPE_RELATION} SET (autovacuum_enabled = false)')
    execute(f'CREATE INDEX idx_step2_batch_input_cell ON {STEP2_INPUT_SCOPE_RELATION} (cell_id)')
    execute(
        f"""
        CREATE INDEX idx_step2_batch_input_op_lac_cell
        ON {STEP2_INPUT_SCOPE_RELATION} (operator_filled, lac_filled, cell_id)
        """
    )
    execute(f'CREATE INDEX idx_step2_batch_input_record ON {STEP2_INPUT_SCOPE_RELATION} (record_id)')
    execute(f'ANALYZE {STEP2_INPUT_SCOPE_RELATION}')
    row = fetchone(f'SELECT COUNT(*) AS cnt FROM {STEP2_INPUT_SCOPE_RELATION}')
    return int(row['cnt']) if row else 0


def _cleanup_after_step4() -> None:
    for rel in (
        'rb5.path_a_records',
        'rb5._profile_seed_grid',
        'rb5._profile_primary_seed',
        'rb5._profile_seed_distance',
        'rb5._profile_core_cutoff',
        'rb5._profile_core_points',
        'rb5._profile_core_gps',
        'rb5._profile_counts',
        'rb5.profile_obs',
        'rb5.profile_base',
    ):
        execute(f'DROP TABLE IF EXISTS {rel}')


def _cleanup_after_step5() -> None:
    for rel in (
        'rb5.cell_metrics_base',
        'rb5.cell_radius_stats',
        'rb5.cell_activity_stats',
        'rb5.cell_drift_stats',
        'rb5.cell_daily_centroid',
        'rb5.cell_metrics_window',
        'rb5.cell_anomaly_summary',
        'rb5.cell_core_seed_grid',
        'rb5.cell_core_primary_seed',
        'rb5.cell_core_seed_distance',
        'rb5.cell_core_cutoff',
        'rb5.cell_core_points',
        'rb5.cell_core_gps_stats',
    ):
        execute(f'DROP TABLE IF EXISTS {rel}')


def _phase_order(phase: str) -> int:
    return {'step2_3': 0, 'step4': 1, 'step5': 2}[phase]


def run_daily_batches(
    *,
    input_relation: str,
    start_day: date,
    end_day: date,
    plan_only: bool,
    start_batch_id: int,
    resume_phase: str,
) -> None:
    ensure_daily_indices(input_relation=input_relation)
    day_counts = summarize_day_counts(input_relation=input_relation, start_day=start_day, end_day=end_day)
    _log({
        'event': 'day_plan',
        'input_relation': input_relation,
        'start_day': start_day.isoformat(),
        'end_day': end_day.isoformat(),
        'days': day_counts,
    })
    if plan_only:
        return

    _assert_ready_for_daily_rebaseline(
        input_relation=input_relation,
        allow_existing_state=(start_batch_id != 1 or resume_phase != 'step2_3'),
    )

    days = _iter_days(start_day, end_day)
    for offset, day in enumerate(days):
        expected_batch = start_batch_id + offset
        phase = resume_phase if offset == 0 else 'step2_3'

        if _phase_order(phase) <= _phase_order('step2_3'):
            scoped_count = materialize_step2_scope(day=day, input_relation=input_relation)
            if scoped_count <= 0:
                raise RuntimeError(f'no records found for day {day.isoformat()}')
            _log({
                'event': 'batch_scope_ready',
                'batch_id': expected_batch,
                'day': day.isoformat(),
                'record_count': scoped_count,
            })
            step3 = run_profile_pipeline()
            if int(step3['batch_id']) != expected_batch:
                raise RuntimeError(
                    f'step2/3 batch mismatch for {day.isoformat()}: '
                    f'expected {expected_batch}, got {step3["batch_id"]}'
                )
            _log({'event': 'step2_3_done', 'batch_id': expected_batch, 'day': day.isoformat(), 'result': step3})

        if _phase_order(phase) <= _phase_order('step4'):
            step4 = run_enrichment_pipeline()
            if int(step4['batch_id']) != expected_batch:
                raise RuntimeError(
                    f'step4 batch mismatch for {day.isoformat()}: '
                    f'expected {expected_batch}, got {step4["batch_id"]}'
                )
            _log({'event': 'step4_done', 'batch_id': expected_batch, 'day': day.isoformat(), 'result': step4})
        _cleanup_after_step4()
        _log({'event': 'cleanup_after_step4_done', 'batch_id': expected_batch, 'day': day.isoformat()})

        step5 = run_maintenance_pipeline()
        if int(step5['batch_id']) != expected_batch:
            raise RuntimeError(
                f'step5 batch mismatch for {day.isoformat()}: '
                f'expected {expected_batch}, got {step5["batch_id"]}'
            )
        _log({'event': 'step5_done', 'batch_id': expected_batch, 'day': day.isoformat(), 'result': step5})
        _cleanup_after_step5()
        _log({'event': 'cleanup_after_step5_done', 'batch_id': expected_batch, 'day': day.isoformat()})
        _drop_step2_scope()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--input-relation',
        default='rb5.etl_cleaned',
        help='source relation used to materialize each daily Step 2 scope',
    )
    parser.add_argument('--start-day', help='inclusive day bucket, e.g. 2025-12-01')
    parser.add_argument('--end-day', help='inclusive day bucket, e.g. 2025-12-07')
    parser.add_argument(
        '--start-batch-id',
        type=int,
        default=1,
        help='expected batch id for start-day; use when resuming from a partially completed daily run',
    )
    parser.add_argument(
        '--resume-phase',
        choices=('step2_3', 'step4', 'step5'),
        default='step2_3',
        help='resume phase for start-day only',
    )
    parser.add_argument(
        '--plan-only',
        action='store_true',
        help='only print day buckets and record counts; do not run Step 2-5',
    )
    args = parser.parse_args()

    dataset_start, dataset_end = _load_dataset_day_range()
    start_day = date.fromisoformat(args.start_day) if args.start_day else dataset_start
    end_day = date.fromisoformat(args.end_day) if args.end_day else dataset_end
    run_daily_batches(
        input_relation=args.input_relation,
        start_day=start_day,
        end_day=end_day,
        plan_only=args.plan_only,
        start_batch_id=args.start_batch_id,
        resume_phase=args.resume_phase,
    )


if __name__ == '__main__':
    main()
