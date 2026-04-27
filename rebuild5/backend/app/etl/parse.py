"""Step 1.1: Parse raw data into structured records."""
from __future__ import annotations

from typing import Any

import yaml

from .source_prep import DATASET_KEY
from ..core.database import execute, fetchone
from ..core.settings import settings


_CELL_INFOS_CFG_CACHE: dict[str, float] | None = None


def _load_cell_infos_cfg() -> dict[str, float]:
    """Load cell_infos ETL params from antitoxin_params.yaml (section etl_cell_infos).

    Rule ODS-019: filter stale cached cells whose age_sec > max_age_sec.
    Fallback to defaults if config missing.
    """
    global _CELL_INFOS_CFG_CACHE
    if _CELL_INFOS_CFG_CACHE is not None:
        return _CELL_INFOS_CFG_CACHE
    path = settings.antitoxin_params_path
    cfg: dict[str, Any] = {}
    if path.exists():
        with path.open('r', encoding='utf-8') as f:
            payload = yaml.safe_load(f) or {}
        cfg = payload.get('etl_cell_infos') or {}
    _CELL_INFOS_CFG_CACHE = {
        'max_age_sec': float(cfg.get('max_age_sec', 300)),
    }
    return _CELL_INFOS_CFG_CACHE


_SS1_CFG_CACHE: dict[str, Any] | None = None


def _load_ss1_cfg() -> dict[str, Any]:
    """Load ss1 ETL params from antitoxin_params.yaml (section etl_ss1).

    Rules:
      - ODS-020: drop sub-records whose batch_max_ts - ts_sec > max_age_from_anchor_sec
      - ODS-021: only keep cells whose tech matches a sig in the same sub-record
      - ODS-022: drop sig entries where ss/rsrp/rsrq/sinr are all -1
    Fallback to defaults if config missing.
    """
    global _SS1_CFG_CACHE
    if _SS1_CFG_CACHE is not None:
        return _SS1_CFG_CACHE
    path = settings.antitoxin_params_path
    cfg: dict[str, Any] = {}
    if path.exists():
        with path.open('r', encoding='utf-8') as f:
            payload = yaml.safe_load(f) or {}
        cfg = payload.get('etl_ss1') or {}
    _SS1_CFG_CACHE = {
        'max_age_from_anchor_sec': float(cfg.get('max_age_from_anchor_sec', 3600)),
        'require_sig_cell_tech_match': bool(cfg.get('require_sig_cell_tech_match', True)),
        'drop_sig_all_minus1': bool(cfg.get('drop_sig_all_minus1', True)),
    }
    return _SS1_CFG_CACHE


def step1_parse() -> dict[str, Any]:
    """Parse cell_infos and ss1 from raw_gps into etl_parsed."""
    raw_count = fetchone('SELECT COUNT(*) AS total FROM rb5.raw_gps')
    input_count = int(raw_count['total']) if raw_count else 0

    _parse_cell_infos('rb5.raw_gps', 'raw_gps', 'rb5.etl_ci')
    _parse_ss1('rb5.raw_gps', 'raw_gps', 'rb5.etl_ss1')

    execute('DROP TABLE IF EXISTS rb5.etl_parsed')
    execute(
        """
        CREATE TABLE rb5.etl_parsed AS
        SELECT * FROM rb5.etl_ci
        UNION ALL
        SELECT * FROM rb5.etl_ss1
        """
    )
    execute('CREATE INDEX IF NOT EXISTS idx_etl_parsed_record ON rb5.etl_parsed (record_id)')
    execute(
        """
        CREATE INDEX IF NOT EXISTS idx_etl_parsed_cell_lookup
        ON rb5.etl_parsed (operator_code, lac, cell_id, tech_norm)
        """
    )

    counts = fetchone(
        """
        SELECT
            (SELECT COUNT(*) FROM rb5.etl_ci) AS ci,
            (SELECT COUNT(*) FROM rb5.etl_ss1) AS ss1,
            (SELECT COUNT(*) FROM rb5.etl_parsed) AS total
        """
    )
    output_count = int(counts['total']) if counts else 0
    details = {
        'ci': int(counts['ci']) if counts else 0,
        'ss1': int(counts['ss1']) if counts else 0,
        'ods_019': _collect_ods_019_stats(),
        'ss1_rules': _collect_ss1_rules_stats(),
    }
    return {'input_count': input_count, 'output_count': output_count, 'details': details}


