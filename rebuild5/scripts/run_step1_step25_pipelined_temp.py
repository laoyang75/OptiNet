#!/usr/bin/env python3
"""Temporary pipelined rerun: Step1 producer + Step2-5 consumer.

Design goals:
1. Keep Step1 implementation unchanged.
2. Freeze each raw-day Step1 output into a staging table.
3. Feed Step2-5 from a cumulative view over the completed Step1 stages so the
   consumer preserves the current serial script semantics.
4. Allow resuming an in-flight formal rerun from the next unfinished batch.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5488/yangca',
)

from rebuild5.backend.app.core.database import execute, fetchone
from rebuild5.backend.app.etl.fill import COMPAT_FILLED_VIEW
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
from rebuild5.backend.app.etl.source_prep import prepare_current_dataset
from rebuild5.backend.app.profile.pipeline import relation_exists
from rebuild5.scripts import run_daily_increment_batch_loop as step25_loop
from rebuild5.scripts.run_daily_increment_batch_loop import _iter_days, _load_dataset_day_range
from rebuild5.scripts.run_step1_to_step5_daily_loop import FULL_RAW_BACKUP, _materialize_raw_gps_day


STAGING_SCHEMA = 'rb5_tmp'
LOG_DIR = REPO_ROOT / 'rebuild5' / 'runtime' / 'logs'
RESET_SQL_PATH = Path(__file__).with_name('reset_step1_to_step5_for_full_rerun_v3.sql')


@dataclass
class ConsumerJob:
    day: date
    batch_id: int
    input_relation: str


@dataclass
class RunningConsumer:
    job: ConsumerJob
    process: subprocess.Popen[str]
    log_fp: object
    log_path: Path


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-day', help='inclusive raw-day bucket, e.g. 2025-12-03')
    parser.add_argument('--end-day', help='inclusive raw-day bucket, e.g. 2025-12-07')
    parser.add_argument(
        '--start-batch-id',
        type=int,
        default=1,
        help='expected batch id for start-day; use 3 to resume from batch3',
    )
    parser.add_argument(
        '--skip-prepare',
        action='store_true',
        help='reuse existing rb5.raw_gps_full_backup instead of running prepare_current_dataset',
    )
    parser.add_argument(
        '--skip-reset-step2-5',
        action='store_true',
        help='keep existing Step1-5 state; intended only for controlled resume',
    )
    parser.add_argument(
        '--base-step1-relation',
        help='existing cumulative Step1 relation to prepend to all later cumulative views',
    )
    parser.add_argument(
        '--plan-only',
        action='store_true',
        help='print the selected range and exit without touching data',
    )
    parser.add_argument('--consumer', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--consumer-day', help=argparse.SUPPRESS)
    parser.add_argument('--consumer-batch-id', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--consumer-input-relation', help=argparse.SUPPRESS)
    return parser.parse_args()


def _sanitize_day(day: date) -> str:
    return day.strftime('%Y%m%d')


def _step1_stage_table(day: date) -> str:
    return f'{STAGING_SCHEMA}.etl_step1_{_sanitize_day(day)}'


def _cumulative_view(day: date) -> str:
    return f'{STAGING_SCHEMA}.etl_cumulative_{_sanitize_day(day)}'


def _consumer_log_path(day: date, batch_id: int) -> Path:
    return LOG_DIR / f'pipelined_step25_batch{batch_id}_{_sanitize_day(day)}.log'


def _ensure_staging_schema() -> None:
    execute(f'CREATE SCHEMA IF NOT EXISTS {STAGING_SCHEMA}')


def _reset_full_rerun_state() -> None:
    sql = RESET_SQL_PATH.read_text(encoding='utf-8')
    for stmt in (part.strip() for part in sql.split(';')):
        if stmt:
            execute(stmt)


def _prepare_or_reuse_full_raw(*, skip_prepare: bool) -> dict[str, object]:
    if skip_prepare:
        if not relation_exists(FULL_RAW_BACKUP):
            if relation_exists('rb5.raw_gps'):
                execute(f'ALTER TABLE rb5.raw_gps RENAME TO raw_gps_full_backup')
            else:
                raise RuntimeError(f'{FULL_RAW_BACKUP} does not exist; cannot skip prepare')
        row = fetchone(f'SELECT COUNT(*) AS cnt FROM {FULL_RAW_BACKUP}')
        return {'reused_backup_rows': int(row['cnt']) if row else 0}

    _log({'event': 'prepare_dataset_start'})
    prepare_result = prepare_current_dataset()
    _log({'event': 'prepare_dataset_done', 'result': prepare_result})
    if relation_exists(FULL_RAW_BACKUP):
        execute(f'DROP TABLE IF EXISTS {FULL_RAW_BACKUP}')
    execute(f'ALTER TABLE rb5.raw_gps RENAME TO raw_gps_full_backup')
    return prepare_result


def _drop_staging_objects(days: Iterable[date]) -> None:
    staged_days = list(days)
    for day in staged_days:
        execute(f'DROP VIEW IF EXISTS {_cumulative_view(day)}')
    for day in staged_days:
        execute(f'DROP TABLE IF EXISTS {_step1_stage_table(day)}')


def _snapshot_step1_stage(day: date) -> tuple[str, int]:
    suffix = _sanitize_day(day)
    table_name = _step1_stage_table(day)
    execute(f'DROP TABLE IF EXISTS {table_name}')
    execute(f'CREATE UNLOGGED TABLE {table_name} AS SELECT * FROM rb5.etl_cleaned')
    execute(f'ALTER TABLE {table_name} SET (autovacuum_enabled = false)')
    execute(f'CREATE INDEX idx_tmp_{suffix}_evt ON {table_name} (event_time_std)')
    execute(f'CREATE INDEX idx_tmp_{suffix}_rec ON {table_name} (record_id)')
    execute(
        f"""
        CREATE INDEX idx_tmp_{suffix}_lookup
        ON {table_name} (operator_filled, lac_filled, bs_id, cell_id, tech_norm)
        """
    )
    execute(f'ANALYZE {table_name}')
    row = fetchone(f'SELECT COUNT(*) AS cnt FROM {table_name}')
    return table_name, int(row['cnt']) if row else 0


def _build_cumulative_view(day: date, staged_days: list[date], *, base_relation: str | None) -> str:
    view_name = _cumulative_view(day)
    parts: list[str] = []
    if base_relation:
        parts.append(f'SELECT * FROM {base_relation}')
    parts.extend(f'SELECT * FROM {_step1_stage_table(staged_day)}' for staged_day in staged_days)
    if not parts:
        raise RuntimeError('cannot build cumulative view without any source relation')
    execute(f'DROP VIEW IF EXISTS {view_name}')
    execute(f'CREATE VIEW {view_name} AS ' + '\nUNION ALL\n'.join(parts))
    return view_name


def _materialize_final_etl(final_relation: str, *, cleanup_partial_base: str | None) -> None:
    execute(f'DROP VIEW IF EXISTS {COMPAT_FILLED_VIEW}')
    execute('DROP TABLE IF EXISTS rb5.etl_cleaned')
    execute(f'CREATE TABLE rb5.etl_cleaned AS SELECT * FROM {final_relation}')
    execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std ON rb5.etl_cleaned (event_time_std)')
    execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rb5.etl_cleaned (record_id)')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_etl_cleaned_path_lookup
        ON rb5.etl_cleaned (operator_filled, lac_filled, bs_id, cell_id, tech_norm)
        """
    )
    execute(f'CREATE VIEW {COMPAT_FILLED_VIEW} AS SELECT * FROM rb5.etl_cleaned')
    execute('ANALYZE rb5.etl_cleaned')
    if cleanup_partial_base and relation_exists(cleanup_partial_base):
        execute(f'DROP TABLE IF EXISTS {cleanup_partial_base}')


