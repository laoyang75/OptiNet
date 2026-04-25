"""Step 5.2 — Cell maintenance: drift metrics and GPS anomaly summarization.

Reads cell_daily_centroid and gps_anomaly_log.
Writes computed drift / anomaly / exit columns into cell_metrics_window.
"""
from __future__ import annotations

from typing import Any

from ..core.database import execute
from ..profile.logic import flatten_antitoxin_thresholds, load_antitoxin_params
from ..profile.pipeline import relation_exists


# ---------------------------------------------------------------------------
# 5.2a  Drift metrics from daily centroids
# ---------------------------------------------------------------------------

def build_cell_drift_stats(*, batch_id: int) -> None:
    """Materialize max_spread, net_drift and drift_ratio in a dedicated stage table."""
    execute('DROP TABLE IF EXISTS rb5.cell_drift_stats')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5.cell_drift_stats AS
        WITH spread AS (
            SELECT
                a.operator_code, a.lac, a.cell_id, a.tech_norm,
                MAX(SQRT(
                    POWER((a.center_lon - b.center_lon) * 85300, 2)
                  + POWER((a.center_lat - b.center_lat) * 111000, 2)
                )) AS max_spread_m
            FROM rb5.cell_daily_centroid a
            JOIN rb5.cell_daily_centroid b
              ON a.batch_id = b.batch_id
             AND a.operator_code = b.operator_code
             AND a.lac = b.lac
             AND a.cell_id = b.cell_id
             AND a.tech_norm IS NOT DISTINCT FROM b.tech_norm
             AND a.obs_date < b.obs_date
            WHERE a.batch_id = {batch_id}
              AND a.center_lon IS NOT NULL
              AND b.center_lon IS NOT NULL
            GROUP BY a.operator_code, a.lac, a.cell_id, a.tech_norm
        ),
        endpoints AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                (array_agg(center_lon ORDER BY obs_date ASC))[1] AS first_lon,
                (array_agg(center_lat ORDER BY obs_date ASC))[1] AS first_lat,
                (array_agg(center_lon ORDER BY obs_date DESC))[1] AS last_lon,
                (array_agg(center_lat ORDER BY obs_date DESC))[1] AS last_lat,
                COUNT(*) AS drift_days
            FROM rb5.cell_daily_centroid
            WHERE batch_id = {batch_id}
              AND center_lon IS NOT NULL
            GROUP BY operator_code, lac, cell_id, tech_norm
        )
        SELECT
            {batch_id}::int AS batch_id,
            COALESCE(s.operator_code, e.operator_code) AS operator_code,
            COALESCE(s.lac, e.lac) AS lac,
            COALESCE(s.cell_id, e.cell_id) AS cell_id,
            COALESCE(s.tech_norm, e.tech_norm) AS tech_norm,
            s.max_spread_m,
            CASE
                WHEN e.drift_days >= 2
                 AND e.first_lon IS NOT NULL
                 AND e.last_lon IS NOT NULL
                    THEN SQRT(
                        POWER((e.last_lon - e.first_lon) * 85300, 2)
                      + POWER((e.last_lat - e.first_lat) * 111000, 2)
                    )
                ELSE NULL::double precision
            END AS net_drift_m,
            CASE
                WHEN COALESCE(s.max_spread_m, 0) > 0
                 AND e.drift_days >= 2
                 AND e.first_lon IS NOT NULL
                 AND e.last_lon IS NOT NULL
                    THEN LEAST(
                        SQRT(
                            POWER((e.last_lon - e.first_lon) * 85300, 2)
                          + POWER((e.last_lat - e.first_lat) * 111000, 2)
                        ) / s.max_spread_m,
                        1.0
                    )
                ELSE 0::double precision
            END AS drift_ratio
        FROM spread s
        FULL OUTER JOIN endpoints e
          ON e.operator_code = s.operator_code
         AND e.lac = s.lac
         AND e.cell_id = s.cell_id
         AND e.tech_norm IS NOT DISTINCT FROM s.tech_norm
        """
    )
    execute("ALTER TABLE rb5.cell_drift_stats SET (autovacuum_enabled = false)")
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cell_drift_stats_key
        ON rb5.cell_drift_stats (batch_id, operator_code, lac, cell_id, tech_norm)
        """
    )
    execute('ANALYZE rb5.cell_drift_stats')


def compute_drift_metrics(*, batch_id: int) -> None:
    """Backward-compatible wrapper that materializes drift stats and refreshes the final join."""
    build_cell_drift_stats(batch_id=batch_id)
    if relation_exists('rb5.cell_metrics_base'):
        from .window import build_cell_metrics_window

        build_cell_metrics_window(batch_id=batch_id)


