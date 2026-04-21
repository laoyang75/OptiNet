"""Step 5.4 — Publish BS/LAC libraries and centroid details.

BS: aggregated from trusted_cell_library (Cell → BS).
LAC: aggregated from trusted_bs_library (BS → LAC).

Current focus:
- BS classification: all 5 types (collision_bs/dynamic_bs/large_spread/multi_centroid/normal_spread)
- BS: is_multi_centroid, window_active_cell_count
- LAC: active_bs_count, retired_bs_count, boundary_stability_score
- Cell / BS centroid detail: lightweight multi-cluster split from staged centroids
"""
from __future__ import annotations

from typing import Any

from ..core.database import execute, get_conn
from ..etl.source_prep import DATASET_KEY
from ..profile.logic import (
    flatten_antitoxin_thresholds,
    flatten_profile_thresholds,
    load_antitoxin_params,
    load_profile_params,
)


# ---------------------------------------------------------------------------
# Cell centroid detail
# ---------------------------------------------------------------------------


def _postgis_centroid_config() -> dict[str, Any]:
    payload = load_antitoxin_params()
    cfg = payload.get('postgis_centroid', {})
    return {
        'lookback_batches': int(cfg.get('lookback_batches', 4)),
        'candidate_min_window_obs': int(cfg.get('candidate_min_window_obs', 5)),
        'candidate_min_active_days': int(cfg.get('candidate_min_active_days', 2)),
        'candidate_min_p90_m': float(cfg.get('candidate_min_p90_m', 800)),
        'candidate_min_raw_p90_m': float(cfg.get('candidate_min_raw_p90_m', cfg.get('candidate_min_p90_m', 800))),
        'candidate_min_max_spread_m': float(cfg.get('candidate_min_max_spread_m', 2200)),
        'candidate_min_outlier_ratio': float(cfg.get('candidate_min_outlier_ratio', 0.15)),
        'candidate_drift_patterns': tuple(cfg.get('candidate_drift_patterns', ['large_coverage', 'migration', 'collision', 'moderate_drift'])),
        'snap_grid_m': float(cfg.get('snap_grid_m', 50)),
        'cluster_eps_m': float(cfg.get('cluster_eps_m', 250)),
        'cluster_min_points': int(cfg.get('cluster_min_points', 4)),
        'stable_min_obs': int(cfg.get('stable_min_obs', 5)),
        'stable_min_share': float(cfg.get('stable_min_share', 0.10)),
        'stable_min_days': int(cfg.get('stable_min_days', 2)),
        'stable_min_devs': int(cfg.get('stable_min_devs', 2)),
        'stable_single_device_max_total_devs': int(cfg.get('stable_single_device_max_total_devs', 2)),
        'classification_min_secondary_share': float(cfg.get('classification_min_secondary_share', 0.15)),
        'dual_cluster_min_distance_m': float(cfg.get('dual_cluster_min_distance_m', 300)),
        'migration_min_distance_m': float(cfg.get('migration_min_distance_m', 500)),
        'migration_max_overlap_days': int(cfg.get('migration_max_overlap_days', 1)),
        'moving_min_overlap_days': int(cfg.get('moving_min_overlap_days', 2)),
        'moving_min_switches': int(cfg.get('moving_min_switches', 2)),
        'multi_cluster_min_cluster_count': int(cfg.get('multi_cluster_min_cluster_count', 3)),
        'recalc_min_p90_delta_m': float(cfg.get('recalc_min_p90_delta_m', 200)),
        'recalc_min_window_obs_delta': int(cfg.get('recalc_min_window_obs_delta', 10)),
    }

