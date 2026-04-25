"""Step 3 evaluation pipeline for rb5."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY
from ..profile.pipeline import (
    create_snapshot_views,
    ensure_profile_schema,
    get_latest_batch_id,
    relation_exists,
    write_run_log,
)
from ..profile.logic import (
    flatten_antitoxin_thresholds,
    flatten_profile_thresholds,
    load_antitoxin_params,
    load_profile_params,
)

CANDIDATE_PRUNE_BATCHES = 45


def _disable_autovacuum(table_name: str) -> None:
    execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false)")


def run_step3_pipeline(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_batch_id: int,
    previous_snapshot_version: str,
    thresholds: dict[str, float],
    antitoxin_thresholds: dict[str, float],
) -> dict[str, Any]:
    _ensure_candidate_pool()
    build_current_cell_snapshot(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_batch_id=previous_batch_id,
        previous_snapshot_version=previous_snapshot_version,
        thresholds=thresholds,
    )
    cleanup_stats = _update_candidate_pool(batch_id=batch_id)
    build_current_bs_snapshot(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_snapshot_version=previous_snapshot_version,
        thresholds=thresholds,
        antitoxin_thresholds=antitoxin_thresholds,
    )
    build_current_lac_snapshot(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_snapshot_version=previous_snapshot_version,
        thresholds=thresholds,
    )
    build_final_snapshot_views(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_batch_id=previous_batch_id,
        previous_snapshot_version=previous_snapshot_version,
        thresholds=thresholds,
        antitoxin_thresholds=antitoxin_thresholds,
    )
    write_snapshot_history(run_id=run_id, batch_id=batch_id)
    build_snapshot_diffs(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_batch_id=previous_batch_id,
        previous_snapshot_version=previous_snapshot_version,
    )
    stats = write_step3_run_stats(
        run_id=run_id,
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        previous_snapshot_version=previous_snapshot_version,
        waiting_pruned_count=cleanup_stats['waiting_pruned_count'],
        dormant_marked_count=cleanup_stats['dormant_marked_count'],
    )
    cleanup_step3_temp_tables()
    create_snapshot_views()
    return stats


def build_final_snapshot_views(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_batch_id: int,
    previous_snapshot_version: str,
    thresholds: dict[str, float],
    antitoxin_thresholds: dict[str, float],
) -> None:
    """Finalize current snapshot = current candidate eval + published-domain carry-forward.

    Step 3 only re-evaluates the candidate domain. Already published objects are
    shown in the frozen snapshot as inherited rows from the previous published
    version so downstream pages and diffs see a complete batch view.
    """
    prev_cell_filter = f'WHERE prev.batch_id = {previous_batch_id}' if previous_batch_id else 'WHERE false'
    if previous_batch_id and relation_exists('rb5.trusted_cell_library'):
        carry_forward_sql = f"""
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            prev.operator_code,
            prev.operator_cn,
            prev.lac,
            prev.bs_id,
            prev.cell_id,
            prev.tech_norm,
            prev.lifecycle_state,
            prev.is_registered,
            prev.anchor_eligible,
            prev.baseline_eligible,
            prev.is_collision_id,
            prev.center_lon,
            prev.center_lat,
            prev.p50_radius_m,
            prev.p90_radius_m,
            prev.position_grade,
            prev.gps_confidence,
            prev.signal_confidence,
            prev.independent_obs,
            prev.distinct_dev_id,
            prev.gps_valid_count,
            prev.active_days,
            prev.observed_span_hours,
            prev.rsrp_avg,
            prev.rsrq_avg,
            prev.sinr_avg
        FROM rb5.trusted_snapshot_cell prev
        JOIN rb5.trusted_cell_library pub
          ON pub.batch_id = {previous_batch_id}
         AND pub.operator_code = prev.operator_code
         AND pub.lac = prev.lac
         AND pub.cell_id = prev.cell_id
         AND pub.tech_norm IS NOT DISTINCT FROM prev.tech_norm
        LEFT JOIN rb5._snapshot_current_cell curr
          ON curr.operator_code = prev.operator_code
         AND curr.lac = prev.lac
         AND curr.cell_id = prev.cell_id
         AND curr.tech_norm IS NOT DISTINCT FROM prev.tech_norm
        {prev_cell_filter}
          AND curr.cell_id IS NULL
        """
    else:
        carry_forward_sql = """
        SELECT
            NULL::int AS batch_id,
            NULL::text AS snapshot_version,
            NULL::text AS snapshot_version_prev,
            NULL::text AS dataset_key,
            NULL::text AS run_id,
            NULL::timestamptz AS created_at,
            NULL::text AS operator_code,
            NULL::text AS operator_cn,
            NULL::bigint AS lac,
            NULL::bigint AS bs_id,
            NULL::bigint AS cell_id,
            NULL::text AS tech_norm,
            NULL::text AS lifecycle_state,
            NULL::boolean AS is_registered,
            NULL::boolean AS anchor_eligible,
            NULL::boolean AS baseline_eligible,
            NULL::boolean AS is_collision_id,
            NULL::double precision AS center_lon,
            NULL::double precision AS center_lat,
            NULL::double precision AS p50_radius_m,
            NULL::double precision AS p90_radius_m,
            NULL::text AS position_grade,
            NULL::text AS gps_confidence,
            NULL::text AS signal_confidence,
            NULL::bigint AS independent_obs,
            NULL::bigint AS distinct_dev_id,
            NULL::bigint AS gps_valid_count,
            NULL::bigint AS active_days,
            NULL::double precision AS observed_span_hours,
            NULL::double precision AS rsrp_avg,
            NULL::double precision AS rsrq_avg,
            NULL::double precision AS sinr_avg
        WHERE false
        """
    execute('DROP TABLE IF EXISTS rb5._snapshot_final_cell')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_final_cell AS
        SELECT * FROM rb5._snapshot_current_cell
        UNION ALL
        {carry_forward_sql}
        """
    )
    _disable_autovacuum('rb5._snapshot_final_cell')

    execute('DROP TABLE IF EXISTS rb5._snapshot_final_bs_center')
    execute('DROP TABLE IF EXISTS rb5._snapshot_final_bs')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._snapshot_final_bs_center AS
        SELECT
            operator_code,
            lac,
            bs_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS center_lat
        FROM rb5._snapshot_final_cell
        WHERE center_lon IS NOT NULL AND center_lat IS NOT NULL
        GROUP BY operator_code, lac, bs_id
        """
    )
    _disable_autovacuum('rb5._snapshot_final_bs_center')

    execute('DROP TABLE IF EXISTS rb5._snapshot_final_bs_dist')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._snapshot_final_bs_dist AS
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY SQRT(POWER((c.center_lon - b.center_lon) * 85300, 2) + POWER((c.center_lat - b.center_lat) * 111000, 2))
            ) AS gps_p50_dist_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (
                ORDER BY SQRT(POWER((c.center_lon - b.center_lon) * 85300, 2) + POWER((c.center_lat - b.center_lat) * 111000, 2))
            ) AS gps_p90_dist_m
        FROM rb5._snapshot_final_cell c
        JOIN rb5._snapshot_final_bs_center b
          ON b.operator_code = c.operator_code
         AND b.lac = c.lac
         AND b.bs_id = c.bs_id
        WHERE c.center_lon IS NOT NULL AND c.center_lat IS NOT NULL
        GROUP BY c.operator_code, c.lac, c.bs_id
        """
    )
    _disable_autovacuum('rb5._snapshot_final_bs_dist')

    execute('DROP TABLE IF EXISTS rb5._snapshot_final_bs')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_final_bs AS
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            c.operator_code,
            MAX(c.operator_cn) AS operator_cn,
            c.lac,
            c.bs_id,
            CASE
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'qualified'
                WHEN COUNT(*) FILTER (WHERE c.gps_valid_count > 0) >= {thresholds['bs_observing_min_cells_with_gps']} THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            TRUE AS is_registered,
            BOOL_OR(c.anchor_eligible) AS anchor_eligible,
            BOOL_OR(c.baseline_eligible) AS baseline_eligible,
            COUNT(*) AS cell_count,
            COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) AS qualified_cell_count,
            COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') AS excellent_cell_count,
            COUNT(*) FILTER (WHERE c.gps_valid_count > 0) AS cells_with_gps,
            b.center_lon,
            b.center_lat,
            d.gps_p50_dist_m,
            d.gps_p90_dist_m,
            CASE
                WHEN COALESCE(d.gps_p90_dist_m, 0) > {antitoxin_thresholds['bs_max_cell_to_bs_distance_m']} THEN 'large_spread'
                ELSE 'normal_spread'
            END AS classification,
            CASE
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'good'
                WHEN COUNT(*) FILTER (WHERE c.gps_valid_count > 0) >= {thresholds['bs_observing_min_cells_with_gps']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade
        FROM rb5._snapshot_final_cell c
        LEFT JOIN rb5._snapshot_final_bs_center b
          ON b.operator_code = c.operator_code AND b.lac = c.lac AND b.bs_id = c.bs_id
        LEFT JOIN rb5._snapshot_final_bs_dist d
          ON d.operator_code = c.operator_code AND d.lac = c.lac AND d.bs_id = c.bs_id
        GROUP BY c.operator_code, c.lac, c.bs_id, b.center_lon, b.center_lat, d.gps_p50_dist_m, d.gps_p90_dist_m
        """
    )
    _disable_autovacuum('rb5._snapshot_final_bs')

    execute('DROP TABLE IF EXISTS rb5._snapshot_final_lac')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_final_lac AS
        WITH lac_center AS (
            SELECT
                operator_code,
                lac,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS center_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS center_lat,
                ((MAX(center_lon) - MIN(center_lon)) * 85300) * ((MAX(center_lat) - MIN(center_lat)) * 111000) / 1000000.0 AS area_km2
            FROM rb5._snapshot_final_bs
            WHERE center_lon IS NOT NULL AND center_lat IS NOT NULL
            GROUP BY operator_code, lac
        )
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            b.operator_code,
            MAX(b.operator_cn) AS operator_cn,
            b.lac,
            CASE
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_excellent_min_excellent_bs']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_qualified_min_excellent_bs']} THEN 'qualified'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') >= {thresholds['lac_observing_min_non_waiting_bs']} THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            TRUE AS is_registered,
            BOOL_OR(b.anchor_eligible) AS anchor_eligible,
            BOOL_OR(b.baseline_eligible) AS baseline_eligible,
            COUNT(*) AS bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') AS excellent_bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state IN ('qualified', 'excellent')) AS qualified_bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') AS non_waiting_bs_count,
            COALESCE(SUM(b.cell_count), 0) AS cell_count,
            c.center_lon,
            c.center_lat,
            COALESCE(c.area_km2, 0) AS area_km2,
            COALESCE(COUNT(*) FILTER (WHERE b.classification = 'large_spread')::double precision / NULLIF(COUNT(*), 0), 0) AS anomaly_bs_ratio,
            CASE
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_excellent_min_excellent_bs']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_qualified_min_excellent_bs']} THEN 'good'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') >= {thresholds['lac_observing_min_non_waiting_bs']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade
        FROM rb5._snapshot_final_bs b
        LEFT JOIN lac_center c
          ON c.operator_code = b.operator_code AND c.lac = b.lac
        GROUP BY b.operator_code, b.lac, c.center_lon, c.center_lat, c.area_km2
        """
    )
    _disable_autovacuum('rb5._snapshot_final_lac')


