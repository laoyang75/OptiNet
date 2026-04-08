-- 补丁_20251219_Layer3_Step30_点级剔除漂移GPS_局部更新.sql
--
-- 目标：
-- - 避免全量重跑 Step30（CTAS 很慢），仅对“少量可疑桶”做局部修复：
--   1) Step30：按“点级鲁棒中心点（中位数）+ 距离阈值剔除漂移点（一次）+ 重算”的方式，重算中心点与离散度
--   2) Step31：对同一批桶，按“非中国坐标视为 Missing，然后按基站中心点回填”的规则重算 gps_status/gps_source/lon_final/lat_final
-- - Step32：建议最后单独执行 `lac_enbid_project/Layer_3/sql/32_step32_compare.sql`（很快）来刷新 WARN。
--
-- 使用方式（建议 psql 执行整文件）：
--   psql -f lac_enbid_project/补丁/补丁_20251219_Layer3_Step30_点级剔除漂移GPS_局部更新.sql
--
-- 你需要做的唯一改动（二选一/可同时用）：
--   A) 调整“0) 生成本次要修复的桶清单”里的阈值/limit（默认只选“少量漂移点导致的超大离散度”桶，通常几十个以内）
--   B) 在“手工追加桶（可选）”里补充你指定的桶（tech_norm, bs_id, lac_dec_final）

SET statement_timeout = 0;

BEGIN;

-- 0) 生成本次要修复的桶清单（落到“表”里：你可以先 SELECT 看，再决定要不要执行下面的 UPDATE）
CREATE TABLE IF NOT EXISTS public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219" (
  tech_norm text NOT NULL,
  bs_id bigint NOT NULL,
  lac_dec_final bigint NOT NULL,
  wuli_fentong_bs_key text GENERATED ALWAYS AS (tech_norm || '|' || bs_id::text || '|' || lac_dec_final::text) STORED,
  select_reason text NOT NULL,
  gps_valid_level text,
  is_collision_suspect int,
  gps_valid_cell_cnt int,
  gps_valid_point_cnt bigint,
  gps_p50_dist_m double precision,
  gps_p90_dist_m double precision,
  gps_max_dist_m double precision,
  anomaly_cell_cnt int,
  collision_reason text,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (tech_norm, bs_id, lac_dec_final)
);

ALTER TABLE public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219"
  ADD COLUMN IF NOT EXISTS anomaly_cell_cnt int;

TRUNCATE public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219";

WITH patch_params AS (
  SELECT
    30::bigint AS min_point_cnt,
    500.0::double precision AS p50_m_le,
    10000.0::double precision AS p90_m_ge,
    1::int AS require_collision_suspect,
    1::int AS require_anomaly_cell_cnt_eq0,
    1::int AS require_reason_scatter,
    50::int AS limit_keys
)
INSERT INTO public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219" (
  tech_norm,
  bs_id,
  lac_dec_final,
  select_reason,
  gps_valid_level,
  is_collision_suspect,
  gps_valid_cell_cnt,
  gps_valid_point_cnt,
  gps_p50_dist_m,
  gps_p90_dist_m,
  gps_max_dist_m,
  anomaly_cell_cnt,
  collision_reason
)
SELECT
  s.tech_norm,
  s.bs_id,
  s.lac_dec_final,
  format(
    'AUTO:p50<=%s,p90>=%s,point>=%s,collision_suspect=%s,anomaly_cell_cnt_eq0=%s,reason_scatter=%s',
    p.p50_m_le::text,
    p.p90_m_ge::text,
    p.min_point_cnt::text,
    p.require_collision_suspect::text,
    p.require_anomaly_cell_cnt_eq0::text,
    p.require_reason_scatter::text
  ) AS select_reason,
  s.gps_valid_level,
  s.is_collision_suspect,
  s.gps_valid_cell_cnt,
  s.gps_valid_point_cnt,
  s.gps_p50_dist_m,
  s.gps_p90_dist_m,
  s.gps_max_dist_m,
  s.anomaly_cell_cnt,
  s.collision_reason
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
CROSS JOIN patch_params p
WHERE
  s.lac_dec_final IS NOT NULL
  AND s.gps_valid_level = 'Usable'
  AND COALESCE(s.gps_valid_point_cnt, 0) >= p.min_point_cnt
  AND s.gps_p50_dist_m IS NOT NULL
  AND s.gps_p90_dist_m IS NOT NULL
  AND s.gps_p50_dist_m <= p.p50_m_le
  AND s.gps_p90_dist_m >= p.p90_m_ge
  AND (p.require_collision_suspect = 0 OR s.is_collision_suspect = 1)
  AND (p.require_anomaly_cell_cnt_eq0 = 0 OR COALESCE(s.anomaly_cell_cnt, 0) = 0)
  AND (p.require_reason_scatter = 0 OR s.collision_reason LIKE '%GPS_SCATTER_P90_GT_THRESHOLD%')
