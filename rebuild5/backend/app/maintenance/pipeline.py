"""Step 5 maintenance / publish pipeline — orchestrator.

Calls sub-modules in order:
  5.0  window.py         — sliding window + cell metric recalculation
  5.2  cell_maintain.py  — drift metrics + GPS anomaly summary
  5.3  publish_cell.py   — trusted_cell_library publication
  5.1  collision.py      — two-layer collision detection (runs after cell publish)
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
from .publish_bs_lac import (
    publish_bs_centroid_detail,
    publish_bs_library,
    publish_cell_centroid_detail,
    publish_lac_library,
)
from .publish_cell import publish_cell_library
from .schema import ensure_maintenance_schema
from .window import build_daily_centroids, recalculate_cell_metrics, refresh_sliding_window
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


def _latest_published_snapshot_version() -> str:
    if not relation_exists('rebuild5.trusted_cell_library'):
        return 'v0'
    row = fetchone(
        """
        SELECT snapshot_version
        FROM rebuild5.trusted_cell_library
        ORDER BY batch_id DESC, cell_id
        LIMIT 1
        """
    )
    return str(row['snapshot_version']) if row else 'v0'


def run_maintenance_pipeline() -> dict[str, Any]:
    # -- Prepare --
    # cell_sliding_window is persistent across batches (continuous window) — do NOT drop
    execute('DROP TABLE IF EXISTS rebuild5.cell_daily_centroid')
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_window')
    execute('DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary')
    execute('DROP TABLE IF EXISTS rebuild5_meta.step5_run_stats')
    ensure_maintenance_schema()

    step3 = _latest_step3()
    if not step3:
        return _empty_stats()

    run_id = f"maint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_id = int(step3['batch_id'])
    snapshot_version = str(step3['snapshot_version'])
    snapshot_version_prev = _latest_published_snapshot_version()
    antitoxin = flatten_antitoxin_thresholds(load_antitoxin_params())

    # -- 5.0 Window preparation --
    refresh_sliding_window(batch_id=batch_id)
    # Index for daily centroid GROUP BY and metrics JOIN
    execute('CREATE INDEX IF NOT EXISTS idx_csw_cell ON rebuild5.cell_sliding_window (batch_id, operator_code, lac, bs_id, cell_id)')
    build_daily_centroids(batch_id=batch_id)
    recalculate_cell_metrics(batch_id=batch_id)
    # Indexes for drift self-join and publish JOIN
    execute('CREATE INDEX IF NOT EXISTS idx_cdc_cell_date ON rebuild5.cell_daily_centroid (batch_id, operator_code, lac, cell_id, obs_date)')
    execute('CREATE INDEX IF NOT EXISTS idx_cmw_cell ON rebuild5.cell_metrics_window (batch_id, operator_code, lac, cell_id)')

    # -- 5.2 Cell maintenance (drift metrics + GPS anomaly summary) --
    compute_drift_metrics(batch_id=batch_id)
    compute_gps_anomaly_summary(batch_id=batch_id)
    # Index for publish JOIN
    if relation_exists('rebuild5.cell_anomaly_summary'):
        execute('CREATE INDEX IF NOT EXISTS idx_cas_cell ON rebuild5.cell_anomaly_summary (batch_id, operator_code, lac, cell_id)')

    # -- 5.3 Publish trusted_cell_library --
    publish_cell_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
        antitoxin=antitoxin,
    )
    # Index for collision self-join and BS/LAC publish
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_collision ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, cell_id)')
    execute('CREATE INDEX IF NOT EXISTS idx_tcl_bs ON rebuild5.trusted_cell_library (batch_id, operator_code, lac, bs_id)')

    # -- 5.1 Collision detection (after cell publish — UPDATEs trusted_cell_library) --
    detect_collisions(
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        absolute_min_distance_m=antitoxin['absolute_collision_min_distance_m'],
    )

    # -- 5.4 BS + LAC --
    publish_cell_centroid_detail(batch_id=batch_id, snapshot_version=snapshot_version)
    publish_bs_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
        antitoxin=antitoxin,
    )
    publish_bs_centroid_detail(batch_id=batch_id, snapshot_version=snapshot_version)
    publish_lac_library(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
    )

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
