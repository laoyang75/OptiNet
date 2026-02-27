-- Layer_3 Step35（附加流程）：动态 Cell / 动态 BS 检测（仅用于异常桶再分层）
--
-- 背景：
-- - Step30 已做“最严格混桶评估”，但仍会有少量桶被标记为 collision_suspect。
-- - 其中一类异常并非混桶，而是“动态/移动 cell”（时间上呈现明显的质心切换/周期切换）。
-- - 本 Step35 只做“异常桶的附加标记”，用于把动态cell从碰撞样本里分离出来，后续再分析剩余异常。
--
-- 输入依赖：
-- - public."Y_codex_Layer3_Step30_Master_BS_Library"（异常桶集合）
-- - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"（点级原始 lon_raw/lat_raw + report_date）
--
-- 输出：
-- - public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile"（cell 级动态标记）
-- - public."Y_codex_Layer3_Step35_Dynamic_BS_Profile"（桶/站级动态标记：被哪些动态cell影响）
-- - public."Y_codex_Layer3_Step35_Dynamic_Impact_Bucket"（可选：排除动态cell后 p90 是否显著回落）
--
-- 说明：
-- - 本实现故意“简单粗暴”：用坐标 round 到 3 位小数（~100m 级）做日主导质心，
--   再按时间分半比较主导质心是否切换 + 两半一致性是否足够高。
-- - 目标是快速把“明显呈现周期/切换的动态cell”标出来；准确度不是本轮重点。

