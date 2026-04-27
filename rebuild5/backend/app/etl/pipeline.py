"""Step 1 ETL pipeline orchestrator for rb5."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from .clean import CLEAN_STAGE_TABLE
from .fill import FINAL_OUTPUT_TABLE
from .parse import step1_parse
from . import clean as clean_module
from . import fill as fill_module
from . import parse as parse_module
from .clean import step1_clean
from .fill import step1_fill
from .source_prep import DATASET_KEY
from ..core.citus_compat import execute_distributed_insert
from ..core.database import _CTAS_RE, _ensure_citus_layout, _strip_sql, execute, fetchone, get_conn


PARALLEL_40_SETUP = [
    'SET max_parallel_workers_per_gather = 40',
    'SET max_parallel_workers = 40',
    'SET max_parallel_maintenance_workers = 16',
    'SET parallel_tuple_cost = 0.01',
    'SET parallel_setup_cost = 100',
]


def _execute_step1_parallel(sql: str, params: tuple[Any, ...] | None = None) -> None:
    match = _CTAS_RE.match(sql)
    if not match:
        execute(sql, params)
        return

    relation = match.group('relation')
    select_sql = _strip_sql(match.group('select_sql'))
    unlogged = 'UNLOGGED ' if match.group('unlogged') else ''
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'CREATE {unlogged}TABLE {relation} AS {select_sql} WITH NO DATA', params)
            _ensure_citus_layout(cur, relation)
    execute_distributed_insert(
        f'INSERT INTO {relation} {select_sql}',
        params=params,
        session_setup_sqls=PARALLEL_40_SETUP,
    )


@contextmanager
def _step1_parallel_execution() -> Any:
    originals = {
        parse_module: parse_module.execute,
        clean_module: clean_module.execute,
        fill_module: fill_module.execute,
    }
    try:
        for module in originals:
            module.execute = _execute_step1_parallel
        yield
    finally:
        for module, original_execute in originals.items():
            module.execute = original_execute


ODS_RULE_STAT_DEFS = {
    'ODS-019': 'CellInfos 陈旧缓存对象过滤',
    'ODS-020': 'SS1 批内锚点陈旧子记录过滤',
    'ODS-021': 'SS1 无配套信号 Cell 过滤',
    'ODS-022': 'SS1 全 -1 Sig 条目过滤',
    'ODS-023b': 'LTE FDD 异常 TA 置空',
    'ODS-024b': 'CellInfos 同记录同 Cell 重复对象去重',
}


def run_step1_pipeline() -> dict[str, Any]:
    run_id = f"step1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    started_at = datetime.now()
    try:
        with _step1_parallel_execution():
            parse_result = step1_parse()
            clean_result = step1_clean()
            before_coverage = calculate_field_coverage(CLEAN_STAGE_TABLE, filled=False)
            fill_result = step1_fill()
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std ON rb5.etl_cleaned (event_time_std)')
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rb5.etl_cleaned (record_id)')
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_source_uid ON rb5.etl_cleaned (source_row_uid)')
        execute(
            """
            CREATE INDEX IF NOT EXISTS idx_etl_cleaned_path_lookup
            ON rb5.etl_cleaned (operator_filled, lac_filled, bs_id, cell_id, tech_norm)
            """
        )
        execute(
            """
            CREATE INDEX IF NOT EXISTS idx_etl_cleaned_dim_time
            ON rb5.etl_cleaned (operator_filled, lac_filled, cell_id, tech_norm, event_time_std)
            """
        )
        execute('ANALYZE rb5.etl_cleaned')
        after_coverage = calculate_field_coverage(FINAL_OUTPUT_TABLE, filled=True)
        # Drop intermediate tables no longer needed
        execute('DROP TABLE IF EXISTS rb5.etl_clean_stage')
        execute('DROP TABLE IF EXISTS rb5.etl_ci')
        execute('DROP TABLE IF EXISTS rb5.etl_ss1')
        source_count = fetchone('SELECT COUNT(*) AS cnt FROM rb5_meta.source_registry WHERE dataset_key = %s', (DATASET_KEY,))
        _save_stats(
            run_id=run_id,
            started_at=started_at,
            parse_result=parse_result,
            clean_result=clean_result,
            fill_result=fill_result,
            source_count=int(source_count['cnt']) if source_count else 0,
            before_coverage=before_coverage,
            after_coverage=after_coverage,
        )
        batch_id = _infer_rule_stats_batch_id()
        _save_rule_stats(batch_id=batch_id, parse_result=parse_result, clean_result=clean_result)

        summary = {
            'run_id': run_id,
            'dataset_key': DATASET_KEY,
            'batch_id': batch_id,
            'raw_record_count': parse_result['input_count'],
            'parsed_record_count': parse_result['output_count'],
            'cleaned_record_count': clean_result['output_count'],
            'filled_record_count': fill_result['output_count'],
            'clean_deleted_count': clean_result['filtered_count'],
            'clean_pass_rate': round(clean_result['output_count'] / clean_result['input_count'], 4) if clean_result['input_count'] else 0,
        }
        _write_run_log(run_id=run_id, status='completed', result_summary=summary)
        return summary
    except Exception as exc:
        _write_run_log(
            run_id=run_id,
            status='failed',
            result_summary={'dataset_key': DATASET_KEY},
            error=str(exc),
        )
        raise


def ensure_etl_rule_stats_schema() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5_meta.etl_rule_stats (
            batch_id INTEGER NOT NULL,
            rule_code TEXT NOT NULL,
            rule_desc TEXT,
            hit_count BIGINT NOT NULL,
            total_rows BIGINT,
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (batch_id, rule_code)
        )
        """
    )
    execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_dist_partition
                WHERE logicalrelid = 'rb5_meta.etl_rule_stats'::regclass
            ) THEN
                PERFORM create_reference_table('rb5_meta.etl_rule_stats');
            END IF;
        END $$;
        """
    )


def _infer_rule_stats_batch_id() -> int:
    """Infer the current daily batch from rb5.raw_gps when callers do not pass it."""
    row = fetchone(
        """
        WITH cur_day AS (
            SELECT MIN((ts::timestamp)::date) AS day
            FROM rb5.raw_gps
            WHERE ts ~ '^\\d{4}-\\d{2}-\\d{2}'
        ),
        all_days AS (
            SELECT DISTINCT (ts::timestamp)::date AS day
            FROM rb5.raw_gps_full_backup
            WHERE ts ~ '^\\d{4}-\\d{2}-\\d{2}'
        )
        SELECT COUNT(*) FILTER (WHERE all_days.day <= cur_day.day) AS batch_id
        FROM all_days, cur_day
        """
    )
    if row and row.get('batch_id'):
        return int(row['batch_id'])
    fallback = fetchone('SELECT COALESCE(MAX(batch_id), 0) + 1 AS batch_id FROM rb5_meta.etl_rule_stats')
    return int(fallback['batch_id']) if fallback else 1


def _save_rule_stats(*, batch_id: int, parse_result: dict[str, Any], clean_result: dict[str, Any]) -> None:
    ensure_etl_rule_stats_schema()
    details = parse_result.get('details') or {}
    ods_019 = details.get('ods_019') or {}
    ss1_rules = details.get('ss1_rules') or {}
    clean_by_id = {rule['id']: rule for rule in clean_result.get('rules', [])}

    rows = [
        (
            batch_id,
            'ODS-019',
            ODS_RULE_STAT_DEFS['ODS-019'],
            int(ods_019.get('dropped_stale_count') or 0),
            int(ods_019.get('total_connected_objects') or 0),
        ),
        (
            batch_id,
            'ODS-020',
            ODS_RULE_STAT_DEFS['ODS-020'],
            int((ss1_rules.get('ods_020') or {}).get('dropped_subrec') or 0),
            int((ss1_rules.get('ods_020') or {}).get('total_subrec') or 0),
        ),
        (
            batch_id,
            'ODS-021',
            ODS_RULE_STAT_DEFS['ODS-021'],
            0,
            int((ss1_rules.get('ods_020') or {}).get('total_subrec') or 0),
        ),
        (
            batch_id,
            'ODS-022',
            ODS_RULE_STAT_DEFS['ODS-022'],
            int((ss1_rules.get('ods_022') or {}).get('dropped_sigs') or 0),
            int((ss1_rules.get('ods_022') or {}).get('total_sigs') or 0),
        ),
        (
            batch_id,
            'ODS-023b',
            ODS_RULE_STAT_DEFS['ODS-023b'],
            int((clean_by_id.get('ODS-023b') or {}).get('violations') or 0),
            int(clean_result.get('input_count') or 0),
        ),
        (
            batch_id,
            'ODS-024b',
            ODS_RULE_STAT_DEFS['ODS-024b'],
            int((ods_019.get('ods_024b') or {}).get('dropped_duplicate_count') or 0),
            int((ods_019.get('ods_024b') or {}).get('total_after_ods019') or 0),
        ),
    ]
    execute('DELETE FROM rb5_meta.etl_rule_stats WHERE batch_id = %s', (batch_id,))
    for row in rows:
        execute(
            """
            INSERT INTO rb5_meta.etl_rule_stats
                (batch_id, rule_code, rule_desc, hit_count, total_rows, recorded_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (batch_id, rule_code) DO UPDATE SET
                rule_desc = EXCLUDED.rule_desc,
                hit_count = EXCLUDED.hit_count,
                total_rows = EXCLUDED.total_rows,
                recorded_at = EXCLUDED.recorded_at
            """,
            row,
        )


def calculate_field_coverage(table_name: str, *, filled: bool) -> dict[str, float]:
    lon_col = 'lon_filled' if filled else 'lon_raw'
    lat_col = 'lat_filled' if filled else 'lat_raw'
    operator_col = 'operator_filled' if filled else 'operator_code'
    lac_col = 'lac_filled' if filled else 'lac'
    rsrp_col = 'rsrp_filled' if filled else 'rsrp'
    row = fetchone(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE cell_id IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS cell_id,
            COUNT(*) FILTER (WHERE {lac_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lac,
            COUNT(*) FILTER (WHERE {operator_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS operator_code,
            COUNT(*) FILTER (WHERE tech_norm IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS tech_norm,
            COUNT(*) FILTER (WHERE {lon_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lon_raw,
            COUNT(*) FILTER (WHERE {lat_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lat_raw,
            COUNT(*) FILTER (WHERE {rsrp_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS rsrp,
            COUNT(*) FILTER (WHERE rsrq IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS rsrq,
            COUNT(*) FILTER (WHERE sinr IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS sinr,
            COUNT(*) FILTER (WHERE pressure IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS pressure,
            COUNT(*) FILTER (WHERE bs_id IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS bs_id,
            COUNT(*) FILTER (WHERE {lon_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lon_filled,
            COUNT(*) FILTER (WHERE {lat_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lat_filled,
            COUNT(*) FILTER (WHERE {operator_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS operator_filled,
            COUNT(*) FILTER (WHERE {lac_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS lac_filled,
            COUNT(*) FILTER (WHERE {rsrp_col} IS NOT NULL)::float / NULLIF(COUNT(*), 0) AS rsrp_filled
        FROM {table_name}
        """
    ) or {}
    return {key: round(float(value or 0), 4) for key, value in row.items()}


