"""Step 5.0 — Sliding window refresh and cell metric recalculation.

Responsibilities:
1. Merge enriched_records into cell_sliding_window
2. Build daily centroids (for drift classification in cell_maintain.py)
3. Recalculate per-cell metrics into cell_metrics_window (intermediate table)

=== 并行策略（基准测试验证，beijing_7d 10% 抽样，~250万行）===

  5.0a sliding_window INSERT（IO密集型）：
    - 策略 B+C：UNLOGGED + multiprocessing 分片，12进程
    - 基线 8.1s → 最优 4.8s（1.7x）

  5.0b daily_centroids PERCENTILE_CONT（CPU密集型）：
    - 策略 A：CTAS，利用 PG 内置并行 worker（max 16）
    - 基线 11.3s → CTAS 4.5s（2.5x）优于 8进程 8.0s

  5.0c cell_metrics PERCENTILE_CONT（CPU密集型，最重）：
    - 策略 A：CTAS，基线 24.8s → CTAS 11.1s（2.2x）优于 8进程 16.7s
    - P50/P90 半径 UPDATE：单线程执行（无并行收益，数据量小）
"""
from __future__ import annotations

from typing import Any

from ..core.database import execute
from ..core.parallel import parallel_execute
from ..profile.logic import (
    build_core_mad_k_sql,
    load_antitoxin_params,
    load_core_mad_filter_params,
    load_gps_anomaly_filter_params,
)
from ..profile.pipeline import relation_exists


# ---------------------------------------------------------------------------
# 5.0a  Refresh sliding window from Step 4 facts
# ---------------------------------------------------------------------------

WINDOW_RETENTION_DAYS = 14
WINDOW_MIN_OBS = 1000
# cell_sliding_window is a logged persistent window table. In production-scale
# reruns, using the same 12-process fan-out as UNLOGGED staging tables can
# trigger relation-extension failures while multiple workers compete to extend
# the same heap file. Keep Step 4 on the higher IO setting, but use a more
# conservative worker count here.
SLIDING_WINDOW_INSERT_WORKERS = 4


def refresh_sliding_window(*, batch_id: int) -> None:
    """Build continuous sliding window from Step4 facts for the current batch.

    Trims to last WINDOW_RETENTION_DAYS days. This ensures all maintenance
    metrics (active_days_30d, consecutive_inactive_days, drift, etc.) are
    computed over a true long-term window, not a single-batch snapshot.

    并行策略：logged 持久窗口 + multiprocessing 4进程（稳定优先）
    """
    has_enriched = relation_exists('rebuild5.enriched_records')
    has_snapshot_seeds = relation_exists('rebuild5.snapshot_seed_records')
    if not has_enriched and not has_snapshot_seeds:
        return

    # Step 1: Add current batch Step 4 facts to the window.
    # `enriched_records` carries Path-A records; `snapshot_seed_records` bridges
    # newly published cells so their current-batch evidence also reaches Step 5.
    execute('DELETE FROM rebuild5.cell_sliding_window WHERE batch_id = %s', (batch_id,))
    if has_enriched:
        parallel_execute(
            """
            INSERT INTO rebuild5.cell_sliding_window (
                batch_id, source_row_uid, record_id,
                operator_code, lac, bs_id, cell_id, tech_norm,
                dev_id, event_time_std, gps_valid,
                lon_final, lat_final,
                rsrp_final, rsrq_final, sinr_final, pressure_final,
                source_type
            )
            SELECT
                {batch_id}, source_row_uid, record_id,
                operator_code, lac, bs_id, cell_id, tech_norm,
                dev_id, event_time_std, gps_valid,
                lon_final, lat_final,
                rsrp_final, rsrq_final, sinr_final, pressure_final,
                'enriched'
            FROM rebuild5.enriched_records
            WHERE batch_id = {batch_id}
              {{shard_filter}}
            """.format(batch_id=batch_id),
            num_workers=SLIDING_WINDOW_INSERT_WORKERS,
            where_prefix='AND',
        )
    if has_snapshot_seeds:
        parallel_execute(
            """
            INSERT INTO rebuild5.cell_sliding_window (
                batch_id, source_row_uid, record_id,
                operator_code, lac, bs_id, cell_id, tech_norm,
                dev_id, event_time_std, gps_valid,
                lon_final, lat_final,
                rsrp_final, rsrq_final, sinr_final, pressure_final,
                source_type
            )
            SELECT
                {batch_id}, source_row_uid, record_id,
                operator_code, lac, bs_id, cell_id, tech_norm,
                dev_id, event_time_std, gps_valid,
                lon_final, lat_final,
                rsrp_final, rsrq_final, sinr_final, pressure_final,
                'snapshot_seed'
            FROM rebuild5.snapshot_seed_records
            WHERE batch_id = {batch_id}
              {{shard_filter}}
            """.format(batch_id=batch_id),
            num_workers=SLIDING_WINDOW_INSERT_WORKERS,
            where_prefix='AND',
        )

    # Step 2: Trim window — quantity-priority retention.
    # Keep the larger scope of:
    #   1) last WINDOW_RETENTION_DAYS days
    #   2) latest WINDOW_MIN_OBS observations per cell
    execute(
        f"""
        WITH ranked AS (
            SELECT
                ctid,
                operator_code,
                lac,
                cell_id,
                tech_norm,
                event_time_std,
                ROW_NUMBER() OVER (
                    PARTITION BY operator_code, lac, cell_id, tech_norm
                    ORDER BY event_time_std DESC, source_row_uid DESC
                ) AS obs_rank,
                MAX(event_time_std) OVER (
                    PARTITION BY operator_code, lac, cell_id, tech_norm
                ) AS latest_event_time
            FROM rebuild5.cell_sliding_window
        ),
        keep_rows AS (
            SELECT ctid
            FROM ranked
            WHERE event_time_std >= latest_event_time - INTERVAL '{WINDOW_RETENTION_DAYS} days'
               OR obs_rank <= {WINDOW_MIN_OBS}
        )
        DELETE FROM rebuild5.cell_sliding_window w
        WHERE NOT EXISTS (
            SELECT 1 FROM keep_rows k WHERE k.ctid = w.ctid
        )
        """
    )


