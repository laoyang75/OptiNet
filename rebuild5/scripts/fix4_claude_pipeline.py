"""Fix4 Claude Research Pipeline — Two-stage centroid + expanded DBSCAN.

Runs 7 daily batches on shared sample data in rebuild5_fix4 schema.
Implements:
  1. Two-stage outlier filtering (3000m threshold) for centroid/p90
  2. Expanded DBSCAN candidate selection (p90-based direct entry)
  3. DBSCAN multi-centroid analysis with classification

Usage:
    python rebuild5/scripts/fix4_claude_pipeline.py
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

import psycopg

DB_DSN = "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"
SCHEMA = "rebuild5_fix4"
OUTLIER_THRESHOLD_M = 3000  # two-stage filter radius

# DBSCAN parameters (from antitoxin_params.yaml)
SNAP_GRID_M = 50
CLUSTER_EPS_M = 250
CLUSTER_MIN_POINTS = 4
STABLE_MIN_OBS = 5
STABLE_MIN_SHARE = 0.10
STABLE_MIN_DAYS = 2
STABLE_MIN_DEVS = 2
STABLE_SINGLE_DEV_MAX_TOTAL = 2
DUAL_CLUSTER_MIN_DIST_M = 300
MIGRATION_MIN_DIST_M = 500
MIGRATION_MAX_OVERLAP_DAYS = 1
MOVING_MIN_OVERLAP_DAYS = 2
MOVING_MIN_SWITCHES = 2
MULTI_CLUSTER_MIN_COUNT = 3

# Candidate selection: expanded from current config
CANDIDATE_MIN_P90_M = 800  # direct entry if p90 > this
CANDIDATE_MIN_WINDOW_OBS = 5
CANDIDATE_MIN_ACTIVE_DAYS = 2

BATCH_DATES = [
    date(2025, 12, 1),
    date(2025, 12, 2),
    date(2025, 12, 3),
    date(2025, 12, 4),
    date(2025, 12, 5),
    date(2025, 12, 6),
    date(2025, 12, 7),
]


def get_conn():
    return psycopg.connect(DB_DSN, autocommit=False)


def execute(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()


def fetchone(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetchall(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ──────────────────────────────────────────────
# Schema setup
# ──────────────────────────────────────────────

def setup_schema(conn):
    """Create/reset all working tables."""
    ddl = f"""
    DROP TABLE IF EXISTS {SCHEMA}.claude_sliding_window CASCADE;
    CREATE UNLOGGED TABLE {SCHEMA}.claude_sliding_window (
        batch_id        int,
        record_id       text,
        operator_code   text,
        lac             bigint,
        bs_id           bigint,
        cell_id         bigint,
        tech_norm       text,
        dev_id          text,
        event_time_std  timestamptz,
        gps_valid       boolean,
        lon_final       double precision,
        lat_final       double precision,
        rsrp_final      double precision,
        rsrq_final      double precision,
        sinr_final      double precision
    );

    DROP TABLE IF EXISTS {SCHEMA}.claude_cell_library CASCADE;
    CREATE TABLE {SCHEMA}.claude_cell_library (
        batch_id        int,
        operator_code   text,
        lac             bigint,
        bs_id           bigint,
        cell_id         bigint,
        tech_norm       text,
        lifecycle_state text,
        center_lon      double precision,
        center_lat      double precision,
        p50_radius_m    double precision,
        p90_radius_m    double precision,
        p80_radius_m    double precision,
        independent_obs bigint,
        distinct_dev_id bigint,
        gps_valid_count bigint,
        active_days     int,
        window_obs_count bigint,
        observed_span_hours double precision,
        -- Filtering stats
        total_gps_pts   int,
        kept_pts        int,
        removed_pts     int,
        outlier_ratio   double precision,
        -- Classification
        drift_pattern   text,
        is_collision    boolean DEFAULT false,
        is_dynamic      boolean DEFAULT false,
        is_multi_centroid boolean DEFAULT false,
        centroid_pattern text,
        stable_cluster_count int DEFAULT 0,
        max_pair_distance_m double precision DEFAULT 0,
        PRIMARY KEY (batch_id, operator_code, lac, cell_id, tech_norm)
    );

    DROP TABLE IF EXISTS {SCHEMA}.claude_bs_library CASCADE;
    CREATE TABLE {SCHEMA}.claude_bs_library (
        batch_id        int,
        operator_code   text,
        lac             bigint,
        bs_id           bigint,
        lifecycle_state text,
        center_lon      double precision,
        center_lat      double precision,
        gps_p50_dist_m  double precision,
        gps_p90_dist_m  double precision,
        total_cells     int,
        qualified_cells int,
        classification  text,
        is_multi_centroid boolean DEFAULT false,
        PRIMARY KEY (batch_id, operator_code, lac, bs_id)
    );

    DROP TABLE IF EXISTS {SCHEMA}.claude_cell_centroid_detail CASCADE;
    CREATE TABLE {SCHEMA}.claude_cell_centroid_detail (
        batch_id        int,
        operator_code   text,
        lac             bigint,
        bs_id           bigint,
        cell_id         bigint,
        tech_norm       text,
        cluster_id      int,
        is_primary      boolean,
        center_lon      double precision,
        center_lat      double precision,
        obs_count       int,
        dev_count       int,
        active_days     int,
        radius_m        double precision,
        share_ratio     double precision
    );

    DROP TABLE IF EXISTS {SCHEMA}.claude_batch_stats CASCADE;
    CREATE TABLE {SCHEMA}.claude_batch_stats (
        batch_id        int,
        step            text,
        started_at      timestamptz DEFAULT now(),
        duration_s      double precision,
        row_count       bigint,
        notes           text,
        PRIMARY KEY (batch_id, step)
    );
    """
    for stmt in ddl.split(';'):
        stmt = stmt.strip()
        if stmt:
            execute(conn, stmt)
    print("Schema setup complete.")


# ──────────────────────────────────────────────
# Step 1: Load daily data into sliding window
# ──────────────────────────────────────────────

def load_sliding_window(conn, batch_id: int, batch_date: date):
    t0 = time.time()
    next_date = batch_date + timedelta(days=1)
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_sliding_window (
            batch_id, record_id, operator_code, lac, bs_id, cell_id, tech_norm,
            dev_id, event_time_std, gps_valid, lon_final, lat_final,
            rsrp_final, rsrq_final, sinr_final
        )
        SELECT
            {batch_id}, record_id, operator_code, lac, bs_id, cell_id, tech_norm,
            dev_id, report_ts, gps_valid, lon_filled, lat_filled,
            rsrp::double precision, rsrq::double precision, sinr::double precision
        FROM {SCHEMA}.etl_cleaned_shared_sample
        WHERE report_ts >= %s AND report_ts < %s
    """, (str(batch_date), str(next_date)))

    row_count = fetchone(conn, f"""
        SELECT count(*) FROM {SCHEMA}.claude_sliding_window WHERE batch_id = {batch_id}
    """)[0]

    # Rebuild index after bulk insert
    execute(conn, f"DROP INDEX IF EXISTS {SCHEMA}.idx_claude_sw_cell")
    execute(conn, f"""
        CREATE INDEX idx_claude_sw_cell ON {SCHEMA}.claude_sliding_window
        (operator_code, lac, bs_id, cell_id, tech_norm)
    """)
    execute(conn, f"ANALYZE {SCHEMA}.claude_sliding_window")

    dt = time.time() - t0
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_batch_stats (batch_id, step, duration_s, row_count, notes)
        VALUES ({batch_id}, 'load_window', {dt:.2f}, {row_count}, 'date={batch_date}')
    """)
    print(f"  Batch {batch_id} window load: {row_count:,} rows in {dt:.1f}s")
    return row_count


# ──────────────────────────────────────────────
# Step 2: Two-stage centroid + publish cell library
# ──────────────────────────────────────────────

def compute_cell_metrics_and_publish(conn, batch_id: int):
    """Two-stage centroid: rough median → filter outliers → refined centroid + p90."""
    t0 = time.time()

    # Clear previous batch
    execute(conn, f"DELETE FROM {SCHEMA}.claude_cell_library WHERE batch_id = {batch_id}")

    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_cell_library (
            batch_id, operator_code, lac, bs_id, cell_id, tech_norm,
            lifecycle_state, center_lon, center_lat,
            p50_radius_m, p90_radius_m, p80_radius_m,
            independent_obs, distinct_dev_id, gps_valid_count, active_days,
            window_obs_count, observed_span_hours,
            total_gps_pts, kept_pts, removed_pts, outlier_ratio
        )
        WITH
        -- Stage 1: rough centroid from ALL valid GPS points in window
        rough AS (
            SELECT
                operator_code, lac, bs_id, cell_id, tech_norm,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS rough_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) AS rough_lat,
                COUNT(*) AS total_gps_pts,
                COUNT(DISTINCT dev_id) AS distinct_dev_id,
                COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text)) AS independent_obs,
                COUNT(DISTINCT DATE(event_time_std)) AS active_days,
                (EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0) AS observed_span_hours,
                COUNT(*) AS window_obs_count
            FROM {SCHEMA}.claude_sliding_window
            WHERE gps_valid AND lon_final IS NOT NULL AND lat_final IS NOT NULL
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        -- Stage 2: filter out outliers > {OUTLIER_THRESHOLD_M}m from rough centroid
        filtered_pts AS (
            SELECT
                w.operator_code, w.lac, w.bs_id, w.cell_id, w.tech_norm,
                w.lon_final, w.lat_final,
                SQRT(POWER((w.lon_final - r.rough_lon) * 85300, 2)
                   + POWER((w.lat_final - r.rough_lat) * 111000, 2)) AS dist_to_rough
            FROM {SCHEMA}.claude_sliding_window w
            JOIN rough r USING (operator_code, lac, bs_id, cell_id, tech_norm)
            WHERE w.gps_valid AND w.lon_final IS NOT NULL AND w.lat_final IS NOT NULL
              AND SQRT(POWER((w.lon_final - r.rough_lon) * 85300, 2)
                     + POWER((w.lat_final - r.rough_lat) * 111000, 2)) <= {OUTLIER_THRESHOLD_M}
        ),
        -- Refined centroid from filtered points
        refined AS (
            SELECT
                operator_code, lac, bs_id, cell_id, tech_norm,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS center_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) AS center_lat,
                COUNT(*) AS kept_pts
            FROM filtered_pts
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        -- p50/p80/p90 from filtered points against refined centroid
        with_radius AS (
            SELECT
                ref.operator_code, ref.lac, ref.bs_id, ref.cell_id, ref.tech_norm,
                ref.center_lon, ref.center_lat, ref.kept_pts,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                    SQRT(POWER((fp.lon_final - ref.center_lon) * 85300, 2)
                       + POWER((fp.lat_final - ref.center_lat) * 111000, 2))
                ) AS p50_radius_m,
                PERCENTILE_CONT(0.8) WITHIN GROUP (ORDER BY
                    SQRT(POWER((fp.lon_final - ref.center_lon) * 85300, 2)
                       + POWER((fp.lat_final - ref.center_lat) * 111000, 2))
                ) AS p80_radius_m,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                    SQRT(POWER((fp.lon_final - ref.center_lon) * 85300, 2)
                       + POWER((fp.lat_final - ref.center_lat) * 111000, 2))
                ) AS p90_radius_m
            FROM refined ref
            JOIN filtered_pts fp USING (operator_code, lac, bs_id, cell_id, tech_norm)
            GROUP BY ref.operator_code, ref.lac, ref.bs_id, ref.cell_id, ref.tech_norm,
                     ref.center_lon, ref.center_lat, ref.kept_pts
        )
        SELECT
            {batch_id},
            r.operator_code, r.lac, r.bs_id, r.cell_id, r.tech_norm,
            CASE
                WHEN ro.independent_obs >= 30 THEN 'excellent'
                WHEN ro.independent_obs >= 10 THEN 'qualified'
                WHEN ro.independent_obs >= 1 THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,
            r.center_lon, r.center_lat,
            r.p50_radius_m, r.p90_radius_m, r.p80_radius_m,
            ro.independent_obs, ro.distinct_dev_id, ro.total_gps_pts AS gps_valid_count,
            ro.active_days, ro.window_obs_count, ro.observed_span_hours,
            ro.total_gps_pts,
            r.kept_pts,
            ro.total_gps_pts - r.kept_pts AS removed_pts,
            CASE WHEN ro.total_gps_pts > 0
                 THEN (ro.total_gps_pts - r.kept_pts)::double precision / ro.total_gps_pts
                 ELSE 0 END AS outlier_ratio
        FROM with_radius r
        JOIN rough ro USING (operator_code, lac, bs_id, cell_id, tech_norm)
    """)

    cell_count = fetchone(conn, f"""
        SELECT count(*) FROM {SCHEMA}.claude_cell_library WHERE batch_id = {batch_id}
    """)[0]

    dt = time.time() - t0
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_batch_stats (batch_id, step, duration_s, row_count, notes)
        VALUES ({batch_id}, 'cell_metrics', {dt:.2f}, {cell_count}, 'two-stage centroid')
    """)
    print(f"  Batch {batch_id} cell metrics: {cell_count:,} cells in {dt:.1f}s")
    return cell_count


# ──────────────────────────────────────────────
# Step 3: DBSCAN multi-centroid analysis
# ──────────────────────────────────────────────

def run_dbscan_analysis(conn, batch_id: int):
    """Expanded DBSCAN candidate selection + PostGIS clustering."""
    t0 = time.time()

    # Stage tables
    stages = [
        f'{SCHEMA}._claude_centroid_candidates',
        f'{SCHEMA}._claude_centroid_points',
        f'{SCHEMA}._claude_centroid_grid',
        f'{SCHEMA}._claude_centroid_clustered',
        f'{SCHEMA}._claude_centroid_labelled',
        f'{SCHEMA}._claude_centroid_valid_clusters',
        f'{SCHEMA}._claude_centroid_daily_presence',
        f'{SCHEMA}._claude_centroid_classification',
    ]
    for t in stages:
        execute(conn, f'DROP TABLE IF EXISTS {t}')

    # 1. Candidates: expanded selection
    # Key fix: add p90 > threshold as direct entry, include large_coverage
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_candidates AS
        SELECT batch_id, operator_code, lac, bs_id, cell_id, tech_norm
        FROM {SCHEMA}.claude_cell_library
        WHERE batch_id = {batch_id}
          AND COALESCE(window_obs_count, 0) >= {CANDIDATE_MIN_WINDOW_OBS}
          AND COALESCE(active_days, 0) >= {CANDIDATE_MIN_ACTIVE_DAYS}
          AND (
              -- Direct p90 entry: any cell with high p90 after filtering
              p90_radius_m >= {CANDIDATE_MIN_P90_M}
              -- Or significant outlier removal (>5% points removed)
              OR (outlier_ratio > 0.05 AND total_gps_pts >= 10)
              -- Or cells that still show spread even after filtering
              OR (p90_radius_m >= 500 AND kept_pts >= 20)
          )
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_candidates
        (operator_code, lac, bs_id, cell_id, tech_norm)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_candidates")

    cand_count = fetchone(conn, f"""
        SELECT count(*) FROM {SCHEMA}._claude_centroid_candidates
    """)[0]
    print(f"    DBSCAN candidates: {cand_count}")

    if cand_count == 0:
        for t in stages:
            execute(conn, f'DROP TABLE IF EXISTS {t}')
        dt = time.time() - t0
        execute(conn, f"""
            INSERT INTO {SCHEMA}.claude_batch_stats (batch_id, step, duration_s, row_count, notes)
            VALUES ({batch_id}, 'dbscan', {dt:.2f}, 0, 'no candidates')
        """)
        return 0

    # 2. Extract GPS points for candidates from sliding window
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_points AS
        SELECT
            c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm,
            w.dev_id,
            DATE(w.event_time_std) AS obs_date,
            ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857) AS geom_3857,
            ST_SnapToGrid(
                ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857),
                {SNAP_GRID_M}
            ) AS snap_geom_3857
        FROM {SCHEMA}._claude_centroid_candidates c
        JOIN {SCHEMA}.claude_sliding_window w
          ON w.operator_code = c.operator_code
         AND w.lac = c.lac AND w.bs_id = c.bs_id
         AND w.cell_id = c.cell_id AND w.tech_norm IS NOT DISTINCT FROM c.tech_norm
        WHERE w.gps_valid AND w.lon_final IS NOT NULL AND w.lat_final IS NOT NULL
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_points
        (operator_code, lac, bs_id, cell_id, tech_norm, obs_date)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_points")

    # 3. Grid aggregation
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_grid AS
        SELECT
            operator_code, lac, bs_id, cell_id, tech_norm,
            snap_geom_3857,
            COUNT(*) AS snap_obs_count,
            ST_X(snap_geom_3857) AS snap_x,
            ST_Y(snap_geom_3857) AS snap_y
        FROM {SCHEMA}._claude_centroid_points
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, snap_geom_3857
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_grid
        (operator_code, lac, bs_id, cell_id, tech_norm)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_grid")

    # 4. DBSCAN clustering
    execute(conn, f"SET enable_nestloop = off")
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_clustered AS
        SELECT
            operator_code, lac, bs_id, cell_id, tech_norm,
            snap_geom_3857, snap_obs_count, snap_x, snap_y,
            COALESCE(
                ST_ClusterDBSCAN(snap_geom_3857, eps => {CLUSTER_EPS_M}, minpoints => {CLUSTER_MIN_POINTS})
                OVER (PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm),
                -1
            ) AS cluster_id
        FROM {SCHEMA}._claude_centroid_grid
    """)
    execute(conn, "RESET enable_nestloop")
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_clustered
        (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_clustered")

    # 5. Label original points
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_labelled AS
        SELECT
            p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm,
            p.dev_id, p.obs_date, p.geom_3857,
            g.cluster_id
        FROM {SCHEMA}._claude_centroid_points p
        JOIN {SCHEMA}._claude_centroid_clustered g
          ON g.operator_code = p.operator_code
         AND g.lac = p.lac AND g.bs_id = p.bs_id
         AND g.cell_id = p.cell_id
         AND g.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND g.snap_geom_3857 = p.snap_geom_3857
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_labelled
        (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id, obs_date)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_labelled")

    # 6. Valid clusters (stable filter)
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_valid_clusters AS
        WITH cell_totals AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm,
                   COUNT(*) AS total_obs,
                   COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS total_dev_count
            FROM {SCHEMA}._claude_centroid_labelled
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        cluster_obs AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm, cluster_id,
                   COUNT(*) AS obs_count,
                   COUNT(DISTINCT dev_id) FILTER (WHERE dev_id IS NOT NULL) AS dev_count,
                   COUNT(DISTINCT obs_date) AS active_days
            FROM {SCHEMA}._claude_centroid_labelled
            WHERE cluster_id >= 0
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, cluster_id
        ),
        cluster_centers AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm, cluster_id,
                   ST_SetSRID(ST_MakePoint(
                       SUM(snap_x * snap_obs_count) / NULLIF(SUM(snap_obs_count), 0),
                       SUM(snap_y * snap_obs_count) / NULLIF(SUM(snap_obs_count), 0)
                   ), 3857) AS center_3857,
                   SUM(snap_obs_count) AS grid_obs
            FROM {SCHEMA}._claude_centroid_clustered
            WHERE cluster_id >= 0
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, cluster_id
        ),
        cluster_radius AS (
            SELECT g.operator_code, g.lac, g.bs_id, g.cell_id, g.tech_norm, c.cluster_id,
                   MAX(SQRT(POWER(g.snap_x - ST_X(c.center_3857), 2)
                          + POWER(g.snap_y - ST_Y(c.center_3857), 2))) AS radius_m
            FROM {SCHEMA}._claude_centroid_clustered g
            JOIN cluster_centers c USING (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
            WHERE g.cluster_id >= 0
            GROUP BY g.operator_code, g.lac, g.bs_id, g.cell_id, g.tech_norm, c.cluster_id
        ),
        stats AS (
            SELECT
                co.operator_code, co.lac, co.bs_id, co.cell_id, co.tech_norm, co.cluster_id,
                ST_X(ST_Transform(cc.center_3857, 4326)) AS center_lon,
                ST_Y(ST_Transform(cc.center_3857, 4326)) AS center_lat,
                cc.center_3857,
                co.obs_count, co.dev_count, co.active_days,
                COALESCE(cr.radius_m, 0) AS radius_m,
                ct.total_obs, ct.total_dev_count,
                co.obs_count::double precision / NULLIF(ct.total_obs, 0) AS share_ratio,
                (co.obs_count >= GREATEST({STABLE_MIN_OBS}, CEIL(ct.total_obs * {STABLE_MIN_SHARE})::int)
                 AND co.dev_count >= CASE
                     WHEN COALESCE(ct.total_dev_count, 0) <= {STABLE_SINGLE_DEV_MAX_TOTAL} THEN 1
                     ELSE {STABLE_MIN_DEVS}
                 END
                 AND co.active_days >= {STABLE_MIN_DAYS}
                ) AS is_valid
            FROM cluster_obs co
            JOIN cluster_centers cc USING (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
            JOIN cell_totals ct USING (operator_code, lac, bs_id, cell_id, tech_norm)
            LEFT JOIN cluster_radius cr USING (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
        ),
        ranked AS (
            SELECT *,
                COUNT(*) FILTER (WHERE is_valid) OVER (
                    PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
                ) AS valid_cluster_count,
                ROW_NUMBER() OVER (
                    PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm
                    ORDER BY obs_count DESC, dev_count DESC, cluster_id
                ) AS cluster_rank
            FROM stats WHERE is_valid
        )
        SELECT * FROM ranked
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_valid_clusters
        (operator_code, lac, bs_id, cell_id, tech_norm, cluster_id)
    """)
    execute(conn, f"ANALYZE {SCHEMA}._claude_centroid_valid_clusters")

    # 7. Write centroid detail
    execute(conn, f"DELETE FROM {SCHEMA}.claude_cell_centroid_detail WHERE batch_id = {batch_id}")
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_cell_centroid_detail (
            batch_id, operator_code, lac, bs_id, cell_id, tech_norm,
            cluster_id, is_primary, center_lon, center_lat,
            obs_count, dev_count, active_days, radius_m, share_ratio
        )
        SELECT
            {batch_id}, operator_code, lac, bs_id, cell_id, tech_norm,
            cluster_id, (cluster_rank = 1), center_lon, center_lat,
            obs_count, dev_count, active_days, radius_m, share_ratio
        FROM {SCHEMA}._claude_centroid_valid_clusters
        WHERE valid_cluster_count >= 2
    """)

    # 8. Update cell library with primary cluster centroid (for multi-centroid cells)
    execute(conn, f"""
        UPDATE {SCHEMA}.claude_cell_library t
        SET center_lon = v.center_lon,
            center_lat = v.center_lat
        FROM {SCHEMA}._claude_centroid_valid_clusters v
        WHERE t.batch_id = {batch_id}
          AND v.cluster_rank = 1
          AND v.valid_cluster_count >= 2
          AND v.operator_code = t.operator_code
          AND v.lac = t.lac AND v.bs_id = t.bs_id
          AND v.cell_id = t.cell_id
          AND v.tech_norm IS NOT DISTINCT FROM t.tech_norm
    """)

    # 9. Daily presence for classification
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_daily_presence AS
        SELECT p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm,
               p.obs_date, p.cluster_id, COUNT(*) AS obs_count
        FROM {SCHEMA}._claude_centroid_labelled p
        JOIN {SCHEMA}._claude_centroid_valid_clusters v
          ON v.operator_code = p.operator_code AND v.lac = p.lac
         AND v.bs_id = p.bs_id AND v.cell_id = p.cell_id
         AND v.tech_norm IS NOT DISTINCT FROM p.tech_norm
         AND v.cluster_id = p.cluster_id
        GROUP BY p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm, p.obs_date, p.cluster_id
    """)
    execute(conn, f"""
        CREATE INDEX ON {SCHEMA}._claude_centroid_daily_presence
        (operator_code, lac, bs_id, cell_id, tech_norm, obs_date, cluster_id)
    """)

    # 10. Classification
    execute(conn, f"""
        CREATE UNLOGGED TABLE {SCHEMA}._claude_centroid_classification AS
        WITH cluster_counts AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm,
                   COUNT(*) AS stable_cluster_count
            FROM {SCHEMA}._claude_centroid_valid_clusters
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        ),
        pair_distance AS (
            SELECT a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm,
                   MAX(ST_Distance(a.center_3857, b.center_3857)) AS max_pair_distance_m
            FROM {SCHEMA}._claude_centroid_valid_clusters a
            JOIN {SCHEMA}._claude_centroid_valid_clusters b
              ON b.operator_code = a.operator_code AND b.lac = a.lac
             AND b.bs_id = a.bs_id AND b.cell_id = a.cell_id
             AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
             AND b.cluster_id > a.cluster_id
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        pair_overlap AS (
            SELECT a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm,
                   MAX(overlap_days) AS max_overlap_days
            FROM (
                SELECT a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm,
                       COUNT(*) AS overlap_days
                FROM {SCHEMA}._claude_centroid_daily_presence a
                JOIN {SCHEMA}._claude_centroid_daily_presence b
                  ON b.operator_code = a.operator_code AND b.lac = a.lac
                 AND b.bs_id = a.bs_id AND b.cell_id = a.cell_id
                 AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
                 AND b.obs_date = a.obs_date AND b.cluster_id > a.cluster_id
                GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm,
                         a.cluster_id, b.cluster_id
            ) a
            GROUP BY a.operator_code, a.lac, a.bs_id, a.cell_id, a.tech_norm
        ),
        daily_primary AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm, obs_date, cluster_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm, obs_date
                       ORDER BY obs_count DESC, cluster_id
                   ) AS day_rank
            FROM {SCHEMA}._claude_centroid_daily_presence
        ),
        switch_summary AS (
            SELECT operator_code, lac, bs_id, cell_id, tech_norm,
                   COUNT(*) FILTER (WHERE prev_cid IS NOT NULL AND prev_cid <> cluster_id) AS cluster_switches
            FROM (
                SELECT *, LAG(cluster_id) OVER (
                    PARTITION BY operator_code, lac, bs_id, cell_id, tech_norm ORDER BY obs_date
                ) AS prev_cid
                FROM daily_primary WHERE day_rank = 1
            ) x
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        )
        SELECT
            c.operator_code, c.lac, c.bs_id, c.cell_id, c.tech_norm,
            COALESCE(cc.stable_cluster_count, 0) AS stable_cluster_count,
            COALESCE(pd.max_pair_distance_m, 0) AS max_pair_distance_m,
            COALESCE(po.max_overlap_days, 0) AS max_overlap_days,
            COALESCE(sw.cluster_switches, 0) AS cluster_switches,
            CASE
                WHEN COALESCE(cc.stable_cluster_count, 0) >= {MULTI_CLUSTER_MIN_COUNT} THEN 'multi_cluster'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                     AND COALESCE(sw.cluster_switches, 0) >= {MOVING_MIN_SWITCHES}
                     AND COALESCE(po.max_overlap_days, 0) >= {MOVING_MIN_OVERLAP_DAYS} THEN 'moving'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                     AND COALESCE(pd.max_pair_distance_m, 0) >= {MIGRATION_MIN_DIST_M}
                     AND COALESCE(po.max_overlap_days, 0) <= {MIGRATION_MAX_OVERLAP_DAYS} THEN 'migration'
                WHEN COALESCE(cc.stable_cluster_count, 0) = 2
                     AND COALESCE(pd.max_pair_distance_m, 0) >= {DUAL_CLUSTER_MIN_DIST_M} THEN 'dual_cluster'
                ELSE NULL
            END AS centroid_pattern
        FROM {SCHEMA}._claude_centroid_candidates c
        LEFT JOIN cluster_counts cc USING (operator_code, lac, bs_id, cell_id, tech_norm)
        LEFT JOIN pair_distance pd USING (operator_code, lac, bs_id, cell_id, tech_norm)
        LEFT JOIN pair_overlap po USING (operator_code, lac, bs_id, cell_id, tech_norm)
        LEFT JOIN switch_summary sw USING (operator_code, lac, bs_id, cell_id, tech_norm)
    """)

    # 11. Update cell library with classification
    execute(conn, f"""
        UPDATE {SCHEMA}.claude_cell_library t
        SET is_multi_centroid = (COALESCE(c.stable_cluster_count, 0) >= 2),
            is_dynamic = COALESCE(c.centroid_pattern = 'moving', FALSE),
            centroid_pattern = c.centroid_pattern,
            stable_cluster_count = COALESCE(c.stable_cluster_count, 0),
            max_pair_distance_m = COALESCE(c.max_pair_distance_m, 0),
            drift_pattern = CASE
                WHEN c.centroid_pattern = 'migration' THEN 'migration'
                ELSE t.drift_pattern
            END
        FROM {SCHEMA}._claude_centroid_classification c
        WHERE t.batch_id = {batch_id}
          AND c.operator_code = t.operator_code AND c.lac = t.lac
          AND c.bs_id = t.bs_id AND c.cell_id = t.cell_id
          AND c.tech_norm IS NOT DISTINCT FROM t.tech_norm
    """)

    detail_count = fetchone(conn, f"""
        SELECT count(*) FROM {SCHEMA}.claude_cell_centroid_detail WHERE batch_id = {batch_id}
    """)[0]

    # Cleanup
    for t in reversed(stages):
        execute(conn, f'DROP TABLE IF EXISTS {t}')

    dt = time.time() - t0
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_batch_stats (batch_id, step, duration_s, row_count, notes)
        VALUES ({batch_id}, 'dbscan', {dt:.2f}, {detail_count},
                'candidates={cand_count}, detail={detail_count}')
    """)
    print(f"  Batch {batch_id} DBSCAN: {detail_count} centroid details in {dt:.1f}s")
    return detail_count


