"""Step 5 label engine for multi-centroid and coverage-shape labels."""
from __future__ import annotations

from typing import Any

from ..core.database import execute
from ..profile.logic import (
    load_antitoxin_params,
    load_label_rules_params,
    load_multi_centroid_v2_params,
)


def _candidate_trigger_config(params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = params or load_antitoxin_params()
    cfg = payload.get('postgis_centroid', {})
    return {
        'candidate_min_window_obs': int(cfg.get('candidate_min_window_obs', 5)),
        'candidate_min_active_days': int(cfg.get('candidate_min_active_days', 2)),
        'candidate_min_p90_m': float(cfg.get('candidate_min_p90_m', 800)),
        'candidate_min_raw_p90_m': float(cfg.get('candidate_min_raw_p90_m', cfg.get('candidate_min_p90_m', 800))),
        'candidate_min_max_spread_m': float(cfg.get('candidate_min_max_spread_m', 2200)),
        'candidate_min_outlier_ratio': float(cfg.get('candidate_min_outlier_ratio', 0.15)),
        'candidate_drift_patterns': tuple(
            cfg.get('candidate_drift_patterns', ['large_coverage', 'migration', 'collision', 'moderate_drift'])
        ),
    }


def run_label_engine(*, batch_id: int, snapshot_version: str) -> None:
    """Reclassify Step5 cell labels using full-window raw_gps-only cluster features."""
    antitoxin = load_antitoxin_params()
    label_rules = load_label_rules_params(antitoxin)
    cluster_cfg = load_multi_centroid_v2_params(antitoxin)
    trigger_cfg = _candidate_trigger_config(antitoxin)
    drift_patterns_sql = ', '.join(f"'{value}'" for value in trigger_cfg['candidate_drift_patterns'])

    stage_tables = (
        'rebuild5._label_candidates',
        'rebuild5._label_input_points',
        'rebuild5._label_cell_stats',
        'rebuild5._label_clustered_points',
        'rebuild5._label_clusters',
        'rebuild5._label_cluster_radius',
        'rebuild5._label_ranked_clusters',
        'rebuild5._label_cell_kstats',
        'rebuild5._label_k2_features',
        'rebuild5._label_kmany_features',
        'rebuild5._label_results_stage',
    )
    for table_name in stage_tables:
        execute(f'DROP TABLE IF EXISTS {table_name}')

    execute('DELETE FROM rebuild5.cell_centroid_detail WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rebuild5.label_results WHERE batch_id = %s', (batch_id,))

    # 方案 7.4：候选池 = p90 >= 1300m 的 cell（其余 cell 按 p90<1300m → stable 直接判定）
    # 大幅缩小候选池（原 27 万 → 约 7 千），避免 DBSCAN/聚类阶段对紧凑小 cell 白跑
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_candidates AS
        SELECT
            t.batch_id,
            t.operator_code,
            t.lac,
            t.bs_id,
            t.cell_id,
            t.tech_norm
        FROM rebuild5.trusted_cell_library t
        WHERE t.batch_id = %s
          AND COALESCE(t.p90_radius_m, 0) >= {cluster_cfg['multi_centroid_entry_p90_m']}
        """,
        (batch_id,),
    )
    execute(
        """
        CREATE INDEX idx_label_candidates_key
        ON rebuild5._label_candidates (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_candidates')

    raw_gps_filter = "AND e.gps_fill_source_final = 'raw_gps'" if cluster_cfg['only_raw_gps'] else ''
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_input_points AS
        WITH source_meta AS (
            SELECT batch_id, source_row_uid, gps_fill_source_final
            FROM rebuild5.enriched_records
            UNION ALL
            SELECT batch_id, source_row_uid, gps_fill_source_final
            FROM rebuild5.snapshot_seed_records
        )
        SELECT DISTINCT ON (
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            COALESCE(NULLIF(w.dev_id, ''), w.record_id),
            DATE(w.event_time_std)
        )
            {batch_id}::int AS batch_id,
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            COALESCE(NULLIF(w.dev_id, ''), w.record_id) AS dedup_dev_id,
            w.source_row_uid,
            DATE(w.event_time_std) AS obs_date,
            w.event_time_std,
            w.lon_final,
            w.lat_final
        FROM rebuild5._label_candidates c
        JOIN rebuild5.cell_sliding_window w
          ON w.operator_code = c.operator_code
         AND w.lac IS NOT DISTINCT FROM c.lac
         AND w.bs_id IS NOT DISTINCT FROM c.bs_id
         AND w.cell_id = c.cell_id
         AND w.tech_norm IS NOT DISTINCT FROM c.tech_norm
        JOIN source_meta e
          ON e.batch_id = w.batch_id
         AND e.source_row_uid = w.source_row_uid
        WHERE w.gps_valid IS TRUE
          AND w.lon_final IS NOT NULL
          AND w.lat_final IS NOT NULL
          AND w.event_time_std IS NOT NULL
          {raw_gps_filter}
        ORDER BY
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            COALESCE(NULLIF(w.dev_id, ''), w.record_id),
            DATE(w.event_time_std),
            w.event_time_std,
            w.record_id
        """
    )
    execute(
        """
        CREATE INDEX idx_label_input_points_key
        ON rebuild5._label_input_points (operator_code, lac, bs_id, cell_id, tech_norm, obs_date)
        """
    )
    execute('ANALYZE rebuild5._label_input_points')

    # 方案 7.4：计算 cell 级 dedup 统计，用于多质心层的稀疏保护
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._label_cell_stats AS
        SELECT
            operator_code, lac, bs_id, cell_id, tech_norm,
            COUNT(*) AS total_dedup_pts,
            COUNT(DISTINCT dedup_dev_id) AS dedup_dev_count,
            COUNT(DISTINCT obs_date) AS dedup_day_count
        FROM rebuild5._label_input_points
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute(
        """
        CREATE INDEX idx_label_cell_stats_key
        ON rebuild5._label_cell_stats (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_cell_stats')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_clustered_points AS
        SELECT
            p.batch_id,
            p.operator_code,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            p.dedup_dev_id,
            p.source_row_uid,
            p.obs_date,
            p.event_time_std,
            p.lon_final,
            p.lat_final,
            ST_ClusterDBSCAN(
                ST_SetSRID(
                    ST_MakePoint(
                        p.lon_final * {cluster_cfg['coord_scale_lon']},
                        p.lat_final * {cluster_cfg['coord_scale_lat']}
                    ),
                    3857
                ),
                eps => {cluster_cfg['dbscan_eps_m']},
                minpoints => {cluster_cfg['dbscan_min_points']}
            ) OVER (
                PARTITION BY p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm
            ) AS cluster_id
        FROM rebuild5._label_input_points p
        """
    )
    execute(
        """
        CREATE INDEX idx_label_clustered_points_key
        ON rebuild5._label_clustered_points (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id, obs_date)
        """
    )
    execute('ANALYZE rebuild5._label_clustered_points')

    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._label_clusters AS
        SELECT
            batch_id,
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            cluster_id,
            COUNT(*) AS dev_day_pts,
            COUNT(DISTINCT dedup_dev_id) AS dev_count,
            COUNT(DISTINCT obs_date) AS day_count,
            MIN(obs_date) AS first_day,
            MAX(obs_date) AS last_day,
            (MAX(obs_date) - MIN(obs_date) + 1) AS dwell_days,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) AS center_lat,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM event_time_std)) AS mid_time_epoch
        FROM rebuild5._label_clustered_points
        WHERE cluster_id IS NOT NULL
        GROUP BY batch_id, operator_code, lac, bs_id, cell_id, tech_norm, cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_label_clusters_key
        ON rebuild5._label_clusters (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._label_clusters')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_cluster_radius AS
        SELECT
            p.operator_code,
            p.lac,
            p.bs_id,
            p.cell_id,
            p.tech_norm,
            p.cluster_id,
            PERCENTILE_CONT(0.9) WITHIN GROUP (
                ORDER BY SQRT(
                    POWER((p.lon_final - c.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
                  + POWER((p.lat_final - c.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
                )
            ) AS radius_m
        FROM rebuild5._label_clustered_points p
        JOIN rebuild5._label_clusters c
          ON c.operator_code = p.operator_code
         AND c.lac IS NOT DISTINCT FROM p.lac
         AND c.bs_id IS NOT DISTINCT FROM p.bs_id
         AND c.cell_id = p.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND c.cluster_id = p.cluster_id
        WHERE p.cluster_id IS NOT NULL
        GROUP BY p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm, p.cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_label_cluster_radius_key
        ON rebuild5._label_cluster_radius (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._label_cluster_radius')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_ranked_clusters AS
        WITH valid_clusters AS (
            SELECT
                c.batch_id,
                c.operator_code,
                c.lac,
                c.bs_id,
                c.cell_id,
                c.tech_norm,
                c.cluster_id,
                c.dev_day_pts,
                c.dev_count,
                c.day_count,
                c.first_day,
                c.last_day,
                c.dwell_days,
                c.center_lon,
                c.center_lat,
                c.mid_time_epoch,
                r.radius_m
            FROM rebuild5._label_clusters c
            LEFT JOIN rebuild5._label_cluster_radius r
              ON r.operator_code = c.operator_code
             AND r.lac IS NOT DISTINCT FROM c.lac
             AND r.bs_id IS NOT DISTINCT FROM c.bs_id
             AND r.cell_id = c.cell_id
             AND r.tech_norm IS NOT DISTINCT FROM c.tech_norm
             AND r.cluster_id = c.cluster_id
            WHERE c.dev_day_pts >= {cluster_cfg['min_cluster_dev_day_pts']}
        )
        SELECT
            v.*,
            COUNT(*) OVER (
                PARTITION BY v.operator_code, v.lac, v.bs_id, v.cell_id, v.tech_norm
            ) AS valid_cluster_count,
            SUM(v.dev_day_pts) OVER (
                PARTITION BY v.operator_code, v.lac, v.bs_id, v.cell_id, v.tech_norm
            ) AS total_valid_pts,
            ROW_NUMBER() OVER (
                PARTITION BY v.operator_code, v.lac, v.bs_id, v.cell_id, v.tech_norm
                ORDER BY v.dev_day_pts DESC, v.day_count DESC, v.cluster_id
            ) AS cluster_rank,
            v.dev_day_pts::double precision / NULLIF(
                SUM(v.dev_day_pts) OVER (
                    PARTITION BY v.operator_code, v.lac, v.bs_id, v.cell_id, v.tech_norm
                ),
                0
            ) AS share_ratio
        FROM valid_clusters v
        """
    )
    execute(
        """
        CREATE INDEX idx_label_ranked_clusters_key
        ON rebuild5._label_ranked_clusters (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        """
    )
    execute('ANALYZE rebuild5._label_ranked_clusters')

    execute(
        """
        INSERT INTO rebuild5.cell_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, tech_norm,
            cluster_id, is_primary, center_lon, center_lat, obs_count, dev_count, radius_m, share_ratio
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
            dev_day_pts,
            dev_count,
            radius_m,
            share_ratio
        FROM rebuild5._label_ranked_clusters
        WHERE valid_cluster_count > 1
        """,
        (batch_id, snapshot_version),
    )
    execute('ANALYZE rebuild5.cell_centroid_detail')

    execute(
        """
        CREATE UNLOGGED TABLE rebuild5._label_cell_kstats AS
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            COUNT(*) AS k_raw,
            COUNT(*) FILTER (WHERE c.dev_day_pts >= %s) AS k_eff,
            COALESCE(SUM(c.dev_day_pts) FILTER (WHERE c.dev_day_pts >= %s), 0) AS total_valid_pts
        FROM rebuild5._label_clusters c
        GROUP BY c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm
        """,
        (cluster_cfg['min_cluster_dev_day_pts'], cluster_cfg['min_cluster_dev_day_pts']),
    )
    execute(
        """
        CREATE INDEX idx_label_cell_kstats_key
        ON rebuild5._label_cell_kstats (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_cell_kstats')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_k2_features AS
        WITH vc AS (
            SELECT c.*
            FROM rebuild5._label_ranked_clusters c
            JOIN rebuild5._label_cell_kstats k
              ON k.operator_code = c.operator_code
             AND k.lac IS NOT DISTINCT FROM c.lac
             AND k.bs_id IS NOT DISTINCT FROM c.bs_id
             AND k.cell_id = c.cell_id
             AND k.tech_norm IS NOT DISTINCT FROM c.tech_norm
            WHERE k.k_eff = 2
        )
        SELECT
            a.operator_code,
            a.lac,
            a.bs_id,
            a.cell_id,
            a.tech_norm,
            SQRT(
                POWER((a.center_lon - b.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
              + POWER((a.center_lat - b.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
            ) AS dist_m,
            GREATEST(
                0,
                LEAST(a.last_day, b.last_day) - GREATEST(a.first_day, b.first_day) + 1
            ) AS overlap_days,
            LEAST(a.day_count, b.day_count) AS min_day_cnt,
            CASE
                WHEN LEAST(a.day_count, b.day_count) > 0 THEN
                    GREATEST(
                        0,
                        LEAST(a.last_day, b.last_day) - GREATEST(a.first_day, b.first_day) + 1
                    )::double precision / LEAST(a.day_count, b.day_count)
                ELSE NULL::double precision
            END AS overlap_ratio,
            CASE
                WHEN a.first_day < b.first_day THEN b.day_count
                WHEN b.first_day < a.first_day THEN a.day_count
                ELSE LEAST(a.day_count, b.day_count)
            END AS post_day_cnt,
            CASE
                WHEN a.first_day < b.first_day THEN b.last_day = GREATEST(a.last_day, b.last_day)
                WHEN b.first_day < a.first_day THEN a.last_day = GREATEST(a.last_day, b.last_day)
                ELSE FALSE
            END AS no_comeback
        FROM vc a
        JOIN vc b
          ON b.operator_code = a.operator_code
         AND b.lac IS NOT DISTINCT FROM a.lac
         AND b.bs_id IS NOT DISTINCT FROM a.bs_id
         AND b.cell_id = a.cell_id
         AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
         AND b.cluster_id > a.cluster_id
        """
    )
    execute(
        """
        CREATE INDEX idx_label_k2_features_key
        ON rebuild5._label_k2_features (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_k2_features')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_kmany_features AS
        WITH vc AS (
            SELECT
                c.operator_code,
                c.lac,
                c.bs_id,
                c.cell_id,
                c.tech_norm,
                c.cluster_id,
                c.center_lon,
                c.center_lat,
                c.dwell_days,
                c.mid_time_epoch,
                ROW_NUMBER() OVER (
                    PARTITION BY c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm
                    ORDER BY c.mid_time_epoch, c.cluster_id
                ) AS time_rank
            FROM rebuild5._label_ranked_clusters c
            JOIN rebuild5._label_cell_kstats k
              ON k.operator_code = c.operator_code
             AND k.lac IS NOT DISTINCT FROM c.lac
             AND k.bs_id IS NOT DISTINCT FROM c.bs_id
             AND k.cell_id = c.cell_id
             AND k.tech_norm IS NOT DISTINCT FROM c.tech_norm
            WHERE k.k_eff >= 3
        ),
        span AS (
            SELECT
                a.operator_code,
                a.lac,
                a.bs_id,
                a.cell_id,
                a.tech_norm,
                MAX(
                    SQRT(
                        POWER((a.center_lon - b.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
                      + POWER((a.center_lat - b.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
                    )
                ) AS max_span_m
            FROM vc a
            JOIN vc b
              ON b.operator_code = a.operator_code
             AND b.lac IS NOT DISTINCT FROM a.lac
             AND b.bs_id IS NOT DISTINCT FROM a.bs_id
             AND b.cell_id = a.cell_id
             AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
             AND b.cluster_id > a.cluster_id
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        path AS (
            SELECT
                a.operator_code,
                a.lac,
                a.bs_id,
                a.cell_id,
                a.tech_norm,
                SUM(
                    SQRT(
                        POWER((a.center_lon - b.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
                      + POWER((a.center_lat - b.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
                    )
                ) AS total_path_m,
                STDDEV_SAMP(
                    SQRT(
                        POWER((a.center_lon - b.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
                      + POWER((a.center_lat - b.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
                    )
                ) / NULLIF(
                    AVG(
                        SQRT(
                            POWER((a.center_lon - b.center_lon) * {cluster_cfg['coord_scale_lon']}, 2)
                          + POWER((a.center_lat - b.center_lat) * {cluster_cfg['coord_scale_lat']}, 2)
                        )
                    ),
                    0
                ) AS distance_cv
            FROM vc a
            JOIN vc b
              ON b.operator_code = a.operator_code
             AND b.lac IS NOT DISTINCT FROM a.lac
             AND b.bs_id IS NOT DISTINCT FROM a.bs_id
             AND b.cell_id = a.cell_id
             AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
             AND b.time_rank = a.time_rank + 1
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        dwell AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                AVG(dwell_days)::double precision AS avg_dwell_days
            FROM vc
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        )
        SELECT
            d.operator_code,
            d.lac,
            d.bs_id,
            d.cell_id,
            d.tech_norm,
            COALESCE(s.max_span_m, 0) AS max_span_m,
            COALESCE(p.total_path_m, 0) AS total_path_m,
            p.distance_cv,
            d.avg_dwell_days
        FROM dwell d
        LEFT JOIN span s
          ON s.operator_code = d.operator_code
         AND s.lac IS NOT DISTINCT FROM d.lac
         AND s.bs_id IS NOT DISTINCT FROM d.bs_id
         AND s.cell_id = d.cell_id
         AND s.tech_norm IS NOT DISTINCT FROM d.tech_norm
        LEFT JOIN path p
          ON p.operator_code = d.operator_code
         AND p.lac IS NOT DISTINCT FROM d.lac
         AND p.bs_id IS NOT DISTINCT FROM d.bs_id
         AND p.cell_id = d.cell_id
         AND p.tech_norm IS NOT DISTINCT FROM d.tech_norm
        """
    )
    execute(
        """
        CREATE INDEX idx_label_kmany_features_key
        ON rebuild5._label_kmany_features (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_kmany_features')

    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5._label_results_stage AS
        SELECT
            %s::int AS batch_id,
            %s::text AS snapshot_version,
            t.operator_code,
            t.lac,
            t.bs_id,
            t.cell_id,
            t.tech_norm,
            (c.cell_id IS NOT NULL) AS candidate_hit,
            COALESCE(k.k_raw, 0) AS k_raw,
            COALESCE(k.k_eff, 0) AS k_eff,
            COALESCE(k.total_valid_pts, 0) AS total_valid_pts,
            t.p90_radius_m,
            k2.dist_m AS pair_dist_m,
            k2.overlap_ratio AS pair_overlap_ratio,
            k2.no_comeback AS pair_no_comeback,
            km.max_span_m,
            km.total_path_m,
            CASE
                WHEN km.total_path_m > 0 THEN km.max_span_m / km.total_path_m
                ELSE NULL::double precision
            END AS line_ratio,
            km.distance_cv,
            km.avg_dwell_days,
            -- 方案 7.4 标签判定路径
            CASE
                -- 规则 1：p90 < 1300m → stable
                --   Step 3 晋级已保证数据量支撑单簇，整体紧凑不做多质心分析
                WHEN t.p90_radius_m IS NOT NULL
                 AND t.p90_radius_m > 0
                 AND t.p90_radius_m < {cluster_cfg['multi_centroid_entry_p90_m']}
                    THEN 'stable'
                -- 无 p90 或极端边缘（中心缺失）
                WHEN t.center_lon IS NULL OR t.center_lat IS NULL
                  OR t.p90_radius_m IS NULL OR COALESCE(t.gps_valid_count, 0) = 0
                    THEN 'insufficient'
                -- 规则 2a：p90 >= 1300m 但多质心层数据稀疏
                WHEN COALESCE(cs.total_dedup_pts, 0) < {cluster_cfg['min_total_dedup_pts']}
                  OR COALESCE(cs.dedup_dev_count, 0) < {cluster_cfg['min_total_devs']}
                  OR COALESCE(cs.dedup_day_count, 0) < {cluster_cfg['min_total_active_days']}
                    THEN 'insufficient'
                -- 规则 2b：按 k_eff 判定
                WHEN COALESCE(k.k_eff, 0) = 0 THEN 'insufficient'
                WHEN k.k_eff = 1 AND t.p90_radius_m <= {label_rules['large_coverage_max_p90_m']}
                    THEN 'large_coverage'
                WHEN k.k_eff = 1 THEN 'oversize_single'
                -- 碰撞：双质心距离 > 100km 硬信号
                WHEN k.k_eff = 2
                 AND COALESCE(k2.dist_m, 0) >= {label_rules['collision_min_dist_m']}
                    THEN 'collision'
                WHEN k.k_eff = 2
                 AND COALESCE(k2.dist_m, 0) < {label_rules['dual_cluster_max_dist_m']}
                 AND COALESCE(k2.overlap_ratio, 0) >= {label_rules['dual_cluster_min_overlap_ratio']}
                    THEN 'dual_cluster'
                WHEN k.k_eff = 2
                 AND COALESCE(k2.dist_m, 0) < {label_rules['dual_cluster_max_dist_m']}
                 AND COALESCE(k2.overlap_ratio, 1) <= {label_rules['migration_max_overlap_ratio']}
                 AND COALESCE(k2.post_day_cnt, 0) >= {label_rules['migration_min_post_days']}
                 AND COALESCE(k2.no_comeback, FALSE)
                    THEN 'migration'
                WHEN k.k_eff = 2 THEN 'uncertain'
                WHEN k.k_eff >= 3
                 AND COALESCE(km.max_span_m, 0) > {label_rules['dynamic_min_span_m']}
                 AND COALESCE(
                     CASE
                         WHEN km.total_path_m > 0 THEN km.max_span_m / km.total_path_m
                         ELSE NULL::double precision
                     END,
                     0
                 ) > {label_rules['dynamic_min_line_ratio']}
                 AND COALESCE(km.distance_cv, 1e9) < {label_rules['dynamic_max_distance_cv']}
                 AND COALESCE(km.avg_dwell_days, 1e9) <= {label_rules['dynamic_max_avg_dwell_days']}
                    THEN 'dynamic'
                WHEN k.k_eff >= 3 THEN 'uncertain'
                ELSE 'insufficient'
            END AS label
        FROM rebuild5.trusted_cell_library t
        LEFT JOIN rebuild5._label_candidates c
          ON c.operator_code = t.operator_code
         AND c.lac IS NOT DISTINCT FROM t.lac
         AND c.bs_id IS NOT DISTINCT FROM t.bs_id
         AND c.cell_id = t.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM t.tech_norm
        LEFT JOIN rebuild5._label_cell_stats cs
          ON cs.operator_code = t.operator_code
         AND cs.lac IS NOT DISTINCT FROM t.lac
         AND cs.bs_id IS NOT DISTINCT FROM t.bs_id
         AND cs.cell_id = t.cell_id
         AND cs.tech_norm IS NOT DISTINCT FROM t.tech_norm
        LEFT JOIN rebuild5._label_cell_kstats k
          ON k.operator_code = t.operator_code
         AND k.lac IS NOT DISTINCT FROM t.lac
         AND k.bs_id IS NOT DISTINCT FROM t.bs_id
         AND k.cell_id = t.cell_id
         AND k.tech_norm IS NOT DISTINCT FROM t.tech_norm
        LEFT JOIN rebuild5._label_k2_features k2
          ON k2.operator_code = t.operator_code
         AND k2.lac IS NOT DISTINCT FROM t.lac
         AND k2.bs_id IS NOT DISTINCT FROM t.bs_id
         AND k2.cell_id = t.cell_id
         AND k2.tech_norm IS NOT DISTINCT FROM t.tech_norm
        LEFT JOIN rebuild5._label_kmany_features km
          ON km.operator_code = t.operator_code
         AND km.lac IS NOT DISTINCT FROM t.lac
         AND km.bs_id IS NOT DISTINCT FROM t.bs_id
         AND km.cell_id = t.cell_id
         AND km.tech_norm IS NOT DISTINCT FROM t.tech_norm
        WHERE t.batch_id = %s
        """,
        (batch_id, snapshot_version, batch_id),
    )
    execute(
        """
        CREATE INDEX idx_label_results_stage_key
        ON rebuild5._label_results_stage (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5._label_results_stage')

    execute(
        """
        INSERT INTO rebuild5.label_results (
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, tech_norm,
            candidate_hit, k_raw, k_eff, total_valid_pts, p90_radius_m,
            pair_dist_m, pair_overlap_ratio, pair_no_comeback,
            max_span_m, total_path_m, line_ratio, distance_cv, avg_dwell_days,
            label
        )
        SELECT
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, tech_norm,
            candidate_hit, k_raw, k_eff, total_valid_pts, p90_radius_m,
            pair_dist_m, pair_overlap_ratio, pair_no_comeback,
            max_span_m, total_path_m, line_ratio, distance_cv, avg_dwell_days,
            label
        FROM rebuild5._label_results_stage
        """
    )
    execute('ANALYZE rebuild5.label_results')

    execute(
        """
        UPDATE rebuild5.trusted_cell_library AS t
        SET drift_pattern = l.label,
            centroid_pattern = CASE
                WHEN l.label IN ('dual_cluster', 'migration') THEN l.label
                WHEN l.label IN ('dynamic', 'uncertain') THEN 'multi_cluster'
                ELSE NULL
            END,
            -- 严格语义：is_multi_centroid 只标 k_eff>=3（真·多质心），双质心用 drift_pattern='dual_cluster' 识别
            is_multi_centroid = (COALESCE(l.k_eff, 0) >= 3),
            is_dynamic = (l.label = 'dynamic'),
            -- collision 与标签联动：label_engine 判定优先于旧 collision.py 的 max_spread 口径
            is_collision = (l.label = 'collision')
        FROM rebuild5.label_results l
        WHERE t.batch_id = %s
          AND l.batch_id = %s
          AND l.operator_code = t.operator_code
          AND l.lac IS NOT DISTINCT FROM t.lac
          AND l.bs_id IS NOT DISTINCT FROM t.bs_id
          AND l.cell_id = t.cell_id
          AND l.tech_norm IS NOT DISTINCT FROM t.tech_norm
        """,
        (batch_id, batch_id),
    )

    for table_name in reversed(stage_tables):
        execute(f'DROP TABLE IF EXISTS {table_name}')
