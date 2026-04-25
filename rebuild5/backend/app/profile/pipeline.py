"""Step 2 routing pipeline for rb5."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..core.citus_compat import execute_distributed_insert
from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY
from .logic import (
    build_core_mad_k_sql,
    flatten_antitoxin_thresholds,
    flatten_profile_thresholds,
    load_antitoxin_params,
    load_core_mad_filter_params,
    load_profile_params,
)


def _disable_autovacuum(table_name: str) -> None:
    execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false)")


def run_profile_pipeline(*, input_relation: str | None = None) -> dict[str, Any]:
    from ..evaluation.pipeline import run_step3_pipeline

    ensure_profile_schema()
    thresholds = flatten_profile_thresholds(load_profile_params())
    antitoxin_thresholds = flatten_antitoxin_thresholds(load_antitoxin_params())
    run_id = f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    previous_batch_id = get_latest_batch_id()
    previous_snapshot_version = f'v{previous_batch_id}' if previous_batch_id else 'v0'
    batch_id = previous_batch_id + 1
    snapshot_version = f'v{batch_id}'

    try:
        step2_stats = run_step2_pipeline(
            run_id=run_id,
            batch_id=batch_id,
            previous_snapshot_version=previous_snapshot_version,
            antitoxin_thresholds=antitoxin_thresholds,
            input_relation=input_relation,
        )
        step3_stats = run_step3_pipeline(
            run_id=run_id,
            batch_id=batch_id,
            snapshot_version=snapshot_version,
            previous_batch_id=previous_batch_id,
            previous_snapshot_version=previous_snapshot_version,
            thresholds=thresholds,
            antitoxin_thresholds=antitoxin_thresholds,
        )
        summary = {
            'run_id': run_id,
            'dataset_key': DATASET_KEY,
            'batch_id': batch_id,
            'snapshot_version': snapshot_version,
            'trusted_snapshot_version_prev': previous_snapshot_version,
            'path_a_record_count': step2_stats['path_a_record_count'],
            'path_b_record_count': step2_stats['path_b_record_count'],
            'path_b_cell_count': step2_stats['path_b_cell_count'],
            'path_c_drop_count': step2_stats['path_c_drop_count'],
            'cell_waiting_count': step3_stats['waiting_cell_count'],
            'cell_qualified_count': step3_stats['qualified_cell_count'],
            'cell_excellent_count': step3_stats['excellent_cell_count'],
            'bs_excellent_count': step3_stats['bs_excellent_count'],
            'bs_qualified_count': step3_stats['bs_qualified_count'],
            'lac_excellent_count': step3_stats['lac_excellent_count'],
            'lac_qualified_count': step3_stats['lac_qualified_count'],
        }
        write_run_log(
            run_id=run_id,
            status='completed',
            snapshot_version=snapshot_version,
            result_summary=summary,
            step_chain='step2 -> step3',
        )
        return summary
    except Exception as exc:
        write_run_log(
            run_id=run_id,
            status='failed',
            snapshot_version=snapshot_version,
            result_summary={'dataset_key': DATASET_KEY, 'snapshot_version': snapshot_version},
            step_chain='step2 -> step3',
            error=str(exc),
        )
        raise


def ensure_profile_schema() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5_meta.step2_run_stats (
            run_id TEXT PRIMARY KEY,
            batch_id INTEGER,
            dataset_key TEXT NOT NULL,
            status TEXT NOT NULL,
            trusted_snapshot_version TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            input_record_count BIGINT NOT NULL,
            path_a_record_count BIGINT NOT NULL,
            path_b_record_count BIGINT NOT NULL,
            path_b_cell_count BIGINT NOT NULL,
            path_c_drop_count BIGINT NOT NULL,
            path_a_ratio DOUBLE PRECISION NOT NULL,
            path_b_ratio DOUBLE PRECISION NOT NULL,
            path_c_drop_ratio DOUBLE PRECISION NOT NULL,
            collision_candidate_count BIGINT NOT NULL,
            collision_path_a_match_count BIGINT NOT NULL,
            collision_pending_count BIGINT NOT NULL,
            collision_drop_count BIGINT NOT NULL,
            collision_match_rate DOUBLE PRECISION NOT NULL,
            collision_drop_rate DOUBLE PRECISION NOT NULL,
            path_b_complete_cell_count BIGINT NOT NULL,
            path_b_partial_cell_count BIGINT NOT NULL,
            path_b_avg_gps_original_ratio DOUBLE PRECISION NOT NULL,
            path_b_avg_signal_original_ratio DOUBLE PRECISION NOT NULL,
            avg_independent_obs DOUBLE PRECISION NOT NULL,
            avg_independent_devs DOUBLE PRECISION NOT NULL,
            avg_observed_span_hours DOUBLE PRECISION NOT NULL,
            avg_p50_radius_m DOUBLE PRECISION NOT NULL,
            avg_p90_radius_m DOUBLE PRECISION NOT NULL
        )
        """
    )
    execute('ALTER TABLE rb5_meta.step2_run_stats ADD COLUMN IF NOT EXISTS batch_id INTEGER')
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5_meta.step3_run_stats (
            run_id TEXT PRIMARY KEY,
            dataset_key TEXT NOT NULL,
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            trusted_snapshot_version_prev TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            profile_base_cell_count BIGINT NOT NULL,
            mode_filtered_count BIGINT NOT NULL DEFAULT 0,
            region_filtered_count BIGINT NOT NULL DEFAULT 0,
            gps_filtered_count BIGINT NOT NULL DEFAULT 0,
            evaluated_cell_count BIGINT NOT NULL,
            waiting_cell_count BIGINT NOT NULL,
            observing_cell_count BIGINT NOT NULL,
            qualified_cell_count BIGINT NOT NULL,
            excellent_cell_count BIGINT NOT NULL,
            new_qualified_cell_count BIGINT NOT NULL,
            new_excellent_cell_count BIGINT NOT NULL,
            anchor_eligible_cell_count BIGINT NOT NULL,
            bs_waiting_count BIGINT NOT NULL,
            bs_observing_count BIGINT NOT NULL,
            bs_excellent_count BIGINT NOT NULL DEFAULT 0,
            bs_qualified_count BIGINT NOT NULL,
            lac_waiting_count BIGINT NOT NULL,
            lac_observing_count BIGINT NOT NULL,
            lac_excellent_count BIGINT NOT NULL DEFAULT 0,
            lac_qualified_count BIGINT NOT NULL,
            waiting_pruned_cell_count BIGINT NOT NULL DEFAULT 0,
            dormant_marked_count BIGINT NOT NULL DEFAULT 0,
            snapshot_new_count BIGINT NOT NULL,
            snapshot_promoted_count BIGINT NOT NULL,
            snapshot_demoted_count BIGINT NOT NULL,
            snapshot_eligibility_changed_count BIGINT NOT NULL DEFAULT 0,
            snapshot_geometry_changed_count BIGINT NOT NULL DEFAULT 0
        )
        """
    )
    execute('ALTER TABLE rb5_meta.step3_run_stats ADD COLUMN IF NOT EXISTS bs_excellent_count BIGINT NOT NULL DEFAULT 0')
    execute('ALTER TABLE rb5_meta.step3_run_stats ADD COLUMN IF NOT EXISTS lac_excellent_count BIGINT NOT NULL DEFAULT 0')
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.trusted_snapshot_cell (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT NOT NULL,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            lifecycle_state TEXT NOT NULL,
            is_registered BOOLEAN NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            is_collision_id BOOLEAN NOT NULL DEFAULT FALSE,
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
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        )
        """
    )
    execute(
        """
        ALTER TABLE rb5.trusted_snapshot_cell
        DROP CONSTRAINT IF EXISTS trusted_snapshot_cell_pkey
        """
    )
    execute(
        """
        ALTER TABLE rb5.trusted_snapshot_cell
        ADD CONSTRAINT trusted_snapshot_cell_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.trusted_snapshot_bs (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT NOT NULL,
            bs_id BIGINT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            is_registered BOOLEAN NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            cell_count BIGINT NOT NULL,
            qualified_cell_count BIGINT NOT NULL,
            excellent_cell_count BIGINT NOT NULL,
            cells_with_gps BIGINT NOT NULL,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            gps_p50_dist_m DOUBLE PRECISION,
            gps_p90_dist_m DOUBLE PRECISION,
            classification TEXT,
            position_grade TEXT,
            PRIMARY KEY (batch_id, operator_code, lac, bs_id)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.trusted_snapshot_lac (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            operator_cn TEXT,
            lac BIGINT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            is_registered BOOLEAN NOT NULL,
            anchor_eligible BOOLEAN NOT NULL,
            baseline_eligible BOOLEAN NOT NULL,
            bs_count BIGINT NOT NULL,
            excellent_bs_count BIGINT NOT NULL DEFAULT 0,
            qualified_bs_count BIGINT NOT NULL,
            non_waiting_bs_count BIGINT NOT NULL,
            cell_count BIGINT NOT NULL,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            area_km2 DOUBLE PRECISION,
            anomaly_bs_ratio DOUBLE PRECISION,
            position_grade TEXT,
            PRIMARY KEY (batch_id, operator_code, lac)
        )
        """
    )
    execute('ALTER TABLE rb5.trusted_snapshot_lac ADD COLUMN IF NOT EXISTS excellent_bs_count BIGINT NOT NULL DEFAULT 0')
    execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS rb5.candidate_seed_history (
            batch_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            source_row_uid TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source_table TEXT,
            event_time_std TIMESTAMPTZ,
            dev_id TEXT,
            operator_code TEXT,
            operator_cn TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            cell_origin TEXT,
            timing_advance INTEGER,
            freq_channel INTEGER,
            gps_valid BOOLEAN,
            lon_filled DOUBLE PRECISION,
            lat_filled DOUBLE PRECISION,
            gps_fill_source TEXT,
            rsrp_filled DOUBLE PRECISION,
            rsrq_filled DOUBLE PRECISION,
            sinr_filled DOUBLE PRECISION,
            pressure DOUBLE PRECISION,
            PRIMARY KEY (batch_id, source_row_uid, cell_id)
        )
        """
    )
    execute("ALTER TABLE rb5.candidate_seed_history SET (autovacuum_enabled = false)")
    execute("ALTER TABLE rb5.candidate_seed_history ADD COLUMN IF NOT EXISTS cell_origin TEXT")
    execute("ALTER TABLE rb5.candidate_seed_history ADD COLUMN IF NOT EXISTS timing_advance INTEGER")
    execute("ALTER TABLE rb5.candidate_seed_history ADD COLUMN IF NOT EXISTS freq_channel INTEGER")
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_seed_history_cell
        ON rb5.candidate_seed_history (operator_code, lac, bs_id, cell_id, tech_norm, batch_id)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_seed_history_event_time
        ON rb5.candidate_seed_history (batch_id, event_time_std)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_seed_history_batch_record
        ON rb5.candidate_seed_history (batch_id, record_id, cell_id, lac, tech_norm)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_seed_history_dim_time
        ON rb5.candidate_seed_history (operator_code, lac, cell_id, tech_norm, batch_id, event_time_std)
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.snapshot_diff_cell (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            lac BIGINT NOT NULL,
            bs_id BIGINT,
            cell_id BIGINT NOT NULL,
            tech_norm TEXT,
            diff_kind TEXT NOT NULL,
            prev_lifecycle_state TEXT,
            curr_lifecycle_state TEXT,
            prev_anchor_eligible BOOLEAN,
            curr_anchor_eligible BOOLEAN,
            prev_baseline_eligible BOOLEAN,
            curr_baseline_eligible BOOLEAN,
            centroid_shift_m DOUBLE PRECISION NOT NULL DEFAULT 0,
            prev_p90_radius_m DOUBLE PRECISION,
            curr_p90_radius_m DOUBLE PRECISION,
            PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        )
        """
    )
    execute('ALTER TABLE rb5.snapshot_diff_cell ADD COLUMN IF NOT EXISTS tech_norm TEXT')
    execute(
        """
        ALTER TABLE rb5.snapshot_diff_cell
        DROP CONSTRAINT IF EXISTS snapshot_diff_cell_pkey
        """
    )
    execute(
        """
        ALTER TABLE rb5.snapshot_diff_cell
        ADD CONSTRAINT snapshot_diff_cell_pkey
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.snapshot_diff_bs (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            lac BIGINT NOT NULL,
            bs_id BIGINT NOT NULL,
            diff_kind TEXT NOT NULL,
            prev_lifecycle_state TEXT,
            curr_lifecycle_state TEXT,
            prev_cell_count BIGINT,
            curr_cell_count BIGINT,
            centroid_shift_m DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (batch_id, operator_code, lac, bs_id)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.snapshot_diff_lac (
            batch_id INTEGER NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            operator_code TEXT NOT NULL,
            lac BIGINT NOT NULL,
            diff_kind TEXT NOT NULL,
            prev_lifecycle_state TEXT,
            curr_lifecycle_state TEXT,
            prev_bs_count BIGINT,
            curr_bs_count BIGINT,
            prev_area_km2 DOUBLE PRECISION,
            curr_area_km2 DOUBLE PRECISION,
            PRIMARY KEY (batch_id, operator_code, lac)
        )
        """
    )
    execute('CREATE INDEX IF NOT EXISTS idx_profile_base_run ON rb5.profile_base (run_id)') if relation_exists('rb5.profile_base') else None
    create_snapshot_views()