def _collect_ods_019_stats() -> dict[str, Any]:
    """Count how many cell_infos objects ODS-019 / ODS-024b filter.

    Scans raw_gps once; expected cost is comparable to one parse-phase SELECT
    but not structurally heavy. Used by /api/etl/clean-rules to surface
    the drop count in the UI for this run.
    """
    max_age_sec = _load_cell_infos_cfg()['max_age_sec']
    row = fetchone(
        f"""
        WITH expanded AS (
            SELECT
                r."记录数唯一标识" AS record_id,
                COALESCE(
                    e.cell->'cell_identity'->>'Ci',
                    e.cell->'cell_identity'->>'Nci',
                    e.cell->'cell_identity'->>'nci',
                    e.cell->'cell_identity'->>'cid'
                ) AS cell_id_text,
                (e.cell->>'isConnected')::int = 1 AS is_connected,
                (
                    e.cell->>'timeStamp' ~ '^[0-9]+$'
                    AND e.cell->>'past_time' ~ '^[0-9]+(\\.[0-9]+)?$'
                    AND length(e.cell->>'timeStamp') <= 19
                    AND split_part((e.cell->>'past_time'), '.', 1)::bigint
                        - CASE WHEN length(e.cell->>'timeStamp') <= 13
                               THEN (e.cell->>'timeStamp')::numeric / 1000
                               ELSE (e.cell->>'timeStamp')::numeric / 1000000000
                          END > {max_age_sec}
                ) AS is_stale
            FROM rb5.raw_gps r,
                 jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
            WHERE r."cell_infos" IS NOT NULL AND length(r."cell_infos") > 5
        ),
        kept_connected AS (
            SELECT *
            FROM expanded
            WHERE is_connected
              AND cell_id_text IS NOT NULL
              AND NOT COALESCE(is_stale, false)
        )
        SELECT
            COUNT(*) FILTER (WHERE is_connected) AS total_connected,
            COUNT(*) FILTER (WHERE is_connected AND is_stale) AS dropped_stale,
            (SELECT COUNT(*) FROM kept_connected) AS total_after_ods019,
            (SELECT COALESCE(SUM(cnt - 1), 0)
             FROM (
                 SELECT record_id, cell_id_text, COUNT(*) AS cnt
                 FROM kept_connected
                 GROUP BY record_id, cell_id_text
                 HAVING COUNT(*) > 1
             ) d) AS dropped_duplicate
        FROM expanded
        """
    )
    total = int(row['total_connected']) if row else 0
    dropped = int(row['dropped_stale']) if row else 0
    total_after_ods019 = int(row['total_after_ods019']) if row else 0
    duplicate = int(row['dropped_duplicate']) if row else 0
    return {
        'max_age_sec': max_age_sec,
        'total_connected_objects': total,
        'dropped_stale_count': dropped,
        'kept_count': max(total - dropped, 0),
        'drop_rate': round(dropped / total, 4) if total else 0.0,
        'ods_024b': {
            'dropped_duplicate_count': duplicate,
            'total_after_ods019': total_after_ods019,
            'drop_rate': round(duplicate / total_after_ods019, 4) if total_after_ods019 else 0.0,
        },
    }