ORDER BY s.gps_p90_dist_m DESC NULLS LAST
LIMIT (SELECT limit_keys FROM patch_params);

-- 手工追加桶（可选）
-- INSERT INTO public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219" (tech_norm, bs_id, lac_dec_final, select_reason)
-- VALUES ('4G', 95640, 4556, 'MANUAL:from_user')
-- ON CONFLICT (tech_norm, bs_id, lac_dec_final) DO NOTHING;

-- 本次补丁桶概览（方便你先看一下修复名单是否合理）
SELECT count(*) AS patch_key_cnt
FROM public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219";

SELECT
  tech_norm,
  bs_id,
  wuli_fentong_bs_key,
  gps_valid_cell_cnt,
  gps_valid_point_cnt,
  gps_p50_dist_m,
  gps_p90_dist_m,
  gps_max_dist_m,
  anomaly_cell_cnt,
  collision_reason,
  select_reason
FROM public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219"
ORDER BY gps_p90_dist_m DESC NULLS LAST
LIMIT 10;

-- 驱动本次补丁的临时键表
CREATE TEMP TABLE tmp_patch_keys AS
SELECT
  tech_norm,
  bs_id,
  lac_dec_final,
  wuli_fentong_bs_key
FROM public."Y_patch_L3_Step30_PointTrim_WorkKeys_20251219";

-- 1) 修复前快照（仅 Step30：1 行/桶）
DROP TABLE IF EXISTS tmp_before_step30;
CREATE TEMP TABLE tmp_before_step30 AS
SELECT s.*
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
JOIN tmp_patch_keys k
  ON k.tech_norm=s.tech_norm AND k.bs_id=s.bs_id AND k.lac_dec_final=s.lac_dec_final AND k.wuli_fentong_bs_key=s.wuli_fentong_bs_key;

CREATE TABLE IF NOT EXISTS public."Y_patch_backup_L3_Step30_20251219" AS
SELECT *
FROM public."Y_codex_Layer3_Step30_Master_BS_Library"
WHERE false;

INSERT INTO public."Y_patch_backup_L3_Step30_20251219"
SELECT s.*
FROM tmp_before_step30 s
WHERE NOT EXISTS (
  SELECT 1
  FROM public."Y_patch_backup_L3_Step30_20251219" b
  WHERE b.tech_norm=s.tech_norm AND b.bs_id=s.bs_id AND b.lac_dec_final=s.lac_dec_final AND b.wuli_fentong_bs_key=s.wuli_fentong_bs_key
);