def build_current_cell_snapshot(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_batch_id: int,
    previous_snapshot_version: str,
    thresholds: dict[str, float],
) -> None:
    """Evaluate ALL candidates: current batch profile_base + historical candidate_pool.

    Snapshot = this round's evaluation result only (no carry-forward from published library).
    """
    execute('DROP TABLE IF EXISTS rb5._candidate_eval_input')
    execute('DROP TABLE IF EXISTS rb5._snapshot_current_cell')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._candidate_eval_input AS
        WITH current_profile AS (
            SELECT DISTINCT ON (operator_code, lac, cell_id, tech_norm)
                operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                independent_obs, independent_devs, independent_days, record_count,
                first_obs_at, last_obs_at, observed_span_hours, active_days, center_lon, center_lat,
                p50_radius_m, p90_radius_m, rsrp_avg, rsrq_avg, sinr_avg,
                gps_valid_count, gps_original_count, signal_original_count,
                gps_original_ratio, gps_valid_ratio, signal_original_ratio
            FROM rb5.profile_base
            WHERE run_id = %s
            ORDER BY operator_code, lac, cell_id, tech_norm, independent_obs DESC NULLS LAST, record_count DESC NULLS LAST
        ),
        historical_pool AS (
            SELECT
                operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                independent_obs, independent_devs, independent_days, record_count,
                first_obs_at, last_obs_at, observed_span_hours, active_days, center_lon, center_lat,
                p50_radius_m, p90_radius_m, rsrp_avg, rsrq_avg, sinr_avg,
                gps_valid_count, gps_original_count, signal_original_count,
                gps_original_ratio, gps_valid_ratio, signal_original_ratio
            FROM rb5.candidate_cell_pool
        )
        SELECT
            COALESCE(c.operator_code, h.operator_code) AS operator_code,
            COALESCE(NULLIF(c.operator_cn, '未知'), c.operator_cn, NULLIF(h.operator_cn, '未知'), h.operator_cn, '未知') AS operator_cn,
            COALESCE(c.lac, h.lac) AS lac,
            COALESCE(c.bs_id, h.bs_id) AS bs_id,
            COALESCE(c.cell_id, h.cell_id) AS cell_id,
            COALESCE(c.tech_norm, h.tech_norm) AS tech_norm,
            COALESCE(c.independent_obs, 0) + COALESCE(h.independent_obs, 0) AS independent_obs,
            CASE
                WHEN c.cell_id IS NOT NULL AND h.cell_id IS NOT NULL THEN
                    GREATEST(COALESCE(c.independent_devs, 0), COALESCE(h.independent_devs, 0))
                WHEN c.cell_id IS NOT NULL THEN COALESCE(c.independent_devs, 0)
                ELSE COALESCE(h.independent_devs, 0)
            END AS independent_devs,
            COALESCE(c.independent_days, 0) + COALESCE(h.independent_days, 0) AS independent_days,
            COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0) AS record_count,
            COALESCE(LEAST(c.first_obs_at, h.first_obs_at), c.first_obs_at, h.first_obs_at) AS first_obs_at,
            COALESCE(GREATEST(c.last_obs_at, h.last_obs_at), c.last_obs_at, h.last_obs_at) AS last_obs_at,
            CASE
                WHEN COALESCE(LEAST(c.first_obs_at, h.first_obs_at), c.first_obs_at, h.first_obs_at) IS NULL
                  OR COALESCE(GREATEST(c.last_obs_at, h.last_obs_at), c.last_obs_at, h.last_obs_at) IS NULL
                    THEN NULL::double precision
                ELSE EXTRACT(
                    EPOCH FROM (
                        COALESCE(GREATEST(c.last_obs_at, h.last_obs_at), c.last_obs_at, h.last_obs_at)
                        - COALESCE(LEAST(c.first_obs_at, h.first_obs_at), c.first_obs_at, h.first_obs_at)
                    )
                ) / 3600.0
            END AS observed_span_hours,
            COALESCE(c.active_days, 0) + COALESCE(h.active_days, 0) AS active_days,
            CASE
                WHEN COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0) > 0
                     AND c.center_lon IS NOT NULL
                     AND h.center_lon IS NOT NULL
                    THEN (
                        c.center_lon * COALESCE(c.gps_valid_count, 0)
                        + h.center_lon * COALESCE(h.gps_valid_count, 0)
                    ) / NULLIF(COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0), 0)
                ELSE COALESCE(c.center_lon, h.center_lon)
            END AS center_lon,
            CASE
                WHEN COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0) > 0
                     AND c.center_lat IS NOT NULL
                     AND h.center_lat IS NOT NULL
                    THEN (
                        c.center_lat * COALESCE(c.gps_valid_count, 0)
                        + h.center_lat * COALESCE(h.gps_valid_count, 0)
                    ) / NULLIF(COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0), 0)
                ELSE COALESCE(c.center_lat, h.center_lat)
            END AS center_lat,
            CASE
                WHEN c.p50_radius_m IS NULL THEN h.p50_radius_m
                WHEN h.p50_radius_m IS NULL THEN c.p50_radius_m
                WHEN COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0) = 0
                    THEN COALESCE(c.p50_radius_m, h.p50_radius_m)
                ELSE (
                    c.p50_radius_m * COALESCE(c.gps_valid_count, 0)
                    + h.p50_radius_m * COALESCE(h.gps_valid_count, 0)
                ) / NULLIF(COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0), 0)
            END AS p50_radius_m,
            CASE
                WHEN c.p90_radius_m IS NULL THEN h.p90_radius_m
                WHEN h.p90_radius_m IS NULL THEN c.p90_radius_m
                WHEN COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0) = 0
                    THEN COALESCE(c.p90_radius_m, h.p90_radius_m)
                ELSE (
                    c.p90_radius_m * COALESCE(c.gps_valid_count, 0)
                    + h.p90_radius_m * COALESCE(h.gps_valid_count, 0)
                ) / NULLIF(COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0), 0)
            END AS p90_radius_m,
            CASE
                WHEN COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0) > 0
                     AND c.rsrp_avg IS NOT NULL
                     AND h.rsrp_avg IS NOT NULL
                    THEN (
                        c.rsrp_avg * COALESCE(c.signal_original_count, 0)
                        + h.rsrp_avg * COALESCE(h.signal_original_count, 0)
                    ) / NULLIF(COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0), 0)
                ELSE COALESCE(c.rsrp_avg, h.rsrp_avg)
            END AS rsrp_avg,
            CASE
                WHEN COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0) > 0
                     AND c.rsrq_avg IS NOT NULL
                     AND h.rsrq_avg IS NOT NULL
                    THEN (
                        c.rsrq_avg * COALESCE(c.signal_original_count, 0)
                        + h.rsrq_avg * COALESCE(h.signal_original_count, 0)
                    ) / NULLIF(COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0), 0)
                ELSE COALESCE(c.rsrq_avg, h.rsrq_avg)
            END AS rsrq_avg,
            CASE
                WHEN COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0) > 0
                     AND c.sinr_avg IS NOT NULL
                     AND h.sinr_avg IS NOT NULL
                    THEN (
                        c.sinr_avg * COALESCE(c.signal_original_count, 0)
                        + h.sinr_avg * COALESCE(h.signal_original_count, 0)
                    ) / NULLIF(COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0), 0)
                ELSE COALESCE(c.sinr_avg, h.sinr_avg)
            END AS sinr_avg,
            COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0) AS gps_valid_count,
            COALESCE(c.gps_original_count, 0) + COALESCE(h.gps_original_count, 0) AS gps_original_count,
            COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0) AS signal_original_count,
            CASE
                WHEN COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0) = 0 THEN 0::double precision
                ELSE (COALESCE(c.gps_original_count, 0) + COALESCE(h.gps_original_count, 0))::double precision
                    / NULLIF(COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0), 0)
            END AS gps_original_ratio,
            CASE
                WHEN COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0) = 0 THEN 0::double precision
                ELSE (COALESCE(c.gps_valid_count, 0) + COALESCE(h.gps_valid_count, 0))::double precision
                    / NULLIF(COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0), 0)
            END AS gps_valid_ratio,
            CASE
                WHEN COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0) = 0 THEN 0::double precision
                ELSE (COALESCE(c.signal_original_count, 0) + COALESCE(h.signal_original_count, 0))::double precision
                    / NULLIF(COALESCE(c.record_count, 0) + COALESCE(h.record_count, 0), 0)
            END AS signal_original_ratio
        FROM current_profile c
        FULL OUTER JOIN historical_pool h
          ON h.operator_code = c.operator_code
         AND h.lac = c.lac
         AND h.cell_id = c.cell_id
         AND h.tech_norm IS NOT DISTINCT FROM c.tech_norm
        WHERE COALESCE(c.cell_id, h.cell_id) IS NOT NULL
        """,
        (run_id,),
    )
    _disable_autovacuum('rb5._candidate_eval_input')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_current_cell AS
        WITH collision_flags AS (
            {f'SELECT DISTINCT cell_id, TRUE AS is_collision_id FROM rb5.collision_id_list WHERE batch_id = {previous_batch_id} AND cell_id IS NOT NULL' if relation_exists('rb5.collision_id_list') and previous_batch_id else 'SELECT NULL::bigint AS cell_id, TRUE AS is_collision_id WHERE false'}
        )
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            p.operator_code,
            p.operator_cn,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            CASE
                WHEN p.independent_obs >= {thresholds['excellent_min_obs']} THEN 'excellent'
                WHEN p.independent_obs >= {thresholds['qualified_min_obs']} THEN 'qualified'
                WHEN p.independent_obs >= {thresholds['waiting_min_obs']} THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            TRUE AS is_registered,
            (
                p.gps_valid_count >= {thresholds['anchorable_min_gps_valid_count']}
                AND p.independent_devs >= {thresholds['anchorable_min_distinct_devices']}
                AND COALESCE(p.p90_radius_m, 1e9) < {thresholds['anchorable_max_p90']}
                AND COALESCE(p.observed_span_hours, 0) >= {thresholds['anchorable_min_span_hours']}
                AND COALESCE(cf.is_collision_id, FALSE) = FALSE
            ) AS anchor_eligible,
            FALSE AS baseline_eligible,
            COALESCE(cf.is_collision_id, FALSE) AS is_collision_id,
            p.center_lon,
            p.center_lat,
            p.p50_radius_m,
            p.p90_radius_m,
            CASE
                WHEN p.independent_obs >= {thresholds['excellent_min_obs']} THEN 'excellent'
                WHEN p.independent_obs >= {thresholds['qualified_min_obs']} THEN 'good'
                WHEN p.independent_obs >= {thresholds['waiting_min_obs']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade,
            CASE
                WHEN p.gps_valid_count >= {thresholds['gps_confidence_high_min_gps']} AND p.independent_devs >= {thresholds['gps_confidence_high_min_devs']} THEN 'high'
                WHEN p.gps_valid_count >= {thresholds['gps_confidence_medium_min_gps']} AND p.independent_devs >= {thresholds['gps_confidence_medium_min_devs']} THEN 'medium'
                WHEN p.gps_valid_count >= {thresholds['gps_confidence_low_min_gps']} THEN 'low'
                ELSE 'none'
            END AS gps_confidence,
            CASE
                WHEN p.signal_original_count >= {thresholds['signal_confidence_high_min_signal']} THEN 'high'
                WHEN p.signal_original_count >= {thresholds['signal_confidence_medium_min_signal']} THEN 'medium'
                WHEN p.signal_original_count >= {thresholds['signal_confidence_low_min_signal']} THEN 'low'
                ELSE 'none'
            END AS signal_confidence,
            p.independent_obs,
            p.independent_devs AS distinct_dev_id,
            p.gps_valid_count,
            p.active_days,
            p.observed_span_hours,
            p.rsrp_avg,
            p.rsrq_avg,
            p.sinr_avg
        FROM rb5._candidate_eval_input p
        LEFT JOIN collision_flags cf ON cf.cell_id = p.cell_id
        """,
    )
    _disable_autovacuum('rb5._snapshot_current_cell')
    execute(
        """
        UPDATE rb5._snapshot_current_cell s
        SET baseline_eligible = (s.anchor_eligible AND s.lifecycle_state = 'excellent')
        """
    )


