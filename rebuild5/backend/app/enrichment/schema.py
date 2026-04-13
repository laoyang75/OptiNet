"""Step 4 table schema definitions and writer helpers."""
from __future__ import annotations

import json
from typing import Any

from ..core.database import execute
from ..etl.source_prep import DATASET_KEY


def ensure_enrichment_schema() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5_meta.step4_run_stats (
            run_id TEXT PRIMARY KEY,
            batch_id INTEGER NOT NULL,
            dataset_key TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            snapshot_version_prev TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_path_a BIGINT NOT NULL,
            donor_matched_count BIGINT NOT NULL,
            gps_filled BIGINT NOT NULL,
            rsrp_filled BIGINT NOT NULL,
            rsrq_filled BIGINT NOT NULL,
            sinr_filled BIGINT NOT NULL,
            operator_filled BIGINT NOT NULL,
            lac_filled BIGINT NOT NULL,
            tech_filled BIGINT NOT NULL,
            gps_anomaly_count BIGINT NOT NULL,
            collision_skip_anomaly_count BIGINT NOT NULL,
            donor_excellent_count BIGINT NOT NULL,
            donor_qualified_count BIGINT NOT NULL,
            gps_fill_rate DOUBLE PRECISION NOT NULL,
            signal_fill_rate DOUBLE PRECISION NOT NULL,
            operator_fill_rate DOUBLE PRECISION NOT NULL,
            remaining_none_gps BIGINT NOT NULL,
            remaining_none_signal BIGINT NOT NULL
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS rebuild5.step4_fill_coverage (
            batch_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            filled_count BIGINT NOT NULL,
            fill_rate DOUBLE PRECISION NOT NULL,
            donor_source TEXT NOT NULL,
            PRIMARY KEY (batch_id, field_name)
        )
        """
    )
    execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS rebuild5.enriched_records (
            batch_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            source_row_uid TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source_table TEXT,
            event_time_std TIMESTAMPTZ,
            dev_id TEXT,
            -- 原始归属
            operator_code TEXT,
            operator_cn TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            -- 原始 GPS
            gps_valid BOOLEAN,
            lon_raw DOUBLE PRECISION,
            lat_raw DOUBLE PRECISION,
            -- GPS 补数结果
            lon_final DOUBLE PRECISION,
            lat_final DOUBLE PRECISION,
            gps_fill_source_final TEXT,
            gps_fill_confidence TEXT,
            -- 信号补数结果
            rsrp_final DOUBLE PRECISION,
            rsrp_fill_source_final TEXT,
            rsrq_final DOUBLE PRECISION,
            rsrq_fill_source_final TEXT,
            sinr_final DOUBLE PRECISION,
            sinr_fill_source_final TEXT,
            -- 气压补数结果（donor pressure_avg 由 Step 5 维护写入 trusted_cell_library）
            pressure_final DOUBLE PRECISION,
            pressure_fill_source_final TEXT,
            -- 运营商 / LAC / 制式补数结果
            operator_final TEXT,
            operator_fill_source_final TEXT,
            lac_final BIGINT,
            lac_fill_source_final TEXT,
            tech_final TEXT,
            tech_fill_source_final TEXT,
            -- donor 审计字段
            donor_batch_id INTEGER,
            donor_snapshot_version TEXT,
            donor_cell_id BIGINT,
            donor_operator_code TEXT,
            donor_lac BIGINT,
            donor_tech_norm TEXT,
            donor_lifecycle_state TEXT,
            donor_position_grade TEXT,
            donor_center_lon DOUBLE PRECISION,
            donor_center_lat DOUBLE PRECISION,
            path_a_is_collision BOOLEAN,
            donor_anchor_eligible BOOLEAN,
            donor_baseline_eligible BOOLEAN,
            PRIMARY KEY (batch_id, source_row_uid)
        )
        """
    )
    execute("ALTER TABLE rebuild5.enriched_records SET (autovacuum_enabled = false)")
    execute("ALTER TABLE rebuild5.enriched_records ADD COLUMN IF NOT EXISTS path_a_is_collision BOOLEAN")
    execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS rebuild5.gps_anomaly_log (
            batch_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            dataset_key TEXT NOT NULL,
            source_row_uid TEXT NOT NULL,
            record_id TEXT NOT NULL,
            operator_code TEXT,
            lac BIGINT,
            bs_id BIGINT,
            cell_id BIGINT,
            tech_norm TEXT,
            dev_id TEXT,
            event_time_std TIMESTAMPTZ,
            -- 原始 GPS
            lon_raw DOUBLE PRECISION,
            lat_raw DOUBLE PRECISION,
            -- donor 质心
            donor_center_lon DOUBLE PRECISION,
            donor_center_lat DOUBLE PRECISION,
            donor_snapshot_version TEXT,
            -- 异常信息
            distance_to_donor_m DOUBLE PRECISION,
            anomaly_type TEXT,
            anomaly_threshold_m DOUBLE PRECISION,
            anomaly_source TEXT,
            is_collision_id BOOLEAN,
            PRIMARY KEY (batch_id, source_row_uid)
        )
        """
    )
    execute("ALTER TABLE rebuild5.gps_anomaly_log SET (autovacuum_enabled = false)")
    execute("ALTER TABLE rebuild5.gps_anomaly_log ADD COLUMN IF NOT EXISTS tech_norm TEXT")


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_step4_coverage(*, batch_id: int, stats: dict[str, Any]) -> None:
    total = stats['total_path_a'] or 1
    rows = [
        ('GPS (lon/lat)', stats['gps_filled'], stats['gps_fill_rate'], 'trusted_cell 质心'),
        ('RSRP', stats['rsrp_filled'], round(stats['rsrp_filled'] / total, 4), 'trusted_cell rsrp_avg'),
        ('RSRQ', stats['rsrq_filled'], round(stats['rsrq_filled'] / total, 4), 'trusted_cell rsrq_avg'),
        ('SINR', stats['sinr_filled'], round(stats['sinr_filled'] / total, 4), 'trusted_cell sinr_avg'),
        ('运营商', stats['operator_filled'], stats['operator_fill_rate'], 'trusted_cell 基础画像'),
        ('LAC', stats['lac_filled'], round(stats['lac_filled'] / total, 4), 'trusted_cell 基础画像'),
        ('制式', stats['tech_filled'], round(stats['tech_filled'] / total, 4), 'trusted_cell 基础画像'),
    ]
    for field_name, filled_count, fill_rate, donor_source in rows:
        execute(
            """
            INSERT INTO rebuild5.step4_fill_coverage (batch_id, field_name, filled_count, fill_rate, donor_source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (batch_id, field_name) DO UPDATE SET
                filled_count = EXCLUDED.filled_count,
                fill_rate = EXCLUDED.fill_rate,
                donor_source = EXCLUDED.donor_source
            """,
            (batch_id, field_name, filled_count, fill_rate, donor_source),
        )


def write_step4_stats(stats: dict[str, Any]) -> None:
    execute('DELETE FROM rebuild5_meta.step4_run_stats WHERE run_id = %s', (stats['run_id'],))
    execute(
        """
        INSERT INTO rebuild5_meta.step4_run_stats (
            run_id, batch_id, dataset_key, snapshot_version, snapshot_version_prev, status,
            started_at, finished_at,
            total_path_a, donor_matched_count,
            gps_filled, rsrp_filled, rsrq_filled, sinr_filled,
            operator_filled, lac_filled, tech_filled,
            gps_anomaly_count, collision_skip_anomaly_count,
            donor_excellent_count, donor_qualified_count,
            gps_fill_rate, signal_fill_rate, operator_fill_rate,
            remaining_none_gps, remaining_none_signal
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            NOW(), NOW(),
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s
        )
        """,
        (
            stats['run_id'], stats['batch_id'], stats['dataset_key'],
            stats['snapshot_version'], stats['snapshot_version_prev'], stats['status'],
            stats['total_path_a'], stats['donor_matched_count'],
            stats['gps_filled'], stats['rsrp_filled'], stats['rsrq_filled'], stats['sinr_filled'],
            stats['operator_filled'], stats['lac_filled'], stats['tech_filled'],
            stats['gps_anomaly_count'], stats['collision_skip_anomaly_count'],
            stats['donor_excellent_count'], stats['donor_qualified_count'],
            stats['gps_fill_rate'], stats['signal_fill_rate'], stats['operator_fill_rate'],
            stats['remaining_none_gps'], stats['remaining_none_signal'],
        ),
    )


def write_run_log(*, run_id: str, batch_id: int, snapshot_version: str,
                  status: str, result_summary: dict[str, Any]) -> None:
    execute('DELETE FROM rebuild5_meta.run_log WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rebuild5_meta.run_log (
            run_id, run_type, dataset_key, snapshot_version, status,
            started_at, finished_at, step_chain, result_summary, error
        ) VALUES (
            %s, %s, %s, %s, %s,
            NOW(), NOW(), %s, %s::jsonb, NULL
        )
        """,
        (run_id, 'enrichment', DATASET_KEY, snapshot_version, status,
         'step4', json.dumps(result_summary, ensure_ascii=False)),
    )
