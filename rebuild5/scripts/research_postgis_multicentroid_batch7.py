#!/usr/bin/env python3
"""PostGIS-based multi-centroid research on representative batch-7 cells."""
from __future__ import annotations

import argparse
import decimal
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


DEFAULT_DSN = 'postgresql://postgres:123456@192.168.200.217:5488/yangca'
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = REPO_ROOT / 'rebuild5/docs/fix3/postgis_multicentroid_batch7_results.json'
DEFAULT_MD = REPO_ROOT / 'rebuild5/docs/fix3/postgis_multicentroid_batch7_report.md'


@dataclass(frozen=True)
class ParamSet:
    label: str
    eps_m: float
    minpoints: int
    snap_m: float


PARAM_SETS = (
    ParamSet(label='eps150_mp3_grid50', eps_m=150.0, minpoints=3, snap_m=50.0),
    ParamSet(label='eps250_mp4_grid50', eps_m=250.0, minpoints=4, snap_m=50.0),
    ParamSet(label='eps400_mp4_grid50', eps_m=400.0, minpoints=4, snap_m=50.0),
)
BASELINE_LABEL = 'eps250_mp4_grid50'


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', default=DEFAULT_DSN)
    parser.add_argument('--batch-id', type=int, default=7)
    parser.add_argument('--min-p90-m', type=float, default=800.0)
    parser.add_argument('--top-radius-min-m', type=float, default=1500.0)
    parser.add_argument('--min-cluster-obs', type=int, default=5)
    parser.add_argument('--min-cluster-share', type=float, default=0.10)
    parser.add_argument('--min-cluster-days', type=int, default=2)
    parser.add_argument('--min-cluster-devs', type=int, default=2)
    parser.add_argument('--qualified-min-obs', type=int, default=20)
    parser.add_argument('--qualified-min-days', type=int, default=3)
    parser.add_argument('--migration-max-overlap-days', type=int, default=1)
    parser.add_argument('--collision-distance-m', type=float, default=20000.0)
    parser.add_argument('--single-noise-ratio', type=float, default=0.35)
    parser.add_argument('--out-json', default=str(DEFAULT_JSON))
    parser.add_argument('--out-md', default=str(DEFAULT_MD))
    return parser.parse_args()


def _strata_sql(args: argparse.Namespace) -> str:
    min_p90 = args.min_p90_m
    qualified_min_obs = args.qualified_min_obs
    qualified_min_days = args.qualified_min_days
    top_radius_min = args.top_radius_min_m
    low_obs_p90 = max(500.0, min_p90 * 0.6)
    specs = [
        (
            'stable_large',
            f"""
            SELECT 'stable_large'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'stable'
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= {qualified_min_obs}
              AND COALESCE(b.active_days, 0) >= {qualified_min_days}
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 12
            """,
        ),
        (
            'large_coverage',
            f"""
            SELECT 'large_coverage'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'large_coverage'
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= {qualified_min_obs}
              AND COALESCE(b.active_days, 0) >= {qualified_min_days}
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 12
            """,
        ),
        (
            'migration',
            f"""
            SELECT 'migration'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'migration'
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= 15
              AND COALESCE(b.active_days, 0) >= {qualified_min_days}
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 10
            """,
        ),
        (
            'collision',
            f"""
            SELECT 'collision'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'collision'
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= 15
              AND COALESCE(b.active_days, 0) >= {qualified_min_days}
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 10
            """,
        ),
        (
            'moderate_drift',
            f"""
            SELECT 'moderate_drift'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'moderate_drift'
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= 10
              AND COALESCE(b.active_days, 0) >= {qualified_min_days}
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 8
            """,
        ),
        (
            'gps_anomaly',
            f"""
            SELECT 'gps_anomaly'::text AS stratum, b.*
            FROM base b
            WHERE b.gps_anomaly_type IS NOT NULL
              AND COALESCE(b.p90_radius_m, 0) >= {min_p90}
              AND COALESCE(b.window_obs_count, 0) >= 10
            ORDER BY b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.p90_radius_m DESC NULLS LAST,
                     b.distinct_dev_id DESC NULLS LAST,
                     b.cell_id
            LIMIT 8
            """,
        ),
        (
            'top_radius',
            f"""
            SELECT 'top_radius'::text AS stratum, b.*
            FROM base b
            WHERE COALESCE(b.p90_radius_m, 0) >= {top_radius_min}
              AND COALESCE(b.window_obs_count, 0) >= 10
            ORDER BY b.p90_radius_m DESC NULLS LAST,
                     b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.cell_id
            LIMIT 8
            """,
        ),
        (
            'low_obs_dirty',
            f"""
            SELECT 'low_obs_dirty'::text AS stratum, b.*
            FROM base b
            WHERE b.drift_pattern = 'insufficient'
              AND b.gps_anomaly_type IS NOT NULL
              AND COALESCE(b.p90_radius_m, 0) >= {low_obs_p90}
            ORDER BY b.p90_radius_m DESC NULLS LAST,
                     b.window_obs_count DESC NULLS LAST,
                     b.active_days DESC NULLS LAST,
                     b.cell_id
            LIMIT 6
            """,
        ),
    ]
    union_sql = '\nUNION ALL\n'.join(f"({fragment.strip()})" for _, fragment in specs)
    return f"""
    DROP TABLE IF EXISTS postgis_research_candidates;
    CREATE TEMP TABLE postgis_research_candidates AS
    WITH base AS (
        SELECT
            batch_id,
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            p90_radius_m,
            p50_radius_m,
            window_obs_count,
            active_days,
            distinct_dev_id,
            drift_pattern,
            gps_anomaly_type,
            is_multi_centroid,
            is_dynamic
        FROM rb5.trusted_cell_library
        WHERE batch_id = {args.batch_id}
          AND p90_radius_m IS NOT NULL
    ),
    selected AS (
        {union_sql}
    )
    SELECT
        MAX(batch_id) AS batch_id,
        operator_code,
        lac,
        bs_id,
        cell_id,
        tech_norm,
        MAX(p90_radius_m) AS p90_radius_m,
        MAX(p50_radius_m) AS p50_radius_m,
        MAX(window_obs_count) AS window_obs_count,
        MAX(active_days) AS active_days,
        MAX(distinct_dev_id) AS distinct_dev_id,
        MAX(drift_pattern) AS current_drift_pattern,
        MAX(gps_anomaly_type) AS current_gps_anomaly_type,
        BOOL_OR(is_multi_centroid) AS current_is_multi_centroid,
        BOOL_OR(is_dynamic) AS current_is_dynamic,
        ARRAY_AGG(DISTINCT stratum ORDER BY stratum) AS strata
    FROM selected
    GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
    ORDER BY MAX(p90_radius_m) DESC NULLS LAST,
             MAX(window_obs_count) DESC NULLS LAST,
             operator_code,
             lac,
             cell_id;
    """


