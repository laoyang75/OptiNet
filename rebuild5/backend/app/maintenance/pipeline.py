"""Step 5 maintenance / publish pipeline — orchestrator.

Calls sub-modules in order:
  5.0  window.py         — sliding window + cell metric recalculation
  5.2  cell_maintain.py  — drift metrics + GPS anomaly summary
  5.3  publish_cell.py   — trusted_cell_library publication
  5.35 label_engine.py   — authoritative Step 5 label rewrite + cell centroid detail
  5.1  collision.py      — collision flags (runs after label_engine)
  5.4  publish_bs_lac.py — BS + LAC + centroid details
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY
from ..profile.logic import flatten_antitoxin_thresholds, load_antitoxin_params
from ..profile.pipeline import relation_exists

from .cell_maintain import compute_drift_metrics, compute_gps_anomaly_summary
from .collision import detect_collisions
from .label_engine import run_label_engine
from .publish_bs_lac import (
    publish_bs_centroid_detail,
    publish_bs_library,
    publish_lac_library,
)
from .publish_cell import publish_cell_library
from .schema import ensure_maintenance_schema
from .window import (
    build_cell_core_gps_stats,
    build_cell_metrics_base,
    build_cell_radius_stats,
    build_daily_centroids,
    refresh_sliding_window,
)
from .writers import collect_step5_stats, write_run_log, write_step5_stats


def _latest_step3() -> dict[str, Any] | None:
    return fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step3_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )


def _step3_for_batch(batch_id: int) -> dict[str, Any] | None:
    return fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step3_run_stats
        WHERE batch_id = %s
        ORDER BY finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """,
        (batch_id,),
    )


def _latest_published_snapshot_version(*, current_batch_id: int) -> str:
    if not relation_exists('rebuild5.trusted_cell_library'):
        return 'v0'
    row = fetchone(
        """
        SELECT snapshot_version
        FROM rebuild5.trusted_cell_library
        WHERE batch_id < %s
        ORDER BY batch_id DESC, cell_id
        LIMIT 1
        """,
        (current_batch_id,),
    )
    return str(row['snapshot_version']) if row else 'v0'


def run_maintenance_pipeline() -> dict[str, Any]:
    step3 = _latest_step3()
    return _run_maintenance_pipeline_for_step3(step3)


def run_maintenance_pipeline_for_batch(*, batch_id: int) -> dict[str, Any]:
    step3 = _step3_for_batch(batch_id)
    return _run_maintenance_pipeline_for_step3(step3)


