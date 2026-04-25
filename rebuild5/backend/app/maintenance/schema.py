"""Step 5 table schema definitions (single source of truth for all DDL)."""
from __future__ import annotations

from ..core.database import execute


def ensure_maintenance_schema() -> None:
    _create_pipeline_artifact_state()
    _create_step5_run_stats()
    _create_trusted_cell_library()
    _create_trusted_bs_library()
    _create_trusted_lac_library()
    _create_label_results()
    _create_collision_id_list()
    _create_cell_centroid_detail()
    _create_bs_centroid_detail()
    _create_cell_sliding_window()
    _create_cell_daily_centroid()
    _create_cell_metrics_window()
    _apply_maintenance_table_policies()
    _ensure_maintenance_compat_columns()


def _create_pipeline_artifact_state() -> None:
    execute('CREATE SCHEMA IF NOT EXISTS rb5_stage')
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5_meta.pipeline_artifacts (
            batch_id INTEGER PRIMARY KEY,
            day DATE NOT NULL,
            artifact_relation TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'ready', 'consumed', 'failed')),
            row_count BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            error TEXT
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
                WHERE logicalrelid = 'rb5_meta.pipeline_artifacts'::regclass
            ) THEN
                PERFORM create_reference_table('rb5_meta.pipeline_artifacts');
            END IF;
        END $$;
        """
    )


def _apply_maintenance_table_policies() -> None:
    """Apply physical-table policies for Step 5 batch-owned tables.

    trusted_*_library and collision/detail tables are rebuilt/overwritten by batch.
    We manage their statistics explicitly in the pipeline, so disabling autovacuum
    avoids background workers competing with long-running reruns.

    cell_sliding_window is intentionally excluded: it is the cross-batch
    persistent window and should keep default autovacuum behavior.
    """
    for table_name in (
        'rb5.trusted_cell_library',
        'rb5.trusted_bs_library',
        'rb5.trusted_lac_library',
        'rb5.label_results',
        'rb5.collision_id_list',
        'rb5.cell_centroid_detail',
        'rb5.bs_centroid_detail',
    ):
        execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false)")


def _create_step5_run_stats() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5_meta.step5_run_stats (
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
        CREATE TABLE IF NOT EXISTS rb5.trusted_cell_library (
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
            ta_n_obs BIGINT DEFAULT 0,
            ta_p50 INTEGER,
            ta_p90 INTEGER,
            ta_dist_p90_m INTEGER,
            freq_band TEXT,
            ta_verification TEXT,
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        )
        """
    )
    # 向后兼容：TA 辅助研究字段（2026-04-23 新增）
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS ta_n_obs BIGINT DEFAULT 0')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS ta_p50 INTEGER')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS ta_p90 INTEGER')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS ta_dist_p90_m INTEGER')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS freq_band TEXT')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS ta_verification TEXT')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tcl_service_cell
        ON rb5.trusted_cell_library (batch_id, cell_id, operator_code, lac, tech_norm)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tcl_service_bs_cells
        ON rb5.trusted_cell_library (batch_id, operator_code, lac, bs_id, p90_radius_m, cell_id)
        """
    )


def _create_trusted_bs_library() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.trusted_bs_library (
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
            normal_cells BIGINT NOT NULL DEFAULT 0,
            anomaly_cells BIGINT NOT NULL DEFAULT 0,
            insufficient_cells BIGINT NOT NULL DEFAULT 0,
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
    # 向后兼容：确保新字段在旧库上也存在
    execute('ALTER TABLE rb5.trusted_bs_library ADD COLUMN IF NOT EXISTS normal_cells BIGINT NOT NULL DEFAULT 0')
    execute('ALTER TABLE rb5.trusted_bs_library ADD COLUMN IF NOT EXISTS anomaly_cells BIGINT NOT NULL DEFAULT 0')
    execute('ALTER TABLE rb5.trusted_bs_library ADD COLUMN IF NOT EXISTS insufficient_cells BIGINT NOT NULL DEFAULT 0')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tbl_service_bs
        ON rb5.trusted_bs_library (batch_id, bs_id, operator_code, lac)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tbl_service_lac
        ON rb5.trusted_bs_library (batch_id, operator_code, lac, anomaly_cell_ratio, total_cells)
        """
    )