# ---------------------------------------------------------------------------
# 5.0b  Build daily centroids for drift classification
# ---------------------------------------------------------------------------

def build_daily_centroids(*, batch_id: int) -> None:
    """Per-cell per-day centroid from sliding window.

    Used by cell_maintain.py to compute max_spread / net_drift / ratio.

    并行策略：UNLOGGED CTAS（PG内置并行 worker，避免额外 INSERT 开销）
    基准测试：在 bench 样本上持续优于 INSERT INTO ... SELECT。
    """
    execute('DROP TABLE IF EXISTS rebuild5.cell_daily_centroid')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_daily_centroid AS
        SELECT
            {batch_id}::int AS batch_id,
            operator_code, lac, bs_id, cell_id, tech_norm,
            DATE(event_time_std) AS obs_date,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
                FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
                FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
            COUNT(*) AS obs_count,
            COUNT(DISTINCT dev_id) AS dev_count
        FROM rebuild5.cell_sliding_window
        WHERE lon_final IS NOT NULL
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm, DATE(event_time_std)
        """
    )
    execute("ALTER TABLE rebuild5.cell_daily_centroid SET (autovacuum_enabled = false)")
    execute('ANALYZE rebuild5.cell_daily_centroid')


# ---------------------------------------------------------------------------
# 5.0c  Recalculate per-cell metrics from sliding window
# ---------------------------------------------------------------------------

def build_cell_metrics_base(*, batch_id: int) -> None:
    """Materialize the base per-cell metrics before radius/activity/drift joins.

    Also computes activity stats (active_days_30d, consecutive_inactive_days)
    in the same pass to avoid a redundant full scan of cell_sliding_window.
    """
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_base')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_metrics_base AS
        WITH window_max AS (
            SELECT MAX(event_time_std) AS ref_time FROM rebuild5.cell_sliding_window
        )
        SELECT
            {batch_id}::int AS batch_id,
            operator_code, lac, bs_id, cell_id, tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
                FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
                FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
            COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text))
                AS independent_obs,
            COUNT(DISTINCT dev_id) AS distinct_dev_id,
            COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid) AS gps_valid_count,
            COUNT(DISTINCT DATE(event_time_std)) AS active_days,
            (EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0)::double precision
                AS observed_span_hours,
            AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1) AS rsrp_avg,
            AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10) AS rsrq_avg,
            AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40) AS sinr_avg,
            AVG(pressure_final::double precision)
                FILTER (WHERE pressure_final IS NOT NULL) AS pressure_avg,
            MAX(event_time_std) AS max_event_time,
            COUNT(*) AS window_obs_count,
            COUNT(DISTINCT DATE(event_time_std))
                FILTER (WHERE event_time_std >= (SELECT ref_time - INTERVAL '30 days' FROM window_max))
                AS active_days_30d,
            EXTRACT(DAY FROM (SELECT ref_time FROM window_max) - MAX(event_time_std))::integer
                AS consecutive_inactive_days
        FROM rebuild5.cell_sliding_window
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_metrics_base SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_metrics_base_key
        ON rebuild5.cell_metrics_base (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_metrics_base')


def build_cell_core_gps_stats(*, batch_id: int) -> None:
    """Build Step5 core GPS stats using MAD filtering around an initial median center.

    Step 4 → Step 5 闭环：通过 gps_anomaly_log（Step 4 已识别的异常点）按 cell 级占比策略过滤：
      - 异常占比 < max_anomaly_ratio AND 异常点数 ≤ max_anomaly_count → 偶发飞跃，dedup 时直接排除
      - 否则保留所有点，让 MAD/DBSCAN 后续处理（多质心 / 碰撞场景下的稳定副簇）
    """
    antitoxin = load_antitoxin_params()
    mad_filter = load_core_mad_filter_params(antitoxin)
    anomaly_filter = load_gps_anomaly_filter_params(antitoxin)
    effective_k_sql = build_core_mad_k_sql('m.total_pts', mad_filter)
    max_anomaly_ratio = float(anomaly_filter['max_anomaly_ratio'])
    max_anomaly_count = int(anomaly_filter['max_anomaly_count'])

    execute('DROP TABLE IF EXISTS rebuild5.cell_core_gps_day_dedup')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_core_gps_day_dedup AS
        WITH anomaly_uids AS (
            -- 去重 Step 4 的 anomaly 标记，避免后续 LEFT JOIN 产生 fan-out
            SELECT DISTINCT source_row_uid
            FROM rebuild5.gps_anomaly_log
            WHERE distance_to_donor_m > anomaly_threshold_m
        ),
        dedup_with_anomaly AS (
            SELECT DISTINCT ON (
                w.operator_code,
                w.lac,
                w.bs_id,
                w.cell_id,
                w.tech_norm,
                COALESCE(NULLIF(w.dev_id, ''), w.record_id),
                DATE(w.event_time_std)
            )
                w.operator_code,
                w.lac,
                w.bs_id,
                w.cell_id,
                w.tech_norm,
                COALESCE(NULLIF(w.dev_id, ''), w.record_id) AS dedup_dev_id,
                DATE(w.event_time_std) AS obs_date,
                w.event_time_std,
                w.lon_final,
                w.lat_final,
                (au.source_row_uid IS NOT NULL) AS is_anomaly
            FROM rebuild5.cell_sliding_window w
            LEFT JOIN anomaly_uids au ON au.source_row_uid = w.source_row_uid
            WHERE w.lon_final IS NOT NULL
              AND w.lat_final IS NOT NULL
              AND w.gps_valid
              AND w.event_time_std IS NOT NULL
            ORDER BY
                w.operator_code,
                w.lac,
                w.bs_id,
                w.cell_id,
                w.tech_norm,
                COALESCE(NULLIF(w.dev_id, ''), w.record_id),
                DATE(w.event_time_std),
                w.event_time_std,
                w.record_id
        ),
        filter_decision AS (
            SELECT
                operator_code, lac, bs_id, cell_id, tech_norm,
                (COUNT(*) FILTER (WHERE is_anomaly) > 0
                 AND COUNT(*) FILTER (WHERE is_anomaly) <= {max_anomaly_count}
                 AND COUNT(*) FILTER (WHERE is_anomaly)::double precision
                     / NULLIF(COUNT(*), 0) < {max_anomaly_ratio}
                ) AS exclude_anomaly
            FROM dedup_with_anomaly
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        )
        SELECT
            d.operator_code, d.lac, d.bs_id, d.cell_id, d.tech_norm,
            d.dedup_dev_id, d.obs_date, d.event_time_std,
            d.lon_final, d.lat_final
        FROM dedup_with_anomaly d
        LEFT JOIN filter_decision f
          ON f.operator_code = d.operator_code
         AND f.lac = d.lac
         AND f.bs_id IS NOT DISTINCT FROM d.bs_id
         AND f.cell_id = d.cell_id
         AND f.tech_norm IS NOT DISTINCT FROM d.tech_norm
        WHERE NOT (COALESCE(f.exclude_anomaly, FALSE) AND d.is_anomaly)
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_gps_day_dedup SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_gps_day_dedup_key
        ON rebuild5.cell_core_gps_day_dedup (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_gps_day_dedup')
    execute('DROP TABLE IF EXISTS rebuild5.cell_core_initial_center')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_core_initial_center AS
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS center_lon0,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) AS center_lat0
        FROM rebuild5.cell_core_gps_day_dedup
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_initial_center SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_initial_center_key
        ON rebuild5.cell_core_initial_center (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_initial_center')

    execute('DROP TABLE IF EXISTS rebuild5.cell_core_point_distance')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_core_point_distance AS
        SELECT
            w.operator_code,
            w.lac,
            w.bs_id,
            w.cell_id,
            w.tech_norm,
            w.obs_date,
            w.event_time_std,
            w.dedup_dev_id,
            w.lon_final,
            w.lat_final,
            SQRT(POWER((w.lon_final - c.center_lon0) * 85300, 2)
               + POWER((w.lat_final - c.center_lat0) * 111000, 2)) AS dist_to_center0_m
        FROM rebuild5.cell_core_gps_day_dedup w
        JOIN rebuild5.cell_core_initial_center c
          ON c.operator_code = w.operator_code
         AND c.lac = w.lac
         AND c.bs_id IS NOT DISTINCT FROM w.bs_id
         AND c.cell_id = w.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM w.tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_point_distance SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_point_distance_key
        ON rebuild5.cell_core_point_distance (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_point_distance')

    execute('DROP TABLE IF EXISTS rebuild5.cell_core_mad_stats')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_core_mad_stats AS
        WITH med AS (
            SELECT
                operator_code,
                lac,
                bs_id,
                cell_id,
                tech_norm,
                COUNT(*) AS total_pts,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dist_to_center0_m) AS med_dist_m
            FROM rebuild5.cell_core_point_distance
            GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        )
        SELECT
            d.operator_code,
            d.lac,
            d.bs_id,
            d.cell_id,
            d.tech_norm,
            m.total_pts,
            m.med_dist_m,
            COALESCE(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.dist_to_center0_m - m.med_dist_m)),
                0
            ) AS mad_dist_m,
            {effective_k_sql} AS effective_k_mad,
            (m.med_dist_m + ({effective_k_sql} * COALESCE(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.dist_to_center0_m - m.med_dist_m)),
                0
            ))) AS keep_threshold_m,
            {int(mad_filter['min_pts'])} AS min_pts
        FROM rebuild5.cell_core_point_distance d
        JOIN med m
          ON m.operator_code = d.operator_code
         AND m.lac = d.lac
         AND m.bs_id IS NOT DISTINCT FROM d.bs_id
         AND m.cell_id = d.cell_id
         AND m.tech_norm IS NOT DISTINCT FROM d.tech_norm
        GROUP BY
            d.operator_code, d.lac, d.bs_id, d.cell_id, d.tech_norm,
            m.total_pts, m.med_dist_m
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_mad_stats SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_mad_stats_key
        ON rebuild5.cell_core_mad_stats (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_mad_stats')

    execute('DROP TABLE IF EXISTS rebuild5.cell_core_points')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_core_points AS
        SELECT
            d.operator_code,
            d.lac,
            d.bs_id,
            d.cell_id,
            d.tech_norm,
            d.obs_date,
            d.event_time_std,
            d.dedup_dev_id,
            d.lon_final,
            d.lat_final,
            s.total_pts,
            s.med_dist_m,
            s.mad_dist_m,
            s.effective_k_mad,
            s.keep_threshold_m,
            CASE
                -- min_pts 是统计学下限（默认 4），不是 Step 3 资格门槛。
                -- 已晋升 cell 进 Step 5 后总应走 MAD；只有点数少到 PERCENTILE_CONT 算不出有意义 MAD 时才跳过。
                WHEN s.total_pts < s.min_pts THEN TRUE
                ELSE d.dist_to_center0_m <= s.keep_threshold_m
            END AS is_core
        FROM rebuild5.cell_core_point_distance d
        JOIN rebuild5.cell_core_mad_stats s
          ON s.operator_code = d.operator_code
         AND s.lac = d.lac
         AND s.bs_id IS NOT DISTINCT FROM d.bs_id
         AND s.cell_id = d.cell_id
         AND s.tech_norm IS NOT DISTINCT FROM d.tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_points SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_points_key
        ON rebuild5.cell_core_points (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_points')

    execute('DROP TABLE IF EXISTS rebuild5.cell_core_gps_stats')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_core_gps_stats AS
        SELECT
            {batch_id}::int AS batch_id,
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            COUNT(*) FILTER (WHERE is_core) AS core_gps_valid_count,
            COUNT(DISTINCT obs_date) FILTER (WHERE is_core) AS core_active_days,
            (EXTRACT(EPOCH FROM MAX(event_time_std) FILTER (WHERE is_core)
                - MIN(event_time_std) FILTER (WHERE is_core)) / 3600.0)::double precision
                AS core_observed_span_hours,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE is_core) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE is_core) AS center_lat
        FROM rebuild5.cell_core_points
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_core_gps_stats SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_core_gps_stats_key
        ON rebuild5.cell_core_gps_stats (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_core_gps_stats')


def build_cell_radius_stats() -> None:
    """Materialize per-cell radius percentiles from the MAD-filtered center."""
    execute('DROP TABLE IF EXISTS rebuild5.cell_radius_stats')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_radius_stats AS
        WITH with_dist AS (
            SELECT
                p.operator_code,
                p.lac,
                p.bs_id,
                p.cell_id,
                p.tech_norm,
                p.is_core,
                SQRT(POWER((p.lon_final - c.center_lon) * 85300, 2)
                   + POWER((p.lat_final - c.center_lat) * 111000, 2)) AS dist_m
            FROM rebuild5.cell_core_points p
            JOIN rebuild5.cell_core_gps_stats c
              ON c.operator_code = p.operator_code
             AND c.lac = p.lac
             AND c.bs_id IS NOT DISTINCT FROM p.bs_id
             AND c.cell_id = p.cell_id
             AND c.tech_norm IS NOT DISTINCT FROM p.tech_norm
            WHERE c.center_lon IS NOT NULL
              AND c.center_lat IS NOT NULL
        )
        SELECT
            operator_code,
            lac,
            bs_id,
            cell_id,
            tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dist_m)
                FILTER (WHERE is_core) AS p50_radius_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY dist_m)
                FILTER (WHERE is_core) AS p90_radius_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY dist_m) AS raw_p90_radius_m,
            COUNT(*) FILTER (WHERE is_core) AS core_gps_valid_count,
            COUNT(*) AS raw_gps_valid_count,
            CASE
                WHEN COUNT(*) <= 0 THEN 0::double precision
                ELSE GREATEST(
                    0::double precision,
                    1::double precision
                        - COUNT(*) FILTER (WHERE is_core)::double precision / COUNT(*)
                )
            END AS core_outlier_ratio
        FROM with_dist
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_radius_stats SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX idx_cell_radius_stats_key
        ON rebuild5.cell_radius_stats (operator_code, lac, bs_id, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rebuild5.cell_radius_stats')


def build_cell_activity_stats() -> None:
    """Materialize 30d activity and inactivity counters from the sliding window."""
    execute('DROP TABLE IF EXISTS rebuild5.cell_activity_stats')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_activity_stats AS
        WITH window_max AS (
            SELECT MAX(event_time_std) AS ref_time FROM rebuild5.cell_sliding_window
        )
        SELECT
            operator_code, lac, cell_id, tech_norm,
            COUNT(DISTINCT DATE(event_time_std))
                FILTER (WHERE event_time_std >= (SELECT ref_time - INTERVAL '30 days' FROM window_max))
                AS active_days_30d,
            EXTRACT(DAY FROM (SELECT ref_time FROM window_max) - MAX(event_time_std))::integer
                AS consecutive_inactive_days
        FROM rebuild5.cell_sliding_window
        GROUP BY operator_code, lac, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_activity_stats SET (autovacuum_enabled = false)")
    execute('ANALYZE rebuild5.cell_activity_stats')


def build_cell_metrics_window(*, batch_id: int) -> None:
    """Join the materialized metric stages into the final cell_metrics_window table."""
    has_drift = relation_exists('rebuild5.cell_drift_stats')
    drift_select = (
        'd.max_spread_m,\n'
        '            d.net_drift_m,\n'
        '            d.drift_ratio'
        if has_drift else
        'NULL::double precision AS max_spread_m,\n'
        '            NULL::double precision AS net_drift_m,\n'
        '            NULL::double precision AS drift_ratio'
    )
    drift_join_sql = (
        """
        LEFT JOIN rebuild5.cell_drift_stats d
          ON d.batch_id = m.batch_id
         AND d.operator_code = m.operator_code
         AND d.lac = m.lac
         AND d.cell_id = m.cell_id
         AND d.tech_norm IS NOT DISTINCT FROM m.tech_norm
        """
        if has_drift else
        ''
    )
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_window')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_metrics_window AS
        SELECT
            m.batch_id, m.operator_code, m.lac, m.bs_id, m.cell_id, m.tech_norm,
            COALESCE(cg.center_lon, m.center_lon) AS center_lon,
            COALESCE(cg.center_lat, m.center_lat) AS center_lat,
            r.p50_radius_m, r.p90_radius_m,
            r.raw_p90_radius_m,
            COALESCE(r.core_outlier_ratio, 0)::double precision AS core_outlier_ratio,
            m.independent_obs, m.distinct_dev_id,
            COALESCE(cg.core_gps_valid_count, m.gps_valid_count) AS gps_valid_count,
            COALESCE(cg.core_active_days, m.active_days) AS active_days,
            COALESCE(cg.core_observed_span_hours, m.observed_span_hours) AS observed_span_hours,
            m.rsrp_avg, m.rsrq_avg, m.sinr_avg, m.pressure_avg,
            m.max_event_time, m.window_obs_count,
            COALESCE(m.active_days_30d, 0)::integer AS active_days_30d,
            COALESCE(m.consecutive_inactive_days, 0) AS consecutive_inactive_days,
            {drift_select}
        FROM rebuild5.cell_metrics_base m
        LEFT JOIN rebuild5.cell_radius_stats r
          ON r.operator_code = m.operator_code
         AND r.lac = m.lac
         AND r.bs_id = m.bs_id
         AND r.cell_id = m.cell_id
         AND r.tech_norm IS NOT DISTINCT FROM m.tech_norm
        LEFT JOIN rebuild5.cell_core_gps_stats cg
          ON cg.batch_id = m.batch_id
         AND cg.operator_code = m.operator_code
         AND cg.lac = m.lac
         AND cg.bs_id IS NOT DISTINCT FROM m.bs_id
         AND cg.cell_id = m.cell_id
         AND cg.tech_norm IS NOT DISTINCT FROM m.tech_norm
        {drift_join_sql}
        WHERE m.batch_id = {batch_id}
        """
    )
    execute("ALTER TABLE rebuild5.cell_metrics_window SET (autovacuum_enabled = false)")
    execute('ANALYZE rebuild5.cell_metrics_window')