def _run_maintenance_pipeline_for_step3(step3: dict[str, Any] | None) -> dict[str, Any]:
    # -- Prepare --
    # cell_sliding_window is persistent across batches (continuous window) — do NOT drop
    execute('DROP TABLE IF EXISTS rebuild5.cell_daily_centroid')
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_base')
    execute('DROP TABLE IF EXISTS rebuild5.cell_radius_stats')
    execute('DROP TABLE IF EXISTS rebuild5._cell_radius_raw_radius')
    execute('DROP TABLE IF EXISTS rebuild5._cell_radius_core_radius')
    execute('DROP TABLE IF EXISTS rebuild5.cell_drift_stats')
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_window')
    execute('DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_initial_center')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_point_distance')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_mad_stats')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_seed_grid')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_primary_seed')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_seed_distance')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_cutoff')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_points')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_gps_stats')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_gps_day_dedup')
    ensure_maintenance_schema()

    if not step3:
        return _empty_stats()

    import time as _time
    _timings = {}
    def _tick(label):
        _timings[label] = _time.time()
    def _report():
        keys = list(_timings.keys())
        for i in range(1, len(keys)):
            print(f"  {keys[i]}: {_timings[keys[i]] - _timings[keys[i-1]]:.0f}s")

    _tick('start')
    run_id = f"maint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_id = int(step3['batch_id'])
    snapshot_version = str(step3['snapshot_version'])
    snapshot_version_prev = _latest_published_snapshot_version(current_batch_id=batch_id)
    antitoxin = flatten_antitoxin_thresholds(load_antitoxin_params())

    # -- 5.0 Window preparation --
    _tick('sliding_window')
    refresh_sliding_window(batch_id=batch_id)
    execute('CREATE INDEX IF NOT EXISTS idx_csw_cell ON rebuild5.cell_sliding_window (batch_id, operator_code, lac, bs_id, cell_id)')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_csw_lookup
        ON rebuild5.cell_sliding_window (batch_id, operator_code, lac, bs_id, cell_id, tech_norm, event_time_std)
        """
    )
    execute('ALTER TABLE rebuild5.cell_sliding_window SET (parallel_workers = 16)')
    _tick('daily_centroids')
    build_daily_centroids(batch_id=batch_id)
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cdc_cell_date
        ON rebuild5.cell_daily_centroid (batch_id, operator_code, lac, cell_id, tech_norm, obs_date)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cdc_lookup
        ON rebuild5.cell_daily_centroid (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    _tick('metrics_base')
    build_cell_metrics_base(batch_id=batch_id)
    _tick('core_gps')
    build_cell_core_gps_stats(batch_id=batch_id)
    _tick('metrics_radius')
    build_cell_radius_stats()

    # -- 5.2 Cell maintenance --
    _tick('drift_metrics')
    compute_drift_metrics(batch_id=batch_id)
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cmw_cell
        ON rebuild5.cell_metrics_window (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cmw_lookup
        ON rebuild5.cell_metrics_window (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    _tick('anomaly_summary')
    compute_gps_anomaly_summary(batch_id=batch_id, antitoxin=antitoxin)
    if relation_exists('rebuild5.cell_anomaly_summary'):
        execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cas_cell
            ON rebuild5.cell_anomaly_summary (batch_id, operator_code, lac, cell_id, tech_norm)
            """
        )
        execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cas_lookup
            ON rebuild5.cell_anomaly_summary (batch_id, operator_code, lac, cell_id, tech_norm)
            """
        )

    # -- 5.3 Publish trusted_cell_library --
    _tick('publish_cell')
    publish_cell_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
        antitoxin=antitoxin,
    )
    # Index for collision self-join and BS/LAC publish
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_collision ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, cell_id)')
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_cell_id ON rebuild5.trusted_cell_library (batch_id, cell_id)')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tcl_abs_collision
        ON rebuild5.trusted_cell_library (batch_id, operator_code, tech_norm, lac, cell_id, bs_id)
        """
    )
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_bs ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, bs_id)')
    execute('ANALYZE rebuild5.trusted_cell_library')

    # -- 5.35 Authoritative label engine --
    _tick('label_engine')
    run_label_engine(batch_id=batch_id, snapshot_version=snapshot_version)
    execute('ANALYZE rebuild5.trusted_cell_library')

    # -- 5.1 Collision detection --
    _tick('collision')
    detect_collisions(
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        absolute_min_distance_m=antitoxin['absolute_collision_min_distance_m'],
    )

    # -- 5.4 BS + LAC --
    _tick('bs_lac')
    publish_bs_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
        antitoxin=antitoxin,
    )
    execute('ANALYZE rebuild5.trusted_bs_library')
    publish_bs_centroid_detail(
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        large_spread_threshold_m=antitoxin['bs_max_cell_to_bs_distance_m'],
    )
    publish_lac_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
    )

    _tick('done')
    print('[Step 5 子步骤耗时]')
    _report()

    # -- Stats --
    stats = collect_step5_stats(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
    )
    write_step5_stats(stats)
    write_run_log(run_id=run_id, snapshot_version=snapshot_version,
                  status='completed', result_summary=stats)
    return stats


def _empty_stats() -> dict[str, Any]:
    return {
        'run_id': '', 'batch_id': 0, 'dataset_key': DATASET_KEY,
        'snapshot_version': 'v0', 'snapshot_version_prev': 'v0',
        'published_cell_count': 0, 'published_bs_count': 0,
        'published_lac_count': 0, 'collision_cell_count': 0,
        'multi_centroid_cell_count': 0, 'dynamic_cell_count': 0,
        'anomaly_bs_count': 0,
    }
