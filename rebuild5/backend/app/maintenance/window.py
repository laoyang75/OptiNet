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

from ..core.database import execute, fetchall
from ..core.parallel import NUM_WORKERS_INSERT, parallel_execute
from ..profile.pipeline import relation_exists


# ---------------------------------------------------------------------------
# 5.0a  Refresh sliding window from enriched_records
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
    """Build continuous sliding window: previous window + current batch enriched_records.

    Trims to last WINDOW_RETENTION_DAYS days. This ensures all maintenance
    metrics (active_days_30d, consecutive_inactive_days, drift, etc.) are
    computed over a true long-term window, not a single-batch snapshot.

    并行策略：logged 持久窗口 + multiprocessing 4进程（稳定优先）
    """
    if not relation_exists('rebuild5.enriched_records'):
        return

    # Step 1: Add current batch enriched_records to window
    # (previous batches' data already in the window from earlier runs)
    execute('DELETE FROM rebuild5.cell_sliding_window WHERE batch_id = %s', (batch_id,))
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
        """.format(batch_id=batch_id),  # 预内联 batch_id，保留 {shard_filter}
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
    """Materialize the base per-cell metrics before radius/activity/drift joins."""
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_base')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_metrics_base AS
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
            COUNT(*) AS window_obs_count
        FROM rebuild5.cell_sliding_window
        GROUP BY operator_code, lac, bs_id, cell_id, tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_metrics_base SET (autovacuum_enabled = false)")
    execute('ANALYZE rebuild5.cell_metrics_base')


def build_cell_radius_stats() -> None:
    """Materialize per-cell radius percentiles off the already-computed base centroid."""
    execute('DROP TABLE IF EXISTS rebuild5.cell_radius_stats')
    execute(
        """
        CREATE UNLOGGED TABLE rebuild5.cell_radius_stats AS
        SELECT
            w.operator_code, w.lac, w.bs_id, w.cell_id, w.tech_norm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
                   + POWER((w.lat_final - m.center_lat) * 111000, 2))
            ) AS p50_radius_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
                   + POWER((w.lat_final - m.center_lat) * 111000, 2))
            ) AS p90_radius_m
        FROM rebuild5.cell_sliding_window w
        JOIN rebuild5.cell_metrics_base m
          ON m.operator_code = w.operator_code
         AND m.lac = w.lac
         AND m.bs_id = w.bs_id
         AND m.cell_id = w.cell_id
         AND m.tech_norm IS NOT DISTINCT FROM w.tech_norm
        WHERE w.lon_final IS NOT NULL
          AND w.gps_valid
          AND m.center_lon IS NOT NULL
          AND m.center_lat IS NOT NULL
        GROUP BY w.operator_code, w.lac, w.bs_id, w.cell_id, w.tech_norm
        """
    )
    execute("ALTER TABLE rebuild5.cell_radius_stats SET (autovacuum_enabled = false)")
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
    drift_join = 'TRUE' if relation_exists('rebuild5.cell_drift_stats') else 'FALSE'
    execute('DROP TABLE IF EXISTS rebuild5.cell_metrics_window')
    execute(
        f"""
        CREATE UNLOGGED TABLE rebuild5.cell_metrics_window AS
        SELECT
            m.batch_id, m.operator_code, m.lac, m.bs_id, m.cell_id, m.tech_norm,
            m.center_lon, m.center_lat,
            r.p50_radius_m, r.p90_radius_m,
            m.independent_obs, m.distinct_dev_id, m.gps_valid_count, m.active_days,
            m.observed_span_hours,
            m.rsrp_avg, m.rsrq_avg, m.sinr_avg, m.pressure_avg,
            m.max_event_time, m.window_obs_count,
            COALESCE(a.active_days_30d, 0)::integer AS active_days_30d,
            COALESCE(a.consecutive_inactive_days, 0) AS consecutive_inactive_days,
            d.max_spread_m,
            d.net_drift_m,
            d.drift_ratio
        FROM rebuild5.cell_metrics_base m
        LEFT JOIN rebuild5.cell_radius_stats r
          ON r.operator_code = m.operator_code
         AND r.lac = m.lac
         AND r.bs_id = m.bs_id
         AND r.cell_id = m.cell_id
         AND r.tech_norm IS NOT DISTINCT FROM m.tech_norm
        LEFT JOIN rebuild5.cell_activity_stats a
          ON a.operator_code = m.operator_code
         AND a.lac = m.lac
         AND a.cell_id = m.cell_id
         AND a.tech_norm IS NOT DISTINCT FROM m.tech_norm
        LEFT JOIN rebuild5.cell_drift_stats d
          ON {drift_join}
         AND d.batch_id = m.batch_id
         AND d.operator_code = m.operator_code
         AND d.lac = m.lac
         AND d.cell_id = m.cell_id
         AND d.tech_norm IS NOT DISTINCT FROM m.tech_norm
        WHERE m.batch_id = {batch_id}
        """
    )
    execute("ALTER TABLE rebuild5.cell_metrics_window SET (autovacuum_enabled = false)")
    execute('ANALYZE rebuild5.cell_metrics_window')


def recalculate_cell_metrics(*, batch_id: int) -> None:
    """Backward-compatible wrapper for callers that still expect one entrypoint."""
    build_cell_metrics_base(batch_id=batch_id)
    build_cell_radius_stats()
    build_cell_activity_stats()
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