-- 2) Step30 局部重算（点级鲁棒中心点 + 距离阈值剔除漂移点）
WITH
params AS (
  SELECT
    2500.0::double precision AS trim_dist_m,
    1500.0::double precision AS collision_if_p90_dist_m_gt
),
china AS (
  -- 中国粗框（你已确认口径 B：剔除非中国）
  SELECT 73.0::double precision AS lon_min, 135.0::double precision AS lon_max,
         3.0::double precision AS lat_min, 54.0::double precision AS lat_max
),
trusted_lac AS (
  SELECT operator_id_raw, tech_norm, lac_dec
  FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  WHERE is_trusted_lac
),
map_choice_cnt AS (
  SELECT operator_id_raw, tech_norm, cell_id_dec, count(*)::bigint AS lac_choice_cnt
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
  GROUP BY 1,2,3
),
map_best AS (
  SELECT DISTINCT ON (s.operator_id_raw, s.tech_norm, s.cell_id_dec)
    s.operator_id_raw,
    s.tech_norm,
    s.cell_id_dec,
    c.lac_choice_cnt,
    CASE WHEN c.lac_choice_cnt = 1 THEN s.lac_dec END AS lac_dec_from_map
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
  JOIN map_choice_cnt c
    ON s.operator_id_raw=c.operator_id_raw
   AND s.tech_norm=c.tech_norm
   AND s.cell_id_dec=c.cell_id_dec
  ORDER BY
    s.operator_id_raw, s.tech_norm, s.cell_id_dec,
    s.record_count DESC, s.valid_gps_count DESC, s.distinct_device_count DESC, s.active_days DESC, s.lac_dec ASC
),
gps_points_raw AS (
  SELECT
    m.operator_id_raw,
    m.tech_norm,
    m.bs_id,
    m.cell_id_dec,
    m.lac_dec,
    m.lon::double precision AS lon,
    m.lat::double precision AS lat
  FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" m
  JOIN tmp_patch_keys k
    ON k.tech_norm=m.tech_norm
   AND k.bs_id=m.bs_id
  CROSS JOIN china c
  WHERE
    m.is_compliant
    AND m.has_gps
    AND m.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND m.tech_norm IN ('4G','5G')
    AND m.cell_id_dec IS NOT NULL
    AND m.lon::double precision BETWEEN c.lon_min AND c.lon_max
    AND m.lat::double precision BETWEEN c.lat_min AND c.lat_max
),
gps_points_lac_final AS (
  SELECT
    g.*,
    CASE
      WHEN tl.lac_dec IS NOT NULL THEN g.lac_dec
      ELSE mb.lac_dec_from_map
    END AS lac_dec_final
  FROM gps_points_raw g
  LEFT JOIN trusted_lac tl
    ON g.operator_id_raw=tl.operator_id_raw
   AND g.tech_norm=tl.tech_norm
   AND g.lac_dec=tl.lac_dec
  LEFT JOIN map_best mb
    ON g.operator_id_raw=mb.operator_id_raw
   AND g.tech_norm=mb.tech_norm
   AND g.cell_id_dec=mb.cell_id_dec
  WHERE (CASE WHEN tl.lac_dec IS NOT NULL THEN g.lac_dec ELSE mb.lac_dec_from_map END) IS NOT NULL
),
gps_points AS (
  SELECT
    g.*,
    (g.tech_norm || '|' || g.bs_id::text || '|' || g.lac_dec_final::text) AS wuli_fentong_bs_key
  FROM gps_points_lac_final g
  JOIN tmp_patch_keys k
    ON k.tech_norm=g.tech_norm AND k.bs_id=g.bs_id AND k.lac_dec_final=g.lac_dec_final
),
center0 AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY g.lon) AS center_lon0,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY g.lat) AS center_lat0,
    count(*)::bigint AS point_cnt0,
    count(DISTINCT (g.operator_id_raw, g.cell_id_dec))::int AS cell_cnt0
  FROM gps_points g
  GROUP BY 1,2,3,4
),
dist0 AS (
  SELECT
    g.*,
    c.center_lon0,
    c.center_lat0,
    6371000.0 * 2.0 * asin(
      sqrt(
        power(sin(radians(g.lat - c.center_lat0) / 2.0), 2)
        + cos(radians(c.center_lat0)) * cos(radians(g.lat))
          * power(sin(radians(g.lon - c.center_lon0) / 2.0), 2)
      )
    ) AS dist_m0
  FROM gps_points g
  JOIN center0 c
    ON c.tech_norm=g.tech_norm
   AND c.bs_id=g.bs_id
   AND c.lac_dec_final=g.lac_dec_final
   AND c.wuli_fentong_bs_key=g.wuli_fentong_bs_key
),
metric0 AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY dist_m0) AS p50_0,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY dist_m0) AS p90_0,
    max(dist_m0) AS max_0
  FROM dist0
  GROUP BY 1,2,3,4
),
keep_flag AS (
  SELECT
    d.*,
    m.max_0,
    CASE
      WHEN m.max_0 <= p.trim_dist_m THEN true
      ELSE (d.dist_m0 <= p.trim_dist_m)
    END AS is_kept
  FROM dist0 d
  JOIN metric0 m
    ON m.tech_norm=d.tech_norm AND m.bs_id=d.bs_id AND m.lac_dec_final=d.lac_dec_final AND m.wuli_fentong_bs_key=d.wuli_fentong_bs_key
  CROSS JOIN params p
),
kept_stats AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*) filter (where is_kept)::bigint AS kept_point_cnt,
    count(*) filter (where not is_kept)::bigint AS removed_point_cnt,
    count(DISTINCT (operator_id_raw, cell_id_dec)) filter (where is_kept)::int AS kept_cell_cnt
  FROM keep_flag
  GROUP BY 1,2,3,4
),
points_kept_effective AS (
  SELECT
    k.*,
    CASE WHEN s.kept_point_cnt > 0 THEN k.is_kept ELSE true END AS is_kept_eff
  FROM keep_flag k
  JOIN kept_stats s
    ON s.tech_norm=k.tech_norm AND s.bs_id=k.bs_id AND s.lac_dec_final=k.lac_dec_final AND s.wuli_fentong_bs_key=k.wuli_fentong_bs_key
),
center1 AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS bs_center_lon,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS bs_center_lat
  FROM points_kept_effective
  WHERE is_kept_eff
  GROUP BY 1,2,3,4
),
dist1 AS (
  SELECT
    p.tech_norm,
    p.bs_id,
    p.lac_dec_final,
    p.wuli_fentong_bs_key,
    p.operator_id_raw,
    p.cell_id_dec,
    p.lon,
    p.lat,
    c.bs_center_lon,
    c.bs_center_lat,
    6371000.0 * 2.0 * asin(
      sqrt(
        power(sin(radians(p.lat - c.bs_center_lat) / 2.0), 2)
        + cos(radians(c.bs_center_lat)) * cos(radians(p.lat))
          * power(sin(radians(p.lon - c.bs_center_lon) / 2.0), 2)
      )
    ) AS dist_m1
  FROM points_kept_effective p
  JOIN center1 c
    ON c.tech_norm=p.tech_norm AND c.bs_id=p.bs_id AND c.lac_dec_final=p.lac_dec_final AND c.wuli_fentong_bs_key=p.wuli_fentong_bs_key
  WHERE p.is_kept_eff
),
metric1 AS (
  SELECT
    d.tech_norm,
    d.bs_id,
    d.lac_dec_final,
    d.wuli_fentong_bs_key,
    max(c.bs_center_lon) AS bs_center_lon,
    max(c.bs_center_lat) AS bs_center_lat,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY d.dist_m1) AS gps_p50_dist_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY d.dist_m1) AS gps_p90_dist_m,
    max(d.dist_m1) AS gps_max_dist_m
  FROM dist1 d
  JOIN center1 c
    ON c.tech_norm=d.tech_norm AND c.bs_id=d.bs_id AND c.lac_dec_final=d.lac_dec_final AND c.wuli_fentong_bs_key=d.wuli_fentong_bs_key
  GROUP BY 1,2,3,4
),
final AS (
  SELECT
    m1.*,
    ks.kept_cell_cnt,
    ks.kept_point_cnt,
    ks.removed_point_cnt
  FROM metric1 m1
  JOIN kept_stats ks
    ON ks.tech_norm=m1.tech_norm AND ks.bs_id=m1.bs_id AND ks.lac_dec_final=m1.lac_dec_final AND ks.wuli_fentong_bs_key=m1.wuli_fentong_bs_key
)
UPDATE public."Y_codex_Layer3_Step30_Master_BS_Library" s
SET
  gps_valid_cell_cnt = f.kept_cell_cnt,
  gps_valid_point_cnt = f.kept_point_cnt,
  bs_center_lon = f.bs_center_lon,
  bs_center_lat = f.bs_center_lat,
  gps_p50_dist_m = f.gps_p50_dist_m,
  gps_p90_dist_m = f.gps_p90_dist_m,
  gps_max_dist_m = f.gps_max_dist_m,
  outlier_removed_cnt = f.removed_point_cnt,
  gps_valid_level = CASE
    WHEN f.kept_cell_cnt = 0 THEN 'Unusable'
    WHEN f.kept_cell_cnt = 1 THEN 'Risk'
    ELSE 'Usable'
  END,
  is_collision_suspect = CASE
    WHEN f.kept_cell_cnt <= 1 THEN 0
    WHEN COALESCE(s.anomaly_cell_cnt, 0) > 0 THEN 1
    WHEN f.gps_p90_dist_m IS NULL THEN 0
    WHEN f.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN 1
    ELSE 0
  END,
  collision_reason = CASE
    WHEN f.kept_cell_cnt <= 1 THEN NULL
    WHEN COALESCE(s.anomaly_cell_cnt, 0) > 0 AND f.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN E'STEP05_MULTI_LAC_CELL\\073GPS_SCATTER_P90_GT_THRESHOLD'
    WHEN COALESCE(s.anomaly_cell_cnt, 0) > 0 THEN 'STEP05_MULTI_LAC_CELL'
    WHEN f.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN 'GPS_SCATTER_P90_GT_THRESHOLD'
    ELSE NULL
  END
