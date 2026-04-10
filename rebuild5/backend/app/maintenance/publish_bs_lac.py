"""Step 5.4 — Publish BS library, BS centroid detail, LAC library.

BS: aggregated from trusted_cell_library (Cell → BS).
LAC: aggregated from trusted_bs_library (BS → LAC).

Fixes vs legacy:
- BS classification: all 5 types (collision_bs/dynamic_bs/large_spread/multi_centroid/normal_spread)
- BS: is_multi_centroid, window_active_cell_count
- LAC: active_bs_count, retired_bs_count, boundary_stability_score
- Cell centroid detail: single-cluster primary stub (real clustering in multi_centroid.py)
"""
from __future__ import annotations

from typing import Any

from ..core.database import execute
from ..etl.source_prep import DATASET_KEY


# ---------------------------------------------------------------------------
# Cell centroid detail (stub — real clustering in multi_centroid.py Round 5)
# ---------------------------------------------------------------------------

def publish_cell_centroid_detail(*, batch_id: int, snapshot_version: str) -> None:
    execute('DELETE FROM rebuild5.cell_centroid_detail WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.cell_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, cluster_id,
            is_primary, center_lon, center_lat, obs_count, dev_count, share_ratio
        )
        SELECT batch_id, snapshot_version, operator_code, lac, bs_id, cell_id, 1,
               TRUE, center_lon, center_lat, independent_obs, distinct_dev_id, 1.0
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = %s AND is_multi_centroid
        """,
        (batch_id,),
    )


# ---------------------------------------------------------------------------
# BS library
# ---------------------------------------------------------------------------

def publish_bs_library(
    *,
    run_id: str,
    batch_id: int,
    snapshot_version: str,
    snapshot_version_prev: str,
    antitoxin: dict[str, float],
) -> None:
    execute('DELETE FROM rebuild5.trusted_bs_library WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.trusted_bs_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, bs_id, lifecycle_state,
            anchor_eligible, baseline_eligible,
            total_cells, qualified_cells, excellent_cells,
            center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m,
            classification, position_grade, anomaly_cell_ratio,
            is_multi_centroid, window_active_cell_count
        )
        WITH cell_agg AS (
            SELECT
                operator_code, lac, bs_id,
                COUNT(*) AS total_cells,
                COUNT(*) FILTER (WHERE lifecycle_state IN ('qualified', 'excellent')) AS qualified_cells,
                COUNT(*) FILTER (WHERE lifecycle_state = 'excellent') AS excellent_cells,
                COUNT(*) FILTER (WHERE is_collision) AS collision_cells,
                COUNT(*) FILTER (WHERE is_dynamic) AS dynamic_cells,
                COUNT(*) FILTER (WHERE is_multi_centroid) AS multi_centroid_cells,
                COUNT(*) FILTER (WHERE is_collision OR is_dynamic OR is_multi_centroid
                    OR drift_pattern IN ('migration', 'large_coverage', 'moderate_drift')) AS anomaly_cells,
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
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon)
                    FILTER (WHERE NOT is_collision AND NOT is_dynamic) AS center_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat)
                    FILTER (WHERE NOT is_collision AND NOT is_dynamic) AS center_lat
            FROM rebuild5.trusted_cell_library
            WHERE batch_id = %s
              AND center_lon IS NOT NULL AND center_lat IS NOT NULL
            GROUP BY operator_code, lac, bs_id
        ),
        bs_dist AS (
            SELECT
                t.operator_code, t.lac, t.bs_id,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                    SQRT(POWER((t.center_lon - b.center_lon) * 85300, 2)
                       + POWER((t.center_lat - b.center_lat) * 111000, 2))
                ) AS gps_p50_dist_m,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                    SQRT(POWER((t.center_lon - b.center_lon) * 85300, 2)
                       + POWER((t.center_lat - b.center_lat) * 111000, 2))
                ) AS gps_p90_dist_m
            FROM rebuild5.trusted_cell_library t
            JOIN bs_center b
              ON b.operator_code = t.operator_code AND b.lac = t.lac AND b.bs_id = t.bs_id
            WHERE t.batch_id = %s
              AND t.center_lon IS NOT NULL AND t.center_lat IS NOT NULL
              AND b.center_lon IS NOT NULL AND b.center_lat IS NOT NULL
            GROUP BY t.operator_code, t.lac, t.bs_id
        )
        SELECT
            %s::int, %s::text, %s::text, %s::text, %s::text, NOW(),
            s.operator_code, s.operator_cn, s.lac, s.bs_id,
            s.lifecycle_state,
            COALESCE(c.anchor_eligible, s.anchor_eligible),
            COALESCE(c.baseline_eligible, s.baseline_eligible),
            COALESCE(c.total_cells, s.cell_count),
            COALESCE(c.qualified_cells, s.qualified_cell_count),
            COALESCE(c.excellent_cells, s.excellent_cell_count),
            COALESCE(bc.center_lon, s.center_lon),
            COALESCE(bc.center_lat, s.center_lat),
            COALESCE(bd.gps_p50_dist_m, s.gps_p50_dist_m),
            COALESCE(bd.gps_p90_dist_m, s.gps_p90_dist_m),
            -- classification: 5 types
            CASE
                WHEN COALESCE(bd.gps_p90_dist_m, s.gps_p90_dist_m, 0) >= %s
                    THEN 'large_spread'
                WHEN COALESCE(c.collision_cells, 0) > 0
                    THEN 'collision_bs'
                WHEN COALESCE(c.multi_centroid_cells, 0) > 0
                    THEN 'multi_centroid'
                WHEN COALESCE(c.dynamic_cells, 0) > 0
                    THEN 'dynamic_bs'
                ELSE 'normal_spread'
            END,
            s.position_grade,
            COALESCE(c.anomaly_cells, 0)::double precision
                / NULLIF(COALESCE(c.total_cells, 0), 0),
            -- is_multi_centroid (BS level)
            (COALESCE(c.multi_centroid_cells, 0) > 0),
            COALESCE(c.active_cell_count, 0)
        FROM rebuild5.trusted_snapshot_bs s
        LEFT JOIN cell_agg c
          ON c.operator_code = s.operator_code AND c.lac = s.lac AND c.bs_id = s.bs_id
        LEFT JOIN bs_center bc
          ON bc.operator_code = s.operator_code AND bc.lac = s.lac AND bc.bs_id = s.bs_id
        LEFT JOIN bs_dist bd
          ON bd.operator_code = s.operator_code AND bd.lac = s.lac AND bd.bs_id = s.bs_id
        WHERE s.batch_id = %s AND s.lifecycle_state = 'qualified'
        """,
        (batch_id, batch_id, batch_id,
         batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id,
         antitoxin['bs_max_cell_to_bs_distance_m'], batch_id),
    )