def build_current_bs_snapshot(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_snapshot_version: str,
    thresholds: dict[str, float],
    antitoxin_thresholds: dict[str, float],
) -> None:
    execute('DROP TABLE IF EXISTS rb5._snapshot_bs_center')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._snapshot_bs_center AS
        SELECT
            operator_code,
            lac,
            bs_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS center_lat
        FROM rb5._snapshot_current_cell
        WHERE center_lon IS NOT NULL AND center_lat IS NOT NULL
        GROUP BY operator_code, lac, bs_id
        """
    )
    _disable_autovacuum('rb5._snapshot_bs_center')
    execute('DROP TABLE IF EXISTS rb5._snapshot_bs_dist')
    execute(
        """
        CREATE UNLOGGED TABLE rb5._snapshot_bs_dist AS
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY SQRT(POWER((c.center_lon - b.center_lon) * 85300, 2) + POWER((c.center_lat - b.center_lat) * 111000, 2))
            ) AS gps_p50_dist_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (
                ORDER BY SQRT(POWER((c.center_lon - b.center_lon) * 85300, 2) + POWER((c.center_lat - b.center_lat) * 111000, 2))
            ) AS gps_p90_dist_m
        FROM rb5._snapshot_current_cell c
        JOIN rb5._snapshot_bs_center b
          ON b.operator_code = c.operator_code
         AND b.lac = c.lac
         AND b.bs_id = c.bs_id
        WHERE c.center_lon IS NOT NULL AND c.center_lat IS NOT NULL
        GROUP BY c.operator_code, c.lac, c.bs_id
        """
    )
    _disable_autovacuum('rb5._snapshot_bs_dist')
    execute('DROP TABLE IF EXISTS rb5._snapshot_current_bs')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_current_bs AS
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            c.operator_code,
            MAX(c.operator_cn) AS operator_cn,
            c.lac,
            c.bs_id,
            CASE
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'qualified'
                WHEN COUNT(*) FILTER (WHERE c.gps_valid_count > 0) >= {thresholds['bs_observing_min_cells_with_gps']} THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            TRUE AS is_registered,
            BOOL_OR(c.anchor_eligible) AS anchor_eligible,
            BOOL_OR(c.baseline_eligible) AS baseline_eligible,
            COUNT(*) AS cell_count,
            COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) AS qualified_cell_count,
            COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') AS excellent_cell_count,
            COUNT(*) FILTER (WHERE c.gps_valid_count > 0) AS cells_with_gps,
            b.center_lon,
            b.center_lat,
            d.gps_p50_dist_m,
            d.gps_p90_dist_m,
            CASE
                WHEN COALESCE(d.gps_p90_dist_m, 0) > {antitoxin_thresholds['bs_max_cell_to_bs_distance_m']} THEN 'large_spread'
                ELSE 'normal_spread'
            END AS classification,
            CASE
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state = 'excellent') >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE c.lifecycle_state IN ('qualified', 'excellent')) >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'good'
                WHEN COUNT(*) FILTER (WHERE c.gps_valid_count > 0) >= {thresholds['bs_observing_min_cells_with_gps']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade
        FROM rb5._snapshot_current_cell c
        LEFT JOIN rb5._snapshot_bs_center b
          ON b.operator_code = c.operator_code AND b.lac = c.lac AND b.bs_id = c.bs_id
        LEFT JOIN rb5._snapshot_bs_dist d
          ON d.operator_code = c.operator_code AND d.lac = c.lac AND d.bs_id = c.bs_id
        GROUP BY c.operator_code, c.lac, c.bs_id, b.center_lon, b.center_lat, d.gps_p50_dist_m, d.gps_p90_dist_m
        """
    )
    _disable_autovacuum('rb5._snapshot_current_bs')


