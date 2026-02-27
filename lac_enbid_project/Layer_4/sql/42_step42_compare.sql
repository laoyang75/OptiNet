-- Layer_4 Step42：最终库 vs 原始库对比汇总（条数/GPS/信号）
--
-- 输入：
-- - public."Y_codex_Layer0_Lac"
-- - public."Y_codex_Layer4_Final_Cell_Library"（或 shard 表合并后）
--
-- 输出：
-- - public."Y_codex_Layer4_Step42_Compare_Summary"
--
-- 说明：
-- - 对比口径默认与 Step40 保持一致：仅 4G/5G + 指定运营商 + cell_id_dec>0 + （bs_id 或可由 cell_id 推导）>0
-- - 当 `codex.shard_count>1` 时，会按 shard 表 UNION ALL 汇总（无需先手工合并）

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';

DO $$
DECLARE
  shard_count int := COALESCE(NULLIF(current_setting('codex.shard_count', true), '')::int, 1);
  is_smoke boolean := COALESCE(NULLIF(current_setting('codex.is_smoke', true), '')::boolean, false);
  smoke_date date := COALESCE(NULLIF(current_setting('codex.smoke_date', true), '')::date, date '2025-12-01');
  smoke_operator text := COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000');
  i int;
  final_union_sql text := '';
BEGIN
  IF shard_count <= 1 THEN
    final_union_sql := 'SELECT * FROM public."Y_codex_Layer4_Final_Cell_Library"';
  ELSE
    FOR i IN 0..(shard_count - 1) LOOP
      final_union_sql := final_union_sql
        || CASE WHEN i > 0 THEN E'\nUNION ALL\n' ELSE '' END
        || format('SELECT * FROM public.%I', format('Y_codex_Layer4_Final_Cell_Library__shard_%s', lpad(i::text, 2, '0')));
    END LOOP;
  END IF;

  EXECUTE 'DROP TABLE IF EXISTS public."Y_codex_Layer4_Step42_Compare_Summary"';

  EXECUTE format($sql$
    CREATE TABLE public."Y_codex_Layer4_Step42_Compare_Summary" AS
    WITH
    params AS (
      SELECT
        %L::boolean AS is_smoke,
        %L::date AS smoke_date,
        %L::text AS smoke_operator_id_raw
    ),
    raw AS (
      SELECT
        count(*)::bigint AS row_cnt,
        count(*) FILTER (WHERE lon IS NOT NULL AND lat IS NOT NULL)::bigint AS gps_present_cnt,
        count(*) FILTER (WHERE lon IS NULL OR lat IS NULL)::bigint AS gps_missing_cnt,

        count(*) FILTER (WHERE sig_rsrp IS NULL)::bigint AS sig_rsrp_null_cnt,
        count(*) FILTER (WHERE sig_rsrq IS NULL)::bigint AS sig_rsrq_null_cnt,
        count(*) FILTER (WHERE sig_sinr IS NULL)::bigint AS sig_sinr_null_cnt,
        count(*) FILTER (WHERE sig_rssi IS NULL)::bigint AS sig_rssi_null_cnt,
        count(*) FILTER (WHERE sig_dbm IS NULL)::bigint AS sig_dbm_null_cnt,
        count(*) FILTER (WHERE sig_asu_level IS NULL)::bigint AS sig_asu_level_null_cnt,
        count(*) FILTER (WHERE sig_level IS NULL)::bigint AS sig_level_null_cnt,
        count(*) FILTER (WHERE sig_ss IS NULL)::bigint AS sig_ss_null_cnt
      FROM public."Y_codex_Layer0_Lac" t
      CROSS JOIN params p
      WHERE
        t.tech IN ('4G','5G')
        AND t."运营商id" IN ('46000','46001','46011','46015','46020')
        AND t.cell_id_dec IS NOT NULL AND t.cell_id_dec > 0
        AND COALESCE(
              t.bs_id,
              CASE
                WHEN t.tech='4G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 256.0)::bigint
                WHEN t.tech='5G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 4096.0)::bigint
              END
            ) IS NOT NULL
        AND COALESCE(
              t.bs_id,
              CASE
                WHEN t.tech='4G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 256.0)::bigint
                WHEN t.tech='5G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 4096.0)::bigint
              END
            ) > 0
        AND (NOT p.is_smoke OR p.smoke_date IS NULL OR t.ts_std::date = p.smoke_date)
        AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t."运营商id"::text = p.smoke_operator_id_raw)
    ),
    final AS (
      SELECT
        count(*)::bigint AS row_cnt,
        count(*) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL)::bigint AS gps_present_cnt,
        count(*) FILTER (WHERE lon_final IS NULL OR lat_final IS NULL)::bigint AS gps_missing_cnt,

        count(*) FILTER (WHERE sig_rsrp_final IS NULL)::bigint AS sig_rsrp_null_cnt,
        count(*) FILTER (WHERE sig_rsrq_final IS NULL)::bigint AS sig_rsrq_null_cnt,
        count(*) FILTER (WHERE sig_sinr_final IS NULL)::bigint AS sig_sinr_null_cnt,
        count(*) FILTER (WHERE sig_rssi_final IS NULL)::bigint AS sig_rssi_null_cnt,
        count(*) FILTER (WHERE sig_dbm_final IS NULL)::bigint AS sig_dbm_null_cnt,
        count(*) FILTER (WHERE sig_asu_level_final IS NULL)::bigint AS sig_asu_level_null_cnt,
        count(*) FILTER (WHERE sig_level_final IS NULL)::bigint AS sig_level_null_cnt,
        count(*) FILTER (WHERE sig_ss_final IS NULL)::bigint AS sig_ss_null_cnt
      FROM (%s) f
    )
    SELECT 'raw'::text AS dataset, * FROM raw
    UNION ALL
    SELECT 'final'::text AS dataset, * FROM final;
  $sql$, is_smoke, smoke_date, smoke_operator, final_union_sql);
END $$;
