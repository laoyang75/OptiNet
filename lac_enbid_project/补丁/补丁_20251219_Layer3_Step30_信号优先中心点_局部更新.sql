-- 补丁_20251219_Layer3_Step30_信号优先中心点_局部更新.sql
--
-- 目标：
-- - 避免全量重跑 Step30（CTAS 很慢），仅对“疑似系统性偏移/低精度”的少量桶做局部重算：
--   1) Step30：引入“信号优先”的中心点估计（Top50/Top20/Top80% 动态口径）+ 一次距离阈值剔除离群点 + 重算离散度
--   2) Step31：对同一批桶，基于新的 Step30 中心点重新判定 Verified/Drift/Missing，并按既有规则回填 lon_final/lat_final/gps_source
--
-- 你已确认的关键口径：
-- - 剔除的是“具体 GPS 点”，不是 cell
-- - 非中国坐标：不删行，视为 Missing；后续可由基站中心点回填
-- - 无效 RSRP：-110 / -1 / >=0 视为无效（本补丁仅用于“选择中心点用的优质点”时清洗，不强制落表）
--
-- 使用方式（建议 psql 执行整文件）：
--   psql -f lac_enbid_project/补丁/补丁_20251219_Layer3_Step30_信号优先中心点_局部更新.sql
--
-- 你需要做的唯一改动：
--   A) 调整“0) 生成本次要修复的桶清单”的阈值/limit（默认挑“点数>=1000 且 p50/p90 中等偏大”的 TopN）
--   B) 或在“手工追加桶（可选）”里直接指定，例如：('5G', 1398103, 2097200)

SET statement_timeout = 0;

BEGIN;

-- 0) 生成本次要修复的桶清单（落到表里：你可先 SELECT 看名单，再决定要不要继续执行 UPDATE）
CREATE TABLE IF NOT EXISTS public."Y_patch_L3_SignalCenter_WorkKeys_20251219" (
  tech_norm text NOT NULL,
  bs_id bigint NOT NULL,
  lac_dec_final bigint NOT NULL,
  wuli_fentong_bs_key text GENERATED ALWAYS AS (tech_norm || '|' || bs_id::text || '|' || lac_dec_final::text) STORED,
  select_reason text NOT NULL,
  gps_valid_level text,
  gps_valid_cell_cnt int,
  gps_valid_point_cnt bigint,
  gps_p50_dist_m double precision,
  gps_p90_dist_m double precision,
  gps_max_dist_m double precision,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (tech_norm, bs_id, lac_dec_final)
);

TRUNCATE public."Y_patch_L3_SignalCenter_WorkKeys_20251219";

WITH patch_params AS (
  SELECT
    1000::bigint AS min_point_cnt,
    500.0::double precision AS p50_m_ge,
    900.0::double precision AS p50_m_le,
    900.0::double precision AS p90_m_ge,
    1500.0::double precision AS p90_m_le,
    4000.0::double precision AS max_m_le,
    20::int AS limit_keys
)
INSERT INTO public."Y_patch_L3_SignalCenter_WorkKeys_20251219" (
  tech_norm,
  bs_id,
  lac_dec_final,
  select_reason,
  gps_valid_level,
  gps_valid_cell_cnt,
  gps_valid_point_cnt,
  gps_p50_dist_m,
  gps_p90_dist_m,
  gps_max_dist_m
)
SELECT
  s.tech_norm,
  s.bs_id,
  s.lac_dec_final,
  format(
    'AUTO:point>=%s,p50=%s~%s,p90=%s~%s,max<=%s',
    p.min_point_cnt::text,
    p.p50_m_ge::text,
    p.p50_m_le::text,
    p.p90_m_ge::text,
    p.p90_m_le::text,
    p.max_m_le::text
  ) AS select_reason,
  s.gps_valid_level,
  s.gps_valid_cell_cnt,
  s.gps_valid_point_cnt,
  s.gps_p50_dist_m,
  s.gps_p90_dist_m,
  s.gps_max_dist_m
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
CROSS JOIN patch_params p
WHERE
  s.lac_dec_final IS NOT NULL
  AND s.gps_valid_level = 'Usable'
  AND COALESCE(s.gps_valid_point_cnt, 0) >= p.min_point_cnt
  AND s.gps_p50_dist_m IS NOT NULL
  AND s.gps_p90_dist_m IS NOT NULL
  AND s.gps_max_dist_m IS NOT NULL
  AND s.gps_p50_dist_m BETWEEN p.p50_m_ge AND p.p50_m_le
  AND s.gps_p90_dist_m BETWEEN p.p90_m_ge AND p.p90_m_le
  AND s.gps_max_dist_m <= p.max_m_le
