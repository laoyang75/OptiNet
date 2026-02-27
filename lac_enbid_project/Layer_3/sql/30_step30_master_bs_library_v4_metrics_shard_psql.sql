\set ON_ERROR_STOP on
\timing on

-- Step30 v4 METRICS（分片并行 / psql 专用）
-- 输入：
-- - public."Y_codex_Layer3_Step30__v4_points_calc"（每桶最近 N=1000 点）
-- 输出：
-- - public."Y_codex_Layer3_Step30__v4_metrics__shard_XX"（每桶一行：中心点+离散度+剔除计数）
--
-- 用法（示例）：
--   psql "$DATABASE_URL" -v shard_count=32 -v shard_id=0  -f lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_metrics_shard_psql.sql &
--   ...
--   psql "$DATABASE_URL" -v shard_count=32 -v shard_id=31 -f lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_metrics_shard_psql.sql &

-- 参数校验
\if :{?shard_count}
\else
  \echo 'ERROR: missing -v shard_count=<N>'
  \quit 2
\endif
\if :{?shard_id}
\else
  \echo 'ERROR: missing -v shard_id=<0..N-1>'
  \quit 2
\endif

-- 输出表名
\if :{?step30_metrics_table}
\else
  SELECT format('"%s"', format('Y_codex_Layer3_Step30__v4_metrics__shard_%s', lpad(:'shard_id', 2, '0'))) AS step30_metrics_table \gset
\endif
\echo Using step30_metrics_table=:step30_metrics_table

-- 方便现场监控过滤
\set app_name 'codex_step30v4|mode=metrics_shard|shard=' :shard_id '/' :shard_count
SET application_name = :'app_name';

