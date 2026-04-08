\set ON_ERROR_STOP on
\timing on

-- Step30 v4 PREPARE
-- 目标：
-- - 先构建 bucket_universe（Step06），再把 Step02 的可信 GPS 点“归一+落桶（semi-join）”
-- - 将底座计算（Step05 唯一映射、点落桶）物化一次，避免分片会话重复扫大表
-- - 为后续“按桶分片并行”准备 points_calc（每桶最近 N=1000 点）与 bucket_stats（全量统计）
--
-- 依赖输入（Layer2 冻结）：
-- - public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
-- - public."Y_codex_Layer2_Step04_Master_Lac_Lib"
-- - public."Y_codex_Layer2_Step05_CellId_Stats_DB"
-- - public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
-- - public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
--
-- 输出（中间表，UNLOGGED）：
-- - public."Y_codex_Layer3_Step30__v4_bucket_universe"
-- - public."Y_codex_Layer3_Step30__v4_map_unique"
-- - public."Y_codex_Layer3_Step30__v4_points_norm"        -- 已落桶（semi-join）的点集
-- - public."Y_codex_Layer3_Step30__v4_points_calc"        -- 每桶最近 1000 点（用于重链路）
-- - public."Y_codex_Layer3_Step30__v4_bucket_stats"       -- 基于 points_norm 的全量桶统计
-- - public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt"   -- 风险哨兵（多 LAC 异常 cell）