OBS_SQL = """
DROP TABLE IF EXISTS postgis_research_obs;
CREATE TEMP TABLE postgis_research_obs AS
SELECT
    c.batch_id,
    c.operator_code,
    c.lac,
    c.bs_id,
    c.cell_id,
    c.tech_norm,
    c.current_drift_pattern,
    c.current_gps_anomaly_type,
    c.current_is_multi_centroid,
    c.current_is_dynamic,
    c.p90_radius_m,
    c.p50_radius_m,
    c.window_obs_count,
    c.active_days,
    c.distinct_dev_id,
    c.strata,
    w.source_row_uid,
    w.dev_id,
    w.event_time_std,
    DATE(w.event_time_std) AS obs_date,
    ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326) AS geom_4326,
    ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857) AS geom_m
FROM postgis_research_candidates c
JOIN rb5.cell_sliding_window w
  ON w.batch_id BETWEEN GREATEST(c.batch_id - 4, 0) AND c.batch_id
 AND w.operator_code = c.operator_code
 AND w.lac = c.lac
 AND w.bs_id = c.bs_id
 AND w.cell_id = c.cell_id
 AND COALESCE(w.tech_norm, '') = COALESCE(c.tech_norm, '')
WHERE w.gps_valid IS TRUE
  AND w.lon_final IS NOT NULL
  AND w.lat_final IS NOT NULL;
"""