def _restore_raw_gps() -> None:
    if relation_exists('rb5.raw_gps'):
        execute('DROP TABLE IF EXISTS rb5.raw_gps')
    if relation_exists(FULL_RAW_BACKUP):
        execute(f'ALTER TABLE {FULL_RAW_BACKUP} RENAME TO raw_gps')
        execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_record_id ON rb5.raw_gps ("记录数唯一标识")')
        execute('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rb5.raw_gps (ts)')
        execute('ANALYZE rb5.raw_gps')


def _relation_kind(relation_name: str) -> str | None:
    row = fetchone(
        """
        SELECT c.relkind
        FROM pg_class c
        WHERE c.oid = to_regclass(%s)
        """,
        (relation_name,),
    )
    return str(row['relkind']) if row and row.get('relkind') is not None else None


def _run_consumer(day: date, *, batch_id: int, input_relation: str) -> None:
    original_ensure = step25_loop.ensure_daily_indices

    def _ensure_indices_view_safe(*, input_relation: str) -> None:
        relkind = _relation_kind(input_relation)
        if relkind in {'r', 'p', 'm'}:
            original_ensure(input_relation=input_relation)
            return
        if not relation_exists(input_relation):
            raise RuntimeError(f'{input_relation} does not exist')

    step25_loop.ensure_daily_indices = _ensure_indices_view_safe
    try:
        step25_loop.run_daily_batches(
            input_relation=input_relation,
            start_day=day,
            end_day=day,
            plan_only=False,
            start_batch_id=batch_id,
            resume_phase='step2_3',
        )
    finally:
        step25_loop.ensure_daily_indices = original_ensure


