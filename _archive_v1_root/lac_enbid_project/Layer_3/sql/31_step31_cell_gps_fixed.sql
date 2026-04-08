-- Layer_3 Step31：按基站中心点回填/纠偏后的明细库（保留回溯字段与来源标记）
-- 输入依赖（Layer_2/3 冻结）：
--   - public."Y_codex_Layer2_Step06_L0_Lac_Filtered"（可信明细库，作为要修正的输入）
--   - public."Y_codex_Layer3_Step30_Master_BS_Library"（基站主库：中心点 + gps_valid_level）
--
-- 输出：
--   - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"（TABLE）
--
-- 回填原则（必须）：
-- - gps_status=Verified：不覆盖原值（gps_source=Original_Verified）
-- - gps_status in (Missing,Drift)：
--   - bs.gps_valid_level=Usable：允许回填中心点（gps_source=Augmented_from_BS）
--   - bs.gps_valid_level=Risk：允许回填，但必须 is_from_risk_bs=1（gps_source=Augmented_from_Risk_BS）
--   - Unusable 或中心点为空：不回填（gps_source=Not_Filled）
--
-- 口径补强（本轮新增，用户确认）：
-- - “非中国境内”的原始 GPS 视为无效：直接按 Missing 处理，后续按基站中心点补齐。
-- - 硬过滤：bs_id=0 / cell_id_dec=0 视为非法占位（不应出现），直接丢弃（避免污染后续画像与映射表）。

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

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