def build_current_lac_snapshot(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_snapshot_version: str,
    thresholds: dict[str, float],
) -> None:
    execute('DROP TABLE IF EXISTS rb5._snapshot_current_lac')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5._snapshot_current_lac AS
        WITH lac_center AS (
            SELECT
                operator_code,
                lac,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS center_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS center_lat,
                ((MAX(center_lon) - MIN(center_lon)) * 85300) * ((MAX(center_lat) - MIN(center_lat)) * 111000) / 1000000.0 AS area_km2
            FROM rb5._snapshot_current_bs
            WHERE center_lon IS NOT NULL AND center_lat IS NOT NULL
            GROUP BY operator_code, lac
        )
        SELECT
            {batch_id}::int AS batch_id,
            '{snapshot_version}'::text AS snapshot_version,
            '{previous_snapshot_version}'::text AS snapshot_version_prev,
            '{DATASET_KEY}'::text AS dataset_key,
            '{run_id}'::text AS run_id,
            NOW() AS created_at,
            b.operator_code,
            MAX(b.operator_cn) AS operator_cn,
            b.lac,
            CASE
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_excellent_min_excellent_bs']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_qualified_min_excellent_bs']} THEN 'qualified'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') >= {thresholds['lac_observing_min_non_waiting_bs']} THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            TRUE AS is_registered,
            BOOL_OR(b.anchor_eligible) AS anchor_eligible,
            BOOL_OR(b.baseline_eligible) AS baseline_eligible,
            COUNT(*) AS bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') AS excellent_bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state IN ('qualified', 'excellent')) AS qualified_bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') AS non_waiting_bs_count,
            COALESCE(SUM(b.cell_count), 0) AS cell_count,
            c.center_lon,
            c.center_lat,
            COALESCE(c.area_km2, 0) AS area_km2,
            COALESCE(COUNT(*) FILTER (WHERE b.classification = 'large_spread')::double precision / NULLIF(COUNT(*), 0), 0) AS anomaly_bs_ratio,
            CASE
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_excellent_min_excellent_bs']} THEN 'excellent'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'excellent') >= {thresholds['lac_qualified_min_excellent_bs']} THEN 'good'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state <> 'waiting') >= {thresholds['lac_observing_min_non_waiting_bs']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade
        FROM rb5._snapshot_current_bs b
        LEFT JOIN lac_center c
          ON c.operator_code = b.operator_code AND c.lac = b.lac
        GROUP BY b.operator_code, b.lac, c.center_lon, c.center_lat, c.area_km2
        """
    )
    _disable_autovacuum('rb5._snapshot_current_lac')


def write_snapshot_history(*, run_id: str, batch_id: int) -> None:
    execute('DELETE FROM rb5.trusted_snapshot_cell WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rb5.trusted_snapshot_bs WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rb5.trusted_snapshot_lac WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rb5.trusted_snapshot_cell (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, is_registered, anchor_eligible, baseline_eligible, is_collision_id,
            center_lon, center_lat, p50_radius_m, p90_radius_m,
            position_grade, gps_confidence, signal_confidence,
            independent_obs, distinct_dev_id, gps_valid_count, active_days, observed_span_hours,
            rsrp_avg, rsrq_avg, sinr_avg
        )
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, is_registered, anchor_eligible, baseline_eligible, is_collision_id,
            center_lon, center_lat, p50_radius_m, p90_radius_m,
            position_grade, gps_confidence, signal_confidence,
            independent_obs, distinct_dev_id, gps_valid_count, active_days, observed_span_hours,
            rsrp_avg, rsrq_avg, sinr_avg
        FROM rb5._snapshot_final_cell
        """
    )
    execute(
        """
        INSERT INTO rb5.trusted_snapshot_bs (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            is_registered, anchor_eligible, baseline_eligible,
            cell_count, qualified_cell_count, excellent_cell_count, cells_with_gps,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade
        )
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            is_registered, anchor_eligible, baseline_eligible,
            cell_count, qualified_cell_count, excellent_cell_count, cells_with_gps,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade
        FROM rb5._snapshot_final_bs
        """
    )
    execute(
        """
        INSERT INTO rb5.trusted_snapshot_lac (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, lifecycle_state,
            is_registered, anchor_eligible, baseline_eligible,
            bs_count, excellent_bs_count, qualified_bs_count, non_waiting_bs_count, cell_count,
            center_lon, center_lat, area_km2, anomaly_bs_ratio, position_grade
        )
        SELECT
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, operator_cn, lac, lifecycle_state,
            is_registered, anchor_eligible, baseline_eligible,
            bs_count, excellent_bs_count, qualified_bs_count, non_waiting_bs_count, cell_count,
            center_lon, center_lat, area_km2, anomaly_bs_ratio, position_grade
        FROM rb5._snapshot_final_lac
        """
    )


