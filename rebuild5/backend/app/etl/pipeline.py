"""Step 1 ETL pipeline orchestrator for rb5."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .clean import CLEAN_STAGE_TABLE
from .fill import FINAL_OUTPUT_TABLE
from .parse import step1_parse
from .clean import step1_clean
from .fill import step1_fill
from .source_prep import DATASET_KEY
from ..core.database import execute, fetchone


def run_step1_pipeline() -> dict[str, Any]:
    run_id = f"step1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    started_at = datetime.now()
    try:
        parse_result = step1_parse()
        clean_result = step1_clean()
        before_coverage = calculate_field_coverage(CLEAN_STAGE_TABLE, filled=False)
        fill_result = step1_fill()
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std ON rb5.etl_cleaned (event_time_std)')
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

        summary = {
            'run_id': run_id,
            'dataset_key': DATASET_KEY,
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