CREATE TABLE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw,

    -- Drift 判定阈值（米）：本轮默认值，后续按分布评估迭代
    1500.0::double precision AS drift_if_dist_m_gt
),
base AS (
  SELECT
    t.*,
    -- 追溯字段（等价：Step06 透传了 Step00 的 seq_id/"记录id"）
    t.seq_id AS src_seq_id,
    t."记录id" AS src_record_id,
    (t.tech_norm || '|' || t.bs_id::text || '|' || t.lac_dec_final::text) AS wuli_fentong_bs_key
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
  CROSS JOIN params p
  WHERE
    t.tech_norm IN ('4G','5G')
    AND t.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND t.bs_id IS NOT NULL
    AND t.bs_id <> 0
    AND t.cell_id_dec IS NOT NULL
    AND t.cell_id_dec <> 0
    AND t.lac_dec_final IS NOT NULL
    AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
),
joined AS (
  SELECT
    b.*,
    bs.gps_valid_level,
    bs.bs_center_lon,
    bs.bs_center_lat,
    bs.is_collision_suspect,
    bs.gps_p50_dist_m AS bs_gps_p50_dist_m,
    bs.gps_valid_point_cnt AS bs_gps_valid_point_cnt,
    bs.anomaly_cell_cnt AS bs_anomaly_cell_cnt,
    bs.is_multi_operator_shared,
    bs.shared_operator_list,
    bs.shared_operator_cnt
  FROM base b
  LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" bs
    ON bs.tech_norm=b.tech_norm
   AND bs.bs_id=b.bs_id
   AND bs.wuli_fentong_bs_key=b.wuli_fentong_bs_key
),
dist_calc AS (
  SELECT
    j.*,
    -- 中国境内坐标判定（粗框）：避免跨洲/越界坐标污染 drift 判定与后续计算
    CASE
      WHEN j.has_gps IS NOT TRUE THEN false
      WHEN j.lon IS NULL OR j.lat IS NULL THEN false
      WHEN j.lon::double precision BETWEEN 73.0 AND 135.0
       AND j.lat::double precision BETWEEN 3.0 AND 54.0
      THEN true
      ELSE false
    END AS gps_in_china,
    CASE
      WHEN (j.has_gps AND (j.lon::double precision BETWEEN 73.0 AND 135.0) AND (j.lat::double precision BETWEEN 3.0 AND 54.0))
       AND j.bs_center_lon IS NOT NULL AND j.bs_center_lat IS NOT NULL THEN
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(j.lat - j.bs_center_lat) / 2.0), 2)
            + cos(radians(j.bs_center_lat)) * cos(radians(j.lat))
              * power(sin(radians(j.lon - j.bs_center_lon) / 2.0), 2)
          )
        )
      ELSE NULL::double precision
    END AS gps_dist_to_bs_m
  FROM joined j
),
classified AS (
  SELECT
    d.*,
    CASE
      WHEN d.is_collision_suspect = 1
       AND d.gps_valid_level = 'Usable'
       AND COALESCE(d.bs_anomaly_cell_cnt, 0) = 0
       AND COALESCE(d.bs_gps_valid_point_cnt, 0) >= 50
       AND COALESCE(d.bs_gps_p50_dist_m, 0) >= 5000
      THEN true
      ELSE false
    END AS is_severe_collision,
    CASE
      WHEN d.has_gps IS NOT TRUE THEN 'Missing'
      WHEN d.gps_in_china IS NOT TRUE THEN 'Missing'
      WHEN d.gps_dist_to_bs_m IS NOT NULL AND d.gps_dist_to_bs_m > p.drift_if_dist_m_gt THEN 'Drift'
      ELSE 'Verified'
    END AS gps_status,
    CASE
      WHEN d.gps_valid_level = 'Risk' THEN 1
      ELSE 0
    END::int AS is_from_risk_bs
  FROM dist_calc d
  CROSS JOIN params p
),
fixed AS (
  SELECT
    c.*,

    -- 原始经纬度（用于回溯/对比）
    -- 注意：Step06 本身已有字段 `lon_raw/lat_raw`，这里若仍命名为 `lon_raw/lat_raw`
    -- 会导致 CTE 输出列重名，从而在最终 SELECT 处触发“字段关联不明确”。
    c.lon AS lon_before_fix,
    c.lat AS lat_before_fix,

    -- 最终经纬度
    CASE
      WHEN c.gps_status = 'Verified' THEN c.lon
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level IN ('Usable','Risk')
      THEN c.bs_center_lon
      ELSE c.lon
    END AS lon_final,
    CASE
      WHEN c.gps_status = 'Verified' THEN c.lat
      WHEN c.gps_status IN ('Missing','Drift')
       AND c.is_severe_collision IS NOT TRUE
       AND c.bs_center_lon IS NOT NULL
       AND c.bs_center_lat IS NOT NULL
       AND c.gps_valid_level IN ('Usable','Risk')
      THEN c.bs_center_lat
      ELSE c.lat
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
)
SELECT
  -- 必须可追溯字段
  src_seq_id,
  src_record_id,

  -- 关键键（用于下游分组/画像）
  operator_id_raw,
  operator_group_hint,
  tech_norm,
  bs_id,
  sector_id,
  cell_id_dec,
  lac_dec_final,
  wuli_fentong_bs_key,

  -- GPS 修正
  gps_status,
  gps_status_final,
  gps_source,
  is_from_risk_bs,
  gps_dist_to_bs_m,
  lon_before_fix AS lon_raw,
  lat_before_fix AS lat_raw,
  lon_final,
  lat_final,

  -- 基站风险/共建信息（用于评估与画像）
  gps_valid_level,
  is_collision_suspect,
  is_multi_operator_shared,
  shared_operator_list,
  shared_operator_cnt,

  -- 时间口径
  ts_std,
  report_date,

  -- 信号字段（透传，后续 Step33 做简单补齐）
  CASE
    WHEN sig_rsrp IN (-110, -1) OR sig_rsrp >= 0 THEN NULL
    ELSE sig_rsrp
  END AS sig_rsrp,
  sig_rsrq,
  sig_sinr,
  sig_rssi,
  sig_dbm,
  sig_asu_level,
  sig_level,
  sig_ss,

  -- 其它透传字段（便于回溯）
  parsed_from,
  match_status,
  "数据来源",
  "北京来源",
  did,
  ip,
  sdk_ver,
  brand,
  model,
  oaid
FROM fixed;

ANALYZE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";