def create_snapshot_views() -> None:
    execute(
        """
        CREATE OR REPLACE VIEW rb5.trusted_snapshot AS
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'cell'::text AS level,
            operator_code, operator_cn, lac, bs_id, cell_id,
            lifecycle_state, is_registered, anchor_eligible, baseline_eligible,
            center_lon, center_lat,
            p50_radius_m,
            p90_radius_m,
            position_grade,
            NULL::bigint AS cell_count,
            NULL::bigint AS qualified_cell_count,
            NULL::bigint AS excellent_cell_count,
            NULL::bigint AS bs_count,
            NULL::bigint AS qualified_bs_count,
            NULL::double precision AS area_km2
        FROM rb5.trusted_snapshot_cell
        UNION ALL
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'bs'::text AS level,
            operator_code, operator_cn, lac, bs_id, NULL::bigint AS cell_id,
            lifecycle_state, is_registered, anchor_eligible, baseline_eligible,
            center_lon, center_lat,
            gps_p50_dist_m AS p50_radius_m,
            gps_p90_dist_m AS p90_radius_m,
            position_grade,
            cell_count,
            qualified_cell_count,
            excellent_cell_count,
            NULL::bigint AS bs_count,
            NULL::bigint AS qualified_bs_count,
            NULL::double precision AS area_km2
        FROM rb5.trusted_snapshot_bs
        UNION ALL
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'lac'::text AS level,
            operator_code, operator_cn, lac, NULL::bigint AS bs_id, NULL::bigint AS cell_id,
            lifecycle_state, is_registered, anchor_eligible, baseline_eligible,
            center_lon, center_lat,
            NULL::double precision AS p50_radius_m,
            NULL::double precision AS p90_radius_m,
            position_grade,
            NULL::bigint AS cell_count,
            NULL::bigint AS qualified_cell_count,
            NULL::bigint AS excellent_cell_count,
            bs_count,
            qualified_bs_count,
            area_km2
        FROM rb5.trusted_snapshot_lac
        """
    )
    execute(
        """
        CREATE OR REPLACE VIEW rb5.snapshot_diff AS
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'cell'::text AS level,
            operator_code, lac, bs_id, cell_id,
            diff_kind,
            prev_lifecycle_state,
            curr_lifecycle_state,
            centroid_shift_m,
            prev_p90_radius_m,
            curr_p90_radius_m,
            NULL::bigint AS prev_count,
            NULL::bigint AS curr_count,
            NULL::double precision AS prev_area_km2,
            NULL::double precision AS curr_area_km2
        FROM rb5.snapshot_diff_cell
        UNION ALL
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'bs'::text AS level,
            operator_code, lac, bs_id, NULL::bigint AS cell_id,
            diff_kind,
            prev_lifecycle_state,
            curr_lifecycle_state,
            centroid_shift_m,
            NULL::double precision AS prev_p90_radius_m,
            NULL::double precision AS curr_p90_radius_m,
            prev_cell_count,
            curr_cell_count,
            NULL::double precision AS prev_area_km2,
            NULL::double precision AS curr_area_km2
        FROM rb5.snapshot_diff_bs
        UNION ALL
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            'lac'::text AS level,
            operator_code, lac, NULL::bigint AS bs_id, NULL::bigint AS cell_id,
            diff_kind,
            prev_lifecycle_state,
            curr_lifecycle_state,
            0::double precision AS centroid_shift_m,
            NULL::double precision AS prev_p90_radius_m,
            NULL::double precision AS curr_p90_radius_m,
            prev_bs_count,
            curr_bs_count,
            prev_area_km2,
            curr_area_km2
        FROM rb5.snapshot_diff_lac
        """
    )


