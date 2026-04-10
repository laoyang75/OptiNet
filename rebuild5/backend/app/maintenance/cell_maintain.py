"""Step 5.2 — Cell maintenance: drift metrics, GPS anomaly summary, exit flags.

Reads cell_daily_centroid and gps_anomaly_log.
Writes computed drift / anomaly / exit columns into cell_metrics_window.
"""
from __future__ import annotations

from math import sqrt
from typing import Any

from ..core.database import execute, fetchall


# ---------------------------------------------------------------------------
# 5.2a  Drift metrics from daily centroids
# ---------------------------------------------------------------------------

def compute_drift_metrics(*, batch_id: int) -> None:
    """Compute max_spread_m, net_drift_m, drift_ratio per cell.

    max_spread_m  = max pairwise distance among daily centroids
    net_drift_m   = distance from first-day centroid to last-day centroid
    drift_ratio   = net_drift / max_spread  (0=random jitter, 1=directional migration)

    Uses SQL self-join for max_spread (at most 30×30 pairs per cell).
    Uses array_agg for first/last day endpoints.
    """
    # Step 1: max_spread via self-join
    execute(
        """
        WITH spread AS (
            SELECT
                a.operator_code, a.lac, a.cell_id,
                MAX(SQRT(
                    POWER((a.center_lon - b.center_lon) * 85300, 2)
                  + POWER((a.center_lat - b.center_lat) * 111000, 2)
                )) AS max_spread_m
            FROM rebuild5.cell_daily_centroid a
            JOIN rebuild5.cell_daily_centroid b
              ON a.batch_id = b.batch_id
             AND a.operator_code = b.operator_code
             AND a.lac = b.lac AND a.cell_id = b.cell_id
             AND a.obs_date < b.obs_date
            WHERE a.batch_id = %s
              AND a.center_lon IS NOT NULL AND b.center_lon IS NOT NULL
            GROUP BY a.operator_code, a.lac, a.cell_id
        )
        UPDATE rebuild5.cell_metrics_window AS t
        SET max_spread_m = s.max_spread_m
        FROM spread s
        WHERE t.batch_id = %s
          AND t.operator_code = s.operator_code
          AND t.lac = s.lac AND t.cell_id = s.cell_id
        """,
        (batch_id, batch_id),
    )

    # Step 2: net_drift (first day → last day) + drift_days
    execute(
        """
        WITH endpoints AS (
            SELECT
                operator_code, lac, cell_id,
                (array_agg(center_lon ORDER BY obs_date ASC))[1]  AS first_lon,
                (array_agg(center_lat ORDER BY obs_date ASC))[1]  AS first_lat,
                (array_agg(center_lon ORDER BY obs_date DESC))[1] AS last_lon,
                (array_agg(center_lat ORDER BY obs_date DESC))[1] AS last_lat,
                COUNT(*) AS drift_days
            FROM rebuild5.cell_daily_centroid
            WHERE batch_id = %s AND center_lon IS NOT NULL
            GROUP BY operator_code, lac, cell_id
        )
        UPDATE rebuild5.cell_metrics_window AS t
        SET net_drift_m = SQRT(
                POWER((e.last_lon - e.first_lon) * 85300, 2)
              + POWER((e.last_lat - e.first_lat) * 111000, 2)
            )
        FROM endpoints e
        WHERE t.batch_id = %s
          AND t.operator_code = e.operator_code
          AND t.lac = e.lac AND t.cell_id = e.cell_id
          AND e.drift_days >= 2
          AND e.first_lon IS NOT NULL AND e.last_lon IS NOT NULL
        """,
        (batch_id, batch_id),
    )

    # Step 3: drift_ratio = net_drift / max_spread
    execute(
        """
        UPDATE rebuild5.cell_metrics_window
        SET drift_ratio = CASE
            WHEN max_spread_m > 0 THEN LEAST(net_drift_m / max_spread_m, 1.0)
            ELSE 0
        END
        WHERE batch_id = %s
          AND max_spread_m IS NOT NULL
          AND net_drift_m IS NOT NULL
        """,
        (batch_id,),
    )


# ---------------------------------------------------------------------------
# 5.2b  GPS anomaly summary from gps_anomaly_log → cell level
# ---------------------------------------------------------------------------

def compute_gps_anomaly_summary(*, batch_id: int) -> None:
    """Aggregate gps_anomaly_log to cell-level counts.

    Stores anomaly_count into a lightweight intermediate: we UPDATE
    cell_metrics_window with two new temp columns via a CTE approach.
    Since cell_metrics_window doesn't have anomaly columns, we store
    the result in a separate small table.
    """
    # We'll create a temp-like persistent table for anomaly summaries
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.cell_anomaly_summary (
            batch_id INTEGER NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            cell_id BIGINT,
            anomaly_count BIGINT NOT NULL DEFAULT 0,
            last_anomaly_at TIMESTAMPTZ,
            PRIMARY KEY (batch_id, operator_code, lac, cell_id)
        )
        """
    )
    execute('DELETE FROM rebuild5.cell_anomaly_summary WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.cell_anomaly_summary (
            batch_id, operator_code, lac, cell_id, anomaly_count, last_anomaly_at
        )
        SELECT
            %s, operator_code, lac, cell_id,
            COUNT(*) AS anomaly_count,
            MAX(event_time_std) AS last_anomaly_at
        FROM rebuild5.gps_anomaly_log
        WHERE batch_id = %s
        GROUP BY operator_code, lac, cell_id
        """,
        (batch_id, batch_id),
    )