def _save_stats(
    *,
    run_id: str,
    started_at: datetime,
    parse_result: dict[str, Any],
    clean_result: dict[str, Any],
    fill_result: dict[str, Any],
    source_count: int,
    before_coverage: dict[str, float],
    after_coverage: dict[str, float],
) -> None:
    execute('DELETE FROM rb5_meta.step1_run_stats WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rb5_meta.step1_run_stats (
            run_id, dataset_key, status, started_at, finished_at,
            raw_record_count, parsed_record_count, cleaned_record_count, filled_record_count,
            clean_deleted_count, clean_pass_rate, source_count,
            parse_details, fill_details, field_coverage_before, field_coverage, clean_rules
        ) VALUES (
            %s, %s, %s, %s, NOW(),
            %s, %s, %s, %s,
            %s, %s, %s,
            %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
        )
        """,
        (
            run_id,
            DATASET_KEY,
            'completed',
            started_at.strftime('%Y-%m-%d %H:%M:%S'),
            parse_result['input_count'],
            parse_result['output_count'],
            clean_result['output_count'],
            fill_result['output_count'],
            clean_result['filtered_count'],
            round(clean_result['output_count'] / clean_result['input_count'], 4) if clean_result['input_count'] else 0,
            source_count,
            json.dumps(parse_result['details'], ensure_ascii=False),
            json.dumps({'before': fill_result['before'], 'after': fill_result['after']}, ensure_ascii=False),
            json.dumps(before_coverage, ensure_ascii=False),
            json.dumps(after_coverage, ensure_ascii=False),
            json.dumps(clean_result['rules'], ensure_ascii=False),
        ),
    )


def _write_run_log(
    *,
    run_id: str,
    status: str,
    result_summary: dict[str, Any],
    error: str | None = None,
) -> None:
    execute('DELETE FROM rb5_meta.run_log WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rb5_meta.run_log (
            run_id, run_type, dataset_key, snapshot_version, status,
            started_at, finished_at, step_chain, result_summary, error
        ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, %s::jsonb, %s)
        """,
        (
            run_id,
            'step1',
            DATASET_KEY,
            'v0',
            status,
            'parse -> clean -> fill',
            json.dumps(result_summary, ensure_ascii=False),
            error,
        ),
    )
    execute(
        """
        UPDATE rb5_meta.dataset_registry
        SET last_run_id = %s,
            last_snapshot_version = %s,
            last_run_status = %s,
            last_updated_at = %s
        WHERE dataset_key = %s
        """,
        (
            run_id,
            'v0',
            status,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            DATASET_KEY,
        ),
    )
