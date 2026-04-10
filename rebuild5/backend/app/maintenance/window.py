"""Step 5.0 — Sliding window refresh and cell metric recalculation.

Responsibilities:
1. Merge enriched_records into cell_sliding_window
2. Build daily centroids (for drift classification in cell_maintain.py)
3. Recalculate per-cell metrics into cell_metrics_window (intermediate table)
"""
from __future__ import annotations

from typing import Any

from ..core.database import execute, fetchall
from ..profile.pipeline import relation_exists


# ---------------------------------------------------------------------------
# 5.0a  Refresh sliding window from enriched_records
# ---------------------------------------------------------------------------

WINDOW_RETENTION_DAYS = 30


def refresh_sliding_window(*, batch_id: int) -> None:
    """Build continuous sliding window: previous window + current batch enriched_records.

    Trims to last WINDOW_RETENTION_DAYS days. This ensures all maintenance
    metrics (active_days_30d, consecutive_inactive_days, drift, etc.) are
    computed over a true long-term window, not a single-batch snapshot.
    """
    if not relation_exists('rebuild5.enriched_records'):
        return

    # Step 1: Add current batch enriched_records to window
    # (previous batches' data already in the window from earlier runs)
    execute('DELETE FROM rebuild5.cell_sliding_window WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.cell_sliding_window (
            batch_id, source_row_uid, record_id,
            operator_code, lac, bs_id, cell_id,
            dev_id, event_time_std, gps_valid,
            lon_final, lat_final,
            rsrp_final, rsrq_final, sinr_final, pressure_final,
            source_type
        )
        SELECT
            %s, source_row_uid, record_id,
            operator_code, lac, bs_id, cell_id,
            dev_id, event_time_std, gps_valid,
            lon_final, lat_final,
            rsrp_final, rsrq_final, sinr_final, pressure_final,
            'enriched'
        FROM rebuild5.enriched_records
        WHERE batch_id = %s
        """,
        (batch_id, batch_id),
    )

    # Step 2: Trim window — use data-driven time reference (not NOW()) for historical replay
    execute(
        f"""
        DELETE FROM rebuild5.cell_sliding_window
        WHERE event_time_std < (
            SELECT MAX(event_time_std) - INTERVAL '{WINDOW_RETENTION_DAYS} days'
            FROM rebuild5.cell_sliding_window
        )
        """
    )


# ---------------------------------------------------------------------------
# 5.0b  Build daily centroids for drift classification
# ---------------------------------------------------------------------------

def build_daily_centroids(*, batch_id: int) -> None:
    """Per-cell per-day centroid from sliding window.

    Used by cell_maintain.py to compute max_spread / net_drift / ratio.
    """
    execute('DELETE FROM rebuild5.cell_daily_centroid WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.cell_daily_centroid (
            batch_id, operator_code, lac, bs_id, cell_id,
            obs_date, center_lon, center_lat, obs_count, dev_count
        )
        SELECT
            %s,
            operator_code, lac, bs_id, cell_id,
            DATE(event_time_std) AS obs_date,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
                FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
                FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
            COUNT(*) AS obs_count,
            COUNT(DISTINCT dev_id) AS dev_count
        FROM rebuild5.cell_sliding_window
        WHERE lon_final IS NOT NULL
        GROUP BY operator_code, lac, bs_id, cell_id, DATE(event_time_std)
        """,
        (batch_id,),
    )


# ---------------------------------------------------------------------------
# 5.0c  Recalculate per-cell metrics from sliding window
# ---------------------------------------------------------------------------