/* ============================================================================
 * 会话级性能参数（PG15 / 40C / 256G / SSD）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '1GB';
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile";
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step35_Dynamic_BS_Profile";
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step35_Dynamic_Impact_Bucket";

CREATE TABLE public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile" AS
WITH
params AS (
  SELECT
    -- 只在“异常桶”里做检测：默认用 Step30 的碰撞疑似桶
    true::boolean AS only_collision_buckets,
    -- 进一步收敛异常桶规模（可调）：仅关注 p90 足够大的桶（更像动态/多质心）
    5000.0::double precision AS min_bs_p90_m,

    -- 日主导质心：round 精度（3 位小数约 100m；越小越粗）
    3::int AS grid_round_decimals,
    -- 单日是否“稳定”：主导质心占比低于该阈值则该天不参与“切换”判定
    0.50::double precision AS min_day_major_share,

    -- 动态判定：两半各自主导质心的“天占比”
    0.60::double precision AS min_half_major_day_share,
    -- 动态判定：两半主导质心间距（km）
    10.0::double precision AS min_half_major_dist_km,
    -- 动态判定：最少参与判定的有效天数（本期通常 7 天；若未来扩到 28 天可提高）
    5::int AS min_effective_days
),
abnormal_bs AS (
  SELECT
    s.wuli_fentong_bs_key,
    s.gps_p90_dist_m,
    s.collision_reason
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
  CROSS JOIN params p
  WHERE
    (NOT p.only_collision_buckets OR s.is_collision_suspect = 1)
    AND (p.min_bs_p90_m IS NULL OR s.gps_p90_dist_m >= p.min_bs_p90_m)
),
pts AS (
  SELECT
    d.operator_id_raw,
    d.tech_norm,
    d.cell_id_dec,
    d.bs_id,
    d.lac_dec_final,
    d.wuli_fentong_bs_key,
    (d.report_date AT TIME ZONE 'UTC')::date AS day_utc,
    d.lon_raw::double precision AS lon,
    d.lat_raw::double precision AS lat,
    d.gps_dist_to_bs_m
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" d
  JOIN abnormal_bs b
    ON b.wuli_fentong_bs_key = d.wuli_fentong_bs_key
  WHERE
    d.cell_id_dec IS NOT NULL AND d.cell_id_dec <> 0
    AND d.bs_id IS NOT NULL AND d.bs_id <> 0
    AND d.lon_raw IS NOT NULL AND d.lat_raw IS NOT NULL
    -- 粗框：只保留中国境内，避免跨洲极端坐标把“主导质心”污染
    AND d.lon_raw::double precision BETWEEN 73.0 AND 135.0
    AND d.lat_raw::double precision BETWEEN 3.0 AND 54.0
),
pt_grid AS (
  SELECT
    p.operator_id_raw,
    p.tech_norm,
    p.cell_id_dec,
    p.bs_id,
    p.lac_dec_final,
    p.wuli_fentong_bs_key,
    p.day_utc,
    round(p.lon::numeric, (SELECT grid_round_decimals FROM params))::double precision AS lon_r,
    round(p.lat::numeric, (SELECT grid_round_decimals FROM params))::double precision AS lat_r,
    count(*)::bigint AS point_cnt
  FROM pts p
  GROUP BY 1,2,3,4,5,6,7,8,9
),
day_ranked AS (
  SELECT
    g.*,
    sum(g.point_cnt) OVER (
      PARTITION BY g.operator_id_raw, g.tech_norm, g.cell_id_dec, g.wuli_fentong_bs_key, g.day_utc
    ) AS day_total_cnt,
    row_number() OVER (
      PARTITION BY g.operator_id_raw, g.tech_norm, g.cell_id_dec, g.wuli_fentong_bs_key, g.day_utc
      ORDER BY g.point_cnt DESC, g.lon_r, g.lat_r
    ) AS rn
  FROM pt_grid g
),
day_major AS (
  SELECT
    r.operator_id_raw,
    r.tech_norm,
    r.cell_id_dec,
    r.bs_id,
    r.lac_dec_final,
    r.wuli_fentong_bs_key,
    r.day_utc,
    r.lon_r,
    r.lat_r,
    r.point_cnt,
    r.day_total_cnt,
    (r.point_cnt::double precision / NULLIF(r.day_total_cnt, 0)) AS day_major_share
  FROM day_ranked r
  WHERE r.rn = 1
),
day_major_filtered AS (
  SELECT *
  FROM day_major
  WHERE day_major_share >= (SELECT min_day_major_share FROM params)
),
cell_span AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    min(day_utc) AS min_day_utc,
    max(day_utc) AS max_day_utc,
    count(*)::int AS effective_days,
    count(DISTINCT (lon_r, lat_r))::int AS major_state_cnt,
    max(day_total_cnt)::bigint AS max_day_total_cnt,
    avg(day_major_share)::double precision AS avg_day_major_share
  FROM day_major_filtered
  GROUP BY 1,2,3,4
),
day_labeled AS (
  SELECT
    d.*,
    s.min_day_utc,
    s.max_day_utc,
    (s.min_day_utc + ((s.max_day_utc - s.min_day_utc) / 2))::date AS mid_day_utc,
    CASE
      WHEN d.day_utc <= (s.min_day_utc + ((s.max_day_utc - s.min_day_utc) / 2))::date THEN 1
      ELSE 2
    END AS half_id
  FROM day_major_filtered d
  JOIN cell_span s
    ON s.operator_id_raw=d.operator_id_raw
   AND s.tech_norm=d.tech_norm
   AND s.cell_id_dec=d.cell_id_dec
   AND s.wuli_fentong_bs_key=d.wuli_fentong_bs_key
),
half_mode AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    half_id,
    lon_r,
    lat_r,
    count(*)::int AS day_cnt
  FROM day_labeled
  GROUP BY 1,2,3,4,5,6,7
),
half_ranked AS (
  SELECT
    m.*,
    sum(m.day_cnt) OVER (PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_dec, m.wuli_fentong_bs_key, m.half_id) AS half_days,
    row_number() OVER (
      PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_dec, m.wuli_fentong_bs_key, m.half_id
      ORDER BY m.day_cnt DESC, m.lon_r, m.lat_r
    ) AS rn
  FROM half_mode m
),
half_picked AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    half_id,
    lon_r,
    lat_r,
    day_cnt,
    half_days,
    (day_cnt::double precision / NULLIF(half_days, 0)) AS half_major_day_share
  FROM half_ranked
  WHERE rn = 1
),
half_pivot AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    max(CASE WHEN half_id=1 THEN lon_r END) AS half1_lon_r,
    max(CASE WHEN half_id=1 THEN lat_r END) AS half1_lat_r,
    max(CASE WHEN half_id=1 THEN half_major_day_share END) AS half1_major_share,
    max(CASE WHEN half_id=1 THEN half_days END) AS half1_days,
    max(CASE WHEN half_id=2 THEN lon_r END) AS half2_lon_r,
    max(CASE WHEN half_id=2 THEN lat_r END) AS half2_lat_r,
    max(CASE WHEN half_id=2 THEN half_major_day_share END) AS half2_major_share,
    max(CASE WHEN half_id=2 THEN half_days END) AS half2_days
  FROM half_picked
  GROUP BY 1,2,3,4
),
switch_base AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    day_utc,
    concat_ws('|', lon_r::text, lat_r::text) AS coord_key,
    lag(concat_ws('|', lon_r::text, lat_r::text)) OVER (
      PARTITION BY operator_id_raw, tech_norm, cell_id_dec, wuli_fentong_bs_key
      ORDER BY day_utc
    ) AS prev_coord_key
  FROM day_labeled
),
switch_cnt AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    wuli_fentong_bs_key,
    sum(CASE WHEN prev_coord_key IS NULL THEN 0 WHEN prev_coord_key <> coord_key THEN 1 ELSE 0 END)::int AS switch_cnt
  FROM switch_base
  GROUP BY 1,2,3,4
),
final AS (
  SELECT
    s.operator_id_raw,
    s.tech_norm,
    s.cell_id_dec,
    upper(ltrim(encode(int8send(s.cell_id_dec::bigint), 'hex'), '0')) AS cell_id_hex,
    s.wuli_fentong_bs_key,
    sp.min_day_utc,
    sp.max_day_utc,
    sp.effective_days,
    sp.major_state_cnt,
    sp.avg_day_major_share,
    sc.switch_cnt,

    hp.half1_lon_r,
    hp.half1_lat_r,
    hp.half1_major_share,
    hp.half1_days,
    hp.half2_lon_r,
    hp.half2_lat_r,
    hp.half2_major_share,
    hp.half2_days,

    CASE
      WHEN hp.half1_lon_r IS NULL OR hp.half1_lat_r IS NULL OR hp.half2_lon_r IS NULL OR hp.half2_lat_r IS NULL THEN NULL::double precision
      ELSE (6371000.0 * acos(
        LEAST(1.0,
          cos(radians(hp.half1_lat_r)) * cos(radians(hp.half2_lat_r)) * cos(radians(hp.half2_lon_r - hp.half1_lon_r))
          + sin(radians(hp.half1_lat_r)) * sin(radians(hp.half2_lat_r))
        )
      )) / 1000.0
    END AS half_major_dist_km,

    CASE
      WHEN sp.effective_days < (SELECT min_effective_days FROM params) THEN 0
      WHEN sp.major_state_cnt < 2 THEN 0
      WHEN hp.half1_lon_r IS NULL OR hp.half2_lon_r IS NULL THEN 0
      WHEN (hp.half1_lon_r = hp.half2_lon_r AND hp.half1_lat_r = hp.half2_lat_r) THEN 0
      WHEN COALESCE(hp.half1_major_share, 0) < (SELECT min_half_major_day_share FROM params) THEN 0
      WHEN COALESCE(hp.half2_major_share, 0) < (SELECT min_half_major_day_share FROM params) THEN 0
      WHEN (
        CASE
          WHEN hp.half1_lon_r IS NULL OR hp.half1_lat_r IS NULL OR hp.half2_lon_r IS NULL OR hp.half2_lat_r IS NULL THEN 0
          ELSE (6371000.0 * acos(
            LEAST(1.0,
              cos(radians(hp.half1_lat_r)) * cos(radians(hp.half2_lat_r)) * cos(radians(hp.half2_lon_r - hp.half1_lon_r))
              + sin(radians(hp.half1_lat_r)) * sin(radians(hp.half2_lat_r))
            )
          )) / 1000.0
        END
      ) < (SELECT min_half_major_dist_km FROM params) THEN 0
      ELSE 1
    END::int AS is_dynamic_cell,

    CASE
      WHEN sp.effective_days < (SELECT min_effective_days FROM params) THEN 'INSUFFICIENT_DAYS'
      WHEN sp.major_state_cnt < 2 THEN 'NO_MULTI_CENTROID'
      WHEN hp.half1_lon_r IS NULL OR hp.half2_lon_r IS NULL THEN 'NO_HALF_MODE'
      WHEN (hp.half1_lon_r = hp.half2_lon_r AND hp.half1_lat_r = hp.half2_lat_r) THEN 'NO_HALF_SWITCH'
      WHEN COALESCE(hp.half1_major_share, 0) < (SELECT min_half_major_day_share FROM params)
        OR COALESCE(hp.half2_major_share, 0) < (SELECT min_half_major_day_share FROM params) THEN 'HALF_DOMINANCE_WEAK'
      WHEN (
        CASE
          WHEN hp.half1_lon_r IS NULL OR hp.half1_lat_r IS NULL OR hp.half2_lon_r IS NULL OR hp.half2_lat_r IS NULL THEN 0
          ELSE (6371000.0 * acos(
            LEAST(1.0,
              cos(radians(hp.half1_lat_r)) * cos(radians(hp.half2_lat_r)) * cos(radians(hp.half2_lon_r - hp.half1_lon_r))
              + sin(radians(hp.half1_lat_r)) * sin(radians(hp.half2_lat_r))
            )
          )) / 1000.0
        END
      ) < (SELECT min_half_major_dist_km FROM params) THEN 'DIST_TOO_SMALL'
      ELSE 'HALF_SWITCH_TIME_CENTROID_CORR'
    END AS dynamic_reason
  FROM cell_span sp
  JOIN half_pivot hp
    ON hp.operator_id_raw=sp.operator_id_raw
   AND hp.tech_norm=sp.tech_norm
   AND hp.cell_id_dec=sp.cell_id_dec
   AND hp.wuli_fentong_bs_key=sp.wuli_fentong_bs_key
  LEFT JOIN switch_cnt sc
    ON sc.operator_id_raw=sp.operator_id_raw
   AND sc.tech_norm=sp.tech_norm
   AND sc.cell_id_dec=sp.cell_id_dec
   AND sc.wuli_fentong_bs_key=sp.wuli_fentong_bs_key
  -- 仅用于生成 cell_id_hex（保持字段齐全）
  JOIN (SELECT DISTINCT operator_id_raw, tech_norm, cell_id_dec, wuli_fentong_bs_key FROM day_major_filtered) s
    ON s.operator_id_raw=sp.operator_id_raw
   AND s.tech_norm=sp.tech_norm
   AND s.cell_id_dec=sp.cell_id_dec
   AND s.wuli_fentong_bs_key=sp.wuli_fentong_bs_key
)
SELECT * FROM final;

CREATE INDEX IF NOT EXISTS idx_step35_dynamic_cell_profile_key
  ON public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile"(wuli_fentong_bs_key);
CREATE INDEX IF NOT EXISTS idx_step35_dynamic_cell_profile_cell
  ON public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile"(operator_id_raw, tech_norm, cell_id_dec);

ANALYZE public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile";

-- ============================================================================
-- BS 级标记：哪些异常桶被动态cell“命中”
-- ============================================================================

CREATE TABLE public."Y_codex_Layer3_Step35_Dynamic_BS_Profile" AS
WITH dyn AS (
  SELECT *
  FROM public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile"
  WHERE is_dynamic_cell = 1
),
cell_to_bucket AS (
  SELECT DISTINCT
    s.operator_id_raw,
    s.tech_norm,
    s.bs_id,
    s.lac_dec_final,
    s.wuli_fentong_bs_key,
    s.cell_id_dec
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
  JOIN dyn d
    ON d.operator_id_raw=s.operator_id_raw
   AND d.tech_norm=s.tech_norm
   AND d.cell_id_dec=s.cell_id_dec
   AND d.wuli_fentong_bs_key=s.wuli_fentong_bs_key
)
SELECT
  c.operator_id_raw,
  c.tech_norm,
  c.bs_id,
  c.lac_dec_final,
  c.wuli_fentong_bs_key,
  count(DISTINCT c.cell_id_dec)::int AS dynamic_cell_cnt,
  array_to_string(array_agg(DISTINCT c.cell_id_dec ORDER BY c.cell_id_dec)[:20], ',') AS dynamic_cell_list_top20
FROM cell_to_bucket c
GROUP BY 1,2,3,4,5;

CREATE UNIQUE INDEX IF NOT EXISTS idx_step35_dynamic_bs_profile_pk
  ON public."Y_codex_Layer3_Step35_Dynamic_BS_Profile"(operator_id_raw, tech_norm, bs_id, lac_dec_final);

ANALYZE public."Y_codex_Layer3_Step35_Dynamic_BS_Profile";

-- ============================================================================
-- （可选）影响评估：排除动态cell后，异常桶 p90 是否显著回落
-- ============================================================================

CREATE TABLE public."Y_codex_Layer3_Step35_Dynamic_Impact_Bucket" AS
WITH
params AS (
  SELECT 5000.0::double precision AS min_bs_p90_m
),
abnormal_bs AS (
  SELECT wuli_fentong_bs_key
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library"
  CROSS JOIN params p
  WHERE is_collision_suspect=1 AND gps_p90_dist_m >= p.min_bs_p90_m
),
dyn_cell AS (
  SELECT DISTINCT operator_id_raw, tech_norm, cell_id_dec, wuli_fentong_bs_key
  FROM public."Y_codex_Layer3_Step35_Dynamic_Cell_Profile"
  WHERE is_dynamic_cell=1
),
base AS (
  SELECT
    s.operator_id_raw,
    s.tech_norm,
    s.bs_id,
    s.lac_dec_final,
    s.wuli_fentong_bs_key,
    s.cell_id_dec,
    s.gps_dist_to_bs_m
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
  JOIN abnormal_bs b ON b.wuli_fentong_bs_key=s.wuli_fentong_bs_key
  WHERE s.gps_dist_to_bs_m IS NOT NULL
),
labeled AS (
  SELECT
    b.*,
    CASE WHEN d.cell_id_dec IS NOT NULL THEN 1 ELSE 0 END AS is_dynamic_cell_row
  FROM base b
  LEFT JOIN dyn_cell d
    ON d.operator_id_raw=b.operator_id_raw
   AND d.tech_norm=b.tech_norm
   AND d.cell_id_dec=b.cell_id_dec
   AND d.wuli_fentong_bs_key=b.wuli_fentong_bs_key
),
all_stats AS (
  SELECT
    operator_id_raw,
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*)::bigint AS point_cnt_all,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY gps_dist_to_bs_m) AS p50_all_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY gps_dist_to_bs_m) AS p90_all_m,
    max(gps_dist_to_bs_m) AS max_all_m
  FROM labeled
  GROUP BY 1,2,3,4,5
),
non_dyn_stats AS (
  SELECT
    operator_id_raw,
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*)::bigint AS point_cnt_non_dynamic,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY gps_dist_to_bs_m) AS p50_non_dynamic_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY gps_dist_to_bs_m) AS p90_non_dynamic_m,
    max(gps_dist_to_bs_m) AS max_non_dynamic_m
  FROM labeled
  WHERE is_dynamic_cell_row=0
  GROUP BY 1,2,3,4,5
),
dyn_cnt AS (
  SELECT
    operator_id_raw,
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*) FILTER (WHERE is_dynamic_cell_row=1)::bigint AS point_cnt_dynamic
  FROM labeled
  GROUP BY 1,2,3,4,5
)
SELECT
  a.operator_id_raw,
  a.tech_norm,
  a.bs_id,
  a.lac_dec_final,
  a.wuli_fentong_bs_key,
  a.point_cnt_all,
  dc.point_cnt_dynamic,
  nd.point_cnt_non_dynamic,
  a.p50_all_m,
  a.p90_all_m,
  a.max_all_m,
  nd.p50_non_dynamic_m,
  nd.p90_non_dynamic_m,
  nd.max_non_dynamic_m
FROM all_stats a
LEFT JOIN dyn_cnt dc
  ON dc.operator_id_raw=a.operator_id_raw AND dc.tech_norm=a.tech_norm
 AND dc.bs_id=a.bs_id AND dc.lac_dec_final=a.lac_dec_final AND dc.wuli_fentong_bs_key=a.wuli_fentong_bs_key
LEFT JOIN non_dyn_stats nd
  ON nd.operator_id_raw=a.operator_id_raw AND nd.tech_norm=a.tech_norm
 AND nd.bs_id=a.bs_id AND nd.lac_dec_final=a.lac_dec_final AND nd.wuli_fentong_bs_key=a.wuli_fentong_bs_key;

CREATE INDEX IF NOT EXISTS idx_step35_dynamic_impact_bucket_key
  ON public."Y_codex_Layer3_Step35_Dynamic_Impact_Bucket"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step35_Dynamic_Impact_Bucket";
