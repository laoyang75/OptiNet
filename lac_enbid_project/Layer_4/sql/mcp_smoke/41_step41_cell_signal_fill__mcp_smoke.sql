-- Layer_4 Step41 MCP Smoke：信号字段二阶段补齐（固定表名，无 DO 块）
--
-- 输入：
-- - public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE"
--
-- 输出：
-- - public."Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE"
-- - public."Y_codex_Layer4_Step41_Signal_Metrics__MCP_SMOKE"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';
SET TIME ZONE 'UTC';

DROP TABLE IF EXISTS public."Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE";

CREATE TABLE public."Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE" AS
WITH
dynamic_cell AS (
  SELECT
    operator_id_raw::text AS operator_id_raw,
    CASE
      WHEN tech_norm ILIKE '5G%%' THEN '5G'
      WHEN tech_norm='4G' THEN '4G'
      ELSE tech_norm
    END AS tech_norm_mapped,
    cell_id_dec,
    max(is_dynamic_cell)::int AS is_dynamic_cell,
    min(dynamic_reason) FILTER (WHERE is_dynamic_cell=1) AS dynamic_reason,
    max(half_major_dist_km) FILTER (WHERE is_dynamic_cell=1) AS half_major_dist_km
  FROM public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"
  WHERE operator_id_raw IN ('46000','46001','46011','46015','46020')
  GROUP BY 1,2,3
),
base AS (
  SELECT
    t.*,
    COALESCE(t.ts_std, t.cell_ts_std::timestamp) AS ts_fill,
    COALESCE(t.wuli_fentong_bs_key, t.bs_shard_key) AS bs_group_key,
    COALESCE(dc.is_dynamic_cell, 0)::int AS is_dynamic_cell,
    dc.dynamic_reason,
    dc.half_major_dist_km
  FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE" t
  LEFT JOIN dynamic_cell dc
    ON dc.operator_id_raw = t.operator_id_raw
   AND dc.tech_norm_mapped = t.tech_norm
   AND dc.cell_id_dec = t.cell_id_dec
),
base_sig AS (
  SELECT
    b.*,
    (
      b.sig_rsrp IS NOT NULL
      OR b.sig_rsrq IS NOT NULL
      OR b.sig_sinr IS NOT NULL
      OR b.sig_rssi IS NOT NULL
      OR b.sig_dbm IS NOT NULL
      OR b.sig_asu_level IS NOT NULL
      OR b.sig_level IS NOT NULL
      OR b.sig_ss IS NOT NULL
    ) AS has_any_signal,
    (
      (b.sig_rsrp IS NULL)::int
      + (b.sig_rsrq IS NULL)::int
      + (b.sig_sinr IS NULL)::int
      + (b.sig_rssi IS NULL)::int
      + (b.sig_dbm IS NULL)::int
      + (b.sig_asu_level IS NULL)::int
      + (b.sig_level IS NULL)::int
      + (b.sig_ss IS NULL)::int
    ) AS signal_missing_before_cnt
  FROM base b
),
cell_win AS (
  SELECT
    b.seq_id,
    max(b.seq_id) FILTER (WHERE b.has_any_signal) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.lac_dec_final, b.cell_id_dec
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS cell_prev_donor_seq_id,
    max(b.ts_fill) FILTER (WHERE b.has_any_signal) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.lac_dec_final, b.cell_id_dec
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS cell_prev_donor_ts_fill,
    min(b.seq_id) FILTER (WHERE b.has_any_signal) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.lac_dec_final, b.cell_id_dec
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
    ) AS cell_next_donor_seq_id,
    min(b.ts_fill) FILTER (WHERE b.has_any_signal) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.lac_dec_final, b.cell_id_dec
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
    ) AS cell_next_donor_ts_fill
  FROM base_sig b
),
with_cell AS (
  SELECT
    b.*,
    CASE
      WHEN b.signal_missing_before_cnt = 0 THEN NULL::bigint
      WHEN b.ts_fill IS NULL THEN COALESCE(cw.cell_prev_donor_seq_id, cw.cell_next_donor_seq_id)
      WHEN cw.cell_prev_donor_seq_id IS NULL THEN cw.cell_next_donor_seq_id
      WHEN cw.cell_next_donor_seq_id IS NULL THEN cw.cell_prev_donor_seq_id
      WHEN abs(extract(epoch from (b.ts_fill - cw.cell_prev_donor_ts_fill)))
         <= abs(extract(epoch from (cw.cell_next_donor_ts_fill - b.ts_fill)))
      THEN cw.cell_prev_donor_seq_id
      ELSE cw.cell_next_donor_seq_id
    END AS cell_donor_seq_id
  FROM base_sig b
  JOIN cell_win cw USING (seq_id)
),
bs_cell_stats AS (
  SELECT
    operator_id_raw,
    tech_norm,
    bs_group_key,
    cell_id_dec,
    count(*)::bigint AS cell_row_cnt,
    count(*) FILTER (WHERE has_any_signal)::bigint AS cell_sig_row_cnt
  FROM with_cell
  GROUP BY 1,2,3,4
),
bs_top_cell AS (
  SELECT DISTINCT ON (operator_id_raw, tech_norm, bs_group_key)
    operator_id_raw,
    tech_norm,
    bs_group_key,
    cell_id_dec AS bs_top_cell_id_dec
  FROM bs_cell_stats
  WHERE cell_sig_row_cnt > 0
  ORDER BY
    operator_id_raw, tech_norm, bs_group_key,
    cell_row_cnt DESC,
    cell_sig_row_cnt DESC,
    cell_id_dec ASC
),
with_bs_top AS (
  SELECT
    c.*,
    btc.bs_top_cell_id_dec,
    (c.cell_id_dec = btc.bs_top_cell_id_dec) AS is_bs_top_cell
  FROM with_cell c
  LEFT JOIN bs_top_cell btc
    ON btc.operator_id_raw=c.operator_id_raw
   AND btc.tech_norm=c.tech_norm
   AND btc.bs_group_key=c.bs_group_key
),
bs_win AS (
  SELECT
    b.seq_id,
    max(b.seq_id) FILTER (WHERE b.has_any_signal AND b.is_bs_top_cell) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.bs_group_key
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS bs_prev_donor_seq_id,
    max(b.ts_fill) FILTER (WHERE b.has_any_signal AND b.is_bs_top_cell) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.bs_group_key
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS bs_prev_donor_ts_fill,
    min(b.seq_id) FILTER (WHERE b.has_any_signal AND b.is_bs_top_cell) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.bs_group_key
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
    ) AS bs_next_donor_seq_id,
    min(b.ts_fill) FILTER (WHERE b.has_any_signal AND b.is_bs_top_cell) OVER (
      PARTITION BY b.operator_id_raw, b.tech_norm, b.bs_group_key
      ORDER BY b.ts_fill, b.seq_id
      ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
    ) AS bs_next_donor_ts_fill
  FROM with_bs_top b
),
picked AS (
  SELECT
    b.*,
    CASE
      WHEN b.signal_missing_before_cnt = 0 THEN NULL::bigint
      WHEN b.cell_donor_seq_id IS NOT NULL THEN b.cell_donor_seq_id
      WHEN b.ts_fill IS NULL THEN COALESCE(bw.bs_prev_donor_seq_id, bw.bs_next_donor_seq_id)
      WHEN bw.bs_prev_donor_seq_id IS NULL THEN bw.bs_next_donor_seq_id
      WHEN bw.bs_next_donor_seq_id IS NULL THEN bw.bs_prev_donor_seq_id
      WHEN abs(extract(epoch from (b.ts_fill - bw.bs_prev_donor_ts_fill)))
         <= abs(extract(epoch from (bw.bs_next_donor_ts_fill - b.ts_fill)))
      THEN bw.bs_prev_donor_seq_id
      ELSE bw.bs_next_donor_seq_id
    END AS signal_donor_seq_id,
    CASE
      WHEN b.signal_missing_before_cnt = 0 THEN 'none'
      WHEN b.cell_donor_seq_id IS NOT NULL THEN 'cell_nearest'
      WHEN (bw.bs_prev_donor_seq_id IS NOT NULL OR bw.bs_next_donor_seq_id IS NOT NULL) THEN 'bs_top_cell_nearest'
      ELSE 'none'
    END AS signal_fill_source
  FROM with_bs_top b
  JOIN bs_win bw USING (seq_id)
),
out AS (
  SELECT
    p.*,
    d.ts_fill AS signal_donor_ts_fill,
    d.cell_id_dec AS signal_donor_cell_id_dec,
    COALESCE(p.sig_rsrp, d.sig_rsrp)::int AS sig_rsrp_final,
    COALESCE(p.sig_rsrq, d.sig_rsrq)::int AS sig_rsrq_final,
    COALESCE(p.sig_sinr, d.sig_sinr)::int AS sig_sinr_final,
    COALESCE(p.sig_rssi, d.sig_rssi)::int AS sig_rssi_final,
    COALESCE(p.sig_dbm, d.sig_dbm)::int AS sig_dbm_final,
    COALESCE(p.sig_asu_level, d.sig_asu_level)::int AS sig_asu_level_final,
    COALESCE(p.sig_level, d.sig_level)::int AS sig_level_final,
    COALESCE(p.sig_ss, d.sig_ss)::int AS sig_ss_final,
    (
      (COALESCE(p.sig_rsrp, d.sig_rsrp) IS NULL)::int
      + (COALESCE(p.sig_rsrq, d.sig_rsrq) IS NULL)::int
      + (COALESCE(p.sig_sinr, d.sig_sinr) IS NULL)::int
      + (COALESCE(p.sig_rssi, d.sig_rssi) IS NULL)::int
      + (COALESCE(p.sig_dbm, d.sig_dbm) IS NULL)::int
      + (COALESCE(p.sig_asu_level, d.sig_asu_level) IS NULL)::int
      + (COALESCE(p.sig_level, d.sig_level) IS NULL)::int
      + (COALESCE(p.sig_ss, d.sig_ss) IS NULL)::int
    ) AS signal_missing_after_cnt,
    (p.signal_missing_before_cnt - (
      (COALESCE(p.sig_rsrp, d.sig_rsrp) IS NULL)::int
      + (COALESCE(p.sig_rsrq, d.sig_rsrq) IS NULL)::int
      + (COALESCE(p.sig_sinr, d.sig_sinr) IS NULL)::int
      + (COALESCE(p.sig_rssi, d.sig_rssi) IS NULL)::int
      + (COALESCE(p.sig_dbm, d.sig_dbm) IS NULL)::int
      + (COALESCE(p.sig_asu_level, d.sig_asu_level) IS NULL)::int
      + (COALESCE(p.sig_level, d.sig_level) IS NULL)::int
      + (COALESCE(p.sig_ss, d.sig_ss) IS NULL)::int
    )) AS signal_filled_field_cnt
  FROM picked p
  LEFT JOIN base_sig d
    ON d.seq_id = p.signal_donor_seq_id
)
SELECT * FROM out;

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step41_Signal_Metrics__MCP_SMOKE";
CREATE TABLE public."Y_codex_Layer4_Step41_Signal_Metrics__MCP_SMOKE" AS
SELECT
  count(*)::bigint AS row_cnt,
  count(*) FILTER (WHERE signal_missing_before_cnt > 0)::bigint AS need_fill_row_cnt,
  count(*) FILTER (WHERE signal_fill_source='cell_nearest')::bigint AS filled_by_cell_nearest_row_cnt,
  count(*) FILTER (WHERE signal_fill_source='bs_top_cell_nearest')::bigint AS filled_by_bs_top_cell_row_cnt,
  sum(signal_missing_before_cnt)::bigint AS missing_field_before_sum,
  sum(signal_missing_after_cnt)::bigint AS missing_field_after_sum,
  sum(signal_filled_field_cnt)::bigint AS filled_field_sum
FROM public."Y_codex_Layer4_Final_Cell_Library__MCP_SMOKE";
