"""Step 1.3: Same-record fill (同报文补齐)."""
from __future__ import annotations

from typing import Any

from ..core.database import execute, fetchone

CLEAN_STAGE_TABLE = 'rebuild5.etl_clean_stage'
FINAL_OUTPUT_TABLE = 'rebuild5.etl_cleaned'
COMPAT_FILLED_VIEW = 'rebuild5.etl_filled'


def step1_fill() -> dict[str, Any]:
    """Fill missing fields using same-record donor logic."""
    before = fetchone(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE lon_raw IS NOT NULL AND gps_valid) AS has_gps,
            COUNT(*) FILTER (WHERE rsrp IS NOT NULL) AS has_rsrp,
            COUNT(*) FILTER (WHERE operator_code IS NOT NULL) AS has_operator,
            COUNT(*) FILTER (WHERE lac IS NOT NULL) AS has_lac
        FROM rebuild5.etl_clean_stage
        """
    )
    input_count = int(before['total']) if before else 0

    execute(f'DROP VIEW IF EXISTS {COMPAT_FILLED_VIEW}')
    execute(f'DROP TABLE IF EXISTS {COMPAT_FILLED_VIEW}')
    execute(f'DROP TABLE IF EXISTS {FINAL_OUTPUT_TABLE}')
    execute(
        r"""
        CREATE TABLE rebuild5.etl_cleaned AS
        WITH
        -- Pool A: stable fields — any source, no time limit, prefer cell_infos
        stable_pool AS (
            SELECT record_id, cell_id,
                (array_agg(operator_code ORDER BY CASE cell_origin WHEN 'cell_infos' THEN 1 ELSE 2 END)
                    FILTER (WHERE operator_code IS NOT NULL))[1] AS p_operator,
                (array_agg(lac ORDER BY CASE cell_origin WHEN 'cell_infos' THEN 1 ELSE 2 END)
                    FILTER (WHERE lac IS NOT NULL))[1] AS p_lac
            FROM rebuild5.etl_clean_stage
            WHERE cell_id IS NOT NULL
            GROUP BY record_id, cell_id
        ),
        -- Pool B: full-fill fields from cell_infos — no time limit
        ci_pool AS (
            SELECT record_id, cell_id,
                (array_agg(lon_raw ORDER BY CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END)
                    FILTER (WHERE lon_raw IS NOT NULL AND gps_valid))[1] AS ci_lon,
                (array_agg(lat_raw ORDER BY CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END)
                    FILTER (WHERE lon_raw IS NOT NULL AND gps_valid))[1] AS ci_lat,
                (array_agg(rsrp ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrp IS NOT NULL))[1] AS ci_rsrp,
                (array_agg(rsrq ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrq IS NOT NULL))[1] AS ci_rsrq,
                (array_agg(sinr ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE sinr IS NOT NULL))[1] AS ci_sinr,
                (array_agg(wifi_name) FILTER (WHERE wifi_name IS NOT NULL))[1] AS ci_wifi_name,
                (array_agg(wifi_mac) FILTER (WHERE wifi_mac IS NOT NULL))[1] AS ci_wifi_mac
            FROM rebuild5.etl_clean_stage
            WHERE cell_id IS NOT NULL AND cell_origin = 'cell_infos'
            GROUP BY record_id, cell_id
        ),
        -- Pool C: time-sensitive fields from ss1 — strongest donor row wins, still gated by 60s
        ss1_pool AS (
            SELECT record_id, cell_id,
                (array_agg(lon_raw ORDER BY CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END)
                    FILTER (WHERE lon_raw IS NOT NULL AND gps_valid))[1] AS s_lon,
                (array_agg(lat_raw ORDER BY CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END)
                    FILTER (WHERE lon_raw IS NOT NULL AND gps_valid))[1] AS s_lat,
                (array_agg(cell_ts_raw ORDER BY CASE WHEN lon_raw IS NOT NULL AND gps_valid THEN 0 ELSE 1 END)
                    FILTER (WHERE lon_raw IS NOT NULL AND gps_valid))[1] AS s_gps_ts,
                (array_agg(rsrp ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrp IS NOT NULL))[1] AS s_rsrp,
                (array_agg(cell_ts_raw ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrp IS NOT NULL))[1] AS s_rsrp_ts,
                (array_agg(rsrq ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrq IS NOT NULL))[1] AS s_rsrq,
                (array_agg(cell_ts_raw ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE rsrq IS NOT NULL))[1] AS s_rsrq_ts,
                (array_agg(sinr ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE sinr IS NOT NULL))[1] AS s_sinr,
                (array_agg(cell_ts_raw ORDER BY rsrp DESC NULLS LAST)
                    FILTER (WHERE sinr IS NOT NULL))[1] AS s_sinr_ts,
                (array_agg(wifi_name) FILTER (WHERE wifi_name IS NOT NULL))[1] AS s_wifi_name,
                (array_agg(wifi_mac) FILTER (WHERE wifi_mac IS NOT NULL))[1] AS s_wifi_mac,
                (array_agg(cell_ts_raw) FILTER (WHERE wifi_name IS NOT NULL))[1] AS s_wifi_ts
            FROM rebuild5.etl_clean_stage
            WHERE cell_id IS NOT NULL AND cell_origin = 'ss1'
            GROUP BY record_id, cell_id
        )
        SELECT
            c.dataset_key, c.source_table, c.record_id, c.data_source, c.data_source_detail, c.cell_origin,
            c.tech_raw, c.tech_norm, c.operator_code, c.lac, c.cell_id,
            c.pci, c.freq_channel, c.bandwidth,
            c.rsrp, c.rsrq, c.sinr, c.rssi, c.dbm, c.asu_level, c.sig_level, c.sig_ss,
            c.timing_advance, c.csi_rsrp, c.csi_rsrq, c.csi_sinr, c.cqi,
            c.ts_raw, c.report_ts, c.cell_ts_raw, c.cell_ts_std, c.gps_ts_raw, c.gps_ts,
            c.event_time_std, c.event_time_source,
            c.gps_info_type, c.gps_valid, c.lon_raw, c.lat_raw, c.gps_filled_from,
            c.has_cell_id, c.dev_id, c.ip, c.plmn_main, c.brand, c.model, c.sdk_ver, c.oaid, c.pkg_name,
            c.wifi_name, c.wifi_mac, c.cpu_info, c.pressure,
            c.bs_id, c.sector_id, c.operator_cn,
            -- Full-fill policy: cell_infos donor is always allowed; ss1 donor needs <=60s
            (
                c.cell_origin = 'cell_infos'
                OR ci.record_id IS NOT NULL
                OR (
                    s.record_id IS NOT NULL
                    AND c.cell_ts_raw ~ '^\d{10}$'
                    AND s.s_gps_ts ~ '^\d{10}$'
                    AND ABS(c.cell_ts_raw::bigint - s.s_gps_ts::bigint) <= 60
                )
            ) AS allow_full_fill,
            -- Stable fields: operator (any source, no time limit)
            COALESCE(c.operator_code, sp.p_operator) AS operator_filled,
            CASE WHEN c.operator_code IS NOT NULL THEN 'original'
                 WHEN sp.p_operator IS NOT NULL THEN 'same_cell' ELSE 'none' END AS operator_fill_source,
            -- Stable fields: lac
            COALESCE(c.lac, sp.p_lac) AS lac_filled,
            CASE WHEN c.lac IS NOT NULL THEN 'original'
                 WHEN sp.p_lac IS NOT NULL THEN 'same_cell' ELSE 'none' END AS lac_fill_source,
            -- GPS: original -> cell_infos pool -> ss1 pool (60s check)
            CASE WHEN c.lon_raw IS NOT NULL AND c.gps_valid THEN c.lon_raw
                 WHEN ci.ci_lon IS NOT NULL THEN ci.ci_lon
                 WHEN s.s_lon IS NOT NULL
                      AND c.cell_ts_raw ~ '^\d{10}$' AND s.s_gps_ts ~ '^\d{10}$'
                      AND ABS(c.cell_ts_raw::bigint - s.s_gps_ts::bigint) <= 60 THEN s.s_lon
            END AS lon_filled,
            CASE WHEN c.lat_raw IS NOT NULL AND c.gps_valid THEN c.lat_raw
                 WHEN ci.ci_lat IS NOT NULL THEN ci.ci_lat
                 WHEN s.s_lat IS NOT NULL
                      AND c.cell_ts_raw ~ '^\d{10}$' AND s.s_gps_ts ~ '^\d{10}$'
                      AND ABS(c.cell_ts_raw::bigint - s.s_gps_ts::bigint) <= 60 THEN s.s_lat
            END AS lat_filled,
            CASE WHEN c.gps_filled_from = 'raw_gps' THEN 'raw_gps'
                 WHEN c.gps_filled_from = 'ss1_own' THEN 'ss1_own'
                 WHEN ci.ci_lon IS NOT NULL THEN 'same_cell'
                 WHEN s.s_lon IS NOT NULL
                      AND c.cell_ts_raw ~ '^\d{10}$' AND s.s_gps_ts ~ '^\d{10}$'
                      AND ABS(c.cell_ts_raw::bigint - s.s_gps_ts::bigint) <= 60 THEN 'same_cell'
                 ELSE 'none'
            END AS gps_fill_source,
            -- RSRP: original -> cell_infos pool -> ss1 pool (60s check)
            COALESCE(c.rsrp,
                ci.ci_rsrp,
                CASE WHEN c.cell_ts_raw ~ '^\d{10}$' AND s.s_rsrp_ts ~ '^\d{10}$'
                          AND ABS(c.cell_ts_raw::bigint - s.s_rsrp_ts::bigint) <= 60 THEN s.s_rsrp END
            ) AS rsrp_filled,
            CASE WHEN c.rsrp IS NOT NULL THEN 'original'
                 WHEN ci.ci_rsrp IS NOT NULL THEN 'same_cell'
                 WHEN s.s_rsrp IS NOT NULL
                      AND c.cell_ts_raw ~ '^\d{10}$' AND s.s_rsrp_ts ~ '^\d{10}$'
                      AND ABS(c.cell_ts_raw::bigint - s.s_rsrp_ts::bigint) <= 60 THEN 'same_cell'
                 ELSE 'none' END AS rsrp_fill_source,
            -- RSRQ
            COALESCE(c.rsrq,
                ci.ci_rsrq,
                CASE WHEN c.cell_ts_raw ~ '^\d{10}$' AND s.s_rsrq_ts ~ '^\d{10}$'
                          AND ABS(c.cell_ts_raw::bigint - s.s_rsrq_ts::bigint) <= 60 THEN s.s_rsrq END
            ) AS rsrq_filled,
            -- SINR
            COALESCE(c.sinr,
                ci.ci_sinr,
                CASE WHEN c.cell_ts_raw ~ '^\d{10}$' AND s.s_sinr_ts ~ '^\d{10}$'
                          AND ABS(c.cell_ts_raw::bigint - s.s_sinr_ts::bigint) <= 60 THEN s.s_sinr END
            ) AS sinr_filled,
            -- WiFi
            COALESCE(c.wifi_name,
                ci.ci_wifi_name,
                CASE WHEN c.cell_ts_raw ~ '^\d{10}$' AND s.s_wifi_ts ~ '^\d{10}$'
                          AND ABS(c.cell_ts_raw::bigint - s.s_wifi_ts::bigint) <= 60 THEN s.s_wifi_name END
            ) AS wifi_name_filled,
            COALESCE(c.wifi_mac,
                ci.ci_wifi_mac,
                CASE WHEN c.cell_ts_raw ~ '^\d{10}$' AND s.s_wifi_ts ~ '^\d{10}$'
                          AND ABS(c.cell_ts_raw::bigint - s.s_wifi_ts::bigint) <= 60 THEN s.s_wifi_mac END
            ) AS wifi_mac_filled
        FROM rebuild5.etl_clean_stage c
        LEFT JOIN stable_pool sp ON sp.record_id = c.record_id AND sp.cell_id = c.cell_id
        LEFT JOIN ci_pool ci ON ci.record_id = c.record_id AND ci.cell_id = c.cell_id
        LEFT JOIN ss1_pool s ON s.record_id = c.record_id AND s.cell_id = c.cell_id
        """
    )
    execute(f'ALTER TABLE {FINAL_OUTPUT_TABLE} SET (autovacuum_enabled = false)')
    execute(f'CREATE VIEW {COMPAT_FILLED_VIEW} AS SELECT * FROM {FINAL_OUTPUT_TABLE}')

    after = fetchone(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE gps_fill_source = 'raw_gps') AS gps_raw_gps,
            COUNT(*) FILTER (WHERE gps_fill_source = 'ss1_own') AS gps_ss1_own,
            COUNT(*) FILTER (WHERE gps_fill_source = 'same_cell') AS gps_filled,
            COUNT(*) FILTER (WHERE gps_fill_source = 'none') AS gps_none,
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'original') AS rsrp_original,
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'same_cell') AS rsrp_filled,
            COUNT(*) FILTER (WHERE rsrp_fill_source = 'none') AS rsrp_none,
            COUNT(*) FILTER (WHERE operator_fill_source = 'same_cell') AS operator_filled_cnt,
            COUNT(*) FILTER (WHERE lac_fill_source = 'same_cell') AS lac_filled_cnt
        FROM rebuild5.etl_cleaned
        """
    )
    total = int(after['total']) if after else 0
    return {
        'input_count': input_count,
        'output_count': total,
        'before': {
            'total': int(before['total']) if before else 0,
            'has_gps': int(before['has_gps']) if before else 0,
            'has_rsrp': int(before['has_rsrp']) if before else 0,
            'has_operator': int(before['has_operator']) if before else 0,
            'has_lac': int(before['has_lac']) if before else 0,
        },
        'after': {
            'total': total,
            'gps_raw_gps': int(after['gps_raw_gps']) if after else 0,
            'gps_ss1_own': int(after['gps_ss1_own']) if after else 0,
            'gps_filled': int(after['gps_filled']) if after else 0,
            'gps_none': int(after['gps_none']) if after else 0,
            'rsrp_original': int(after['rsrp_original']) if after else 0,
            'rsrp_filled': int(after['rsrp_filled']) if after else 0,
            'rsrp_none': int(after['rsrp_none']) if after else 0,
            'operator_filled': int(after['operator_filled_cnt']) if after else 0,
            'lac_filled': int(after['lac_filled_cnt']) if after else 0,
        },
    }