ORDER BY s.gps_p50_dist_m DESC NULLS LAST, s.gps_valid_point_cnt DESC
LIMIT (SELECT limit_keys FROM patch_params);

-- 手工追加桶（可选）
-- INSERT INTO public."Y_patch_L3_SignalCenter_WorkKeys_20251219" (tech_norm, bs_id, lac_dec_final, select_reason)
-- VALUES ('5G', 1398103, 2097200, 'MANUAL:from_user')
-- ON CONFLICT (tech_norm, bs_id, lac_dec_final) DO NOTHING;

SELECT count(*) AS patch_key_cnt
FROM public."Y_patch_L3_SignalCenter_WorkKeys_20251219";

SELECT
  tech_norm,
  bs_id,
  lac_dec_final,
  wuli_fentong_bs_key,
  gps_valid_cell_cnt,
  gps_valid_point_cnt,
  gps_p50_dist_m,
  gps_p90_dist_m,
  gps_max_dist_m,
  select_reason
FROM public."Y_patch_L3_SignalCenter_WorkKeys_20251219"
ORDER BY gps_p50_dist_m DESC NULLS LAST
LIMIT 20;

CREATE TEMP TABLE tmp_patch_keys AS
SELECT
  tech_norm,
  bs_id,
  lac_dec_final,
  wuli_fentong_bs_key
FROM public."Y_patch_L3_SignalCenter_WorkKeys_20251219";

-- 1) Step30 备份（只备份本次要更新的桶）
CREATE TABLE IF NOT EXISTS public."Y_patch_backup_L3_Step30_SignalCenter_20251219" AS
SELECT *
FROM public."Y_codex_Layer3_Step30_Master_BS_Library"
WHERE false;

INSERT INTO public."Y_patch_backup_L3_Step30_SignalCenter_20251219"
SELECT s.*
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
JOIN tmp_patch_keys k
  ON k.wuli_fentong_bs_key=s.wuli_fentong_bs_key
WHERE NOT EXISTS (
  SELECT 1
  FROM public."Y_patch_backup_L3_Step30_SignalCenter_20251219" b
  WHERE b.wuli_fentong_bs_key=s.wuli_fentong_bs_key
);