def _create_trusted_lac_library() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.trusted_lac_library (
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
            normal_bs BIGINT NOT NULL DEFAULT 0,
            anomaly_bs BIGINT NOT NULL DEFAULT 0,
            insufficient_bs BIGINT NOT NULL DEFAULT 0,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
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
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS excellent_bs BIGINT NOT NULL DEFAULT 0')
    # LAC 层三分类（正常/异常/数据不足 BS）— 观察字段
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS normal_bs BIGINT NOT NULL DEFAULT 0')
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS anomaly_bs BIGINT NOT NULL DEFAULT 0')
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS insufficient_bs BIGINT NOT NULL DEFAULT 0')
    # LAC 质心（基于正常 BS）
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS center_lon DOUBLE PRECISION')
    execute('ALTER TABLE rb5.trusted_lac_library ADD COLUMN IF NOT EXISTS center_lat DOUBLE PRECISION')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tll_service_lac
        ON rb5.trusted_lac_library (batch_id, lac, operator_code)
        """
    )


def _create_collision_id_list() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.collision_id_list (
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


def _create_label_results() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.label_results (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            operator_code TEXT NOT NULL,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            candidate_hit BOOLEAN NOT NULL DEFAULT FALSE,
            k_raw INTEGER NOT NULL DEFAULT 0,
            k_eff INTEGER NOT NULL DEFAULT 0,
            total_valid_pts BIGINT NOT NULL DEFAULT 0,
            p90_radius_m DOUBLE PRECISION,
            pair_dist_m DOUBLE PRECISION,
            pair_overlap_ratio DOUBLE PRECISION,
            pair_no_comeback BOOLEAN,
            max_span_m DOUBLE PRECISION,
            total_path_m DOUBLE PRECISION,
            line_ratio DOUBLE PRECISION,
            distance_cv DOUBLE PRECISION,
            avg_dwell_days DOUBLE PRECISION,
            label TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        )
        """
    )


def _create_cell_centroid_detail() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.cell_centroid_detail (
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
        CREATE TABLE IF NOT EXISTS rb5.bs_centroid_detail (
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
    execute('ALTER TABLE rb5.cell_centroid_detail ADD COLUMN IF NOT EXISTS radius_m DOUBLE PRECISION')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rb5.trusted_cell_library ADD COLUMN IF NOT EXISTS centroid_pattern TEXT')
    execute('ALTER TABLE rb5.cell_centroid_detail ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rb5.cell_sliding_window ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rb5.cell_daily_centroid ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rb5.cell_metrics_window ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute('ALTER TABLE rb5.trusted_cell_library DROP CONSTRAINT IF EXISTS trusted_cell_library_pkey')
    execute(
        """
        ALTER TABLE rb5.trusted_cell_library
        ADD CONSTRAINT trusted_cell_library_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('ALTER TABLE rb5.cell_centroid_detail DROP CONSTRAINT IF EXISTS cell_centroid_detail_pkey')
    execute(
        """
        ALTER TABLE rb5.cell_centroid_detail
        ADD CONSTRAINT cell_centroid_detail_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm, cluster_id)
        """
    )


def _create_cell_sliding_window() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.cell_sliding_window (
            batch_id INTEGER NOT NULL,
            source_row_uid TEXT NOT NULL,
            record_id TEXT NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            cell_origin TEXT,
            timing_advance INTEGER,
            freq_channel INTEGER,
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
            PRIMARY KEY (batch_id, source_row_uid, cell_id)
        )
        """
    )
    execute("ALTER TABLE rb5.cell_sliding_window ADD COLUMN IF NOT EXISTS cell_origin TEXT")
    execute("ALTER TABLE rb5.cell_sliding_window ADD COLUMN IF NOT EXISTS timing_advance INTEGER")
    execute("ALTER TABLE rb5.cell_sliding_window ADD COLUMN IF NOT EXISTS freq_channel INTEGER")
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_csw_dim_time
        ON rb5.cell_sliding_window (operator_code, lac, cell_id, tech_norm, event_time_std)
        """
    )
    execute('CREATE INDEX IF NOT EXISTS idx_csw_source_uid ON rb5.cell_sliding_window (source_row_uid)')
    execute('CREATE INDEX IF NOT EXISTS idx_csw_event_time ON rb5.cell_sliding_window (event_time_std)')


def _create_cell_daily_centroid() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.cell_daily_centroid (
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
        CREATE TABLE IF NOT EXISTS rb5.cell_metrics_window (
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
