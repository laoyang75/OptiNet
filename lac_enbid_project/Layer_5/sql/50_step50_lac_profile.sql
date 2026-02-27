-- Layer_5 Step50：LAC Profile（按 LAC 汇总一行一对象）
--
-- 输入：
-- - public."Y_codex_Layer4_Final_Cell_Library"
--
-- 输出：
-- - public."Y_codex_Layer5_Lac_Profile"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET TIME ZONE 'UTC';

DROP VIEW IF EXISTS public."Y_codex_Layer5_Lac_Profile_EN";
DROP TABLE IF EXISTS public."Y_codex_Layer5_Lac_Profile";

CREATE TABLE public."Y_codex_Layer5_Lac_Profile" AS
WITH
params AS (
  SELECT
    5000::bigint AS min_rows_for_profile,
    100000.0::double precision AS lac_gps_p90_warn_m
),
base AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    bs_id_final,
    cell_id_dec,
    (ts_fill AT TIME ZONE 'UTC') AS event_ts_utc,
    lon_final,
    lat_final,
    has_any_signal,
    signal_missing_before_cnt,
    signal_missing_after_cnt,
    signal_filled_field_cnt,
    signal_fill_source,
    sig_rsrp_final,
    sig_rsrq_final,
    sig_sinr_final,
    sig_rssi_final,
    sig_dbm_final,
    sig_asu_level_final,
    sig_level_final,
    sig_ss_final
  FROM public."Y_codex_Layer4_Final_Cell_Library"
  WHERE
    tech_norm IN ('4G','5G')
    AND operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND lac_dec_final IS NOT NULL AND lac_dec_final > 0
    AND cell_id_dec > 0
    AND bs_id_final > 0
),
bs_op_group AS (
  SELECT
    tech_norm,
    lac_dec_final,
    bs_id_final,
    count(distinct operator_group)::int AS operator_group_cnt
  FROM (
    SELECT
      tech_norm,
      lac_dec_final,
      bs_id_final,
      CASE
        WHEN operator_id_raw IN ('46000','46015','46020') THEN 'G1'
        WHEN operator_id_raw IN ('46001','46011') THEN 'G2'
        ELSE NULL
      END AS operator_group
    FROM base
  ) x
  WHERE operator_group IS NOT NULL
  GROUP BY 1,2,3
),
lac_multi_bs AS (
  SELECT
    b.operator_id_raw,
    b.tech_norm,
    b.lac_dec_final,
    count(distinct b.bs_id_final) FILTER (WHERE g.operator_group_cnt > 1)::bigint AS multi_operator_bs_cnt
  FROM base b
  LEFT JOIN bs_op_group g
    ON g.tech_norm=b.tech_norm
   AND g.lac_dec_final=b.lac_dec_final
   AND g.bs_id_final=b.bs_id_final
  GROUP BY 1,2,3
),
center AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    count(*)::bigint AS row_cnt,
    min(event_ts_utc) AS first_cell_ts_utc,
    max(event_ts_utc) AS last_cell_ts_utc,
    count(distinct (event_ts_utc at time zone 'UTC')::date)::int AS active_days_utc,
    count(distinct bs_id_final)::bigint AS distinct_bs_cnt,
    count(distinct cell_id_dec)::bigint AS distinct_cell_cnt,

    count(*) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL)::bigint AS gps_present_cnt,
    count(*) FILTER (WHERE lon_final IS NULL OR lat_final IS NULL)::bigint AS gps_missing_cnt,

    min(lon_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS lon_min,
    max(lon_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS lon_max,
    min(lat_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS lat_min,
    max(lat_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS lat_max,

    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS center_lon,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NOT NULL) AS center_lat
  FROM base
  GROUP BY 1,2,3
),
dist AS (
  SELECT
    b.operator_id_raw,
    b.tech_norm,
    b.lac_dec_final,
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
  WHERE b.lon_final IS NOT NULL AND b.lat_final IS NOT NULL AND c.center_lon IS NOT NULL AND c.center_lat IS NOT NULL
),
dist_agg AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY dist_m) AS gps_p50_dist_m,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY dist_m) AS gps_p90_dist_m,
    max(dist_m) AS gps_max_dist_m
  FROM dist
  GROUP BY 1,2,3
),
sig AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    count(*) FILTER (WHERE sig_rsrp_final IS NOT NULL)::bigint AS sig_rsrp_nonnull_cnt,
    count(*) FILTER (WHERE sig_rsrq_final IS NOT NULL)::bigint AS sig_rsrq_nonnull_cnt,
    count(*) FILTER (WHERE sig_sinr_final IS NOT NULL)::bigint AS sig_sinr_nonnull_cnt,
    count(*) FILTER (WHERE sig_rssi_final IS NOT NULL)::bigint AS sig_rssi_nonnull_cnt,
    count(*) FILTER (WHERE sig_dbm_final IS NOT NULL)::bigint AS sig_dbm_nonnull_cnt,
    count(*) FILTER (WHERE sig_asu_level_final IS NOT NULL)::bigint AS sig_asu_level_nonnull_cnt,
    count(*) FILTER (WHERE sig_level_final IS NOT NULL)::bigint AS sig_level_nonnull_cnt,
    count(*) FILTER (WHERE sig_ss_final IS NOT NULL)::bigint AS sig_ss_nonnull_cnt
  FROM base
  GROUP BY 1,2,3
),
sig_prov AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
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
  GROUP BY 1,2,3
)
SELECT
  c.operator_id_raw AS "运营商ID",
  c.tech_norm AS "制式",
  c.lac_dec_final AS "LAC",
  c.row_cnt AS "行数",
  c.first_cell_ts_utc AS "最早时间UTC",
  c.last_cell_ts_utc AS "最晚时间UTC",
  c.active_days_utc AS "活跃天数UTC",
  c.distinct_bs_cnt AS "BS去重数",
  c.distinct_cell_cnt AS "CELL去重数",
  c.gps_present_cnt AS "GPS有效行数",
  c.gps_missing_cnt AS "GPS缺失行数",
  round(100.0 * (c.gps_present_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)), 2) AS "GPS有效率",
  c.center_lon AS "GPS中心经度",
  c.center_lat AS "GPS中心纬度",
  c.lon_min AS "经度最小",
  c.lon_max AS "经度最大",
  c.lat_min AS "纬度最小",
  c.lat_max AS "纬度最大",
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

  m.multi_operator_bs_cnt AS "多运营商BS去重数",
  (COALESCE(m.multi_operator_bs_cnt, 0) > 0) AS "多运营商BS标记",

  (c.row_cnt < (SELECT min_rows_for_profile FROM params)) AS "样本不足",
  (c.gps_present_cnt > 0) AS "有GPS画像",
  (d.gps_p90_dist_m IS NOT NULL AND d.gps_p90_dist_m > (SELECT lac_gps_p90_warn_m FROM params)) AS "GPS不稳定"