# ---------------------------------------------------------------------------
# BS centroid detail (stub — real clustering in multi_centroid.py Round 5)
# ---------------------------------------------------------------------------

def publish_bs_centroid_detail(*, batch_id: int, snapshot_version: str) -> None:
    execute('DELETE FROM rebuild5.bs_centroid_detail WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.bs_centroid_detail (
            batch_id, snapshot_version, operator_code, lac, bs_id, cluster_id,
            is_primary, center_lon, center_lat, cell_count, share_ratio
        )
        SELECT batch_id, snapshot_version, operator_code, lac, bs_id, 1,
               TRUE, center_lon, center_lat, total_cells, 1.0
        FROM rebuild5.trusted_bs_library
        WHERE batch_id = %s AND classification = 'large_spread'
        """,
        (batch_id,),
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
    execute('DELETE FROM rebuild5.trusted_lac_library WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.trusted_lac_library (
            batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at,
            operator_code, operator_cn, lac, lifecycle_state,
            anchor_eligible, baseline_eligible,
            total_bs, qualified_bs, qualified_bs_ratio,
            area_km2, anomaly_bs_ratio,
            boundary_stability_score, active_bs_count, retired_bs_count,
            trend
        )
        WITH bs_agg AS (
            SELECT
                operator_code, lac,
                COUNT(*) AS total_bs,
                COUNT(*) FILTER (WHERE lifecycle_state = 'qualified') AS qualified_bs,
                COUNT(*) FILTER (WHERE lifecycle_state = 'dormant' OR lifecycle_state = 'retired')
                    AS retired_bs,
                BOOL_OR(anchor_eligible) AS anchor_eligible,
                BOOL_OR(baseline_eligible) AS baseline_eligible,
                COALESCE(AVG(CASE WHEN classification IN
                    ('large_spread', 'dynamic_bs', 'collision_bs', 'multi_centroid')
                    THEN 1 ELSE 0 END), 0) AS anomaly_bs_ratio,
                COUNT(*) FILTER (WHERE window_active_cell_count > 0) AS active_bs
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = %s
            GROUP BY operator_code, lac
        ),
        lac_area AS (
            SELECT
                operator_code, lac,
                CASE WHEN COUNT(*) < 2 THEN NULL
                     ELSE ((MAX(center_lon) - MIN(center_lon)) * 85.3)
                        * ((MAX(center_lat) - MIN(center_lat)) * 111.0)
                END AS area_km2
            FROM rebuild5.trusted_bs_library
            WHERE batch_id = %s
              AND center_lon IS NOT NULL AND center_lat IS NOT NULL
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
            s.operator_code, s.operator_cn, s.lac,
            s.lifecycle_state,
            COALESCE(ba.anchor_eligible, s.anchor_eligible),
            COALESCE(ba.baseline_eligible, s.baseline_eligible),
            COALESCE(ba.total_bs, s.bs_count),
            COALESCE(ba.qualified_bs, s.qualified_bs_count),
            COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0),
            COALESCE(la.area_km2, s.area_km2),
            COALESCE(ba.anomaly_bs_ratio, 0),
            -- boundary_stability_score: 1.0 if area stable, decreases with area change
            CASE
                WHEN p.prev_area_km2 IS NULL OR p.prev_area_km2 = 0 THEN 1.0
                WHEN la.area_km2 IS NULL THEN 1.0
                ELSE GREATEST(0, 1.0 - ABS(la.area_km2 - p.prev_area_km2)
                     / GREATEST(p.prev_area_km2, 0.01))
            END,
            COALESCE(ba.active_bs, 0),
            COALESCE(ba.retired_bs, 0),
            -- trend
            CASE
                WHEN p.qualified_bs_ratio IS NULL THEN 'stable'
                WHEN COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0)
                     - p.qualified_bs_ratio >= 0.02 THEN 'improving'
                WHEN p.qualified_bs_ratio
                     - COALESCE(ba.qualified_bs::double precision / NULLIF(ba.total_bs, 0), 0) >= 0.02
                    THEN 'degrading'
                ELSE 'stable'
            END
        FROM rebuild5.trusted_snapshot_lac s
        LEFT JOIN bs_agg ba ON ba.operator_code = s.operator_code AND ba.lac = s.lac
        LEFT JOIN lac_area la ON la.operator_code = s.operator_code AND la.lac = s.lac
        LEFT JOIN prev_lac p ON p.operator_code = s.operator_code AND p.lac = s.lac
        WHERE s.batch_id = %s AND s.lifecycle_state = 'qualified'
        """,
        (batch_id, batch_id, batch_id,
         batch_id, snapshot_version, snapshot_version_prev, DATASET_KEY, run_id,
         batch_id),
    )
