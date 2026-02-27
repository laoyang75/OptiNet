-- Layer_0 数据准备（北京明细 20251201-20251207）
-- 生成两张 L0 标准表：
--   public."Y_codex_Layer0_Gps_base"
--   public."Y_codex_Layer0_Lac"
--
-- 运行提示：
-- - 全量 CTAS 需要较长时间与临时空间。
-- - 原始表索引对“全表解析”加速有限，但便于后续局部查询/排障。
--
-- 依赖注意（重要）：
-- - Layer_2 的 Step00/Step02 视图会依赖 Layer_0 的两张表；直接 DROP Layer_0 表会报“有其它对象依赖”。
-- - 因此本脚本在重建 Layer_0 表前，会先删除依赖它们的下游视图（Step02/Step00），避免你手工 CASCADE。

/* ============================================================================
 * 会话级性能参数（PG15 / 264GB / 40核 / SSD）
 * 参考：lac_enbid_project/服务器配置与SQL调优建议.md
 * ==========================================================================*/
SET statement_timeout = 0;
SET work_mem = '2GB';
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;
SET jit = off;

/* ============================================================================
 * 0.0 清理依赖视图（避免 DROP Layer0 表失败）
 * ==========================================================================*/

DO $$
BEGIN
  -- Step02 视图依赖 Step00 视图；先删 Step02 再删 Step00
  IF to_regclass('public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public'
        AND c.relname='Y_codex_Layer2_Step02_Gps_Compliance_Marked'
        AND c.relkind='v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    END IF;
  END IF;

  IF to_regclass('public."Y_codex_Layer2_Step00_Gps_Std"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public'
        AND c.relname='Y_codex_Layer2_Step00_Gps_Std'
        AND c.relkind='v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step00_Gps_Std"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step00_Gps_Std"';
    END IF;
  END IF;

  IF to_regclass('public."Y_codex_Layer2_Step00_Lac_Std"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public'
        AND c.relname='Y_codex_Layer2_Step00_Lac_Std'
        AND c.relkind='v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step00_Lac_Std"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step00_Lac_Std"';
    END IF;
  END IF;
END $$;

/* ============================================================================
 * 0. 原始表索引（可选，但建议先建）
 * ==========================================================================*/

-- GPS 原始表
CREATE INDEX IF NOT EXISTS idx_bj_gps_20251201_rid
  ON public."网优项目_gps定位北京明细数据_20251201_20251207" ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_bj_gps_20251201_ts
  ON public."网优项目_gps定位北京明细数据_20251201_20251207" (ts);
CREATE INDEX IF NOT EXISTS idx_bj_gps_20251201_did
  ON public."网优项目_gps定位北京明细数据_20251201_20251207" (did);
ANALYZE public."网优项目_gps定位北京明细数据_20251201_20251207";

-- LAC 原始表
CREATE INDEX IF NOT EXISTS idx_bj_lac_20251201_rid
  ON public."网优项目_lac定位北京明细数据_20251201_20251207" ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_bj_lac_20251201_ts
  ON public."网优项目_lac定位北京明细数据_20251201_20251207" (ts);
CREATE INDEX IF NOT EXISTS idx_bj_lac_20251201_did
  ON public."网优项目_lac定位北京明细数据_20251201_20251207" (did);
ANALYZE public."网优项目_lac定位北京明细数据_20251201_20251207";


/* ============================================================================
 * 1. Layer0 GPS：Y_codex_Layer0_Gps_base（带报文顺序 seq_id）
 * ==========================================================================*/

DROP TABLE IF EXISTS public."Y_codex_Layer0_Gps_base";

CREATE TABLE public."Y_codex_Layer0_Gps_base" AS
WITH base AS (
  SELECT
    t."记录数唯一标识" AS record_id,
    t."数据来源dna或daa" AS data_source,
    t.did,
    t.ts,
    t.ip,
    t.sdk_ver,
    t."品牌" AS brand,
    t."机型" AS model,
    t.oaid,
    t.gps_info_type,
    t."原始上报gps" AS gps_raw,
    t."当前数据最终经度" AS lon,
    t."当前数据最终纬度" AS lat,
    t."主卡运营商id" AS plmn_main,
    NULLIF(btrim(t."cell_infos"), '')::jsonb AS cell_infos_json,
    NULLIF(btrim(t.ss1), '') AS ss1,
    t."gps定位北京来源ss1或daa" AS loc_method
  FROM public."网优项目_gps定位北京明细数据_20251201_20251207" t
),
	cell_infos_cells AS (
	  SELECT
	    b.record_id,
	    b.data_source,
	    b.loc_method,
	    b.did,
	    b.ts,
	    b.ip,
	    b.sdk_ver,
	    b.brand,
	    b.model,
	    b.oaid,
	    b.gps_info_type,
	    b.gps_raw,
	    b.lon,
	    b.lat,
	    b.plmn_main,
	    NULLIF(e.value->>'timeStamp','') AS cell_ts,
	    NULLIF(e.value->>'isConnected','')::int AS is_connected_raw,
	    lower(e.value->>'type') AS type_raw,
	    COALESCE(
	      e.value->'cell_identity'->>'Nci',
	      e.value->'cell_identity'->>'nci',
	      e.value->'cell_identity'->>'Ci',
      e.value->'cell_identity'->>'ci'
    ) AS cell_id_raw,
    COALESCE(
      e.value->'cell_identity'->>'Tac',
      e.value->'cell_identity'->>'tac',
      e.value->'cell_identity'->>'Lac',
      e.value->'cell_identity'->>'lac'
    ) AS lac_raw,
    COALESCE(
      e.value->'cell_identity'->>'mno',
      e.value->'cell_identity'->>'Mno',
      (e.value->'cell_identity'->>'mccString') || lpad(COALESCE(e.value->'cell_identity'->>'mncString',''), 2, '0')
    ) AS plmn_id_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rsrp'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsRsrp'), ''),
      NULLIF(btrim(e.value->'string'->>'rsrp'), '')
    ) AS sig_rsrp_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rsrq'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsRsrq'), ''),
      NULLIF(btrim(e.value->'string'->>'rsrq'), '')
    ) AS sig_rsrq_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rssnr'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsSinr'), '')
    ) AS sig_sinr_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'rssi'), '') AS sig_rssi_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'Dbm'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'dbm'), '')
    ) AS sig_dbm_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'AsuLevel'), '') AS sig_asu_level_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'Level'), '') AS sig_level_raw,
    COALESCE(
      NULLIF(btrim(e.value->'string'->>'ss'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'ss'), '')
    ) AS sig_ss_raw
  FROM base b
  CROSS JOIN LATERAL jsonb_each(b.cell_infos_json) AS e(key, value)
  WHERE b.cell_infos_json IS NOT NULL
),
cell_infos_out AS (
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    'cell_infos'::text AS parsed_from,
    'CELL_INFOS'::text AS match_status,
    cell_ts,
    CASE
      WHEN lower(type_raw)='nr' THEN '5G'
      WHEN lower(type_raw)='lte' THEN '4G'
      WHEN lower(type_raw)='wcdma' THEN '3G'
      WHEN lower(type_raw) IN ('gsm','cdma') THEN '2G'
      ELSE NULL
    END AS tech,
    NULLIF(btrim(plmn_id_raw),'') AS "运营商id",
    NULLIF(btrim(lac_raw),'') AS "原始lac",
    NULLIF(btrim(cell_id_raw),'') AS cell_id,
    CASE WHEN lac_raw ~ '^[0-9]+$' THEN lac_raw::bigint END AS lac_dec,
    CASE WHEN cell_id_raw ~ '^[0-9]+$' THEN cell_id_raw::bigint END AS cell_id_dec,
    CASE WHEN sig_rsrp_raw ~ '^-?[0-9]+$' THEN sig_rsrp_raw::int END AS sig_rsrp,
    CASE WHEN sig_rsrq_raw ~ '^-?[0-9]+$' THEN sig_rsrq_raw::int END AS sig_rsrq,
    CASE WHEN sig_sinr_raw ~ '^-?[0-9]+$' THEN sig_sinr_raw::int END AS sig_sinr,
    CASE WHEN sig_rssi_raw ~ '^-?[0-9]+$' THEN sig_rssi_raw::int END AS sig_rssi,
    CASE WHEN sig_dbm_raw ~ '^-?[0-9]+$' THEN sig_dbm_raw::int END AS sig_dbm,
    CASE WHEN sig_asu_level_raw ~ '^-?[0-9]+$' THEN sig_asu_level_raw::int END AS sig_asu_level,
    CASE WHEN sig_level_raw ~ '^-?[0-9]+$' THEN sig_level_raw::int END AS sig_level,
    CASE WHEN sig_ss_raw ~ '^-?[0-9]+$' THEN sig_ss_raw::int END AS sig_ss,
    (is_connected_raw=1) AS is_connected
  FROM cell_infos_cells
	),
	ss1_groups AS (
	  SELECT
	    b.record_id,
	    b.data_source,
	    b.loc_method,
	    b.did,
	    b.ts,
	    b.ip,
	    b.sdk_ver,
	    b.brand,
	    b.model,
	    b.oaid,
	    b.gps_info_type,
	    b.gps_raw,
	    b.lon,
	    b.lat,
	    b.plmn_main,
	    group_txt
	  FROM base b
	  CROSS JOIN LATERAL unnest(string_to_array(b.ss1, chr(59))) AS group_txt
	  WHERE b.ss1 IS NOT NULL AND btrim(group_txt) <> ''
	),
	ss1_group_parts AS (
	  SELECT
	    sg.record_id,
	    sg.data_source,
	    sg.loc_method,
	    sg.did,
	    sg.ts,
	    sg.ip,
	    sg.sdk_ver,
	    sg.brand,
	    sg.model,
	    sg.oaid,
	    sg.gps_info_type,
	    sg.gps_raw,
	    sg.lon,
	    sg.lat,
	    sg.plmn_main,
	    sg.group_txt,
	    string_to_array(sg.group_txt, '&') AS parts
	  FROM ss1_groups sg
	),
	ss1_cells_raw AS (
	  SELECT
	    sgp.record_id,
	    sgp.data_source,
	    sgp.loc_method,
	    sgp.did,
	    sgp.ts,
	    sgp.ip,
	    sgp.sdk_ver,
	    sgp.brand,
	    sgp.model,
	    sgp.oaid,
	    sgp.gps_info_type,
	    sgp.gps_raw,
	    sgp.lon,
	    sgp.lat,
	    sgp.plmn_main,
	    sgp.group_txt,
	    NULLIF(btrim(sgp.parts[2]), '') AS cell_ts,
	    sgp.parts[1] AS sig_part,
	    sgp.parts[4] AS cell_part
	  FROM ss1_group_parts sgp
	  WHERE array_length(sgp.parts,1) >= 4
	),
	ss1_cell_tokens AS (
	  SELECT
	    s.record_id,
	    s.data_source,
	    s.loc_method,
	    s.did,
	    s.ts,
	    s.ip,
	    s.sdk_ver,
	    s.brand,
	    s.model,
	    s.oaid,
	    s.gps_info_type,
	    s.gps_raw,
	    s.lon,
	    s.lat,
	    s.plmn_main,
	    s.group_txt,
	    s.cell_ts,
	    cell_token_txt,
	    ord,
	    row_number() OVER (PARTITION BY s.record_id, s.group_txt ORDER BY ord) AS rn
	  FROM ss1_cells_raw s
  CROSS JOIN LATERAL unnest(string_to_array(s.cell_part, '+')) WITH ORDINALITY AS t(cell_token_txt, ord)
  WHERE s.cell_part IS NOT NULL
    AND btrim(cell_token_txt) <> ''
    AND btrim(cell_token_txt) ~ '^[a-z],[^,]*,[^,]*,[^,]*'
),
ss1_sig_tokens AS (
  SELECT
    s.record_id,
    s.data_source,
    s.loc_method,
    s.did,
    s.ts,
    s.ip,
    s.sdk_ver,
    s.brand,
    s.model,
    s.oaid,
    s.gps_info_type,
    s.gps_raw,
    s.lon,
    s.lat,
    s.plmn_main,
    s.group_txt,
    s.cell_ts,
    sig_token_txt,
    ord,
    row_number() OVER (PARTITION BY s.record_id, s.group_txt ORDER BY ord) AS rn
  FROM ss1_cells_raw s
  CROSS JOIN LATERAL unnest(string_to_array(s.sig_part, '+')) WITH ORDINALITY AS t(sig_token_txt, ord)
  WHERE s.sig_part IS NOT NULL
    AND btrim(sig_token_txt) <> ''
    AND btrim(sig_token_txt) ~ '^[a-z],-?[0-9]+,-?[0-9]+,-?[0-9]+,-?[0-9]+$'
),
ss1_cells AS (
  SELECT
    c.record_id, c.data_source, c.loc_method, c.did, c.ts, c.ip, c.sdk_ver, c.brand, c.model, c.oaid,
    c.gps_info_type, c.gps_raw, c.lon, c.lat, c.plmn_main,
    'ss1'::text AS parsed_from,
    c.cell_ts,
    CASE
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='n' THEN '5G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='l' THEN '4G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='w' THEN '3G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='g' THEN '2G'
      ELSE NULL
    END AS tech,
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 4)), '') AS "运营商id",
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 3)), '') AS "原始lac",
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 2)), '') AS cell_id,
    CASE WHEN split_part(btrim(c.cell_token_txt), ',', 3) ~ '^-?[0-9]+$' THEN split_part(btrim(c.cell_token_txt), ',', 3)::bigint END AS lac_dec,
    CASE WHEN split_part(btrim(c.cell_token_txt), ',', 2) ~ '^-?[0-9]+$' THEN split_part(btrim(c.cell_token_txt), ',', 2)::bigint END AS cell_id_dec,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 2) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 2)::int END AS sig_ss,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 3) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 3)::int END AS sig_rsrp,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 4) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 4)::int END AS sig_rsrq,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 5) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 5)::int END AS sig_sinr,
    NULL::int AS sig_rssi,
    NULL::int AS sig_dbm,
    NULL::int AS sig_asu_level,
    NULL::int AS sig_level
  FROM ss1_cell_tokens c
  LEFT JOIN ss1_sig_tokens st
    ON st.record_id = c.record_id
   AND st.group_txt = c.group_txt
   AND st.rn = c.rn
),
ss1_inherit AS (
  SELECT
    s.record_id, s.data_source, s.loc_method, s.did, s.ts, s.ip, s.sdk_ver, s.brand, s.model, s.oaid,
    s.gps_info_type, s.gps_raw, s.lon, s.lat, s.plmn_main,
    s.parsed_from,
    'SS1_UNMATCHED'::text AS match_status,
    s.cell_ts,
    COALESCE(ci.tech, s.tech) AS tech,
    COALESCE(ci."运营商id", s."运营商id", NULLIF(btrim(s.plmn_main), '')) AS "运营商id",
    COALESCE(ci."原始lac", s."原始lac") AS "原始lac",
    COALESCE(ci.cell_id, s.cell_id) AS cell_id,
    COALESCE(ci.lac_dec, s.lac_dec) AS lac_dec,
    COALESCE(ci.cell_id_dec, s.cell_id_dec) AS cell_id_dec,
    COALESCE(ci.sig_rsrp, s.sig_rsrp) AS sig_rsrp,
    COALESCE(ci.sig_rsrq, s.sig_rsrq) AS sig_rsrq,
    COALESCE(ci.sig_sinr, s.sig_sinr) AS sig_sinr,
    COALESCE(ci.sig_rssi, s.sig_rssi) AS sig_rssi,
    COALESCE(ci.sig_dbm, s.sig_dbm) AS sig_dbm,
    COALESCE(ci.sig_asu_level, s.sig_asu_level) AS sig_asu_level,
    COALESCE(ci.sig_level, s.sig_level) AS sig_level,
    COALESCE(ci.sig_ss, s.sig_ss) AS sig_ss,
    false AS is_connected
  FROM ss1_cells s
  LEFT JOIN cell_infos_out ci
    ON ci.record_id=s.record_id AND ci.cell_id_dec IS NOT NULL AND ci.cell_id_dec=s.cell_id_dec
),
unioned AS (
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    parsed_from, match_status, cell_ts, tech, "运营商id", "原始lac", cell_id, lac_dec, cell_id_dec,
    sig_rsrp, sig_rsrq, sig_sinr, sig_rssi, sig_dbm, sig_asu_level, sig_level, sig_ss,
    is_connected
  FROM cell_infos_out
  UNION ALL
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    parsed_from, match_status, cell_ts, tech, "运营商id", "原始lac", cell_id, lac_dec, cell_id_dec,
    sig_rsrp, sig_rsrq, sig_sinr, sig_rssi, sig_dbm, sig_asu_level, sig_level, sig_ss,
    is_connected
  FROM ss1_inherit s
  WHERE NOT EXISTS (
    SELECT 1 FROM cell_infos_out ci
    WHERE ci.record_id=s.record_id AND ci.cell_id_dec IS NOT NULL AND ci.cell_id_dec=s.cell_id_dec
  )
)
SELECT
  row_number() OVER (
    ORDER BY
      CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END NULLS LAST,
      record_id,
      CASE WHEN parsed_from='cell_infos' THEN 0 ELSE 1 END,
      CASE WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN cell_ts::bigint END NULLS LAST,
      cell_id_dec NULLS LAST
  )::bigint AS seq_id,

  record_id AS "记录id",
  cell_ts,
  CASE
    WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN
      CASE
        WHEN parsed_from='ss1'
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)
        WHEN parsed_from='cell_infos'
         AND char_length(cell_ts) >= 13
         AND cell_ts::bigint BETWEEN 946684800000 AND 4102444800000
        THEN to_timestamp(cell_ts::bigint/1000.0)
        WHEN parsed_from='cell_infos'
         AND char_length(cell_ts) BETWEEN 10 AND 11
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)
        ELSE NULL
      END
  END AS cell_ts_std,

  tech,
  "运营商id",
  "原始lac",
  cell_id,

  lac_dec,
  CASE WHEN lac_dec IS NOT NULL THEN upper(to_hex(lac_dec)) END AS lac_hex,
  cell_id_dec,
  CASE WHEN cell_id_dec IS NOT NULL THEN upper(to_hex(cell_id_dec)) END AS cell_id_hex,

  CASE WHEN lower(tech)='4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec/256::bigint
       WHEN lower(tech)='5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec/4096::bigint END AS bs_id,
  CASE WHEN lower(tech)='4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec%256::bigint
       WHEN lower(tech)='5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec%4096::bigint END AS sector_id,

  gps_raw,
  CASE WHEN btrim(split_part(gps_raw, ',', 1)) ~ '^-?[0-9.]+$' THEN btrim(split_part(gps_raw, ',', 1))::double precision END AS lon_raw,
  CASE WHEN btrim(split_part(gps_raw, ',', 2)) ~ '^-?[0-9.]+$' THEN btrim(split_part(gps_raw, ',', 2))::double precision END AS lat_raw,

  CASE WHEN lon IS NOT NULL AND lat IS NOT NULL THEN lon::text||','||lat::text END AS gps_final,
  lon,
  lat,
  gps_info_type,

  data_source AS "数据来源",
  loc_method AS "北京来源",
  did,
  ts,
  CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END AS ts_std,
  ip,
  sdk_ver,
  brand,
  model,
  oaid,

  parsed_from,
  match_status,
  sig_rsrp,
  sig_rsrq,
  sig_sinr,
  sig_rssi,
  sig_dbm,
  sig_asu_level,
  sig_level,
  sig_ss,
  is_connected