def recalculate_cell_metrics(*, batch_id: int) -> None:
    """Backward-compatible wrapper for callers that still expect one entrypoint."""
    build_cell_metrics_base(batch_id=batch_id)
    build_cell_core_gps_stats(batch_id=batch_id)
    build_cell_radius_stats()
    build_cell_metrics_window(batch_id=batch_id)


def _update_activity_metrics(*, batch_id: int) -> None:
    """Compute active_days_30d and consecutive_inactive_days per cell.

    Uses data-driven time reference (max event_time in window) instead of NOW()
    to support historical data replay correctly.
    """
    execute(
        """
        WITH window_max AS (
            SELECT MAX(event_time_std) AS ref_time FROM rebuild5.cell_sliding_window
        ),
        activity AS (
            SELECT
                operator_code, lac, cell_id, tech_norm,
                COUNT(DISTINCT DATE(event_time_std))
                    FILTER (WHERE event_time_std >= (SELECT ref_time - INTERVAL '30 days' FROM window_max))
                    AS active_days_30d,
                EXTRACT(DAY FROM (SELECT ref_time FROM window_max) - MAX(event_time_std))::integer
                    AS consecutive_inactive_days
            FROM rebuild5.cell_sliding_window
            GROUP BY operator_code, lac, cell_id, tech_norm
        )
        UPDATE rebuild5.cell_metrics_window AS t
        SET active_days_30d = COALESCE(a.active_days_30d, 0),
            consecutive_inactive_days = COALESCE(a.consecutive_inactive_days, 0)
        FROM activity a
        WHERE t.batch_id = %s
          AND t.operator_code = a.operator_code
          AND t.lac = a.lac AND t.cell_id = a.cell_id
          AND t.tech_norm IS NOT DISTINCT FROM a.tech_norm
        """,
        (batch_id,),
    )
