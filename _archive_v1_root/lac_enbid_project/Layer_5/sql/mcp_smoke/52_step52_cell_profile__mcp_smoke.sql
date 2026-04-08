-- Layer_5 Step52 MCP smoke：CELL Profile（小样本验证 SQL 是否可跑）

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';
SET TIME ZONE 'UTC';

DROP TABLE IF EXISTS public."Y_codex_Layer5_Smoke_Cell_Profile";

CREATE TABLE public."Y_codex_Layer5_Smoke_Cell_Profile" AS
WITH
params AS (
  SELECT
    date '2025-12-01' AS smoke_day_utc,
    '46000'::text AS smoke_operator_id_raw,
    1::bigint AS min_rows_for_profile,
    1000.0::double precision AS cell_gps_p90_warn_4g_m,
    500.0::double precision AS cell_gps_p90_warn_5g_m
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
    t.cell_id_dec,
    (t.ts_fill AT TIME ZONE 'UTC') AS event_ts_utc,
    t.lon_final,
    t.lat_final,
    t.gps_status,
    COALESCE(t.is_collision_suspect, 0)::int AS is_collision_suspect,
    COALESCE(t.is_severe_collision, false) AS is_severe_collision,
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
  FROM public."Y_codex_Layer4_Final_Cell_Library" t TABLESAMPLE SYSTEM (0.1)
  CROSS JOIN params p
  LEFT JOIN dynamic_cell dc
    ON dc.operator_id_raw = t.operator_id_raw
   AND dc.tech_norm_mapped = t.tech_norm
   AND dc.cell_id_dec = t.cell_id_dec
  WHERE
    t.tech_norm IN ('4G','5G')
    AND t.operator_id_raw = p.smoke_operator_id_raw
    AND t.lac_dec_final IS NOT NULL AND t.lac_dec_final > 0
    AND t.cell_id_dec IS NOT NULL AND t.cell_id_dec > 0
    AND t.bs_id_final IS NOT NULL AND t.bs_id_final > 0
    AND (t.ts_fill AT TIME ZONE 'UTC')::date = p.smoke_day_utc
),
center AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    cell_id_dec,
    min(bs_id_final)::bigint AS bs_id_final,
    count(*)::bigint AS row_cnt,
    min(event_ts_utc) AS first_cell_ts_utc,
    max(event_ts_utc) AS last_cell_ts_utc,
    count(distinct (event_ts_utc at time zone 'UTC')::date)::int AS active_days_utc,
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
    b.cell_id_dec,
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
   AND c.cell_id_dec=b.cell_id_dec
  WHERE b.lon_final IS NOT NULL AND b.lat_final IS NOT NULL AND c.center_lon IS NOT NULL AND c.center_lat IS NOT NULL
),
dist_agg AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec_final,
    cell_id_dec,
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
    cell_id_dec,
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
    cell_id_dec,
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
    cell_id_dec,
    (max(is_collision_suspect) > 0) AS is_collision_suspect,
    (max(is_severe_collision::int) > 0) AS is_severe_collision,
    min(collision_reason) FILTER (WHERE collision_reason IS NOT NULL) AS collision_reason,
    count(*) FILTER (WHERE gps_status='Drift')::bigint AS gps_drift_row_cnt,
    round(100.0 * count(*) FILTER (WHERE gps_status='Drift')::numeric / NULLIF(count(*)::numeric, 0), 2) AS gps_drift_row_pct,
    (max(is_dynamic_cell) > 0) AS is_dynamic_cell,
    min(dynamic_reason) FILTER (WHERE dynamic_reason IS NOT NULL) AS dynamic_reason,
    max(half_major_dist_km) AS half_major_dist_km
  FROM base
  GROUP BY 1,2,3,4
)
SELECT
  c.operator_id_raw,
  c.tech_norm,
  c.lac_dec_final,
  c.bs_id_final,
  c.cell_id_dec,
  c.row_cnt,
  c.first_cell_ts_utc,
  c.last_cell_ts_utc,
  c.active_days_utc,
  c.gps_present_cnt,
  c.gps_missing_cnt,
  (c.gps_present_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)) AS gps_present_ratio,
  c.center_lon,
  c.center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  s.sig_rsrp_nonnull_cnt,
  s.sig_rsrq_nonnull_cnt,
  s.sig_sinr_nonnull_cnt,
  s.sig_rssi_nonnull_cnt,
  s.sig_dbm_nonnull_cnt,
  s.sig_asu_level_nonnull_cnt,
  s.sig_level_nonnull_cnt,
  s.sig_ss_nonnull_cnt,
  (s.sig_rsrp_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)) AS sig_rsrp_nonnull_ratio,
  (s.sig_rsrq_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)) AS sig_rsrq_nonnull_ratio,
  (s.sig_sinr_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)) AS sig_sinr_nonnull_ratio,
  (s.sig_dbm_nonnull_cnt::numeric / NULLIF(c.row_cnt::numeric, 0)) AS sig_dbm_nonnull_ratio,
  p.native_any_signal_row_cnt,
  p.native_no_signal_row_cnt,
  p.need_fill_row_cnt,
  p.filled_row_cnt,
  p.filled_by_cell_nearest_row_cnt,
  p.filled_by_bs_top_cell_nearest_row_cnt,
  p.fill_failed_row_cnt,
  p.missing_field_before_sum,
  p.missing_field_after_sum,
  p.filled_field_sum,
  a.is_collision_suspect,
  a.is_severe_collision,
  a.collision_reason,
  a.gps_drift_row_cnt,
  a.gps_drift_row_pct,
  a.is_dynamic_cell,
  a.dynamic_reason,
  a.half_major_dist_km,
  (c.row_cnt < (SELECT min_rows_for_profile FROM params)) AS is_low_sample,
  (c.gps_present_cnt > 0) AS has_gps_profile,
  (
    d.gps_p90_dist_m IS NOT NULL AND d.gps_p90_dist_m >
    CASE WHEN c.tech_norm='4G' THEN (SELECT cell_gps_p90_warn_4g_m FROM params) ELSE (SELECT cell_gps_p90_warn_5g_m FROM params) END
  ) AS is_gps_unstable
FROM center c
LEFT JOIN dist_agg d USING (operator_id_raw, tech_norm, lac_dec_final, cell_id_dec)
LEFT JOIN sig s USING (operator_id_raw, tech_norm, lac_dec_final, cell_id_dec)
LEFT JOIN sig_prov p USING (operator_id_raw, tech_norm, lac_dec_final, cell_id_dec)
LEFT JOIN anomaly a USING (operator_id_raw, tech_norm, lac_dec_final, cell_id_dec);

ANALYZE public."Y_codex_Layer5_Smoke_Cell_Profile";