def _collect_ss1_rules_stats() -> dict[str, Any]:
    """Count drop volumes for ODS-020/021/022 on ss1.

    Expansion logic matches _parse_ss1 so numbers reflect the actual rule effect.
    Scans raw_gps once; used by /api/etl/clean-rules to surface drops in the UI.
    """
    cfg = _load_ss1_cfg()
    max_age = cfg['max_age_from_anchor_sec']
    row = fetchone(
        f"""
        WITH grp AS (
            SELECT r."记录数唯一标识" AS record_id,
                   t.grp, t.grp_idx,
                   split_part(t.grp, '&', 1) AS sig_block,
                   split_part(t.grp, '&', 4) AS cell_block,
                   CASE WHEN split_part(t.grp, '&', 2) ~ '^[0-9]+$'
                          AND length(split_part(t.grp, '&', 2)) <= 19 THEN
                     CASE WHEN length(split_part(t.grp, '&', 2)) >= 13
                          THEN floor(split_part(t.grp, '&', 2)::numeric / 1000)::bigint
                          ELSE split_part(t.grp, '&', 2)::bigint END
                   END AS ts_sec
            FROM rb5.raw_gps r,
                 LATERAL unnest(string_to_array(trim(trailing ';' FROM NULLIF(btrim(r."ss1"), '')), ';'))
                         WITH ORDINALITY AS t(grp, grp_idx)
            WHERE r."ss1" IS NOT NULL AND length(r."ss1") > 5
        ),
        anchored AS (
            SELECT g.*, MAX(ts_sec) OVER (PARTITION BY record_id) AS batch_max_ts_sec
            FROM grp g
        )
        SELECT
            -- ODS-020: 按批内锚点过滤（age > {max_age}）的子记录数
            COUNT(*) FILTER (WHERE batch_max_ts_sec IS NOT NULL AND ts_sec IS NOT NULL
                             AND batch_max_ts_sec - ts_sec > {max_age}) AS ods_020_dropped_subrec,
            COUNT(*) AS total_subrec,
            -- ODS-022: sig 全 -1 条目数
            (SELECT COUNT(*)
             FROM anchored a, LATERAL unnest(string_to_array(rtrim(a.sig_block, '+'), '+')) AS se
             WHERE a.sig_block IS NOT NULL AND a.sig_block != ''
               AND se ~ '^[lng],-1,-1,-1,-1') AS ods_022_all_minus1_sigs,
            (SELECT COUNT(*)
             FROM anchored a, LATERAL unnest(string_to_array(rtrim(a.sig_block, '+'), '+')) AS se
             WHERE a.sig_block IS NOT NULL AND a.sig_block != ''
               AND length(se) > 2 AND se ~ '^[lng]') AS total_sigs
        FROM anchored
        """
    ) or {}
    total_sub = int(row.get('total_subrec') or 0)
    d020 = int(row.get('ods_020_dropped_subrec') or 0)
    total_sigs = int(row.get('total_sigs') or 0)
    d022 = int(row.get('ods_022_all_minus1_sigs') or 0)
    return {
        'max_age_from_anchor_sec': max_age,
        'ods_020': {
            'dropped_subrec': d020,
            'total_subrec': total_sub,
            'drop_rate': round(d020 / total_sub, 4) if total_sub else 0.0,
        },
        'ods_022': {
            'dropped_sigs': d022,
            'total_sigs': total_sigs,
            'drop_rate': round(d022 / total_sigs, 4) if total_sigs else 0.0,
        },
    }


