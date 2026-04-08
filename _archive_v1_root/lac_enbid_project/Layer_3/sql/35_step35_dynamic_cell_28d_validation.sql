-- Layer_3 Step35（外部验证版本）：动态/移动 Cell 检测（基于 28 天原始明细表）
--
-- 用途：
-- - 不依赖 Layer_3 Step31 明细（避免“回填后”污染），直接用你提供的 28 天原始明细表做验证。
-- - 目标是识别“时间相关多质心切换/周期切换”的 scoped cell，用于从疑似混桶样本中先剥离动态/移动 cell。
--
-- 输入（你准备的表，需存在）：
-- - public.cell_id_375_28d_data_20251225
--   必须列：ts, opt_id, cell_id, dynamic_network_type, lgt, ltt
--
-- 输出：
-- - public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"
--
-- 重要说明：
-- - 本输出表中的 `tech_norm` 直接使用输入表的 `dynamic_network_type`（例如 5G_SA/4G），并非 Layer_3 的 tech_norm(4G/5G)。
--   若需要与 Layer_3 表 join，请自行做一次归一映射（例如 5G_SA -> 5G）。

/* ============================================================================
 * 会话级性能参数（PG15 / SSD）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile";

CREATE TABLE public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile" AS
WITH
params AS (
  SELECT
    28::int AS window_days,
    14::int AS half_days,

    3::int AS grid_round_decimals,
    0.30::double precision AS min_day_major_share,

    7::int AS min_effective_days,
    0.60::double precision AS min_half_major_day_share,
    10.0::double precision AS min_half_major_dist_km
),
window_bound AS (
  SELECT
    (max(to_timestamp(ts, 'YYYY-MM-DD HH24:MI:SS')) AT TIME ZONE 'UTC')::date AS window_end_day,
    ((max(to_timestamp(ts, 'YYYY-MM-DD HH24:MI:SS')) AT TIME ZONE 'UTC')::date - ((SELECT window_days FROM params) - 1))::date AS window_start_day
  FROM public.cell_id_375_28d_data_20251225
  WHERE ts IS NOT NULL
),
pts AS (
  SELECT
    d.opt_id AS operator_id_raw,
    d.dynamic_network_type AS tech_norm,
    d.cell_id AS cell_id_raw,
    CASE WHEN d.cell_id ~ '^[0-9]+$' THEN d.cell_id::bigint ELSE NULL::bigint END AS cell_id_dec,
    (to_timestamp(d.ts, 'YYYY-MM-DD HH24:MI:SS') AT TIME ZONE 'UTC') AS ts_utc,
    (to_timestamp(d.ts, 'YYYY-MM-DD HH24:MI:SS') AT TIME ZONE 'UTC')::date AS day_utc,
    d.lgt::double precision AS lon,
    d.ltt::double precision AS lat
  FROM public.cell_id_375_28d_data_20251225 d
  CROSS JOIN window_bound wb
  WHERE
    d.ts IS NOT NULL
    AND ((to_timestamp(d.ts, 'YYYY-MM-DD HH24:MI:SS') AT TIME ZONE 'UTC')::date BETWEEN wb.window_start_day AND wb.window_end_day)
    AND d.opt_id IS NOT NULL AND d.dynamic_network_type IS NOT NULL AND d.cell_id IS NOT NULL
    AND d.lgt IS NOT NULL AND d.ltt IS NOT NULL
    AND d.lgt BETWEEN 73.0 AND 135.0
    AND d.ltt BETWEEN 3.0 AND 54.0
),
pt_grid AS (
  SELECT
    p.operator_id_raw,
    p.tech_norm,
    p.cell_id_raw,
    p.cell_id_dec,
    p.day_utc,
    round(p.lon::numeric, (SELECT grid_round_decimals FROM params))::double precision AS lon_r,
    round(p.lat::numeric, (SELECT grid_round_decimals FROM params))::double precision AS lat_r,
    count(*)::bigint AS point_cnt
  FROM pts p
  GROUP BY 1,2,3,4,5,6,7
),
day_ranked AS (
  SELECT
    g.*,
    sum(g.point_cnt) OVER (PARTITION BY g.operator_id_raw, g.tech_norm, g.cell_id_raw, g.day_utc) AS day_total_cnt,
    row_number() OVER (
      PARTITION BY g.operator_id_raw, g.tech_norm, g.cell_id_raw, g.day_utc
      ORDER BY g.point_cnt DESC, g.lon_r, g.lat_r
    ) AS rn
  FROM pt_grid g
),
day_major AS (
  SELECT
    r.operator_id_raw,
    r.tech_norm,
    r.cell_id_raw,
    r.cell_id_dec,
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
    cell_id_raw,
    max(cell_id_dec) AS cell_id_dec,
    min(day_utc) AS min_day_utc,
    max(day_utc) AS max_day_utc,
    count(*)::int AS effective_days,
    count(DISTINCT (lon_r, lat_r))::int AS major_state_cnt,
    avg(day_major_share)::double precision AS avg_day_major_share
  FROM day_major_filtered
  GROUP BY 1,2,3
),
day_labeled AS (
  SELECT
    d.*,
    wb.window_start_day,
    wb.window_end_day,
    (wb.window_start_day + ((SELECT half_days FROM params) - 1))::date AS mid_day_utc,
    CASE
      WHEN d.day_utc <= (wb.window_start_day + ((SELECT half_days FROM params) - 1))::date THEN 1
      ELSE 2
    END AS half_id
  FROM day_major_filtered d
  CROSS JOIN window_bound wb
),
half_mode AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_raw,
    half_id,
    lon_r,
    lat_r,
    count(*)::int AS day_cnt
  FROM day_labeled
  GROUP BY 1,2,3,4,5,6
),
half_ranked AS (
  SELECT
    m.*,
    sum(m.day_cnt) OVER (PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_raw, m.half_id) AS half_days,
    row_number() OVER (
      PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_raw, m.half_id
      ORDER BY m.day_cnt DESC, m.lon_r, m.lat_r
    ) AS rn
  FROM half_mode m
),
half_picked AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_raw,
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
    cell_id_raw,
    max(CASE WHEN half_id=1 THEN lon_r END) AS half1_lon_r,
    max(CASE WHEN half_id=1 THEN lat_r END) AS half1_lat_r,
    max(CASE WHEN half_id=1 THEN half_major_day_share END) AS half1_major_share,
    max(CASE WHEN half_id=1 THEN half_days END) AS half1_days,
    max(CASE WHEN half_id=2 THEN lon_r END) AS half2_lon_r,
    max(CASE WHEN half_id=2 THEN lat_r END) AS half2_lat_r,
    max(CASE WHEN half_id=2 THEN half_major_day_share END) AS half2_major_share,
    max(CASE WHEN half_id=2 THEN half_days END) AS half2_days
  FROM half_picked
  GROUP BY 1,2,3
),
switch_base AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_raw,
    day_utc,
    concat_ws('|', lon_r::text, lat_r::text) AS coord_key,
    lag(concat_ws('|', lon_r::text, lat_r::text)) OVER (
      PARTITION BY operator_id_raw, tech_norm, cell_id_raw
      ORDER BY day_utc
    ) AS prev_coord_key
  FROM day_labeled
),
switch_cnt AS (
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_raw,
    sum(CASE WHEN prev_coord_key IS NULL THEN 0 WHEN prev_coord_key <> coord_key THEN 1 ELSE 0 END)::int AS switch_cnt
  FROM switch_base
  GROUP BY 1,2,3
),
final AS (
  SELECT
    sp.operator_id_raw,
    sp.tech_norm,
    sp.cell_id_raw AS cell_id,
    sp.cell_id_dec,
    CASE
      WHEN sp.cell_id_dec IS NULL THEN NULL
      ELSE upper(ltrim(encode(int8send(sp.cell_id_dec), 'hex'), '0'))
    END AS cell_id_hex,

    wb.window_start_day,
    wb.window_end_day,

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
   AND hp.cell_id_raw=sp.cell_id_raw
  LEFT JOIN switch_cnt sc
    ON sc.operator_id_raw=sp.operator_id_raw
   AND sc.tech_norm=sp.tech_norm
   AND sc.cell_id_raw=sp.cell_id_raw
  CROSS JOIN window_bound wb
)
SELECT * FROM final;

CREATE INDEX IF NOT EXISTS idx_step35_28d_dynamic_cell_pk
  ON public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"(operator_id_raw, tech_norm, cell_id);
CREATE INDEX IF NOT EXISTS idx_step35_28d_dynamic_cell_flag
  ON public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"(is_dynamic_cell);

ANALYZE public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile";

