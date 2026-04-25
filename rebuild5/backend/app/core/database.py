"""Database helpers for rb5."""
from __future__ import annotations

import datetime as dt
import decimal
import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

from .settings import settings

if TYPE_CHECKING:
    import psycopg


_CTAS_RE = re.compile(
    r"^\s*CREATE\s+(?P<unlogged>UNLOGGED\s+)?TABLE\s+"
    r"(?P<relation>[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)"
    r"\s+AS\s+(?P<select_sql>.+?)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_TABLE_RE = re.compile(
    r"^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+IF\s+NOT\s+EXISTS\s+"
    r"(?P<relation>[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*\(",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_SCHEMA_RE = re.compile(
    r"^\s*CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+(?P<schema>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_REFERENCE_TABLES = {
    "step4_fill_coverage",
    "trusted_lac_library",
    "trusted_snapshot_lac",
    "snapshot_diff_lac",
}


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


def _strip_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def _relation_parts(relation: str) -> tuple[str | None, str]:
    if "." not in relation:
        return None, relation
    schema, table = relation.split(".", 1)
    return schema, table


def _is_citus_available(cur: "psycopg.Cursor[Any]") -> bool:
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'citus')")
    return bool(cur.fetchone()[0])


def _is_distributed_or_reference(cur: "psycopg.Cursor[Any]", relation: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_dist_partition
            WHERE logicalrelid = to_regclass(%s)
        )
        """,
        (relation,),
    )
    return bool(cur.fetchone()[0])


def _relation_columns(cur: "psycopg.Cursor[Any]", relation: str) -> set[str]:
    cur.execute(
        """
        SELECT a.attname
        FROM pg_attribute a
        WHERE a.attrelid = to_regclass(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        (relation,),
    )
    return {str(row[0]) for row in cur.fetchall()}


def _distributed_target_exists(cur: "psycopg.Cursor[Any]", relation: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_dist_partition
            WHERE logicalrelid = to_regclass(%s)
              AND partmethod = 'h'
        )
        """,
        (relation,),
    )
    return bool(cur.fetchone()[0])


def _distribution_key(table_name: str, columns: set[str]) -> str | None:
    if table_name in {"raw_gps", "raw_gps_full_backup"} and "did" in columns:
        return "did"
    if table_name.startswith("etl_") and "dev_id" in columns:
        return "dev_id"
    if table_name.startswith("etl_step1_") and "dev_id" in columns:
        return "dev_id"
    if table_name.startswith("etl_cumulative_") and "dev_id" in columns:
        return "dev_id"
    if table_name in {"trusted_bs_library", "trusted_snapshot_bs", "snapshot_diff_bs", "bs_centroid_detail"} and "bs_id" in columns:
        return "bs_id"
    if table_name.endswith("_bs") and "bs_id" in columns and "cell_id" not in columns:
        return "bs_id"
    if "cell_id" in columns:
        return "cell_id"
    if "donor_cell_id" in columns:
        return "donor_cell_id"
    if "dev_id" in columns:
        return "dev_id"
    if "did" in columns:
        return "did"
    return None


def _ensure_citus_layout(cur: "psycopg.Cursor[Any]", relation: str) -> None:
    schema, table = _relation_parts(relation)
    if schema not in {"rb5", "rb5_meta", "rb5_tmp"}:
        return
    if not _is_citus_available(cur) or _is_distributed_or_reference(cur, relation):
        return

    if schema == "rb5_meta" or table in _REFERENCE_TABLES or table.endswith("_lac"):
        cur.execute("SELECT create_reference_table(%s)", (relation,))
        return

    columns = _relation_columns(cur, relation)
    dist_key = _distribution_key(table, columns)
    if dist_key is None:
        cur.execute("SELECT create_reference_table(%s)", (relation,))
        return

    colocate_with: str | None = None
    if relation != "rb5.raw_gps_full_backup":
        if dist_key in {"did", "dev_id"} and _distributed_target_exists(cur, "rb5.raw_gps_full_backup"):
            colocate_with = "rb5.raw_gps_full_backup"

    if colocate_with:
        cur.execute(
            "SELECT create_distributed_table(%s, %s, colocate_with => %s)",
            (relation, dist_key, colocate_with),
        )
    else:
        cur.execute("SELECT create_distributed_table(%s, %s)", (relation, dist_key))


def _execute_ctas_as_distributed(
    cur: "psycopg.Cursor[Any]",
    sql: str,
    params: tuple[Any, ...] | None,
) -> bool:
    match = _CTAS_RE.match(sql)
    if not match:
        return False

    relation = match.group("relation")
    select_sql = _strip_sql(match.group("select_sql"))
    unlogged = "UNLOGGED " if match.group("unlogged") else ""

    cur.execute(f"CREATE {unlogged}TABLE {relation} AS {select_sql} WITH NO DATA", params)
    _ensure_citus_layout(cur, relation)
    cur.execute(f"INSERT INTO {relation} {select_sql}", params)
    return True


def _ensure_layout_after_create(cur: "psycopg.Cursor[Any]", sql: str) -> None:
    match = _CREATE_TABLE_RE.match(sql)
    if match:
        _ensure_citus_layout(cur, match.group("relation"))


def execute(sql: str, params: tuple[Any, ...] | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if _execute_ctas_as_distributed(cur, sql, params):
                return
            cur.execute(sql, params)
            _ensure_layout_after_create(cur, sql)


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