def _parse_cell_infos(source_table: str, source_tag: str, target_table: str) -> None:
    max_age_sec = _load_cell_infos_cfg()['max_age_sec']
    execute(f'DROP TABLE IF EXISTS {target_table}')
    execute(
        f"""
        CREATE TABLE {target_table} AS
        SELECT DISTINCT ON (record_id, cell_id)
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
          -- ODS-019: filter stale cached cells (age_sec > max_age_sec).
          -- 秒级粒度比较，timeStamp 用 numeric 运算防止纳秒值溢出 bigint。
          -- timeStamp 单位按字符串长度自动识别：
          --   <= 13 位 → 毫秒 (/ 10^3 得秒)
          --   >= 14 位 → 纳秒 (/ 10^9 得秒) - 实测约 9% 设备使用纳秒
          -- Field missing / malformed → KEEP (conservative fallback).
          AND (
              e.cell->>'timeStamp' IS NULL
              OR e.cell->>'past_time' IS NULL
              OR NOT (e.cell->>'timeStamp' ~ '^[0-9]+$')
              OR NOT (e.cell->>'past_time' ~ '^[0-9]+(\\.[0-9]+)?$')
              -- 防 bigint 溢出（某些 SDK 会上报 19+ 位异常大值 9223372036854776000 等）：
              -- 长度 > 19 的畸形 timeStamp 按 KEEP 兜底
              OR length(e.cell->>'timeStamp') > 19
              OR (
                  -- 使用 ::numeric 防止运算中间值溢出 bigint
                  split_part((e.cell->>'past_time'), '.', 1)::bigint
                  - CASE WHEN length(e.cell->>'timeStamp') <= 13
                         THEN (e.cell->>'timeStamp')::numeric / 1000
                         ELSE (e.cell->>'timeStamp')::numeric / 1000000000
                    END
                  <= {max_age_sec}
              )
          )
        -- ODS-024b: 同 (record_id, cell_id) 若 cell_infos 内重复出现，保留 age 最小（最新）那条；
        -- 全库 7.2% 的 cell_infos 行会被清理，其中污染 cell 重复率约为真基站的 3 倍，对症去噪。
        ORDER BY
            record_id,
            cell_id,
            CASE
                WHEN e.cell->>'timeStamp' IS NULL OR e.cell->>'past_time' IS NULL THEN NULL::numeric
                WHEN NOT (e.cell->>'timeStamp' ~ '^[0-9]+$') THEN NULL::numeric
                WHEN NOT (e.cell->>'past_time' ~ '^[0-9]+(\\.[0-9]+)?$') THEN NULL::numeric
                WHEN length(e.cell->>'timeStamp') > 19 THEN NULL::numeric
                WHEN length(e.cell->>'timeStamp') <= 13 THEN
                    split_part(e.cell->>'past_time', '.', 1)::numeric - (e.cell->>'timeStamp')::numeric / 1000
                ELSE
                    split_part(e.cell->>'past_time', '.', 1)::numeric - (e.cell->>'timeStamp')::numeric / 1000000000
            END ASC NULLS LAST,
            rsrp DESC NULLS LAST
        """
    )