def relation_exists(relation_name: str) -> bool:
    row = fetchone('SELECT to_regclass(%s) IS NOT NULL AS exists', (relation_name,))
    return bool(row['exists']) if row else False


STEP2_INPUT_SCOPE_RELATION = 'rb5.step2_batch_input'
STEP2_FALLBACK_CELL_RELATION = 'rb5._step2_cell_input'


def get_step2_input_relation(*, override: str | None = None) -> str:
    """Return the relation Step 2 should consume for the current batch.

    Default behavior keeps backward compatibility with the historical full-table
    rerun flow by reading ``rb5.etl_cleaned``. Daily rebaseline / daily
    increment scripts can materialize ``rb5.step2_batch_input`` to scope
    Step 2 to a single day without touching downstream logic.
    """
    if override:
        if not relation_exists(override):
            raise RuntimeError(f"input_relation '{override}' does not exist")
        return override
    if relation_exists(STEP2_INPUT_SCOPE_RELATION):
        return STEP2_INPUT_SCOPE_RELATION
    if relation_exists(STEP2_FALLBACK_CELL_RELATION):
        return STEP2_FALLBACK_CELL_RELATION
    if relation_exists('rb5.etl_cleaned'):
        execute(f'DROP TABLE IF EXISTS {STEP2_FALLBACK_CELL_RELATION}')
        execute(f'CREATE UNLOGGED TABLE {STEP2_FALLBACK_CELL_RELATION} AS SELECT * FROM rb5.etl_cleaned')
        _disable_autovacuum(STEP2_FALLBACK_CELL_RELATION)
        execute(f'CREATE INDEX IF NOT EXISTS idx_step2_cell_input_cell ON {STEP2_FALLBACK_CELL_RELATION} (cell_id)')
        execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_step2_cell_input_lookup
            ON {STEP2_FALLBACK_CELL_RELATION} (operator_filled, lac_filled, bs_id, cell_id, tech_norm)
            """
        )
        execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_step2_cell_input_dim_time
            ON {STEP2_FALLBACK_CELL_RELATION} (operator_filled, lac_filled, cell_id, tech_norm, event_time_std)
            """
        )
        execute(f'CREATE INDEX IF NOT EXISTS idx_step2_cell_input_source_uid ON {STEP2_FALLBACK_CELL_RELATION} (source_row_uid)')
        execute(f'CREATE INDEX IF NOT EXISTS idx_step2_cell_input_event_time ON {STEP2_FALLBACK_CELL_RELATION} (event_time_std)')
        execute(f'ANALYZE {STEP2_FALLBACK_CELL_RELATION}')
        return STEP2_FALLBACK_CELL_RELATION
    return 'rb5.etl_cleaned'


def get_latest_batch_id() -> int:
    if not relation_exists('rb5.trusted_snapshot_cell'):
        return 0
    row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5.trusted_snapshot_cell')
    return int(row['batch_id']) if row else 0


def get_latest_published_batch_id() -> int:
    if not relation_exists('rb5.trusted_cell_library'):
        return 0
    row = fetchone('SELECT COALESCE(MAX(batch_id), 0) AS batch_id FROM rb5.trusted_cell_library')
    return int(row['batch_id']) if row else 0