FROM final f
CROSS JOIN params p
WHERE
  s.tech_norm=f.tech_norm
  AND s.bs_id=f.bs_id
  AND s.lac_dec_final=f.lac_dec_final
  AND s.wuli_fentong_bs_key=f.wuli_fentong_bs_key;

-- 3) Step31 局部重算（仅更新这些桶的明细）
WITH
params AS (
  SELECT 1500.0::double precision AS drift_if_dist_m_gt
),
china AS (
  SELECT 73.0::double precision AS lon_min, 135.0::double precision AS lon_max,
         3.0::double precision AS lat_min, 54.0::double precision AS lat_max
)
UPDATE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
SET
  gps_valid_level = bs.gps_valid_level,
  is_collision_suspect = bs.is_collision_suspect,
  is_multi_operator_shared = bs.is_multi_operator_shared,
  shared_operator_list = bs.shared_operator_list,
  shared_operator_cnt = bs.shared_operator_cnt,
  is_from_risk_bs = CASE WHEN bs.gps_valid_level = 'Risk' THEN 1 ELSE 0 END::int,
  gps_dist_to_bs_m = CASE
    WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN NULL::double precision
    WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN NULL::double precision
    WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
    ELSE
      6371000.0 * 2.0 * asin(
        sqrt(
          power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
          + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
            * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
        )
      )
  END,
  gps_status = CASE
    WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
    WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN 'Missing'
    WHEN (
      CASE
        WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
        ELSE
          6371000.0 * 2.0 * asin(
            sqrt(
              power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
              + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
            )
          )
      END
    ) > p.drift_if_dist_m_gt THEN 'Drift'
    ELSE 'Verified'
  END,
  gps_source = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN 'Original_Verified'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level = 'Usable'
    THEN 'Augmented_from_BS'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level = 'Risk'
    THEN 'Augmented_from_Risk_BS'
    ELSE 'Not_Filled'
  END,
  gps_status_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN 'Verified'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level IN ('Usable','Risk')
    THEN 'Verified'
    ELSE 'Missing'
  END,
  lon_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN s.lon_raw
    WHEN bs.bs_center_lon IS NOT NULL AND bs.bs_center_lat IS NOT NULL AND bs.gps_valid_level IN ('Usable','Risk') THEN bs.bs_center_lon
    ELSE s.lon_raw
  END,
  lat_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN s.lat_raw
    WHEN bs.bs_center_lon IS NOT NULL AND bs.bs_center_lat IS NOT NULL AND bs.gps_valid_level IN ('Usable','Risk') THEN bs.bs_center_lat
    ELSE s.lat_raw
  END
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" bs
CROSS JOIN params p
CROSS JOIN china c
JOIN tmp_patch_keys k
  ON k.wuli_fentong_bs_key=s.wuli_fentong_bs_key
