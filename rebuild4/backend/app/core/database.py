import os
import datetime
import decimal
import psycopg
from contextlib import contextmanager

DSN = os.getenv(
    "REBUILD4_PG_DSN",
    "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2",
)

@contextmanager
def get_conn():
    conn = psycopg.connect(DSN, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def _serialize(val):
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, datetime.timedelta):
        return str(val)
    if isinstance(val, decimal.Decimal):
        return float(val)
    return val


def fetchall(sql: str, params=None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            cols = [d.name for d in cur.description]
            return [{c: _serialize(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def fetchone(sql: str, params=None) -> dict | None:
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=None) -> None:
    """执行 SQL（DDL/DML），不返回结果。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
