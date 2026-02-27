-- Layer_4 Step40 MCP Smoke：GPS 过滤 + 按 BS 回填（固定表名，无 DO 块）
--
-- 输出（固定）：
-- - public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE"
-- - public."Y_codex_Layer4_Step40_Gps_Metrics__MCP_SMOKE"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE";

CREATE TABLE public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE" AS
WITH
params AS (
  SELECT
    true::boolean AS is_smoke,
    date '2025-12-01' AS smoke_date,
    '46000'::text AS smoke_operator_id_raw,
    200000::bigint AS smoke_limit_rows,
    1000.0::double precision AS city_dist_threshold_4g_m,
    500.0::double precision AS city_dist_threshold_5g_m,
    73.0::double precision AS china_lon_min,
    135.0::double precision AS china_lon_max,
    3.0::double precision AS china_lat_min,
    54.0::double precision AS china_lat_max
),
base0 AS (
  SELECT
    t.seq_id,
    t."运营商id"::text AS operator_id_raw,
    t.tech::text AS tech_norm,
    t.lac_dec,
    t.cell_id_dec,
    t.bs_id,
    t.ts_std,
    t.cell_ts_std,
    t.lon,
    t.lat,
    t.sig_rsrp,
    t.sig_rsrq,
    t.sig_sinr,
    t.sig_rssi,
    t.sig_dbm,
    t.sig_asu_level,
    t.sig_level,
    t.sig_ss
  FROM public."Y_codex_Layer0_Lac" t
  CROSS JOIN params p
  WHERE
    t.tech IN ('4G','5G')
    AND t."运营商id" IN ('46000','46001','46011','46015','46020')
    AND t.cell_id_dec IS NOT NULL AND t.cell_id_dec > 0
    AND (NOT p.is_smoke OR p.smoke_date IS NULL OR t.ts_std::date = p.smoke_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t."运营商id"::text = p.smoke_operator_id_raw)
  ORDER BY t.ts_std, t.seq_id
  LIMIT (SELECT smoke_limit_rows FROM params)
),
cells AS (
  SELECT DISTINCT operator_id_raw, tech_norm, cell_id_dec FROM base0
),
lacs AS (
  SELECT DISTINCT operator_id_raw, tech_norm, lac_dec FROM base0 WHERE lac_dec IS NOT NULL
),
trusted_lac AS (
  SELECT l.operator_id_raw, l.tech_norm, l.lac_dec
  FROM lacs l
  JOIN public."Y_codex_Layer2_Step04_Master_Lac_Lib" m
    ON m.operator_id_raw=l.operator_id_raw
   AND m.tech_norm=l.tech_norm
   AND m.lac_dec=l.lac_dec
  WHERE m.is_trusted_lac
),
map_unique AS (
  SELECT
    s.operator_id_raw,
    s.tech_norm,
    s.cell_id_dec,
    CASE WHEN min(s.lac_dec) = max(s.lac_dec) THEN min(s.lac_dec) END AS lac_dec_from_map
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
  JOIN cells c
    ON c.operator_id_raw=s.operator_id_raw
   AND c.tech_norm=s.tech_norm
   AND c.cell_id_dec=s.cell_id_dec
  GROUP BY 1,2,3
),
base AS (
  SELECT
    b0.*,
    COALESCE(
      b0.bs_id,
      CASE
        WHEN b0.tech_norm='4G' AND b0.cell_id_dec IS NOT NULL THEN floor(b0.cell_id_dec / 256.0)::bigint
        WHEN b0.tech_norm='5G' AND b0.cell_id_dec IS NOT NULL THEN floor(b0.cell_id_dec / 4096.0)::bigint
      END
    ) AS bs_id_final,
    CASE
      WHEN tl.lac_dec IS NOT NULL THEN b0.lac_dec
      ELSE mu.lac_dec_from_map
    END AS lac_dec_final
  FROM base0 b0
  LEFT JOIN trusted_lac tl
    ON tl.operator_id_raw=b0.operator_id_raw
   AND tl.tech_norm=b0.tech_norm
   AND tl.lac_dec=b0.lac_dec
  LEFT JOIN map_unique mu
    ON mu.operator_id_raw=b0.operator_id_raw
   AND mu.tech_norm=b0.tech_norm
   AND mu.cell_id_dec=b0.cell_id_dec
),
keyed AS (
  SELECT
    b.*,
    CASE
      WHEN b.lac_dec_final IS NOT NULL THEN concat_ws('|', b.tech_norm, b.bs_id_final::text, b.lac_dec_final::text)
      ELSE NULL::text
    END AS wuli_fentong_bs_key,
    concat_ws('|', b.tech_norm, b.bs_id_final::text) AS bs_shard_key
  FROM base b
  WHERE b.bs_id_final IS NOT NULL AND b.bs_id_final > 0
),
joined AS (
  SELECT
    k.*,
    bs.gps_valid_level,
    bs.bs_center_lon,
    bs.bs_center_lat,
    bs.is_collision_suspect,
    bs.gps_valid_point_cnt AS bs_gps_valid_point_cnt,
    bs.gps_p50_dist_m AS bs_gps_p50_dist_m,
    bs.anomaly_cell_cnt AS bs_anomaly_cell_cnt
  FROM keyed k
  LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" bs
    ON bs.tech_norm = k.tech_norm
   AND bs.bs_id = k.bs_id_final
   AND bs.wuli_fentong_bs_key = k.wuli_fentong_bs_key
),
dist_calc AS (
  SELECT
    j.*,
    CASE
      WHEN j.lon IS NULL OR j.lat IS NULL THEN false
      WHEN j.lon BETWEEN (SELECT china_lon_min FROM params) AND (SELECT china_lon_max FROM params)
       AND j.lat BETWEEN (SELECT china_lat_min FROM params) AND (SELECT china_lat_max FROM params)
      THEN true
      ELSE false
    END AS gps_in_china,
    CASE
      WHEN j.lon IS NULL OR j.lat IS NULL THEN NULL::double precision
      WHEN j.bs_center_lon IS NULL OR j.bs_center_lat IS NULL THEN NULL::double precision
      ELSE
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(j.lat - j.bs_center_lat) / 2.0), 2)
            + cos(radians(j.bs_center_lat)) * cos(radians(j.lat))
              * power(sin(radians(j.lon - j.bs_center_lon) / 2.0), 2)
          )
        )
    END AS gps_dist_to_bs_m,
    CASE
      WHEN j.tech_norm = '4G' THEN (SELECT city_dist_threshold_4g_m FROM params)
      WHEN j.tech_norm = '5G' THEN (SELECT city_dist_threshold_5g_m FROM params)
      ELSE NULL::double precision
    END AS dist_threshold_m
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
      WHEN d.lon IS NULL OR d.lat IS NULL THEN 'Missing'
      WHEN d.gps_in_china IS NOT TRUE THEN 'Missing'
      WHEN d.gps_dist_to_bs_m IS NOT NULL AND d.dist_threshold_m IS NOT NULL AND d.gps_dist_to_bs_m > d.dist_threshold_m THEN 'Drift'
      ELSE 'Verified'
    END AS gps_status
  FROM dist_calc d
),
fixed AS (
  SELECT
    c.seq_id,
    c.operator_id_raw,
    c.tech_norm,
    c.cell_id_dec,
    c.bs_id_final,
    c.lac_dec_final,
    c.wuli_fentong_bs_key,
    c.bs_shard_key,
    c.ts_std,
    c.cell_ts_std,
    c.lon AS lon_before_fix,
    c.lat AS lat_before_fix,
    c.gps_valid_level,
	    c.is_collision_suspect,
	    c.is_severe_collision,
	    c.gps_status,
	    CASE
	      WHEN c.gps_status='Verified' THEN 'keep_raw'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level IN ('Usable','Risk')
	       AND c.is_severe_collision IS TRUE
	      THEN 'fill_bs_severe_collision'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level='Usable'
	       AND c.is_severe_collision IS NOT TRUE
	      THEN 'fill_bs'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level='Risk'
	      THEN 'fill_risk_bs'
	      ELSE 'not_filled'
	    END AS gps_fix_strategy,
	    CASE
	      WHEN c.gps_status='Verified' THEN c.lon
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level IN ('Usable','Risk')
	      THEN c.bs_center_lon
	      ELSE NULL::double precision
    END AS lon_final,
	    CASE
	      WHEN c.gps_status='Verified' THEN c.lat
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level IN ('Usable','Risk')
	      THEN c.bs_center_lat
	      ELSE NULL::double precision
	    END AS lat_final,
	    CASE
	      WHEN c.gps_status='Verified' THEN 'Original_Verified'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level='Usable'
	       AND c.is_severe_collision IS TRUE
	      THEN 'Augmented_from_BS_SevereCollision'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level='Usable'
	       AND c.is_severe_collision IS NOT TRUE
	      THEN 'Augmented_from_BS'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level='Risk'
	      THEN 'Augmented_from_Risk_BS'
	      ELSE 'Not_Filled'
    END AS gps_source,
	    CASE
	      WHEN c.gps_status='Verified' THEN 'Verified'
	      WHEN c.gps_status IN ('Missing','Drift')
	       AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
	       AND c.gps_valid_level IN ('Usable','Risk')
	      THEN 'Verified'
	      ELSE 'Missing'
	    END AS gps_status_final,
    c.sig_rsrp,
    c.sig_rsrq,
    c.sig_sinr,
    c.sig_rssi,
    c.sig_dbm,
    c.sig_asu_level,
    c.sig_level,
    c.sig_ss
  FROM classified c
)
SELECT * FROM fixed;

UPDATE public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE"
SET sig_rsrp = NULL
WHERE sig_rsrp IN (-110, -1) OR sig_rsrp >= 0;

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step40_Gps_Metrics__MCP_SMOKE";
CREATE TABLE public."Y_codex_Layer4_Step40_Gps_Metrics__MCP_SMOKE" AS
SELECT
  count(*)::bigint AS row_cnt,
  count(*) FILTER (WHERE gps_status='Missing')::bigint AS gps_missing_cnt,
  count(*) FILTER (WHERE gps_status='Drift')::bigint AS gps_drift_cnt,
  count(*) FILTER (WHERE gps_source='Augmented_from_BS')::bigint AS gps_fill_from_bs_cnt,
  count(*) FILTER (WHERE gps_source='Augmented_from_BS_SevereCollision')::bigint AS gps_fill_from_bs_severe_collision_cnt,
  count(*) FILTER (WHERE gps_source='Augmented_from_Risk_BS')::bigint AS gps_fill_from_risk_bs_cnt,
  count(*) FILTER (WHERE gps_source='Not_Filled')::bigint AS gps_not_filled_cnt,
  count(*) FILTER (WHERE is_severe_collision IS TRUE)::bigint AS severe_collision_row_cnt
FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__MCP_SMOKE";