def ensure_step2_indexes() -> None:
    if relation_exists('rb5.etl_cleaned'):
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
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rb5.etl_cleaned (record_id)')
        execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_source_uid ON rb5.etl_cleaned (source_row_uid)')
    if relation_exists('rb5.trusted_cell_library'):
        execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trusted_cell_library_lookup
            ON rb5.trusted_cell_library (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
            """
        )
    if relation_exists('rb5.collision_id_list'):
        execute('CREATE INDEX IF NOT EXISTS idx_collision_id_list_cell_id ON rb5.collision_id_list (cell_id)')



def run_step2_pipeline(
    *,
    run_id: str,
    batch_id: int,
    previous_snapshot_version: str,
    antitoxin_thresholds: dict[str, float],
    input_relation: str | None = None,
) -> dict[str, Any]:
    ensure_step2_indexes()
    step2_input = get_step2_input_relation(override=input_relation)
    build_path_a_records(run_id, antitoxin_thresholds=antitoxin_thresholds, input_relation=step2_input)
    profile_params = load_profile_params()
    tech_whitelist = profile_params.get('routing', {}).get('path_b_tech_whitelist', ['4G', '5G'])
    build_path_b_cells(run_id, tech_whitelist=tech_whitelist, input_relation=step2_input)
    build_profile_obs(run_id)
    build_profile_base(run_id)
    persist_candidate_seed_history(batch_id=batch_id, run_id=run_id, input_relation=step2_input)
    stats = write_step2_run_stats(
        run_id=run_id,
        batch_id=batch_id,
        previous_snapshot_version=previous_snapshot_version,
        input_relation=step2_input,
    )
    cleanup_step2_temp_tables()
    return stats


def build_path_a_records(
    run_id: str,
    *,
    antitoxin_thresholds: dict[str, float],
    input_relation: str | None = None,
) -> None:
    input_relation = get_step2_input_relation(override=input_relation)
    execute('DROP TABLE IF EXISTS rb5.path_a_records')
    execute('DROP TABLE IF EXISTS rb5._profile_path_a_candidates')
    for table_name in (
        'rb5._path_a_latest_library',
        'rb5._path_a_collision_cells',
        'rb5._path_a_latest_unique_cell',
        'rb5._path_a_layer1',
        'rb5._path_a_layer2',
        'rb5._path_a_layer3_all',
        'rb5._path_a_layer3',
    ):
        execute(f'DROP TABLE IF EXISTS {table_name}')
    if not relation_exists('rb5.trusted_cell_library'):
        execute(
            """
            CREATE UNLOGGED TABLE rb5._profile_path_a_candidates AS
            SELECT
                NULL::text AS run_id,
                NULL::text AS source_tid,
                NULL::varchar AS record_id,
                NULL::text AS match_status,
                NULL::boolean AS is_collision_id,
                NULL::double precision AS distance_to_ref_m,
                NULL::text AS match_layer,
                NULL::bigint AS donor_cell_id
            WHERE false
            """
        )
        _disable_autovacuum('rb5._profile_path_a_candidates')
        execute(
            f"""
            CREATE UNLOGGED TABLE rb5.path_a_records AS
            SELECT NULL::text AS source_tid, e.*, %s::text AS run_id
            FROM {input_relation} e
            WHERE false
            """,
            (run_id,),
        )
        _disable_autovacuum('rb5.path_a_records')
        return

    # Three-layer Path A matching:
    # Layer 1: exact match (operator + lac + cell_id all present and match)
    # Layer 2: relaxed match for non-collision cell_ids (operator/lac may be NULL)
    # Layer 3: collision cell_id with missing operator → GPS proximity fallback
    _lib_batch_sql = "(SELECT COALESCE(MAX(batch_id), 0) FROM rb5.trusted_cell_library)"
    execute('DROP TABLE IF EXISTS rb5._path_a_latest_library')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._path_a_latest_library AS
        SELECT
            batch_id,
            snapshot_version,
            operator_code,
            lac,
            cell_id,
            tech_norm,
            lifecycle_state,
            position_grade,
            center_lon,
            center_lat,
            p50_radius_m,
            p90_radius_m,
            rsrp_avg,
            rsrq_avg,
            sinr_avg,
            pressure_avg,
            anchor_eligible,
            baseline_eligible,
            independent_obs
        FROM rb5.trusted_cell_library
        WHERE batch_id = {_lib_batch_sql}
        """
    )
    _disable_autovacuum('rb5._path_a_latest_library')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_path_a_latest_exact
        ON rb5._path_a_latest_library (operator_code, lac, cell_id, tech_norm)
        """
    )
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_path_a_latest_cell
        ON rb5._path_a_latest_library (cell_id)
        """
    )

    execute('DROP TABLE IF EXISTS rb5._path_a_collision_cells')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._path_a_collision_cells AS
        SELECT DISTINCT cell_id
        FROM rb5.collision_id_list
        WHERE batch_id = {_lib_batch_sql}
        """
    )
    _disable_autovacuum('rb5._path_a_collision_cells')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_path_a_collision_cells_cell_id
        ON rb5._path_a_collision_cells (cell_id)
        """
    )

    execute('DROP TABLE IF EXISTS rb5._path_a_latest_unique_cell')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._path_a_latest_unique_cell AS
        SELECT DISTINCT ON (cell_id)
            batch_id,
            snapshot_version,
            operator_code,
            lac,
            cell_id,
            tech_norm
        FROM rb5._path_a_latest_library
        ORDER BY cell_id, independent_obs DESC NULLS LAST
        """
    )
    _disable_autovacuum('rb5._path_a_latest_unique_cell')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_path_a_latest_unique_cell
        ON rb5._path_a_latest_unique_cell (cell_id)
        """
    )

    execute('DROP TABLE IF EXISTS rb5._path_a_layer1')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._path_a_layer1 AS
        SELECT
            e.source_row_uid AS source_tid,
            e.record_id,
            'direct_match'::text AS match_status,
            FALSE AS is_collision_id,
            NULL::double precision AS distance_to_ref_m,
            'layer1_exact'::text AS match_layer,
            l.batch_id AS donor_batch_id,
            l.snapshot_version AS donor_snapshot_version,
            l.cell_id AS donor_cell_id,
            l.operator_code AS donor_operator_code,
            l.lac AS donor_lac,
            l.tech_norm AS donor_tech_norm
        FROM {input_relation} e
        JOIN rb5._path_a_latest_library l
          ON l.cell_id = e.cell_id
         AND l.operator_code = e.operator_filled
         AND l.lac = e.lac_filled
         AND COALESCE(l.tech_norm, e.tech_norm) = e.tech_norm
        WHERE e.cell_id IS NOT NULL
          AND e.operator_filled IS NOT NULL
          AND e.lac_filled IS NOT NULL
        """
    )
    _disable_autovacuum('rb5._path_a_layer1')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_path_a_layer1_source_tid
        ON rb5._path_a_layer1 (source_tid)
        """
    )

    execute('DROP TABLE IF EXISTS rb5._path_a_layer2')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._path_a_layer2 AS
        SELECT
            e.source_row_uid AS source_tid,
            e.record_id,
            'relaxed_match'::text AS match_status,
            FALSE AS is_collision_id,
            NULL::double precision AS distance_to_ref_m,
            'layer2_relaxed'::text AS match_layer,
            l.batch_id AS donor_batch_id,
            l.snapshot_version AS donor_snapshot_version,
            l.cell_id AS donor_cell_id,
            l.operator_code AS donor_operator_code,
            l.lac AS donor_lac,
            l.tech_norm AS donor_tech_norm
        FROM {input_relation} e
        JOIN rb5._path_a_latest_unique_cell l
          ON l.cell_id = e.cell_id
        LEFT JOIN rb5._path_a_collision_cells c
          ON c.cell_id = e.cell_id
        LEFT JOIN rb5._path_a_layer1 x
          ON x.source_tid = e.source_row_uid
         AND x.donor_cell_id = e.cell_id
        WHERE e.cell_id IS NOT NULL
          AND c.cell_id IS NULL
          AND x.source_tid IS NULL
        """
    )
    _disable_autovacuum('rb5._path_a_layer2')
    execute(
        """
        CREATE INDEX idx_path_a_layer2_source_tid
        ON rb5._path_a_layer2 (source_tid)
        """
    )

    execute('DROP TABLE IF EXISTS rb5._path_a_layer3_all')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._path_a_layer3_all AS
        SELECT
            e.source_row_uid AS source_tid,
            e.record_id,
            CASE
                WHEN NOT (e.lon_raw IS NOT NULL AND e.lat_raw IS NOT NULL AND e.gps_valid)
                    THEN 'pending_no_gps'
                WHEN l.center_lon IS NULL OR l.center_lat IS NULL
                    THEN 'pending_no_gps'
                WHEN SQRT(POWER((e.lon_raw - l.center_lon) * 85300, 2) + POWER((e.lat_raw - l.center_lat) * 111000, 2)) <= {antitoxin_thresholds['collision_min_spread_m']}
                    THEN 'collision_matched'
                ELSE 'collision_dropped'
            END AS match_status,
            TRUE AS is_collision_id,
            CASE
                WHEN e.lon_raw IS NULL OR l.center_lon IS NULL THEN NULL::double precision
                ELSE SQRT(POWER((e.lon_raw - l.center_lon) * 85300, 2) + POWER((e.lat_raw - l.center_lat) * 111000, 2))
            END AS distance_to_ref_m,
            'layer3_collision_gps'::text AS match_layer,
            l.batch_id AS donor_batch_id,
            l.snapshot_version AS donor_snapshot_version,
            l.cell_id AS donor_cell_id,
            l.operator_code AS donor_operator_code,
            l.lac AS donor_lac,
            l.tech_norm AS donor_tech_norm
        FROM {input_relation} e
        JOIN rb5._path_a_collision_cells c
          ON c.cell_id = e.cell_id
        JOIN rb5._path_a_latest_library l
          ON l.cell_id = e.cell_id
         AND (e.operator_filled IS NULL OR l.operator_code = e.operator_filled)
         AND (e.lac_filled IS NULL OR l.lac = e.lac_filled)
        LEFT JOIN rb5._path_a_layer1 x
          ON x.source_tid = e.source_row_uid
         AND x.donor_cell_id = e.cell_id
        WHERE e.cell_id IS NOT NULL
          AND x.source_tid IS NULL
        """
    )
    _disable_autovacuum('rb5._path_a_layer3_all')

    execute('DROP TABLE IF EXISTS rb5._path_a_layer3')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._path_a_layer3 AS
        SELECT DISTINCT ON (source_tid)
            source_tid,
            record_id,
            match_status,
            is_collision_id,
            distance_to_ref_m,
            match_layer,
            donor_batch_id,
            donor_snapshot_version,
            donor_cell_id,
            donor_operator_code,
            donor_lac,
            donor_tech_norm
        FROM rb5._path_a_layer3_all
        ORDER BY source_tid,
            CASE match_status WHEN 'collision_matched' THEN 0 WHEN 'pending_no_gps' THEN 1 ELSE 2 END,
            distance_to_ref_m NULLS LAST
        """
    )
    _disable_autovacuum('rb5._path_a_layer3')

    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_path_a_candidates AS
        SELECT
            source_tid,
            record_id,
            match_status,
            is_collision_id,
            distance_to_ref_m,
            match_layer,
            donor_batch_id,
            donor_snapshot_version,
            donor_cell_id,
            donor_operator_code,
            donor_lac,
            donor_tech_norm
        FROM rb5._path_a_layer1
        UNION ALL
        SELECT
            source_tid,
            record_id,
            match_status,
            is_collision_id,
            distance_to_ref_m,
            match_layer,
            donor_batch_id,
            donor_snapshot_version,
            donor_cell_id,
            donor_operator_code,
            donor_lac,
            donor_tech_norm
        FROM rb5._path_a_layer2
        UNION ALL
        SELECT
            source_tid,
            record_id,
            match_status,
            is_collision_id,
            distance_to_ref_m,
            match_layer,
            donor_batch_id,
            donor_snapshot_version,
            donor_cell_id,
            donor_operator_code,
            donor_lac,
            donor_tech_norm
        FROM rb5._path_a_layer3
        """
    )
    _disable_autovacuum('rb5._profile_path_a_candidates')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_profile_path_a_candidates_source_tid
        ON rb5._profile_path_a_candidates (source_tid)
        """
    )
    # Carry the Step-2-selected donor directly into path_a_records so Step 4
    # never needs to re-match against trusted_cell_library.
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5.path_a_records AS
        SELECT e.source_row_uid AS source_tid, e.*, %s::text AS run_id,
               c.match_layer, c.is_collision_id AS path_a_is_collision,
               c.donor_batch_id,
               c.donor_snapshot_version,
               c.donor_cell_id,
               c.donor_operator_code,
               c.donor_lac,
               c.donor_tech_norm,
               d.lifecycle_state AS donor_lifecycle_state,
               d.position_grade AS donor_position_grade,
               d.center_lon AS donor_center_lon,
               d.center_lat AS donor_center_lat,
               d.p50_radius_m AS donor_p50_radius_m,
               d.p90_radius_m AS donor_p90_radius_m,
               d.rsrp_avg AS donor_rsrp_avg,
               d.rsrq_avg AS donor_rsrq_avg,
               d.sinr_avg AS donor_sinr_avg,
               d.pressure_avg AS donor_pressure_avg,
               d.anchor_eligible AS donor_anchor_eligible,
               d.baseline_eligible AS donor_baseline_eligible
        FROM {input_relation} e
        JOIN rb5._profile_path_a_candidates c
          ON c.source_tid = e.source_row_uid
         AND c.donor_cell_id = e.cell_id
        LEFT JOIN rb5._path_a_latest_library d
          ON d.batch_id = c.donor_batch_id
         AND d.operator_code = c.donor_operator_code
         AND d.lac = c.donor_lac
         AND d.cell_id = c.donor_cell_id
         AND d.tech_norm IS NOT DISTINCT FROM c.donor_tech_norm
        WHERE c.match_status IN ('direct_match', 'relaxed_match', 'collision_matched')
        """,
        (run_id,),
    )
    _disable_autovacuum('rb5.path_a_records')
    execute('CREATE INDEX IF NOT EXISTS idx_path_a_records_record_id ON rb5.path_a_records (record_id)')
    execute('CREATE INDEX IF NOT EXISTS idx_path_a_records_source_tid ON rb5.path_a_records (source_tid)')