def _launch_consumer(job: ConsumerJob) -> RunningConsumer:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _consumer_log_path(job.day, job.batch_id)
    log_fp = log_path.open('w', encoding='utf-8')
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        '--consumer',
        '--consumer-day', job.day.isoformat(),
        '--consumer-batch-id', str(job.batch_id),
        '--consumer-input-relation', job.input_relation,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )
    _log({
        'event': 'consumer_started',
        'day': job.day.isoformat(),
        'batch_id': job.batch_id,
        'input_relation': job.input_relation,
        'log_path': str(log_path),
        'pid': proc.pid,
    })
    return RunningConsumer(job=job, process=proc, log_fp=log_fp, log_path=log_path)


def _reap_consumer(consumer: RunningConsumer | None) -> RunningConsumer | None:
    if consumer is None:
        return None
    returncode = consumer.process.poll()
    if returncode is None:
        return consumer
    consumer.log_fp.close()
    if returncode != 0:
        raise RuntimeError(
            f'consumer failed for day {consumer.job.day.isoformat()} batch {consumer.job.batch_id}; '
            f'see {consumer.log_path}'
        )
    _log({
        'event': 'consumer_done',
        'day': consumer.job.day.isoformat(),
        'batch_id': consumer.job.batch_id,
        'log_path': str(consumer.log_path),
    })
    return None


def _run_orchestrator(args: argparse.Namespace) -> None:
    dataset_start, dataset_end = _load_dataset_day_range()
    start_day = date.fromisoformat(args.start_day) if args.start_day else dataset_start
    end_day = date.fromisoformat(args.end_day) if args.end_day else dataset_end
    days = _iter_days(start_day, end_day)
    base_relation = args.base_step1_relation

    if base_relation and not relation_exists(base_relation):
        raise RuntimeError(f'base step1 relation {base_relation} does not exist')
    if base_relation and not args.skip_reset_step2_5:
        raise RuntimeError('base-step1-relation requires --skip-reset-step2-5')

    _log({
        'event': 'pipeline_plan',
        'start_day': start_day.isoformat(),
        'end_day': end_day.isoformat(),
        'days': [day.isoformat() for day in days],
        'start_batch_id': args.start_batch_id,
        'skip_prepare': args.skip_prepare,
        'skip_reset_step2_5': args.skip_reset_step2_5,
        'base_step1_relation': base_relation,
    })
    if args.plan_only:
        return

    prepare_result = _prepare_or_reuse_full_raw(skip_prepare=args.skip_prepare)
    _log({'event': 'full_raw_backup_ready', 'result': prepare_result})

    _ensure_staging_schema()
    _drop_staging_objects(days)

    if not args.skip_reset_step2_5:
        _reset_full_rerun_state()
        _log({'event': 'reset_full_rerun_done', 'sql': RESET_SQL_PATH.name})

    ready_jobs: deque[ConsumerJob] = deque()
    running_consumer: RunningConsumer | None = None
    staged_days: list[date] = []
    final_relation = base_relation

    try:
        for offset, day in enumerate(days):
            running_consumer = _reap_consumer(running_consumer)

            batch_id = args.start_batch_id + offset
            raw_count = _materialize_raw_gps_day(day)
            _log({'event': 'raw_gps_day_ready', 'day': day.isoformat(), 'batch_id': batch_id, 'raw_count': raw_count})

            step1 = run_step1_pipeline()
            stage_table, stage_rows = _snapshot_step1_stage(day)
            staged_days.append(day)
            final_relation = _build_cumulative_view(day, staged_days, base_relation=base_relation)
            _log({
                'event': 'step1_stage_ready',
                'day': day.isoformat(),
                'batch_id': batch_id,
                'step1': step1,
                'stage_table': stage_table,
                'stage_rows': stage_rows,
                'cumulative_relation': final_relation,
            })

            ready_jobs.append(ConsumerJob(day=day, batch_id=batch_id, input_relation=final_relation))
            running_consumer = _reap_consumer(running_consumer)
            if running_consumer is None and ready_jobs:
                running_consumer = _launch_consumer(ready_jobs.popleft())

        while ready_jobs or running_consumer is not None:
            running_consumer = _reap_consumer(running_consumer)
            if running_consumer is None and ready_jobs:
                running_consumer = _launch_consumer(ready_jobs.popleft())
            if running_consumer is not None:
                time.sleep(5)

        if final_relation is None:
            raise RuntimeError('no final cumulative relation was produced')
        _materialize_final_etl(final_relation, cleanup_partial_base=base_relation)
        _restore_raw_gps()
        _drop_staging_objects(days)
        _log({'event': 'pipeline_finalize_done', 'final_relation': final_relation})
    finally:
        running_consumer = _reap_consumer(running_consumer)


def main() -> None:
    args = _parse_args()
    if args.consumer:
        if not args.consumer_day or args.consumer_batch_id is None or not args.consumer_input_relation:
            raise RuntimeError('consumer mode requires day, batch-id and input-relation')
        _run_consumer(
            date.fromisoformat(args.consumer_day),
            batch_id=args.consumer_batch_id,
            input_relation=args.consumer_input_relation,
        )
        return
    _run_orchestrator(args)


if __name__ == '__main__':
    main()
