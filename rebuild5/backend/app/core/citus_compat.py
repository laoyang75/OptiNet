"""Citus-safe DML helper.

Extracted from the publish_bs_lac fix5 D session-settings hotfix.

psycopg3's default cursor can use server-side parameter binding. Citus
distributed planning can reject large parameterized INSERT...SELECT statements
with CTEs, as seen in fix5 D batch 4. ClientCursor plus mogrify forces
client-side binding so the coordinator receives a fully inlined SQL statement.
"""
from __future__ import annotations

from typing import Any

from psycopg import ClientCursor

from .database import get_conn


def execute_distributed_insert(
    sql: str,
    *,
    params: tuple[Any, ...] | None = None,
    session_setup_sqls: list[str] | None = None,
) -> None:
    """Citus-safe INSERT...SELECT / DML entry point.

    Use for parameterized DML targeting distributed rb5 tables, especially
    INSERT INTO rb5.<distributed_table> SELECT ... statements with CTEs.

    Do not use this for regular SELECT fetches, Citus metadata function calls,
    or simple no-params DDL/INSERT paths that can stay on core.database.execute.
    """
    setup = list(session_setup_sqls or [])
    with get_conn() as conn:
        with ClientCursor(conn) as cur:
            for stmt in setup:
                cur.execute(stmt)
            if params:
                cur.execute(cur.mogrify(sql, params))
            else:
                cur.execute(sql)
            for stmt in reversed(setup):
                if stmt.upper().lstrip().startswith('SET '):
                    cur.execute(f"RESET {stmt.split()[1]}")