FROM unioned
;

ANALYZE public."Y_codex_Layer0_Gps_base";


/* ============================================================================
 * 2. Layer0 LAC：Y_codex_Layer0_Lac（带报文顺序 seq_id）
 * ==========================================================================*/

DROP TABLE IF EXISTS public."Y_codex_Layer0_Lac";

CREATE TABLE public."Y_codex_Layer0_Lac" AS
WITH base AS (
  SELECT
    t."记录数唯一标识" AS record_id,
    t."数据来源dna或daa" AS data_source,
    t.did,
    t.ts,
    t.ip,
    t.sdk_ver,
    t."品牌" AS brand,
    t."机型" AS model,
    t.oaid,
    t.gps_info_type,
    t."原始上报gps" AS gps_raw,
    t."当前数据最终经度" AS lon,
    t."当前数据最终纬度" AS lat,
    t."主卡运营商id" AS plmn_main,
    NULLIF(btrim(t."cell_infos"), '')::jsonb AS cell_infos_json,
    NULLIF(btrim(t.ss1), '') AS ss1,
    t."lac定位北京来源ss1或daa" AS loc_method
  FROM public."网优项目_lac定位北京明细数据_20251201_20251207" t
),
	cell_infos_cells AS (
	  SELECT
	    b.record_id,
	    b.data_source,
	    b.loc_method,
	    b.did,
	    b.ts,
	    b.ip,
	    b.sdk_ver,
	    b.brand,
	    b.model,
	    b.oaid,
	    b.gps_info_type,
	    b.gps_raw,
	    b.lon,
	    b.lat,
	    b.plmn_main,
	    NULLIF(e.value->>'timeStamp','') AS cell_ts,
	    NULLIF(e.value->>'isConnected','')::int AS is_connected_raw,
	    lower(e.value->>'type') AS type_raw,
	    COALESCE(
	      e.value->'cell_identity'->>'Nci',
	      e.value->'cell_identity'->>'nci',
	      e.value->'cell_identity'->>'Ci',
      e.value->'cell_identity'->>'ci'
    ) AS cell_id_raw,
    COALESCE(
      e.value->'cell_identity'->>'Tac',
      e.value->'cell_identity'->>'tac',
      e.value->'cell_identity'->>'Lac',
      e.value->'cell_identity'->>'lac'
    ) AS lac_raw,
    COALESCE(
      e.value->'cell_identity'->>'mno',
      e.value->'cell_identity'->>'Mno',
      (e.value->'cell_identity'->>'mccString') || lpad(COALESCE(e.value->'cell_identity'->>'mncString',''), 2, '0')
    ) AS plmn_id_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rsrp'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsRsrp'), ''),
      NULLIF(btrim(e.value->'string'->>'rsrp'), '')
    ) AS sig_rsrp_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rsrq'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsRsrq'), ''),
      NULLIF(btrim(e.value->'string'->>'rsrq'), '')
    ) AS sig_rsrq_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'rssnr'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'SsSinr'), '')
    ) AS sig_sinr_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'rssi'), '') AS sig_rssi_raw,
    COALESCE(
      NULLIF(btrim(e.value->'signal_strength'->>'Dbm'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'dbm'), '')
    ) AS sig_dbm_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'AsuLevel'), '') AS sig_asu_level_raw,
    NULLIF(btrim(e.value->'signal_strength'->>'Level'), '') AS sig_level_raw,
    COALESCE(
      NULLIF(btrim(e.value->'string'->>'ss'), ''),
      NULLIF(btrim(e.value->'signal_strength'->>'ss'), '')
    ) AS sig_ss_raw
  FROM base b
  CROSS JOIN LATERAL jsonb_each(b.cell_infos_json) AS e(key, value)
  WHERE b.cell_infos_json IS NOT NULL
),
cell_infos_out AS (
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    'cell_infos'::text AS parsed_from,
    'CELL_INFOS'::text AS match_status,
    cell_ts,
    CASE
      WHEN lower(type_raw)='nr' THEN '5G'
      WHEN lower(type_raw)='lte' THEN '4G'
      WHEN lower(type_raw)='wcdma' THEN '3G'
      WHEN lower(type_raw) IN ('gsm','cdma') THEN '2G'
      ELSE NULL
    END AS tech,
    NULLIF(btrim(plmn_id_raw),'') AS "运营商id",
    NULLIF(btrim(lac_raw),'') AS "原始lac",
    NULLIF(btrim(cell_id_raw),'') AS cell_id,
    CASE WHEN lac_raw ~ '^[0-9]+$' THEN lac_raw::bigint END AS lac_dec,
    CASE WHEN cell_id_raw ~ '^[0-9]+$' THEN cell_id_raw::bigint END AS cell_id_dec,
    CASE WHEN sig_rsrp_raw ~ '^-?[0-9]+$' THEN sig_rsrp_raw::int END AS sig_rsrp,
    CASE WHEN sig_rsrq_raw ~ '^-?[0-9]+$' THEN sig_rsrq_raw::int END AS sig_rsrq,
    CASE WHEN sig_sinr_raw ~ '^-?[0-9]+$' THEN sig_sinr_raw::int END AS sig_sinr,
    CASE WHEN sig_rssi_raw ~ '^-?[0-9]+$' THEN sig_rssi_raw::int END AS sig_rssi,
    CASE WHEN sig_dbm_raw ~ '^-?[0-9]+$' THEN sig_dbm_raw::int END AS sig_dbm,
    CASE WHEN sig_asu_level_raw ~ '^-?[0-9]+$' THEN sig_asu_level_raw::int END AS sig_asu_level,
    CASE WHEN sig_level_raw ~ '^-?[0-9]+$' THEN sig_level_raw::int END AS sig_level,
    CASE WHEN sig_ss_raw ~ '^-?[0-9]+$' THEN sig_ss_raw::int END AS sig_ss,
    (is_connected_raw=1) AS is_connected
  FROM cell_infos_cells
	),
	ss1_groups AS (
	  SELECT
	    b.record_id,
	    b.data_source,
	    b.loc_method,
	    b.did,
	    b.ts,
	    b.ip,
	    b.sdk_ver,
	    b.brand,
	    b.model,
	    b.oaid,
	    b.gps_info_type,
	    b.gps_raw,
	    b.lon,
	    b.lat,
	    b.plmn_main,
	    group_txt
	  FROM base b
	  CROSS JOIN LATERAL unnest(string_to_array(b.ss1, chr(59))) AS group_txt
	  WHERE b.ss1 IS NOT NULL AND btrim(group_txt) <> ''
	),
	ss1_group_parts AS (
	  SELECT
	    sg.record_id,
	    sg.data_source,
	    sg.loc_method,
	    sg.did,
	    sg.ts,
	    sg.ip,
	    sg.sdk_ver,
	    sg.brand,
	    sg.model,
	    sg.oaid,
	    sg.gps_info_type,
	    sg.gps_raw,
	    sg.lon,
	    sg.lat,
	    sg.plmn_main,
	    sg.group_txt,
	    string_to_array(sg.group_txt, '&') AS parts
	  FROM ss1_groups sg
	),
	ss1_cells_raw AS (
	  SELECT
	    sgp.record_id,
	    sgp.data_source,
	    sgp.loc_method,
	    sgp.did,
	    sgp.ts,
	    sgp.ip,
	    sgp.sdk_ver,
	    sgp.brand,
	    sgp.model,
	    sgp.oaid,
	    sgp.gps_info_type,
	    sgp.gps_raw,
	    sgp.lon,
	    sgp.lat,
	    sgp.plmn_main,
	    sgp.group_txt,
	    NULLIF(btrim(sgp.parts[2]), '') AS cell_ts,
	    sgp.parts[1] AS sig_part,
	    sgp.parts[4] AS cell_part
	  FROM ss1_group_parts sgp
	  WHERE array_length(sgp.parts,1) >= 4
	),
	ss1_cell_tokens AS (
	  SELECT
	    s.record_id,
	    s.data_source,
	    s.loc_method,
	    s.did,
	    s.ts,
	    s.ip,
	    s.sdk_ver,
	    s.brand,
	    s.model,
	    s.oaid,
	    s.gps_info_type,
	    s.gps_raw,
	    s.lon,
	    s.lat,
	    s.plmn_main,
	    s.group_txt,
	    s.cell_ts,
	    cell_token_txt,
	    ord,
	    row_number() OVER (PARTITION BY s.record_id, s.group_txt ORDER BY ord) AS rn
	  FROM ss1_cells_raw s
  CROSS JOIN LATERAL unnest(string_to_array(s.cell_part, '+')) WITH ORDINALITY AS t(cell_token_txt, ord)
  WHERE s.cell_part IS NOT NULL
    AND btrim(cell_token_txt) <> ''
    AND btrim(cell_token_txt) ~ '^[a-z],[^,]*,[^,]*,[^,]*'
),
ss1_sig_tokens AS (
  SELECT
    s.record_id,
    s.data_source,
    s.loc_method,
    s.did,
    s.ts,
    s.ip,
    s.sdk_ver,
    s.brand,
    s.model,
    s.oaid,
    s.gps_info_type,
    s.gps_raw,
    s.lon,
    s.lat,
    s.plmn_main,
    s.group_txt,
    s.cell_ts,
    sig_token_txt,
    ord,
    row_number() OVER (PARTITION BY s.record_id, s.group_txt ORDER BY ord) AS rn
  FROM ss1_cells_raw s
  CROSS JOIN LATERAL unnest(string_to_array(s.sig_part, '+')) WITH ORDINALITY AS t(sig_token_txt, ord)
  WHERE s.sig_part IS NOT NULL
    AND btrim(sig_token_txt) <> ''
    AND btrim(sig_token_txt) ~ '^[a-z],-?[0-9]+,-?[0-9]+,-?[0-9]+,-?[0-9]+$'
),
ss1_cells AS (
  SELECT
    c.record_id, c.data_source, c.loc_method, c.did, c.ts, c.ip, c.sdk_ver, c.brand, c.model, c.oaid,
    c.gps_info_type, c.gps_raw, c.lon, c.lat, c.plmn_main,
    'ss1'::text AS parsed_from,
    c.cell_ts,
    CASE
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='n' THEN '5G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='l' THEN '4G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='w' THEN '3G'
      WHEN split_part(btrim(c.cell_token_txt), ',', 1)='g' THEN '2G'
      ELSE NULL
    END AS tech,
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 4)), '') AS "运营商id",
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 3)), '') AS "原始lac",
    NULLIF(btrim(split_part(btrim(c.cell_token_txt), ',', 2)), '') AS cell_id,
    CASE WHEN split_part(btrim(c.cell_token_txt), ',', 3) ~ '^-?[0-9]+$' THEN split_part(btrim(c.cell_token_txt), ',', 3)::bigint END AS lac_dec,
    CASE WHEN split_part(btrim(c.cell_token_txt), ',', 2) ~ '^-?[0-9]+$' THEN split_part(btrim(c.cell_token_txt), ',', 2)::bigint END AS cell_id_dec,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 2) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 2)::int END AS sig_ss,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 3) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 3)::int END AS sig_rsrp,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 4) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 4)::int END AS sig_rsrq,
    CASE WHEN split_part(btrim(st.sig_token_txt), ',', 5) ~ '^-?[0-9]+$' THEN split_part(btrim(st.sig_token_txt), ',', 5)::int END AS sig_sinr,
    NULL::int AS sig_rssi,
    NULL::int AS sig_dbm,
    NULL::int AS sig_asu_level,
    NULL::int AS sig_level
  FROM ss1_cell_tokens c
  LEFT JOIN ss1_sig_tokens st
    ON st.record_id = c.record_id
   AND st.group_txt = c.group_txt
   AND st.rn = c.rn
),
ss1_inherit AS (
  SELECT
    s.record_id, s.data_source, s.loc_method, s.did, s.ts, s.ip, s.sdk_ver, s.brand, s.model, s.oaid,
    s.gps_info_type, s.gps_raw, s.lon, s.lat, s.plmn_main,
    s.parsed_from,
    'SS1_UNMATCHED'::text AS match_status,
    s.cell_ts,
    COALESCE(ci.tech, s.tech) AS tech,
    COALESCE(ci."运营商id", s."运营商id", NULLIF(btrim(s.plmn_main), '')) AS "运营商id",
    COALESCE(ci."原始lac", s."原始lac") AS "原始lac",
    COALESCE(ci.cell_id, s.cell_id) AS cell_id,
    COALESCE(ci.lac_dec, s.lac_dec) AS lac_dec,
    COALESCE(ci.cell_id_dec, s.cell_id_dec) AS cell_id_dec,
    COALESCE(ci.sig_rsrp, s.sig_rsrp) AS sig_rsrp,
    COALESCE(ci.sig_rsrq, s.sig_rsrq) AS sig_rsrq,
    COALESCE(ci.sig_sinr, s.sig_sinr) AS sig_sinr,
    COALESCE(ci.sig_rssi, s.sig_rssi) AS sig_rssi,
    COALESCE(ci.sig_dbm, s.sig_dbm) AS sig_dbm,
    COALESCE(ci.sig_asu_level, s.sig_asu_level) AS sig_asu_level,
    COALESCE(ci.sig_level, s.sig_level) AS sig_level,
    COALESCE(ci.sig_ss, s.sig_ss) AS sig_ss,
    false AS is_connected
  FROM ss1_cells s
  LEFT JOIN cell_infos_out ci
    ON ci.record_id=s.record_id AND ci.cell_id_dec IS NOT NULL AND ci.cell_id_dec=s.cell_id_dec
),
unioned AS (
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    parsed_from, match_status, cell_ts, tech, "运营商id", "原始lac", cell_id, lac_dec, cell_id_dec,
    sig_rsrp, sig_rsrq, sig_sinr, sig_rssi, sig_dbm, sig_asu_level, sig_level, sig_ss,
    is_connected
  FROM cell_infos_out
  UNION ALL
  SELECT
    record_id, data_source, loc_method, did, ts, ip, sdk_ver, brand, model, oaid,
    gps_info_type, gps_raw, lon, lat, plmn_main,
    parsed_from, match_status, cell_ts, tech, "运营商id", "原始lac", cell_id, lac_dec, cell_id_dec,
    sig_rsrp, sig_rsrq, sig_sinr, sig_rssi, sig_dbm, sig_asu_level, sig_level, sig_ss,
    is_connected
  FROM ss1_inherit s
  WHERE NOT EXISTS (
    SELECT 1 FROM cell_infos_out ci
    WHERE ci.record_id=s.record_id AND ci.cell_id_dec IS NOT NULL AND ci.cell_id_dec=s.cell_id_dec
  )
)
SELECT
  row_number() OVER (
    ORDER BY
      CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END NULLS LAST,
      record_id,
      CASE WHEN parsed_from='cell_infos' THEN 0 ELSE 1 END,
      CASE WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN cell_ts::bigint END NULLS LAST,
      cell_id_dec NULLS LAST
  )::bigint AS seq_id,

  record_id AS "记录id",
  cell_ts,
  CASE
    WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN
      CASE
        WHEN parsed_from='ss1'
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)
        WHEN parsed_from='cell_infos'
         AND char_length(cell_ts) >= 13
         AND cell_ts::bigint BETWEEN 946684800000 AND 4102444800000
        THEN to_timestamp(cell_ts::bigint/1000.0)
        WHEN parsed_from='cell_infos'
         AND char_length(cell_ts) BETWEEN 10 AND 11
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)
        ELSE NULL
      END
  END AS cell_ts_std,

  tech,
  "运营商id",
  "原始lac",
  cell_id,

  lac_dec,
  CASE WHEN lac_dec IS NOT NULL THEN upper(to_hex(lac_dec)) END AS lac_hex,
  cell_id_dec,
  CASE WHEN cell_id_dec IS NOT NULL THEN upper(to_hex(cell_id_dec)) END AS cell_id_hex,

  CASE WHEN lower(tech)='4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec/256::bigint
       WHEN lower(tech)='5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec/4096::bigint END AS bs_id,
  CASE WHEN lower(tech)='4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec%256::bigint
       WHEN lower(tech)='5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec%4096::bigint END AS sector_id,

  gps_raw,
  CASE WHEN btrim(split_part(gps_raw, ',', 1)) ~ '^-?[0-9.]+$' THEN btrim(split_part(gps_raw, ',', 1))::double precision END AS lon_raw,
  CASE WHEN btrim(split_part(gps_raw, ',', 2)) ~ '^-?[0-9.]+$' THEN btrim(split_part(gps_raw, ',', 2))::double precision END AS lat_raw,

  CASE WHEN lon IS NOT NULL AND lat IS NOT NULL THEN lon::text||','||lat::text END AS gps_final,
  lon,
  lat,
  gps_info_type,

  data_source AS "数据来源",
  loc_method AS "北京来源",
  did,
  ts,
  CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END AS ts_std,
  ip,
  sdk_ver,
  brand,
  model,
  oaid,

  parsed_from,
  match_status,
  sig_rsrp,
  sig_rsrq,
  sig_sinr,
  sig_rssi,
  sig_dbm,
  sig_asu_level,
  sig_level,
  sig_ss,
  is_connected
FROM unioned
;

ANALYZE public."Y_codex_Layer0_Lac";