def _parse_ss1(source_table: str, source_tag: str, target_table: str) -> None:
    ss1_cfg = _load_ss1_cfg()
    max_age_from_anchor_sec = ss1_cfg['max_age_from_anchor_sec']

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
            split_part(grp, '&', 4) AS cell_block,
            -- ODS-020: 解析 ts_sec 供批内锚点过滤用（支持秒/毫秒格式）
            -- 秒级粒度，用 numeric 先除法再转 bigint，避免异常大毫秒值溢出。
            CASE WHEN split_part(grp, '&', 2) ~ '^[0-9]+$'
                   AND length(split_part(grp, '&', 2)) <= 19 THEN
              CASE WHEN length(split_part(grp, '&', 2)) >= 13
                   THEN floor(split_part(grp, '&', 2)::numeric / 1000)::bigint
                   ELSE split_part(grp, '&', 2)::bigint
              END
            END AS ts_sec
        FROM {source_table} r,
        LATERAL unnest(string_to_array(trim(trailing ';' FROM NULLIF(btrim(r."ss1"), '')), ';')) WITH ORDINALITY AS t(grp, grp_idx)
        WHERE r."ss1" IS NOT NULL AND length(r."ss1") > 5
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}_step1')
    execute(
        f"""
        CREATE TABLE {target_table}_step1 AS
        SELECT g.*,
            CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[lng]'
                 THEN cell_block ELSE NULL END AS cb_own,
            -- 疑点 1 修复：用"最近有效行的 grp_idx"而非字典序 MAX(cell_block)
            -- 取截至当前行为止最近一个有效 cell_block 所在的 grp_idx
            MAX(CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[lng]'
                     THEN grp_idx END)
              OVER (PARTITION BY dev_id, record_id
                    ORDER BY grp_idx
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS resolved_grp_idx,
            -- ODS-020: 批内 max(ts_sec) 作为锚点（NULL 不参与 MAX）
            MAX(ts_sec) OVER (PARTITION BY dev_id, record_id) AS batch_max_ts_sec
        FROM {target_table}_groups g
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}_carry')
    execute(
        f"""
        CREATE TABLE {target_table}_carry AS
        SELECT s1.*,
          s2.cb_own AS cell_block_resolved
        FROM {target_table}_step1 s1
        LEFT JOIN {target_table}_step1 s2
          ON s2.dev_id = s1.dev_id
         AND s2.record_id = s1.record_id
         AND s2.grp_idx = s1.resolved_grp_idx
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
              -- 疑点 2: cell tech 对齐 sig 只收 l/n/g（e 制式实测占比 0）
              AND cell_entry ~ '^[lng],'
              -- 规则 2: CI 必须有效（非空、非 -1）
              AND split_part(cell_entry, ',', 2) NOT IN ('', '-1')
              -- ODS-020: 子记录时间在批内锚点 1 小时内（字段缺失时保守 KEEP）
              AND (
                c.ts_sec IS NULL OR c.batch_max_ts_sec IS NULL
                OR c.batch_max_ts_sec - c.ts_sec <= {max_age_from_anchor_sec}
              )
        ),
        sigs AS (
            SELECT dev_id, record_id, grp_idx,
                left(sig_entry, 1) AS sig_tech,
                split_part(sig_entry, ',', 2) AS ss_val,
                split_part(sig_entry, ',', 3) AS rsrp_val,
                split_part(sig_entry, ',', 4) AS rsrq_val,
                split_part(sig_entry, ',', 5) AS sinr_val
            FROM (
                SELECT c.dev_id, c.record_id, c.grp_idx,
                       unnest(string_to_array(rtrim(c.sig_block, '+'), '+')) AS sig_entry,
                       c.ts_sec, c.batch_max_ts_sec
                FROM {target_table}_carry c
                WHERE c.sig_block IS NOT NULL AND c.sig_block != ''
                  -- ODS-020: sig 条目也按批内锚点过滤
                  AND (
                    c.ts_sec IS NULL OR c.batch_max_ts_sec IS NULL
                    OR c.batch_max_ts_sec - c.ts_sec <= {max_age_from_anchor_sec}
                  )
            ) sub
            WHERE length(sig_entry) > 2 AND sig_entry ~ '^[lng]'
              -- ODS-022: 丢弃 ss/rsrp/rsrq/sinr 全 -1 的无效 sig 条目
              AND NOT sig_entry ~ '^[lng],-1,-1,-1,-1'
        )
        SELECT
            dataset_key,
            source_table,
            c.record_id,
            'sdk' AS data_source,
            c.data_source_detail,
            'ss1' AS cell_origin,
            c.cell_tech AS tech_raw,
            CASE c.cell_tech WHEN 'l' THEN '4G' WHEN 'n' THEN '5G' WHEN 'g' THEN '2G' END AS tech_norm,
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
        -- ODS-021: INNER JOIN 要求 sig_tech = cell_tech，无配套 sig 的 cell 不 emit
        -- 实测 99.3% 双卡场景只有 1 个 sig，另一个 cell 大概率是 SDK 缓存 cell_id。
        -- 真正双信号双卡（NSA）仅占 0.31%，误伤上限很低。
        JOIN sigs s
          ON s.dev_id = c.dev_id
         AND s.record_id = c.record_id
         AND s.grp_idx = c.grp_idx
         AND s.sig_tech = c.cell_tech
        """
    )

    execute(f'DROP TABLE IF EXISTS {target_table}_groups')
    execute(f'DROP TABLE IF EXISTS {target_table}_step1')
    execute(f'DROP TABLE IF EXISTS {target_table}_carry')