# ---------------------------------------------------------------------------
# 5.2b  GPS anomaly summary from gps_anomaly_log → cell level
# ---------------------------------------------------------------------------

def compute_gps_anomaly_summary(
    *,
    batch_id: int,
    antitoxin: dict[str, float] | None = None,
) -> None:
    """Aggregate gps_anomaly_log to cell-level time-series anomaly summaries.

    This keeps the implementation SQL-first, but moves beyond a plain count so
    Step 5 can distinguish between drift, time-clustered anomalies and
    migration suspects.
    """
    thresholds = antitoxin or flatten_antitoxin_thresholds(load_antitoxin_params())
    execute('DROP TABLE IF EXISTS rb5.cell_anomaly_summary')
    execute(
        f"""
        CREATE UNLOGGED TABLE rb5.cell_anomaly_summary AS
        WITH raw AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                event_time_std,
                DATE(event_time_std) AS anomaly_date,
                EXTRACT(HOUR FROM event_time_std)::int AS anomaly_hour
            FROM rb5.gps_anomaly_log
            WHERE batch_id = {batch_id}
        ),
        agg AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                COUNT(*) AS anomaly_count,
                COUNT(DISTINCT anomaly_date) AS anomaly_days,
                MAX(event_time_std) AS last_anomaly_at
            FROM raw
            GROUP BY operator_code, lac, cell_id, tech_norm
        ),
        day_runs AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                anomaly_date,
                anomaly_date - (ROW_NUMBER() OVER (
                    PARTITION BY operator_code, lac, cell_id, tech_norm
                    ORDER BY anomaly_date
                ))::integer AS grp
            FROM (
                SELECT DISTINCT operator_code, lac, cell_id, tech_norm, anomaly_date
                FROM raw
            ) d
        ),
        consec AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                MAX(run_len) AS max_consecutive_anomaly_days
            FROM (
                SELECT
                    operator_code,
                    lac,
                    cell_id,
                    tech_norm,
                    grp,
                    COUNT(*) AS run_len
                FROM day_runs
                GROUP BY operator_code, lac, cell_id, tech_norm, grp
            ) s
            GROUP BY operator_code, lac, cell_id, tech_norm
        ),
        hour_stats AS (
            SELECT
                operator_code,
                lac,
                cell_id,
                tech_norm,
                MAX(hour_count)::double precision / NULLIF(SUM(hour_count), 0) AS peak_hour_ratio
            FROM (
                SELECT
                    operator_code,
                    lac,
                    cell_id,
                    tech_norm,
                    anomaly_hour,
                    COUNT(*) AS hour_count
                FROM raw
                GROUP BY operator_code, lac, cell_id, tech_norm, anomaly_hour
            ) h
            GROUP BY operator_code, lac, cell_id, tech_norm
        )
        SELECT
            {batch_id}::int AS batch_id,
            a.operator_code,
            a.lac,
            a.cell_id,
            a.tech_norm,
            a.anomaly_count,
            a.last_anomaly_at,
            a.anomaly_days,
            COALESCE(c.max_consecutive_anomaly_days, 0)::int AS max_consecutive_anomaly_days,
            COALESCE(h.peak_hour_ratio, 0)::double precision AS peak_hour_ratio,
            CASE
                WHEN a.anomaly_count <= 0 THEN NULL::text
                WHEN COALESCE(c.max_consecutive_anomaly_days, 0) >= 2
                  AND COALESCE(m.max_spread_m, 0) >= {thresholds['migration_min_spread_m']}
                  AND COALESCE(m.drift_ratio, 0) >= {thresholds['drift_migration_min_ratio']}
                    THEN 'migration_suspect'
                WHEN COALESCE(h.peak_hour_ratio, 0) >= 0.6
                    THEN 'time_cluster'
                ELSE 'drift'
            END AS gps_anomaly_type
        FROM agg a
        LEFT JOIN consec c
          ON c.operator_code = a.operator_code
         AND c.lac = a.lac
         AND c.cell_id = a.cell_id
         AND c.tech_norm IS NOT DISTINCT FROM a.tech_norm
        LEFT JOIN hour_stats h
          ON h.operator_code = a.operator_code
         AND h.lac = a.lac
         AND h.cell_id = a.cell_id
         AND h.tech_norm IS NOT DISTINCT FROM a.tech_norm
        LEFT JOIN rb5.cell_metrics_window m
          ON m.batch_id = {batch_id}
         AND m.operator_code = a.operator_code
         AND m.lac = a.lac
         AND m.cell_id = a.cell_id
         AND m.tech_norm IS NOT DISTINCT FROM a.tech_norm
        """
    )
    execute("ALTER TABLE rb5.cell_anomaly_summary SET (autovacuum_enabled = false)")
