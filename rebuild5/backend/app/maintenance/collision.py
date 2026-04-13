"""Step 5.1 — Two-layer collision detection.

B-class: cell_id mapping table — same cell_id used by multiple (operator_code, lac) combos.
         Not an anomaly label; informs Step 2 fill strategy.

A-class: absolute collision — same (operator_code, tech_norm, lac, cell_id) appears on
         different BS with centroid distance >= threshold. Sets is_collision=true.
"""
from __future__ import annotations

from ..core.database import execute, fetchone


def detect_collisions(
    *,
    batch_id: int,
    snapshot_version: str,
    absolute_min_distance_m: float,
) -> None:
    """Run both collision layers and mark trusted_cell_library."""
    _build_collision_id_list(batch_id=batch_id, snapshot_version=snapshot_version)
    # A-class: geographic collision from DBSCAN centroid detail.
    # The previous approach (COUNT(DISTINCT bs_id) > 1 on trusted_cell_library)
    # was structurally broken because the PK is (batch_id, operator_code, lac,
    # cell_id, tech_norm) — each combo has exactly one row, so multi-BS was
    # impossible.  The replacement detects cells whose stable clusters are
    # >= absolute_min_distance_m apart, which is the actual definition of
    # geographic collision.
    _detect_geographic_collision(
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

def _detect_geographic_collision(
    *,
    batch_id: int,
    absolute_min_distance_m: float,
) -> None:
    """Detect geographic collision from DBSCAN centroid detail.

    A cell with >= 2 stable clusters whose max pair distance >=
    absolute_min_distance_m is a geographic collision: the same cell_id
    is being reported from physically distant locations.

    This replaces the old _detect_absolute_collision which relied on
    COUNT(DISTINCT bs_id) > 1 — structurally impossible given the PK.

    Reads from: cell_centroid_detail (populated by publish_cell_centroid_detail)
    Marks affected cells in trusted_cell_library:
      is_collision=TRUE, drift_pattern='collision',
      antitoxin_hit=TRUE, baseline_eligible=FALSE
    """
    execute(
        """
        UPDATE rebuild5.trusted_cell_library c
        SET is_collision = TRUE,
            drift_pattern = 'collision',
            antitoxin_hit = TRUE,
            baseline_eligible = FALSE
        FROM (
            SELECT DISTINCT
                a.operator_code, a.lac, a.cell_id, a.tech_norm
            FROM rebuild5.cell_centroid_detail a
            JOIN rebuild5.cell_centroid_detail b
              ON b.batch_id = a.batch_id
             AND b.operator_code = a.operator_code
             AND b.lac IS NOT DISTINCT FROM a.lac
             AND b.cell_id = a.cell_id
             AND b.tech_norm IS NOT DISTINCT FROM a.tech_norm
             AND b.cluster_id > a.cluster_id
            WHERE a.batch_id = %s
              AND a.center_lon IS NOT NULL AND b.center_lon IS NOT NULL
              AND SQRT(
                  POWER((a.center_lon - b.center_lon) * 85300, 2)
                + POWER((a.center_lat - b.center_lat) * 111000, 2)
              ) >= %s
        ) geo_col
        WHERE c.batch_id = %s
          AND c.operator_code = geo_col.operator_code
          AND c.lac IS NOT DISTINCT FROM geo_col.lac
          AND c.cell_id = geo_col.cell_id
          AND c.tech_norm IS NOT DISTINCT FROM geo_col.tech_norm
        """,
        (batch_id, absolute_min_distance_m, batch_id),
    )
