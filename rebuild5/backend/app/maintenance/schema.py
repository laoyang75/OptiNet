"""Step 5 table schema definitions (single source of truth for all DDL)."""
from __future__ import annotations

from ..core.database import execute


def ensure_maintenance_schema() -> None:
    _create_step5_run_stats()
    _create_trusted_cell_library()
    _create_trusted_bs_library()
    _create_trusted_lac_library()
    _create_collision_id_list()
    _create_cell_centroid_detail()
    _create_bs_centroid_detail()
    _create_cell_sliding_window()
    _create_cell_daily_centroid()
    _create_cell_metrics_window()
    _apply_maintenance_table_policies()
    _ensure_maintenance_compat_columns()


def _apply_maintenance_table_policies() -> None:
    """Apply physical-table policies for Step 5 batch-owned tables.

    trusted_*_library and collision/detail tables are rebuilt/overwritten by batch.
    We manage their statistics explicitly in the pipeline, so disabling autovacuum
    avoids background workers competing with long-running reruns.

    cell_sliding_window is intentionally excluded: it is the cross-batch
    persistent window and should keep default autovacuum behavior.
    """
    for table_name in (
        'rebuild5.trusted_cell_library',
        'rebuild5.trusted_bs_library',
        'rebuild5.trusted_lac_library',
        'rebuild5.collision_id_list',
        'rebuild5.cell_centroid_detail',
        'rebuild5.bs_centroid_detail',
    ):
        execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false)")


def _create_step5_run_stats() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5_meta.step5_run_stats (
            run_id TEXT PRIMARY KEY,
            batch_id INTEGER NOT NULL,
            dataset_key TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_cell_count BIGINT NOT NULL,
            published_bs_count BIGINT NOT NULL,
            published_lac_count BIGINT NOT NULL,
            collision_cell_count BIGINT NOT NULL,
            multi_centroid_cell_count BIGINT NOT NULL,
            dynamic_cell_count BIGINT NOT NULL,
            anomaly_bs_count BIGINT NOT NULL
        )
        """
    )


def _create_trusted_cell_library() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.trusted_cell_library (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            lifecycle_state TEXT NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            p50_radius_m DOUBLE PRECISION,
            p90_radius_m DOUBLE PRECISION,
            position_grade TEXT,
            gps_confidence TEXT,
            signal_confidence TEXT,
            independent_obs BIGINT,
            distinct_dev_id BIGINT,
            gps_valid_count BIGINT,
            active_days BIGINT,
            observed_span_hours DOUBLE PRECISION,
            rsrp_avg DOUBLE PRECISION,
            rsrq_avg DOUBLE PRECISION,
            sinr_avg DOUBLE PRECISION,
            pressure_avg DOUBLE PRECISION,
            drift_pattern TEXT,
            max_spread_m DOUBLE PRECISION,
            net_drift_m DOUBLE PRECISION,
            drift_ratio DOUBLE PRECISION,
            gps_anomaly_type TEXT,
            is_collision BOOLEAN NOT NULL DEFAULT FALSE,
            is_dynamic BOOLEAN NOT NULL DEFAULT FALSE,
            is_multi_centroid BOOLEAN NOT NULL DEFAULT FALSE,
            centroid_pattern TEXT,
            antitoxin_hit BOOLEAN NOT NULL DEFAULT FALSE,
            cell_scale TEXT,
            last_maintained_at TIMESTAMPTZ,
            last_observed_at TIMESTAMPTZ,
            window_obs_count BIGINT NOT NULL DEFAULT 0,
            active_days_30d INTEGER DEFAULT 0,
            consecutive_inactive_days INTEGER DEFAULT 0,
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        )
        """
    )


def _create_trusted_bs_library() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.trusted_bs_library (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT,
            bs_id BIGINT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            total_cells BIGINT NOT NULL,
            qualified_cells BIGINT NOT NULL,
            excellent_cells BIGINT NOT NULL,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            gps_p50_dist_m DOUBLE PRECISION,
            gps_p90_dist_m DOUBLE PRECISION,
            classification TEXT,
            position_grade TEXT,
            anomaly_cell_ratio DOUBLE PRECISION,
            is_multi_centroid BOOLEAN NOT NULL DEFAULT FALSE,
            window_active_cell_count BIGINT DEFAULT 0,
            PRIMARY KEY (batch_id, operator_code, lac, bs_id)
        )
        """
    )


def _create_trusted_lac_library() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.trusted_lac_library (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT,
            lifecycle_state TEXT NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            total_bs BIGINT NOT NULL,
            qualified_bs BIGINT NOT NULL,
            excellent_bs BIGINT NOT NULL DEFAULT 0,
            qualified_bs_ratio DOUBLE PRECISION NOT NULL,
            area_km2 DOUBLE PRECISION,
            anomaly_bs_ratio DOUBLE PRECISION,
            boundary_stability_score DOUBLE PRECISION,
            active_bs_count BIGINT DEFAULT 0,
            retired_bs_count BIGINT DEFAULT 0,
            trend TEXT,
            PRIMARY KEY (batch_id, operator_code, lac)
        )
        """
    )
    execute('ALTER TABLE rebuild5.trusted_lac_library ADD COLUMN IF NOT EXISTS excellent_bs BIGINT NOT NULL DEFAULT 0')


