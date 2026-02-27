-- Layer_3 Step33：信号字段“简单补齐”（摸底版）
-- 输入：
--   - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
-- 输出：
--   - public."Y_codex_Layer3_Step33_Signal_Fill_Simple"（TABLE）
--
-- 策略（本轮摸底版）：
-- 1) 先按 cell 聚合得到 cell_signal_profile（中位数）
-- 2) cell 无法补齐则回退到 bs 聚合得到 bs_signal_profile（中位数）
-- 3) 写入 signal_fill_source：cell_agg / bs_agg / none（优先级：cell_agg > bs_agg > none）

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

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step33_Signal_Fill_Simple";

CREATE TABLE public."Y_codex_Layer3_Step33_Signal_Fill_Simple" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw
),
base AS (
  SELECT
    t.*,
    -- 信号字段清洗（用户确认）：无效/占位值统一置 NULL（-110、-1、以及非负数>=0）
    CASE
      WHEN t.sig_rsrp IN (-110, -1) OR t.sig_rsrp >= 0 THEN NULL
      ELSE t.sig_rsrp
    END AS sig_rsrp_clean
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" t
  CROSS JOIN params p
  WHERE
    (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
),
cell_profile AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rsrp_clean) FILTER (WHERE sig_rsrp_clean IS NOT NULL) AS cell_sig_rsrp,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rsrq) FILTER (WHERE sig_rsrq IS NOT NULL) AS cell_sig_rsrq,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_sinr) FILTER (WHERE sig_sinr IS NOT NULL) AS cell_sig_sinr,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rssi) FILTER (WHERE sig_rssi IS NOT NULL) AS cell_sig_rssi,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_dbm) FILTER (WHERE sig_dbm IS NOT NULL) AS cell_sig_dbm,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_asu_level) FILTER (WHERE sig_asu_level IS NOT NULL) AS cell_sig_asu_level,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_level) FILTER (WHERE sig_level IS NOT NULL) AS cell_sig_level,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_ss) FILTER (WHERE sig_ss IS NOT NULL) AS cell_sig_ss
  FROM base
  GROUP BY 1,2,3
),
bs_profile AS (
  SELECT
    tech_norm,
    bs_id,
    wuli_fentong_bs_key,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rsrp_clean) FILTER (WHERE sig_rsrp_clean IS NOT NULL) AS bs_sig_rsrp,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rsrq) FILTER (WHERE sig_rsrq IS NOT NULL) AS bs_sig_rsrq,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_sinr) FILTER (WHERE sig_sinr IS NOT NULL) AS bs_sig_sinr,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_rssi) FILTER (WHERE sig_rssi IS NOT NULL) AS bs_sig_rssi,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_dbm) FILTER (WHERE sig_dbm IS NOT NULL) AS bs_sig_dbm,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_asu_level) FILTER (WHERE sig_asu_level IS NOT NULL) AS bs_sig_asu_level,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_level) FILTER (WHERE sig_level IS NOT NULL) AS bs_sig_level,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY sig_ss) FILTER (WHERE sig_ss IS NOT NULL) AS bs_sig_ss
  FROM base
  GROUP BY 1,2,3
),
filled AS (
  SELECT
    b.*,
    cp.cell_sig_rsrp, cp.cell_sig_rsrq, cp.cell_sig_sinr, cp.cell_sig_rssi, cp.cell_sig_dbm, cp.cell_sig_asu_level, cp.cell_sig_level, cp.cell_sig_ss,
    bp.bs_sig_rsrp, bp.bs_sig_rsrq, bp.bs_sig_sinr, bp.bs_sig_rssi, bp.bs_sig_dbm, bp.bs_sig_asu_level, bp.bs_sig_level, bp.bs_sig_ss,

    -- 统一输出“最终信号字段”
    COALESCE(b.sig_rsrp_clean, cp.cell_sig_rsrp, bp.bs_sig_rsrp)::int AS sig_rsrp_final,
    COALESCE(b.sig_rsrq, cp.cell_sig_rsrq, bp.bs_sig_rsrq)::int AS sig_rsrq_final,
    COALESCE(b.sig_sinr, cp.cell_sig_sinr, bp.bs_sig_sinr)::int AS sig_sinr_final,
    COALESCE(b.sig_rssi, cp.cell_sig_rssi, bp.bs_sig_rssi)::int AS sig_rssi_final,
    COALESCE(b.sig_dbm, cp.cell_sig_dbm, bp.bs_sig_dbm)::int AS sig_dbm_final,
    COALESCE(b.sig_asu_level, cp.cell_sig_asu_level, bp.bs_sig_asu_level)::int AS sig_asu_level_final,
    COALESCE(b.sig_level, cp.cell_sig_level, bp.bs_sig_level)::int AS sig_level_final,
    COALESCE(b.sig_ss, cp.cell_sig_ss, bp.bs_sig_ss)::int AS sig_ss_final,

    -- 缺失摸底（补齐前/后）
    (
      (b.sig_rsrp_clean IS NULL)::int
      + (b.sig_rsrq IS NULL)::int
      + (b.sig_sinr IS NULL)::int
      + (b.sig_rssi IS NULL)::int
      + (b.sig_dbm IS NULL)::int
      + (b.sig_asu_level IS NULL)::int
      + (b.sig_level IS NULL)::int
      + (b.sig_ss IS NULL)::int
    ) AS signal_missing_before_cnt,
    (
      (COALESCE(b.sig_rsrp_clean, cp.cell_sig_rsrp, bp.bs_sig_rsrp) IS NULL)::int
      + (COALESCE(b.sig_rsrq, cp.cell_sig_rsrq, bp.bs_sig_rsrq) IS NULL)::int
      + (COALESCE(b.sig_sinr, cp.cell_sig_sinr, bp.bs_sig_sinr) IS NULL)::int
      + (COALESCE(b.sig_rssi, cp.cell_sig_rssi, bp.bs_sig_rssi) IS NULL)::int
      + (COALESCE(b.sig_dbm, cp.cell_sig_dbm, bp.bs_sig_dbm) IS NULL)::int
      + (COALESCE(b.sig_asu_level, cp.cell_sig_asu_level, bp.bs_sig_asu_level) IS NULL)::int
      + (COALESCE(b.sig_level, cp.cell_sig_level, bp.bs_sig_level) IS NULL)::int
      + (COALESCE(b.sig_ss, cp.cell_sig_ss, bp.bs_sig_ss) IS NULL)::int
    ) AS signal_missing_after_cnt
  FROM base b
  LEFT JOIN cell_profile cp
    ON cp.operator_id_raw=b.operator_id_raw
   AND cp.tech_norm=b.tech_norm
   AND cp.cell_id_dec=b.cell_id_dec
  LEFT JOIN bs_profile bp
    ON bp.tech_norm=b.tech_norm
   AND bp.bs_id=b.bs_id
   AND bp.wuli_fentong_bs_key=b.wuli_fentong_bs_key
),
with_source AS (
  SELECT
    f.*,
    CASE
      WHEN f.signal_missing_before_cnt = 0 THEN 'none'
      WHEN (
        (f.sig_rsrp_clean IS NULL AND f.cell_sig_rsrp IS NOT NULL)
        OR (f.sig_rsrq IS NULL AND f.cell_sig_rsrq IS NOT NULL)
        OR (f.sig_sinr IS NULL AND f.cell_sig_sinr IS NOT NULL)
        OR (f.sig_rssi IS NULL AND f.cell_sig_rssi IS NOT NULL)
        OR (f.sig_dbm IS NULL AND f.cell_sig_dbm IS NOT NULL)
        OR (f.sig_asu_level IS NULL AND f.cell_sig_asu_level IS NOT NULL)
        OR (f.sig_level IS NULL AND f.cell_sig_level IS NOT NULL)
        OR (f.sig_ss IS NULL AND f.cell_sig_ss IS NOT NULL)
      ) THEN 'cell_agg'
      WHEN (
        (f.sig_rsrp_clean IS NULL AND f.bs_sig_rsrp IS NOT NULL)
        OR (f.sig_rsrq IS NULL AND f.bs_sig_rsrq IS NOT NULL)
        OR (f.sig_sinr IS NULL AND f.bs_sig_sinr IS NOT NULL)
        OR (f.sig_rssi IS NULL AND f.bs_sig_rssi IS NOT NULL)
        OR (f.sig_dbm IS NULL AND f.bs_sig_dbm IS NOT NULL)
        OR (f.sig_asu_level IS NULL AND f.bs_sig_asu_level IS NOT NULL)
        OR (f.sig_level IS NULL AND f.bs_sig_level IS NOT NULL)
        OR (f.sig_ss IS NULL AND f.bs_sig_ss IS NOT NULL)
      ) THEN 'bs_agg'
      ELSE 'none'
    END AS signal_fill_source
  FROM filled f
)
SELECT
  -- 追溯
  src_seq_id,
  src_record_id,

  operator_id_raw,
  operator_group_hint,
  tech_norm,
  bs_id,
  sector_id,
  cell_id_dec,
  lac_dec_final,
  wuli_fentong_bs_key,

  report_date,
  ts_std,

  -- GPS（透传 Step31 结果）
  gps_status,
  gps_status_final,
  gps_source,
  is_from_risk_bs,
  lon_final,
  lat_final,

  -- 信号补齐（输出 final）
  signal_fill_source,
  signal_missing_before_cnt,
  signal_missing_after_cnt,

  sig_rsrp_final,
  sig_rsrq_final,
  sig_sinr_final,
  sig_rssi_final,
  sig_dbm_final,
  sig_asu_level_final,
  sig_level_final,
  sig_ss_final
FROM with_source;

ANALYZE public."Y_codex_Layer3_Step33_Signal_Fill_Simple";
