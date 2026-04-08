-- Layer_4 Step41：信号字段二阶段补齐（同 cell 最近 → 同 BS top cell 最近）
--
-- 输入：
-- - public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"（或 shard 表）
--
-- 输出：
-- - public."Y_codex_Layer4_Final_Cell_Library"（或 shard 表）
-- - public."Y_codex_Layer4_Step41_Signal_Metrics"（或 shard 表）
--
-- 口径：
-- - 仅补齐“缺失字段”（逐字段 COALESCE，不覆盖已有值）
-- - donor 只要求“任一信号字段非 NULL”
-- - 优先同 cell（operator+tech+lac_dec_final+cell_id_dec）找时间最近 donor
-- - 若同 cell 无任何 donor：退化到同 BS 桶下“数据量最多且存在信号的 cell_id”作为 donor_cell，再找时间最近 donor
--
-- 性能说明：
-- - 支持按 BS 分片（与 Step40 一致：bs_shard_key=tech_norm|bs_id_final；codex.shard_count/shard_id）

/* ============================================================================
 * 会话级性能参数（建议按机器调整）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET maintenance_work_mem = '2GB';
SET max_parallel_workers_per_gather = 8;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET TIME ZONE 'UTC';

DO $$
DECLARE
  shard_count int := COALESCE(NULLIF(current_setting('codex.shard_count', true), '')::int, 1);
  shard_id int := COALESCE(NULLIF(current_setting('codex.shard_id', true), '')::int, 0);
  is_smoke boolean := COALESCE(NULLIF(current_setting('codex.is_smoke', true), '')::boolean, false);
  smoke_date date := COALESCE(NULLIF(current_setting('codex.smoke_date', true), '')::date, date '2025-12-01');
  smoke_operator text := COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000');

  in_table text := CASE
    WHEN shard_count > 1 THEN format('Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__shard_%s', lpad(shard_id::text, 2, '0'))
    ELSE 'Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill'
  END;
  out_table text := CASE
    WHEN shard_count > 1 THEN format('Y_codex_Layer4_Final_Cell_Library__shard_%s', lpad(shard_id::text, 2, '0'))
    ELSE 'Y_codex_Layer4_Final_Cell_Library'
  END;
  metric_table text := CASE
    WHEN shard_count > 1 THEN format('Y_codex_Layer4_Step41_Signal_Metrics__shard_%s', lpad(shard_id::text, 2, '0'))
    ELSE 'Y_codex_Layer4_Step41_Signal_Metrics'
  END;
  idx_cell_ts_name text := CASE
    WHEN shard_count > 1 THEN format('idx_l4_final_cell_ts_s%s', lpad(shard_id::text, 2, '0'))
    ELSE 'idx_l4_final_cell_ts'
  END;
  idx_bs_ts_name text := CASE
    WHEN shard_count > 1 THEN format('idx_l4_final_bs_ts_s%s', lpad(shard_id::text, 2, '0'))
    ELSE 'idx_l4_final_bs_ts'
  END;
BEGIN
  EXECUTE format('DROP TABLE IF EXISTS public.%I', out_table);

  EXECUTE format($sql$
    CREATE TABLE public.%I AS
    WITH
    params AS (
      SELECT
        %L::boolean AS is_smoke,
        %L::date AS smoke_date,
        %L::text AS smoke_operator_id_raw
    ),
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
      FROM public.%I t
      CROSS JOIN params p
      LEFT JOIN dynamic_cell dc
        ON dc.operator_id_raw = t.operator_id_raw
       AND dc.tech_norm_mapped = t.tech_norm
       AND dc.cell_id_dec = t.cell_id_dec
      WHERE
        (NOT p.is_smoke OR p.smoke_date IS NULL OR t.ts_std::date = p.smoke_date)
        AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
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
    SELECT * FROM out
  $sql$,
    out_table,
    is_smoke, smoke_date, smoke_operator,
    in_table
  );

  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(operator_id_raw, tech_norm, cell_id_dec, ts_fill)', idx_cell_ts_name, out_table);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(operator_id_raw, tech_norm, bs_group_key, ts_fill)', idx_bs_ts_name, out_table);
  EXECUTE format('ANALYZE public.%I', out_table);

  EXECUTE format('DROP TABLE IF EXISTS public.%I', metric_table);
  EXECUTE format($m$
    CREATE TABLE public.%I AS
    SELECT
      max(%s)::int AS shard_count,
      max(%s)::int AS shard_id,
      count(*)::bigint AS row_cnt,

      count(*) FILTER (WHERE signal_missing_before_cnt > 0)::bigint AS need_fill_row_cnt,
      count(*) FILTER (WHERE signal_fill_source='cell_nearest')::bigint AS filled_by_cell_nearest_row_cnt,
      count(*) FILTER (WHERE signal_fill_source='bs_top_cell_nearest')::bigint AS filled_by_bs_top_cell_row_cnt,

      sum(signal_missing_before_cnt)::bigint AS missing_field_before_sum,
      sum(signal_missing_after_cnt)::bigint AS missing_field_after_sum,
      sum(signal_filled_field_cnt)::bigint AS filled_field_sum,

      -- 逐字段缺失（before/after）
      count(*) FILTER (WHERE sig_rsrp IS NULL)::bigint AS sig_rsrp_null_before_cnt,
      count(*) FILTER (WHERE sig_rsrp_final IS NULL)::bigint AS sig_rsrp_null_after_cnt,
      count(*) FILTER (WHERE sig_rsrq IS NULL)::bigint AS sig_rsrq_null_before_cnt,
      count(*) FILTER (WHERE sig_rsrq_final IS NULL)::bigint AS sig_rsrq_null_after_cnt,
      count(*) FILTER (WHERE sig_sinr IS NULL)::bigint AS sig_sinr_null_before_cnt,
      count(*) FILTER (WHERE sig_sinr_final IS NULL)::bigint AS sig_sinr_null_after_cnt,
      count(*) FILTER (WHERE sig_rssi IS NULL)::bigint AS sig_rssi_null_before_cnt,
      count(*) FILTER (WHERE sig_rssi_final IS NULL)::bigint AS sig_rssi_null_after_cnt,
      count(*) FILTER (WHERE sig_dbm IS NULL)::bigint AS sig_dbm_null_before_cnt,
      count(*) FILTER (WHERE sig_dbm_final IS NULL)::bigint AS sig_dbm_null_after_cnt,
      count(*) FILTER (WHERE sig_asu_level IS NULL)::bigint AS sig_asu_level_null_before_cnt,
      count(*) FILTER (WHERE sig_asu_level_final IS NULL)::bigint AS sig_asu_level_null_after_cnt,
      count(*) FILTER (WHERE sig_level IS NULL)::bigint AS sig_level_null_before_cnt,
      count(*) FILTER (WHERE sig_level_final IS NULL)::bigint AS sig_level_null_after_cnt,
      count(*) FILTER (WHERE sig_ss IS NULL)::bigint AS sig_ss_null_before_cnt,
      count(*) FILTER (WHERE sig_ss_final IS NULL)::bigint AS sig_ss_null_after_cnt
    FROM public.%I;
  $m$, metric_table, shard_count, shard_id, out_table);
END $$;
