#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT_DIR / "backend" / "sql"
DEFAULT_DSN = os.environ.get(
    "REBUILD3_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2",
)

SQL_BOOTSTRAP_FILES = [
    SQL_DIR / "schema" / "002_timepoint_snapshot_extensions.sql",
    SQL_DIR / "govern" / "004_timepoint_snapshot_scenarios.sql",
]


def run_sql_file(dsn: str, sql_file: Path) -> None:
    subprocess.run(
        ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)],
        check=True,
    )


def fetch_bounds(conn: psycopg.Connection) -> tuple[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              min("上报时间")::text AS min_event_time,
              max("上报时间")::text AS max_event_time
            FROM rebuild2.l0_lac
            """
        )
        row = cur.fetchone()
    if not row or not row[0] or not row[1]:
        raise RuntimeError("rebuild2.l0_lac has no event_time range")
    return row[0], row[1]


def call_scenario(
    conn: psycopg.Connection,
    *,
    scenario_key: str,
    init_days: int,
    step_hours: int,
    window_start: str,
    window_end: str,
    note: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CALL rebuild3_meta.run_timepoint_snapshot_scenario(
              %(scenario_key)s,
              %(init_days)s,
              %(step_hours)s,
              %(window_start)s::timestamptz,
              %(window_end)s::timestamptz,
              'rebuild3-contract-v1',
              'rebuild3-rule-set-v1',
              %(note)s,
              true
            )
            """,
            {
                "scenario_key": scenario_key,
                "init_days": init_days,
                "step_hours": step_hours,
                "window_start": window_start,
                "window_end": window_end,
                "note": note,
            },
        )


def print_scenario_summary(conn: psycopg.Connection, scenario_key: str) -> None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              r.run_id,
              r.status,
              r.window_start,
              r.window_end,
              r.init_days,
              r.step_hours,
              count(*) AS batch_count,
              min(b.snapshot_at) AS first_snapshot_at,
              max(b.snapshot_at) AS last_snapshot_at
            FROM rebuild3_meta.run r
            JOIN rebuild3_meta.batch b
              ON b.run_id = r.run_id
            WHERE r.scenario_key = %(scenario_key)s
            GROUP BY r.run_id, r.status, r.window_start, r.window_end, r.init_days, r.step_hours
            ORDER BY max(b.snapshot_at) DESC
            LIMIT 1
            """,
            {"scenario_key": scenario_key},
        )
        row = cur.fetchone()
    if row:
        print(
            "scenario=%s run_id=%s status=%s batch_count=%s first_snapshot=%s last_snapshot=%s"
            % (
                scenario_key,
                row["run_id"],
                row["status"],
                row["batch_count"],
                row["first_snapshot_at"],
                row["last_snapshot_at"],
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rebuild3 timepoint snapshot scenarios.")
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN")
    parser.add_argument(
        "--mode",
        choices=("smoke", "scenarios"),
        default="scenarios",
        help="smoke: short validation run, scenarios: full 1d/2d scenario reruns",
    )
    args = parser.parse_args()

    for sql_file in SQL_BOOTSTRAP_FILES:
        run_sql_file(args.dsn, sql_file)

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        min_event_time, max_event_time = fetch_bounds(conn)
        print(f"event_time_range={min_event_time}..{max_event_time}")

        if args.mode == "smoke":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT (
                      min("上报时间") + interval '36 hours'
                    )::text
                    FROM rebuild2.l0_lac
                    """
                )
                smoke_end = cur.fetchone()[0]
            call_scenario(
                conn,
                scenario_key="SMOKE_INIT1D_STEP2H",
                init_days=1,
                step_hours=2,
                window_start=min_event_time,
                window_end=smoke_end,
                note="smoke run for timepoint snapshot schema/procedure validation",
            )
            print_scenario_summary(conn, "SMOKE_INIT1D_STEP2H")
            return 0

        call_scenario(
            conn,
            scenario_key="INIT1D_STEP2H",
            init_days=1,
            step_hours=2,
            window_start=min_event_time,
            window_end=max_event_time,
            note="scenario run: 1-day initialization + rolling 2-hour snapshots",
        )
        print_scenario_summary(conn, "INIT1D_STEP2H")

        call_scenario(
            conn,
            scenario_key="INIT2D_STEP2H",
            init_days=2,
            step_hours=2,
            window_start=min_event_time,
            window_end=max_event_time,
            note="scenario run: 2-day initialization + rolling 2-hour snapshots",
        )
        print_scenario_summary(conn, "INIT2D_STEP2H")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