def build_path_b_cells(
    run_id: str,
    *,
    tech_whitelist: list[str] | None = None,
    input_relation: str | None = None,
) -> None:
    input_relation = get_step2_input_relation(override=input_relation)
    allowed_techs = tech_whitelist or ['4G', '5G']
    tech_in = ','.join(f"'{t}'" for t in allowed_techs)
    execute('DROP TABLE IF EXISTS rb5._profile_path_b_cells')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._profile_path_b_cells AS
        SELECT
            %s::text AS run_id,
            %s::text AS dataset_key,
            e.operator_filled AS operator_code,
            COALESCE(MAX(e.operator_cn), '未知') AS operator_cn,
            e.lac_filled AS lac,
            MODE() WITHIN GROUP (ORDER BY e.bs_id) AS bs_id,
            e.cell_id,
            e.tech_norm,
            COUNT(*) AS record_count,
            BOOL_OR(e.lon_raw IS NOT NULL AND e.lat_raw IS NOT NULL AND e.gps_valid) AS has_raw_gps,
            COUNT(*) FILTER (WHERE e.lon_raw IS NOT NULL AND e.lat_raw IS NOT NULL AND e.gps_valid) AS raw_gps_record_count,
            COUNT(*) FILTER (WHERE e.rsrp IS NOT NULL) AS signal_original_count
        FROM {input_relation} e
        LEFT JOIN rb5.path_a_records a
          ON a.source_tid = e.source_row_uid
         AND a.cell_id = e.cell_id
        WHERE e.cell_id IS NOT NULL
          AND e.operator_filled IS NOT NULL
          AND e.lac_filled IS NOT NULL
          AND e.tech_norm IN ({tech_in})
          AND a.source_tid IS NULL
        GROUP BY e.operator_filled, e.lac_filled, e.cell_id, e.tech_norm
        """,
        (run_id, DATASET_KEY),
    )
    _disable_autovacuum('rb5._profile_path_b_cells')
    execute(
        """
        CREATE INDEX idx_profile_path_b_cells_key
        ON rb5._profile_path_b_cells (operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rb5._profile_path_b_cells')
    execute('DROP TABLE IF EXISTS rb5._profile_path_b_records')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._profile_path_b_records AS
        SELECT
            c.run_id,
            c.dataset_key,
            c.operator_code,
            c.operator_cn,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            e.cell_origin,
            e.timing_advance,
            e.freq_channel,
            e.record_id,
            e.dev_id,
            e.event_time_std,
            e.lon_raw,
            e.lat_raw,
            e.gps_valid,
            e.rsrp,
            e.rsrq,
            e.sinr
        FROM {input_relation} e
        LEFT JOIN rb5.path_a_records a
          ON a.source_tid = e.source_row_uid
         AND a.cell_id = e.cell_id
        JOIN rb5._profile_path_b_cells c
          ON c.operator_code = e.operator_filled
         AND c.lac = e.lac_filled
         AND c.cell_id = e.cell_id
         AND c.tech_norm = e.tech_norm
        WHERE c.has_raw_gps
          AND a.source_tid IS NULL
        """
    )
    _disable_autovacuum('rb5._profile_path_b_records')


def build_profile_obs(run_id: str) -> None:
    # 设计原则（docs/03_流式质量评估.md §GPS 有效性）：
    # 每个 profile_obs 记录必须 GPS 有效。无 GPS 的分钟级观测不应参与
    # independent_obs 计数。否则仅含信号记录的 cell 会凭虚高的观测数晋级。
    execute('DROP TABLE IF EXISTS rb5.profile_obs')
    execute(
        """
        CREATE UNLOGGED TABLE rb5.profile_obs AS
        SELECT
            %s::text AS run_id,
            %s::text AS dataset_key,
            operator_code,
            operator_cn,
            lac,
            cell_id,
            tech_norm,
            date_trunc('minute', event_time_std) AS obs_minute,
            DATE(event_time_std) AS obs_date,
            AVG(lon_raw) AS lon,
            AVG(lat_raw) AS lat,
            AVG(rsrp) FILTER (WHERE rsrp BETWEEN -156 AND -1) AS rsrp,
            AVG(rsrq) FILTER (WHERE rsrq BETWEEN -34 AND 10) AS rsrq,
            AVG(sinr) FILTER (WHERE sinr BETWEEN -23 AND 40) AS sinr,
            COUNT(*) AS raw_records,
            COUNT(*) AS gps_original_records,
            COUNT(*) FILTER (WHERE rsrp IS NOT NULL) AS signal_original_records
        FROM rb5._profile_path_b_records
        WHERE lon_raw IS NOT NULL AND lat_raw IS NOT NULL AND gps_valid
        GROUP BY operator_code, operator_cn, lac, cell_id, tech_norm, date_trunc('minute', event_time_std), DATE(event_time_std)
        """,
        (run_id, DATASET_KEY),
    )
    _disable_autovacuum('rb5.profile_obs')


def build_profile_base(run_id: str) -> None:
    mad_filter = load_core_mad_filter_params(load_antitoxin_params())
    effective_k_sql = build_core_mad_k_sql('m.total_pts', mad_filter)
    execute('DROP TABLE IF EXISTS rb5._profile_gps_day_dedup')
    # 去重键（DEDUP-V2.1）：按 origin 区分去重粒度。
    # - cell_infos: (cell, dev, cell_infos, 5min_bucket)
    # - ss1: (cell, dev, ss1, record_id)
    # 原因：天去重会把单设备多次上报压成 1 点，导致半径统计对远点污染敏感
    # （占比被稀释从 5% 放大到 50%）。cell_infos 保留每设备每 5 分钟 1 点；
    # ss1 每 raw_gps 报文只保留 1 点，按 record_id 去掉 forward-fill 冗余。
    # 表名沿用 _profile_gps_day_dedup 仅为向后兼容，语义已变化。
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_gps_day_dedup AS
        SELECT DISTINCT ON (
            run_id,
            dataset_key,
            operator_code,
            lac,
            cell_id,
            tech_norm,
            COALESCE(NULLIF(dev_id, ''), record_id),
            COALESCE(cell_origin, ''),
            CASE WHEN cell_origin = 'ss1'
                 THEN 'rid:' || record_id
                 ELSE 'bk5:' || to_char(
                   date_trunc('minute', event_time_std)
                     - ((EXTRACT(MINUTE FROM event_time_std)::int % 5) * INTERVAL '1 minute'),
                   'YYYY-MM-DD HH24:MI')
            END
        )
            run_id,
            dataset_key,
            operator_code,
            operator_cn,
            lac,
            cell_id,
            tech_norm,
            cell_origin,
            COALESCE(NULLIF(dev_id, ''), record_id) AS dedup_dev_id,
            DATE(event_time_std) AS obs_date,
            date_trunc('minute', event_time_std) AS obs_minute,
            date_trunc('minute', event_time_std)
              - ((EXTRACT(MINUTE FROM event_time_std)::int % 5) * INTERVAL '1 minute') AS obs_bucket_5min,
            event_time_std,
            lon_raw AS lon,
            lat_raw AS lat
        FROM rb5._profile_path_b_records
        WHERE lon_raw IS NOT NULL
          AND lat_raw IS NOT NULL
          AND gps_valid
          AND event_time_std IS NOT NULL
        ORDER BY
            run_id,
            dataset_key,
            operator_code,
            lac,
            cell_id,
            tech_norm,
            COALESCE(NULLIF(dev_id, ''), record_id),
            COALESCE(cell_origin, ''),
            CASE WHEN cell_origin = 'ss1'
                 THEN 'rid:' || record_id
                 ELSE 'bk5:' || to_char(
                   date_trunc('minute', event_time_std)
                     - ((EXTRACT(MINUTE FROM event_time_std)::int % 5) * INTERVAL '1 minute'),
                   'YYYY-MM-DD HH24:MI')
            END,
            event_time_std,
            record_id
        """
    )
    _disable_autovacuum('rb5._profile_gps_day_dedup')
    execute(
        """
        CREATE INDEX idx_profile_gps_day_dedup_key
        ON rb5._profile_gps_day_dedup (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_core_initial_center')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_core_initial_center AS
        SELECT
            run_id,
            dataset_key,
            operator_code,
            lac,
            cell_id,
            tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon0,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat0
        FROM rb5._profile_gps_day_dedup
        GROUP BY run_id, dataset_key, operator_code, lac, cell_id, tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_core_initial_center')
    execute(
        """
        CREATE INDEX idx_profile_core_initial_center_key
        ON rb5._profile_core_initial_center (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_core_point_distance')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_core_point_distance AS
        SELECT
            p.run_id,
            p.dataset_key,
            p.operator_code,
            p.operator_cn,
            p.lac,
            p.cell_id,
            p.tech_norm,
            p.dedup_dev_id,
            p.obs_minute,
            p.obs_date,
            p.event_time_std,
            p.lon,
            p.lat,
            SQRT(POWER((p.lon - c.center_lon0) * 85300, 2)
               + POWER((p.lat - c.center_lat0) * 111000, 2)) AS dist_to_center0_m
        FROM rb5._profile_gps_day_dedup p
        JOIN rb5._profile_core_initial_center c
          ON c.run_id = p.run_id
         AND c.dataset_key = p.dataset_key
         AND c.operator_code = p.operator_code
         AND c.lac = p.lac
         AND c.cell_id = p.cell_id
         AND c.tech_norm = p.tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_core_point_distance')
    execute(
        """
        CREATE INDEX idx_profile_core_point_distance_key
        ON rb5._profile_core_point_distance (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_core_mad_stats')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._profile_core_mad_stats AS
        WITH med AS (
            SELECT
                run_id,
                dataset_key,
                operator_code,
                lac,
                cell_id,
                tech_norm,
                COUNT(*) AS total_pts,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dist_to_center0_m) AS med_dist_m
            FROM rb5._profile_core_point_distance
            GROUP BY run_id, dataset_key, operator_code, lac, cell_id, tech_norm
        )
        SELECT
            d.run_id,
            d.dataset_key,
            d.operator_code,
            d.lac,
            d.cell_id,
            d.tech_norm,
            m.total_pts,
            m.med_dist_m,
            COALESCE(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.dist_to_center0_m - m.med_dist_m)),
                0
            ) AS mad_dist_m,
            {effective_k_sql} AS effective_k_mad,
            (m.med_dist_m + ({effective_k_sql}) * COALESCE(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.dist_to_center0_m - m.med_dist_m)),
                0
            )) AS keep_threshold_m,
            {int(mad_filter['min_pts'])} AS min_pts
        FROM rb5._profile_core_point_distance d
        JOIN med m
          ON m.run_id = d.run_id
         AND m.dataset_key = d.dataset_key
         AND m.operator_code = d.operator_code
         AND m.lac = d.lac
         AND m.cell_id = d.cell_id
         AND m.tech_norm = d.tech_norm
        GROUP BY
            d.run_id,
            d.dataset_key,
            d.operator_code,
            d.lac,
            d.cell_id,
            d.tech_norm,
            m.total_pts,
            m.med_dist_m
        """
    )
    _disable_autovacuum('rb5._profile_core_mad_stats')
    execute(
        """
        CREATE INDEX idx_profile_core_mad_stats_key
        ON rb5._profile_core_mad_stats (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_core_points')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_core_points AS
        SELECT
            d.run_id,
            d.dataset_key,
            d.operator_code,
            d.operator_cn,
            d.lac,
            d.cell_id,
            d.tech_norm,
            d.dedup_dev_id,
            d.obs_minute,
            d.obs_date,
            d.event_time_std,
            d.lon,
            d.lat,
            s.total_pts,
            s.med_dist_m,
            s.mad_dist_m,
            s.effective_k_mad,
            s.keep_threshold_m,
            CASE
                WHEN s.total_pts < s.min_pts THEN TRUE
                ELSE d.dist_to_center0_m <= s.keep_threshold_m
            END AS is_core
        FROM rb5._profile_core_point_distance d
        JOIN rb5._profile_core_mad_stats s
          ON s.run_id = d.run_id
         AND s.dataset_key = d.dataset_key
         AND s.operator_code = d.operator_code
         AND s.lac = d.lac
         AND s.cell_id = d.cell_id
         AND s.tech_norm = d.tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_core_points')
    execute(
        """
        CREATE INDEX idx_profile_core_points_key
        ON rb5._profile_core_points (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_core_gps')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_core_gps AS
        SELECT
            run_id,
            dataset_key,
            operator_code,
            operator_cn,
            lac,
            cell_id,
            tech_norm,
            COUNT(*) FILTER (WHERE is_core) AS gps_valid_count,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) FILTER (WHERE is_core) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) FILTER (WHERE is_core) AS center_lat,
            MIN(obs_minute) FILTER (WHERE is_core) AS first_obs_at,
            MAX(obs_minute) FILTER (WHERE is_core) AS last_obs_at,
            EXTRACT(EPOCH FROM MAX(obs_minute) FILTER (WHERE is_core)
                - MIN(obs_minute) FILTER (WHERE is_core)) / 3600.0 AS observed_span_hours,
            COUNT(DISTINCT obs_date) FILTER (WHERE is_core) AS active_days
        FROM rb5._profile_core_points
        GROUP BY run_id, dataset_key, operator_code, operator_cn, lac, cell_id, tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_core_gps')
    execute(
        """
        CREATE INDEX idx_profile_core_gps_key
        ON rb5._profile_core_gps (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_counts')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_counts AS
        SELECT
            run_id,
            dataset_key,
            operator_code,
            operator_cn,
            lac,
            cell_id,
            tech_norm,
            COUNT(*) AS independent_obs,
            COUNT(DISTINCT obs_date) AS independent_days,
            AVG(rsrp) AS rsrp_avg,
            AVG(rsrq) AS rsrq_avg,
            AVG(sinr) AS sinr_avg,
            MIN(obs_minute) AS first_obs_at,
            MAX(obs_minute) AS last_obs_at,
            EXTRACT(EPOCH FROM MAX(obs_minute) - MIN(obs_minute)) / 3600.0 AS observed_span_hours,
            SUM(raw_records) AS record_count,
            SUM(gps_original_records) AS gps_original_count,
            SUM(signal_original_records) AS signal_original_count
        FROM rb5.profile_obs
        GROUP BY run_id, dataset_key, operator_code, operator_cn, lac, cell_id, tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_counts')
    execute(
        """
        CREATE INDEX idx_profile_counts_key
        ON rb5._profile_counts (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('DROP TABLE IF EXISTS rb5._profile_devs')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_devs AS
        SELECT
            run_id,
            dataset_key,
            operator_code,
            lac,
            cell_id,
            tech_norm,
            COUNT(DISTINCT dev_id) AS independent_devs
        FROM rb5._profile_path_b_records
        GROUP BY run_id, dataset_key, operator_code, lac, cell_id, tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_devs')
    execute('CREATE INDEX idx_tmp_devs ON rb5._profile_devs (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)')
    execute('DROP TABLE IF EXISTS rb5._profile_radius')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._profile_radius AS
        SELECT
            p.run_id,
            p.dataset_key,
            p.operator_code,
            p.lac,
            p.cell_id,
            p.tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY SQRT(POWER((p.lon - c.center_lon) * 85300, 2) + POWER((p.lat - c.center_lat) * 111000, 2))
            ) FILTER (WHERE p.is_core) AS p50_radius_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (
                ORDER BY SQRT(POWER((p.lon - c.center_lon) * 85300, 2) + POWER((p.lat - c.center_lat) * 111000, 2))
            ) FILTER (WHERE p.is_core) AS p90_radius_m
        FROM rb5._profile_core_points p
        JOIN rb5._profile_core_gps c
          ON c.run_id = p.run_id
         AND c.dataset_key = p.dataset_key
         AND c.operator_code = p.operator_code
         AND c.lac = p.lac
         AND c.cell_id = p.cell_id
         AND c.tech_norm = p.tech_norm
        GROUP BY p.run_id, p.dataset_key, p.operator_code, p.lac, p.cell_id, p.tech_norm
        """
    )
    _disable_autovacuum('rb5._profile_radius')
    execute('CREATE INDEX idx_tmp_radius ON rb5._profile_radius (run_id, dataset_key, operator_code, lac, cell_id, tech_norm)')
    # Derive bs_id from path_b_cells (MODE aggregated, not part of Cell key)
    execute('DROP TABLE IF EXISTS rb5.profile_base')
    execute(
        """
        CREATE UNLOGGED TABLE rb5.profile_base AS
        SELECT
            c.run_id,
            c.dataset_key,
            c.operator_code,
            c.operator_cn,
            c.lac,
            b.bs_id,
            c.cell_id,
            c.tech_norm,
            c.independent_obs,
            d.independent_devs,
            c.independent_days,
            c.record_count,
            COALESCE(g.first_obs_at, c.first_obs_at) AS first_obs_at,
            COALESCE(g.last_obs_at, c.last_obs_at) AS last_obs_at,
            COALESCE(g.observed_span_hours, c.observed_span_hours) AS observed_span_hours,
            COALESCE(g.active_days, 0) AS active_days,
            g.center_lon,
            g.center_lat,
            r.p50_radius_m,
            r.p90_radius_m,
            c.rsrp_avg,
            c.rsrq_avg,
            c.sinr_avg,
            COALESCE(g.gps_valid_count, 0) AS gps_valid_count,
            c.gps_original_count,
            c.signal_original_count,
            COALESCE(c.gps_original_count::double precision / NULLIF(c.record_count, 0), 0) AS gps_original_ratio,
            COALESCE(COALESCE(g.gps_valid_count, 0)::double precision / NULLIF(c.independent_obs, 0), 0) AS gps_valid_ratio,
            COALESCE(c.signal_original_count::double precision / NULLIF(c.record_count, 0), 0) AS signal_original_ratio
        FROM rb5._profile_counts c
        JOIN rb5._profile_devs d
          ON d.run_id = c.run_id
         AND d.dataset_key = c.dataset_key
         AND d.operator_code = c.operator_code
         AND d.lac = c.lac
         AND d.cell_id = c.cell_id
         AND d.tech_norm = c.tech_norm
        LEFT JOIN rb5._profile_core_gps g
          ON g.run_id = c.run_id
         AND g.dataset_key = c.dataset_key
         AND g.operator_code = c.operator_code
         AND g.lac = c.lac
         AND g.cell_id = c.cell_id
         AND g.tech_norm = c.tech_norm
        LEFT JOIN rb5._profile_radius r
          ON r.run_id = c.run_id
         AND r.dataset_key = c.dataset_key
         AND r.operator_code = c.operator_code
         AND r.lac = c.lac
         AND r.cell_id = c.cell_id
         AND r.tech_norm = c.tech_norm
        LEFT JOIN rb5._profile_path_b_cells b
          ON b.operator_code = c.operator_code
         AND b.lac = c.lac
         AND b.cell_id = c.cell_id
         AND b.tech_norm = c.tech_norm
        """
    )
    _disable_autovacuum('rb5.profile_base')


def persist_candidate_seed_history(*, batch_id: int, run_id: str, input_relation: str | None = None) -> None:
    input_relation = get_step2_input_relation(override=input_relation)
    execute('DELETE FROM rb5.candidate_seed_history WHERE batch_id = %s', (batch_id,))
    execute_distributed_insert(
        f"""
        INSERT INTO rb5.candidate_seed_history (
            batch_id, run_id, dataset_key, source_row_uid, record_id, source_table,
            event_time_std, dev_id,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm, cell_origin,
            timing_advance, freq_channel,
            gps_valid,
            lon_filled, lat_filled, gps_fill_source,
            rsrp_filled, rsrq_filled, sinr_filled, pressure
        )
        SELECT
            %s::int,
            %s::text,
            %s::text,
            md5(
                concat_ws(
                    '|',
                    %s::text,
                    e.source_row_uid,
                    e.record_id,
                    COALESCE(e.operator_filled, ''),
                    COALESCE(e.lac_filled::text, ''),
                    COALESCE(c.bs_id::text, ''),
                    COALESCE(e.cell_id::text, ''),
                    COALESCE(e.tech_norm, ''),
                    COALESCE(e.dev_id, ''),
                    COALESCE(e.event_time_std::text, '')
                )
            ) AS source_row_uid,
            e.record_id,
            e.source_table,
            e.event_time_std,
            e.dev_id,
            e.operator_filled,
            c.operator_cn,
            e.lac_filled,
            c.bs_id,
            e.cell_id,
            e.tech_norm,
            e.cell_origin,
            e.timing_advance,
            e.freq_channel,
            COALESCE(e.gps_valid, FALSE),
            e.lon_filled,
            e.lat_filled,
            e.gps_fill_source,
            e.rsrp_filled,
            e.rsrq_filled,
            e.sinr_filled,
            CASE
                WHEN e.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN e.pressure::double precision
                ELSE NULL::double precision
            END
        FROM {input_relation} e
        LEFT JOIN rb5.path_a_records a
          ON a.source_tid = e.source_row_uid
         AND a.cell_id = e.cell_id
        JOIN rb5._profile_path_b_cells c
          ON c.operator_code = e.operator_filled
         AND c.lac = e.lac_filled
         AND c.cell_id = e.cell_id
         AND c.tech_norm = e.tech_norm
        WHERE c.has_raw_gps
          AND a.source_tid IS NULL
        """,
        params=(batch_id, run_id, DATASET_KEY, run_id),
    )
    execute('ANALYZE rb5.candidate_seed_history')


def write_step2_run_stats(
    *,
    run_id: str,
    batch_id: int,
    previous_snapshot_version: str,
    input_relation: str | None = None,
) -> dict[str, Any]:
    input_relation = get_step2_input_relation(override=input_relation)
    input_row = fetchone(f'SELECT COUNT(*) AS cnt FROM {input_relation}')
    path_a_row = fetchone('SELECT COUNT(*) AS cnt FROM rb5.path_a_records')
    collision_row = fetchone(
        """
        SELECT
            COUNT(*) FILTER (WHERE is_collision_id) AS candidate_count,
            COUNT(*) FILTER (WHERE match_status = 'collision_matched') AS matched_count,
            COUNT(*) FILTER (WHERE match_status = 'pending_no_gps') AS pending_count,
            COUNT(*) FILTER (WHERE match_status = 'collision_dropped') AS dropped_count,
            COUNT(*) FILTER (WHERE match_layer = 'layer1_exact') AS layer1_count,
            COUNT(*) FILTER (WHERE match_layer = 'layer2_relaxed') AS layer2_count,
            COUNT(*) FILTER (WHERE match_layer = 'layer3_collision_gps') AS layer3_count
        FROM rb5._profile_path_a_candidates
        """
    )
    path_b_row = fetchone(
        """
        SELECT
            COUNT(*) AS cell_count,
            COALESCE(SUM(record_count), 0) AS record_count
        FROM rb5._profile_path_b_cells
        WHERE has_raw_gps
        """
    )
    path_b_metrics = fetchone(
        """
        SELECT
            COUNT(*) FILTER (WHERE gps_original_ratio = 1 AND signal_original_ratio = 1) AS complete_cells,
            COUNT(*) FILTER (WHERE NOT (gps_original_ratio = 1 AND signal_original_ratio = 1)) AS partial_cells,
            COALESCE(AVG(gps_original_ratio), 0) AS avg_gps_original_ratio,
            COALESCE(AVG(signal_original_ratio), 0) AS avg_signal_original_ratio,
            COALESCE(AVG(independent_obs), 0) AS avg_independent_obs,
            COALESCE(AVG(independent_devs), 0) AS avg_independent_devs,
            COALESCE(AVG(observed_span_hours), 0) AS avg_observed_span_hours,
            COALESCE(AVG(p50_radius_m), 0) AS avg_p50_radius_m,
            COALESCE(AVG(p90_radius_m), 0) AS avg_p90_radius_m
        FROM rb5.profile_base
        """
    )

    input_count = int(input_row['cnt']) if input_row else 0
    path_a_count = int(path_a_row['cnt']) if path_a_row else 0
    path_b_record_count = int(path_b_row['record_count']) if path_b_row else 0
    path_b_cell_count = int(path_b_row['cell_count']) if path_b_row else 0
    path_c_drop_count = max(input_count - path_a_count - path_b_record_count, 0)

    stats = {
        'run_id': run_id,
        'batch_id': batch_id,
        'dataset_key': DATASET_KEY,
        'status': 'completed',
        'trusted_snapshot_version': previous_snapshot_version,
        'input_record_count': input_count,
        'path_a_record_count': path_a_count,
        'path_b_record_count': path_b_record_count,
        'path_b_cell_count': path_b_cell_count,
        'path_c_drop_count': path_c_drop_count,
        'path_a_ratio': round(path_a_count / input_count, 4) if input_count else 0,
        'path_b_ratio': round(path_b_record_count / input_count, 4) if input_count else 0,
        'path_c_drop_ratio': round(path_c_drop_count / input_count, 4) if input_count else 0,
        'collision_candidate_count': int(collision_row['candidate_count']) if collision_row else 0,
        'collision_path_a_match_count': int(collision_row['matched_count']) if collision_row else 0,
        'collision_pending_count': int(collision_row['pending_count']) if collision_row else 0,
        'collision_drop_count': int(collision_row['dropped_count']) if collision_row else 0,
        'collision_match_rate': round(
            (int(collision_row['matched_count']) if collision_row else 0)
            / max(int(collision_row['candidate_count']) if collision_row else 0, 1),
            4,
        ) if (collision_row and int(collision_row['candidate_count']) > 0) else 0.0,
        'collision_drop_rate': round(
            (int(collision_row['dropped_count']) if collision_row else 0)
            / max(int(collision_row['candidate_count']) if collision_row else 0, 1),
            4,
        ) if (collision_row and int(collision_row['candidate_count']) > 0) else 0.0,
        'path_b_complete_cell_count': int(path_b_metrics['complete_cells']) if path_b_metrics else 0,
        'path_b_partial_cell_count': int(path_b_metrics['partial_cells']) if path_b_metrics else 0,
        'path_b_avg_gps_original_ratio': float(path_b_metrics['avg_gps_original_ratio']) if path_b_metrics else 0.0,
        'path_b_avg_signal_original_ratio': float(path_b_metrics['avg_signal_original_ratio']) if path_b_metrics else 0.0,
        'avg_independent_obs': float(path_b_metrics['avg_independent_obs']) if path_b_metrics else 0.0,
        'avg_independent_devs': float(path_b_metrics['avg_independent_devs']) if path_b_metrics else 0.0,
        'avg_observed_span_hours': float(path_b_metrics['avg_observed_span_hours']) if path_b_metrics else 0.0,
        'avg_p50_radius_m': float(path_b_metrics['avg_p50_radius_m']) if path_b_metrics else 0.0,
        'avg_p90_radius_m': float(path_b_metrics['avg_p90_radius_m']) if path_b_metrics else 0.0,
    }
    execute('DELETE FROM rb5_meta.step2_run_stats WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rb5_meta.step2_run_stats (
            run_id, batch_id, dataset_key, status, trusted_snapshot_version, started_at, finished_at,
            input_record_count, path_a_record_count, path_b_record_count, path_b_cell_count, path_c_drop_count,
            path_a_ratio, path_b_ratio, path_c_drop_ratio,
            collision_candidate_count, collision_path_a_match_count, collision_pending_count, collision_drop_count,
            collision_match_rate, collision_drop_rate,
            path_b_complete_cell_count, path_b_partial_cell_count,
            path_b_avg_gps_original_ratio, path_b_avg_signal_original_ratio,
            avg_independent_obs, avg_independent_devs, avg_observed_span_hours, avg_p50_radius_m, avg_p90_radius_m
        ) VALUES (
            %s, %s, %s, %s, %s, NOW(), NOW(),
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s
        )
        """,
        (
            stats['run_id'], stats['batch_id'], stats['dataset_key'], stats['status'], stats['trusted_snapshot_version'],
            stats['input_record_count'], stats['path_a_record_count'], stats['path_b_record_count'], stats['path_b_cell_count'], stats['path_c_drop_count'],
            stats['path_a_ratio'], stats['path_b_ratio'], stats['path_c_drop_ratio'],
            stats['collision_candidate_count'], stats['collision_path_a_match_count'], stats['collision_pending_count'], stats['collision_drop_count'],
            stats['collision_match_rate'], stats['collision_drop_rate'],
            stats['path_b_complete_cell_count'], stats['path_b_partial_cell_count'],
            stats['path_b_avg_gps_original_ratio'], stats['path_b_avg_signal_original_ratio'],
            stats['avg_independent_obs'], stats['avg_independent_devs'], stats['avg_observed_span_hours'], stats['avg_p50_radius_m'], stats['avg_p90_radius_m'],
        ),
    )
    return stats


def write_run_log(
    *,
    run_id: str,
    status: str,
    snapshot_version: str,
    result_summary: dict[str, Any],
    step_chain: str,
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
            'pipeline',
            DATASET_KEY,
            snapshot_version,
            status,
            step_chain,
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
            snapshot_version,
            status,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            DATASET_KEY,
        ),
    )


def cleanup_step2_temp_tables() -> None:
    for table_name in (
        'rb5._profile_path_a_candidates',
        'rb5._profile_path_b_cells',
        'rb5._profile_path_b_records',
        'rb5._profile_gps_day_dedup',
        'rb5._profile_core_initial_center',
        'rb5._profile_core_point_distance',
        'rb5._profile_core_mad_stats',
        'rb5._profile_core_points',
        'rb5._profile_core_gps',
        'rb5._profile_counts',
        'rb5._profile_devs',
        'rb5._profile_radius',
        'rb5._path_a_latest_library',
        'rb5._path_a_collision_cells',
        'rb5._path_a_latest_unique_cell',
        'rb5._path_a_layer1',
        'rb5._path_a_layer2',
        'rb5._path_a_layer3_all',
        'rb5._path_a_layer3',
        'rb5._profile_seed_grid',
        'rb5._profile_primary_seed',
        'rb5._profile_seed_distance',
        'rb5._profile_core_cutoff',
        'rb5._profile_centroid',
    ):
        execute(f'DROP TABLE IF EXISTS {table_name}')
