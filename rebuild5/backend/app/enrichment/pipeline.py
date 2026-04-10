"""Step 4 enrichment pipeline — trusted-cell knowledge fill + GPS anomaly tagging."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY
from ..profile.logic import flatten_antitoxin_thresholds, load_antitoxin_params
from ..profile.pipeline import relation_exists
from .schema import (
    ensure_enrichment_schema,
    write_run_log,
    write_step4_coverage,
    write_step4_stats,
)


def _latest_step2() -> dict[str, Any] | None:
    return fetchone(
        """
        SELECT *
        FROM rebuild5_meta.step2_run_stats
        ORDER BY batch_id DESC NULLS LAST, finished_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        """
    )


def _latest_library_version() -> dict[str, Any] | None:
    if not relation_exists('rebuild5.trusted_cell_library'):
        return None
    return fetchone(
        """
        SELECT batch_id, snapshot_version
        FROM rebuild5.trusted_cell_library
        ORDER BY batch_id DESC, cell_id
        LIMIT 1
        """
    )


def _empty_stats(run_id: str, batch_id: int, sv: str, dsv: str) -> dict[str, Any]:
    return {
        'run_id': run_id, 'batch_id': batch_id, 'dataset_key': DATASET_KEY,
        'snapshot_version': sv, 'snapshot_version_prev': dsv, 'status': 'completed',
        'total_path_a': 0, 'donor_matched_count': 0,
        'gps_filled': 0, 'rsrp_filled': 0, 'rsrq_filled': 0, 'sinr_filled': 0,
        'operator_filled': 0, 'lac_filled': 0, 'tech_filled': 0,
        'gps_anomaly_count': 0, 'collision_skip_anomaly_count': 0,
        'donor_excellent_count': 0, 'donor_qualified_count': 0,
        'gps_fill_rate': 0.0, 'signal_fill_rate': 0.0, 'operator_fill_rate': 0.0,
        'remaining_none_gps': 0, 'remaining_none_signal': 0,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_enrichment_pipeline() -> dict[str, Any]:
    execute('DROP TABLE IF EXISTS rebuild5.enriched_records')
    execute('DROP TABLE IF EXISTS rebuild5.gps_anomaly_log')
    execute('DROP TABLE IF EXISTS rebuild5_meta.step4_run_stats')
    ensure_enrichment_schema()

    run_id = f"enrich_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    step2 = _latest_step2()
    antitoxin = flatten_antitoxin_thresholds(load_antitoxin_params())

    batch_id = int(step2['batch_id']) if step2 and step2.get('batch_id') is not None else 0
    snapshot_version = f'v{batch_id}' if batch_id else 'v0'
    # Use the SAME source version Step 2 used — not MAX(batch_id)
    donor_snapshot_version = str(step2['trusted_snapshot_version']) if step2 else 'v0'
    # Derive donor batch_id from version string (e.g. "v1" → 1)
    donor_batch_id = int(donor_snapshot_version.lstrip('v')) if donor_snapshot_version != 'v0' else 0
    anomaly_threshold_m = antitoxin['collision_min_spread_m']

    execute('DELETE FROM rebuild5.enriched_records WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rebuild5.gps_anomaly_log WHERE batch_id = %s', (batch_id,))
    execute('DELETE FROM rebuild5.step4_fill_coverage WHERE batch_id = %s', (batch_id,))

    has_library = relation_exists('rebuild5.trusted_cell_library') and donor_batch_id > 0
    if not step2 or not has_library or not relation_exists('rebuild5.path_a_records'):
        stats = _empty_stats(run_id, batch_id, snapshot_version, donor_snapshot_version)
        write_step4_stats(stats)
        write_run_log(run_id=run_id, batch_id=batch_id, snapshot_version=snapshot_version,
                      status='completed', result_summary=stats)
        return stats

    _insert_enriched_records(batch_id, run_id)
    _insert_gps_anomaly_log(batch_id, anomaly_threshold_m, donor_batch_id)

    stats = _collect_step4_stats(
        run_id=run_id, batch_id=batch_id,
        snapshot_version=snapshot_version,
        snapshot_version_prev=donor_snapshot_version,
    )
    write_step4_coverage(batch_id=batch_id, stats=stats)
    write_step4_stats(stats)
    write_run_log(run_id=run_id, batch_id=batch_id,
                  snapshot_version=snapshot_version,
                  status='completed', result_summary=stats)
    return stats


# ---------------------------------------------------------------------------
# Step 1: Knowledge fill — path_a LEFT JOIN trusted_cell (anchor_eligible)
# ---------------------------------------------------------------------------

def _insert_enriched_records(batch_id: int, run_id: str) -> None:
    """Simple enricher: read donor fields directly from path_a_records (placed by Step 2).

    No re-JOIN to trusted_cell_library — Step 2 already confirmed the source cell.
    """
    execute(
        """
        INSERT INTO rebuild5.enriched_records (
            batch_id, run_id, dataset_key, source_row_uid, record_id, source_table,
            event_time_std, dev_id,
            operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
            gps_valid, lon_raw, lat_raw,
            lon_final, lat_final, gps_fill_source_final, gps_fill_confidence,
            rsrp_final, rsrp_fill_source_final,
            rsrq_final, rsrq_fill_source_final,
            sinr_final, sinr_fill_source_final,
            pressure_final, pressure_fill_source_final,
            operator_final, operator_fill_source_final,
            lac_final, lac_fill_source_final,
            tech_final, tech_fill_source_final,
            donor_batch_id, donor_snapshot_version, donor_cell_id,
            donor_lifecycle_state, donor_position_grade,
            donor_center_lon, donor_center_lat,
            donor_anchor_eligible, donor_baseline_eligible
        )
        SELECT
            %s::int   AS batch_id,
            %s::text  AS run_id,
            %s::text  AS dataset_key,
            COALESCE(p.source_tid::text, p.record_id) AS source_row_uid,
            p.record_id, p.source_table, p.event_time_std, p.dev_id,
            p.operator_code, p.operator_cn, p.lac, p.bs_id, p.cell_id, p.tech_norm,
            p.gps_valid, p.lon_raw, p.lat_raw,

            -- GPS: Step1 filled → donor center (from path_a_records) → NULL
            COALESCE(p.lon_filled, p.donor_center_lon),
            COALESCE(p.lat_filled, p.donor_center_lat),
            CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL
                     THEN COALESCE(p.gps_fill_source, 'none')
                 WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
                     THEN 'trusted_cell'
                 ELSE 'none' END,
            CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL THEN NULL
                 WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
                     THEN p.donor_position_grade
                 ELSE NULL END,

            -- RSRP
            COALESCE(p.rsrp_filled, p.donor_rsrp_avg),
            CASE WHEN p.rsrp_filled IS NOT NULL THEN COALESCE(p.rsrp_fill_source, 'none')
                 WHEN p.donor_rsrp_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- RSRQ
            COALESCE(p.rsrq_filled, p.donor_rsrq_avg),
            CASE WHEN p.rsrq_filled IS NOT NULL THEN 'original'
                 WHEN p.donor_rsrq_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- SINR
            COALESCE(p.sinr_filled, p.donor_sinr_avg),
            CASE WHEN p.sinr_filled IS NOT NULL THEN 'original'
                 WHEN p.donor_sinr_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- 气压
            CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN p.pressure::double precision
                 ELSE p.donor_pressure_avg END,
            CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN 'original'
                 WHEN p.donor_pressure_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- 运营商
            COALESCE(p.operator_filled, p.donor_operator_code),
            CASE WHEN p.operator_filled IS NOT NULL
                     THEN COALESCE(p.operator_fill_source, 'none')
                 WHEN p.donor_operator_code IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- LAC
            COALESCE(p.lac_filled, p.donor_lac),
            CASE WHEN p.lac_filled IS NOT NULL
                     THEN COALESCE(p.lac_fill_source, 'none')
                 WHEN p.donor_lac IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- 制式
            COALESCE(p.tech_norm, p.donor_tech_norm),
            CASE WHEN p.tech_norm IS NOT NULL THEN 'original'
                 WHEN p.donor_tech_norm IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,

            -- donor 审计 (directly from path_a_records)
            p.donor_batch_id, p.donor_snapshot_version, p.donor_cell_id,
            p.donor_lifecycle_state, p.donor_position_grade,
            p.donor_center_lon, p.donor_center_lat,
            p.donor_anchor_eligible, p.donor_baseline_eligible

        FROM rebuild5.path_a_records p
        """,
        (batch_id, run_id, DATASET_KEY),
    )


# ---------------------------------------------------------------------------
# Step 2: GPS anomaly detection — skip collision cell_ids
# ---------------------------------------------------------------------------

def _insert_gps_anomaly_log(batch_id: int, anomaly_threshold_m: float, donor_batch_id: int) -> None:
    has_collision = relation_exists('rebuild5.collision_id_list')
    # Use same source version as Step 2 — not MAX(batch_id)
    collision_filter = f"""
         AND NOT EXISTS (
             SELECT 1 FROM rebuild5.collision_id_list c
             WHERE c.batch_id = {donor_batch_id}
               AND c.cell_id = e.cell_id
         )
    """ if has_collision else ""

    execute(
        f"""
        INSERT INTO rebuild5.gps_anomaly_log (
            batch_id, run_id, dataset_key, source_row_uid, record_id,
            operator_code, lac, bs_id, cell_id, dev_id, event_time_std,
            lon_raw, lat_raw,
            donor_center_lon, donor_center_lat, donor_snapshot_version,
            distance_to_donor_m, anomaly_type, anomaly_threshold_m,
            anomaly_source, is_collision_id
        )
        SELECT
            batch_id, run_id, dataset_key, source_row_uid, record_id,
            operator_code, lac, bs_id, cell_id, dev_id, event_time_std,
            lon_raw, lat_raw,
            donor_center_lon, donor_center_lat, donor_snapshot_version,
            SQRT(POWER((lon_raw - donor_center_lon) * 85300, 2)
               + POWER((lat_raw - donor_center_lat) * 111000, 2)),
            'pending'::text,
            %s::double precision,
            'trusted_cell_compare'::text,
            false
        FROM rebuild5.enriched_records e
        WHERE e.batch_id = %s
          AND e.lon_raw IS NOT NULL AND e.lat_raw IS NOT NULL
          AND e.donor_center_lon IS NOT NULL AND e.donor_center_lat IS NOT NULL
          AND SQRT(POWER((lon_raw - donor_center_lon) * 85300, 2)
                 + POWER((lat_raw - donor_center_lat) * 111000, 2)) > %s
          {collision_filter}
        """,
        (anomaly_threshold_m, batch_id, anomaly_threshold_m),
    )


# ---------------------------------------------------------------------------
# Stats collection
# ---------------------------------------------------------------------------

def _collect_step4_stats(
    *, run_id: str, batch_id: int,
    snapshot_version: str, snapshot_version_prev: str,
) -> dict[str, Any]:
    row = fetchone(
        """
        SELECT
            COUNT(*)                                                          AS total_path_a,
            COUNT(*) FILTER (WHERE donor_batch_id IS NOT NULL)                AS donor_matched_count,
            COUNT(*) FILTER (WHERE gps_fill_source_final = 'trusted_cell')    AS gps_filled,
            COUNT(*) FILTER (WHERE rsrp_fill_source_final = 'trusted_cell')   AS rsrp_filled,
            COUNT(*) FILTER (WHERE rsrq_fill_source_final = 'trusted_cell')   AS rsrq_filled,
            COUNT(*) FILTER (WHERE sinr_fill_source_final = 'trusted_cell')   AS sinr_filled,
            COUNT(*) FILTER (WHERE operator_fill_source_final = 'trusted_cell') AS operator_filled,
            COUNT(*) FILTER (WHERE lac_fill_source_final = 'trusted_cell')    AS lac_filled,
            COUNT(*) FILTER (WHERE tech_fill_source_final = 'trusted_cell')   AS tech_filled,
            COUNT(*) FILTER (WHERE donor_lifecycle_state = 'excellent')        AS donor_excellent_count,
            COUNT(*) FILTER (WHERE donor_lifecycle_state = 'qualified')        AS donor_qualified_count,
            COUNT(*) FILTER (WHERE lon_final IS NULL)                          AS remaining_none_gps,
            COUNT(*) FILTER (WHERE rsrp_final IS NULL
                               AND rsrq_final IS NULL
                               AND sinr_final IS NULL)                         AS remaining_none_signal
        FROM rebuild5.enriched_records
        WHERE batch_id = %s
        """,
        (batch_id,),
    )

    anomaly_cnt = fetchone(
        'SELECT COUNT(*) AS cnt FROM rebuild5.gps_anomaly_log WHERE batch_id = %s',
        (batch_id,),
    )

    collision_skip = 0
    # Read donor_batch_id from step2_run_stats for consistent version
    step2 = _latest_step2()
    sv = str(step2['trusted_snapshot_version']) if step2 else 'v0'
    stats_donor_batch = int(sv.lstrip('v')) if sv != 'v0' else 0
    if relation_exists('rebuild5.collision_id_list'):
        skip_row = fetchone(
            """
            SELECT COUNT(*) AS cnt
            FROM rebuild5.enriched_records e
            WHERE e.batch_id = %s
              AND e.lon_raw IS NOT NULL AND e.lat_raw IS NOT NULL
              AND e.donor_center_lon IS NOT NULL AND e.donor_center_lat IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM rebuild5.collision_id_list c
                  WHERE c.batch_id = %s
                    AND c.cell_id = e.cell_id
              )
            """,
            (batch_id, stats_donor_batch),
        )
        collision_skip = int(skip_row['cnt']) if skip_row else 0

    total = int(row['total_path_a']) if row else 0
    gps_f = int(row['gps_filled']) if row else 0
    rsrp_f = int(row['rsrp_filled']) if row else 0
    rsrq_f = int(row['rsrq_filled']) if row else 0
    sinr_f = int(row['sinr_filled']) if row else 0
    sig_total = rsrp_f + rsrq_f + sinr_f
    op_f = int(row['operator_filled']) if row else 0

    return {
        'run_id': run_id, 'batch_id': batch_id, 'dataset_key': DATASET_KEY,
        'snapshot_version': snapshot_version,
        'snapshot_version_prev': snapshot_version_prev,
        'status': 'completed',
        'total_path_a': total,
        'donor_matched_count': int(row['donor_matched_count']) if row else 0,
        'gps_filled': gps_f,
        'rsrp_filled': rsrp_f, 'rsrq_filled': rsrq_f, 'sinr_filled': sinr_f,
        'operator_filled': op_f,
        'lac_filled': int(row['lac_filled']) if row else 0,
        'tech_filled': int(row['tech_filled']) if row else 0,
        'gps_anomaly_count': int(anomaly_cnt['cnt']) if anomaly_cnt else 0,
        'collision_skip_anomaly_count': collision_skip,
        'donor_excellent_count': int(row['donor_excellent_count']) if row else 0,
        'donor_qualified_count': int(row['donor_qualified_count']) if row else 0,
        'gps_fill_rate': round(gps_f / total, 4) if total else 0.0,
        'signal_fill_rate': round(sig_total / (total * 3), 4) if total else 0.0,
        'operator_fill_rate': round(op_f / total, 4) if total else 0.0,
        'remaining_none_gps': int(row['remaining_none_gps']) if row else 0,
        'remaining_none_signal': int(row['remaining_none_signal']) if row else 0,
    }
