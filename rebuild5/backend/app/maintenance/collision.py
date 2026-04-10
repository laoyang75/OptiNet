"""Step 5.1 — Two-layer collision detection.

B-class: cell_id mapping table — same cell_id used by multiple (operator_code, lac) combos.
         Not an anomaly label; informs Step 2 fill strategy.

A-class: absolute collision — same (operator_code, tech_norm, lac, cell_id) appears on
         different BS with centroid distance >= threshold. Sets is_collision=true.
"""
from __future__ import annotations

from ..core.database import execute


def detect_collisions(
    *,
    batch_id: int,
    snapshot_version: str,
    absolute_min_distance_m: float,
) -> None:
    """Run both collision layers and mark trusted_cell_library."""
    _build_collision_id_list(batch_id=batch_id, snapshot_version=snapshot_version)
    _detect_absolute_collision(
        batch_id=batch_id,
        absolute_min_distance_m=absolute_min_distance_m,
    )


# ---------------------------------------------------------------------------
# B-class: cell_id mapping table
# ---------------------------------------------------------------------------

def _build_collision_id_list(*, batch_id: int, snapshot_version: str) -> None:
    """Same cell_id across multiple (operator_code, lac) combos.

    Output: collision_id_list with is_collision_id=TRUE, dominant_combo by obs count.
    Step 2 uses this to decide whether operator/LAC validation is needed during fill.
    """
    execute('DELETE FROM rebuild5.collision_id_list WHERE batch_id = %s', (batch_id,))
    execute(
        """
        INSERT INTO rebuild5.collision_id_list (
            batch_id, snapshot_version, cell_id, is_collision_id,
            collision_combo_count, dominant_combo, combo_keys_json, created_at
        )
        SELECT
            %s, %s, cell_id, TRUE,
            COUNT(DISTINCT (operator_code, lac)) AS collision_combo_count,
            (array_agg(
                operator_code || ':' || lac::text
                ORDER BY independent_obs DESC NULLS LAST
            ))[1] AS dominant_combo,
            jsonb_agg(jsonb_build_object(
                'operator_code', operator_code,
                'lac', lac,
                'bs_id', bs_id,
                'p90_radius_m', p90_radius_m,
                'center_lon', center_lon,
                'center_lat', center_lat,
                'independent_obs', independent_obs,
                'distinct_dev_id', distinct_dev_id
            ) ORDER BY independent_obs DESC NULLS LAST) AS combo_keys_json,
            NOW()
        FROM rebuild5.trusted_cell_library
        WHERE batch_id = %s
        GROUP BY cell_id
        HAVING COUNT(DISTINCT (operator_code, lac)) > 1
        """,
        (batch_id, snapshot_version, batch_id),
    )


# ---------------------------------------------------------------------------
# A-class: absolute collision
# ---------------------------------------------------------------------------

def _detect_absolute_collision(
    *,
    batch_id: int,
    absolute_min_distance_m: float,
) -> None:
    """Same (operator_code, lac, cell_id) on different BS with distance >= threshold.

    Marks affected cells in trusted_cell_library:
      is_collision=TRUE, drift_pattern='collision',
      antitoxin_hit=TRUE, baseline_eligible=FALSE
    """
    # First find cells with multiple BS (tiny subset), then only compare those pairs
    execute(
        """
        UPDATE rebuild5.trusted_cell_library c
        SET is_collision = TRUE,
            drift_pattern = 'collision',
            antitoxin_hit = TRUE,
            baseline_eligible = FALSE
        FROM (
            WITH multi_bs AS (
                SELECT operator_code, tech_norm, lac, cell_id
                FROM rebuild5.trusted_cell_library
                WHERE batch_id = %s
                GROUP BY operator_code, tech_norm, lac, cell_id
                HAVING COUNT(DISTINCT bs_id) > 1
            )
            SELECT DISTINCT a.operator_code, a.tech_norm, a.lac, a.cell_id
            FROM rebuild5.trusted_cell_library a
            JOIN rebuild5.trusted_cell_library b
              ON a.batch_id = b.batch_id
             AND a.operator_code = b.operator_code
             AND a.tech_norm = b.tech_norm
             AND a.lac = b.lac
             AND a.cell_id = b.cell_id
             AND a.bs_id < b.bs_id
            JOIN multi_bs m
              ON m.operator_code = a.operator_code
             AND m.tech_norm = a.tech_norm
             AND m.lac = a.lac
             AND m.cell_id = a.cell_id
            WHERE a.batch_id = %s
              AND a.center_lon IS NOT NULL AND b.center_lon IS NOT NULL
              AND a.center_lat IS NOT NULL AND b.center_lat IS NOT NULL
              AND SQRT(
                  POWER((a.center_lon - b.center_lon) * 85300, 2)
                + POWER((a.center_lat - b.center_lat) * 111000, 2)
              ) >= %s
        ) abs_col
        WHERE c.batch_id = %s
          AND c.operator_code = abs_col.operator_code
          AND c.tech_norm = abs_col.tech_norm
          AND c.lac = abs_col.lac
          AND c.cell_id = abs_col.cell_id
        """,
        (batch_id, batch_id, absolute_min_distance_m, batch_id),
    )