def build_snapshot_diffs(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_batch_id: int,
    previous_snapshot_version: str,
) -> None:
    execute('DELETE FROM rb5.snapshot_diff_cell WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rb5.snapshot_diff_bs WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rb5.snapshot_diff_lac WHERE batch_id = %s', (batch_id,))

    prev_cell_filter = f'WHERE batch_id = {previous_batch_id}' if previous_batch_id else 'WHERE false'
    execute(
        f"""
        INSERT INTO rb5.snapshot_diff_cell (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, lac, bs_id, cell_id,
            tech_norm,
            diff_kind, prev_lifecycle_state, curr_lifecycle_state,
            prev_anchor_eligible, curr_anchor_eligible,
            prev_baseline_eligible, curr_baseline_eligible,
            centroid_shift_m, prev_p90_radius_m, curr_p90_radius_m
        )
        WITH prev AS (
            SELECT * FROM rb5.trusted_snapshot_cell {prev_cell_filter}
        ),
        curr AS (
            SELECT * FROM rb5._snapshot_final_cell
        )
        SELECT
            {batch_id}::int,
            '{snapshot_version}'::text,
            '{previous_snapshot_version}'::text,
            '{DATASET_KEY}'::text,
            '{run_id}'::text,
            NOW(),
            COALESCE(curr.operator_code, prev.operator_code) AS operator_code,
            COALESCE(curr.lac, prev.lac) AS lac,
            COALESCE(curr.bs_id, prev.bs_id) AS bs_id,
            COALESCE(curr.cell_id, prev.cell_id) AS cell_id,
            COALESCE(curr.tech_norm, prev.tech_norm) AS tech_norm,
            CASE
                WHEN prev.cell_id IS NULL THEN 'new'
                WHEN curr.cell_id IS NULL THEN 'removed'
                WHEN CASE
                        WHEN curr.lifecycle_state = 'waiting' THEN 0
                        WHEN curr.lifecycle_state = 'observing' THEN 1
                        WHEN curr.lifecycle_state = 'qualified' THEN 2
                        WHEN curr.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END
                   > CASE
                        WHEN prev.lifecycle_state = 'waiting' THEN 0
                        WHEN prev.lifecycle_state = 'observing' THEN 1
                        WHEN prev.lifecycle_state = 'qualified' THEN 2
                        WHEN prev.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END THEN 'promoted'
                WHEN CASE
                        WHEN curr.lifecycle_state = 'waiting' THEN 0
                        WHEN curr.lifecycle_state = 'observing' THEN 1
                        WHEN curr.lifecycle_state = 'qualified' THEN 2
                        WHEN curr.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END
                   < CASE
                        WHEN prev.lifecycle_state = 'waiting' THEN 0
                        WHEN prev.lifecycle_state = 'observing' THEN 1
                        WHEN prev.lifecycle_state = 'qualified' THEN 2
                        WHEN prev.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END THEN 'demoted'
                WHEN COALESCE(curr.anchor_eligible, FALSE) <> COALESCE(prev.anchor_eligible, FALSE)
                  OR COALESCE(curr.baseline_eligible, FALSE) <> COALESCE(prev.baseline_eligible, FALSE) THEN 'eligibility_changed'
                WHEN SQRT(
                    POWER((COALESCE(curr.center_lon, prev.center_lon) - prev.center_lon) * 85300, 2)
                  + POWER((COALESCE(curr.center_lat, prev.center_lat) - prev.center_lat) * 111000, 2)
                ) >= 50 THEN 'geometry_changed'
                ELSE 'unchanged'
            END AS diff_kind,
            prev.lifecycle_state,
            curr.lifecycle_state,
            prev.anchor_eligible,
            curr.anchor_eligible,
            prev.baseline_eligible,
            curr.baseline_eligible,
            CASE
                WHEN prev.center_lon IS NULL OR prev.center_lat IS NULL OR curr.center_lon IS NULL OR curr.center_lat IS NULL THEN 0
                ELSE SQRT(POWER((curr.center_lon - prev.center_lon) * 85300, 2) + POWER((curr.center_lat - prev.center_lat) * 111000, 2))
            END AS centroid_shift_m,
            prev.p90_radius_m,
            curr.p90_radius_m
        FROM curr
        FULL OUTER JOIN prev
          ON prev.operator_code = curr.operator_code
         AND prev.lac = curr.lac
         AND prev.cell_id = curr.cell_id
         AND prev.tech_norm IS NOT DISTINCT FROM curr.tech_norm
        """
    )

    prev_bs_filter = f'WHERE batch_id = {previous_batch_id}' if previous_batch_id else 'WHERE false'
    execute(
        f"""
        INSERT INTO rb5.snapshot_diff_bs (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
            operator_code, lac, bs_id, diff_kind,
            prev_lifecycle_state, curr_lifecycle_state,
            prev_cell_count, curr_cell_count, centroid_shift_m
        )
        WITH prev AS (
            SELECT * FROM rb5.trusted_snapshot_bs {prev_bs_filter}
        ),
        curr AS (
            SELECT * FROM rb5._snapshot_final_bs
        )
        SELECT
            {batch_id}::int,
            '{snapshot_version}'::text,
            '{previous_snapshot_version}'::text,
            '{DATASET_KEY}'::text,
            '{run_id}'::text,
            NOW(),
            COALESCE(curr.operator_code, prev.operator_code),
            COALESCE(curr.lac, prev.lac),
            COALESCE(curr.bs_id, prev.bs_id),
            CASE
                WHEN prev.bs_id IS NULL THEN 'new'
                WHEN curr.bs_id IS NULL THEN 'removed'
                WHEN CASE
                        WHEN curr.lifecycle_state = 'waiting' THEN 0
                        WHEN curr.lifecycle_state = 'observing' THEN 1
                        WHEN curr.lifecycle_state = 'qualified' THEN 2
                        WHEN curr.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END
                   > CASE
                        WHEN prev.lifecycle_state = 'waiting' THEN 0
                        WHEN prev.lifecycle_state = 'observing' THEN 1
                        WHEN prev.lifecycle_state = 'qualified' THEN 2
                        WHEN prev.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END THEN 'promoted'
                WHEN CASE
                        WHEN curr.lifecycle_state = 'waiting' THEN 0
                        WHEN curr.lifecycle_state = 'observing' THEN 1
                        WHEN curr.lifecycle_state = 'qualified' THEN 2
                        WHEN curr.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END
                   < CASE
                        WHEN prev.lifecycle_state = 'waiting' THEN 0
                        WHEN prev.lifecycle_state = 'observing' THEN 1
                        WHEN prev.lifecycle_state = 'qualified' THEN 2
                        WHEN prev.lifecycle_state = 'excellent' THEN 3
                        ELSE 0
                     END THEN 'demoted'
                WHEN COALESCE(curr.cell_count, 0) <> COALESCE(prev.cell_count, 0) THEN 'geometry_changed'
                ELSE 'unchanged'
            END,
            prev.lifecycle_state,
            curr.lifecycle_state,
            prev.cell_count,
            curr.cell_count,
            CASE
                WHEN prev.center_lon IS NULL OR prev.center_lat IS NULL OR curr.center_lon IS NULL OR curr.center_lat IS NULL THEN 0
                ELSE SQRT(POWER((curr.center_lon - prev.center_lon) * 85300, 2) + POWER((curr.center_lat - prev.center_lat) * 111000, 2))
            END
        FROM curr
        FULL OUTER JOIN prev
          ON prev.operator_code = curr.operator_code
         AND prev.lac = curr.lac
         AND prev.bs_id = curr.bs_id
        """
    )

    if not previous_batch_id:
        execute(
            f"""
            INSERT INTO rb5.snapshot_diff_lac (
                batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
                operator_code, lac, diff_kind,
                prev_lifecycle_state, curr_lifecycle_state,
                prev_bs_count, curr_bs_count,
                prev_area_km2, curr_area_km2
            )
            SELECT
                {batch_id}::int,
                '{snapshot_version}'::text,
                '{previous_snapshot_version}'::text,
                '{DATASET_KEY}'::text,
                '{run_id}'::text,
                NOW(),
                curr.operator_code,
                curr.lac,
                'new'::text,
                NULL::text,
                curr.lifecycle_state,
                NULL::bigint,
                curr.bs_count,
                NULL::double precision,
                curr.area_km2
            FROM rb5._snapshot_final_lac curr
            """
        )
    else:
        prev_lac_filter = f'WHERE batch_id = {previous_batch_id}'
        execute(
            f"""
            INSERT INTO rb5.snapshot_diff_lac (
                batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, created_at,
                operator_code, lac, diff_kind,
                prev_lifecycle_state, curr_lifecycle_state,
                prev_bs_count, curr_bs_count,
                prev_area_km2, curr_area_km2
            )
            WITH prev AS (
                SELECT * FROM rb5.trusted_snapshot_lac {prev_lac_filter}
            ),
            curr AS (
                SELECT * FROM rb5._snapshot_final_lac
            )
            SELECT
                {batch_id}::int,
                '{snapshot_version}'::text,
                '{previous_snapshot_version}'::text,
                '{DATASET_KEY}'::text,
                '{run_id}'::text,
                NOW(),
                COALESCE(curr.operator_code, prev.operator_code),
                COALESCE(curr.lac, prev.lac),
                CASE
                    WHEN prev.lac IS NULL THEN 'new'
                    WHEN curr.lac IS NULL THEN 'removed'
                    WHEN CASE
                            WHEN curr.lifecycle_state = 'waiting' THEN 0
                            WHEN curr.lifecycle_state = 'observing' THEN 1
                            WHEN curr.lifecycle_state = 'qualified' THEN 2
                            WHEN curr.lifecycle_state = 'excellent' THEN 3
                            ELSE 0
                         END
                       > CASE
                            WHEN prev.lifecycle_state = 'waiting' THEN 0
                            WHEN prev.lifecycle_state = 'observing' THEN 1
                            WHEN prev.lifecycle_state = 'qualified' THEN 2
                            WHEN prev.lifecycle_state = 'excellent' THEN 3
                            ELSE 0
                         END THEN 'promoted'
                    WHEN CASE
                            WHEN curr.lifecycle_state = 'waiting' THEN 0
                            WHEN curr.lifecycle_state = 'observing' THEN 1
                            WHEN curr.lifecycle_state = 'qualified' THEN 2
                            WHEN curr.lifecycle_state = 'excellent' THEN 3
                            ELSE 0
                         END
                       < CASE
                            WHEN prev.lifecycle_state = 'waiting' THEN 0
                            WHEN prev.lifecycle_state = 'observing' THEN 1
                            WHEN prev.lifecycle_state = 'qualified' THEN 2
                            WHEN prev.lifecycle_state = 'excellent' THEN 3
                            ELSE 0
                         END THEN 'demoted'
                    WHEN COALESCE(curr.bs_count, 0) <> COALESCE(prev.bs_count, 0)
                      OR ABS(COALESCE(curr.area_km2, 0) - COALESCE(prev.area_km2, 0)) >= 0.01 THEN 'geometry_changed'
                    ELSE 'unchanged'
                END,
                prev.lifecycle_state,
                curr.lifecycle_state,
                prev.bs_count,
                curr.bs_count,
                prev.area_km2,
                curr.area_km2
            FROM curr
            FULL OUTER JOIN prev
              ON prev.operator_code = curr.operator_code
             AND prev.lac = curr.lac
            """
        )