def publish_cell_centroid_detail(
    *,
    batch_id: int,
    snapshot_version: str,
    multi_centroid_threshold_m: float | None = None,
    spread_threshold_m: float | None = None,
) -> None:
    thresholds = flatten_antitoxin_thresholds(load_antitoxin_params())
    centroid_cfg = _postgis_centroid_config()
    multi_centroid_threshold_m = (
        float(multi_centroid_threshold_m)
        if multi_centroid_threshold_m is not None
        else centroid_cfg['candidate_min_p90_m']
    )
    spread_threshold_m = (
        float(spread_threshold_m)
        if spread_threshold_m is not None
        else centroid_cfg['candidate_min_max_spread_m']
    )
    snap_grid_m = centroid_cfg['snap_grid_m']
    cluster_eps_m = centroid_cfg['cluster_eps_m']
    cluster_min_points = centroid_cfg['cluster_min_points']
    min_cluster_obs = centroid_cfg['stable_min_obs']
    min_cluster_share = centroid_cfg['stable_min_share']
    min_cluster_days = centroid_cfg['stable_min_days']
    candidate_window_obs = centroid_cfg['candidate_min_window_obs']
    candidate_active_days = centroid_cfg['candidate_min_active_days']
    candidate_min_p90_m = centroid_cfg['candidate_min_p90_m']
    candidate_min_raw_p90_m = centroid_cfg['candidate_min_raw_p90_m']
    candidate_min_max_spread_m = centroid_cfg['candidate_min_max_spread_m']
    candidate_min_outlier_ratio = centroid_cfg['candidate_min_outlier_ratio']
    lookback_batches = centroid_cfg['lookback_batches']
    drift_patterns_sql = ', '.join(f"'{value}'" for value in centroid_cfg['candidate_drift_patterns'])
    window_batch_start = max(batch_id - lookback_batches, 0)
    recalc_p90_delta_m = centroid_cfg['recalc_min_p90_delta_m']
    recalc_window_obs_delta = centroid_cfg['recalc_min_window_obs_delta']
    stage_tables = (
        'rebuild5._cell_centroid_candidates',
        'rebuild5._cell_centroid_points',
        'rebuild5._cell_centroid_grid_points',
        'rebuild5._cell_centroid_clustered_grid',
        'rebuild5._cell_centroid_labelled_points',
        'rebuild5._cell_centroid_cell_totals',
        'rebuild5._cell_centroid_cluster_base',
        'rebuild5._cell_centroid_cluster_centers',
        'rebuild5._cell_centroid_cluster_radius',
        'rebuild5._cell_centroid_cluster_stats',
        'rebuild5._cell_centroid_filtered_clusters',
        'rebuild5._cell_centroid_ranked_clusters',
        'rebuild5._cell_centroid_valid_clusters',
        'rebuild5._cell_centroid_daily_presence',
        'rebuild5._cell_centroid_classification',
    )
    for table_name in stage_tables:
        execute(f'DROP TABLE IF EXISTS {table_name}')
    execute('DELETE FROM rebuild5.cell_centroid_detail WHERE batch_id = %s', (batch_id,))
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_candidates AS
        WITH prev AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                p90_radius_m,
                window_obs_count,
                drift_pattern,
                gps_anomaly_type,
                is_dynamic,
                is_multi_centroid,
                centroid_pattern
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = (
                SELECT COALESCE(MAX(batch_id), 0)
                FROM rebuild5.trusted_cell_library
                WHERE batch_id < {batch_id}
            )
        )
        SELECT
            t.batch_id,
            t.operator_code,
            t.lac,
            t.bs_id,
            t.cell_id,
            t.tech_norm
        FROM rebuild5.trusted_cell_library t
        LEFT JOIN rebuild5.cell_metrics_window m
          ON m.batch_id = t.batch_id
         AND m.operator_code = t.operator_code
         AND m.lac IS NOT DISTINCT FROM t.lac
         AND m.bs_id IS NOT DISTINCT FROM t.bs_id
         AND m.cell_id = t.cell_id
         AND m.tech_norm IS NOT DISTINCT FROM t.tech_norm
        LEFT JOIN prev p
          ON p.operator_code = t.operator_code
         AND p.lac IS NOT DISTINCT FROM t.lac
         AND p.bs_id IS NOT DISTINCT FROM t.bs_id
         AND p.cell_id = t.cell_id
         AND p.tech_norm IS NOT DISTINCT FROM t.tech_norm
        WHERE t.batch_id = %s
          AND (
              (
                  COALESCE(t.window_obs_count, 0) >= {candidate_window_obs}
                  AND COALESCE(t.active_days, 0) >= {candidate_active_days}
              )
              OR COALESCE(t.p90_radius_m, 0) >= {candidate_min_p90_m}
              OR COALESCE(m.raw_p90_radius_m, 0) >= {candidate_min_raw_p90_m}
              OR COALESCE(t.max_spread_m, 0) >= {candidate_min_max_spread_m}
              OR COALESCE(m.core_outlier_ratio, 0) >= {candidate_min_outlier_ratio}
              OR t.gps_anomaly_type IS NOT NULL
          )
          AND (
              t.gps_anomaly_type IS NOT NULL
              OR t.is_collision
              OR t.is_dynamic
              OR t.is_multi_centroid
              OR t.centroid_pattern IS NOT NULL
              OR t.drift_pattern IN ({drift_patterns_sql})
              OR COALESCE(t.p90_radius_m, 0) >= {candidate_min_p90_m}
              OR COALESCE(m.raw_p90_radius_m, 0) >= {candidate_min_raw_p90_m}
              OR COALESCE(t.max_spread_m, 0) >= {candidate_min_max_spread_m}
              OR COALESCE(m.core_outlier_ratio, 0) >= {candidate_min_outlier_ratio}
          )
          AND (
              p.cell_id IS NULL
              OR p.gps_anomaly_type IS DISTINCT FROM t.gps_anomaly_type
              OR COALESCE(p.is_dynamic, FALSE) <> COALESCE(t.is_dynamic, FALSE)
              OR COALESCE(p.is_multi_centroid, FALSE) <> COALESCE(t.is_multi_centroid, FALSE)
              OR p.centroid_pattern IS DISTINCT FROM t.centroid_pattern
              OR p.drift_pattern IS DISTINCT FROM t.drift_pattern
              OR ABS(COALESCE(t.p90_radius_m, 0) - COALESCE(p.p90_radius_m, 0)) >= {recalc_p90_delta_m}
              OR ABS(COALESCE(t.window_obs_count, 0) - COALESCE(p.window_obs_count, 0)) >= {recalc_window_obs_delta}
              OR COALESCE(m.core_outlier_ratio, 0) >= {candidate_min_outlier_ratio}
          )
        """,
        (batch_id,),
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_candidates_key
        ON rebuild5._cell_centroid_candidates (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_candidates')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_points AS
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            w.source_row_uid,
            w.dev_id,
            DATE(w.event_time_std) AS obs_date,
            ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857) AS geom_3857,
            ST_SnapToGrid(
                ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857),
                {snap_grid_m}
            ) AS snap_geom_3857
        FROM rebuild5._cell_centroid_candidates c
        JOIN rebuild5.cell_sliding_window w
          ON w.batch_id BETWEEN {window_batch_start} AND {batch_id}
         AND w.operator_code = c.operator_code
         AND w.lac IS NOT DISTINCT FROM c.lac
         AND w.bs_id IS NOT DISTINCT FROM c.bs_id
         AND w.cell_id = c.cell_id
         AND w.tech_norm IS NOT DISTINCT FROM c.tech_norm
        WHERE w.gps_valid IS TRUE
          AND w.lon_final IS NOT NULL
          AND w.lat_final IS NOT NULL
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_points_key
        ON rebuild5._cell_centroid_points (operator_code, lac, bs_id, cell_id, tech_norm, obs_date)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_points')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_grid_points AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            snap_geom_3857,
            COUNT(*) AS snap_obs_count
        FROM rebuild5._cell_centroid_points
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, snap_geom_3857
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_grid_key
        ON rebuild5._cell_centroid_grid_points (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_grid_points')
    _execute_with_session_settings(
        session_setup_sqls=['SET enable_nestloop = off'],
        sql=f"""
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_clustered_grid AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            snap_geom_3857,
            COALESCE(
                ST_ClusterDBSCAN(
                    snap_geom_3857,
                    eps => {cluster_eps_m},
                    minpoints => {cluster_min_points}
                ) OVER (
                    PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
                ),
                -1
            ) AS cluster_id
        FROM rebuild5._cell_centroid_grid_points
        """,
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_clustered_grid_key
        ON rebuild5._cell_centroid_clustered_grid (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_clustered_grid')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_labelled_points AS
        SELECT
            p.operator_code,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            p.source_row_uid,
            p.dev_id,
            p.obs_date,
            p.geom_3857,
            g.cluster_id
        FROM rebuild5._cell_centroid_points p
        JOIN rebuild5._cell_centroid_clustered_grid g
          ON g.operator_code = p.operator_code
         AND g.lac IS NOT DISTINCT FROM p.lac
         AND g.bs_id IS NOT DISTINCT FROM p.bs_id
         AND g.cell_id = p.cell_id
         AND g.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND g.snap_geom_3857 = p.snap_geom_3857
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_labelled_key
        ON rebuild5._cell_centroid_labelled_points (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id, obs_date)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_labelled_points')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_cell_totals AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            COUNT(*) AS total_obs,
            COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS total_dev_count
        FROM rebuild5._cell_centroid_points
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_cell_totals_key
        ON rebuild5._cell_centroid_cell_totals (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_cell_totals')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_base AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            cluster_id,
            COUNT(*) AS obs_count,
            COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS dev_count,
            COUNT(DISTINCT obs_date) AS active_days,
            AVG(ST_X(geom_3857)) AS center_x,
            AVG(ST_Y(geom_3857)) AS center_y
        FROM rebuild5._cell_centroid_labelled_points
        WHERE cluster_id >= 0
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_cluster_base_key
        ON rebuild5._cell_centroid_cluster_base (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_cluster_base')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_centers AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            cluster_id,
            center_x,
            center_y,
            ST_SetSRID(ST_MakePoint(center_x, center_y), 3857) AS center_3857,
            obs_count,
            dev_count,
            active_days
        FROM rebuild5._cell_centroid_cluster_base
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_cluster_centers_key
        ON rebuild5._cell_centroid_cluster_centers (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_cluster_centers')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_radius AS
        SELECT
            p.operator_code,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            p.cluster_id,
            MAX(
                SQRT(
                    POWER(ST_X(p.geom_3857) - c.center_x, 2)
                  + POWER(ST_Y(p.geom_3857) - c.center_y, 2)
                )
            ) AS radius_m
        FROM rebuild5._cell_centroid_labelled_points p
        JOIN rebuild5._cell_centroid_cluster_centers c
          ON c.operator_code = p.operator_code
         AND c.lac IS NOT DISTINCT FROM p.lac
         AND c.bs_id IS NOT DISTINCT FROM p.bs_id
         AND c.cell_id = p.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND c.cluster_id = p.cluster_id
        WHERE p.cluster_id >= 0
        GROUP BY p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm, p.cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_cluster_radius_key
        ON rebuild5._cell_centroid_cluster_radius (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_cluster_radius')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_stats AS
        SELECT
            cc.operator_code,
            cc.lac,
            cc.bs_id,
            cc.cell_id,
            cc.tech_norm,
            cc.cluster_id,
            ST_X(ST_Transform(cc.center_3857, 4326)) AS center_lon,
            ST_Y(ST_Transform(cc.center_3857, 4326)) AS center_lat,
            cc.center_3857,
            cc.obs_count,
            cc.dev_count,
            cc.active_days,
            COALESCE(r.radius_m, 0) AS radius_m,
            t.total_obs,
            t.total_dev_count,
            cc.obs_count::double precision / NULLIF(t.total_obs, 0) AS share_ratio
        FROM rebuild5._cell_centroid_cluster_centers cc
        JOIN rebuild5._cell_centroid_cell_totals t
          ON t.operator_code = cc.operator_code
         AND t.lac IS NOT DISTINCT FROM cc.lac
         AND t.bs_id IS NOT DISTINCT FROM cc.bs_id
         AND t.cell_id = cc.cell_id
         AND t.tech_norm IS NOT DISTINCT FROM cc.tech_norm
        LEFT JOIN rebuild5._cell_centroid_cluster_radius r
          ON r.operator_code = cc.operator_code
         AND r.lac IS NOT DISTINCT FROM cc.lac
         AND r.bs_id IS NOT DISTINCT FROM cc.bs_id
         AND r.cell_id = cc.cell_id
         AND r.tech_norm IS NOT DISTINCT FROM cc.tech_norm
         AND r.cluster_id = cc.cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_cluster_stats_key
        ON rebuild5._cell_centroid_cluster_stats (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_cluster_stats')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_filtered_clusters AS
        SELECT
            *,
            (
                obs_count >= GREATEST({min_cluster_obs}, CEIL(total_obs * {min_cluster_share})::integer)
                AND dev_count >= CASE
                    WHEN COALESCE(total_dev_count, 0) <= {centroid_cfg['stable_single_device_max_total_devs']}
                        THEN 1
                    ELSE {centroid_cfg['stable_min_devs']}
                END
                AND active_days >= {min_cluster_days}
            ) AS is_valid
        FROM rebuild5._cell_centroid_cluster_stats
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_filtered_clusters_key
        ON rebuild5._cell_centroid_filtered_clusters (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_filtered_clusters')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_ranked_clusters AS
        SELECT
            *,
            COUNT(*) FILTER (WHERE is_valid) OVER (
                PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
            ) AS valid_cluster_count,
            ROW_NUMBER() OVER (
                PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
                ORDER BY obs_count DESC, dev_count DESC, cluster_id
            ) AS cluster_rank
        FROM rebuild5._cell_centroid_filtered_clusters
        WHERE is_valid
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_ranked_clusters_key
        ON rebuild5._cell_centroid_ranked_clusters (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_ranked_clusters')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_valid_clusters AS
        SELECT *
        FROM rebuild5._cell_centroid_ranked_clusters
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_valid_clusters_key
        ON rebuild5._cell_centroid_valid_clusters (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_valid_clusters')
    execute(
        """
        INSERT INTO rebuild5.cell_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, tech_norm, cluster_id,
            is_primary, center_lon, center_lat, obs_count, dev_count, radius_m, share_ratio
        )
        SELECT
            %s::int,
            %s::text,
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            cluster_id,
            (cluster_rank = 1) AS is_primary,
            center_lon,
            center_lat,
            obs_count,
            dev_count,
            radius_m,
            share_ratio
        FROM rebuild5._cell_centroid_valid_clusters
        WHERE valid_cluster_count > 1
        """,
        (batch_id, snapshot_version),
    )
    execute(
        f"""
        INSERT INTO rebuild5.cell_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, tech_norm, cluster_id,
            is_primary, center_lon, center_lat, obs_count, dev_count, radius_m, share_ratio
        )
        SELECT
            {batch_id}::int,
            %s::text,
            d.operator_code,
            d.lac,
            d.bs_id,
            d.cell_id,
            d.tech_norm,
            d.cluster_id,
            d.is_primary,
            d.center_lon,
            d.center_lat,
            d.obs_count,
            d.dev_count,
            d.radius_m,
            d.share_ratio
        FROM rebuild5.cell_centroid_detail d
        JOIN rebuild5.trusted_cell_library t
          ON t.batch_id = {batch_id}
         AND t.operator_code = d.operator_code
         AND t.lac IS NOT DISTINCT FROM d.lac
         AND t.bs_id IS NOT DISTINCT FROM d.bs_id
         AND t.cell_id = d.cell_id
         AND t.tech_norm IS NOT DISTINCT FROM d.tech_norm
        LEFT JOIN rebuild5._cell_centroid_candidates c
          ON c.operator_code = d.operator_code
         AND c.lac IS NOT DISTINCT FROM d.lac
         AND c.bs_id IS NOT DISTINCT FROM d.bs_id
         AND c.cell_id = d.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM d.tech_norm
        WHERE d.batch_id = (
            SELECT COALESCE(MAX(batch_id), 0)
            FROM rebuild5.cell_centroid_detail
            WHERE batch_id < {batch_id}
        )
          AND c.cell_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM rebuild5.cell_centroid_detail curr
              WHERE curr.batch_id = {batch_id}
                AND curr.operator_code = d.operator_code
                AND curr.lac IS NOT DISTINCT FROM d.lac
                AND curr.bs_id IS NOT DISTINCT FROM d.bs_id
                AND curr.cell_id = d.cell_id
                AND curr.tech_norm IS NOT DISTINCT FROM d.tech_norm
                AND curr.cluster_id = d.cluster_id
          )
        """,
        (snapshot_version,),
    )
    execute('ANALYZE rebuild5.cell_centroid_detail')
    execute(
        """
        UPDATE rebuild5.trusted_cell_library AS t
        SET center_lon = d.center_lon,
            center_lat = d.center_lat
        FROM rebuild5._cell_centroid_valid_clusters d
        WHERE t.batch_id = %s
          AND d.cluster_rank = 1
          AND d.operator_code = t.operator_code
          AND d.lac IS NOT DISTINCT FROM t.lac
          AND d.bs_id IS NOT DISTINCT FROM t.bs_id
          AND d.cell_id = t.cell_id
          AND d.tech_norm IS NOT DISTINCT FROM t.tech_norm
        """,
        (batch_id,),
    )
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_daily_presence AS
        SELECT
            p.operator_code,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            p.obs_date,
            p.cluster_id,
            COUNT(*) AS obs_count
        FROM rebuild5._cell_centroid_labelled_points p
        JOIN rebuild5._cell_centroid_valid_clusters v
          ON v.operator_code = p.operator_code
         AND v.lac IS NOT DISTINCT FROM p.lac
         AND v.bs_id IS NOT DISTINCT FROM p.bs_id
         AND v.cell_id = p.cell_id
         AND v.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND v.cluster_id = p.cluster_id
        GROUP BY p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm, p.obs_date, p.cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_daily_presence_key
        ON rebuild5._cell_centroid_daily_presence (operator_code, lac, bs_id, cell_id, tech_norm, obs_date, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_daily_presence')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._cell_centroid_classification AS
        WITH cluster_counts AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                COUNT(*) AS stable_cluster_count
            FROM rebuild5._cell_centroid_valid_clusters
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        cluster_share_summary AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                MAX(share_ratio) FILTER (WHERE cluster_rank = 1) AS primary_share_ratio,
                MAX(share_ratio) FILTER (WHERE cluster_rank > 1) AS secondary_share_ratio
            FROM rebuild5._cell_centroid_valid_clusters
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        pair_distance AS (
            SELECT
                a.operator_code,
                a.lac,
                a.bs_id,
                a.cell_id,
                a.tech_norm,
                MAX(ST_Distance(a.center_3857, b.center_3857)) AS max_pair_distance_m
            FROM rebuild5._cell_centroid_valid_clusters a
            JOIN rebuild5._cell_centroid_valid_clusters b
              ON b.operator_code = a.operator_code
             AND b.lac IS NOT DISTINCT FROM a.lac
             AND b.bs_id IS NOT DISTINCT FROM a.bs_id
             AND b.cell_id = a.cell_id
             AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
             AND b.cluster_id > a.cluster_id
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        pair_overlap AS (
            SELECT
                a.operator_code,
                a.lac,
                a.bs_id,
                a.cell_id,
                a.tech_norm,
                MAX(overlap_days) AS max_overlap_days
            FROM (
                SELECT
                    a.operator_code,
                    a.lac,
                    a.bs_id,
                    a.cell_id,
                    a.tech_norm,
                    a.cluster_id AS cluster_a,
                    b.cluster_id AS cluster_b,
                    COUNT(*) AS overlap_days
                FROM rebuild5._cell_centroid_daily_presence a
                JOIN rebuild5._cell_centroid_daily_presence b
                  ON b.operator_code = a.operator_code
                 AND b.lac IS NOT DISTINCT FROM a.lac
                 AND b.bs_id IS NOT DISTINCT FROM a.bs_id
                 AND b.cell_id = a.cell_id
                 AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
                 AND b.obs_date = a.obs_date
                 AND b.cluster_id > a.cluster_id
                GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm, a.cluster_id, b.cluster_id
            ) a
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        daily_primary AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                obs_date,
                cluster_id,
                ROW_NUMBER() OVER (
                    PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm, obs_date
                    ORDER BY obs_count DESC, cluster_id
                ) AS day_rank
            FROM rebuild5._cell_centroid_daily_presence
        ),
        switch_summary AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                COUNT(*) FILTER (
                    WHERE prev_cluster_id IS NOT NULL
                      AND prev_cluster_id <> cluster_id
                ) AS cluster_switches
            FROM (
                SELECT
                    operator_code,
                    lac,
                    bs_id,
                    cell_id,
                    tech_norm,
                    obs_date,
                    cluster_id,
                    LAG(cluster_id) OVER (
                        PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
                        ORDER BY obs_date
                    ) AS prev_cluster_id
                FROM daily_primary
                WHERE day_rank = 1
            ) x
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        )
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            COALESCE(cc.stable_cluster_count, 0) AS stable_cluster_count,
            COALESCE(pd.max_pair_distance_m, 0) AS max_pair_distance_m,
            COALESCE(po.max_overlap_days, 0) AS max_overlap_days,
            COALESCE(sw.cluster_switches, 0) AS cluster_switches,
            COALESCE(cs.secondary_share_ratio, 0) AS secondary_share_ratio,
            CASE
                WHEN COALESCE(cc.stable_cluster_count, 0) >= {centroid_cfg['multi_cluster_min_cluster_count']}
                 AND COALESCE(cs.secondary_share_ratio, 0) >= {centroid_cfg['classification_min_secondary_share']}
                    THEN 'multi_cluster'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                 AND COALESCE(cs.secondary_share_ratio, 0) >= {centroid_cfg['classification_min_secondary_share']}
                 AND COALESCE(sw.cluster_switches, 0) >= {centroid_cfg['moving_min_switches']}
                 AND COALESCE(po.max_overlap_days, 0) >= {centroid_cfg['moving_min_overlap_days']}
                    THEN 'moving'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                 AND COALESCE(cs.secondary_share_ratio, 0) >= {centroid_cfg['classification_min_secondary_share']}
                 AND COALESCE(pd.max_pair_distance_m, 0) >= {centroid_cfg['migration_min_distance_m']}
                 AND COALESCE(po.max_overlap_days, 0) <= {centroid_cfg['migration_max_overlap_days']}
                    THEN 'migration'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                 AND COALESCE(cs.secondary_share_ratio, 0) >= {centroid_cfg['classification_min_secondary_share']}
                 AND COALESCE(pd.max_pair_distance_m, 0) >= {centroid_cfg['dual_cluster_min_distance_m']}
                    THEN 'dual_cluster'
                ELSE NULL
            END AS centroid_pattern
        FROM rebuild5._cell_centroid_candidates c
        LEFT JOIN cluster_counts cc
          ON cc.operator_code = c.operator_code
         AND cc.lac IS NOT DISTINCT FROM c.lac
         AND cc.bs_id IS NOT DISTINCT FROM c.bs_id
         AND cc.cell_id = c.cell_id
         AND cc.tech_norm IS NOT DISTINCT FROM c.tech_norm
        LEFT JOIN pair_distance pd
          ON pd.operator_code = c.operator_code
         AND pd.lac IS NOT DISTINCT FROM c.lac
         AND pd.bs_id IS NOT DISTINCT FROM c.bs_id
         AND pd.cell_id = c.cell_id
         AND pd.tech_norm IS NOT DISTINCT FROM c.tech_norm
        LEFT JOIN pair_overlap po
          ON po.operator_code = c.operator_code
         AND po.lac IS NOT DISTINCT FROM c.lac
         AND po.bs_id IS NOT DISTINCT FROM c.bs_id
         AND po.cell_id = c.cell_id
         AND po.tech_norm IS NOT DISTINCT FROM c.tech_norm
        LEFT JOIN switch_summary sw
          ON sw.operator_code = c.operator_code
         AND sw.lac IS NOT DISTINCT FROM c.lac
         AND sw.bs_id IS NOT DISTINCT FROM c.bs_id
         AND sw.cell_id = c.cell_id
         AND sw.tech_norm IS NOT DISTINCT FROM c.tech_norm
        LEFT JOIN cluster_share_summary cs
          ON cs.operator_code = c.operator_code
         AND cs.lac IS NOT DISTINCT FROM c.lac
         AND cs.bs_id IS NOT DISTINCT FROM c.bs_id
         AND cs.cell_id = c.cell_id
         AND cs.tech_norm IS NOT DISTINCT FROM c.tech_norm
        """
    )
    execute(
        """
        CREATE INDEX idx_cell_centroid_classification_key
        ON rebuild5._cell_centroid_classification (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._cell_centroid_classification')
    execute(
        """
        UPDATE rebuild5.trusted_cell_library AS t
        SET is_multi_centroid = COALESCE(c.centroid_pattern IS NOT NULL, FALSE),
            is_dynamic = COALESCE(c.centroid_pattern = 'moving', FALSE),
            centroid_pattern = c.centroid_pattern,
            drift_pattern = CASE
                WHEN c.centroid_pattern = 'migration' THEN 'migration'
                ELSE t.drift_pattern
            END
        FROM rebuild5._cell_centroid_classification c
        WHERE t.batch_id = %s
          AND c.operator_code = t.operator_code
          AND c.lac IS NOT DISTINCT FROM t.lac
          AND c.bs_id IS NOT DISTINCT FROM t.bs_id
          AND c.cell_id = t.cell_id
          AND c.tech_norm IS NOT DISTINCT FROM t.tech_norm
        """,
        (batch_id,),
    )
    for table_name in reversed(stage_tables):
        execute(f'DROP TABLE IF EXISTS {table_name}')


# ---------------------------------------------------------------------------
# BS library
# ---------------------------------------------------------------------------


def _execute_with_session_settings(
    *,
    session_setup_sqls: list[str],
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in session_setup_sqls:
                cur.execute(stmt)
            cur.execute(sql, params)
            for stmt in reversed(session_setup_sqls):
                if stmt.upper().startswith('SET '):
                    cur.execute(f"RESET {stmt.split()[1]}")

def publish_bs_library(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    snapshot_version_prev: str,
    antitoxin: dict[str, float],
) -> None:
    """
    BS 聚合逻辑（方案 BS-LAC-v1）：

    cell 三分类：
      - 正常 cell = drift_pattern IN ('stable','large_coverage','oversize_single')
      - 异常 cell = drift_pattern IN ('collision','dynamic','dual_cluster','migration','uncertain')
      - insufficient cell = drift_pattern = 'insufficient'

    BS 派生规则：
      - 质心/覆盖半径 只用"正常 cell"计算；全异常时退化用异常 cell 的 median（占位，实际极少）
      - classification:
         * normal_cells > 0 → 'normal'（有任何正常 cell 即正常 BS）
         * 全 insufficient → 'insufficient'
         * 全异常同类 → 'collision_bs' / 'dynamic_bs' / 'dual_cluster_bs' / 'migration_bs' / 'uncertain_bs'
         * 全异常多类 → 'anomaly'
    """
    thresholds = flatten_profile_thresholds(load_profile_params())
    execute('DELETE FROM rebuild5.trusted_bs_library WHERE batch_id = %s', (batch_id,))
    _execute_with_session_settings(
        session_setup_sqls=['SET enable_nestloop = off'],
        sql=f"""
        INSERT INTO rebuild5.trusted_bs_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            anchor_eligible, baseline_eligible,
            total_cells, qualified_cells, excellent_cells,
            normal_cells, anomaly_cells, insufficient_cells,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade, anomaly_cell_ratio,
            is_multi_centroid, window_active_cell_count
        )
        WITH cell_agg AS (
            SELECT
                operator_code, lac, bs_id,
                MAX(operator_cn) AS operator_cn,
                COUNT(*) AS total_cells,
                COUNT(*) FILTER (WHERE lifecycle_state IN ('qualified', 'excellent')) AS qualified_cells,
                COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_cells,
                COUNT(*) FILTER (WHERE lifecycle_state = 'retired') AS retired_cells,
                COUNT(*) FILTER (WHERE lifecycle_state IN ('dormant', 'retired')) AS inactive_cells,
                -- 三分类：正常 / 异常 / 数据不足
                COUNT(*) FILTER (WHERE drift_pattern IN ('stable','large_coverage','oversize_single')) AS normal_cells,
                COUNT(*) FILTER (WHERE drift_pattern IN ('collision','dynamic','dual_cluster','migration','uncertain')) AS anomaly_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'insufficient') AS insufficient_cells,
                -- 异常子类（用于 classification 判定"全异常同类"）
                COUNT(*) FILTER (WHERE drift_pattern = 'collision') AS collision_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'dynamic') AS dynamic_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'dual_cluster') AS dual_cluster_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'migration') AS migration_cells,
                COUNT(*) FILTER (WHERE drift_pattern = 'uncertain') AS uncertain_cells,
                -- 多质心统计（保留向后兼容）
                COUNT(*) FILTER (WHERE is_multi_centroid) AS multi_centroid_cells,
                BOOL_OR(anchor_eligible) AS anchor_eligible,
                BOOL_OR(baseline_eligible) AS baseline_eligible,
                COUNT(*) FILTER (WHERE window_obs_count > 0) AS active_cell_count
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = %s
            GROUP BY operator_code, lac, bs_id
        ),
        bs_center AS (
            SELECT
                operator_code, lac, bs_id,
                -- 首选：正常 cell 的中位数
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon)
                    FILTER (WHERE drift_pattern IN ('stable','large_coverage','oversize_single'))
                    AS center_lon_normal,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat)
                    FILTER (WHERE drift_pattern IN ('stable','large_coverage','oversize_single'))
                    AS center_lat_normal,
                -- 备选：所有非 insufficient cell（全异常 BS 时使用）
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon)
                    FILTER (WHERE drift_pattern IS NOT NULL AND drift_pattern != 'insufficient')
                    AS center_lon_any,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat)
                    FILTER (WHERE drift_pattern IS NOT NULL AND drift_pattern != 'insufficient')
                    AS center_lat_any
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = %s
              AND center_lon IS NOT NULL AND center_lat IS NOT NULL
            GROUP BY operator_code, lac, bs_id
        ),
        bs_dist AS (
            -- 只用正常 cell 到 BS 质心的距离；若 BS 无正常 cell 则距离为 NULL
            SELECT
                t.operator_code, t.lac, t.bs_id,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                    SQRT(POWER((t.center_lon - COALESCE(b.center_lon_normal, b.center_lon_any)) * 85300, 2)
                       + POWER((t.center_lat - COALESCE(b.center_lat_normal, b.center_lat_any)) * 111000, 2))
                ) AS gps_p50_dist_m,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                    SQRT(POWER((t.center_lon - COALESCE(b.center_lon_normal, b.center_lon_any)) * 85300, 2)
                       + POWER((t.center_lat - COALESCE(b.center_lat_normal, b.center_lat_any)) * 111000, 2))
                ) AS gps_p90_dist_m
            FROM rebuild5.trusted_cell_library t
            JOIN bs_center b
              ON b.operator_code = t.operator_code AND b.lac = t.lac AND b.bs_id = t.bs_id
            WHERE t.batch_id = %s
              AND t.center_lon IS NOT NULL AND t.center_lat IS NOT NULL
              AND t.drift_pattern IN ('stable','large_coverage','oversize_single')
              AND COALESCE(b.center_lon_normal, b.center_lon_any) IS NOT NULL
            GROUP BY t.operator_code, t.lac, t.bs_id
        )
        SELECT
            %s::int, %s::text, %s::text, %s::text, %s::text, NOW(),
            c.operator_code, c.operator_cn, c.lac, c.bs_id,
            CASE
                WHEN c.excellent_cells >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN c.qualified_cells >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'qualified'
                WHEN c.total_cells > 0 AND c.total_cells = COALESCE(c.retired_cells, 0) THEN 'retired'
                WHEN c.total_cells > 0 AND c.total_cells = COALESCE(c.inactive_cells, 0) THEN 'dormant'
                ELSE 'observing'
            END,
            c.anchor_eligible,
            c.baseline_eligible,
            c.total_cells,
            c.qualified_cells,
            c.excellent_cells,
            c.normal_cells,
            c.anomaly_cells,
            c.insufficient_cells,
            -- BS 质心：正常 cell 优先，全异常时退化
            COALESCE(bc.center_lon_normal, bc.center_lon_any),
            COALESCE(bc.center_lat_normal, bc.center_lat_any),
            -- 覆盖半径：只基于正常 cell；全异常 BS 的 dist 为 NULL
            bd.gps_p50_dist_m,
            bd.gps_p90_dist_m,
            -- classification（BS-LAC-v1 新规则）：
            CASE
                WHEN c.normal_cells > 0 THEN 'normal'
                WHEN c.anomaly_cells = 0 THEN 'insufficient'
                -- 全异常 BS，判断是否同一异常类型
                WHEN c.collision_cells = c.anomaly_cells THEN 'collision_bs'
                WHEN c.dynamic_cells = c.anomaly_cells THEN 'dynamic_bs'
                WHEN c.dual_cluster_cells = c.anomaly_cells THEN 'dual_cluster_bs'
                WHEN c.migration_cells = c.anomaly_cells THEN 'migration_bs'
                WHEN c.uncertain_cells = c.anomaly_cells THEN 'uncertain_bs'
                ELSE 'anomaly'
            END,
            -- position_grade：BS 不再独立评级，按 lifecycle 映射（向后兼容保留字段）
            CASE
                WHEN c.excellent_cells >= {thresholds['bs_excellent_min_excellent_cells']} THEN 'excellent'
                WHEN c.qualified_cells >= {thresholds['bs_qualified_min_qualified_cells']} THEN 'good'
                ELSE 'qualified'
            END,
            -- anomaly_cell_ratio：异常 cell 占比（观察字段）
            COALESCE(c.anomaly_cells, 0)::double precision / NULLIF(c.total_cells, 0),
            -- is_multi_centroid (BS level)：任一 cell is_multi_centroid 即 true（向后兼容）
            (COALESCE(c.multi_centroid_cells, 0) > 0),
            COALESCE(c.active_cell_count, 0)
        FROM cell_agg c
        LEFT JOIN bs_center bc
          ON bc.operator_code = c.operator_code AND bc.lac = c.lac AND bc.bs_id = c.bs_id
        LEFT JOIN bs_dist bd
          ON bd.operator_code = c.operator_code AND bd.lac = c.lac AND bd.bs_id = c.bs_id
        """,
        params=(
            batch_id, batch_id, batch_id,
            batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id,
        ),
    )


# ---------------------------------------------------------------------------
# BS centroid detail
# ---------------------------------------------------------------------------

def publish_bs_centroid_detail(
    *,
    batch_id: int,
    snapshot_version: str,
    large_spread_threshold_m: float | None = None,
) -> None:
    thresholds = flatten_antitoxin_thresholds(load_antitoxin_params())
    large_spread_threshold_m = (
        float(large_spread_threshold_m)
        if large_spread_threshold_m is not None
        else thresholds['bs_max_cell_to_bs_distance_m']
    )
    execute('DELETE FROM rebuild5.bs_centroid_detail WHERE batch_id = %s', (batch_id,))
    execute(
        f"""
        WITH candidates AS (
            SELECT
                batch_id,
                operator_code,
                lac,
                bs_id,
                center_lon AS ref_lon,
                center_lat AS ref_lat
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = %s
              AND center_lon IS NOT NULL
              AND center_lat IS NOT NULL
              AND classification IN ('large_spread', 'multi_centroid', 'dynamic_bs')
        ),
        cell_points AS (
            SELECT
                c.operator_code,
                c.lac,
                c.bs_id,
                t.center_lon,
                t.center_lat,
                COALESCE(t.window_obs_count, 0) AS obs_count,
                SQRT(
                    POWER((t.center_lon - c.ref_lon) * 85300, 2)
                  + POWER((t.center_lat - c.ref_lat) * 111000, 2)
                ) AS dist_to_ref_m
            FROM candidates c
            JOIN rebuild5.trusted_cell_library t
              ON t.batch_id = c.batch_id
             AND t.operator_code = c.operator_code
             AND t.lac = c.lac
             AND t.bs_id = c.bs_id
            WHERE t.center_lon IS NOT NULL
              AND t.center_lat IS NOT NULL
        ),
        labelled AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                center_lon,
                center_lat,
                obs_count,
                CASE
                    WHEN dist_to_ref_m >= {large_spread_threshold_m} THEN 2
                    ELSE 1
                END AS cluster_id
            FROM cell_points
        ),
        agg AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cluster_id,
                AVG(center_lon) AS center_lon,
                AVG(center_lat) AS center_lat,
                COUNT(*) AS cell_count,
                SUM(obs_count) AS weighted_obs
            FROM labelled
            GROUP BY operator_code, lac, bs_id, cluster_id
        ),
        ranked AS (
            SELECT
                *,
                COUNT(*) OVER (PARTITION BY operator_code, lac, bs_id) AS cluster_count,
                SUM(cell_count) OVER (PARTITION BY operator_code, lac, bs_id) AS total_cells,
                ROW_NUMBER() OVER (
                    PARTITION BY operator_code, lac, bs_id
                    ORDER BY weighted_obs DESC, cell_count DESC, cluster_id
                ) AS cluster_rank
            FROM agg
        )
        INSERT INTO rebuild5.bs_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cluster_id,
            is_primary, center_lon, center_lat, cell_count, share_ratio
        )
        SELECT
            %s::int,
            %s::text,
            operator_code,
            lac,
            bs_id,
            cluster_id,
            (cluster_rank = 1) AS is_primary,
            center_lon,
            center_lat,
            cell_count,
            cell_count::double precision / NULLIF(total_cells, 0) AS share_ratio
        FROM ranked
        WHERE cluster_count > 1
        """,
        (batch_id, batch_id, snapshot_version),
    )
    execute(
        """
        UPDATE rebuild5.trusted_bs_library AS b
        SET is_multi_centroid = TRUE,
            classification = 'multi_centroid'
        FROM (
            SELECT DISTINCT operator_code, lac, bs_id
            FROM rebuild5.bs_centroid_detail
            WHERE batch_id = %s
        ) d
        WHERE b.batch_id = %s
          AND d.operator_code = b.operator_code
          AND d.lac = b.lac
          AND d.bs_id = b.bs_id
        """,
        (batch_id, batch_id),
    )


# ---------------------------------------------------------------------------
# LAC library
# ---------------------------------------------------------------------------

def publish_lac_library(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    snapshot_version_prev: str,
) -> None:
    """
    LAC 聚合逻辑（方案 BS-LAC-v1）：

    原则：LAC 是纯观察层，没有品质分级。
      - 质心 / 面积 只基于"正常 BS"（classification='normal'）
      - 正常 BS 超过 1000 → 随机取 1000 个参与质心/面积计算（偏差无所谓，减算力）
      - lifecycle_state 简化为 active / dormant / retired

    保留旧字段（qualified_bs / excellent_bs / qualified_bs_ratio / boundary_stability_score / trend）
    向后兼容：仍计算并填入，但不再参与 lifecycle 判定。
    """
    thresholds = flatten_profile_thresholds(load_profile_params())
    execute('DELETE FROM rebuild5.trusted_lac_library WHERE batch_id = %s', (batch_id,))
    execute(
        f"""
        INSERT INTO rebuild5.trusted_lac_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, lifecycle_state,
            anchor_eligible, baseline_eligible,
            total_bs, qualified_bs, excellent_bs, qualified_bs_ratio,
            normal_bs, anomaly_bs, insufficient_bs,
            center_lon, center_lat,
            area_km2, anomaly_bs_ratio,
            boundary_stability_score, active_bs_count, retired_bs_count,
            trend
        )
        WITH bs_agg AS (
            SELECT
                operator_code, lac,
                MAX(operator_cn) AS operator_cn,
                COUNT(*) AS total_bs,
                COUNT(*) FILTER (WHERE lifecycle_state IN ('qualified', 'excellent')) AS qualified_bs,
                COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_bs,
                COUNT(*) FILTER (WHERE lifecycle_state = 'dormant' OR lifecycle_state = 'retired') AS retired_bs,
                -- 三分类 BS
                COUNT(*) FILTER (WHERE classification = 'normal') AS normal_bs,
                COUNT(*) FILTER (WHERE classification IN ('collision_bs','dynamic_bs','dual_cluster_bs','migration_bs','uncertain_bs','anomaly')) AS anomaly_bs,
                COUNT(*) FILTER (WHERE classification = 'insufficient') AS insufficient_bs,
                BOOL_OR(anchor_eligible) AS anchor_eligible,
                BOOL_OR(baseline_eligible) AS baseline_eligible,
                COUNT(*) FILTER (WHERE window_active_cell_count > 0) AS active_bs
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = %s
            GROUP BY operator_code, lac
        ),
        -- 正常 BS 采样（每 LAC 上限 1000，超出随机取）
        normal_bs_sample AS (
            SELECT operator_code, lac, bs_id, center_lon, center_lat
            FROM (
                SELECT operator_code, lac, bs_id, center_lon, center_lat,
                       ROW_NUMBER() OVER (PARTITION BY operator_code, lac ORDER BY random()) AS rn
                FROM rebuild5.trusted_bs_library
                WHERE batch_id = %s
                  AND classification = 'normal'
                  AND center_lon IS NOT NULL AND center_lat IS NOT NULL
            ) s
            WHERE rn <= 1000
        ),
        lac_geo AS (
            -- 质心与面积：只基于正常 BS（采样后）
            SELECT
                operator_code, lac,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS center_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS center_lat,
                CASE WHEN COUNT(*) < 2 THEN NULL
                     ELSE ((MAX(center_lon) - MIN(center_lon)) * 85.3)
                        * ((MAX(center_lat) - MIN(center_lat)) * 111.0)
                END AS area_km2
            FROM normal_bs_sample
            GROUP BY operator_code, lac
        ),
        prev_lac AS (
            SELECT operator_code, lac, qualified_bs_ratio, area_km2 AS prev_area_km2
            FROM rebuild5.trusted_lac_library
            WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0)
                              FROM rebuild5.trusted_lac_library
                              WHERE batch_id < %s)
        )
        SELECT
            %s::int, %s::text, %s::text, %s::text, %s::text, NOW(),
            ba.operator_code, ba.operator_cn, ba.lac,
            -- lifecycle_state 简化：active / dormant / retired（LAC 没有品质分级）
            CASE
                WHEN ba.total_bs > 0 AND ba.total_bs = COALESCE(ba.retired_bs, 0) THEN 'retired'
                WHEN COALESCE(ba.active_bs, 0) = 0 THEN 'dormant'
                ELSE 'active'
            END,
            ba.anchor_eligible,
            ba.baseline_eligible,
            ba.total_bs,
            ba.qualified_bs,
            ba.excellent_bs,
            COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0),
            ba.normal_bs,
            ba.anomaly_bs,
            ba.insufficient_bs,
            lg.center_lon,
            lg.center_lat,
            COALESCE(lg.area_km2, 0),
            -- anomaly_bs_ratio: 异常 BS 占比（基于 total_bs）
            COALESCE(ba.anomaly_bs::double precision / NULLIF(ba.total_bs, 0), 0),
            -- boundary_stability_score（保留向后兼容）
            CASE
                WHEN p.prev_area_km2 IS NULL OR p.prev_area_km2 = 0 THEN 1.0
                WHEN lg.area_km2 IS NULL THEN 1.0
                ELSE GREATEST(0, 1.0 - ABS(lg.area_km2 - p.prev_area_km2)
                     / GREATEST(p.prev_area_km2, 0.01))
            END,
            COALESCE(ba.active_bs, 0),
            COALESCE(ba.retired_bs, 0),
            -- trend（保留向后兼容）
            CASE
                WHEN p.qualified_bs_ratio IS NULL THEN 'stable'
                WHEN COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0)
                     - p.qualified_bs_ratio >= 0.02 THEN 'improving'
                WHEN p.qualified_bs_ratio
                     - COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0) >= 0.02
                    THEN 'degrading'
                ELSE 'stable'
            END
        FROM bs_agg ba
        LEFT JOIN lac_geo lg ON lg.operator_code = ba.operator_code AND lg.lac = ba.lac
        LEFT JOIN prev_lac p ON p.operator_code = ba.operator_code AND p.lac = ba.lac
        """,
        (batch_id, batch_id, batch_id,
         batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id),
    )
