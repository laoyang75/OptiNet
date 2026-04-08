-- Layer_5 Step51：BS Profile（按 BS 汇总一行一对象）
--
-- 输入：
-- - public."Y_codex_Layer4_Final_Cell_Library"
--
-- 输出：
-- - public."Y_codex_Layer5_BS_Profile"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET TIME ZONE 'UTC';

DROP VIEW IF EXISTS public."Y_codex_Layer5_BS_Profile_EN";
DROP TABLE IF EXISTS public."Y_codex_Layer5_BS_Profile";

CREATE TABLE public."Y_codex_Layer5_BS_Profile" AS
WITH
params AS (
  SELECT
    1000.0::double precision AS bs_gps_p90_warn_4g_m,
    500.0::double precision AS bs_gps_p90_warn_5g_m,
    500::bigint AS min_rows_for_profile
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
    t.operator_id_raw,
    t.tech_norm,
    t.lac_dec_final,
    t.bs_id_final,
    t.wuli_fentong_bs_key,
    t.cell_id_dec,
    (t.ts_fill AT TIME ZONE 'UTC') AS event_ts_utc,
    t.lon_final,
    t.lat_final,
    t.gps_status,
    COALESCE(t.is_collision_suspect, 0)::int AS is_collision_suspect,
    COALESCE(t.is_severe_collision, false) AS is_severe_collision,
    COALESCE(t.is_bs_id_lt_256, false) AS is_bs_id_lt_256,
    COALESCE(t.is_multi_operator_shared, false) AS is_multi_operator_shared,
    COALESCE(t.shared_operator_cnt, 0)::int AS shared_operator_cnt,
    t.shared_operator_list,
    t.collision_reason,
    COALESCE(dc.is_dynamic_cell, 0)::int AS is_dynamic_cell,
    dc.dynamic_reason,
    dc.half_major_dist_km,
    t.has_any_signal,
    t.signal_missing_before_cnt,
    t.signal_missing_after_cnt,
    t.signal_filled_field_cnt,
    t.signal_fill_source,
    t.sig_rsrp_final,
    t.sig_rsrq_final,
    t.sig_sinr_final,
    t.sig_rssi_final,
    t.sig_dbm_final,
    t.sig_asu_level_final,
    t.sig_level_final,
    t.sig_ss_final
  FROM public."Y_codex_Layer4_Final_Cell_Library" t
  LEFT JOIN dynamic_cell dc
    ON dc.operator_id_raw = t.operator_id_raw
   AND dc.tech_norm_mapped = t.tech_norm
   AND dc.cell_id_dec = t.cell_id_dec
  WHERE
    t.tech_norm IN ('4G','5G')
    AND t.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND t.lac_dec_final IS NOT NULL AND t.lac_dec_final > 0
    AND t.bs_id_final IS NOT NULL AND t.bs_id_final > 0
    AND t.cell_id_dec > 0
),
center AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    min(wuli_fentong_bs_key) AS wuli_fentong_bs_key,
    count(*)::bigint AS row_cnt,
    min(event_ts_utc) AS first_cell_ts_utc,
    max(event_ts_utc) AS last_cell_ts_utc,
    count(distinct (event_ts_utc at time zone 'UTC')::date)::int AS active_days_utc,
    count(distinct cell_id_dec)::bigint AS distinct_cell_cnt,

    count(*) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL)::bigint AS gps_present_cnt,
    count(*) FILTER (WHERE lon_final IS NULL OR lat_final IS NULL)::bigint AS gps_missing_cnt,

    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS center_lon,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS center_lat
  FROM base
  GROUP BY 1,2,3,4
),
dist AS (
  SELECT
    b.operator_id_raw,
    b.tech_norm,
    b.lac_dec_final,
    b.bs_id_final,
    6371000.0 * 2.0 * asin(
      sqrt(
        power(sin(radians(b.lat_final - c.center_lat) / 2.0), 2)
        + cos(radians(c.center_lat)) * cos(radians(b.lat_final))
          * power(sin(radians(b.lon_final - c.center_lon) / 2.0), 2)
      )
    ) AS dist_m
  FROM base b
  JOIN center c
    ON c.operator_id_raw=b.operator_id_raw
   AND c.tech_norm=b.tech_norm
   AND c.lac_dec_final=b.lac_dec_final
   AND c.bs_id_final=b.bs_id_final
  WHERE b.lon_final IS NOT NULL AND b.lat_final IS NOT NULL AND c.center_lon IS NOT NULL AND c.center_lat IS NOT NULL
),
dist_agg AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY dist_m) AS gps_p50_dist_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY dist_m) AS gps_p90_dist_m,
    max(dist_m) AS gps_max_dist_m
  FROM dist
  GROUP BY 1,2,3,4
),
sig AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    count(*) FILTER (WHERE sig_rsrp_final IS NOT NULL)::bigint AS sig_rsrp_nonnull_cnt,
    count(*) FILTER (WHERE sig_rsrq_final IS NOT NULL)::bigint AS sig_rsrq_nonnull_cnt,
    count(*) FILTER (WHERE sig_sinr_final IS NOT NULL)::bigint AS sig_sinr_nonnull_cnt,
    count(*) FILTER (WHERE sig_rssi_final IS NOT NULL)::bigint AS sig_rssi_nonnull_cnt,
    count(*) FILTER (WHERE sig_dbm_final IS NOT NULL)::bigint AS sig_dbm_nonnull_cnt,
    count(*) FILTER (WHERE sig_asu_level_final IS NOT NULL)::bigint AS sig_asu_level_nonnull_cnt,
    count(*) FILTER (WHERE sig_level_final IS NOT NULL)::bigint AS sig_level_nonnull_cnt,
    count(*) FILTER (WHERE sig_ss_final IS NOT NULL)::bigint AS sig_ss_nonnull_cnt
  FROM base
  GROUP BY 1,2,3,4
),
sig_prov AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    count(*) FILTER (WHERE has_any_signal)::bigint AS native_any_signal_row_cnt,
    count(*) FILTER (WHERE NOT has_any_signal)::bigint AS native_no_signal_row_cnt,
    count(*) FILTER (WHERE signal_missing_before_cnt > 0)::bigint AS need_fill_row_cnt,
    count(*) FILTER (WHERE signal_filled_field_cnt > 0)::bigint AS filled_row_cnt,
    count(*) FILTER (WHERE signal_fill_source='cell_nearest' AND signal_filled_field_cnt > 0)::bigint AS filled_by_cell_nearest_row_cnt,
    count(*) FILTER (WHERE signal_fill_source='bs_top_cell_nearest' AND signal_filled_field_cnt > 0)::bigint AS filled_by_bs_top_cell_nearest_row_cnt,
    count(*) FILTER (WHERE signal_missing_before_cnt > 0 AND COALESCE(signal_filled_field_cnt,0) = 0)::bigint AS fill_failed_row_cnt,
    sum(signal_missing_before_cnt)::bigint AS missing_field_before_sum,
    sum(signal_missing_after_cnt)::bigint AS missing_field_after_sum,
    sum(signal_filled_field_cnt)::bigint AS filled_field_sum
  FROM base
  GROUP BY 1,2,3,4
),
anomaly AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    (max(is_collision_suspect) > 0) AS is_collision_suspect,
    (max(is_severe_collision::int) > 0) AS is_severe_collision,
    (max(is_bs_id_lt_256::int) > 0) AS is_bs_id_lt_256,
    (max(is_multi_operator_shared::int) > 0) AS is_multi_operator_shared,
    max(shared_operator_cnt)::int AS shared_operator_cnt,
    string_agg(DISTINCT shared_operator_list, ';' ORDER BY shared_operator_list)
      FILTER (WHERE shared_operator_list IS NOT NULL AND btrim(shared_operator_list) <> '') AS shared_operator_list,
    min(collision_reason) FILTER (WHERE collision_reason IS NOT NULL) AS collision_reason,
    count(*) FILTER (WHERE gps_status='Drift')::bigint AS gps_drift_row_cnt,
    round(100.0 * count(*) FILTER (WHERE gps_status='Drift')::numeric / NULLIF(count(*)::numeric, 0), 2) AS gps_drift_row_pct,
    count(distinct cell_id_dec) FILTER (WHERE is_dynamic_cell=1)::bigint AS dynamic_cell_cnt,
    (count(distinct cell_id_dec) FILTER (WHERE is_dynamic_cell=1) > 0) AS has_dynamic_cell
  FROM base
  GROUP BY 1,2,3,4
)
SELECT
  c.operator_id_raw AS "运营商ID",
  c.tech_norm AS "制式",
  c.lac_dec_final AS "LAC",
  c.bs_id_final AS "BS",
  c.wuli_fentong_bs_key AS "物理分桶BS键",
  c.row_cnt AS "行数",
  c.first_cell_ts_utc AS "最早时间UTC",
  c.last_cell_ts_utc AS "最晚时间UTC",
  c.active_days_utc AS "活跃天数UTC",
  c.distinct_cell_cnt AS "CELL去重数",
  c.gps_present_cnt AS "GPS有效行数",
  c.gps_missing_cnt AS "GPS缺失行数",
  round(100.0 * (c.gps_present_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "GPS有效率",
  c.center_lon AS "GPS中心经度",
  c.center_lat AS "GPS中心纬度",
  round(d.gps_p50_dist_m::numeric, 2) AS "GPS距离P50_米",
  round(d.gps_p90_dist_m::numeric, 2) AS "GPS距离P90_米",
  round(d.gps_max_dist_m::numeric, 2) AS "GPS距离MAX_米",
  s.sig_rsrp_nonnull_cnt AS "RSRP非空行数",
  s.sig_rsrq_nonnull_cnt AS "RSRQ非空行数",
  s.sig_sinr_nonnull_cnt AS "SINR非空行数",
  s.sig_rssi_nonnull_cnt AS "RSSI非空行数",
  s.sig_dbm_nonnull_cnt AS "DBM非空行数",
  s.sig_asu_level_nonnull_cnt AS "ASU_LEVEL非空行数",
  s.sig_level_nonnull_cnt AS "LEVEL非空行数",
  s.sig_ss_nonnull_cnt AS "SS非空行数",
  round(100.0 * (s.sig_rsrp_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "RSRP有效率",
  round(100.0 * (s.sig_rsrq_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "RSRQ有效率",
  round(100.0 * (s.sig_sinr_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "SINR有效率",
  round(100.0 * (s.sig_dbm_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "DBM有效率",

  p.native_any_signal_row_cnt AS "原生有信号行数",
  p.native_no_signal_row_cnt AS "原生无信号行数",
  p.need_fill_row_cnt AS "需要补齐行数",
  p.filled_row_cnt AS "补齐成功行数",
  p.filled_by_cell_nearest_row_cnt AS "补齐_同CELL_行数",
  p.filled_by_bs_top_cell_nearest_row_cnt AS "补齐_BS_TOP_行数",
  p.fill_failed_row_cnt AS "补齐失败行数",
  p.missing_field_before_sum AS "缺失字段数_补前合计",
  p.missing_field_after_sum AS "缺失字段数_补后合计",
  p.filled_field_sum AS "补齐字段数合计",

  a.is_collision_suspect AS "疑似碰撞标记",
  a.is_severe_collision AS "严重碰撞桶标记",
  a.collision_reason AS "碰撞原因",
  a.gps_drift_row_cnt AS "GPS漂移行数",
  a.gps_drift_row_pct AS "GPS漂移占比",
  a.dynamic_cell_cnt AS "移动CELL去重数",
  a.has_dynamic_cell AS "含移动CELL标记",
  a.is_bs_id_lt_256 AS "BS_ID<256标记",
  a.is_multi_operator_shared AS "多运营商共享标记",
  a.shared_operator_cnt AS "共享运营商数",
  a.shared_operator_list AS "共享运营商列表",

  (c.row_cnt < (SELECT min_rows_for_profile FROM params)) AS "样本不足",
  (c.gps_present_cnt > 0) AS "有GPS画像",
  (
    d.gps_p90_dist_m IS NOT NULL AND d.gps_p90_dist_m >
    CASE WHEN c.tech_norm='4G' THEN (SELECT bs_gps_p90_warn_4g_m FROM params) ELSE (SELECT bs_gps_p90_warn_5g_m FROM params) END
  ) AS "GPS不稳定"
FROM center c
LEFT JOIN dist_agg d USING (operator_id_raw, tech_norm, lac_dec_final, bs_id_final)
LEFT JOIN sig s USING (operator_id_raw, tech_norm, lac_dec_final, bs_id_final)
LEFT JOIN sig_prov p USING (operator_id_raw, tech_norm, lac_dec_final, bs_id_final)
LEFT JOIN anomaly a USING (operator_id_raw, tech_norm, lac_dec_final, bs_id_final);

ANALYZE public."Y_codex_Layer5_BS_Profile";

-- 可选：英文视图（底表字段为中文）
CREATE OR REPLACE VIEW public."Y_codex_Layer5_BS_Profile_EN" AS
SELECT
  "运营商ID" AS operator_id_raw,
  "制式" AS tech_norm,
  "LAC" AS lac_dec_final,
  "BS" AS bs_id_final,
  "物理分桶BS键" AS wuli_fentong_bs_key,
  "行数" AS row_cnt,
  "最早时间UTC" AS first_cell_ts_utc,
  "最晚时间UTC" AS last_cell_ts_utc,
  "活跃天数UTC" AS active_days_utc,
  "CELL去重数" AS distinct_cell_cnt,
  "GPS有效行数" AS gps_present_cnt,
  "GPS缺失行数" AS gps_missing_cnt,
  "GPS有效率" AS gps_present_ratio,
  "GPS中心经度" AS center_lon,
  "GPS中心纬度" AS center_lat,
  "GPS距离P50_米" AS gps_p50_dist_m,
  "GPS距离P90_米" AS gps_p90_dist_m,
  "GPS距离MAX_米" AS gps_max_dist_m,
  "RSRP非空行数" AS sig_rsrp_nonnull_cnt,
  "RSRQ非空行数" AS sig_rsrq_nonnull_cnt,
  "SINR非空行数" AS sig_sinr_nonnull_cnt,
  "RSSI非空行数" AS sig_rssi_nonnull_cnt,
  "DBM非空行数" AS sig_dbm_nonnull_cnt,
  "ASU_LEVEL非空行数" AS sig_asu_level_nonnull_cnt,
  "LEVEL非空行数" AS sig_level_nonnull_cnt,
  "SS非空行数" AS sig_ss_nonnull_cnt,
  "RSRP有效率" AS sig_rsrp_nonnull_ratio,
  "RSRQ有效率" AS sig_rsrq_nonnull_ratio,
  "SINR有效率" AS sig_sinr_nonnull_ratio,
  "DBM有效率" AS sig_dbm_nonnull_ratio,
  "原生有信号行数" AS native_any_signal_row_cnt,
  "原生无信号行数" AS native_no_signal_row_cnt,
  "需要补齐行数" AS need_fill_row_cnt,
  "补齐成功行数" AS filled_row_cnt,
  "补齐_同CELL_行数" AS filled_by_cell_nearest_row_cnt,
  "补齐_BS_TOP_行数" AS filled_by_bs_top_cell_nearest_row_cnt,
  "补齐失败行数" AS fill_failed_row_cnt,
  "缺失字段数_补前合计" AS missing_field_before_sum,
  "缺失字段数_补后合计" AS missing_field_after_sum,
  "补齐字段数合计" AS filled_field_sum,
  "疑似碰撞标记" AS is_collision_suspect,
  "严重碰撞桶标记" AS is_severe_collision,
  "碰撞原因" AS collision_reason,
  "GPS漂移行数" AS gps_drift_row_cnt,
  "GPS漂移占比" AS gps_drift_row_pct,
  "移动CELL去重数" AS dynamic_cell_cnt,
  "含移动CELL标记" AS has_dynamic_cell,
  "BS_ID<256标记" AS is_bs_id_lt_256,
  "多运营商共享标记" AS is_multi_operator_shared,
  "共享运营商数" AS shared_operator_cnt,
  "共享运营商列表" AS shared_operator_list,
  "样本不足" AS is_low_sample,
  "有GPS画像" AS has_gps_profile,
  "GPS不稳定" AS is_gps_unstable
FROM public."Y_codex_Layer5_BS_Profile";
