-- Layer_4 Step42 MCP Smoke：Final vs Raw 对比汇总（固定表名，无 DO 块）
--
-- 输出：
-- - public."Y_codex_Layer4_Step42_Compare_Summary__MCP_SMOKE"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step42_Compare_Summary__MCP_SMOKE";

CREATE TABLE public."Y_codex_Layer4_Step42_Compare_Summary__MCP_SMOKE" AS
WITH
params AS (
  SELECT
    true::boolean AS is_smoke,
    date '2025-12-01' AS smoke_date,
    '46000'::text AS smoke_operator_id_raw,
    200000::bigint AS smoke_limit_rows
),
raw_slice AS (
  -- 与 Step40 MCP Smoke 对齐：先取同一顺序的 LIMIT 切片，再做 bs_id_final>0 过滤
  WITH raw0 AS (
    SELECT
      t.seq_id,
      t.tech,
      t.cell_id_dec,
      t.bs_id,
      t.ts_std,
      t."运营商id"::text AS operator_id_raw,
      t.lon,
      t.lat,
      t.sig_rsrp,
      t.sig_rsrq,
      t.sig_sinr,
      t.sig_rssi,
      t.sig_dbm,
      t.sig_asu_level,
      t.sig_level,
      t.sig_ss
    FROM public."Y_codex_Layer0_Lac" t
    CROSS JOIN params p
    WHERE
      t.tech IN ('4G','5G')
      AND t."运营商id" IN ('46000','46001','46011','46015','46020')
      AND t.cell_id_dec IS NOT NULL AND t.cell_id_dec > 0
      AND (NOT p.is_smoke OR p.smoke_date IS NULL OR t.ts_std::date = p.smoke_date)
      AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t."运营商id"::text = p.smoke_operator_id_raw)
    ORDER BY t.ts_std, t.seq_id
    LIMIT (SELECT smoke_limit_rows FROM params)
  )
  SELECT
    r.seq_id,
    r.lon,
    r.lat,
    r.sig_rsrp,
    r.sig_rsrq,
    r.sig_sinr,
    r.sig_rssi,
    r.sig_dbm,
    r.sig_asu_level,
    r.sig_level,
    r.sig_ss
  FROM raw0 r
  WHERE
    COALESCE(
      r.bs_id,
      CASE
        WHEN r.tech='4G' AND r.cell_id_dec IS NOT NULL THEN floor(r.cell_id_dec / 256.0)::bigint
        WHEN r.tech='5G' AND r.cell_id_dec IS NOT NULL THEN floor(r.cell_id_dec / 4096.0)::bigint
      END
    ) IS NOT NULL
    AND COALESCE(
      r.bs_id,
      CASE
        WHEN r.tech='4G' AND r.cell_id_dec IS NOT NULL THEN floor(r.cell_id_dec / 256.0)::bigint
        WHEN r.tech='5G' AND r.cell_id_dec IS NOT NULL THEN floor(r.cell_id_dec / 4096.0)::bigint
      END
    ) > 0
),
raw AS (
  SELECT
    count(*)::bigint AS row_cnt,
    count(*) FILTER (WHERE lon IS NOT NULL AND lat IS NOT NULL)::bigint AS gps_present_cnt,
    count(*) FILTER (WHERE lon IS NULL OR lat IS NULL)::bigint AS gps_missing_cnt,
    count(*) FILTER (WHERE sig_rsrp IS NULL)::bigint AS sig_rsrp_null_cnt,
    count(*) FILTER (WHERE sig_rsrq IS NULL)::bigint AS sig_rsrq_null_cnt,
    count(*) FILTER (WHERE sig_sinr IS NULL)::bigint AS sig_sinr_null_cnt,
    count(*) FILTER (WHERE sig_ss IS NULL)::bigint AS sig_ss_null_cnt
  FROM raw_slice
),
final AS (
  SELECT
    count(*)::bigint AS row_cnt,
    count(*) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL)::bigint AS gps_present_cnt,
    count(*) FILTER (WHERE lon_final IS NULL OR lat_final IS NULL)::bigint AS gps_missing_cnt,
    count(*) FILTER (WHERE sig_rsrp_final IS NULL)::bigint AS sig_rsrp_null_cnt,
    count(*) FILTER (WHERE sig_rsrq_final IS NULL)::bigint AS sig_rsrq_null_cnt,
    count(*) FILTER (WHERE sig_sinr_final IS NULL)::bigint AS sig_sinr_null_cnt,
    count(*) FILTER (WHERE sig_ss_final IS NULL)::bigint AS sig_ss_null_cnt
  FROM public."Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE"
)
SELECT 'raw'::text AS dataset, * FROM raw
UNION ALL
SELECT 'final'::text AS dataset, * FROM final;