# ──────────────────────────────────────────────
# Step 4: Publish BS library
# ──────────────────────────────────────────────

def publish_bs_library(conn, batch_id: int):
    t0 = time.time()
    execute(conn, f"DELETE FROM {SCHEMA}.claude_bs_library WHERE batch_id = {batch_id}")
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_bs_library (
            batch_id, operator_code, lac, bs_id, lifecycle_state,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            total_cells, qualified_cells, classification, is_multi_centroid
        )
        WITH cell_agg AS (
            SELECT operator_code, lac, bs_id,
                   COUNT(*) AS total_cells,
                   COUNT(*) FILTER (WHERE lifecycle_state IN ('qualified','excellent')) AS qualified_cells,
                   COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_cells,
                   COUNT(*) FILTER (WHERE is_multi_centroid) AS multi_centroid_cells,
                   COUNT(*) FILTER (WHERE is_dynamic) AS dynamic_cells,
                   COUNT(*) FILTER (WHERE is_collision) AS collision_cells
            FROM {SCHEMA}.claude_cell_library
            WHERE batch_id = {batch_id}
            GROUP BY operator_code, lac, bs_id
        ),
        bs_center AS (
            SELECT operator_code, lac, bs_id,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon)
                       FILTER (WHERE NOT is_collision AND NOT is_dynamic) AS center_lon,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat)
                       FILTER (WHERE NOT is_collision AND NOT is_dynamic) AS center_lat
            FROM {SCHEMA}.claude_cell_library
            WHERE batch_id = {batch_id} AND center_lon IS NOT NULL
            GROUP BY operator_code, lac, bs_id
        ),
        bs_dist AS (
            SELECT t.operator_code, t.lac, t.bs_id,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                       SQRT(POWER((t.center_lon - b.center_lon)*85300, 2)
                          + POWER((t.center_lat - b.center_lat)*111000, 2))
                   ) AS gps_p50_dist_m,
                   PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                       SQRT(POWER((t.center_lon - b.center_lon)*85300, 2)
                          + POWER((t.center_lat - b.center_lat)*111000, 2))
                   ) AS gps_p90_dist_m
            FROM {SCHEMA}.claude_cell_library t
            JOIN bs_center b USING (operator_code, lac, bs_id)
            WHERE t.batch_id = {batch_id} AND t.center_lon IS NOT NULL AND b.center_lon IS NOT NULL
            GROUP BY t.operator_code, t.lac, t.bs_id
        )
        SELECT
            {batch_id}, c.operator_code, c.lac, c.bs_id,
            CASE
                WHEN c.excellent_cells >= 1 THEN 'excellent'
                WHEN c.qualified_cells >= 2 THEN 'qualified'
                ELSE 'observing'
            END,
            bc.center_lon, bc.center_lat,
            bd.gps_p50_dist_m, bd.gps_p90_dist_m,
            c.total_cells, c.qualified_cells,
            CASE
                WHEN c.collision_cells > 0 THEN 'collision_bs'
                WHEN c.dynamic_cells > 0 THEN 'dynamic_bs'
                WHEN c.multi_centroid_cells > 0 THEN 'multi_centroid'
                WHEN COALESCE(bd.gps_p90_dist_m, 0) >= 2500 THEN 'large_spread'
                ELSE 'normal_spread'
            END,
            (c.multi_centroid_cells > 0)
        FROM cell_agg c
        LEFT JOIN bs_center bc USING (operator_code, lac, bs_id)
        LEFT JOIN bs_dist bd USING (operator_code, lac, bs_id)
    """)

    bs_count = fetchone(conn, f"""
        SELECT count(*) FROM {SCHEMA}.claude_bs_library WHERE batch_id = {batch_id}
    """)[0]

    dt = time.time() - t0
    execute(conn, f"""
        INSERT INTO {SCHEMA}.claude_batch_stats (batch_id, step, duration_s, row_count, notes)
        VALUES ({batch_id}, 'bs_library', {dt:.2f}, {bs_count}, NULL)
    """)
    print(f"  Batch {batch_id} BS library: {bs_count:,} BS in {dt:.1f}s")
    return bs_count


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def run_all():
    conn = get_conn()
    print("=" * 60)
    print("Fix4 Claude Pipeline — Two-stage Centroid + Expanded DBSCAN")
    print("=" * 60)

    setup_schema(conn)

    all_metrics = []

    for i, batch_date in enumerate(BATCH_DATES, 1):
        batch_t0 = time.time()
        print(f"\n--- Batch {i}: {batch_date} ---")

        window_rows = load_sliding_window(conn, i, batch_date)
        cell_count = compute_cell_metrics_and_publish(conn, i)
        detail_count = run_dbscan_analysis(conn, i)
        bs_count = publish_bs_library(conn, i)

        batch_dt = time.time() - batch_t0
        print(f"  Batch {i} total: {batch_dt:.1f}s")

        # Collect metrics for this batch
        metrics = fetchall(conn, f"""
            SELECT step, duration_s, row_count, notes
            FROM {SCHEMA}.claude_batch_stats WHERE batch_id = {i}
            ORDER BY step
        """)

        # Focus cell stats for this batch
        focus_stats = fetchall(conn, f"""
            SELECT f.source_bucket, cl.cell_id,
                   cl.total_gps_pts, cl.kept_pts, cl.removed_pts,
                   round(cl.p50_radius_m::numeric, 1) AS p50_m,
                   round(cl.p90_radius_m::numeric, 1) AS p90_m,
                   cl.is_multi_centroid, cl.centroid_pattern,
                   cl.stable_cluster_count
            FROM {SCHEMA}.claude_cell_library cl
            JOIN {SCHEMA}.focus_cells_shared f
              ON f.operator_code = cl.operator_code AND f.lac = cl.lac
             AND f.cell_id = cl.cell_id AND f.tech_norm = cl.tech_norm
            WHERE cl.batch_id = {i}
            ORDER BY f.source_bucket, cl.p90_radius_m DESC
        """)

        all_metrics.append({
            'batch_id': i,
            'batch_date': str(batch_date),
            'total_duration_s': round(batch_dt, 2),
            'steps': metrics,
            'focus_cells': focus_stats,
        })

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    summary = fetchall(conn, f"""
        SELECT batch_id, step, duration_s, row_count
        FROM {SCHEMA}.claude_batch_stats
        ORDER BY batch_id, step
    """)
    for row in summary:
        print(f"  batch={row['batch_id']} step={row['step']:<15} "
              f"time={row['duration_s']:.1f}s rows={row['row_count']}")

    # Write metrics to JSON
    output_path = '/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/fix4/claude/metrics_summary.json'
    with open(output_path, 'w') as f:
        json.dump(all_metrics, f, indent=2, default=str)
    print(f"\nMetrics written to {output_path}")

    conn.close()


if __name__ == '__main__':
    run_all()
