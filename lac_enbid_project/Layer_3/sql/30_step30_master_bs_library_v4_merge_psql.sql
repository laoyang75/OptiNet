\set ON_ERROR_STOP on
\timing on

-- Step30 v4 MERGE（psql 专用）
-- 目标：
-- - 合并 metrics shards
-- - 构建最终 Step30 输出表 public."Y_codex_Layer3_Step30_Master_BS_Library"
-- - 构建统计表 public."Y_codex_Layer3_Step30_Gps_Level_Stats"

\if :{?shard_count}
\else
  \echo 'ERROR: missing -v shard_count=<N>'
  \quit 2
\endif

-- 输出表名（可覆盖）
\if :{?step30_master_table}
\else
  \set step30_master_table '"Y_codex_Layer3_Step30_Master_BS_Library"'
\endif
\if :{?step30_stats_table}
\else
  \set step30_stats_table '"Y_codex_Layer3_Step30_Gps_Level_Stats"'
\endif

\echo Using step30_master_table=:step30_master_table
\echo Using step30_stats_table=:step30_stats_table

/* ============================================================================
 * 会话级性能参数（PG15 / 40 核 / 256G / SSD）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;
SET application_name = 'codex_step30v4|mode=merge';

-- 先合并 shard 结果到 v4_metrics
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_metrics";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_metrics" (
  tech_norm text,
  bs_id bigint,
  lac_dec_final bigint,
  wuli_fentong_bs_key text PRIMARY KEY,
  outlier_removed_cnt bigint,
  bs_center_lon double precision,
  bs_center_lat double precision,
  gps_p50_dist_m double precision,
  gps_p90_dist_m double precision,
  gps_max_dist_m double precision
);


-- 注入变量到会话配置（解决 DO block 无法读取 psql 变量的问题）
SELECT set_config('codex.shard_count', :'shard_count', false);

DO $$
DECLARE
  shard_count int := current_setting('codex.shard_count')::int;
  shard_id int;
  shard_table text;
  missing_shards text[] := ARRAY[]::text[];
BEGIN
  FOR shard_id IN 0..(shard_count - 1) LOOP
    shard_table := format('public."Y_codex_Layer3_Step30__v4_metrics__shard_%s"', lpad(shard_id::text, 2, '0'));
    IF to_regclass(shard_table) IS NULL THEN
      missing_shards := array_append(missing_shards, shard_table);
    ELSE
      EXECUTE format('INSERT INTO public."Y_codex_Layer3_Step30__v4_metrics" SELECT * FROM %s', shard_table);
    END IF;
  END LOOP;

  IF array_length(missing_shards, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'Missing metrics shard tables (%): %', array_length(missing_shards, 1), array_to_string(missing_shards, ', ');
  END IF;
END $$;

ANALYZE public."Y_codex_Layer3_Step30__v4_metrics";

-- 构建最终 Step30 主表
DROP TABLE IF EXISTS public.:step30_master_table;

CREATE TABLE public.:step30_master_table AS
WITH
params AS (
  SELECT
    1500.0::double precision AS collision_if_p90_dist_m_gt
)
SELECT
  u.tech_norm,
  u.bs_id,
  u.wuli_fentong_bs_key,
  u.lac_dec_final,

  -- 共建/共用
  u.shared_operator_cnt,
  u.shared_operator_list,
  (u.shared_operator_cnt > 1) AS is_multi_operator_shared,

  -- GPS 有效性分级（基于 points_norm 的全量桶统计，避免被 points_calc 截断影响）
  COALESCE(s.gps_valid_cell_cnt, 0)::int AS gps_valid_cell_cnt,
  COALESCE(s.gps_valid_point_cnt, 0)::bigint AS gps_valid_point_cnt,
  CASE
    WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN 'Unusable'
    WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 1 THEN 'Risk'
    ELSE 'Usable'
  END AS gps_valid_level,

  -- 中心点与离散度（Unusable 置空）
  CASE WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN NULL ELSE m.bs_center_lon END AS bs_center_lon,
  CASE WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN NULL ELSE m.bs_center_lat END AS bs_center_lat,
  CASE WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN NULL ELSE m.gps_p50_dist_m END AS gps_p50_dist_m,
  -- 兼容：当样本点极少且 metrics 侧 p90 为空时，p90 等价于 max（避免 collision 低估）
  CASE
    WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN NULL
    ELSE COALESCE(m.gps_p90_dist_m, CASE WHEN m.gps_p50_dist_m IS NOT NULL THEN m.gps_max_dist_m END)
  END AS gps_p90_dist_m,
  CASE WHEN COALESCE(s.gps_valid_cell_cnt, 0) = 0 THEN NULL ELSE m.gps_max_dist_m END AS gps_max_dist_m,
  COALESCE(m.outlier_removed_cnt, 0) AS outlier_removed_cnt,

  -- 风险/碰撞
  CASE
    WHEN COALESCE(s.gps_valid_cell_cnt, 0) <= 1 THEN 0
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0 THEN 1
    WHEN COALESCE(m.gps_p90_dist_m, CASE WHEN m.gps_p50_dist_m IS NOT NULL THEN m.gps_max_dist_m END) IS NULL THEN 0
    WHEN COALESCE(m.gps_p90_dist_m, CASE WHEN m.gps_p50_dist_m IS NOT NULL THEN m.gps_max_dist_m END) > p.collision_if_p90_dist_m_gt THEN 1
    ELSE 0
  END::int AS is_collision_suspect,
  CASE
    WHEN COALESCE(s.gps_valid_cell_cnt, 0) <= 1 THEN NULL
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0
     AND COALESCE(m.gps_p90_dist_m, CASE WHEN m.gps_p50_dist_m IS NOT NULL THEN m.gps_max_dist_m END) > p.collision_if_p90_dist_m_gt
    THEN E'STEP05_MULTI_LAC_CELL\\073GPS_SCATTER_P90_GT_THRESHOLD'
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0 THEN 'STEP05_MULTI_LAC_CELL'
    WHEN COALESCE(m.gps_p90_dist_m, CASE WHEN m.gps_p50_dist_m IS NOT NULL THEN m.gps_max_dist_m END) > p.collision_if_p90_dist_m_gt THEN 'GPS_SCATTER_P90_GT_THRESHOLD'
    ELSE NULL
  END AS collision_reason,
  COALESCE(a.anomaly_cell_cnt, 0) AS anomaly_cell_cnt,

  -- 覆盖时间画像（来自 Step06）
  u.first_seen_ts,
  u.last_seen_ts,
  u.active_days
FROM public."Y_codex_Layer3_Step30__v4_bucket_universe" u
LEFT JOIN public."Y_codex_Layer3_Step30__v4_bucket_stats" s
  ON s.wuli_fentong_bs_key=u.wuli_fentong_bs_key
LEFT JOIN public."Y_codex_Layer3_Step30__v4_metrics" m
  ON m.wuli_fentong_bs_key=u.wuli_fentong_bs_key
LEFT JOIN public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt" a
  ON a.wuli_fentong_bs_key=u.wuli_fentong_bs_key
CROSS JOIN params p;

ANALYZE public.:step30_master_table;

-- Step30 统计表：GPS 可用性分级分布（按运营商/tech）
DROP TABLE IF EXISTS public.:step30_stats_table;

CREATE TABLE public.:step30_stats_table AS
WITH base AS (
  SELECT
    s.tech_norm,
    op.operator_id_raw,
    s.gps_valid_level,
    count(*)::bigint AS bs_cnt
  FROM public.:step30_master_table s
  CROSS JOIN LATERAL unnest(string_to_array(s.shared_operator_list, ',')) AS op(operator_id_raw)
  GROUP BY 1,2,3
),
scored AS (
  SELECT
    b.*,
    round(b.bs_cnt::numeric / nullif(sum(b.bs_cnt) OVER (PARTITION BY b.tech_norm, b.operator_id_raw), 0), 8) AS bs_pct
  FROM base b
)
SELECT * FROM scored;

ANALYZE public.:step30_stats_table;