def recalculate_cell_metrics(*, batch_id: int) -> None:
    """Compute per-cell aggregate metrics from sliding window.

    Writes to cell_metrics_window, consumed by cell_maintain.py and
    publish_cell.py in subsequent pipeline rounds.

    Key fixes vs old code:
    - Uses lon_final/lat_final (not lon_raw)
    - Recalculates rsrq_avg / sinr_avg / pressure_avg
    - Computes active_days_30d and consecutive_inactive_days for exit management
    """
    execute('DELETE FROM rebuild5.cell_metrics_window WHERE batch_id = %s', (batch_id,))

    # -- Main metrics: centroid, radius, signals, pressure, obs counts --
    execute(
        """
        INSERT INTO rebuild5.cell_metrics_window (
            batch_id, operator_code, lac, bs_id, cell_id,
            center_lon, center_lat,
            independent_obs, distinct_dev_id, gps_valid_count, active_days,
            observed_span_hours,
            rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
            max_event_time, window_obs_count
        )
        SELECT
            %s,
            operator_code, lac, bs_id, cell_id,
            -- 质心：中位数（用 lon_final, 不是 lon_raw）
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
                FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
                FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
            -- 观测量
            COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text))
                AS independent_obs,
            COUNT(DISTINCT dev_id) AS distinct_dev_id,
            COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid) AS gps_valid_count,
            COUNT(DISTINCT DATE(event_time_std)) AS active_days,
            EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0
                AS observed_span_hours,
            -- 信号 + 气压均值
            AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1) AS rsrp_avg,
            AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10) AS rsrq_avg,
            AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40) AS sinr_avg,
            AVG(pressure_final::double precision)
                FILTER (WHERE pressure_final IS NOT NULL) AS pressure_avg,
            MAX(event_time_std) AS max_event_time,
            COUNT(*) AS window_obs_count
        FROM rebuild5.cell_sliding_window
        GROUP BY operator_code, lac, bs_id, cell_id
        """,
        (batch_id,),
    )

    # -- P50/P90 radius from each observation to the recalculated centroid --
    execute(
        """
        WITH radii AS (
            SELECT
                w.operator_code, w.lac, w.bs_id, w.cell_id,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                    SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
                       + POWER((w.lat_final - m.center_lat) * 111000, 2))
                ) AS p50_radius_m,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                    SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
                       + POWER((w.lat_final - m.center_lat) * 111000, 2))
                ) AS p90_radius_m
            FROM rebuild5.cell_sliding_window w
            JOIN rebuild5.cell_metrics_window m
              ON m.batch_id = %s
             AND m.operator_code = w.operator_code
             AND m.lac = w.lac AND m.cell_id = w.cell_id
            WHERE w.lon_final IS NOT NULL AND w.gps_valid
              AND m.center_lon IS NOT NULL AND m.center_lat IS NOT NULL
            GROUP BY w.operator_code, w.lac, w.bs_id, w.cell_id
        )
        UPDATE rebuild5.cell_metrics_window AS t
        SET p50_radius_m = r.p50_radius_m,
            p90_radius_m = r.p90_radius_m
        FROM radii r
        WHERE t.batch_id = %s
          AND t.operator_code = r.operator_code
          AND t.lac = r.lac AND t.cell_id = r.cell_id
        """,
        (batch_id, batch_id),
    )

    # -- Activity metrics for exit management --
    _update_activity_metrics(batch_id=batch_id)


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
                operator_code, lac, cell_id,
                COUNT(DISTINCT DATE(event_time_std))
                    FILTER (WHERE event_time_std >= (SELECT ref_time - INTERVAL '30 days' FROM window_max))
                    AS active_days_30d,
                EXTRACT(DAY FROM (SELECT ref_time FROM window_max) - MAX(event_time_std))::integer
                    AS consecutive_inactive_days
            FROM rebuild5.cell_sliding_window
            GROUP BY operator_code, lac, cell_id
        )
        UPDATE rebuild5.cell_metrics_window AS t
        SET active_days_30d = COALESCE(a.active_days_30d, 0),
            consecutive_inactive_days = COALESCE(a.consecutive_inactive_days, 0)
        FROM activity a
        WHERE t.batch_id = %s
          AND t.operator_code = a.operator_code
          AND t.lac = a.lac AND t.cell_id = a.cell_id
        """,
        (batch_id,),
    )