WHERE
  bs.wuli_fentong_bs_key = k.wuli_fentong_bs_key
  AND bs.tech_norm = s.tech_norm
  AND bs.bs_id = s.bs_id;

-- 4) COMMENT 同步（避免“outlier_removed_cnt”含义与现状不一致）
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".outlier_removed_cnt
IS 'CN: 中文名=剔除异常GPS点数; 说明=鲁棒中心点算法按距离阈值剔除的漂移/异常 GPS 点数量; EN: Outlier removed GPS point count (trimmed by distance threshold).';

COMMIT;

ANALYZE public."Y_codex_Layer3_Step30_Master_BS_Library";
-- Step31 表很大：本补丁只更新少量桶，通常不强制 ANALYZE；如你后续要跑 Step33/34 或发现执行计划异常，再手工执行：
-- ANALYZE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- 4.1 输出本次补丁的 Step30 前后对比（落表，便于你直接看效果）
CREATE TABLE IF NOT EXISTS public."Y_patch_audit_L3_Step30_PointTrim_20251219" (
  wuli_fentong_bs_key text PRIMARY KEY,
  tech_norm text NOT NULL,
  bs_id bigint NOT NULL,
  lac_dec_final bigint NOT NULL,
  before_gps_valid_cell_cnt int,
  after_gps_valid_cell_cnt int,
  before_gps_valid_point_cnt bigint,
  after_gps_valid_point_cnt bigint,
  before_gps_p50_dist_m double precision,
  after_gps_p50_dist_m double precision,
  before_gps_p90_dist_m double precision,
  after_gps_p90_dist_m double precision,
  before_gps_max_dist_m double precision,
  after_gps_max_dist_m double precision,
  before_outlier_removed_cnt bigint,
  after_outlier_removed_cnt bigint,
  before_is_collision_suspect int,
  after_is_collision_suspect int,
  before_collision_reason text,
  after_collision_reason text,
  created_at timestamp without time zone NOT NULL DEFAULT now()
);