-- 2) Step30 局部重算（信号优先中心点 + 一次距离剔除离群点 + 重算）
WITH
params AS (
  SELECT
    2500.0::double precision AS trim_dist_m,
    1500.0::double precision AS collision_if_p90_dist_m_gt,
    1500.0::double precision AS drift_if_dist_m_gt,
    5::int AS min_center_point_cnt
),
china AS (
  SELECT 73.0::double precision AS lon_min, 135.0::double precision AS lon_max,
         3.0::double precision AS lat_min, 54.0::double precision AS lat_max
),
points_raw AS (
  -- 用 Step31 的原始坐标作为“可复算点集”（避免再走一遍 Step02->LAC 归一逻辑）
  SELECT
    s.wuli_fentong_bs_key,
    s.operator_id_raw,
    s.cell_id_dec,
    s.lon_raw::double precision AS lon,
    s.lat_raw::double precision AS lat,
    CASE
      WHEN s.sig_rsrp IN (-110, -1) OR s.sig_rsrp >= 0 THEN NULL::int
      ELSE s.sig_rsrp
    END AS sig_rsrp_clean
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
  JOIN tmp_patch_keys k
    ON k.wuli_fentong_bs_key=s.wuli_fentong_bs_key
  CROSS JOIN china c
  WHERE
    s.lon_raw IS NOT NULL
    AND s.lat_raw IS NOT NULL
    AND NOT (s.lon_raw = 0 AND s.lat_raw = 0)
    AND s.lon_raw::double precision BETWEEN c.lon_min AND c.lon_max
    AND s.lat_raw::double precision BETWEEN c.lat_min AND c.lat_max
    AND s.cell_id_dec IS NOT NULL
),
sig_meta AS (
  SELECT
    wuli_fentong_bs_key,
    count(*) filter (where sig_rsrp_clean is not null)::int AS sig_valid_cnt
  FROM points_raw
  GROUP BY 1
),
sig_policy AS (
  SELECT
    m.wuli_fentong_bs_key,
    m.sig_valid_cnt,
    CASE
      WHEN m.sig_valid_cnt >= 50 THEN 'TOP50'
      WHEN m.sig_valid_cnt >= 20 THEN 'TOP20'
      WHEN m.sig_valid_cnt >= 1 THEN 'TOP80PCT'
      ELSE 'ALL'
    END AS sig_keep_mode,
    CASE
      WHEN m.sig_valid_cnt >= 50 THEN (1.0 - (50.0 / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= 20 THEN (1.0 - (20.0 / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= 1 THEN 0.2
      ELSE NULL::double precision
    END AS keep_percentile
  FROM sig_meta m
),
sig_threshold AS (
  SELECT
    p.wuli_fentong_bs_key,
    p.sig_valid_cnt,
    p.sig_keep_mode,
    p.keep_percentile,
    CASE
      WHEN p.keep_percentile IS NULL THEN NULL::double precision
      ELSE percentile_cont(p.keep_percentile) WITHIN GROUP (ORDER BY pr.sig_rsrp_clean)
    END AS sig_rsrp_threshold
  FROM sig_policy p
  LEFT JOIN points_raw pr
    ON pr.wuli_fentong_bs_key=p.wuli_fentong_bs_key
   AND pr.sig_rsrp_clean IS NOT NULL
  GROUP BY 1,2,3,4
),
seed_points AS (
  SELECT
    pr.*,
    st.sig_valid_cnt,
    st.sig_keep_mode,
    st.sig_rsrp_threshold,
    CASE
      WHEN st.sig_keep_mode = 'ALL' THEN true
      WHEN st.sig_rsrp_threshold IS NULL THEN false
      ELSE (pr.sig_rsrp_clean IS NOT NULL AND pr.sig_rsrp_clean >= st.sig_rsrp_threshold)
    END AS is_in_signal_seed
  FROM points_raw pr
  JOIN sig_threshold st
    ON st.wuli_fentong_bs_key=pr.wuli_fentong_bs_key
),
seed_center_sig AS (
  SELECT
    wuli_fentong_bs_key,
    count(*)::int AS seed_cnt,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS seed_lon,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS seed_lat
  FROM seed_points
  WHERE is_in_signal_seed
  GROUP BY 1
),
seed_center_all AS (
  SELECT
    wuli_fentong_bs_key,
    count(*)::int AS all_cnt,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS seed_lon_all,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS seed_lat_all
  FROM seed_points
  GROUP BY 1
),
seed_center_final AS (
  SELECT
    a.wuli_fentong_bs_key,
    coalesce(s.seed_cnt, 0) AS seed_cnt,
    a.all_cnt,
    CASE WHEN coalesce(s.seed_cnt, 0) >= (SELECT min_center_point_cnt FROM params) THEN s.seed_lon ELSE a.seed_lon_all END AS seed_lon,
    CASE WHEN coalesce(s.seed_cnt, 0) >= (SELECT min_center_point_cnt FROM params) THEN s.seed_lat ELSE a.seed_lat_all END AS seed_lat
  FROM seed_center_all a
  LEFT JOIN seed_center_sig s USING (wuli_fentong_bs_key)
),
point_dist_seed AS (
  SELECT
    sp.*,
    sc.seed_lon,
    sc.seed_lat,
    6371000.0 * 2.0 * asin(
      sqrt(
        power(sin(radians(sp.lat - sc.seed_lat) / 2.0), 2)
        + cos(radians(sc.seed_lat)) * cos(radians(sp.lat))
          * power(sin(radians(sp.lon - sc.seed_lon) / 2.0), 2)
      )
    ) AS dist_seed_m
  FROM seed_points sp
  JOIN seed_center_final sc USING (wuli_fentong_bs_key)
),
max_seed AS (
  SELECT wuli_fentong_bs_key, max(dist_seed_m) AS max_dist_seed_m
  FROM point_dist_seed
  GROUP BY 1
),
kept_flag AS (
  SELECT
    d.*,
    CASE
      WHEN ms.max_dist_seed_m IS NULL THEN true
      WHEN ms.max_dist_seed_m <= (SELECT trim_dist_m FROM params) THEN true
      ELSE (d.dist_seed_m <= (SELECT trim_dist_m FROM params))
    END AS is_kept
  FROM point_dist_seed d
  JOIN max_seed ms USING (wuli_fentong_bs_key)
),
kept_points AS (
  SELECT *
  FROM kept_flag
  WHERE is_kept
),
center_final_sig AS (
  SELECT
    wuli_fentong_bs_key,
    count(*)::int AS kept_sig_cnt,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon_sig,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat_sig
  FROM kept_points
  WHERE is_in_signal_seed
  GROUP BY 1
),
center_final_all AS (
  SELECT
    wuli_fentong_bs_key,
    count(*)::int AS kept_all_cnt,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon_all,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat_all
  FROM kept_points
  GROUP BY 1
),
center_final AS (
  SELECT
    a.wuli_fentong_bs_key,
    coalesce(s.kept_sig_cnt, 0) AS kept_sig_cnt,
    a.kept_all_cnt,
    CASE WHEN coalesce(s.kept_sig_cnt, 0) >= (SELECT min_center_point_cnt FROM params) THEN s.center_lon_sig ELSE a.center_lon_all END AS bs_center_lon,
    CASE WHEN coalesce(s.kept_sig_cnt, 0) >= (SELECT min_center_point_cnt FROM params) THEN s.center_lat_sig ELSE a.center_lat_all END AS bs_center_lat
  FROM center_final_all a
  LEFT JOIN center_final_sig s USING (wuli_fentong_bs_key)
),
dist_final AS (
  SELECT
    k.wuli_fentong_bs_key,
    6371000.0 * 2.0 * asin(
      sqrt(
        power(sin(radians(k.lat - c.bs_center_lat) / 2.0), 2)
        + cos(radians(c.bs_center_lat)) * cos(radians(k.lat))
          * power(sin(radians(k.lon - c.bs_center_lon) / 2.0), 2)
      )
    ) AS dist_m
  FROM kept_points k
  JOIN center_final c USING (wuli_fentong_bs_key)
),
metric_final AS (
  SELECT
    d.wuli_fentong_bs_key,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY d.dist_m) AS gps_p50_dist_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY d.dist_m) AS gps_p90_dist_m,
    max(d.dist_m) AS gps_max_dist_m
  FROM dist_final d
  GROUP BY 1
),
kept_stats AS (
  SELECT
    wuli_fentong_bs_key,
    count(*)::bigint AS kept_point_cnt,
    count(DISTINCT (operator_id_raw, cell_id_dec))::int AS kept_cell_cnt
  FROM kept_points
  GROUP BY 1
),
outlier_cnt AS (
  SELECT
    wuli_fentong_bs_key,
    count(*) filter (where NOT is_kept)::int AS outlier_removed_cnt
  FROM kept_flag
  GROUP BY 1
),
upd AS (
  SELECT
    k.wuli_fentong_bs_key,
    ks.kept_cell_cnt,
    ks.kept_point_cnt,
    c.bs_center_lon,
    c.bs_center_lat,
    m.gps_p50_dist_m,
    m.gps_p90_dist_m,
    m.gps_max_dist_m,
    oc.outlier_removed_cnt
  FROM tmp_patch_keys k
  JOIN kept_stats ks USING (wuli_fentong_bs_key)
  JOIN center_final c USING (wuli_fentong_bs_key)
  JOIN metric_final m USING (wuli_fentong_bs_key)
  JOIN outlier_cnt oc USING (wuli_fentong_bs_key)
)
UPDATE public."Y_codex_Layer3_Step30_Master_BS_Library" t
SET
  gps_valid_cell_cnt = u.kept_cell_cnt,
  gps_valid_point_cnt = u.kept_point_cnt,
  gps_valid_level = CASE
    WHEN u.kept_cell_cnt = 0 THEN 'Unusable'
    WHEN u.kept_cell_cnt = 1 THEN 'Risk'
    ELSE 'Usable'
  END,
  bs_center_lon = CASE WHEN u.kept_cell_cnt = 0 THEN NULL ELSE u.bs_center_lon END,
  bs_center_lat = CASE WHEN u.kept_cell_cnt = 0 THEN NULL ELSE u.bs_center_lat END,
  gps_p50_dist_m = CASE WHEN u.kept_cell_cnt = 0 THEN NULL ELSE u.gps_p50_dist_m END,
  gps_p90_dist_m = CASE WHEN u.kept_cell_cnt = 0 THEN NULL ELSE u.gps_p90_dist_m END,
  gps_max_dist_m = CASE WHEN u.kept_cell_cnt = 0 THEN NULL ELSE u.gps_max_dist_m END,
  outlier_removed_cnt = coalesce(u.outlier_removed_cnt, 0),
  is_collision_suspect = CASE
    WHEN u.kept_cell_cnt <= 1 THEN 0
    WHEN coalesce(t.anomaly_cell_cnt, 0) > 0 THEN 1
    WHEN u.gps_p90_dist_m IS NULL THEN 0
    WHEN u.gps_p90_dist_m > (SELECT collision_if_p90_dist_m_gt FROM params) THEN 1
    ELSE 0
  END,
  collision_reason = CASE
    WHEN u.kept_cell_cnt <= 1 THEN NULL
    WHEN coalesce(t.anomaly_cell_cnt, 0) > 0 AND u.gps_p90_dist_m > (SELECT collision_if_p90_dist_m_gt FROM params) THEN E'STEP05_MULTI_LAC_CELL\\073GPS_SCATTER_P90_GT_THRESHOLD'
    WHEN coalesce(t.anomaly_cell_cnt, 0) > 0 THEN 'STEP05_MULTI_LAC_CELL'
    WHEN u.gps_p90_dist_m > (SELECT collision_if_p90_dist_m_gt FROM params) THEN 'GPS_SCATTER_P90_GT_THRESHOLD'
    ELSE NULL
  END
FROM upd u
WHERE t.wuli_fentong_bs_key = u.wuli_fentong_bs_key;

-- 3) Step31 局部更新（基于新的 Step30 中心点重新判定 drift/回填）
WITH
params AS (
  SELECT 1500.0::double precision AS drift_if_dist_m_gt
),
bs AS (
  SELECT
    b.wuli_fentong_bs_key,
    b.bs_center_lon,
    b.bs_center_lat,
    b.gps_valid_level,
    b.is_collision_suspect,
    b.gps_p50_dist_m AS bs_gps_p50_dist_m,
    b.gps_valid_point_cnt AS bs_gps_valid_point_cnt,
    b.anomaly_cell_cnt AS bs_anomaly_cell_cnt,
    b.is_multi_operator_shared,
    b.shared_operator_list,
    b.shared_operator_cnt
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library" b
  JOIN tmp_patch_keys k USING (wuli_fentong_bs_key)
),
recalc AS (
  SELECT
    s.src_seq_id,
    bs.gps_valid_level,
    bs.is_collision_suspect,
    bs.is_multi_operator_shared,
    bs.shared_operator_list,
    bs.shared_operator_cnt,
    bs.bs_center_lon,
    bs.bs_center_lat,
    bs.bs_gps_p50_dist_m,
    bs.bs_gps_valid_point_cnt,
    bs.bs_anomaly_cell_cnt,
    CASE
      WHEN s.lon_raw IS NOT NULL AND s.lat_raw IS NOT NULL
       AND s.lon_raw BETWEEN 73.0 AND 135.0
       AND s.lat_raw BETWEEN 3.0 AND 54.0
      THEN true
      ELSE false
    END AS gps_in_china,
    CASE
      WHEN s.lon_raw IS NOT NULL AND s.lat_raw IS NOT NULL
       AND s.lon_raw BETWEEN 73.0 AND 135.0
       AND s.lat_raw BETWEEN 3.0 AND 54.0
       AND bs.bs_center_lon IS NOT NULL AND bs.bs_center_lat IS NOT NULL
      THEN
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
            + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
              * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
          )
        )
      ELSE NULL::double precision
    END AS gps_dist_to_bs_m,
    CASE
      WHEN bs.is_collision_suspect = 1
       AND bs.gps_valid_level = 'Usable'
       AND coalesce(bs.bs_anomaly_cell_cnt, 0) = 0
       AND coalesce(bs.bs_gps_valid_point_cnt, 0) >= 50
       AND coalesce(bs.bs_gps_p50_dist_m, 0) >= 5000
      THEN true
      ELSE false
    END AS is_severe_collision
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
  JOIN bs USING (wuli_fentong_bs_key)
),
classified AS (
  SELECT
    r.*,
    CASE
      WHEN r.gps_in_china IS NOT TRUE THEN 'Missing'
      WHEN r.gps_dist_to_bs_m IS NOT NULL AND r.gps_dist_to_bs_m > (SELECT drift_if_dist_m_gt FROM params) THEN 'Drift'
      ELSE 'Verified'
    END AS gps_status
  FROM recalc r
),
fixed AS (
  SELECT
    c.src_seq_id,
    c.gps_valid_level,
    c.is_collision_suspect,
    c.is_multi_operator_shared,
    c.shared_operator_list,
    c.shared_operator_cnt,
    c.gps_dist_to_bs_m,
    c.gps_status,
    CASE
      WHEN c.gps_valid_level = 'Risk' THEN 1
      ELSE 0
    END::int AS is_from_risk_bs,
    CASE
      WHEN c.gps_status = 'Verified' THEN s.lon_raw
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level IN ('Usable','Risk')
      THEN c.bs_center_lon
      ELSE s.lon_raw
    END AS lon_final,
    CASE
      WHEN c.gps_status = 'Verified' THEN s.lat_raw
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level IN ('Usable','Risk')
      THEN c.bs_center_lat
      ELSE s.lat_raw
    END AS lat_final,
    CASE
      WHEN c.gps_status = 'Verified' THEN 'Original_Verified'
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level = 'Usable'
      THEN 'Augmented_from_BS'
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level = 'Risk'
      THEN 'Augmented_from_Risk_BS'
      ELSE 'Not_Filled'
    END AS gps_source,
    CASE
      WHEN c.gps_status = 'Verified' THEN 'Verified'
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level IN ('Usable','Risk')
      THEN 'Verified'
      ELSE 'Missing'
    END AS gps_status_final
  FROM classified c
  JOIN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
    ON s.src_seq_id=c.src_seq_id
)
UPDATE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
SET
  gps_valid_level = f.gps_valid_level,
  is_collision_suspect = f.is_collision_suspect,
  is_multi_operator_shared = f.is_multi_operator_shared,
  shared_operator_list = f.shared_operator_list,
  shared_operator_cnt = f.shared_operator_cnt,
  gps_dist_to_bs_m = f.gps_dist_to_bs_m,
  gps_status = f.gps_status,
  gps_status_final = f.gps_status_final,
  gps_source = f.gps_source,
  is_from_risk_bs = f.is_from_risk_bs,
  lon_final = f.lon_final,
  lat_final = f.lat_final
FROM fixed f
WHERE s.src_seq_id = f.src_seq_id;

COMMIT;

-- 建议你最后跑一次 Step32（很快）刷新 WARN：
--   psql -f lac_enbid_project/Layer_3/sql/32_step32_compare.sql

