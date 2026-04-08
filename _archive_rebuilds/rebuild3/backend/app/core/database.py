from __future__ import annotations

import atexit
from contextlib import contextmanager
import threading

import psycopg

from app.core.config import settings

_thread_local = threading.local()


def _new_conn() -> psycopg.Connection:
    return psycopg.connect(settings.database_dsn, autocommit=True)


def _thread_conn() -> psycopg.Connection:
    conn = getattr(_thread_local, 'conn', None)
    if conn is None or conn.closed:
        conn = _new_conn()
        _thread_local.conn = conn
    return conn


def _close_thread_conn() -> None:
    conn = getattr(_thread_local, 'conn', None)
    if conn is not None and not conn.closed:
        conn.close()


atexit.register(_close_thread_conn)


@contextmanager
def get_conn():
    conn = _thread_conn()
    try:
        yield conn
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
