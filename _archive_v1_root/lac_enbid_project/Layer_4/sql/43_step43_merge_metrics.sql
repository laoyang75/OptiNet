-- Layer_4 Step43：汇总 Step40/Step41 shard 指标（UNION ALL + rollup）
--
-- 输入：
-- - public."Y_codex_Layer4_Step40_Gps_Metrics" 或 public."Y_codex_Layer4_Step40_Gps_Metrics__shard_XX"
-- - public."Y_codex_Layer4_Step41_Signal_Metrics" 或 public."Y_codex_Layer4_Step41_Signal_Metrics__shard_XX"
--
-- 输出：
-- - public."Y_codex_Layer4_Step40_Gps_Metrics_All"
-- - public."Y_codex_Layer4_Step41_Signal_Metrics_All"
--
-- 说明：
-- - shard_count 通过 session setting `codex.shard_count` 读取；默认 1
-- - 每个 *_All 表包含：每 shard 一行 + rollup 行（shard_id=-1）

SET statement_timeout = 0;
SET jit = off;

DO $$
DECLARE
  shard_count int := COALESCE(NULLIF(current_setting('codex.shard_count', true), '')::int, 1);
  i int;
  s40_sql text := '';
  s41_sql text := '';
BEGIN
  IF shard_count <= 1 THEN
    s40_sql := 'SELECT * FROM public."Y_codex_Layer4_Step40_Gps_Metrics"';
    s41_sql := 'SELECT * FROM public."Y_codex_Layer4_Step41_Signal_Metrics"';
  ELSE
    FOR i IN 0..(shard_count - 1) LOOP
      s40_sql := s40_sql
        || CASE WHEN i > 0 THEN E'\nUNION ALL\n' ELSE '' END
        || format('SELECT * FROM public.%I', format('Y_codex_Layer4_Step40_Gps_Metrics__shard_%s', lpad(i::text, 2, '0')));

      s41_sql := s41_sql
        || CASE WHEN i > 0 THEN E'\nUNION ALL\n' ELSE '' END
        || format('SELECT * FROM public.%I', format('Y_codex_Layer4_Step41_Signal_Metrics__shard_%s', lpad(i::text, 2, '0')));
    END LOOP;
  END IF;

  EXECUTE 'DROP TABLE IF EXISTS public."Y_codex_Layer4_Step40_Gps_Metrics_All"';
  EXECUTE format($sql$
    CREATE TABLE public."Y_codex_Layer4_Step40_Gps_Metrics_All" AS
    WITH all_rows AS (
      %s
    ),
    rollup AS (
      SELECT
        max(shard_count)::int AS shard_count,
        -1::int AS shard_id,
        sum(row_cnt)::bigint AS row_cnt,
        sum(gps_missing_cnt)::bigint AS gps_missing_cnt,
        sum(gps_drift_cnt)::bigint AS gps_drift_cnt,
        sum(gps_fill_from_bs_cnt)::bigint AS gps_fill_from_bs_cnt,
        sum(gps_fill_from_bs_severe_collision_cnt)::bigint AS gps_fill_from_bs_severe_collision_cnt,
        sum(gps_fill_from_risk_bs_cnt)::bigint AS gps_fill_from_risk_bs_cnt,
        sum(gps_not_filled_cnt)::bigint AS gps_not_filled_cnt,
        sum(severe_collision_row_cnt)::bigint AS severe_collision_row_cnt,
        sum(bs_id_lt_256_row_cnt)::bigint AS bs_id_lt_256_row_cnt,
        sum(bs_id_eq_1_row_cnt)::bigint AS bs_id_eq_1_row_cnt
      FROM all_rows
    )
    SELECT * FROM all_rows
    UNION ALL
    SELECT * FROM rollup;
  $sql$, s40_sql);

  EXECUTE 'DROP TABLE IF EXISTS public."Y_codex_Layer4_Step41_Signal_Metrics_All"';
  EXECUTE format($sql$
    CREATE TABLE public."Y_codex_Layer4_Step41_Signal_Metrics_All" AS
    WITH all_rows AS (
      %s
    ),
    rollup AS (
      SELECT
        max(shard_count)::int AS shard_count,
        -1::int AS shard_id,
        sum(row_cnt)::bigint AS row_cnt,
        sum(need_fill_row_cnt)::bigint AS need_fill_row_cnt,
        sum(filled_by_cell_nearest_row_cnt)::bigint AS filled_by_cell_nearest_row_cnt,
        sum(filled_by_bs_top_cell_row_cnt)::bigint AS filled_by_bs_top_cell_row_cnt,
        sum(missing_field_before_sum)::bigint AS missing_field_before_sum,
        sum(missing_field_after_sum)::bigint AS missing_field_after_sum,
        sum(filled_field_sum)::bigint AS filled_field_sum,
        sum(sig_rsrp_null_before_cnt)::bigint AS sig_rsrp_null_before_cnt,
        sum(sig_rsrp_null_after_cnt)::bigint AS sig_rsrp_null_after_cnt,
        sum(sig_rsrq_null_before_cnt)::bigint AS sig_rsrq_null_before_cnt,
        sum(sig_rsrq_null_after_cnt)::bigint AS sig_rsrq_null_after_cnt,
        sum(sig_sinr_null_before_cnt)::bigint AS sig_sinr_null_before_cnt,
        sum(sig_sinr_null_after_cnt)::bigint AS sig_sinr_null_after_cnt,
        sum(sig_rssi_null_before_cnt)::bigint AS sig_rssi_null_before_cnt,
        sum(sig_rssi_null_after_cnt)::bigint AS sig_rssi_null_after_cnt,
        sum(sig_dbm_null_before_cnt)::bigint AS sig_dbm_null_before_cnt,
        sum(sig_dbm_null_after_cnt)::bigint AS sig_dbm_null_after_cnt,
        sum(sig_asu_level_null_before_cnt)::bigint AS sig_asu_level_null_before_cnt,
        sum(sig_asu_level_null_after_cnt)::bigint AS sig_asu_level_null_after_cnt,
        sum(sig_level_null_before_cnt)::bigint AS sig_level_null_before_cnt,
        sum(sig_level_null_after_cnt)::bigint AS sig_level_null_after_cnt,
        sum(sig_ss_null_before_cnt)::bigint AS sig_ss_null_before_cnt,
        sum(sig_ss_null_after_cnt)::bigint AS sig_ss_null_after_cnt
      FROM all_rows
    )
    SELECT * FROM all_rows
    UNION ALL
    SELECT * FROM rollup;
  $sql$, s41_sql);
END $$;