/* ============================================================================
 * 会话级性能参数（PG15 / 40 核 / 256G / SSD）
 * - PREPARE 为单会话运行：允许查询内并行，但避免过高 work_mem
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
SET application_name = 'codex_step30v4|mode=prepare';

-- 可选：smoke 注入（用于 psql 脚本化执行；不传入则等价全量）
\if :{?is_smoke}
  SELECT set_config('codex.is_smoke', :'is_smoke', false);
\endif
\if :{?smoke_report_date}
  SELECT set_config('codex.smoke_report_date', :'smoke_report_date', false);
\endif
\if :{?smoke_operator_id_raw}
  SELECT set_config('codex.smoke_operator_id_raw', :'smoke_operator_id_raw', false);
\endif

-- 0.1 bucket_universe（桶全集）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_bucket_universe";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_bucket_universe" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw
)
SELECT
  t.tech_norm,
  t.bs_id,
  t.lac_dec_final,
  (t.tech_norm || '|' || t.bs_id::text || '|' || t.lac_dec_final::text) AS wuli_fentong_bs_key,
  count(DISTINCT t.operator_id_raw)::int AS shared_operator_cnt,
  array_to_string(array_agg(DISTINCT t.operator_id_raw ORDER BY t.operator_id_raw), ',') AS shared_operator_list,
  min(t.ts_std) AS first_seen_ts,
  max(t.ts_std) AS last_seen_ts,
  count(DISTINCT t.report_date)::int AS active_days
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
CROSS JOIN params p
WHERE
  t.tech_norm IN ('4G','5G')
  AND t.operator_id_raw IN ('46000','46001','46011','46015','46020')
  AND t.bs_id IS NOT NULL
  AND t.lac_dec_final IS NOT NULL
  AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
  AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
GROUP BY 1,2,3;

CREATE UNIQUE INDEX IF NOT EXISTS idx_step30_v4_bucket_universe_key
  ON public."Y_codex_Layer3_Step30__v4_bucket_universe"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step30__v4_bucket_universe";

-- 0.2 map_unique（唯一映射维表）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_map_unique";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_map_unique" AS
SELECT
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  CASE WHEN min(lac_dec) = max(lac_dec) THEN min(lac_dec) END AS lac_dec_from_map
FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
WHERE
  operator_id_raw IN ('46000','46001','46011','46015','46020')
  AND tech_norm IN ('4G','5G')
  AND cell_id_dec IS NOT NULL
  AND lac_dec IS NOT NULL
GROUP BY 1,2,3;

CREATE INDEX IF NOT EXISTS idx_step30_v4_map_unique_key
  ON public."Y_codex_Layer3_Step30__v4_map_unique"(operator_id_raw, tech_norm, cell_id_dec);

ANALYZE public."Y_codex_Layer3_Step30__v4_map_unique";

-- 1 points_norm（规范点窄表 + 落桶）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_points_norm";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_points_norm" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw
),
trusted_lac AS (
  SELECT operator_id_raw, tech_norm, lac_dec
  FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  WHERE is_trusted_lac
),
base AS (
  SELECT
    m.operator_id_raw,
    m.tech_norm,
    COALESCE(
      m.bs_id,
      CASE
        WHEN m.tech_norm='4G' AND m.cell_id_dec IS NOT NULL THEN floor(m.cell_id_dec / 256.0)::bigint
        WHEN m.tech_norm='5G' AND m.cell_id_dec IS NOT NULL THEN floor(m.cell_id_dec / 4096.0)::bigint
      END
    ) AS bs_id,
    m.cell_id_dec,
    m.report_date,
    m.ts_std,
    m.lon::double precision AS lon,
    m.lat::double precision AS lat,
    CASE
      WHEN m.sig_rsrp IN (-110, -1) OR m.sig_rsrp >= 0 THEN NULL::int
      ELSE m.sig_rsrp
    END AS sig_rsrp_clean,
    CASE
      WHEN tl.lac_dec IS NOT NULL THEN m.lac_dec
      ELSE mu.lac_dec_from_map
    END AS lac_dec_final
  FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" m
  CROSS JOIN params p
  LEFT JOIN trusted_lac tl
    ON m.operator_id_raw=tl.operator_id_raw
   AND m.tech_norm=tl.tech_norm
   AND m.lac_dec=tl.lac_dec
  LEFT JOIN public."Y_codex_Layer3_Step30__v4_map_unique" mu
    ON m.operator_id_raw=mu.operator_id_raw
   AND m.tech_norm=mu.tech_norm
   AND m.cell_id_dec=mu.cell_id_dec
  WHERE
    m.is_compliant
    AND m.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND m.tech_norm IN ('4G','5G')
    AND m.cell_id_dec IS NOT NULL
    AND m.has_gps
    AND m.lon::double precision BETWEEN 73.0 AND 135.0
    AND m.lat::double precision BETWEEN 3.0 AND 54.0
    AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR m.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR m.operator_id_raw = p.smoke_operator_id_raw)
)
SELECT
  b.operator_id_raw,
  b.tech_norm,
  b.bs_id,
  b.cell_id_dec,
  b.lac_dec_final,
  (b.tech_norm || '|' || b.bs_id::text || '|' || b.lac_dec_final::text) AS wuli_fentong_bs_key,
  b.report_date,
  b.ts_std,
  b.lon,
  b.lat,
  b.sig_rsrp_clean
FROM base b
JOIN public."Y_codex_Layer3_Step30__v4_bucket_universe" u
  ON u.tech_norm=b.tech_norm
 AND u.bs_id=b.bs_id
 AND u.lac_dec_final=b.lac_dec_final
WHERE
  b.bs_id IS NOT NULL
  AND b.lac_dec_final IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_step30_v4_points_norm_key_ts
  ON public."Y_codex_Layer3_Step30__v4_points_norm"(wuli_fentong_bs_key, ts_std DESC);

ANALYZE public."Y_codex_Layer3_Step30__v4_points_norm";

-- 2 points_calc（每桶最近 N=1000 点，用于重链路）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_points_calc";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_points_calc" AS
SELECT
  operator_id_raw,
  tech_norm,
  bs_id,
  cell_id_dec,
  lac_dec_final,
  wuli_fentong_bs_key,
  report_date,
  ts_std,
  lon,
  lat,
  sig_rsrp_clean
FROM (
  SELECT
    p.*,
    row_number() OVER (
      PARTITION BY p.wuli_fentong_bs_key
      ORDER BY p.ts_std DESC
    ) AS rn
  FROM public."Y_codex_Layer3_Step30__v4_points_norm" p
) t
WHERE t.rn <= 1000;

CREATE INDEX IF NOT EXISTS idx_step30_v4_points_calc_key
  ON public."Y_codex_Layer3_Step30__v4_points_calc"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step30__v4_points_calc";

-- 3 bucket_stats（全量桶统计；用于 gps_valid_level 等，避免被 points_calc 截断影响）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_bucket_stats";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_bucket_stats" AS
WITH
cell_stats AS (
  SELECT
    p.tech_norm,
    p.bs_id,
    p.lac_dec_final,
    p.wuli_fentong_bs_key,
    p.operator_id_raw,
    p.cell_id_dec,
    count(*)::bigint AS cell_point_cnt,
    count(*) FILTER (WHERE p.sig_rsrp_clean IS NOT NULL)::bigint AS cell_sig_valid_point_cnt
  FROM public."Y_codex_Layer3_Step30__v4_points_norm" p
  GROUP BY 1,2,3,4,5,6
),
bucket_counts AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*)::int AS gps_valid_cell_cnt,
    sum(cell_point_cnt)::bigint AS gps_valid_point_cnt,
    sum(cell_sig_valid_point_cnt)::bigint AS sig_valid_point_cnt
  FROM cell_stats
  GROUP BY 1,2,3,4
),
bbox AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    min(lon) AS lon_min,
    max(lon) AS lon_max,
    min(lat) AS lat_min,
    max(lat) AS lat_max
  FROM public."Y_codex_Layer3_Step30__v4_points_norm"
  GROUP BY 1,2,3,4
)
SELECT
  c.tech_norm,
  c.bs_id,
  c.lac_dec_final,
  c.wuli_fentong_bs_key,
  c.gps_valid_cell_cnt,
  c.gps_valid_point_cnt,
  c.sig_valid_point_cnt,
  b.lon_min,
  b.lon_max,
  b.lat_min,
  b.lat_max,
  sqrt(
    power(((b.lon_max - b.lon_min) * cos(radians((b.lat_max + b.lat_min) / 2.0)) * 111320.0), 2)
    + power(((b.lat_max - b.lat_min) * 110540.0), 2)
  ) AS diag_est_m
FROM bucket_counts c
JOIN bbox b
  ON b.tech_norm=c.tech_norm
 AND b.bs_id=c.bs_id
 AND b.lac_dec_final=c.lac_dec_final
 AND b.wuli_fentong_bs_key=c.wuli_fentong_bs_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_step30_v4_bucket_stats_key
  ON public."Y_codex_Layer3_Step30__v4_bucket_stats"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step30__v4_bucket_stats";

-- 0.x 风险哨兵（多 LAC 异常 cell 计数）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt";

CREATE UNLOGGED TABLE public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw
)
SELECT
  s.tech_norm,
  s.bs_id,
  s.lac_dec_final,
  (s.tech_norm || '|' || s.bs_id::text || '|' || s.lac_dec_final::text) AS wuli_fentong_bs_key,
  count(DISTINCT (s.operator_id_raw, s.cell_id_dec))::bigint AS anomaly_cell_cnt
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" s
CROSS JOIN params p
JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
  ON a.operator_id_raw=s.operator_id_raw
 AND a.tech_norm=s.tech_norm
 AND a.cell_id_dec=s.cell_id_dec
WHERE
  s.tech_norm IN ('4G','5G')
  AND s.operator_id_raw IN ('46000','46001','46011','46015','46020')
  AND s.bs_id IS NOT NULL
  AND s.lac_dec_final IS NOT NULL
  AND s.cell_id_dec IS NOT NULL
  AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR s.report_date = p.smoke_report_date)
  AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR s.operator_id_raw = p.smoke_operator_id_raw)
GROUP BY 1,2,3,4;

CREATE UNIQUE INDEX IF NOT EXISTS idx_step30_v4_anomaly_cell_cnt_key
  ON public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt";