DELETE FROM public."Y_patch_audit_L3_Step30_PointTrim_20251219" a
USING tmp_patch_keys k
WHERE a.wuli_fentong_bs_key = k.wuli_fentong_bs_key;

INSERT INTO public."Y_patch_audit_L3_Step30_PointTrim_20251219" (
  wuli_fentong_bs_key,
  tech_norm,
  bs_id,
  lac_dec_final,
  before_gps_valid_cell_cnt,
  after_gps_valid_cell_cnt,
  before_gps_valid_point_cnt,
  after_gps_valid_point_cnt,
  before_gps_p50_dist_m,
  after_gps_p50_dist_m,
  before_gps_p90_dist_m,
  after_gps_p90_dist_m,
  before_gps_max_dist_m,
  after_gps_max_dist_m,
  before_outlier_removed_cnt,
  after_outlier_removed_cnt,
  before_is_collision_suspect,
  after_is_collision_suspect,
  before_collision_reason,
  after_collision_reason
)
SELECT
  a.wuli_fentong_bs_key,
  a.tech_norm,
  a.bs_id,
  a.lac_dec_final,
  b.gps_valid_cell_cnt AS before_gps_valid_cell_cnt,
  a.gps_valid_cell_cnt AS after_gps_valid_cell_cnt,
  b.gps_valid_point_cnt AS before_gps_valid_point_cnt,
  a.gps_valid_point_cnt AS after_gps_valid_point_cnt,
  b.gps_p50_dist_m AS before_gps_p50_dist_m,
  a.gps_p50_dist_m AS after_gps_p50_dist_m,
  b.gps_p90_dist_m AS before_gps_p90_dist_m,
  a.gps_p90_dist_m AS after_gps_p90_dist_m,
  b.gps_max_dist_m AS before_gps_max_dist_m,
  a.gps_max_dist_m AS after_gps_max_dist_m,
  b.outlier_removed_cnt AS before_outlier_removed_cnt,
  a.outlier_removed_cnt AS after_outlier_removed_cnt,
  b.is_collision_suspect AS before_is_collision_suspect,
  a.is_collision_suspect AS after_is_collision_suspect,
  b.collision_reason AS before_collision_reason,
  a.collision_reason AS after_collision_reason
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" a
JOIN tmp_before_step30 b
  ON b.wuli_fentong_bs_key = a.wuli_fentong_bs_key
JOIN tmp_patch_keys k
  ON k.wuli_fentong_bs_key = a.wuli_fentong_bs_key;

-- 5) 验收建议（执行完补丁后手动跑）
-- 5.1 看补丁桶是否收敛、是否从 collision_suspect 降级
-- select * from public."Y_codex_Layer3_Step30_Master_BS_Library" where wuli_fentong_bs_key in (select wuli_fentong_bs_key from tmp_patch_keys);
--
-- 5.2 只需要刷新 Step32（很快）
-- psql -f lac_enbid_project/Layer_3/sql/32_step32_compare.sql
-- select pass_flag, count(*) from public."Y_codex_Layer3_Step32_Compare" group by 1 order by 2 desc;
