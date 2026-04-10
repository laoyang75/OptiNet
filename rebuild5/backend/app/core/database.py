"""Database helpers for rebuild5."""
from __future__ import annotations

import datetime as dt
import decimal
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

from .settings import settings

if TYPE_CHECKING:
    import psycopg


@contextmanager
def get_conn() -> Iterator["psycopg.Connection"]:
    import psycopg

    conn = psycopg.connect(settings.pg_dsn, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def _serialize(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def fetchall(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            columns = [col.name for col in cur.description]
            return [
                {name: _serialize(value) for name, value in zip(columns, row)}
                for row in cur.fetchall()
            ]


def fetchone(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple[Any, ...] | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def paginate(
    sql: str,
    params: tuple[Any, ...] | None = None,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Execute a SELECT with pagination, returning rows + page meta."""
    count_sql = f"SELECT COUNT(*) AS total FROM ({sql}) _paged"
    total_row = fetchone(count_sql, params)
    total_count = int(total_row['total']) if total_row else 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    offset = (page - 1) * page_size
    paged_sql = f"{sql} LIMIT {page_size} OFFSET {offset}"
    rows = fetchall(paged_sql, params)

    return {
        'items': rows,
        'page': page,
        'page_size': page_size,
        'total_count': total_count,
        'total_pages': total_pages,
    }
