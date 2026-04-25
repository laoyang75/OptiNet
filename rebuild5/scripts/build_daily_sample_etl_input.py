#!/usr/bin/env python3
"""Build a sample table from Step 1 output for fast testing.

Supported modes:
1. `per_day_cap` (default): cap each stored `event_time_std` day to a fixed row count.
2. `top_lacs`: choose the top-N high-volume `lac_filled` values and copy all rows
   for those LACs into the sample table. This is the preferred end-to-end sample
   because it preserves cross-day accumulation inside a stable area slice.
3. `hybrid_top_lacs_random`: include all rows for the chosen top-N LACs, then
   top up each day with deterministic pseudo-random rows from the remaining
   population until the daily cap is reached.
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
from rebuild5.backend.app.profile.pipeline import relation_exists


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


def build_sample_table(
    *,
    source_relation: str,
    target_relation: str,
    start_day: date,
    end_day: date,
    rows_per_day: int,
) -> list[dict[str, object]]:
    if not relation_exists(source_relation):
        raise RuntimeError(f'{source_relation} does not exist')

    execute(f'DROP TABLE IF EXISTS {target_relation}')
    execute(f'CREATE UNLOGGED TABLE {target_relation} AS SELECT * FROM {source_relation} WHERE false')
    execute(f'ALTER TABLE {target_relation} SET (autovacuum_enabled = false)')
    index_prefix = target_relation.replace('.', '_').replace('"', '').replace('-', '_')

    day_stats: list[dict[str, object]] = []
    for day in _iter_days(start_day, end_day):
        start_ts = _day_start_ts(day)
        end_ts = _day_start_ts(day + timedelta(days=1))
        total_row = fetchone(
            f"""
            SELECT COUNT(*) AS cnt
            FROM {source_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )
        total_count = int(total_row['cnt']) if total_row else 0
        execute(
            f"""
            INSERT INTO {target_relation}
            SELECT *
            FROM {source_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
            LIMIT %s
            """,
            (start_ts.isoformat(), end_ts.isoformat(), rows_per_day),
        )
        sample_row = fetchone(
            f"""
            SELECT COUNT(*) AS cnt
            FROM {target_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )
        sampled_count = int(sample_row['cnt']) if sample_row else 0
        day_stats.append({
            'day': day.isoformat(),
            'source_count': total_count,
            'sample_count': sampled_count,
        })

    execute(f'CREATE INDEX {index_prefix}_event_time_std ON {target_relation} (event_time_std)')
    execute(f'CREATE INDEX {index_prefix}_cell_id ON {target_relation} (cell_id)')
    execute(f'CREATE INDEX {index_prefix}_op_lac_cell ON {target_relation} (operator_filled, lac_filled, cell_id)')
    execute(f'CREATE INDEX {index_prefix}_record_id ON {target_relation} (record_id)')
    execute(f'ANALYZE {target_relation}')
    return day_stats


def build_top_lac_sample_table(
    *,
    source_relation: str,
    target_relation: str,
    start_day: date,
    end_day: date,
    top_lac_count: int,
    min_rows_per_lac: int,
) -> dict[str, object]:
    if not relation_exists(source_relation):
        raise RuntimeError(f'{source_relation} does not exist')

    start_ts = _day_start_ts(start_day)
    end_ts = _day_start_ts(end_day + timedelta(days=1))
    top_lacs = fetchall(
        f"""
        SELECT
            lac_filled AS lac,
            COUNT(*) AS record_count,
            COUNT(DISTINCT cell_id) AS distinct_cells,
            COUNT(DISTINCT operator_filled) AS operators
        FROM {source_relation}
        WHERE event_time_std >= %s
          AND event_time_std < %s
          AND lac_filled IS NOT NULL
        GROUP BY lac_filled
        HAVING COUNT(*) >= %s
        ORDER BY record_count DESC
        LIMIT {top_lac_count}
        """,
        (start_ts.isoformat(), end_ts.isoformat(), min_rows_per_lac),
    )
    if not top_lacs:
        raise RuntimeError('no LACs matched the requested top_lac sample criteria')

    lac_list_sql = ', '.join(str(int(row['lac'])) for row in top_lacs)
    execute(f'DROP TABLE IF EXISTS {target_relation}')
    execute(
        f"""
        CREATE UNLOGGED TABLE {target_relation} AS
        SELECT *
        FROM {source_relation}
        WHERE event_time_std >= %s
          AND event_time_std < %s
          AND lac_filled IN ({lac_list_sql})
        """,
        (start_ts.isoformat(), end_ts.isoformat()),
    )
    execute(f'ALTER TABLE {target_relation} SET (autovacuum_enabled = false)')
    index_prefix = target_relation.replace('.', '_').replace('"', '').replace('-', '_')
    execute(f'CREATE INDEX {index_prefix}_event_time_std ON {target_relation} (event_time_std)')
    execute(f'CREATE INDEX {index_prefix}_cell_id ON {target_relation} (cell_id)')
    execute(f'CREATE INDEX {index_prefix}_op_lac_cell ON {target_relation} (operator_filled, lac_filled, cell_id)')
    execute(f'CREATE INDEX {index_prefix}_record_id ON {target_relation} (record_id)')
    execute(f'ANALYZE {target_relation}')

    total_row = fetchone(f'SELECT COUNT(*) AS cnt FROM {target_relation}')
    day_rows = fetchall(
        f"""
        SELECT to_char(event_time_std, 'YYYY-MM-DD') AS day, COUNT(*) AS cnt
        FROM {target_relation}
        GROUP BY 1
        ORDER BY 1
        """
    )
    return {
        'top_lacs': [
            {
                'lac': int(row['lac']),
                'record_count': int(row['record_count']),
                'distinct_cells': int(row['distinct_cells']),
                'operators': int(row['operators']),
            }
            for row in top_lacs
        ],
        'total_rows': int(total_row['cnt']) if total_row else 0,
        'days': [{'day': str(row['day']), 'sample_count': int(row['cnt'])} for row in day_rows],
    }


def build_hybrid_sample_table(
    *,
    source_relation: str,
    target_relation: str,
    start_day: date,
    end_day: date,
    rows_per_day: int,
    top_lac_count: int,
    min_rows_per_lac: int,
) -> dict[str, object]:
    if not relation_exists(source_relation):
        raise RuntimeError(f'{source_relation} does not exist')

    start_ts = _day_start_ts(start_day)
    end_ts = _day_start_ts(end_day + timedelta(days=1))
    top_lacs = fetchall(
        f"""
        SELECT
            lac_filled AS lac,
            COUNT(*) AS record_count,
            COUNT(DISTINCT cell_id) AS distinct_cells,
            COUNT(DISTINCT operator_filled) AS operators
        FROM {source_relation}
        WHERE event_time_std >= %s
          AND event_time_std < %s
          AND lac_filled IS NOT NULL
        GROUP BY lac_filled
        HAVING COUNT(*) >= %s
        ORDER BY record_count DESC
        LIMIT {top_lac_count}
        """,
        (start_ts.isoformat(), end_ts.isoformat(), min_rows_per_lac),
    )
    if not top_lacs:
        raise RuntimeError('no LACs matched the requested hybrid sample criteria')

    lac_list_sql = ', '.join(str(int(row['lac'])) for row in top_lacs)
    execute(f'DROP TABLE IF EXISTS {target_relation}')
    execute(f'CREATE UNLOGGED TABLE {target_relation} AS SELECT * FROM {source_relation} WHERE false')
    execute(f'ALTER TABLE {target_relation} SET (autovacuum_enabled = false)')

    day_stats: list[dict[str, object]] = []
    for day in _iter_days(start_day, end_day):
        day_start = _day_start_ts(day)
        day_end = _day_start_ts(day + timedelta(days=1))
        execute(
            f"""
            INSERT INTO {target_relation}
            SELECT *
            FROM {source_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
              AND lac_filled IN ({lac_list_sql})
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        fixed_row = fetchone(
            f"""
            SELECT COUNT(*) AS cnt
            FROM {target_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        fixed_count = int(fixed_row['cnt']) if fixed_row else 0
        random_needed = max(rows_per_day - fixed_count, 0)
        if random_needed > 0:
            execute(
                f"""
                INSERT INTO {target_relation}
                SELECT *
                FROM {source_relation}
                WHERE event_time_std >= %s
                  AND event_time_std < %s
                  AND (lac_filled IS NULL OR lac_filled NOT IN ({lac_list_sql}))
                ORDER BY md5(COALESCE(record_id, '') || '-' || COALESCE(cell_id::text, ''))
                LIMIT %s
                """,
                (day_start.isoformat(), day_end.isoformat(), random_needed),
            )
        total_row = fetchone(
            f"""
            SELECT COUNT(*) AS cnt
            FROM {target_relation}
            WHERE event_time_std >= %s
              AND event_time_std < %s
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        total_count = int(total_row['cnt']) if total_row else 0
        day_stats.append({
            'day': day.isoformat(),
            'fixed_count': fixed_count,
            'random_count': max(total_count - fixed_count, 0),
            'sample_count': total_count,
        })

    index_prefix = target_relation.replace('.', '_').replace('"', '').replace('-', '_')
    execute(f'CREATE INDEX {index_prefix}_event_time_std ON {target_relation} (event_time_std)')
    execute(f'CREATE INDEX {index_prefix}_cell_id ON {target_relation} (cell_id)')
    execute(f'CREATE INDEX {index_prefix}_op_lac_cell ON {target_relation} (operator_filled, lac_filled, cell_id)')
    execute(f'CREATE INDEX {index_prefix}_record_id ON {target_relation} (record_id)')
    execute(f'ANALYZE {target_relation}')

    total_row = fetchone(f'SELECT COUNT(*) AS cnt FROM {target_relation}')
    return {
        'top_lacs': [
            {
                'lac': int(row['lac']),
                'record_count': int(row['record_count']),
                'distinct_cells': int(row['distinct_cells']),
                'operators': int(row['operators']),
            }
            for row in top_lacs
        ],
        'total_rows': int(total_row['cnt']) if total_row else 0,
        'days': day_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-relation', default='rb5.etl_cleaned')
    parser.add_argument('--target-relation', default='rb5.etl_cleaned_daily_sample_1m')
    parser.add_argument(
        '--sample-mode',
        choices=('per_day_cap', 'top_lacs', 'hybrid_top_lacs_random'),
        default='per_day_cap',
    )
    parser.add_argument('--rows-per-day', type=int, default=1_000_000)
    parser.add_argument('--top-lac-count', type=int, default=10)
    parser.add_argument('--min-rows-per-lac', type=int, default=100_000)
    parser.add_argument('--start-day')
    parser.add_argument('--end-day')
    args = parser.parse_args()

    dataset_start, dataset_end = _load_dataset_day_range()
    start_day = date.fromisoformat(args.start_day) if args.start_day else dataset_start
    end_day = date.fromisoformat(args.end_day) if args.end_day else dataset_end

    if args.sample_mode == 'top_lacs':
        result = build_top_lac_sample_table(
            source_relation=args.source_relation,
            target_relation=args.target_relation,
            start_day=start_day,
            end_day=end_day,
            top_lac_count=args.top_lac_count,
            min_rows_per_lac=args.min_rows_per_lac,
        )
        _log({
            'event': 'sample_table_ready',
            'sample_mode': args.sample_mode,
            'source_relation': args.source_relation,
            'target_relation': args.target_relation,
            **result,
        })
        return

    if args.sample_mode == 'hybrid_top_lacs_random':
        result = build_hybrid_sample_table(
            source_relation=args.source_relation,
            target_relation=args.target_relation,
            start_day=start_day,
            end_day=end_day,
            rows_per_day=args.rows_per_day,
            top_lac_count=args.top_lac_count,
            min_rows_per_lac=args.min_rows_per_lac,
        )
        _log({
            'event': 'sample_table_ready',
            'sample_mode': args.sample_mode,
            'source_relation': args.source_relation,
            'target_relation': args.target_relation,
            'rows_per_day': args.rows_per_day,
            **result,
        })
        return

    day_stats = build_sample_table(
        source_relation=args.source_relation,
        target_relation=args.target_relation,
        start_day=start_day,
        end_day=end_day,
        rows_per_day=args.rows_per_day,
    )
    total_row = fetchone(f'SELECT COUNT(*) AS cnt FROM {args.target_relation}')
    _log({
        'event': 'sample_table_ready',
        'sample_mode': args.sample_mode,
        'source_relation': args.source_relation,
        'target_relation': args.target_relation,
        'rows_per_day': args.rows_per_day,
        'total_rows': int(total_row['cnt']) if total_row else 0,
        'days': day_stats,
    })


if __name__ == '__main__':
    main()
