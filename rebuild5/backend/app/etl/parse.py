"""Step 1.1: Parse raw data into structured records."""
from __future__ import annotations

from typing import Any

from .source_prep import DATASET_KEY
from ..core.database import execute, fetchone


def step1_parse() -> dict[str, Any]:
    """Parse cell_infos and ss1 from raw_gps into etl_parsed."""
    raw_count = fetchone('SELECT COUNT(*) AS total FROM rebuild5.raw_gps')
    input_count = int(raw_count['total']) if raw_count else 0

    _parse_cell_infos('rebuild5.raw_gps', 'raw_gps', 'rebuild5.etl_ci')
    _parse_ss1('rebuild5.raw_gps', 'raw_gps', 'rebuild5.etl_ss1')

    execute('DROP TABLE IF EXISTS rebuild5.etl_parsed')
    execute(
        """
        CREATE TABLE rebuild5.etl_parsed AS
        SELECT * FROM rebuild5.etl_ci
        UNION ALL
        SELECT * FROM rebuild5.etl_ss1
        """
    )

    counts = fetchone(
        """
        SELECT
            (SELECT COUNT(*) FROM rebuild5.etl_ci) AS ci,
            (SELECT COUNT(*) FROM rebuild5.etl_ss1) AS ss1,
            (SELECT COUNT(*) FROM rebuild5.etl_parsed) AS total
        """
    )
    output_count = int(counts['total']) if counts else 0
    details = {
        'ci': int(counts['ci']) if counts else 0,
        'ss1': int(counts['ss1']) if counts else 0,
    }
    return {'input_count': input_count, 'output_count': output_count, 'details': details}


def _parse_cell_infos(source_table: str, source_tag: str, target_table: str) -> None:
    execute(f'DROP TABLE IF EXISTS {target_table}')
    execute(
        f"""
        CREATE TABLE {target_table} AS
        SELECT
            '{DATASET_KEY}' AS dataset_key,
            '{source_tag}' AS source_table,
            r."记录数唯一标识" AS record_id,
            'sdk' AS data_source,
            r."数据来源dna或daa" AS data_source_detail,
            'cell_infos' AS cell_origin,
            lower(cell->>'type') AS tech_raw,
            CASE lower(cell->>'type')
                WHEN 'lte' THEN '4G' WHEN 'nr' THEN '5G'
                WHEN 'gsm' THEN '2G' WHEN 'wcdma' THEN '3G'
                ELSE lower(cell->>'type')
            END AS tech_norm,
            COALESCE(
                cell->'cell_identity'->>'mno',
                (cell->'cell_identity'->>'mccString') || (cell->'cell_identity'->>'mncString')
            ) AS operator_code,
            COALESCE(
                (cell->'cell_identity'->>'Tac')::bigint,
                (cell->'cell_identity'->>'tac')::bigint,
                (cell->'cell_identity'->>'lac')::bigint,
                (cell->'cell_identity'->>'Lac')::bigint
            ) AS lac,
            COALESCE(
                (cell->'cell_identity'->>'Ci')::bigint,
                (cell->'cell_identity'->>'Nci')::bigint,
                (cell->'cell_identity'->>'nci')::bigint,
                (cell->'cell_identity'->>'cid')::bigint
            ) AS cell_id,
            (cell->'cell_identity'->>'Pci')::int AS pci,
            COALESCE(
                (cell->'cell_identity'->>'Earfcn')::int,
                (cell->'cell_identity'->>'earfcn')::int,
                (cell->'cell_identity'->>'ChannelNumber')::int,
                (cell->'cell_identity'->>'arfcn')::int,
                (cell->'cell_identity'->>'uarfcn')::int
            ) AS freq_channel,
            (cell->'cell_identity'->>'Bwth')::int AS bandwidth,
            COALESCE((cell->'signal_strength'->>'rsrp')::int, (cell->'signal_strength'->>'SsRsrp')::int) AS rsrp,
            COALESCE((cell->'signal_strength'->>'rsrq')::int, (cell->'signal_strength'->>'SsRsrq')::int) AS rsrq,
            COALESCE((cell->'signal_strength'->>'rssnr')::int, (cell->'signal_strength'->>'SsSinr')::int) AS sinr,
            (cell->'signal_strength'->>'rssi')::int AS rssi,
            (cell->'signal_strength'->>'Dbm')::int AS dbm,
            (cell->'signal_strength'->>'AsuLevel')::int AS asu_level,
            (cell->'signal_strength'->>'Level')::int AS sig_level,
            NULL::int AS sig_ss,
            (cell->'signal_strength'->>'TimingAdvance')::int AS timing_advance,
            (cell->'signal_strength'->>'CsiRsrp')::int AS csi_rsrp,
            (cell->'signal_strength'->>'CsiRsrq')::int AS csi_rsrq,
            (cell->'signal_strength'->>'CsiSinr')::int AS csi_sinr,
            (cell->'signal_strength'->>'cqi')::int AS cqi,
            r."ts" AS ts_raw,
            cell->>'timeStamp' AS cell_ts_raw,
            r."gps上报时间" AS gps_ts_raw,
            r."gps_info_type" AS gps_info_type,
            CASE WHEN r."gps_info_type" IN ('gps','1') THEN true ELSE false END AS gps_valid,
            CASE WHEN r."原始上报gps" IS NOT NULL AND r."原始上报gps" LIKE '%,%'
                THEN split_part(r."原始上报gps", ',', 1)::float8 END AS lon_raw,
            CASE WHEN r."原始上报gps" IS NOT NULL AND r."原始上报gps" LIKE '%,%'
                THEN split_part(r."原始上报gps", ',', 2)::float8 END AS lat_raw,
            'raw_gps' AS gps_filled_from,
            r."did" AS dev_id,
            r."ip" AS ip,
            r."主卡运营商id" AS plmn_main,
            r."品牌" AS brand,
            r."机型" AS model,
            r."sdk_ver" AS sdk_ver,
            r."oaid" AS oaid,
            r."pkg_name" AS pkg_name,
            r."wifi_name" AS wifi_name,
            r."wifi_mac" AS wifi_mac,
            r."cpu_info" AS cpu_info,
            r."压力" AS pressure
        FROM {source_table} r,
            jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
        WHERE r."cell_infos" IS NOT NULL
          AND length(r."cell_infos") > 5
          AND (e.cell->>'isConnected')::int = 1
          AND COALESCE(
                e.cell->'cell_identity'->>'Ci',
                e.cell->'cell_identity'->>'Nci',
                e.cell->'cell_identity'->>'nci',
                e.cell->'cell_identity'->>'cid'
              ) IS NOT NULL
        """
    )