def write_step3_run_stats(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    previous_snapshot_version: str,
    waiting_pruned_count: int,
    dormant_marked_count: int,
) -> dict[str, Any]:
    profile_base_row = fetchone('SELECT COUNT(*) AS cnt FROM rb5.profile_base WHERE run_id = %s', (run_id,))
    cell_row = fetchone(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') AS waiting_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'qualified') AS qualified_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_count,
            COUNT(*) FILTER (WHERE anchor_eligible) AS anchor_count
        FROM rb5.trusted_snapshot_cell
        WHERE batch_id = %s
        """,
        (batch_id,),
    )
    bs_row = fetchone(
        """
        SELECT
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') AS waiting_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'qualified') AS qualified_count
        FROM rb5.trusted_snapshot_bs
        WHERE batch_id = %s
        """,
        (batch_id,),
    )
    lac_row = fetchone(
        """
        SELECT
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') AS waiting_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_count,
            COUNT(*) FILTER (WHERE lifecycle_state = 'qualified') AS qualified_count
        FROM rb5.trusted_snapshot_lac
        WHERE batch_id = %s
        """,
        (batch_id,),
    )
    diff_row = fetchone(
        """
        SELECT
            COUNT(*) FILTER (WHERE diff_kind = 'new') AS new_count,
            COUNT(*) FILTER (WHERE diff_kind = 'promoted') AS promoted_count,
            COUNT(*) FILTER (WHERE diff_kind = 'demoted') AS demoted_count,
            COUNT(*) FILTER (WHERE diff_kind = 'eligibility_changed') AS eligibility_changed_count,
            COUNT(*) FILTER (WHERE diff_kind = 'geometry_changed') AS geometry_changed_count,
            COUNT(*) FILTER (WHERE curr_lifecycle_state = 'qualified' AND (prev_lifecycle_state IS NULL OR prev_lifecycle_state <> 'qualified')) AS new_qualified_count,
            COUNT(*) FILTER (WHERE curr_lifecycle_state = 'excellent' AND (prev_lifecycle_state IS NULL OR prev_lifecycle_state <> 'excellent')) AS new_excellent_count
        FROM rb5.snapshot_diff_cell
        WHERE batch_id = %s
        """,
        (batch_id,),
    )

    stats = {
        'run_id': run_id,
        'dataset_key': DATASET_KEY,
        'batch_id': batch_id,
        'snapshot_version': snapshot_version,
        'trusted_snapshot_version_prev': previous_snapshot_version,
        'status': 'completed',
        'profile_base_cell_count': int(profile_base_row['cnt']) if profile_base_row else 0,
        'mode_filtered_count': 0,
        'region_filtered_count': 0,
        'gps_filtered_count': 0,
        'evaluated_cell_count': int(cell_row['total']) if cell_row else 0,
        'waiting_cell_count': int(cell_row['waiting_count']) if cell_row else 0,
        'observing_cell_count': int(cell_row['observing_count']) if cell_row else 0,
        'qualified_cell_count': int(cell_row['qualified_count']) if cell_row else 0,
        'excellent_cell_count': int(cell_row['excellent_count']) if cell_row else 0,
        'new_qualified_cell_count': int(diff_row['new_qualified_count']) if diff_row else 0,
        'new_excellent_cell_count': int(diff_row['new_excellent_count']) if diff_row else 0,
        'anchor_eligible_cell_count': int(cell_row['anchor_count']) if cell_row else 0,
        'bs_waiting_count': int(bs_row['waiting_count']) if bs_row else 0,
        'bs_observing_count': int(bs_row['observing_count']) if bs_row else 0,
        'bs_excellent_count': int(bs_row['excellent_count']) if bs_row else 0,
        'bs_qualified_count': int(bs_row['qualified_count']) if bs_row else 0,
        'lac_waiting_count': int(lac_row['waiting_count']) if lac_row else 0,
        'lac_observing_count': int(lac_row['observing_count']) if lac_row else 0,
        'lac_excellent_count': int(lac_row['excellent_count']) if lac_row else 0,
        'lac_qualified_count': int(lac_row['qualified_count']) if lac_row else 0,
        'waiting_pruned_cell_count': waiting_pruned_count,
        'dormant_marked_count': dormant_marked_count,
        'snapshot_new_count': int(diff_row['new_count']) if diff_row else 0,
        'snapshot_promoted_count': int(diff_row['promoted_count']) if diff_row else 0,
        'snapshot_demoted_count': int(diff_row['demoted_count']) if diff_row else 0,
        'snapshot_eligibility_changed_count': int(diff_row['eligibility_changed_count']) if diff_row else 0,
        'snapshot_geometry_changed_count': int(diff_row['geometry_changed_count']) if diff_row else 0,
    }
    execute('DELETE FROM rb5_meta.step3_run_stats WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rb5_meta.step3_run_stats (
            run_id, dataset_key, batch_id, snapshot_version, trusted_snapshot_version_prev, status,
            started_at, finished_at,
            profile_base_cell_count, mode_filtered_count, region_filtered_count, gps_filtered_count,
            evaluated_cell_count, waiting_cell_count, observing_cell_count, qualified_cell_count, excellent_cell_count,
            new_qualified_cell_count, new_excellent_cell_count, anchor_eligible_cell_count,
            bs_waiting_count, bs_observing_count, bs_excellent_count, bs_qualified_count,
            lac_waiting_count, lac_observing_count, lac_excellent_count, lac_qualified_count,
            waiting_pruned_cell_count, dormant_marked_count,
            snapshot_new_count, snapshot_promoted_count, snapshot_demoted_count,
            snapshot_eligibility_changed_count, snapshot_geometry_changed_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            NOW(), NOW(),
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s
        )
        """,
        (
            stats['run_id'], stats['dataset_key'], stats['batch_id'], stats['snapshot_version'], stats['trusted_snapshot_version_prev'], stats['status'],
            stats['profile_base_cell_count'], stats['mode_filtered_count'], stats['region_filtered_count'], stats['gps_filtered_count'],
            stats['evaluated_cell_count'], stats['waiting_cell_count'], stats['observing_cell_count'], stats['qualified_cell_count'], stats['excellent_cell_count'],
            stats['new_qualified_cell_count'], stats['new_excellent_cell_count'], stats['anchor_eligible_cell_count'],
            stats['bs_waiting_count'], stats['bs_observing_count'], stats['bs_excellent_count'], stats['bs_qualified_count'],
            stats['lac_waiting_count'], stats['lac_observing_count'], stats['lac_excellent_count'], stats['lac_qualified_count'],
            stats['waiting_pruned_cell_count'], stats['dormant_marked_count'],
            stats['snapshot_new_count'], stats['snapshot_promoted_count'], stats['snapshot_demoted_count'],
            stats['snapshot_eligibility_changed_count'], stats['snapshot_geometry_changed_count'],
        ),
    )
    return stats


