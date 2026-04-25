"""Step 5.3 — Publish trusted_cell_library.

Merges:
- trusted_snapshot_cell (Step 3 frozen snapshot — list of qualified/excellent cells)
- cell_metrics_window (recalculated metrics from window.py)
- cell_anomaly_summary (GPS anomaly counts from cell_maintain.py)
- previous trusted_cell_library (for anti-toxification comparison)

Applies:
- Drift classification (from max_spread / net_drift / ratio — NOT p90)
- Anti-toxification (new vs old profile comparison)
- Exit management (dormant / retired from active_days_30d + consecutive_inactive_days)
- Label completion (is_dynamic, is_multi_centroid, cell_scale)
- Carry-forward: previously published cells that went Path A (not re-evaluated
  in current snapshot) are carried forward to the new batch_id with updated
  metrics from the sliding window, ensuring they remain visible to future
  routing and enrichment queries that read MAX(batch_id).

All SQL uses %s parameterization.
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY
from ..profile.pipeline import relation_exists

logger = logging.getLogger(__name__)


def publish_cell_library(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    snapshot_version_prev: str,
    antitoxin: dict[str, float],
) -> None:
    execute('DELETE FROM rb5.trusted_cell_library WHERE batch_id = %s', (batch_id,))

    has_metrics = relation_exists('rb5.cell_metrics_window')
    has_anomaly = relation_exists('rb5.cell_anomaly_summary')
    has_prev = relation_exists('rb5.trusted_cell_library')
    has_ta = relation_exists('rb5.cell_ta_stats')

    # Build optional JOIN flags — only used to gate LEFT JOINs
    metrics_join = 'TRUE' if has_metrics else 'FALSE'
    anomaly_join = 'TRUE' if has_anomaly else 'FALSE'
    ta_join = 'TRUE' if has_ta else 'FALSE'

    # Previous library for anti-toxification
    prev_join = 'TRUE' if has_prev else 'FALSE'

    execute(
        f"""
        INSERT INTO rb5.trusted_cell_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, anchor_eligible, baseline_eligible,
            center_lon, center_lat, p50_radius_m, p90_radius_m,
            position_grade, gps_confidence, signal_confidence,
            independent_obs, distinct_dev_id, gps_valid_count, active_days, observed_span_hours,
            rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
            drift_pattern, max_spread_m, net_drift_m, drift_ratio,
            gps_anomaly_type,
            is_collision, is_dynamic, is_multi_centroid, centroid_pattern, antitoxin_hit,
            cell_scale, last_maintained_at, last_observed_at, window_obs_count,
            active_days_30d, consecutive_inactive_days,
            ta_n_obs, ta_p50, ta_p90, ta_dist_p90_m, freq_band, ta_verification
        )
        WITH merged AS (
            SELECT
                s.operator_code, s.operator_cn, s.lac, s.bs_id, s.cell_id, s.tech_norm,
                s.lifecycle_state, s.anchor_eligible, s.baseline_eligible,
                -- Spatial: prefer recalculated
                COALESCE(cw.center_lon, s.center_lon) AS center_lon,
                COALESCE(cw.center_lat, s.center_lat) AS center_lat,
                COALESCE(cw.p50_radius_m, s.p50_radius_m) AS p50_radius_m,
                COALESCE(cw.p90_radius_m, s.p90_radius_m) AS p90_radius_m,
                s.position_grade, s.gps_confidence, s.signal_confidence,
                -- Observation metrics
                COALESCE(cw.independent_obs, s.independent_obs) AS independent_obs,
                COALESCE(cw.distinct_dev_id, s.distinct_dev_id) AS distinct_dev_id,
                COALESCE(cw.gps_valid_count, s.gps_valid_count) AS gps_valid_count,
                COALESCE(cw.active_days, s.active_days) AS active_days,
                COALESCE(cw.observed_span_hours, s.observed_span_hours) AS observed_span_hours,
                -- Signal + pressure
                COALESCE(cw.rsrp_avg, s.rsrp_avg) AS rsrp_avg,
                COALESCE(cw.rsrq_avg, s.rsrq_avg) AS rsrq_avg,
                COALESCE(cw.sinr_avg, s.sinr_avg) AS sinr_avg,
                cw.pressure_avg,
                -- Drift metrics (from cell_maintain.py)
                cw.max_spread_m,
                cw.net_drift_m,
                cw.drift_ratio,
                -- Anomaly
                COALESCE(a.anomaly_count, 0) AS anomaly_count,
                a.last_anomaly_at,
                a.gps_anomaly_type,
                -- Window
                cw.max_event_time,
                COALESCE(cw.window_obs_count, 0) AS window_obs_count,
                COALESCE(cw.active_days_30d, 0) AS active_days_30d,
                COALESCE(cw.consecutive_inactive_days, 0) AS consecutive_inactive_days,
                -- Previous library values for anti-toxification
                prev.center_lon AS prev_center_lon,
                prev.center_lat AS prev_center_lat,
                prev.p90_radius_m AS prev_p90_radius_m,
                prev.distinct_dev_id AS prev_distinct_dev_id,
                COALESCE(prev.is_dynamic, FALSE) AS prev_is_dynamic,
                COALESCE(prev.is_multi_centroid, FALSE) AS prev_is_multi_centroid,
                prev.centroid_pattern AS prev_centroid_pattern,
                -- TA stats (from cell_ta_stats; NULL 视为无 TA 数据)
                COALESCE(ta.ta_n_obs, 0) AS ta_n_obs,
                ta.ta_p50,
                ta.ta_p90,
                ta.ta_dist_p90_m,
                ta.freq_band
            FROM rb5.trusted_snapshot_cell s
            LEFT JOIN rb5.cell_metrics_window cw
              ON {metrics_join}
             AND cw.batch_id = %s
             AND cw.operator_code = s.operator_code AND cw.lac = s.lac
             AND cw.bs_id = s.bs_id AND cw.cell_id = s.cell_id
             AND cw.tech_norm IS NOT DISTINCT FROM s.tech_norm
            LEFT JOIN rb5.cell_anomaly_summary a
              ON {anomaly_join}
             AND a.batch_id = %s
             AND a.operator_code = s.operator_code AND a.lac = s.lac
             AND a.cell_id = s.cell_id
             AND a.tech_norm IS NOT DISTINCT FROM s.tech_norm
            LEFT JOIN rb5.cell_ta_stats ta
              ON {ta_join}
             AND ta.operator_code = s.operator_code AND ta.lac = s.lac
             AND ta.bs_id IS NOT DISTINCT FROM s.bs_id
             AND ta.cell_id = s.cell_id
             AND ta.tech_norm IS NOT DISTINCT FROM s.tech_norm
            LEFT JOIN (
                SELECT
                    operator_code,
                    lac,
                    cell_id,
                    tech_norm,
                    center_lon,
                    center_lat,
                    p90_radius_m,
                    distinct_dev_id,
                    is_dynamic,
                    is_multi_centroid,
                    centroid_pattern
                FROM rb5.trusted_cell_library
                WHERE batch_id = (
                    SELECT COALESCE(MAX(batch_id), 0)
                    FROM rb5.trusted_cell_library
                    WHERE batch_id < %s)
            ) prev
              ON {prev_join}
             AND prev.operator_code = s.operator_code AND prev.lac = s.lac
             AND prev.cell_id = s.cell_id
             AND prev.tech_norm IS NOT DISTINCT FROM s.tech_norm
            WHERE s.batch_id = %s
              AND s.lifecycle_state IN ('qualified', 'excellent')
        )
        SELECT
            %s::int, %s::text, %s::text, %s::text, %s::text, NOW(),
            m.operator_code, m.operator_cn, m.lac, m.bs_id, m.cell_id, m.tech_norm,

            -- lifecycle_state: exit management
            CASE
                WHEN m.consecutive_inactive_days >= %s THEN 'retired'
                WHEN (m.active_days_30d >= %s AND m.consecutive_inactive_days >= %s)
                  OR (m.active_days_30d >= %s AND m.consecutive_inactive_days >= %s)
                  OR (m.consecutive_inactive_days >= %s)
                    THEN 'dormant'
                ELSE m.lifecycle_state
            END AS lifecycle_state,

            m.anchor_eligible,

            -- baseline_eligible: blocked by antitoxin or anomaly
            (m.baseline_eligible AND NOT (
                -- antitoxin: centroid shift
                (m.prev_center_lon IS NOT NULL AND m.center_lon IS NOT NULL
                 AND SQRT(POWER((m.center_lon - m.prev_center_lon) * 85300, 2)
                        + POWER((m.center_lat - m.prev_center_lat) * 111000, 2)) > %s)
                -- antitoxin: p90 inflation
                OR (m.prev_p90_radius_m IS NOT NULL AND m.prev_p90_radius_m > 0
                    AND COALESCE(m.p90_radius_m, 0) / m.prev_p90_radius_m > %s)
                -- antitoxin: device surge
                OR (m.prev_distinct_dev_id IS NOT NULL AND m.prev_distinct_dev_id > 0
                    AND COALESCE(m.distinct_dev_id, 0)::double precision / m.prev_distinct_dev_id > %s)
                -- anomaly block
                OR m.anomaly_count >= 3
            )) AS baseline_eligible,

            m.center_lon, m.center_lat, m.p50_radius_m, m.p90_radius_m,
            m.position_grade, m.gps_confidence, m.signal_confidence,
            m.independent_obs, m.distinct_dev_id, m.gps_valid_count,
            m.active_days, m.observed_span_hours,
            m.rsrp_avg, m.rsrq_avg, m.sinr_avg, m.pressure_avg,

            -- drift_pattern: from max_spread / ratio (NOT p90)
            CASE
                WHEN COALESCE(m.active_days, 0) < %s THEN 'insufficient'
                WHEN COALESCE(m.max_spread_m, 0) < %s THEN 'stable'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.drift_ratio, 1) < %s
                    THEN 'collision'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.drift_ratio, 0) >= %s
                    THEN 'migration'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.max_spread_m, 0) < %s
                    THEN 'large_coverage'
                WHEN COALESCE(m.max_spread_m, 0) >= %s
                    THEN 'moderate_drift'
                ELSE 'stable'
            END AS drift_pattern,
            m.max_spread_m, m.net_drift_m, m.drift_ratio,

            -- gps_anomaly_type
            m.gps_anomaly_type,

            FALSE AS is_collision,  -- set by collision.py after publish

            -- is_dynamic: spread > 1500 AND drift_pattern in (migration, large_coverage)
            (COALESCE(m.prev_is_dynamic, FALSE) OR (
                COALESCE(m.max_spread_m, 0) > %s
             AND CASE
                 WHEN COALESCE(m.max_spread_m, 0) >= %s THEN TRUE
                 WHEN COALESCE(m.max_spread_m, 0) >= %s
                  AND COALESCE(m.max_spread_m, 0) < %s THEN TRUE
                 ELSE FALSE
             END)) AS is_dynamic,

            -- is_multi_centroid is finalized by PostGIS stable-cluster analysis in publish_bs_lac.py
            COALESCE(m.prev_is_multi_centroid, FALSE) AS is_multi_centroid,
            m.prev_centroid_pattern AS centroid_pattern,

            -- antitoxin_hit
            (
                (m.prev_center_lon IS NOT NULL AND m.center_lon IS NOT NULL
                 AND SQRT(POWER((m.center_lon - m.prev_center_lon) * 85300, 2)
                        + POWER((m.center_lat - m.prev_center_lat) * 111000, 2)) > %s)
                OR (m.prev_p90_radius_m IS NOT NULL AND m.prev_p90_radius_m > 0
                    AND COALESCE(m.p90_radius_m, 0) / m.prev_p90_radius_m > %s)
                OR (m.prev_distinct_dev_id IS NOT NULL AND m.prev_distinct_dev_id > 0
                    AND COALESCE(m.distinct_dev_id, 0)::double precision / m.prev_distinct_dev_id > %s)
                OR (m.anomaly_count >= 3 AND COALESCE(m.max_spread_m, 0) >= %s)
            ) AS antitoxin_hit,

            -- cell_scale
            CASE
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'major'
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'large'
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'medium'
                WHEN m.independent_obs >= %s THEN 'small'
                ELSE 'micro'
            END,

            NOW(),
            COALESCE(m.max_event_time, m.last_anomaly_at),
            m.window_obs_count,
            m.active_days_30d,
            m.consecutive_inactive_days,

            -- TA 统计字段透传
            m.ta_n_obs,
            m.ta_p50,
            m.ta_p90,
            m.ta_dist_p90_m,
            m.freq_band,

            -- ta_verification（基于 is_multi_centroid / is_collision / freq_band / ta_p90 计算）
            -- 参考 docs/gps研究/11_TA字段应用可行性研究.md §6
            CASE
                WHEN COALESCE(m.prev_is_multi_centroid, FALSE) THEN 'not_applicable'
                WHEN m.freq_band IS NULL OR m.freq_band != 'fdd' THEN 'not_checked'
                WHEN COALESCE(m.ta_n_obs, 0) < 5 THEN 'insufficient'
                WHEN m.ta_p90 > 30 THEN 'xlarge'      -- TA 估算 >2.3km，郊区/农村
                WHEN m.ta_p90 > 20 THEN 'large'       -- TA 估算 1.5-2.3km
                ELSE 'ok'                              -- 小/中覆盖
            END
        FROM merged m
        """,
        (
            # merged CTE joins
            batch_id,  # cw.batch_id
            batch_id,  # a.batch_id
            batch_id,  # prev batch_id <
            batch_id,  # s.batch_id
            # INSERT values
            batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id,
            # exit management
            antitoxin['exit_retired_after_dormant_days'],                    # retired threshold
            antitoxin['exit_high_density_min_30d'],                          # high density check
            antitoxin['exit_dormant_days_high'],                             # high density dormant
            antitoxin['exit_mid_density_min_30d'],                           # mid density check
            antitoxin['exit_dormant_days_mid'],                              # mid density dormant
            antitoxin['exit_dormant_days_low'],                              # low density dormant
            # baseline antitoxin
            antitoxin['antitoxin_max_centroid_shift_m'],
            antitoxin['antitoxin_max_p90_ratio'],
            antitoxin['antitoxin_max_dev_ratio'],
            # drift classification
            antitoxin['insufficient_min_days'],                              # insufficient
            antitoxin['stable_max_spread_m'],                                # stable
            antitoxin['collision_min_spread_m'],                             # collision spread
            antitoxin['drift_collision_max_ratio'],                          # collision ratio
            antitoxin['collision_min_spread_m'],                             # migration spread
            antitoxin['drift_migration_min_ratio'],                          # migration ratio
            antitoxin['stable_max_spread_m'],                                # large_coverage lower
            antitoxin['drift_large_coverage_max_spread_m'],                  # large_coverage upper
            antitoxin['collision_min_spread_m'],                             # moderate_drift
            # is_dynamic
            antitoxin['is_dynamic_min_spread_m'],                            # spread > 1500
            antitoxin['collision_min_spread_m'],                             # migration check
            antitoxin['stable_max_spread_m'],                                # large_coverage lower
            antitoxin['drift_large_coverage_max_spread_m'],                  # large_coverage upper
            # antitoxin_hit
            antitoxin['antitoxin_max_centroid_shift_m'],
            antitoxin['antitoxin_max_p90_ratio'],
            antitoxin['antitoxin_max_dev_ratio'],
            antitoxin['stable_max_spread_m'],                                # anomaly + spread
            # cell_scale
            antitoxin['cell_scale_major_min_obs'], antitoxin['cell_scale_major_min_devs'],
            antitoxin['cell_scale_large_min_obs'], antitoxin['cell_scale_large_min_devs'],
            antitoxin['cell_scale_medium_min_obs'], antitoxin['cell_scale_medium_min_devs'],
            antitoxin['cell_scale_small_min_obs'],
        ),
    )

    # -- Carry forward previously published cells not in current snapshot --
    carried = _carry_forward_previous_cells(
        batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=snapshot_version_prev,
        run_id=run_id,
        antitoxin=antitoxin,
    )
    if carried:
        logger.info('Carried forward %d cells from previous library', carried)


def _carry_forward_previous_cells(
    *,
    batch_id: int,
    snapshot_version: str,
    snapshot_version_prev: str,
    run_id: str,
    antitoxin: dict[str, float],
) -> int:
    """Carry forward cells from the previous library that were not re-evaluated.

    These are cells that went through Path A (hit the library) in Step 2, so
    they were not included in the current batch's trusted_snapshot_cell.  Without
    carry-forward they would "fall off" the active library because routing and
    enrichment queries read only MAX(batch_id).

    For each carried-forward cell, if cell_metrics_window has updated data (from
    enriched Path-A records flowing through the sliding window), the metrics are
    refreshed; otherwise the previous values are kept unchanged.

    Returns the number of cells carried forward.
    """
    has_metrics = relation_exists('rb5.cell_metrics_window')
    has_anomaly = relation_exists('rb5.cell_anomaly_summary')
    has_ta = relation_exists('rb5.cell_ta_stats')

    metrics_join = 'TRUE' if has_metrics else 'FALSE'
    anomaly_join = 'TRUE' if has_anomaly else 'FALSE'
    ta_join = 'TRUE' if has_ta else 'FALSE'

    execute(
        f"""
        INSERT INTO rb5.trusted_cell_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, anchor_eligible, baseline_eligible,
            center_lon, center_lat, p50_radius_m, p90_radius_m,
            position_grade, gps_confidence, signal_confidence,
            independent_obs, distinct_dev_id, gps_valid_count, active_days, observed_span_hours,
            rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
            drift_pattern, max_spread_m, net_drift_m, drift_ratio,
            gps_anomaly_type,
            is_collision, is_dynamic, is_multi_centroid, centroid_pattern, antitoxin_hit,
            cell_scale, last_maintained_at, last_observed_at, window_obs_count,
            active_days_30d, consecutive_inactive_days,
            ta_n_obs, ta_p50, ta_p90, ta_dist_p90_m, freq_band, ta_verification
        )
        WITH prev_cells AS (
            SELECT prev.*
            FROM rb5.trusted_cell_library prev
            WHERE prev.batch_id = (
                SELECT COALESCE(MAX(batch_id), 0)
                FROM rb5.trusted_cell_library
                WHERE batch_id < %s
            )
            AND prev.lifecycle_state != 'retired'
            -- Exclude cells already published from the current snapshot
            AND NOT EXISTS (
                SELECT 1 FROM rb5.trusted_cell_library curr
                WHERE curr.batch_id = %s
                  AND curr.operator_code = prev.operator_code
                  AND curr.lac = prev.lac
                  AND curr.cell_id = prev.cell_id
                  AND curr.tech_norm IS NOT DISTINCT FROM prev.tech_norm
            )
        ),
        merged AS (
            SELECT
                p.operator_code, p.operator_cn, p.lac, p.bs_id, p.cell_id, p.tech_norm,
                p.lifecycle_state,
                p.anchor_eligible,
                p.baseline_eligible,
                -- Spatial: prefer recalculated from window
                COALESCE(cw.center_lon, p.center_lon) AS center_lon,
                COALESCE(cw.center_lat, p.center_lat) AS center_lat,
                COALESCE(cw.p50_radius_m, p.p50_radius_m) AS p50_radius_m,
                COALESCE(cw.p90_radius_m, p.p90_radius_m) AS p90_radius_m,
                p.position_grade, p.gps_confidence, p.signal_confidence,
                -- Observation metrics
                COALESCE(cw.independent_obs, p.independent_obs) AS independent_obs,
                COALESCE(cw.distinct_dev_id, p.distinct_dev_id) AS distinct_dev_id,
                COALESCE(cw.gps_valid_count, p.gps_valid_count) AS gps_valid_count,
                COALESCE(cw.active_days, p.active_days) AS active_days,
                COALESCE(cw.observed_span_hours, p.observed_span_hours) AS observed_span_hours,
                -- Signal + pressure
                COALESCE(cw.rsrp_avg, p.rsrp_avg) AS rsrp_avg,
                COALESCE(cw.rsrq_avg, p.rsrq_avg) AS rsrq_avg,
                COALESCE(cw.sinr_avg, p.sinr_avg) AS sinr_avg,
                COALESCE(cw.pressure_avg, p.pressure_avg) AS pressure_avg,
                -- Drift metrics: prefer recalculated
                COALESCE(cw.max_spread_m, p.max_spread_m) AS max_spread_m,
                COALESCE(cw.net_drift_m, p.net_drift_m) AS net_drift_m,
                COALESCE(cw.drift_ratio, p.drift_ratio) AS drift_ratio,
                -- Anomaly
                COALESCE(a.anomaly_count, 0) AS anomaly_count,
                a.last_anomaly_at,
                a.gps_anomaly_type,
                -- Window
                cw.max_event_time,
                COALESCE(cw.window_obs_count, p.window_obs_count, 0) AS window_obs_count,
                COALESCE(cw.active_days_30d, p.active_days_30d, 0) AS active_days_30d,
                COALESCE(cw.consecutive_inactive_days, p.consecutive_inactive_days, 0) AS consecutive_inactive_days,
                -- Previous values for antitoxin (= the carry-forward source itself)
                p.center_lon AS prev_center_lon,
                p.center_lat AS prev_center_lat,
                p.p90_radius_m AS prev_p90_radius_m,
                p.distinct_dev_id AS prev_distinct_dev_id,
                COALESCE(p.is_dynamic, FALSE) AS prev_is_dynamic,
                COALESCE(p.is_multi_centroid, FALSE) AS prev_is_multi_centroid,
                p.centroid_pattern AS prev_centroid_pattern,
                -- TA stats: prefer fresh from cell_ta_stats, fallback to prev
                COALESCE(ta.ta_n_obs, p.ta_n_obs, 0) AS ta_n_obs,
                COALESCE(ta.ta_p50, p.ta_p50) AS ta_p50,
                COALESCE(ta.ta_p90, p.ta_p90) AS ta_p90,
                COALESCE(ta.ta_dist_p90_m, p.ta_dist_p90_m) AS ta_dist_p90_m,
                COALESCE(ta.freq_band, p.freq_band) AS freq_band
            FROM prev_cells p
            LEFT JOIN rb5.cell_metrics_window cw
              ON {metrics_join}
             AND cw.batch_id = %s
             AND cw.operator_code = p.operator_code AND cw.lac = p.lac
             AND cw.bs_id = p.bs_id AND cw.cell_id = p.cell_id
             AND cw.tech_norm IS NOT DISTINCT FROM p.tech_norm
            LEFT JOIN rb5.cell_anomaly_summary a
              ON {anomaly_join}
             AND a.batch_id = %s
             AND a.operator_code = p.operator_code AND a.lac = p.lac
             AND a.cell_id = p.cell_id
             AND a.tech_norm IS NOT DISTINCT FROM p.tech_norm
            LEFT JOIN rb5.cell_ta_stats ta
              ON {ta_join}
             AND ta.operator_code = p.operator_code AND ta.lac = p.lac
             AND ta.bs_id IS NOT DISTINCT FROM p.bs_id
             AND ta.cell_id = p.cell_id
             AND ta.tech_norm IS NOT DISTINCT FROM p.tech_norm
        )
        SELECT
            %s::int, %s::text, %s::text, %s::text, %s::text, NOW(),
            m.operator_code, m.operator_cn, m.lac, m.bs_id, m.cell_id, m.tech_norm,

            -- lifecycle_state: exit management
            CASE
                WHEN m.consecutive_inactive_days >= %s THEN 'retired'
                WHEN (m.active_days_30d >= %s AND m.consecutive_inactive_days >= %s)
                  OR (m.active_days_30d >= %s AND m.consecutive_inactive_days >= %s)
                  OR (m.consecutive_inactive_days >= %s)
                    THEN 'dormant'
                ELSE m.lifecycle_state
            END AS lifecycle_state,

            m.anchor_eligible,

            -- baseline_eligible: blocked by antitoxin or anomaly
            (m.baseline_eligible AND NOT (
                (m.prev_center_lon IS NOT NULL AND m.center_lon IS NOT NULL
                 AND SQRT(POWER((m.center_lon - m.prev_center_lon) * 85300, 2)
                        + POWER((m.center_lat - m.prev_center_lat) * 111000, 2)) > %s)
                OR (m.prev_p90_radius_m IS NOT NULL AND m.prev_p90_radius_m > 0
                    AND COALESCE(m.p90_radius_m, 0) / m.prev_p90_radius_m > %s)
                OR (m.prev_distinct_dev_id IS NOT NULL AND m.prev_distinct_dev_id > 0
                    AND COALESCE(m.distinct_dev_id, 0)::double precision / m.prev_distinct_dev_id > %s)
                OR m.anomaly_count >= 3
            )) AS baseline_eligible,

            m.center_lon, m.center_lat, m.p50_radius_m, m.p90_radius_m,
            m.position_grade, m.gps_confidence, m.signal_confidence,
            m.independent_obs, m.distinct_dev_id, m.gps_valid_count,
            m.active_days, m.observed_span_hours,
            m.rsrp_avg, m.rsrq_avg, m.sinr_avg, m.pressure_avg,

            -- drift_pattern
            CASE
                WHEN COALESCE(m.active_days, 0) < %s THEN 'insufficient'
                WHEN COALESCE(m.max_spread_m, 0) < %s THEN 'stable'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.drift_ratio, 1) < %s
                    THEN 'collision'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.drift_ratio, 0) >= %s
                    THEN 'migration'
                WHEN COALESCE(m.max_spread_m, 0) >= %s AND COALESCE(m.max_spread_m, 0) < %s
                    THEN 'large_coverage'
                WHEN COALESCE(m.max_spread_m, 0) >= %s
                    THEN 'moderate_drift'
                ELSE 'stable'
            END AS drift_pattern,
            m.max_spread_m, m.net_drift_m, m.drift_ratio,

            m.gps_anomaly_type,

            FALSE AS is_collision,

            (COALESCE(m.prev_is_dynamic, FALSE) OR (
                COALESCE(m.max_spread_m, 0) > %s
             AND CASE
                 WHEN COALESCE(m.max_spread_m, 0) >= %s THEN TRUE
                 WHEN COALESCE(m.max_spread_m, 0) >= %s
                  AND COALESCE(m.max_spread_m, 0) < %s THEN TRUE
                 ELSE FALSE
             END)) AS is_dynamic,

            COALESCE(m.prev_is_multi_centroid, FALSE) AS is_multi_centroid,
            m.prev_centroid_pattern AS centroid_pattern,

            (
                (m.prev_center_lon IS NOT NULL AND m.center_lon IS NOT NULL
                 AND SQRT(POWER((m.center_lon - m.prev_center_lon) * 85300, 2)
                        + POWER((m.center_lat - m.prev_center_lat) * 111000, 2)) > %s)
                OR (m.prev_p90_radius_m IS NOT NULL AND m.prev_p90_radius_m > 0
                    AND COALESCE(m.p90_radius_m, 0) / m.prev_p90_radius_m > %s)
                OR (m.prev_distinct_dev_id IS NOT NULL AND m.prev_distinct_dev_id > 0
                    AND COALESCE(m.distinct_dev_id, 0)::double precision / m.prev_distinct_dev_id > %s)
                OR (m.anomaly_count >= 3 AND COALESCE(m.max_spread_m, 0) >= %s)
            ) AS antitoxin_hit,

            CASE
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'major'
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'large'
                WHEN m.independent_obs >= %s AND m.distinct_dev_id >= %s THEN 'medium'
                WHEN m.independent_obs >= %s THEN 'small'
                ELSE 'micro'
            END,

            NOW(),
            COALESCE(m.max_event_time, m.last_anomaly_at, p_last_obs.last_observed_at),
            m.window_obs_count,
            m.active_days_30d,
            m.consecutive_inactive_days,

            -- TA 字段透传（carry-forward 也带）
            m.ta_n_obs,
            m.ta_p50,
            m.ta_p90,
            m.ta_dist_p90_m,
            m.freq_band,

            -- ta_verification（同主 INSERT 的规则）
            CASE
                WHEN COALESCE(m.prev_is_multi_centroid, FALSE) THEN 'not_applicable'
                WHEN m.freq_band IS NULL OR m.freq_band != 'fdd' THEN 'not_checked'
                WHEN COALESCE(m.ta_n_obs, 0) < 5 THEN 'insufficient'
                WHEN m.ta_p90 > 30 THEN 'xlarge'
                WHEN m.ta_p90 > 20 THEN 'large'
                ELSE 'ok'
            END
        FROM merged m
        LEFT JOIN prev_cells p_last_obs
          ON p_last_obs.operator_code = m.operator_code
         AND p_last_obs.lac = m.lac
         AND p_last_obs.cell_id = m.cell_id
        """,
        (
            # prev_cells CTE
            batch_id,  # batch_id < %s
            batch_id,  # curr.batch_id = %s
            # merged CTE joins
            batch_id,  # cw.batch_id
            batch_id,  # a.batch_id
            # INSERT values
            batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id,
            # exit management (same thresholds as main publish)
            antitoxin['exit_retired_after_dormant_days'],
            antitoxin['exit_high_density_min_30d'],
            antitoxin['exit_dormant_days_high'],
            antitoxin['exit_mid_density_min_30d'],
            antitoxin['exit_dormant_days_mid'],
            antitoxin['exit_dormant_days_low'],
            # baseline antitoxin
            antitoxin['antitoxin_max_centroid_shift_m'],
            antitoxin['antitoxin_max_p90_ratio'],
            antitoxin['antitoxin_max_dev_ratio'],
            # drift classification
            antitoxin['insufficient_min_days'],
            antitoxin['stable_max_spread_m'],
            antitoxin['collision_min_spread_m'],
            antitoxin['drift_collision_max_ratio'],
            antitoxin['collision_min_spread_m'],
            antitoxin['drift_migration_min_ratio'],
            antitoxin['stable_max_spread_m'],
            antitoxin['drift_large_coverage_max_spread_m'],
            antitoxin['collision_min_spread_m'],
            # is_dynamic
            antitoxin['is_dynamic_min_spread_m'],
            antitoxin['collision_min_spread_m'],
            antitoxin['stable_max_spread_m'],
            antitoxin['drift_large_coverage_max_spread_m'],
            # antitoxin_hit
            antitoxin['antitoxin_max_centroid_shift_m'],
            antitoxin['antitoxin_max_p90_ratio'],
            antitoxin['antitoxin_max_dev_ratio'],
            antitoxin['stable_max_spread_m'],
            # cell_scale
            antitoxin['cell_scale_major_min_obs'], antitoxin['cell_scale_major_min_devs'],
            antitoxin['cell_scale_large_min_obs'], antitoxin['cell_scale_large_min_devs'],
            antitoxin['cell_scale_medium_min_obs'], antitoxin['cell_scale_medium_min_devs'],
            antitoxin['cell_scale_small_min_obs'],
        ),
    )

    # Step 3 writes a large fresh snapshot immediately before Step 5.
    # Refresh stats before the anti-join count so early batches do not wait for autovacuum.
    execute('ANALYZE rb5.trusted_cell_library')
    execute('ANALYZE rb5.trusted_snapshot_cell')

    # Count how many were actually carried forward
    row = fetchone(
        """
        SELECT COUNT(*) AS cnt
        FROM rb5.trusted_cell_library c
        WHERE c.batch_id = %s
          AND NOT EXISTS (
              SELECT 1 FROM rb5.trusted_snapshot_cell s
              WHERE s.batch_id = %s
                AND s.operator_code = c.operator_code
                AND s.lac = c.lac
                AND s.cell_id = c.cell_id
          )
        """,
        (batch_id, batch_id),
    )
    return int(row['cnt']) if row else 0