def _create_collision_id_list() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.collision_id_list (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            cell_id BIGINT NOT NULL,
            is_collision_id BOOLEAN NOT NULL DEFAULT TRUE,
            collision_combo_count BIGINT NOT NULL,
            dominant_combo TEXT,
            combo_keys_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (batch_id, cell_id)
        )
        """
    )


def _create_cell_centroid_detail() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.cell_centroid_detail (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            operator_code TEXT NOT NULL,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            cluster_id INTEGER NOT NULL,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            obs_count BIGINT,
            dev_count BIGINT,
            radius_m DOUBLE PRECISION,
            share_ratio DOUBLE PRECISION,
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm, cluster_id)
        )
        """
    )


def _create_bs_centroid_detail() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.bs_centroid_detail (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            operator_code TEXT NOT NULL,
            lac BIGINT,
            bs_id BIGINT NOT NULL,
            cluster_id INTEGER NOT NULL,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            cell_count BIGINT,
            share_ratio DOUBLE PRECISION,
            PRIMARY KEY (batch_id, operator_code, lac, bs_id, cluster_id)
        )
        """
    )


def _ensure_maintenance_compat_columns() -> None:
    execute('ALTER TABLE rebuild5.cell_centroid_detail ADD COLUMN IF NOT EXISTS radius_m DOUBLE PRECISION')
    execute('ALTER TABLE rebuild5.trusted_cell_library ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rebuild5.trusted_cell_library ADD COLUMN IF NOT EXISTS centroid_pattern TEXT')
    execute('ALTER TABLE rebuild5.cell_centroid_detail ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rebuild5.cell_sliding_window ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rebuild5.cell_daily_centroid ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rebuild5.cell_metrics_window ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rebuild5.trusted_cell_library DROP CONSTRAINT IF EXISTS trusted_cell_library_pkey')
    execute(
        """
        ALTER TABLE rebuild5.trusted_cell_library
        ADD CONSTRAINT trusted_cell_library_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('ALTER TABLE rebuild5.cell_centroid_detail DROP CONSTRAINT IF EXISTS cell_centroid_detail_pkey')
    execute(
        """
        ALTER TABLE rebuild5.cell_centroid_detail
        ADD CONSTRAINT cell_centroid_detail_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm, cluster_id)
        """
    )


def _create_cell_sliding_window() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.cell_sliding_window (
            batch_id INTEGER NOT NULL,
            source_row_uid TEXT NOT NULL,
            record_id TEXT NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            dev_id TEXT,
            event_time_std TIMESTAMPTZ,
            gps_valid BOOLEAN,
            lon_final DOUBLE PRECISION,
            lat_final DOUBLE PRECISION,
            rsrp_final DOUBLE PRECISION,
            rsrq_final DOUBLE PRECISION,
            sinr_final DOUBLE PRECISION,
            pressure_final DOUBLE PRECISION,
            source_type TEXT,
            PRIMARY KEY (batch_id, source_row_uid)
        )
        """
    )


def _create_cell_daily_centroid() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.cell_daily_centroid (
            batch_id INTEGER NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            obs_date DATE NOT NULL,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            obs_count BIGINT,
            dev_count BIGINT
        )
        """
    )


def _create_cell_metrics_window() -> None:
    """Intermediate table: per-cell metrics recalculated from sliding window.

    Consumed by cell_maintain.py and publish_cell.py in subsequent rounds.
    """
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.cell_metrics_window (
            batch_id INTEGER NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            -- recalculated spatial metrics
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            p50_radius_m DOUBLE PRECISION,
            p90_radius_m DOUBLE PRECISION,
            -- recalculated observation metrics
            independent_obs BIGINT,
            distinct_dev_id BIGINT,
            gps_valid_count BIGINT,
            active_days BIGINT,
            observed_span_hours DOUBLE PRECISION,
            -- recalculated signal / pressure
            rsrp_avg DOUBLE PRECISION,
            rsrq_avg DOUBLE PRECISION,
            sinr_avg DOUBLE PRECISION,
            pressure_avg DOUBLE PRECISION,
            -- window metadata
            max_event_time TIMESTAMPTZ,
            window_obs_count BIGINT,
            -- activity for exit management
            active_days_30d INTEGER DEFAULT 0,
            consecutive_inactive_days INTEGER DEFAULT 0,
            -- drift metrics (populated by cell_maintain.py)
            max_spread_m DOUBLE PRECISION,
            net_drift_m DOUBLE PRECISION,
            drift_ratio DOUBLE PRECISION
        )
        """
    )
