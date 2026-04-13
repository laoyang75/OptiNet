#!/usr/bin/env python3
"""Run Step 5 against a tiny isolated sample database.

This script creates a scratch database, seeds a compact Step 5 fixture,
runs both per-phase checks and the full Step 5 pipeline, and prints a JSON
report with timings and output counts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_BASE_DSN = os.getenv(
    'REBUILD5_PG_DSN',
    'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2',
)
DEFAULT_SCRATCH_DB = 'ip_loc2_step5_smoke'
BATCH_ID = 101
SNAPSHOT_VERSION = f'v{BATCH_ID}'
PREV_SNAPSHOT_VERSION = 'v0'
DATASET_KEY = 'beijing_7d'


@dataclass(frozen=True)
class SnapshotCell:
    operator_code: str
    operator_cn: str
    lac: int
    bs_id: int
    cell_id: int
    tech_norm: str
    lifecycle_state: str
    center_lon: float
    center_lat: float
    p50_radius_m: float
    p90_radius_m: float
    position_grade: str
    gps_confidence: str
    signal_confidence: str
    independent_obs: int
    distinct_dev_id: int
    gps_valid_count: int
    active_days: int
    observed_span_hours: float
    rsrp_avg: float
    rsrq_avg: float
    sinr_avg: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dsn', default=DEFAULT_BASE_DSN)
    parser.add_argument('--scratch-db', default=DEFAULT_SCRATCH_DB)
    parser.add_argument(
        '--mode',
        choices=('all', 'phases', 'full'),
        default='all',
        help='Run phase checks only, full pipeline only, or both (default).',
    )
    return parser.parse_args()


def _make_dsns(base_dsn: str, scratch_db: str) -> tuple[str, str]:
    parts = conninfo_to_dict(base_dsn)
    if not parts.get('dbname'):
        raise ValueError(f'Base DSN is missing dbname: {base_dsn}')
    admin_dsn = make_conninfo(
        host=parts.get('host'),
        port=parts.get('port'),
        user=parts.get('user'),
        password=parts.get('password'),
        dbname='postgres',
    )
    scratch_dsn = make_conninfo(
        host=parts.get('host'),
        port=parts.get('port'),
        user=parts.get('user'),
        password=parts.get('password'),
        dbname=scratch_db,
    )
    return admin_dsn, scratch_dsn


def _reset_database(admin_dsn: str, scratch_db: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (scratch_db,),
            )
            cur.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(scratch_db)))
            cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(scratch_db)))


def _load_runtime(scratch_dsn: str) -> dict[str, Any]:
    os.environ['REBUILD5_PG_DSN'] = scratch_dsn

    from rebuild5.backend.app.core.database import execute, fetchall, fetchone
    from rebuild5.backend.app.enrichment.schema import ensure_enrichment_schema
    from rebuild5.backend.app.etl.source_prep import bootstrap_metadata_tables
    from rebuild5.backend.app.maintenance.cell_maintain import (
        compute_drift_metrics,
        compute_gps_anomaly_summary,
    )
    from rebuild5.backend.app.maintenance.collision import detect_collisions
    from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
    from rebuild5.backend.app.maintenance.publish_bs_lac import (
        publish_bs_centroid_detail,
        publish_bs_library,
        publish_cell_centroid_detail,
        publish_lac_library,
    )
    from rebuild5.backend.app.maintenance.publish_cell import publish_cell_library
    from rebuild5.backend.app.maintenance.schema import ensure_maintenance_schema
    from rebuild5.backend.app.maintenance.writers import collect_step5_stats
    from rebuild5.backend.app.maintenance.window import (
        build_daily_centroids,
        recalculate_cell_metrics,
        refresh_sliding_window,
    )
    from rebuild5.backend.app.profile.logic import flatten_antitoxin_thresholds, load_antitoxin_params
    from rebuild5.backend.app.profile.pipeline import ensure_profile_schema, relation_exists

    return {
        'execute': execute,
        'fetchall': fetchall,
        'fetchone': fetchone,
        'ensure_enrichment_schema': ensure_enrichment_schema,
        'bootstrap_metadata_tables': bootstrap_metadata_tables,
        'compute_drift_metrics': compute_drift_metrics,
        'compute_gps_anomaly_summary': compute_gps_anomaly_summary,
        'detect_collisions': detect_collisions,
        'run_maintenance_pipeline': run_maintenance_pipeline,
        'publish_bs_centroid_detail': publish_bs_centroid_detail,
        'publish_bs_library': publish_bs_library,
        'publish_cell_centroid_detail': publish_cell_centroid_detail,
        'publish_lac_library': publish_lac_library,
        'publish_cell_library': publish_cell_library,
        'ensure_maintenance_schema': ensure_maintenance_schema,
        'collect_step5_stats': collect_step5_stats,
        'refresh_sliding_window': refresh_sliding_window,
        'build_daily_centroids': build_daily_centroids,
        'recalculate_cell_metrics': recalculate_cell_metrics,
        'flatten_antitoxin_thresholds': flatten_antitoxin_thresholds,
        'load_antitoxin_params': load_antitoxin_params,
        'ensure_profile_schema': ensure_profile_schema,
        'relation_exists': relation_exists,
    }


def _bootstrap_schemas(runtime: dict[str, Any]) -> None:
    runtime['bootstrap_metadata_tables']()
    runtime['ensure_profile_schema']()
    runtime['ensure_enrichment_schema']()
    runtime['ensure_maintenance_schema']()


def _sample_snapshot_cells() -> list[SnapshotCell]:
    return [
        SnapshotCell(
            operator_code='CMCC',
            operator_cn='中国移动',
            lac=1001,
            bs_id=5001,
            cell_id=101,
            tech_norm='LTE',
            lifecycle_state='qualified',
            center_lon=116.4000,
            center_lat=39.9000,
            p50_radius_m=120.0,
            p90_radius_m=180.0,
            position_grade='good',
            gps_confidence='high',
            signal_confidence='high',
            independent_obs=12,
            distinct_dev_id=4,
            gps_valid_count=12,
            active_days=3,
            observed_span_hours=48.0,
            rsrp_avg=-88.0,
            rsrq_avg=-10.0,
            sinr_avg=14.0,
        ),
        SnapshotCell(
            operator_code='CMCC',
            operator_cn='中国移动',
            lac=1001,
            bs_id=5001,
            cell_id=102,
            tech_norm='LTE',
            lifecycle_state='excellent',
            center_lon=116.4500,
            center_lat=39.9300,
            p50_radius_m=900.0,
            p90_radius_m=1400.0,
            position_grade='excellent',
            gps_confidence='high',
            signal_confidence='high',
            independent_obs=12,
            distinct_dev_id=4,
            gps_valid_count=12,
            active_days=3,
            observed_span_hours=48.0,
            rsrp_avg=-82.0,
            rsrq_avg=-9.0,
            sinr_avg=18.0,
        ),
        SnapshotCell(
            operator_code='CMCC',
            operator_cn='中国移动',
            lac=1002,
            bs_id=5002,
            cell_id=101,
            tech_norm='LTE',
            lifecycle_state='qualified',
            center_lon=116.5200,
            center_lat=39.9500,
            p50_radius_m=100.0,
            p90_radius_m=150.0,
            position_grade='qualified',
            gps_confidence='high',
            signal_confidence='medium',
            independent_obs=12,
            distinct_dev_id=3,
            gps_valid_count=12,
            active_days=3,
            observed_span_hours=48.0,
            rsrp_avg=-91.0,
            rsrq_avg=-11.0,
            sinr_avg=11.0,
        ),
        SnapshotCell(
            operator_code='CU',
            operator_cn='中国联通',
            lac=2001,
            bs_id=6001,
            cell_id=201,
            tech_norm='LTE',
            lifecycle_state='qualified',
            center_lon=116.3500,
            center_lat=39.8800,
            p50_radius_m=90.0,
            p90_radius_m=130.0,
            position_grade='qualified',
            gps_confidence='high',
            signal_confidence='medium',
            independent_obs=12,
            distinct_dev_id=3,
            gps_valid_count=12,
            active_days=3,
            observed_span_hours=48.0,
            rsrp_avg=-95.0,
            rsrq_avg=-12.0,
            sinr_avg=10.0,
        ),
    ]


def _sample_enriched_rows() -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    anchors = {
        ('CMCC', 1001, 5001, 101): (116.4000, 39.9000),
        ('CMCC', 1001, 5001, 102): (116.4100, 39.9000),
        ('CMCC', 1002, 5002, 101): (116.5200, 39.9500),
        ('CU', 2001, 6001, 201): (116.3500, 39.8800),
    }
    ts0 = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
    source_index = 0
    for day in range(3):
        for obs_idx in range(4):
            minute = day * 24 * 60 + obs_idx * 7
            event_time = ts0 + timedelta(minutes=minute)
            for operator_code, lac, bs_id, cell_id in anchors:
                base_lon, base_lat = anchors[(operator_code, lac, bs_id, cell_id)]
                if cell_id == 102 and lac == 1001:
                    lon = base_lon + (day * 0.020) + (obs_idx - 1.5) * 0.0010
                    lat = base_lat + (day * 0.015) + (obs_idx - 1.5) * 0.0008
                else:
                    lon = base_lon + (obs_idx - 1.5) * 0.00008
                    lat = base_lat + (obs_idx - 1.5) * 0.00006
                operator_cn = '中国移动' if operator_code == 'CMCC' else '中国联通'
                source_index += 1
                rows.append(
                    (
                        BATCH_ID,
                        'enrich_sample_001',
                        DATASET_KEY,
                        f'sample-{source_index}',
                        f'record-{source_index}',
                        'step5_small_sample',
                        event_time,
                        f'dev-{cell_id % 10}-{obs_idx}',
                        operator_code,
                        operator_cn,
                        lac,
                        bs_id,
                        cell_id,
                        'LTE',
                        True,
                        lon,
                        lat,
                        lon,
                        lat,
                        'original',
                        'high',
                        -90.0 + obs_idx,
                        'original',
                        -11.0 + obs_idx * 0.2,
                        'original',
                        12.0 + obs_idx,
                        'original',
                        1000.0 + obs_idx,
                        'original',
                        operator_code,
                        'original',
                        lac,
                        'original',
                        'LTE',
                        'original',
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                )
    return rows


def _seed_sample(runtime: dict[str, Any]) -> None:
    execute = runtime['execute']
    with psycopg.connect(os.environ['REBUILD5_PG_DSN'], autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO rebuild5.enriched_records (
                    batch_id, run_id, dataset_key, source_row_uid, record_id, source_table,
                    event_time_std, dev_id,
                    operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                    gps_valid, lon_raw, lat_raw,
                    lon_final, lat_final, gps_fill_source_final, gps_fill_confidence,
                    rsrp_final, rsrp_fill_source_final,
                    rsrq_final, rsrq_fill_source_final,
                    sinr_final, sinr_fill_source_final,
                    pressure_final, pressure_fill_source_final,
                    operator_final, operator_fill_source_final,
                    lac_final, lac_fill_source_final,
                    tech_final, tech_fill_source_final,
                    donor_batch_id, donor_snapshot_version, donor_cell_id,
                    donor_lifecycle_state, donor_position_grade,
                    donor_center_lon, donor_center_lat,
                    donor_anchor_eligible, donor_baseline_eligible
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                """,
                _sample_enriched_rows(),
            )
            cur.executemany(
                """
                INSERT INTO rebuild5.trusted_snapshot_cell (
                    batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
                    operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                    lifecycle_state, is_registered, anchor_eligible, baseline_eligible,
                    is_collision_id, center_lon, center_lat, p50_radius_m, p90_radius_m,
                    position_grade, gps_confidence, signal_confidence,
                    independent_obs, distinct_dev_id, gps_valid_count, active_days,
                    observed_span_hours, rsrp_avg, rsrq_avg, sinr_avg
                ) VALUES (
                    %s, %s, %s, %s, %s, NOW(),
                    %s, %s, %s, %s, %s, %s,
                    %s, TRUE, TRUE, TRUE,
                    FALSE, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                [
                    (
                        BATCH_ID,
                        SNAPSHOT_VERSION,
                        PREV_SNAPSHOT_VERSION,
                        DATASET_KEY,
                        'profile_sample_001',
                        cell.operator_code,
                        cell.operator_cn,
                        cell.lac,
                        cell.bs_id,
                        cell.cell_id,
                        cell.tech_norm,
                        cell.lifecycle_state,
                        cell.center_lon,
                        cell.center_lat,
                        cell.p50_radius_m,
                        cell.p90_radius_m,
                        cell.position_grade,
                        cell.gps_confidence,
                        cell.signal_confidence,
                        cell.independent_obs,
                        cell.distinct_dev_id,
                        cell.gps_valid_count,
                        cell.active_days,
                        cell.observed_span_hours,
                        cell.rsrp_avg,
                        cell.rsrq_avg,
                        cell.sinr_avg,
                    )
                    for cell in _sample_snapshot_cells()
                ],
            )
    execute(
        """
        INSERT INTO rebuild5_meta.step3_run_stats (
            run_id, dataset_key, batch_id, snapshot_version, trusted_snapshot_version_prev, status,
            started_at, finished_at,
            profile_base_cell_count, mode_filtered_count, region_filtered_count, gps_filtered_count,
            evaluated_cell_count, waiting_cell_count, observing_cell_count, qualified_cell_count,
            excellent_cell_count, new_qualified_cell_count, new_excellent_cell_count,
            anchor_eligible_cell_count, bs_waiting_count, bs_observing_count, bs_qualified_count,
            lac_waiting_count, lac_observing_count, lac_qualified_count,
            waiting_pruned_cell_count, dormant_marked_count,
            snapshot_new_count, snapshot_promoted_count, snapshot_demoted_count,
            snapshot_eligibility_changed_count, snapshot_geometry_changed_count
        ) VALUES (
            %s, %s, %s, %s, %s, 'completed',
            NOW(), NOW(),
            4, 0, 0, 0,
            4, 0, 0, 3,
            1, 3, 1,
            4, 0, 2, 1,
            0, 1, 1,
            0, 0,
            4, 1, 0,
            0, 0
        )
        """,
        ('profile_sample_001', DATASET_KEY, BATCH_ID, SNAPSHOT_VERSION, PREV_SNAPSHOT_VERSION),
    )


def _truncate_step5_outputs(runtime: dict[str, Any]) -> None:
    execute = runtime['execute']
    execute('TRUNCATE rebuild5.trusted_cell_library')
    execute('TRUNCATE rebuild5.trusted_bs_library')
    execute('TRUNCATE rebuild5.trusted_lac_library')
    execute('TRUNCATE rebuild5.collision_id_list')
    execute('TRUNCATE rebuild5.cell_centroid_detail')
    execute('TRUNCATE rebuild5.bs_centroid_detail')
    execute('DROP TABLE IF EXISTS rebuild5.cell_daily_centroid')
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_window')
    execute('DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary')
    execute('DELETE FROM rebuild5_meta.step5_run_stats')


def _collect_counts(runtime: dict[str, Any]) -> dict[str, int]:
    fetchone = runtime['fetchone']
    relation_exists = runtime['relation_exists']
    tables = {
        'enriched_records': 'rebuild5.enriched_records',
        'trusted_snapshot_cell': 'rebuild5.trusted_snapshot_cell',
        'cell_sliding_window': 'rebuild5.cell_sliding_window',
        'cell_daily_centroid': 'rebuild5.cell_daily_centroid',
        'cell_metrics_window': 'rebuild5.cell_metrics_window',
        'cell_anomaly_summary': 'rebuild5.cell_anomaly_summary',
        'trusted_cell_library': 'rebuild5.trusted_cell_library',
        'collision_id_list': 'rebuild5.collision_id_list',
        'trusted_bs_library': 'rebuild5.trusted_bs_library',
        'trusted_lac_library': 'rebuild5.trusted_lac_library',
        'cell_centroid_detail': 'rebuild5.cell_centroid_detail',
        'bs_centroid_detail': 'rebuild5.bs_centroid_detail',
    }
    counts: dict[str, int] = {}
    for key, table in tables.items():
        if not relation_exists(table):
            counts[key] = 0
            continue
        row = fetchone(f'SELECT COUNT(*) AS cnt FROM {table} WHERE batch_id = %s', (BATCH_ID,))
        counts[key] = int(row['cnt']) if row else 0
    if relation_exists('rebuild5.trusted_cell_library'):
        row = fetchone(
            'SELECT COUNT(*) AS cnt FROM rebuild5.trusted_cell_library WHERE batch_id = %s AND is_multi_centroid',
            (BATCH_ID,),
        )
        counts['multi_centroid_cells'] = int(row['cnt']) if row else 0
    else:
        counts['multi_centroid_cells'] = 0
    if relation_exists('rebuild5.trusted_bs_library'):
        row = fetchone(
            """
            SELECT COUNT(*) AS cnt
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = %s
              AND classification IN ('large_spread', 'multi_centroid', 'dynamic_bs', 'collision_bs')
            """,
            (BATCH_ID,),
        )
        counts['anomalous_bs'] = int(row['cnt']) if row else 0
    else:
        counts['anomalous_bs'] = 0
    return counts


def _assert_phase_outputs(counts: dict[str, int]) -> None:
    expected = {
        'enriched_records': 48,
        'trusted_snapshot_cell': 4,
        'cell_sliding_window': 48,
        'cell_metrics_window': 4,
        'trusted_cell_library': 4,
        'collision_id_list': 1,
        'trusted_bs_library': 3,
        'trusted_lac_library': 1,
    }
    for key, minimum in expected.items():
        actual = counts.get(key, 0)
        if actual < minimum:
            raise AssertionError(f'{key} expected >= {minimum}, got {actual}')
    if counts.get('multi_centroid_cells', 0) < 1:
        raise AssertionError('expected at least one multi-centroid cell in sample output')
    if counts.get('anomalous_bs', 0) < 1:
        raise AssertionError('expected at least one anomalous BS in sample output')


def _time_phase(name: str, fn, counts_fn) -> dict[str, Any]:
    started = time.perf_counter()
    fn()
    elapsed = round(time.perf_counter() - started, 3)
    snapshot = counts_fn()
    return {'phase': name, 'seconds': elapsed, 'counts': snapshot}


def _run_phases(runtime: dict[str, Any]) -> dict[str, Any]:
    execute = runtime['execute']
    antitoxin = runtime['flatten_antitoxin_thresholds'](runtime['load_antitoxin_params']())
    report: list[dict[str, Any]] = []

    report.append(
        _time_phase(
            'refresh_sliding_window',
            lambda: runtime['refresh_sliding_window'](batch_id=BATCH_ID),
            lambda: _collect_counts(runtime),
        )
    )
    execute('CREATE INDEX IF NOT EXISTS idx_csw_cell ON rebuild5.cell_sliding_window (batch_id, operator_code, lac, bs_id, cell_id)')
    report.append(
        _time_phase(
            'build_daily_centroids',
            lambda: runtime['build_daily_centroids'](batch_id=BATCH_ID),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'recalculate_cell_metrics',
            lambda: runtime['recalculate_cell_metrics'](batch_id=BATCH_ID),
            lambda: _collect_counts(runtime),
        )
    )
    execute('CREATE INDEX IF NOT EXISTS idx_cdc_cell_date ON rebuild5.cell_daily_centroid (batch_id, operator_code, lac, cell_id, obs_date)')
    execute('CREATE INDEX IF NOT EXISTS idx_cmw_cell ON rebuild5.cell_metrics_window (batch_id, operator_code, lac, cell_id)')
    report.append(
        _time_phase(
            'compute_drift_metrics',
            lambda: runtime['compute_drift_metrics'](batch_id=BATCH_ID),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'compute_gps_anomaly_summary',
            lambda: runtime['compute_gps_anomaly_summary'](batch_id=BATCH_ID),
            lambda: _collect_counts(runtime),
        )
    )
    if runtime['relation_exists']('rebuild5.cell_anomaly_summary'):
        execute('CREATE INDEX IF NOT EXISTS idx_cas_cell ON rebuild5.cell_anomaly_summary (batch_id, operator_code, lac, cell_id)')
    report.append(
        _time_phase(
            'publish_cell_library',
            lambda: runtime['publish_cell_library'](
                run_id='maint_sample_001',
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
                snapshot_version_prev=PREV_SNAPSHOT_VERSION,
                antitoxin=antitoxin,
            ),
            lambda: _collect_counts(runtime),
        )
    )
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_collision ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, cell_id)')
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_bs ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, bs_id)')
    report.append(
        _time_phase(
            'detect_collisions',
            lambda: runtime['detect_collisions'](
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
                absolute_min_distance_m=antitoxin['absolute_collision_min_distance_m'],
            ),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'publish_cell_centroid_detail',
            lambda: runtime['publish_cell_centroid_detail'](
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
            ),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'publish_bs_library',
            lambda: runtime['publish_bs_library'](
                run_id='maint_sample_001',
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
                snapshot_version_prev=PREV_SNAPSHOT_VERSION,
                antitoxin=antitoxin,
            ),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'publish_bs_centroid_detail',
            lambda: runtime['publish_bs_centroid_detail'](
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
            ),
            lambda: _collect_counts(runtime),
        )
    )
    report.append(
        _time_phase(
            'publish_lac_library',
            lambda: runtime['publish_lac_library'](
                run_id='maint_sample_001',
                batch_id=BATCH_ID,
                snapshot_version=SNAPSHOT_VERSION,
                snapshot_version_prev=PREV_SNAPSHOT_VERSION,
            ),
            lambda: _collect_counts(runtime),
        )
    )

    counts = _collect_counts(runtime)
    _assert_phase_outputs(counts)
    return {
        'phase_timings': report,
        'final_counts': counts,
        'stats': runtime['collect_step5_stats'](
            run_id='maint_sample_001',
            batch_id=BATCH_ID,
            snapshot_version=SNAPSHOT_VERSION,
            snapshot_version_prev=PREV_SNAPSHOT_VERSION,
        ),
    }


def _run_full_pipeline(runtime: dict[str, Any]) -> dict[str, Any]:
    _truncate_step5_outputs(runtime)
    started = time.perf_counter()
    result = runtime['run_maintenance_pipeline']()
    elapsed = round(time.perf_counter() - started, 3)
    counts = _collect_counts(runtime)
    _assert_phase_outputs(counts)
    return {'seconds': elapsed, 'result': result, 'counts': counts}


def main() -> None:
    args = _parse_args()
    admin_dsn, scratch_dsn = _make_dsns(args.base_dsn, args.scratch_db)
    _reset_database(admin_dsn, args.scratch_db)
    runtime = _load_runtime(scratch_dsn)
    _bootstrap_schemas(runtime)
    _seed_sample(runtime)

    report: dict[str, Any] = {
        'scratch_db': args.scratch_db,
        'batch_id': BATCH_ID,
        'snapshot_version': SNAPSHOT_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

    if args.mode in ('all', 'phases'):
        report['phases'] = _run_phases(runtime)
    if args.mode in ('all', 'full'):
        report['full_pipeline'] = _run_full_pipeline(runtime)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