FROM center c
LEFT JOIN dist_agg d USING (operator_id_raw, tech_norm, lac_dec_final)
LEFT JOIN sig s USING (operator_id_raw, tech_norm, lac_dec_final)
LEFT JOIN sig_prov p USING (operator_id_raw, tech_norm, lac_dec_final)
LEFT JOIN lac_multi_bs m USING (operator_id_raw, tech_norm, lac_dec_final);

ANALYZE public."Y_codex_Layer5_Lac_Profile";

-- 可选：提供英文视图，便于后续 SQL/程序使用（底表字段为中文）
CREATE OR REPLACE VIEW public."Y_codex_Layer5_Lac_Profile_EN" AS
SELECT
  "运营商ID" AS operator_id_raw,
  "制式" AS tech_norm,
  "LAC" AS lac_dec_final,
  "行数" AS row_cnt,
  "最早时间UTC" AS first_cell_ts_utc,
  "最晚时间UTC" AS last_cell_ts_utc,
  "活跃天数UTC" AS active_days_utc,
  "BS去重数" AS distinct_bs_cnt,
  "CELL去重数" AS distinct_cell_cnt,
  "GPS有效行数" AS gps_present_cnt,
  "GPS缺失行数" AS gps_missing_cnt,
  "GPS有效率" AS gps_present_ratio,
  "GPS中心经度" AS center_lon,
  "GPS中心纬度" AS center_lat,
  "经度最小" AS lon_min,
  "经度最大" AS lon_max,
  "纬度最小" AS lat_min,
  "纬度最大" AS lat_max,
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
  "多运营商BS去重数" AS multi_operator_bs_cnt,
  "多运营商BS标记" AS has_multi_operator_bs,
  "样本不足" AS is_low_sample,
  "有GPS画像" AS has_gps_profile,
  "GPS不稳定" AS is_gps_unstable
FROM public."Y_codex_Layer5_Lac_Profile";
