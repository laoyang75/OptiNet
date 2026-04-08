-- Layer_3 交付表（最终实体表）
-- 目标：
-- 1) BS 聚合画像表：按 operator_id_raw + tech_norm + bs_id + lac_dec_final 聚合
--    输出：LAC 十六进制、设备量(did2)、上报量、cell 数量、GPS 中心/范围/离散度、共建/多运营商等
-- 2) cell -> BS 映射表：按 operator_id_raw + tech_norm + cell_id_dec 唯一映射到 (bs_id, lac_dec_final)
--
-- 依赖（已由 Step30~34 产出）：
-- - public."Y_codex_Layer3_Step30_Master_BS_Library"
-- - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"

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

-- ============================================================================
-- A) BS 聚合画像表
-- ============================================================================

DROP TABLE IF EXISTS public."Y_codex_Layer3_Final_BS_Profile";

CREATE TABLE public."Y_codex_Layer3_Final_BS_Profile" AS
WITH
base AS (
  SELECT
    operator_id_raw,
    operator_group_hint,
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    did,
    oaid,
    cell_id_dec,
    report_date,
    ts_std,
    gps_status,
    gps_source,
    lon_raw,
    lat_raw
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
  WHERE
    operator_id_raw IS NOT NULL
    AND tech_norm IS NOT NULL
    AND bs_id IS NOT NULL
    AND bs_id <> 0
    AND lac_dec_final IS NOT NULL
    AND wuli_fentong_bs_key IS NOT NULL
    AND cell_id_dec IS NOT NULL
    AND cell_id_dec <> 0
),
base2 AS (
  SELECT
    b.*,
    COALESCE(NULLIF(b.did, ''), NULLIF(b.oaid, '')) AS did2
  FROM base b
),
agg AS (
  SELECT
    operator_id_raw,
    max(operator_group_hint) AS operator_group_hint,
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*)::bigint AS report_cnt,
    count(DISTINCT did)::bigint AS device_cnt_did,
    count(DISTINCT did2)::bigint AS device_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT report_date)::int AS active_days,
    min(ts_std) AS first_seen_ts,
    max(ts_std) AS last_seen_ts,
    count(*) FILTER (WHERE gps_status='Verified')::bigint AS gps_verified_row_cnt,
    count(*) FILTER (WHERE gps_source='Augmented_from_BS')::bigint AS gps_filled_from_usable_bs_cnt,
    count(*) FILTER (WHERE gps_source='Augmented_from_Risk_BS')::bigint AS gps_filled_from_risk_bs_cnt,
    count(*) FILTER (WHERE gps_status='Drift')::bigint AS gps_drift_row_cnt,
    min(lon_raw) FILTER (WHERE gps_status='Verified') AS lon_raw_min,
    max(lon_raw) FILTER (WHERE gps_status='Verified') AS lon_raw_max,
    min(lat_raw) FILTER (WHERE gps_status='Verified') AS lat_raw_min,
    max(lat_raw) FILTER (WHERE gps_status='Verified') AS lat_raw_max
  FROM base2
  GROUP BY 1,3,4,5,6
),
joined AS (
  SELECT
    a.*,
    s.gps_valid_level,
    s.gps_valid_cell_cnt AS gps_valid_cell_cnt_verified_sample,
    s.gps_valid_point_cnt AS gps_valid_point_cnt_verified_sample,
    s.bs_center_lon,
    s.bs_center_lat,
    s.gps_p50_dist_m,
    s.gps_p90_dist_m,
    s.gps_max_dist_m,
    s.is_collision_suspect,
    s.collision_reason,
    s.anomaly_cell_cnt,
    s.is_multi_operator_shared,
    s.shared_operator_cnt,
    s.shared_operator_list,
    s.first_seen_ts AS bs_first_seen_ts,
    s.last_seen_ts AS bs_last_seen_ts,
    s.active_days AS bs_active_days
  FROM agg a
  LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" s
    ON s.wuli_fentong_bs_key=a.wuli_fentong_bs_key
)
SELECT
  operator_id_raw,
  operator_group_hint,
  tech_norm,
  bs_id,
  upper(to_hex(bs_id::bigint)) AS bs_id_hex,
  lac_dec_final,
  upper(to_hex(lac_dec_final::bigint)) AS lac_hex,
  wuli_fentong_bs_key,

  device_cnt,
  device_cnt_did,
  report_cnt,
  cell_cnt,
  active_days,
  first_seen_ts,
  last_seen_ts,

  -- Step30（站级）画像
  gps_valid_level,
  bs_center_lon,
  bs_center_lat,
  gps_p50_dist_m,
  gps_p90_dist_m,
  gps_max_dist_m,
  is_collision_suspect,
  collision_reason,
  anomaly_cell_cnt,

  -- 多运营商/共建
  is_multi_operator_shared,
  shared_operator_cnt,
  shared_operator_list,

  -- 站级（Verified GPS 原始点）粗范围：bbox + 近似对角线（米）
  lon_raw_min,
  lon_raw_max,
  lat_raw_min,
  lat_raw_max,
  CASE
    WHEN lon_raw_min IS NULL OR lon_raw_max IS NULL OR lat_raw_min IS NULL OR lat_raw_max IS NULL THEN NULL::double precision
    ELSE sqrt(
      power(((lon_raw_max - lon_raw_min) * cos(radians((lat_raw_max + lat_raw_min) / 2.0)) * 111320.0), 2)
      + power(((lat_raw_max - lat_raw_min) * 110540.0), 2)
    )
  END AS gps_bbox_diag_m,

  -- 明细侧补齐质量画像（行级）
  gps_verified_row_cnt,
  gps_drift_row_cnt,
  gps_filled_from_usable_bs_cnt,
  gps_filled_from_risk_bs_cnt,

  -- 对齐信息（来自 Step30 的覆盖时间画像）
  bs_first_seen_ts,
  bs_last_seen_ts,
  bs_active_days,
  gps_valid_cell_cnt_verified_sample,
  gps_valid_point_cnt_verified_sample