def cleanup_step3_temp_tables() -> None:
    for table_name in (
        'rb5._candidate_eval_input',
        'rb5._snapshot_current_cell',
        'rb5._snapshot_bs_center',
        'rb5._snapshot_bs_dist',
        'rb5._snapshot_current_bs',
        'rb5._snapshot_current_lac',
        'rb5._snapshot_final_cell',
        'rb5._snapshot_final_bs_center',
        'rb5._snapshot_final_bs_dist',
        'rb5._snapshot_final_bs',
        'rb5._snapshot_final_lac',
    ):
        execute(f'DROP TABLE IF EXISTS {table_name}')


# ---------------------------------------------------------------------------
# Candidate pool: persistent storage for waiting/observing cells
# ---------------------------------------------------------------------------

def _ensure_candidate_pool() -> None:
    """Create candidate_cell_pool if not exists."""
    execute(
        """
        CREATE TABLE IF NOT EXISTS rb5.candidate_cell_pool (
            operator_code TEXT,
            operator_cn TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            independent_obs BIGINT,
            independent_devs BIGINT,
            independent_days BIGINT,
            record_count BIGINT,
            first_obs_at TIMESTAMPTZ,
            last_obs_at TIMESTAMPTZ,
            observed_span_hours DOUBLE PRECISION,
            active_days BIGINT,
            center_lon DOUBLE PRECISION,
            center_lat DOUBLE PRECISION,
            p50_radius_m DOUBLE PRECISION,
            p90_radius_m DOUBLE PRECISION,
            rsrp_avg DOUBLE PRECISION,
            rsrq_avg DOUBLE PRECISION,
            sinr_avg DOUBLE PRECISION,
            gps_valid_count BIGINT,
            gps_original_count BIGINT,
            signal_original_count BIGINT,
            gps_original_ratio DOUBLE PRECISION,
            gps_valid_ratio DOUBLE PRECISION,
            signal_original_ratio DOUBLE PRECISION,
            lifecycle_state TEXT NOT NULL DEFAULT 'waiting',
            first_seen_batch_id INTEGER,
            last_evaluated_batch_id INTEGER,
            UNIQUE (operator_code, lac, cell_id, tech_norm)
        )
        """
    )
    execute('ALTER TABLE rb5.candidate_cell_pool ADD COLUMN IF NOT EXISTS first_obs_at TIMESTAMPTZ')
    execute('ALTER TABLE rb5.candidate_cell_pool ADD COLUMN IF NOT EXISTS last_obs_at TIMESTAMPTZ')
    execute(
        """
        ALTER TABLE rb5.candidate_cell_pool
        DROP CONSTRAINT IF EXISTS candidate_cell_pool_operator_code_lac_cell_id_key
        """
    )
    execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'candidate_cell_pool_operator_code_lac_cell_id_tech_norm_key'
            ) THEN
                ALTER TABLE rb5.candidate_cell_pool
                ADD CONSTRAINT candidate_cell_pool_operator_code_lac_cell_id_tech_norm_key
                UNIQUE (operator_code, lac, cell_id, tech_norm);
            END IF;
        END $$;
        """
    )


def _update_candidate_pool(*, batch_id: int) -> dict[str, int]:
    """After evaluation: non-graduated → into pool, graduated → remove from pool.

    Graduated = lifecycle_state IN ('qualified', 'excellent') → delivered to Step 5 via snapshot.
    Non-graduated = waiting / observing → persist in pool for next round.
    """
    # Remove graduated cells from pool (they're now in snapshot for Step 5)
    execute(
        """
        DELETE FROM rb5.candidate_cell_pool cp
        WHERE EXISTS (
            SELECT 1 FROM rb5._snapshot_current_cell s
            WHERE s.operator_code = cp.operator_code
              AND s.lac = cp.lac
              AND s.cell_id = cp.cell_id
              AND s.tech_norm IS NOT DISTINCT FROM cp.tech_norm
              AND s.lifecycle_state IN ('qualified', 'excellent')
        )
        """
    )
    if relation_exists('rb5._candidate_eval_input'):
        execute(
            """
            INSERT INTO rb5.candidate_cell_pool (
                operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                independent_obs, independent_devs, independent_days, record_count,
                first_obs_at, last_obs_at, observed_span_hours, active_days, center_lon, center_lat,
                p50_radius_m, p90_radius_m, rsrp_avg, rsrq_avg, sinr_avg,
                gps_valid_count, gps_original_count, signal_original_count,
                gps_original_ratio, gps_valid_ratio, signal_original_ratio,
                lifecycle_state, first_seen_batch_id, last_evaluated_batch_id
            )
            SELECT
                p.operator_code, p.operator_cn, p.lac, p.bs_id, p.cell_id, p.tech_norm,
                p.independent_obs, p.independent_devs, p.independent_days, p.record_count,
                p.first_obs_at, p.last_obs_at, p.observed_span_hours, p.active_days, p.center_lon, p.center_lat,
                p.p50_radius_m, p.p90_radius_m, p.rsrp_avg, p.rsrq_avg, p.sinr_avg,
                p.gps_valid_count, p.gps_original_count, p.signal_original_count,
                p.gps_original_ratio, p.gps_valid_ratio, p.signal_original_ratio,
                s.lifecycle_state, %s, %s
            FROM rb5._candidate_eval_input p
            JOIN rb5._snapshot_current_cell s
              ON p.operator_code = s.operator_code
             AND p.lac = s.lac
             AND p.cell_id = s.cell_id
             AND p.tech_norm IS NOT DISTINCT FROM s.tech_norm
            WHERE s.lifecycle_state IN ('waiting', 'observing')
            ON CONFLICT (operator_code, lac, cell_id, tech_norm)
                DO UPDATE SET
                    operator_cn = EXCLUDED.operator_cn,
                    bs_id = EXCLUDED.bs_id,
                    tech_norm = EXCLUDED.tech_norm,
                    independent_obs = EXCLUDED.independent_obs,
                    independent_devs = EXCLUDED.independent_devs,
                    independent_days = EXCLUDED.independent_days,
                    record_count = EXCLUDED.record_count,
                    first_obs_at = EXCLUDED.first_obs_at,
                    last_obs_at = EXCLUDED.last_obs_at,
                    observed_span_hours = EXCLUDED.observed_span_hours,
                    active_days = EXCLUDED.active_days,
                    center_lon = EXCLUDED.center_lon,
                    center_lat = EXCLUDED.center_lat,
                    p50_radius_m = EXCLUDED.p50_radius_m,
                    p90_radius_m = EXCLUDED.p90_radius_m,
                    rsrp_avg = EXCLUDED.rsrp_avg,
                    rsrq_avg = EXCLUDED.rsrq_avg,
                    sinr_avg = EXCLUDED.sinr_avg,
                    gps_valid_count = EXCLUDED.gps_valid_count,
                    gps_original_count = EXCLUDED.gps_original_count,
                    signal_original_count = EXCLUDED.signal_original_count,
                    gps_original_ratio = EXCLUDED.gps_original_ratio,
                    gps_valid_ratio = EXCLUDED.gps_valid_ratio,
                    signal_original_ratio = EXCLUDED.signal_original_ratio,
                    lifecycle_state = EXCLUDED.lifecycle_state,
                    last_evaluated_batch_id = EXCLUDED.last_evaluated_batch_id
            """,
            (batch_id, batch_id),
        )
    prune_row = fetchone(
        """
        WITH pruned AS (
            DELETE FROM rb5.candidate_cell_pool
            WHERE lifecycle_state IN ('waiting', 'observing')
              AND COALESCE(first_seen_batch_id, %s) <= %s - %s
            RETURNING 1
        )
        SELECT COUNT(*) AS cnt FROM pruned
        """,
        (batch_id, batch_id, CANDIDATE_PRUNE_BATCHES),
    )
    return {
        'waiting_pruned_count': int(prune_row['cnt']) if prune_row else 0,
        'dormant_marked_count': 0,
    }


def run_evaluation_only() -> dict[str, Any]:
    """Run Step 3 evaluation independently (snapshot already exists from Step 2)."""
    ensure_profile_schema()
    thresholds = flatten_profile_thresholds(load_profile_params())
    antitoxin_thresholds = flatten_antitoxin_thresholds(load_antitoxin_params())
    run_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    previous_batch_id = get_latest_batch_id()
    previous_snapshot_version = f'v{previous_batch_id}' if previous_batch_id else 'v0'
    batch_id = previous_batch_id + 1
    snapshot_version = f'v{batch_id}'

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
        **step3_stats,
    }
    write_run_log(
        run_id=run_id,
        status='completed',
        snapshot_version=snapshot_version,
        result_summary=summary,
        step_chain='step3',
    )
    return summary