/* ============================================================================
 * 会话级性能参数（PG15 / 40 核 / 256G / SSD）
 * - 分片并发时：禁止查询内并行，避免“会话并行 × 查询并行”互相打架
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- 分片参数注入：SQL 体内使用 current_setting('codex.*')
SELECT set_config('codex.shard_count', :'shard_count', false);
SELECT set_config('codex.shard_id', :'shard_id', false);

DROP TABLE IF EXISTS public.:step30_metrics_table;

CREATE TABLE public.:step30_metrics_table AS
WITH
params AS (
  SELECT
    2500.0::double precision AS outlier_remove_if_dist_m_gt,
    50::int AS signal_keep_top50_n,
    20::int AS signal_keep_top20_n,
    0.8::double precision AS signal_keep_ratio_if_low_cnt,
    5::int AS signal_min_points_for_signal_center,
    COALESCE((NULLIF(current_setting('codex.shard_count', true), ''))::int, 1) AS shard_count,
    COALESCE((NULLIF(current_setting('codex.shard_id', true), ''))::int, 0) AS shard_id,
    10000::int AS center_bin_scale,
    10::int AS dist_bin_m
),
points AS (
  SELECT
    p.operator_id_raw,
    p.tech_norm,
    p.bs_id,
    p.cell_id_dec,
    p.lac_dec_final,
    p.wuli_fentong_bs_key,
    p.lon,
    p.lat,
    p.sig_rsrp_clean
  FROM public."Y_codex_Layer3_Step30__v4_points_calc" p
  CROSS JOIN params pr
  WHERE
    pr.shard_count <= 1
    OR ((mod(hashtextextended(p.wuli_fentong_bs_key, 0), pr.shard_count) + pr.shard_count) % pr.shard_count) = pr.shard_id
),
sig_meta AS (
  SELECT
    wuli_fentong_bs_key,
    count(*) FILTER (WHERE sig_rsrp_clean IS NOT NULL)::int AS sig_valid_cnt
  FROM points
  GROUP BY 1
),
sig_policy AS (
  SELECT
    m.wuli_fentong_bs_key,
    m.sig_valid_cnt,
    CASE
      WHEN m.sig_valid_cnt >= p.signal_keep_top50_n THEN 'TOP50'
      WHEN m.sig_valid_cnt >= p.signal_keep_top20_n THEN 'TOP20'
      WHEN m.sig_valid_cnt >= 1 THEN 'TOP80PCT'
      ELSE 'ALL'
    END AS sig_keep_mode,
    CASE
      WHEN m.sig_valid_cnt >= p.signal_keep_top50_n THEN greatest(0.0, 1.0 - (p.signal_keep_top50_n::double precision / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= p.signal_keep_top20_n THEN greatest(0.0, 1.0 - (p.signal_keep_top20_n::double precision / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= 1 THEN (1.0 - p.signal_keep_ratio_if_low_cnt)
      ELSE NULL::double precision
    END AS keep_percentile
  FROM sig_meta m
  CROSS JOIN params p
),
sig_hist AS (
  SELECT
    g.wuli_fentong_bs_key,
    g.sig_rsrp_clean::int AS sig_rsrp_clean,
    count(*)::bigint AS cnt
  FROM points g
  WHERE g.sig_rsrp_clean IS NOT NULL
  GROUP BY 1,2
),
sig_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.sig_rsrp_clean) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM sig_hist h
),
sig_target AS (
  SELECT
    p.*,
    CASE
      WHEN p.keep_percentile IS NULL OR p.sig_valid_cnt <= 0 THEN NULL::bigint
      ELSE greatest(1::bigint, ceil(p.keep_percentile * p.sig_valid_cnt::double precision)::bigint)
    END AS sig_target_pos
  FROM sig_policy p
),
sig_threshold AS (
  SELECT
    t.wuli_fentong_bs_key,
    t.sig_valid_cnt,
    t.sig_keep_mode,
    t.keep_percentile,
    min(r.sig_rsrp_clean)::double precision AS sig_rsrp_threshold
  FROM sig_target t
  LEFT JOIN sig_rank r
    ON r.wuli_fentong_bs_key=t.wuli_fentong_bs_key
   AND t.sig_target_pos IS NOT NULL
   AND r.cum_cnt >= t.sig_target_pos
  GROUP BY 1,2,3,4
),
seed_points AS (
  SELECT
    g.*,
    st.sig_keep_mode,
    st.sig_valid_cnt,
    st.sig_rsrp_threshold,
    CASE
      WHEN st.sig_keep_mode = 'ALL' THEN true
      WHEN st.sig_rsrp_threshold IS NULL THEN false
      ELSE (g.sig_rsrp_clean IS NOT NULL AND g.sig_rsrp_clean >= st.sig_rsrp_threshold)
    END AS is_in_signal_seed
  FROM points g
  LEFT JOIN sig_threshold st
    ON st.wuli_fentong_bs_key=g.wuli_fentong_bs_key
),
seed_points_binned AS (
  SELECT
    s.*,
    round(s.lon * p.center_bin_scale)::int AS lon_bin,
    round(s.lat * p.center_bin_scale)::int AS lat_bin
  FROM seed_points s
  CROSS JOIN params p
),
center_init_all_lon_hist AS (
  SELECT wuli_fentong_bs_key, lon_bin, count(*)::bigint AS cnt
  FROM seed_points_binned
  GROUP BY 1,2
),
center_init_all_lon_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lon_bin) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM center_init_all_lon_hist h
),
center_init_all_lat_hist AS (
  SELECT wuli_fentong_bs_key, lat_bin, count(*)::bigint AS cnt
  FROM seed_points_binned
  GROUP BY 1,2
),
center_init_all_lat_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lat_bin) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM center_init_all_lat_hist h
),
center_init_all_lon AS (
  SELECT
    lo.wuli_fentong_bs_key,
    max(lo.total_cnt)::int AS all_point_cnt,
    ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ceil(lo.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS center_lon_all
  FROM center_init_all_lon_rank lo
  CROSS JOIN params p
  GROUP BY lo.wuli_fentong_bs_key, p.center_bin_scale
),
center_init_all_lat AS (
  SELECT
    la.wuli_fentong_bs_key,
    ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ceil(la.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS center_lat_all
  FROM center_init_all_lat_rank la
  CROSS JOIN params p
  GROUP BY la.wuli_fentong_bs_key, p.center_bin_scale
),
center_init_all AS (
  SELECT
    lo.wuli_fentong_bs_key,
    lo.all_point_cnt,
    lo.center_lon_all,
    la.center_lat_all
  FROM center_init_all_lon lo
  JOIN center_init_all_lat la
    ON la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
),
center_init_sig_lon_hist AS (
  SELECT wuli_fentong_bs_key, lon_bin, count(*)::bigint AS cnt
  FROM seed_points_binned
  WHERE is_in_signal_seed
  GROUP BY 1,2
),
center_init_sig_lon_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lon_bin) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM center_init_sig_lon_hist h
),
center_init_sig_lat_hist AS (
  SELECT wuli_fentong_bs_key, lat_bin, count(*)::bigint AS cnt
  FROM seed_points_binned
  WHERE is_in_signal_seed
  GROUP BY 1,2
),
center_init_sig_lat_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lat_bin) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM center_init_sig_lat_hist h
),
center_init_sig_lon AS (
  SELECT
    lo.wuli_fentong_bs_key,
    max(lo.total_cnt)::int AS sig_point_cnt,
    ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ceil(lo.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS center_lon_sig
  FROM center_init_sig_lon_rank lo
  CROSS JOIN params p
  GROUP BY lo.wuli_fentong_bs_key, p.center_bin_scale
),
center_init_sig_lat AS (
  SELECT
    la.wuli_fentong_bs_key,
    ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ceil(la.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS center_lat_sig
  FROM center_init_sig_lat_rank la
  CROSS JOIN params p
  GROUP BY la.wuli_fentong_bs_key, p.center_bin_scale
),
center_init_sig AS (
  SELECT
    lo.wuli_fentong_bs_key,
    lo.sig_point_cnt,
    lo.center_lon_sig,
    la.center_lat_sig
  FROM center_init_sig_lon lo
  JOIN center_init_sig_lat la
    ON la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
),
center_init AS (
  SELECT
    a.wuli_fentong_bs_key,
    CASE
      WHEN coalesce(s.sig_point_cnt, 0) >= p.signal_min_points_for_signal_center THEN s.center_lon_sig
      ELSE a.center_lon_all
    END AS center_lon_init,
    CASE
      WHEN coalesce(s.sig_point_cnt, 0) >= p.signal_min_points_for_signal_center THEN s.center_lat_sig
      ELSE a.center_lat_all
    END AS center_lat_init
  FROM center_init_all a
  LEFT JOIN center_init_sig s
    ON s.wuli_fentong_bs_key=a.wuli_fentong_bs_key
  CROSS JOIN params p
),
point_dist_init AS (
  SELECT
    g.wuli_fentong_bs_key,
    g.operator_id_raw,
    g.cell_id_dec,
    g.lon,
    g.lat,
    g.sig_rsrp_clean,
    g.is_in_signal_seed,
    c.center_lon_init,
    c.center_lat_init,
    CASE
      WHEN c.center_lon_init IS NULL OR c.center_lat_init IS NULL THEN NULL::double precision
      ELSE
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(g.lat - c.center_lat_init) / 2.0), 2)
            + cos(radians(c.center_lat_init)) * cos(radians(g.lat))
              * power(sin(radians(g.lon - c.center_lon_init) / 2.0), 2)
          )
        )
    END AS dist_m_init
  FROM seed_points g
  JOIN center_init c
    ON c.wuli_fentong_bs_key=g.wuli_fentong_bs_key
),
metric_init AS (
  SELECT
    wuli_fentong_bs_key,
    max(dist_m_init) AS gps_max_dist_m_init
  FROM point_dist_init
  WHERE dist_m_init IS NOT NULL
  GROUP BY 1
),
point_keep_flag AS (
  SELECT
    d.*,
    m.gps_max_dist_m_init,
    CASE
      WHEN m.gps_max_dist_m_init IS NULL THEN true
      WHEN m.gps_max_dist_m_init <= p.outlier_remove_if_dist_m_gt THEN true
      ELSE (d.dist_m_init <= p.outlier_remove_if_dist_m_gt)
    END AS is_kept
  FROM point_dist_init d
  JOIN metric_init m
    ON m.wuli_fentong_bs_key=d.wuli_fentong_bs_key
  CROSS JOIN params p
),
kept_stats AS (
  SELECT
    wuli_fentong_bs_key,
    count(*) FILTER (WHERE is_kept)::bigint AS kept_point_cnt,
    count(*) FILTER (WHERE NOT is_kept)::bigint AS removed_point_cnt
  FROM point_keep_flag
  GROUP BY 1
),
point_after AS (
  SELECT
    p.*,
    CASE
      WHEN ks.kept_point_cnt > 0 THEN p.is_kept
      ELSE true
    END AS is_kept_effective
  FROM point_keep_flag p
  JOIN kept_stats ks
    ON ks.wuli_fentong_bs_key=p.wuli_fentong_bs_key
),
center_final AS (
  WITH
  all_lon_hist AS (
    SELECT wuli_fentong_bs_key, round(lon * p.center_bin_scale)::int AS lon_bin, count(*)::bigint AS cnt
    FROM point_after
    CROSS JOIN params p
    WHERE is_kept_effective
    GROUP BY 1,2
  ),
  all_lon_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lon_bin) AS cum_cnt,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
    FROM all_lon_hist h
  ),
  all_lat_hist AS (
    SELECT wuli_fentong_bs_key, round(lat * p.center_bin_scale)::int AS lat_bin, count(*)::bigint AS cnt
    FROM point_after
    CROSS JOIN params p
    WHERE is_kept_effective
    GROUP BY 1,2
  ),
  all_lat_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lat_bin) AS cum_cnt,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
    FROM all_lat_hist h
  ),
  all_center_lon AS (
    SELECT
      lo.wuli_fentong_bs_key,
      max(lo.total_cnt)::int AS all_kept_cnt,
      ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ceil(lo.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS bs_center_lon_all
    FROM all_lon_rank lo
    CROSS JOIN params p
    GROUP BY lo.wuli_fentong_bs_key, p.center_bin_scale
  ),
  all_center_lat AS (
    SELECT
      la.wuli_fentong_bs_key,
      ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ceil(la.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS bs_center_lat_all
    FROM all_lat_rank la
    CROSS JOIN params p
    GROUP BY la.wuli_fentong_bs_key, p.center_bin_scale
  ),
  all_center AS (
    SELECT
      lo.wuli_fentong_bs_key,
      lo.all_kept_cnt,
      lo.bs_center_lon_all,
      la.bs_center_lat_all
    FROM all_center_lon lo
    JOIN all_center_lat la
      ON la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
  ),
  sig_lon_hist AS (
    SELECT wuli_fentong_bs_key, round(lon * p.center_bin_scale)::int AS lon_bin, count(*)::bigint AS cnt
    FROM point_after
    CROSS JOIN params p
    WHERE is_kept_effective AND is_in_signal_seed
    GROUP BY 1,2
  ),
  sig_lon_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lon_bin) AS cum_cnt,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
    FROM sig_lon_hist h
  ),
  sig_lat_hist AS (
    SELECT wuli_fentong_bs_key, round(lat * p.center_bin_scale)::int AS lat_bin, count(*)::bigint AS cnt
    FROM point_after
    CROSS JOIN params p
    WHERE is_kept_effective AND is_in_signal_seed
    GROUP BY 1,2
  ),
  sig_lat_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.lat_bin) AS cum_cnt,
      sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
    FROM sig_lat_hist h
  ),
  sig_center_lon AS (
    SELECT
      lo.wuli_fentong_bs_key,
      max(lo.total_cnt)::int AS sig_kept_cnt,
      ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ceil(lo.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS bs_center_lon_sig
    FROM sig_lon_rank lo
    CROSS JOIN params p
    GROUP BY lo.wuli_fentong_bs_key, p.center_bin_scale
  ),
  sig_center_lat AS (
    SELECT
      la.wuli_fentong_bs_key,
      ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ceil(la.total_cnt / 2.0)))::double precision) / p.center_bin_scale::double precision AS bs_center_lat_sig
    FROM sig_lat_rank la
    CROSS JOIN params p
    GROUP BY la.wuli_fentong_bs_key, p.center_bin_scale
  ),
  sig_center AS (
    SELECT
      lo.wuli_fentong_bs_key,
      lo.sig_kept_cnt,
      lo.bs_center_lon_sig,
      la.bs_center_lat_sig
    FROM sig_center_lon lo
    JOIN sig_center_lat la
      ON la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
  )
  SELECT
    ac.wuli_fentong_bs_key,
    max(ks.removed_point_cnt)::bigint AS outlier_removed_cnt,
    CASE
      WHEN coalesce(sc.sig_kept_cnt, 0) >= p.signal_min_points_for_signal_center THEN sc.bs_center_lon_sig
      ELSE ac.bs_center_lon_all
    END AS bs_center_lon,
    CASE
      WHEN coalesce(sc.sig_kept_cnt, 0) >= p.signal_min_points_for_signal_center THEN sc.bs_center_lat_sig
      ELSE ac.bs_center_lat_all
    END AS bs_center_lat
  FROM all_center ac
  LEFT JOIN sig_center sc
    ON sc.wuli_fentong_bs_key=ac.wuli_fentong_bs_key
  JOIN kept_stats ks
    ON ks.wuli_fentong_bs_key=ac.wuli_fentong_bs_key
  CROSS JOIN params p
  GROUP BY ac.wuli_fentong_bs_key, ac.bs_center_lon_all, ac.bs_center_lat_all, sc.sig_kept_cnt, sc.bs_center_lon_sig, sc.bs_center_lat_sig, p.signal_min_points_for_signal_center
),
point_dist_final AS (
  SELECT
    a.wuli_fentong_bs_key,
    a.lon,
    a.lat,
    c.bs_center_lon,
    c.bs_center_lat,
    c.outlier_removed_cnt,
    CASE
      WHEN c.bs_center_lon IS NULL OR c.bs_center_lat IS NULL THEN NULL::double precision
      ELSE
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(a.lat - c.bs_center_lat) / 2.0), 2)
            + cos(radians(c.bs_center_lat)) * cos(radians(a.lat))
              * power(sin(radians(a.lon - c.bs_center_lon) / 2.0), 2)
          )
        )
    END AS dist_m
  FROM point_after a
  JOIN center_final c
    ON c.wuli_fentong_bs_key=a.wuli_fentong_bs_key
  WHERE a.is_kept_effective
),
dist_hist AS (
  SELECT
    d.wuli_fentong_bs_key,
    (floor(d.dist_m / p.dist_bin_m::double precision)::bigint * p.dist_bin_m::bigint)::bigint AS dist_bin_m,
    count(*)::bigint AS cnt
  FROM point_dist_final d
  CROSS JOIN params p
  WHERE d.dist_m IS NOT NULL
  GROUP BY 1,2
),
dist_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key ORDER BY h.dist_bin_m) AS cum_cnt,
    sum(h.cnt) OVER (PARTITION BY h.wuli_fentong_bs_key) AS total_cnt
  FROM dist_hist h
),
dist_pcts AS (
  SELECT
    r.wuli_fentong_bs_key,
    ((min(r.dist_bin_m) FILTER (WHERE r.cum_cnt >= ceil(r.total_cnt / 2.0)))::double precision) AS gps_p50_dist_m,
    ((min(r.dist_bin_m) FILTER (WHERE r.cum_cnt >= ceil(r.total_cnt * 0.9)))::double precision) AS gps_p90_dist_m
  FROM dist_rank r
  GROUP BY 1
),
metric_final_base AS (
  SELECT
    wuli_fentong_bs_key,
    max(outlier_removed_cnt)::bigint AS outlier_removed_cnt,
    max(bs_center_lon) AS bs_center_lon,
    max(bs_center_lat) AS bs_center_lat,
    max(dist_m) AS gps_max_dist_m
  FROM point_dist_final
  WHERE dist_m IS NOT NULL
  GROUP BY 1
),
metric_final AS (
  SELECT
    b.wuli_fentong_bs_key,
    b.outlier_removed_cnt,
    b.bs_center_lon,
    b.bs_center_lat,
    p.gps_p50_dist_m,
    p.gps_p90_dist_m,
    b.gps_max_dist_m
  FROM metric_final_base b
  LEFT JOIN dist_pcts p
    ON p.wuli_fentong_bs_key=b.wuli_fentong_bs_key
),
key_dim AS (
  SELECT
    wuli_fentong_bs_key,
    min(tech_norm) AS tech_norm,
    min(bs_id) AS bs_id,
    min(lac_dec_final) AS lac_dec_final
  FROM points
  GROUP BY 1
)
SELECT
  d.tech_norm,
  d.bs_id,
  d.lac_dec_final,
  d.wuli_fentong_bs_key,
  m.outlier_removed_cnt,
  m.bs_center_lon,
  m.bs_center_lat,
  m.gps_p50_dist_m,
  m.gps_p90_dist_m,
  m.gps_max_dist_m
FROM key_dim d
LEFT JOIN metric_final m
  ON m.wuli_fentong_bs_key=d.wuli_fentong_bs_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_step30_v4_metrics_shard_key
  ON public.:step30_metrics_table(wuli_fentong_bs_key);

ANALYZE public.:step30_metrics_table;