FROM joined;

CREATE UNIQUE INDEX IF NOT EXISTS idx_layer3_final_bs_profile_pk
  ON public."Y_codex_Layer3_Final_BS_Profile"(operator_id_raw, tech_norm, bs_id, lac_dec_final);

CREATE INDEX IF NOT EXISTS idx_layer3_final_bs_profile_key
  ON public."Y_codex_Layer3_Final_BS_Profile"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Final_BS_Profile";

-- ============================================================================
-- B) cell -> BS 映射表
-- ============================================================================

DROP TABLE IF EXISTS public."Y_codex_Layer3_Final_Cell_BS_Map";

CREATE TABLE public."Y_codex_Layer3_Final_Cell_BS_Map" AS
WITH
base AS (
  SELECT
    operator_id_raw,
    operator_group_hint,
    tech_norm,
    cell_id_dec,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    did,
    oaid,
    report_date,
    ts_std
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
  WHERE
    operator_id_raw IS NOT NULL
    AND tech_norm IS NOT NULL
    AND cell_id_dec IS NOT NULL
    AND cell_id_dec <> 0
    AND bs_id IS NOT NULL
    AND bs_id <> 0
    AND lac_dec_final IS NOT NULL
    AND wuli_fentong_bs_key IS NOT NULL
),
base2 AS (
  SELECT
    b.*,
    COALESCE(NULLIF(b.did, ''), NULLIF(b.oaid, '')) AS did2
  FROM base b
),
mapping_stats AS (
  SELECT
    operator_id_raw,
    max(operator_group_hint) AS operator_group_hint,
    tech_norm,
    cell_id_dec,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*)::bigint AS report_cnt,
    count(DISTINCT did)::bigint AS device_cnt_did,
    count(DISTINCT did2)::bigint AS device_cnt,
    count(DISTINCT report_date)::int AS active_days,
    min(ts_std) AS first_seen_ts,
    max(ts_std) AS last_seen_ts
  FROM base2
  GROUP BY 1,3,4,5,6,7
),
ranked AS (
  SELECT
    m.*,
    sum(m.report_cnt) OVER (PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_dec) AS cell_total_report_cnt,
    count(*) OVER (PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_dec) AS bucket_cnt_per_cell,
    row_number() OVER (
      PARTITION BY m.operator_id_raw, m.tech_norm, m.cell_id_dec
      ORDER BY m.report_cnt DESC, m.last_seen_ts DESC
    ) AS rn
  FROM mapping_stats m
),
picked AS (
  SELECT *
  FROM ranked
  WHERE rn=1
)
SELECT
  p.operator_id_raw,
  p.operator_group_hint,
  p.tech_norm,
  p.cell_id_dec,
  upper(to_hex(p.cell_id_dec::bigint)) AS cell_id_hex,
  p.bs_id,
  upper(to_hex(p.bs_id::bigint)) AS bs_id_hex,
  p.lac_dec_final,
  upper(to_hex(p.lac_dec_final::bigint)) AS lac_hex,
  p.wuli_fentong_bs_key,

  p.device_cnt,
  p.device_cnt_did,
  p.report_cnt,
  p.cell_total_report_cnt,
  p.active_days,
  p.first_seen_ts,
  p.last_seen_ts,

  p.bucket_cnt_per_cell,
  (p.bucket_cnt_per_cell > 1) AS is_ambiguous_mapping,

  -- 关联站级画像（便于下阶段直接用站中心/风险做 cell 补数策略）
  s.gps_valid_level,
  s.bs_center_lon,
  s.bs_center_lat,
  s.is_collision_suspect,
  s.is_multi_operator_shared,
  s.shared_operator_list
FROM picked p
LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" s
  ON s.wuli_fentong_bs_key=p.wuli_fentong_bs_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_layer3_final_cell_bs_map_pk
  ON public."Y_codex_Layer3_Final_Cell_BS_Map"(operator_id_raw, tech_norm, cell_id_dec);

CREATE INDEX IF NOT EXISTS idx_layer3_final_cell_bs_map_bs
  ON public."Y_codex_Layer3_Final_Cell_BS_Map"(operator_id_raw, tech_norm, bs_id);

ANALYZE public."Y_codex_Layer3_Final_Cell_BS_Map";