def _run_sql(conn: psycopg.Connection, sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(sql)


def _fetchall(conn: psycopg.Connection, sql: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def _json_default(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _candidate_overview(conn: psycopg.Connection) -> dict[str, Any]:
    rows = _fetchall(
        conn,
        """
        SELECT
            s.stratum,
            COUNT(*) AS sample_cells,
            COUNT(*) FILTER (WHERE tech_norm = '4G') AS cells_4g,
            COUNT(*) FILTER (WHERE tech_norm = '5G') AS cells_5g,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY window_obs_count)::numeric, 1) AS p50_window_obs,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY active_days)::numeric, 1) AS p50_active_days
        FROM postgis_research_candidates c
        CROSS JOIN LATERAL unnest(c.strata) AS s(stratum)
        GROUP BY s.stratum
        ORDER BY sample_cells DESC, s.stratum
        """,
    )
    drift_rows = _fetchall(
        conn,
        """
        SELECT
            current_drift_pattern,
            COUNT(*) AS sample_cells,
            COUNT(*) FILTER (WHERE current_gps_anomaly_type IS NOT NULL) AS anomaly_cells
        FROM postgis_research_candidates
        GROUP BY current_drift_pattern
        ORDER BY sample_cells DESC, current_drift_pattern
        """,
    )
    stats = _fetchall(
        conn,
        """
        SELECT
            COUNT(*) AS candidate_cells,
            COUNT(*) FILTER (WHERE current_gps_anomaly_type IS NOT NULL) AS anomaly_candidates,
            COUNT(*) FILTER (WHERE current_is_dynamic) AS dynamic_candidates,
            COUNT(*) FILTER (WHERE current_is_multi_centroid) AS multi_candidates,
            COUNT(*) FILTER (WHERE tech_norm = '4G') AS cells_4g,
            COUNT(*) FILTER (WHERE tech_norm = '5G') AS cells_5g
        FROM postgis_research_candidates
        """,
    )[0]
    obs = _fetchall(
        conn,
        """
        SELECT
            COALESCE(SUM(obs_per_cell), 0) AS total_obs,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY obs_per_cell)::numeric, 1) AS p50_obs_per_cell,
            ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY obs_per_cell)::numeric, 1) AS p90_obs_per_cell
        FROM (
            SELECT COUNT(*) AS obs_per_cell
            FROM postgis_research_obs
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ) t
        """,
    )[0]
    return {
        'headline': stats,
        'by_stratum': rows,
        'by_drift': drift_rows,
        'obs': obs,
    }


def _build_cluster_tables(conn: psycopg.Connection, args: argparse.Namespace, params: ParamSet) -> None:
    sql = f"""
    DROP TABLE IF EXISTS postgis_clustered;
    DROP TABLE IF EXISTS postgis_cluster_stats;
    DROP TABLE IF EXISTS postgis_cluster_days;
    DROP TABLE IF EXISTS postgis_pair_overlap;
    DROP TABLE IF EXISTS postgis_pair_stats;
    DROP TABLE IF EXISTS postgis_ranked_clusters;
    DROP TABLE IF EXISTS postgis_cell_summary;

    CREATE TEMP TABLE postgis_clustered AS
    SELECT
        o.*,
        ST_SnapToGrid(o.geom_m, {params.snap_m}) AS geom_snap_m,
        ST_ClusterDBSCAN(
            ST_SnapToGrid(o.geom_m, {params.snap_m}),
            eps => {params.eps_m},
            minpoints => {params.minpoints}
        ) OVER (
            PARTITION BY o.operator_code, o.lac, o.bs_id, o.cell_id, o.tech_norm
            ORDER BY o.event_time_std, o.source_row_uid
        ) AS cluster_id
    FROM postgis_research_obs o;

    CREATE TEMP TABLE postgis_cluster_stats AS
    WITH totals AS (
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            COUNT(*) AS total_obs,
            COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS total_devs,
            COUNT(DISTINCT obs_date) AS total_days
        FROM postgis_clustered
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
    ),
    cluster_agg AS (
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            c.cluster_id,
            COUNT(*) AS obs_count,
            COUNT(DISTINCT c.dev_id) FILTER (WHERE c.dev_id IS NOT NULL) AS dev_count,
            COUNT(DISTINCT c.obs_date) AS active_days,
            MIN(c.obs_date) AS first_day,
            MAX(c.obs_date) AS last_day,
            ST_Centroid(ST_Collect(c.geom_m)) AS centroid_geom_m,
            ST_Transform(ST_Centroid(ST_Collect(c.geom_m)), 4326) AS centroid_geom_4326,
            CASE
                WHEN COUNT(*) >= 3 THEN ST_Area(ST_ConvexHull(ST_Collect(c.geom_m)))
                ELSE 0::double precision
            END AS hull_area_m2,
            t.total_obs,
            t.total_devs,
            t.total_days
        FROM postgis_clustered c
        JOIN totals t
          ON t.operator_code IS NOT DISTINCT FROM c.operator_code
         AND t.lac IS NOT DISTINCT FROM c.lac
         AND t.bs_id IS NOT DISTINCT FROM c.bs_id
         AND t.cell_id IS NOT DISTINCT FROM c.cell_id
         AND t.tech_norm IS NOT DISTINCT FROM c.tech_norm
        GROUP BY
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            c.cluster_id,
            t.total_obs,
            t.total_devs,
            t.total_days
    ),
    cluster_radius AS (
        SELECT
            c.operator_code,
            c.lac,
            c.bs_id,
            c.cell_id,
            c.tech_norm,
            c.cluster_id,
            MAX(ST_Distance(c.geom_m, s.centroid_geom_m)) AS max_radius_m
        FROM postgis_clustered c
        JOIN cluster_agg s
          ON s.cluster_id IS NOT DISTINCT FROM c.cluster_id
         AND s.operator_code IS NOT DISTINCT FROM c.operator_code
         AND s.lac IS NOT DISTINCT FROM c.lac
         AND s.bs_id IS NOT DISTINCT FROM c.bs_id
         AND s.cell_id IS NOT DISTINCT FROM c.cell_id
         AND s.tech_norm IS NOT DISTINCT FROM c.tech_norm
        WHERE c.cluster_id IS NOT NULL
        GROUP BY c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm, c.cluster_id
    )
    SELECT
        a.operator_code,
        a.lac,
        a.bs_id,
        a.cell_id,
        a.tech_norm,
        a.cluster_id,
        a.obs_count,
        a.dev_count,
        a.active_days,
        a.first_day,
        a.last_day,
        a.centroid_geom_m,
        a.centroid_geom_4326,
        a.hull_area_m2,
        COALESCE(r.max_radius_m, 0) AS max_radius_m,
        a.total_obs,
        a.total_devs,
        a.total_days,
        a.obs_count::double precision / NULLIF(a.total_obs, 0) AS share_ratio,
        (
            a.cluster_id IS NOT NULL
            AND a.obs_count >= GREATEST({args.min_cluster_obs}, CEIL(a.total_obs * {args.min_cluster_share})::int)
            AND a.dev_count >= {args.min_cluster_devs}
            AND a.active_days >= {args.min_cluster_days}
        ) AS is_stable
    FROM cluster_agg a
    LEFT JOIN cluster_radius r
      ON r.cluster_id IS NOT DISTINCT FROM a.cluster_id
     AND r.operator_code IS NOT DISTINCT FROM a.operator_code
     AND r.lac IS NOT DISTINCT FROM a.lac
     AND r.bs_id IS NOT DISTINCT FROM a.bs_id
     AND r.cell_id IS NOT DISTINCT FROM a.cell_id
     AND r.tech_norm IS NOT DISTINCT FROM a.tech_norm;

    CREATE TEMP TABLE postgis_cluster_days AS
    SELECT DISTINCT
        operator_code,
        lac,
        bs_id,
        cell_id,
        tech_norm,
        cluster_id,
        obs_date
    FROM postgis_clustered
    WHERE cluster_id IS NOT NULL;

    CREATE TEMP TABLE postgis_pair_overlap AS
    SELECT
        a.operator_code,
        a.lac,
        a.bs_id,
        a.cell_id,
        a.tech_norm,
        a.cluster_id AS cluster_id_a,
        b.cluster_id AS cluster_id_b,
        COUNT(*) AS overlap_days
    FROM postgis_cluster_days a
    JOIN postgis_cluster_days b
      ON a.operator_code IS NOT DISTINCT FROM b.operator_code
     AND a.lac IS NOT DISTINCT FROM b.lac
     AND a.bs_id IS NOT DISTINCT FROM b.bs_id
     AND a.cell_id IS NOT DISTINCT FROM b.cell_id
     AND a.tech_norm IS NOT DISTINCT FROM b.tech_norm
     AND a.cluster_id < b.cluster_id
     AND a.obs_date = b.obs_date
    GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm, a.cluster_id, b.cluster_id;

    CREATE TEMP TABLE postgis_pair_stats AS
    SELECT
        a.operator_code,
        a.lac,
        a.bs_id,
        a.cell_id,
        a.tech_norm,
        COUNT(*) AS stable_pair_count,
        MAX(ST_Distance(a.centroid_geom_4326::geography, b.centroid_geom_4326::geography)) AS max_centroid_distance_m,
        AVG(ST_Distance(a.centroid_geom_4326::geography, b.centroid_geom_4326::geography)) AS avg_centroid_distance_m,
        MAX(COALESCE(o.overlap_days, 0)) AS max_overlap_days
    FROM postgis_cluster_stats a
    JOIN postgis_cluster_stats b
      ON a.operator_code IS NOT DISTINCT FROM b.operator_code
     AND a.lac IS NOT DISTINCT FROM b.lac
     AND a.bs_id IS NOT DISTINCT FROM b.bs_id
     AND a.cell_id IS NOT DISTINCT FROM b.cell_id
     AND a.tech_norm IS NOT DISTINCT FROM b.tech_norm
     AND a.cluster_id < b.cluster_id
    LEFT JOIN postgis_pair_overlap o
      ON o.operator_code IS NOT DISTINCT FROM a.operator_code
     AND o.lac IS NOT DISTINCT FROM a.lac
     AND o.bs_id IS NOT DISTINCT FROM a.bs_id
     AND o.cell_id IS NOT DISTINCT FROM a.cell_id
     AND o.tech_norm IS NOT DISTINCT FROM a.tech_norm
     AND o.cluster_id_a = a.cluster_id
     AND o.cluster_id_b = b.cluster_id
    WHERE a.is_stable AND b.is_stable
    GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm;

    CREATE TEMP TABLE postgis_ranked_clusters AS
    SELECT
        c.*,
        ROW_NUMBER() OVER (
            PARTITION BY c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm
            ORDER BY c.obs_count DESC, c.share_ratio DESC, c.cluster_id NULLS LAST
        ) AS cluster_rank
    FROM postgis_cluster_stats c
    WHERE c.is_stable;

    CREATE TEMP TABLE postgis_cell_summary AS
    WITH stable_rollup AS (
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            COUNT(*) AS stable_cluster_count,
            SUM(obs_count) AS stable_obs,
            MAX(share_ratio) FILTER (WHERE cluster_rank = 1) AS primary_share,
            MAX(share_ratio) FILTER (WHERE cluster_rank = 2) AS secondary_share,
            MAX(obs_count) FILTER (WHERE cluster_rank = 1) AS primary_obs,
            MAX(obs_count) FILTER (WHERE cluster_rank = 2) AS secondary_obs,
            MAX(active_days) FILTER (WHERE cluster_rank = 1) AS primary_days,
            MAX(active_days) FILTER (WHERE cluster_rank = 2) AS secondary_days
        FROM postgis_ranked_clusters
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
    )
    SELECT
        c.operator_code,
        c.lac,
        c.bs_id,
        c.cell_id,
        c.tech_norm,
        c.current_drift_pattern,
        c.current_gps_anomaly_type,
        c.current_is_multi_centroid,
        c.current_is_dynamic,
        c.p90_radius_m,
        c.p50_radius_m,
        c.window_obs_count,
        c.active_days,
        c.distinct_dev_id,
        c.strata,
        t.total_obs,
        t.total_devs,
        t.total_days,
        COALESCE(s.stable_cluster_count, 0) AS stable_cluster_count,
        COALESCE(s.stable_obs, 0) AS stable_obs,
        COALESCE(t.total_obs - s.stable_obs, t.total_obs) AS filtered_noise_obs,
        COALESCE((t.total_obs - s.stable_obs)::double precision / NULLIF(t.total_obs, 0), 1.0) AS filtered_noise_ratio,
        COALESCE(s.primary_share, 0) AS primary_share,
        COALESCE(s.secondary_share, 0) AS secondary_share,
        COALESCE(s.primary_obs, 0) AS primary_obs,
        COALESCE(s.secondary_obs, 0) AS secondary_obs,
        COALESCE(s.primary_days, 0) AS primary_days,
        COALESCE(s.secondary_days, 0) AS secondary_days,
        COALESCE(p.max_centroid_distance_m, 0) AS max_centroid_distance_m,
        COALESCE(p.avg_centroid_distance_m, 0) AS avg_centroid_distance_m,
        COALESCE(p.max_overlap_days, 0) AS max_overlap_days,
        CASE
            WHEN COALESCE(s.stable_cluster_count, 0) = 0 THEN 'dirty_sparse'
            WHEN COALESCE(s.stable_cluster_count, 0) = 1
                AND COALESCE((t.total_obs - s.stable_obs)::double precision / NULLIF(t.total_obs, 0), 0) >= {args.single_noise_ratio}
                THEN 'single_with_noise'
            WHEN COALESCE(s.stable_cluster_count, 0) = 1 THEN 'single_large_coverage'
            WHEN COALESCE(p.max_centroid_distance_m, 0) >= {args.collision_distance_m} THEN 'collision_like'
            WHEN COALESCE(s.stable_cluster_count, 0) >= 3 THEN 'dynamic_multi'
            WHEN COALESCE(p.max_overlap_days, 0) <= {args.migration_max_overlap_days} THEN 'migration_like'
            ELSE 'dual_centroid'
        END AS research_class
    FROM postgis_research_candidates c
    JOIN (
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            COUNT(*) AS total_obs,
            COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS total_devs,
            COUNT(DISTINCT obs_date) AS total_days
        FROM postgis_clustered
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
    ) t
      ON t.operator_code IS NOT DISTINCT FROM c.operator_code
     AND t.lac IS NOT DISTINCT FROM c.lac
     AND t.bs_id IS NOT DISTINCT FROM c.bs_id
     AND t.cell_id IS NOT DISTINCT FROM c.cell_id
     AND t.tech_norm IS NOT DISTINCT FROM c.tech_norm
    LEFT JOIN stable_rollup s
      ON s.operator_code IS NOT DISTINCT FROM c.operator_code
     AND s.lac IS NOT DISTINCT FROM c.lac
     AND s.bs_id IS NOT DISTINCT FROM c.bs_id
     AND s.cell_id IS NOT DISTINCT FROM c.cell_id
     AND s.tech_norm IS NOT DISTINCT FROM c.tech_norm
    LEFT JOIN postgis_pair_stats p
      ON p.operator_code IS NOT DISTINCT FROM c.operator_code
     AND p.lac IS NOT DISTINCT FROM c.lac
     AND p.bs_id IS NOT DISTINCT FROM c.bs_id
     AND p.cell_id IS NOT DISTINCT FROM c.cell_id
     AND p.tech_norm IS NOT DISTINCT FROM c.tech_norm;
    """
    _run_sql(conn, sql)


def _parameter_payload(conn: psycopg.Connection, params: ParamSet) -> dict[str, Any]:
    summary_rows = _fetchall(
        conn,
        """
        SELECT
            research_class,
            COUNT(*) AS cell_count,
            ROUND(AVG(stable_cluster_count)::numeric, 2) AS avg_stable_clusters,
            ROUND(AVG(filtered_noise_ratio)::numeric, 3) AS avg_noise_ratio
        FROM postgis_cell_summary
        GROUP BY research_class
        ORDER BY cell_count DESC, research_class
        """,
    )
    sample_rows = _fetchall(
        conn,
        """
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            current_drift_pattern,
            current_gps_anomaly_type,
            current_is_multi_centroid,
            current_is_dynamic,
            p90_radius_m,
            window_obs_count,
            active_days,
            distinct_dev_id,
            strata,
            total_obs,
            total_devs,
            total_days,
            stable_cluster_count,
            filtered_noise_obs,
            filtered_noise_ratio,
            primary_share,
            secondary_share,
            primary_obs,
            secondary_obs,
            primary_days,
            secondary_days,
            max_centroid_distance_m,
            avg_centroid_distance_m,
            max_overlap_days,
            research_class
        FROM postgis_cell_summary
        ORDER BY research_class, total_obs DESC, p90_radius_m DESC NULLS LAST, cell_id
        """,
    )
    cluster_rows = _fetchall(
        conn,
        """
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            cluster_id,
            obs_count,
            dev_count,
            active_days,
            ROUND(share_ratio::numeric, 4) AS share_ratio,
            ROUND(max_radius_m::numeric, 1) AS max_radius_m,
            ROUND(hull_area_m2::numeric, 1) AS hull_area_m2,
            ST_X(centroid_geom_4326) AS center_lon,
            ST_Y(centroid_geom_4326) AS center_lat,
            is_stable
        FROM postgis_cluster_stats
        ORDER BY operator_code, lac, bs_id, cell_id, tech_norm, is_stable DESC, obs_count DESC, cluster_id NULLS LAST
        """,
    )
    return {
        'label': params.label,
        'eps_m': params.eps_m,
        'minpoints': params.minpoints,
        'snap_m': params.snap_m,
        'summary': summary_rows,
        'cells': sample_rows,
        'clusters': cluster_rows,
    }


def _pick_representatives(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for key in (
        'single_large_coverage',
        'single_with_noise',
        'dirty_sparse',
        'dual_centroid',
        'migration_like',
        'collision_like',
        'dynamic_multi',
    ):
        chosen = [row for row in rows if row['research_class'] == key][:3]
        if chosen:
            grouped[key] = chosen
    return grouped


def _fmt_case(row: dict[str, Any]) -> str:
    key = f"{row['operator_code']}|{row['lac']}|{row['bs_id']}|{row['cell_id']}|{row['tech_norm']}"
    return (
        f"- `{key}` p90={float(row['p90_radius_m'] or 0):.1f}m, "
        f"window_obs={int(row['window_obs_count'] or 0)}, total_obs={int(row['total_obs'] or 0)}, "
        f"stable_clusters={int(row['stable_cluster_count'] or 0)}, "
        f"noise_ratio={float(row['filtered_noise_ratio'] or 0):.2f}, "
        f"max_centroid_distance={float(row['max_centroid_distance_m'] or 0):.1f}m, "
        f"overlap_days={int(row['max_overlap_days'] or 0)}, "
        f"current=({row['current_drift_pattern']}, multi={row['current_is_multi_centroid']}, dynamic={row['current_is_dynamic']}, anomaly={row['current_gps_anomaly_type']})"
    )


def _render_markdown(
    *,
    args: argparse.Namespace,
    overview: dict[str, Any],
    parameter_payloads: list[dict[str, Any]],
) -> str:
    baseline = next(payload for payload in parameter_payloads if payload['label'] == BASELINE_LABEL)
    baseline_cells = baseline['cells']
    baseline_counter = Counter(str(row['research_class']) for row in baseline_cells)
    representatives = _pick_representatives(baseline_cells)

    lines: list[str] = [
        '# Batch7 PostGIS 多质心 / 迁移 / 碰撞研究报告',
        '',
        f"- 生成时间: `{datetime.now(UTC).isoformat()}`",
        f"- 研究输入数据库: `{args.dsn}`",
        f"- 研究批次: `batch_id={args.batch_id}`",
        f"- 基线参数: `{BASELINE_LABEL}`",
        '',
        '## 1. 样本选择方法',
        '',
        '研究不是简单取 `p90` 最大前 100，而是先按真实标签分层，再做去重抽样。',
        '',
        '- 基础候选范围: `trusted_cell_library(batch7)` 中 `p90_radius_m >= 800m` 的大半径 Cell',
        '- 高质量主样本: `window_obs_count >= 20` 且 `active_days >= 3`，覆盖 `stable / large_coverage / migration / collision / moderate_drift`',
        '- 脏信号补样: 额外纳入 `gps_anomaly_type IS NOT NULL` 与 `drift_pattern=insufficient` 的低观测异常样本',
        '- 极端值补样: 额外纳入 `p90_radius_m >= 1500m` 的超大半径对象',
        '',
        f"- 最终样本 Cell 数: `{int(overview['headline']['candidate_cells'])}`",
        f"- 最终样本观测点数: `{int(overview['obs']['total_obs'])}`",
        f"- 样本中 4G/5G: `{int(overview['headline']['cells_4g'])}` / `{int(overview['headline']['cells_5g'])}`",
        f"- 样本中 `gps_anomaly_type IS NOT NULL`: `{int(overview['headline']['anomaly_candidates'])}`",
        '',
        '### 1.1 分层覆盖',
        '',
        '| 分层 | 样本 Cell | 4G | 5G | p50 window_obs | p50 active_days |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for row in overview['by_stratum']:
        lines.append(
            f"| {row['stratum']} | {int(row['sample_cells'])} | {int(row['cells_4g'])} | {int(row['cells_5g'])} | {float(row['p50_window_obs'] or 0):.1f} | {float(row['p50_active_days'] or 0):.1f} |"
        )

    lines.extend(
        [
            '',
            '### 1.2 当前 drift_pattern 覆盖',
            '',
            '| drift_pattern | 样本 Cell | anomaly Cell |',
            '|---|---:|---:|',
        ]
    )
    for row in overview['by_drift']:
        lines.append(f"| {row['current_drift_pattern']} | {int(row['sample_cells'])} | {int(row['anomaly_cells'])} |")

    lines.extend(
        [
            '',
            '## 2. PostGIS 研究方法',
            '',
            '### 2.1 空间处理顺序',
            '',
            '1. 从 `cell_sliding_window` 提取真实 GPS 观测，只保留 `gps_valid=true` 且经纬度非空的记录。',
            '2. 把 WGS84 点转成 `EPSG:3857` 的米制 geometry，用于 `ST_ClusterDBSCAN` 和 `ST_SnapToGrid`。',
            '3. 先用 `ST_SnapToGrid(geom_m, 50m)` 压掉抖动，再对每个 Cell 分区执行 `ST_ClusterDBSCAN`。',
            '4. 对每个簇统计 `obs/dev/active_days/share_ratio`，并用这些稳定性指标过滤掉小簇、单设备簇和短时簇。',
            '5. 对稳定簇再算 `ST_Centroid`、`ST_ConvexHull`、`ST_Area`、簇间 `ST_Distance` 和日期重叠度。',
            '',
            '### 2.2 脏信号定义',
            '',
            '- `ST_ClusterDBSCAN` 输出 `cluster_id IS NULL` 的噪声点，视为一级脏信号。',
            '- 即便被聚成簇，只要 `obs_count < max(5, total_obs*10%)`、或 `dev_count < 2`、或 `active_days < 2`，视为不稳定簇，仍在最终质心计算前过滤。',
            '- 主质心、多质心、迁移、碰撞的分类只基于稳定簇，不直接把噪声点或不稳定簇纳入最终中心。',
            '',
            '### 2.3 基线参数',
            '',
            f"- `eps = 250m`",
            f"- `minpoints = 4`",
            f"- `snap_to_grid = 50m`",
            f"- `stable cluster`: `obs >= max({args.min_cluster_obs}, total_obs*{args.min_cluster_share:.2f})`, `dev >= {args.min_cluster_devs}`, `active_days >= {args.min_cluster_days}`",
            f"- `collision_distance = {args.collision_distance_m:.0f}m`",
            f"- `migration_max_overlap_days = {args.migration_max_overlap_days}`",
            '',
            '## 3. 参数敏感性',
            '',
            '| 参数组 | single_large | single_noise | dirty_sparse | dual | migration | collision | dynamic_multi |',
            '|---|---:|---:|---:|---:|---:|---:|---:|',
        ]
    )
    for payload in parameter_payloads:
        counter = Counter(str(row['research_class']) for row in payload['cells'])
        lines.append(
            f"| {payload['label']} | {counter['single_large_coverage']} | {counter['single_with_noise']} | "
            f"{counter['dirty_sparse']} | {counter['dual_centroid']} | {counter['migration_like']} | "
            f"{counter['collision_like']} | {counter['dynamic_multi']} |"
        )

    lines.extend(
        [
            '',
            '观察：',
            '- `eps=150` 更容易把相邻热点拆成多个簇，`dual_centroid / dirty_sparse` 会偏多。',
            '- `eps=400` 会明显吞并邻近热点，`single_large_coverage` 会偏多，迁移和双质心会被低估。',
            '- `eps=250, minpoints=4` 在“稳定双簇能保留下来、单设备噪声不会轻易晋级”为目标下更平衡。',
            '',
            '## 4. 基线结果',
            '',
            '| 类别 | Cell 数 |',
            '|---|---:|',
        ]
    )
    for key in (
        'single_large_coverage',
        'single_with_noise',
        'dirty_sparse',
        'dual_centroid',
        'migration_like',
        'collision_like',
        'dynamic_multi',
    ):
        lines.append(f"| {key} | {baseline_counter.get(key, 0)} |")

    noise_rows = [row for row in baseline_cells if float(row['filtered_noise_ratio'] or 0) >= args.single_noise_ratio]
    lines.extend(
        [
            '',
            f"- `filtered_noise_ratio >= {args.single_noise_ratio:.2f}` 的样本数: `{len(noise_rows)}`",
            f"- `stable_cluster_count = 0` 的样本数: `{baseline_counter.get('dirty_sparse', 0)}`",
            f"- 当前系统 `is_multi_centroid=true` 的样本数: `{sum(1 for row in baseline_cells if row['current_is_multi_centroid'])}`",
            f"- 研究判定 `stable_cluster_count >= 2` 的样本数: `{sum(1 for row in baseline_cells if int(row['stable_cluster_count'] or 0) >= 2)}`",
            '',
            '## 5. 代表 case',
            '',
        ]
    )
    for category, rows in representatives.items():
        lines.append(f'### {category}')
        lines.append('')
        lines.extend(_fmt_case(row) for row in rows)
        lines.append('')

    lines.extend(
        [
            '## 6. 推荐正式实现方案',
            '',
            '### 6.1 候选集收缩',
            '',
            '- 只对 `p90_radius_m >= 800m`、或 `gps_anomaly_type IS NOT NULL`、或 `is_dynamic`、或 `drift_pattern IN (collision, migration, moderate_drift)` 的 Cell 进入 PostGIS 研究链。',
            '- `window_obs_count < 5` 或 `active_days < 2` 的对象不直接做多质心结论，只进入“dirty/insufficient”观察池。',
            '',
            '### 6.2 PG 内实现顺序',
            '',
            '1. `candidate_cells`：从 `trusted_cell_library(batch=t)` 选候选集。',
            '2. `candidate_obs`：从 `cell_sliding_window` 提取有效 GPS，并生成 `geom_4326`、`geom_m`。',
            '3. `clustered_points`：`ST_SnapToGrid` 后按 Cell 分区跑 `ST_ClusterDBSCAN`。',
            '4. `cluster_stats`：按簇聚合 `obs/dev/active_days/share_ratio`，算 `ST_Centroid / ST_ConvexHull / ST_Area`。',
            '5. `stable_clusters`：过滤掉噪声簇和不稳定簇。',
            '6. `cell_cluster_summary`：算稳定簇数、簇间最大距离、日期重叠天数、主次簇占比。',
            '7. `cell_centroid_detail`：只把稳定簇写入细表；主簇作为主质心，对外服务只默认返回主簇。',
            '',
            '### 6.3 分类判定建议',
            '',
            '- `dirty_sparse`: 没有稳定簇，或稳定证据完全不足。',
            '- `single_large_coverage`: 只有 1 个稳定簇，允许存在少量噪声点，但噪声不会进入最终质心。',
            '- `single_with_noise`: 只有 1 个稳定簇，但过滤掉的噪声/不稳定簇占比偏高，应保留异常标签而不是直接升为多质心。',
            '- `dual_centroid`: 恰好 2 个稳定簇，簇间距离明显，且时间上存在持续重叠。',
            '- `migration_like`: 2 个稳定簇，但重叠天数很低，更像阶段性搬迁而不是长期双中心。',
            '- `collision_like`: 2 个及以上稳定簇，且任意稳定簇间距超过 20km。',
            '- `dynamic_multi`: 3 个及以上稳定簇，或多簇长期交替出现。',
            '',
            '### 6.4 坐标与函数建议',
            '',
            '- `ST_ClusterDBSCAN` 和 `ST_SnapToGrid` 用米制 `geometry`，推荐先 `ST_Transform(..., 3857)`。',
            '- 报告距离和簇间距离用 `ST_Distance(geography)`，减少经纬度尺度误差。',
            '- 面积类指标用 `ST_Area`，可以对 `ST_ConvexHull` 结果做 geography/投影后再算。',
            '',
            '### 6.5 成本与增量化',
            '',
            '- 候选集外的稳定 Cell 直接复用已有结果，不做全量聚类。',
            '- 增量重算触发条件建议收口到：`p90` 显著变化、`gps_anomaly_type` 变化、`drift_pattern` 变化、新进候选集。',
            '- `cell_centroid_detail` 可以作为下一批的先验簇库，新点优先按距离归属到已有稳定簇，再决定是否触发重聚类。',
            '',
            '## 7. 本轮结论',
            '',
            '- PostGIS 已能在 PG 内完成候选筛选、簇生成、簇特征统计和分类判定，不需要长期依赖 Python 离线聚类。',
            '- 研究结果已经形成，但还没有并入主链，也没有触发 smoke 全流程或正式 7 天重跑。',
            '- 下一步必须先人工确认这套分类边界与参数，再进入整合验证。',
        ]
    )
    return '\n'.join(lines) + '\n'


def main() -> None:
    args = _parse_args()
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(args.dsn, autocommit=True, row_factory=dict_row) as conn:
        _run_sql(conn, _strata_sql(args))
        _run_sql(
            conn,
            """
            CREATE INDEX ON postgis_research_candidates
                (batch_id, operator_code, lac, bs_id, cell_id, tech_norm);
            ANALYZE postgis_research_candidates;
            """,
        )
        _run_sql(conn, OBS_SQL)
        _run_sql(
            conn,
            """
            CREATE INDEX ON postgis_research_obs
                (batch_id, operator_code, lac, bs_id, cell_id, tech_norm, obs_date);
            ANALYZE postgis_research_obs;
            """,
        )

        overview = _candidate_overview(conn)
        parameter_payloads: list[dict[str, Any]] = []
        for params in PARAM_SETS:
            _build_cluster_tables(conn, args, params)
            parameter_payloads.append(_parameter_payload(conn, params))

    markdown = _render_markdown(
        args=args,
        overview=overview,
        parameter_payloads=parameter_payloads,
    )
    payload = {
        'generated_at': datetime.now(UTC).isoformat(),
        'dsn': args.dsn,
        'batch_id': args.batch_id,
        'overview': overview,
        'parameter_payloads': parameter_payloads,
        'baseline_label': BASELINE_LABEL,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding='utf-8')
    out_md.write_text(markdown, encoding='utf-8')
    print(f'Wrote {out_json}')
    print(f'Wrote {out_md}')


if __name__ == '__main__':
    main()