def _parse_ss1(source_table: str, source_tag: str, target_table: str) -> None:
    execute(f'DROP TABLE IF EXISTS {target_table}_groups')
    execute(
        f"""
        CREATE TABLE {target_table}_groups AS
        SELECT
            r."记录数唯一标识" AS record_id,
            r."数据来源dna或daa" AS data_source_detail,
            r."ts" AS ts_raw,
            r."gps上报时间" AS gps_ts_raw,
            r."gps_info_type" AS gps_info_type,
            r."did" AS dev_id,
            r."ip" AS ip,
            r."主卡运营商id" AS plmn_main,
            r."品牌" AS brand,
            r."机型" AS model,
            r."sdk_ver" AS sdk_ver,
            r."oaid" AS oaid,
            r."pkg_name" AS pkg_name,
            r."wifi_name" AS wifi_name,
            r."wifi_mac" AS wifi_mac,
            r."cpu_info" AS cpu_info,
            r."压力" AS pressure,
            grp,
            grp_idx,
            split_part(grp, '&', 1) AS sig_block,
            split_part(grp, '&', 2) AS ts_block,
            split_part(grp, '&', 3) AS gps_block,
            split_part(grp, '&', 4) AS cell_block
        FROM {source_table} r,
        LATERAL unnest(string_to_array(trim(trailing ';' FROM NULLIF(btrim(r."ss1"), '')), ';')) WITH ORDINALITY AS t(grp, grp_idx)
        WHERE r."ss1" IS NOT NULL AND length(r."ss1") > 5
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}_carry')
    execute(
        f"""
        CREATE TABLE {target_table}_carry AS
        SELECT g.*,
            CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[lnge]'
                THEN cell_block ELSE NULL END AS cb_own,
            COALESCE(
                CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[lnge]'
                    THEN cell_block ELSE NULL END,
                MAX(CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[lnge]'
                    THEN cell_block ELSE NULL END)
                    OVER (PARTITION BY record_id ORDER BY grp_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            ) AS cell_block_resolved
        FROM {target_table}_groups g
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}')
    execute(
        f"""
        CREATE TABLE {target_table} AS
        WITH cells AS (
            SELECT
                '{DATASET_KEY}' AS dataset_key,
                '{source_tag}' AS source_table,
                c.record_id,
                c.data_source_detail,
                c.grp_idx,
                c.ts_raw,
                c.ts_block,
                c.gps_block,
                c.gps_ts_raw,
                c.gps_info_type,
                c.sig_block,
                c.dev_id,
                c.ip,
                c.plmn_main,
                c.brand,
                c.model,
                c.sdk_ver,
                c.oaid,
                c.pkg_name,
                c.wifi_name,
                c.wifi_mac,
                c.cpu_info,
                c.pressure,
                left(cell_entry, 1) AS cell_tech,
                split_part(cell_entry, ',', 2) AS cid_str,
                split_part(cell_entry, ',', 3) AS lac_str,
                split_part(cell_entry, ',', 4) AS plmn_str
            FROM {target_table}_carry c,
                 unnest(string_to_array(rtrim(c.cell_block_resolved, '+'), '+')) AS cell_entry
            WHERE c.cell_block_resolved IS NOT NULL
              AND c.cell_block_resolved != ''
              AND length(cell_entry) > 2
              AND cell_entry ~ '^[lnge],'
              AND split_part(cell_entry, ',', 2) NOT IN ('', '-1')
        ),
        sigs AS (
            SELECT record_id, grp_idx,
                left(sig_entry, 1) AS sig_tech,
                split_part(sig_entry, ',', 2) AS ss_val,
                split_part(sig_entry, ',', 3) AS rsrp_val,
                split_part(sig_entry, ',', 4) AS rsrq_val,
                split_part(sig_entry, ',', 5) AS sinr_val
            FROM (
                SELECT record_id, grp_idx, unnest(string_to_array(rtrim(sig_block, '+'), '+')) AS sig_entry
                FROM {target_table}_carry
                WHERE sig_block IS NOT NULL AND sig_block != ''
            ) sub
            WHERE length(sig_entry) > 2 AND sig_entry ~ '^[lng]'
        )
        SELECT
            dataset_key,
            source_table,
            c.record_id,
            'sdk' AS data_source,
            c.data_source_detail,
            'ss1' AS cell_origin,
            c.cell_tech AS tech_raw,
            CASE c.cell_tech WHEN 'l' THEN '4G' WHEN 'n' THEN '5G' WHEN 'g' THEN '2G' ELSE c.cell_tech END AS tech_norm,
            NULLIF(c.plmn_str, '') AS operator_code,
            CASE WHEN c.lac_str ~ '^\\d+$' THEN c.lac_str::bigint END AS lac,
            CASE WHEN c.cid_str ~ '^\\d+$' THEN c.cid_str::bigint END AS cell_id,
            NULL::int AS pci,
            NULL::int AS freq_channel,
            NULL::int AS bandwidth,
            CASE WHEN s.rsrp_val ~ '^-?\\d+$' AND s.rsrp_val != '-1' THEN s.rsrp_val::int END AS rsrp,
            CASE WHEN s.rsrq_val ~ '^-?\\d+$' AND s.rsrq_val != '-1' THEN s.rsrq_val::int END AS rsrq,
            CASE WHEN s.sinr_val ~ '^-?\\d+$' AND s.sinr_val != '-1' THEN s.sinr_val::int END AS sinr,
            NULL::int AS rssi,
            NULL::int AS dbm,
            NULL::int AS asu_level,
            NULL::int AS sig_level,
            CASE WHEN s.ss_val ~ '^-?\\d+$' AND s.ss_val != '-1' THEN s.ss_val::int END AS sig_ss,
            NULL::int AS timing_advance,
            NULL::int AS csi_rsrp,
            NULL::int AS csi_rsrq,
            NULL::int AS csi_sinr,
            NULL::int AS cqi,
            c.ts_raw,
            c.ts_block AS cell_ts_raw,
            c.gps_ts_raw,
            c.gps_info_type,
            CASE
                WHEN c.gps_info_type IN ('gps', '1')
                 AND c.gps_block != '0'
                 AND c.gps_block ~ '^\\d+\\.\\d+,\\d+\\.\\d+'
                THEN true
                ELSE false
            END AS gps_valid,
            CASE WHEN c.gps_block ~ '^\\d+\\.\\d+,' THEN split_part(c.gps_block, ',', 1)::float8 END AS lon_raw,
            CASE WHEN c.gps_block ~ '^\\d+\\.\\d+,\\d+\\.\\d+' THEN split_part(c.gps_block, ',', 2)::float8 END AS lat_raw,
            CASE WHEN c.gps_block != '0' AND c.gps_block ~ '^\\d+\\.\\d+,' THEN 'ss1_own' ELSE 'none' END AS gps_filled_from,
            c.dev_id,
            c.ip,
            c.plmn_main,
            c.brand,
            c.model,
            c.sdk_ver,
            c.oaid,
            c.pkg_name,
            c.wifi_name,
            c.wifi_mac,
            c.cpu_info,
            c.pressure
        FROM cells c
        LEFT JOIN sigs s
          ON s.record_id = c.record_id AND s.grp_idx = c.grp_idx AND s.sig_tech = c.cell_tech
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}_groups')
    execute(f'DROP TABLE IF EXISTS {target_table}_carry')
