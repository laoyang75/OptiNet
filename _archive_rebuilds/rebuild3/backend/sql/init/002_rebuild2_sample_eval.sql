SET statement_timeout = 0;
SET work_mem = '256MB';

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_dim_cell_stats;
CREATE TABLE rebuild3_sample_meta.r2_dim_cell_stats AS
SELECT
  l."运营商编码" AS operator_code,
  l."运营商中文" AS operator_cn,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."CellID" AS cell_id,
  l."基站ID" AS bs_id,
  l."扇区ID" AS sector_id,
  count(*) AS record_count,
  count(DISTINCT l."设备标识") AS distinct_device_count,
  count(DISTINCT date_trunc('day', l."上报时间")) FILTER (WHERE l."上报时间" IS NOT NULL) AS active_days,
  min(l."上报时间") AS first_seen,
  max(l."上报时间") AS last_seen,
  percentile_cont(0.5) within group (order by l."经度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS gps_center_lon,
  percentile_cont(0.5) within group (order by l."纬度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS gps_center_lat,
  count(*) FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS valid_gps_count
FROM rebuild3_sample.source_l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
GROUP BY 1,2,3,4,5,6,7;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_bs_center;
CREATE TABLE rebuild3_sample_meta.r2_bs_center AS
SELECT
  l."运营商编码" AS operator_code,
  l."运营商中文" AS operator_cn,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."基站ID" AS bs_id,
  count(*) AS record_count,
  count(DISTINCT l."设备标识") AS distinct_device_count,
  count(DISTINCT date_trunc('day', l."上报时间")) FILTER (WHERE l."上报时间" IS NOT NULL) AS active_days,
  min(l."上报时间") AS first_seen,
  max(l."上报时间") AS last_seen,
  percentile_cont(0.5) within group (order by l."经度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS gps_center_lon,
  percentile_cont(0.5) within group (order by l."纬度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS gps_center_lat,
  count(*) FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS total_gps_points,
  count(DISTINCT l."设备标识") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS distinct_gps_devices
FROM rebuild3_sample.source_l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
GROUP BY 1,2,3,4,5;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_bs_distance;
CREATE TABLE rebuild3_sample_meta.r2_bs_distance AS
SELECT
  c.operator_code,
  c.tech_norm,
  c.lac,
  c.bs_id,
  percentile_cont(0.5) within group (order by d.dist_m) AS gps_p50_dist_m,
  percentile_cont(0.9) within group (order by d.dist_m) AS gps_p90_dist_m,
  max(d.dist_m) AS gps_max_dist_m
FROM rebuild3_sample_meta.r2_bs_center c
JOIN (
  SELECT
    l."运营商编码" AS operator_code,
    l."标准制式" AS tech_norm,
    l."LAC"::text AS lac,
    l."基站ID" AS bs_id,
    sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))::numeric AS dist_m
  FROM rebuild3_sample.source_l0_lac l
  JOIN rebuild3_sample_meta.r2_bs_center c
    ON l."运营商编码" = c.operator_code
   AND l."标准制式" = c.tech_norm
   AND l."LAC"::text = c.lac
   AND l."基站ID" = c.bs_id
  WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54
) d
  ON c.operator_code = d.operator_code
 AND c.tech_norm = d.tech_norm
 AND c.lac = d.lac
 AND c.bs_id = d.bs_id
GROUP BY 1,2,3,4;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_dim_bs_refined;
CREATE TABLE rebuild3_sample_meta.r2_dim_bs_refined AS
SELECT
  c.operator_code,
  c.operator_cn,
  c.tech_norm,
  c.lac,
  c.bs_id,
  count(cs.cell_id) AS cell_count,
  c.record_count,
  c.distinct_device_count,
  c.active_days AS max_active_days,
  c.first_seen,
  c.last_seen,
  c.gps_center_lon,
  c.gps_center_lat,
  c.total_gps_points,
  c.distinct_gps_devices,
  count(cs.cell_id) FILTER (WHERE cs.valid_gps_count > 0) AS cells_with_gps,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  CASE
    WHEN c.total_gps_points >= 10 AND coalesce(d.gps_p90_dist_m, 999999) <= 1500 THEN 'Usable'
    WHEN c.total_gps_points >= 3 AND coalesce(d.gps_p90_dist_m, 999999) <= 4000 THEN 'Risk'
    ELSE 'Unusable'
  END AS gps_quality,
  now() AS created_at
FROM rebuild3_sample_meta.r2_bs_center c
LEFT JOIN rebuild3_sample_meta.r2_bs_distance d
  ON c.operator_code = d.operator_code
 AND c.tech_norm = d.tech_norm
 AND c.lac = d.lac
 AND c.bs_id = d.bs_id
LEFT JOIN rebuild3_sample_meta.r2_dim_cell_stats cs
  ON c.operator_code = cs.operator_code
 AND c.tech_norm = cs.tech_norm
 AND c.lac = cs.lac
 AND c.bs_id = cs.bs_id
GROUP BY
  c.operator_code,
  c.operator_cn,
  c.tech_norm,
  c.lac,
  c.bs_id,
  c.record_count,
  c.distinct_device_count,
  c.active_days,
  c.first_seen,
  c.last_seen,
  c.gps_center_lon,
  c.gps_center_lat,
  c.total_gps_points,
  c.distinct_gps_devices,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m;
DROP TABLE IF EXISTS rebuild3_sample_meta.r2_tmp_cell_center;
CREATE TABLE rebuild3_sample_meta.r2_tmp_cell_center AS
SELECT
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."CellID" AS cell_id,
  percentile_cont(0.5) within group (order by l."经度") AS clon,
  percentile_cont(0.5) within group (order by l."纬度") AS clat,
  count(*) AS gps_count,
  count(DISTINCT l."设备标识") AS gps_device_count
FROM rebuild3_sample.source_l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND l."GPS有效"
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54
GROUP BY 1,2,3,4;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_tmp_cell_dist;
CREATE TABLE rebuild3_sample_meta.r2_tmp_cell_dist AS
SELECT
  cc.operator_code,
  cc.tech_norm,
  cc.lac,
  cc.cell_id,
  cc.clon,
  cc.clat,
  cc.gps_count,
  cc.gps_device_count,
  br.gps_center_lon AS bs_lon,
  br.gps_center_lat AS bs_lat,
  br.gps_quality AS bs_gps_quality,
  sqrt(power((cc.clon - br.gps_center_lon) * 85300, 2) + power((cc.clat - br.gps_center_lat) * 111000, 2))::numeric AS dist_to_bs_m,
  CASE
    WHEN br.gps_center_lon IS NULL THEN false
    WHEN cc.tech_norm LIKE '%5G%' AND sqrt(power((cc.clon - br.gps_center_lon) * 85300, 2) + power((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000 THEN true
    WHEN cc.tech_norm NOT LIKE '%5G%' AND sqrt(power((cc.clon - br.gps_center_lon) * 85300, 2) + power((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000 THEN true
    ELSE false
  END AS gps_anomaly,
  CASE
    WHEN br.gps_center_lon IS NULL THEN NULL
    WHEN cc.tech_norm LIKE '%5G%' AND sqrt(power((cc.clon - br.gps_center_lon) * 85300, 2) + power((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000 THEN 'cell_to_bs_dist>1000m(5G)'
    WHEN cc.tech_norm NOT LIKE '%5G%' AND sqrt(power((cc.clon - br.gps_center_lon) * 85300, 2) + power((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000 THEN 'cell_to_bs_dist>2000m(non5G)'
    ELSE NULL
  END AS gps_anomaly_reason
FROM rebuild3_sample_meta.r2_tmp_cell_center cc
LEFT JOIN rebuild3_sample_meta.r2_dim_cell_stats cs
  ON cc.operator_code = cs.operator_code
 AND cc.tech_norm = cs.tech_norm
 AND cc.lac = cs.lac
 AND cc.cell_id = cs.cell_id
LEFT JOIN rebuild3_sample_meta.r2_dim_bs_refined br
  ON cs.operator_code = br.operator_code
 AND cs.tech_norm = br.tech_norm
 AND cs.lac = br.lac
 AND cs.bs_id = br.bs_id;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_dim_cell_refined;
CREATE TABLE rebuild3_sample_meta.r2_dim_cell_refined AS
SELECT
  cs.operator_code,
  cs.operator_cn,
  cs.tech_norm,
  cs.lac,
  cs.cell_id,
  cs.bs_id,
  cs.sector_id,
  cs.record_count,
  cs.distinct_device_count,
  cs.active_days,
  coalesce(cd.clon, cs.gps_center_lon) AS gps_center_lon,
  coalesce(cd.clat, cs.gps_center_lat) AS gps_center_lat,
  coalesce(cd.gps_count, cs.valid_gps_count) AS gps_count,
  coalesce(cd.gps_device_count, 0) AS gps_device_count,
  cd.dist_to_bs_m,
  coalesce(cd.gps_anomaly, false) AS gps_anomaly,
  cd.gps_anomaly_reason,
  coalesce(cd.bs_gps_quality, br.gps_quality) AS bs_gps_quality,
  now() AS created_at
FROM rebuild3_sample_meta.r2_dim_cell_stats cs
LEFT JOIN rebuild3_sample_meta.r2_tmp_cell_dist cd
  ON cs.operator_code = cd.operator_code
 AND cs.tech_norm = cd.tech_norm
 AND cs.lac = cd.lac
 AND cs.cell_id = cd.cell_id
LEFT JOIN rebuild3_sample_meta.r2_dim_bs_refined br
  ON cs.operator_code = br.operator_code
 AND cs.tech_norm = br.tech_norm
 AND cs.lac = br.lac
 AND cs.bs_id = br.bs_id;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_tmp_gps_fixed;
CREATE TABLE rebuild3_sample_meta.r2_tmp_gps_fixed AS
SELECT
  l."L0行ID" AS l0_row_id,
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."CellID" AS cell_id,
  l."基站ID" AS bs_id,
  l."原始记录ID" AS source_record_id,
  l."上报时间" AS report_time,
  l."设备标识" AS dev_id,
  l."RSRP" AS rsrp,
  l."RSRQ" AS rsrq,
  l."SINR" AS sinr,
  l."Dbm" AS dbm,
  CASE
    WHEN l."GPS有效" = true
     AND l."经度" BETWEEN 73 AND 135
     AND l."纬度" BETWEEN 3 AND 54
     AND c.gps_center_lon IS NOT NULL
     AND NOT coalesce(c.gps_anomaly, false)
     AND sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))
         <= CASE WHEN l."标准制式" LIKE '%5G%' THEN 500 ELSE 1000 END
      THEN l."经度"
    WHEN c.gps_center_lon IS NOT NULL AND NOT coalesce(c.gps_anomaly, false) THEN c.gps_center_lon
    WHEN (c.gps_center_lon IS NULL OR coalesce(c.gps_anomaly, false)) AND b.gps_center_lon IS NOT NULL AND b.gps_quality IN ('Usable', 'Risk') THEN b.gps_center_lon
    ELSE NULL
  END AS lon_final,
  CASE
    WHEN l."GPS有效" = true
     AND l."经度" BETWEEN 73 AND 135
     AND l."纬度" BETWEEN 3 AND 54
     AND c.gps_center_lon IS NOT NULL
     AND NOT coalesce(c.gps_anomaly, false)
     AND sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))
         <= CASE WHEN l."标准制式" LIKE '%5G%' THEN 500 ELSE 1000 END
      THEN l."纬度"
    WHEN c.gps_center_lon IS NOT NULL AND NOT coalesce(c.gps_anomaly, false) THEN c.gps_center_lat
    WHEN (c.gps_center_lon IS NULL OR coalesce(c.gps_anomaly, false)) AND b.gps_center_lon IS NOT NULL AND b.gps_quality IN ('Usable', 'Risk') THEN b.gps_center_lat
    ELSE NULL
  END AS lat_final,
  CASE
    WHEN l."GPS有效" = true
     AND l."经度" BETWEEN 73 AND 135
     AND l."纬度" BETWEEN 3 AND 54
     AND c.gps_center_lon IS NOT NULL
     AND NOT coalesce(c.gps_anomaly, false)
     AND sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))
         <= CASE WHEN l."标准制式" LIKE '%5G%' THEN 500 ELSE 1000 END
      THEN 'original'
    WHEN c.gps_center_lon IS NOT NULL AND NOT coalesce(c.gps_anomaly, false) THEN 'cell_center'
    WHEN (c.gps_center_lon IS NULL OR coalesce(c.gps_anomaly, false)) AND b.gps_center_lon IS NOT NULL AND b.gps_quality = 'Usable' THEN 'bs_center'
    WHEN (c.gps_center_lon IS NULL OR coalesce(c.gps_anomaly, false)) AND b.gps_center_lon IS NOT NULL AND b.gps_quality = 'Risk' THEN 'bs_center_risk'
    ELSE 'not_filled'
  END AS gps_source
FROM rebuild3_sample.source_l0_lac l
LEFT JOIN rebuild3_sample_meta.r2_dim_cell_refined c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
LEFT JOIN rebuild3_sample_meta.r2_dim_bs_refined b
  ON l."运营商编码" = b.operator_code
 AND l."标准制式" = b.tech_norm
 AND l."LAC"::text = b.lac
 AND l."基站ID" = b.bs_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_signal_s1;
DROP TABLE IF EXISTS rebuild3_sample_meta.r2_signal_ordered;
CREATE TABLE rebuild3_sample_meta.r2_signal_ordered AS
SELECT
  g.*,
  row_number() OVER (
    PARTITION BY g.operator_code, g.tech_norm, g.lac, g.cell_id
    ORDER BY g.report_time NULLS FIRST, g.l0_row_id
  ) AS seq_no
FROM rebuild3_sample_meta.r2_tmp_gps_fixed g;

CREATE INDEX IF NOT EXISTS idx_r2_signal_ordered_partition_seq
  ON rebuild3_sample_meta.r2_signal_ordered (operator_code, tech_norm, lac, cell_id, seq_no);

ANALYZE rebuild3_sample_meta.r2_signal_ordered;

CREATE TABLE rebuild3_sample_meta.r2_signal_s1 AS
SELECT
  g.l0_row_id,
  g.operator_code,
  g.tech_norm,
  g.lac,
  g.cell_id,
  g.bs_id,
  g.source_record_id,
  g.lon_final,
  g.lat_final,
  g.gps_source,
  g.report_time,
  g.dev_id,
  g.rsrp AS rsrp_raw,
  g.rsrq AS rsrq_raw,
  g.sinr AS sinr_raw,
  g.dbm AS dbm_raw,
  prev_rsrp.rsrp AS rsrp_lag,
  next_rsrp.rsrp AS rsrp_lead,
  prev_rsrq.rsrq AS rsrq_lag,
  next_rsrq.rsrq AS rsrq_lead,
  prev_sinr.sinr AS sinr_lag,
  next_sinr.sinr AS sinr_lead,
  prev_dbm.dbm AS dbm_lag,
  next_dbm.dbm AS dbm_lead
FROM rebuild3_sample_meta.r2_signal_ordered g
LEFT JOIN LATERAL (
    SELECT o.rsrp
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.rsrp IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_rsrp ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrp
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.rsrp IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_rsrp ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrq
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.rsrq IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_rsrq ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrq
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.rsrq IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_rsrq ON true
  LEFT JOIN LATERAL (
    SELECT o.sinr
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.sinr IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_sinr ON true
  LEFT JOIN LATERAL (
    SELECT o.sinr
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.sinr IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_sinr ON true
  LEFT JOIN LATERAL (
    SELECT o.dbm
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.dbm IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_dbm ON true
  LEFT JOIN LATERAL (
    SELECT o.dbm
    FROM rebuild3_sample_meta.r2_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.dbm IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_dbm ON true;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_bs_main_cell;
CREATE TABLE rebuild3_sample_meta.r2_bs_main_cell AS
SELECT DISTINCT ON (operator_code, tech_norm, lac, bs_id)
  operator_code,
  tech_norm,
  lac,
  bs_id,
  cell_id AS main_cell_id
FROM (
  SELECT operator_code, tech_norm, lac, bs_id, cell_id, count(*) AS cnt
  FROM rebuild3_sample_meta.r2_tmp_gps_fixed
  WHERE rsrp IS NOT NULL AND rsrp < 0 AND rsrp NOT IN (-1, -110)
  GROUP BY 1,2,3,4,5
) x
ORDER BY operator_code, tech_norm, lac, bs_id, cnt DESC;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_main_cell_signal;
CREATE TABLE rebuild3_sample_meta.r2_main_cell_signal AS
SELECT DISTINCT ON (g.operator_code, g.tech_norm, g.lac, g.bs_id)
  g.operator_code,
  g.tech_norm,
  g.lac,
  g.bs_id,
  g.rsrp AS bs_rsrp,
  g.rsrq AS bs_rsrq,
  g.sinr AS bs_sinr,
  g.dbm AS bs_dbm
FROM rebuild3_sample_meta.r2_tmp_gps_fixed g
JOIN rebuild3_sample_meta.r2_bs_main_cell mc
  ON g.operator_code = mc.operator_code
 AND g.tech_norm = mc.tech_norm
 AND g.lac = mc.lac
 AND g.cell_id = mc.main_cell_id
WHERE g.rsrp IS NOT NULL AND g.rsrp < 0 AND g.rsrp NOT IN (-1, -110)
ORDER BY g.operator_code, g.tech_norm, g.lac, g.bs_id, g.report_time DESC, g.l0_row_id DESC;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_dwd_fact_enriched;
CREATE TABLE rebuild3_sample_meta.r2_dwd_fact_enriched AS
SELECT
  s.l0_row_id,
  md5('r2|' || s.l0_row_id::text) AS standardized_event_id,
  s.operator_code,
  s.tech_norm,
  s.lac,
  s.cell_id,
  s.bs_id,
  s.source_record_id,
  s.lon_final,
  s.lat_final,
  s.gps_source,
  s.report_time,
  s.dev_id,
  coalesce(
    CASE WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0 AND s.rsrp_raw NOT IN (-1, -110) THEN s.rsrp_raw END,
    s.rsrp_lag,
    s.rsrp_lead,
    m.bs_rsrp
  ) AS rsrp_final,
  coalesce(CASE WHEN s.rsrq_raw IS NOT NULL THEN s.rsrq_raw END, s.rsrq_lag, s.rsrq_lead, m.bs_rsrq) AS rsrq_final,
  coalesce(CASE WHEN s.sinr_raw IS NOT NULL THEN s.sinr_raw END, s.sinr_lag, s.sinr_lead, m.bs_sinr) AS sinr_final,
  coalesce(CASE WHEN s.dbm_raw IS NOT NULL THEN s.dbm_raw END, s.dbm_lag, s.dbm_lead, m.bs_dbm) AS dbm_final,
  CASE
    WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0 AND s.rsrp_raw NOT IN (-1, -110) THEN 'original'
    WHEN coalesce(s.rsrp_lag, s.rsrp_lead) IS NOT NULL THEN 'cell_fill'
    WHEN m.bs_rsrp IS NOT NULL THEN 'bs_fill'
    ELSE 'unfilled'
  END AS signal_fill_source
FROM rebuild3_sample_meta.r2_signal_s1 s
LEFT JOIN rebuild3_sample_meta.r2_main_cell_signal m
  ON s.operator_code = m.operator_code
 AND s.tech_norm = m.tech_norm
 AND s.lac = m.lac
 AND s.bs_id = m.bs_id;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_bs_classification_ref;
CREATE TABLE rebuild3_sample_meta.r2_bs_classification_ref AS
SELECT
  bs.operator_code,
  bs.tech_norm,
  bs.lac,
  bs.bs_id,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m
FROM (
  SELECT DISTINCT operator_code, tech_norm, lac, bs_id
  FROM rebuild3_sample_meta.r2_dim_bs_refined
) bs
LEFT JOIN rebuild2._research_bs_classification_v2 cls
  ON bs.operator_code = cls.operator_code
 AND bs.tech_norm = cls.tech_norm
 AND bs.lac = cls.lac
 AND bs.bs_id = cls.bs_id;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_profile_bs;
CREATE TABLE rebuild3_sample_meta.r2_profile_bs AS
WITH center AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    bs_id,
    percentile_cont(0.5) within group (order by lon_final) FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    percentile_cont(0.5) within group (order by lat_final) FILTER (WHERE lat_final IS NOT NULL) AS center_lat
  FROM rebuild3_sample_meta.r2_dwd_fact_enriched
  GROUP BY 1,2,3,4
),
dist AS (
  SELECT
    f.operator_code,
    f.tech_norm,
    f.lac,
    f.bs_id,
    percentile_cont(0.5) within group (order by sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_p50_dist_m,
    percentile_cont(0.9) within group (order by sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_p90_dist_m,
    max(sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_max_dist_m
  FROM rebuild3_sample_meta.r2_dwd_fact_enriched f
  JOIN center c USING (operator_code, tech_norm, lac, bs_id)
  GROUP BY 1,2,3,4
)
SELECT
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  count(*) AS total_records,
  count(DISTINCT f.dev_id) AS total_devices,
  count(DISTINCT f.cell_id) AS total_cells,
  count(DISTINCT date_trunc('day', f.report_time)) FILTER (WHERE f.report_time IS NOT NULL) AS active_days,
  c.center_lon,
  c.center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  count(*) FILTER (WHERE f.gps_source = 'original') AS gps_original_cnt,
  count(*) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_valid_cnt,
  round(count(*) FILTER (WHERE f.gps_source = 'original')::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE f.lon_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS gps_valid_ratio,
  count(*) FILTER (WHERE f.signal_fill_source = 'original') AS signal_original_cnt,
  count(*) FILTER (WHERE f.rsrp_final IS NOT NULL) AS signal_valid_cnt,
  round(count(*) FILTER (WHERE f.signal_fill_source = 'original')::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  round(count(*) FILTER (WHERE f.rsrp_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_valid_ratio,
  avg(f.rsrp_final)::numeric(12,2) AS rsrp_avg,
  avg(f.rsrq_final)::numeric(12,2) AS rsrq_avg,
  avg(f.sinr_final)::numeric(12,2) AS sinr_avg,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m
FROM rebuild3_sample_meta.r2_dwd_fact_enriched f
LEFT JOIN center c USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN dist d USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN rebuild3_sample_meta.r2_bs_classification_ref cls USING (operator_code, tech_norm, lac, bs_id)
GROUP BY
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  c.center_lon,
  c.center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_profile_cell;
CREATE TABLE rebuild3_sample_meta.r2_profile_cell AS
WITH center AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    bs_id,
    cell_id,
    percentile_cont(0.5) within group (order by lon_final) FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    percentile_cont(0.5) within group (order by lat_final) FILTER (WHERE lat_final IS NOT NULL) AS center_lat
  FROM rebuild3_sample_meta.r2_dwd_fact_enriched
  GROUP BY 1,2,3,4,5
),
dist AS (
  SELECT
    f.operator_code,
    f.tech_norm,
    f.lac,
    f.bs_id,
    f.cell_id,
    percentile_cont(0.5) within group (order by sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_p50_dist_m,
    percentile_cont(0.9) within group (order by sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_p90_dist_m,
    max(sqrt(power((f.lon_final - c.center_lon) * 85300, 2) + power((f.lat_final - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_max_dist_m
  FROM rebuild3_sample_meta.r2_dwd_fact_enriched f
  JOIN center c USING (operator_code, tech_norm, lac, bs_id, cell_id)
  GROUP BY 1,2,3,4,5
)
SELECT
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  f.cell_id,
  count(*) AS total_records,
  count(DISTINCT f.dev_id) AS total_devices,
  count(DISTINCT date_trunc('day', f.report_time)) FILTER (WHERE f.report_time IS NOT NULL) AS active_days,
  c.center_lon,
  c.center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  count(*) FILTER (WHERE f.gps_source = 'original') AS gps_original_cnt,
  count(*) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_valid_cnt,
  round(count(*) FILTER (WHERE f.gps_source = 'original')::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE f.lon_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS gps_valid_ratio,
  count(*) FILTER (WHERE f.signal_fill_source = 'original') AS signal_original_cnt,
  count(*) FILTER (WHERE f.rsrp_final IS NOT NULL) AS signal_valid_cnt,
  round(count(*) FILTER (WHERE f.signal_fill_source = 'original')::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  round(count(*) FILTER (WHERE f.rsrp_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_valid_ratio,
  avg(f.rsrp_final)::numeric(12,2) AS rsrp_avg,
  avg(f.rsrq_final)::numeric(12,2) AS rsrq_avg,
  avg(f.sinr_final)::numeric(12,2) AS sinr_avg,
  cls.classification_v2 AS bs_classification
FROM rebuild3_sample_meta.r2_dwd_fact_enriched f
LEFT JOIN center c USING (operator_code, tech_norm, lac, bs_id, cell_id)
LEFT JOIN dist d USING (operator_code, tech_norm, lac, bs_id, cell_id)
LEFT JOIN rebuild3_sample_meta.r2_bs_classification_ref cls USING (operator_code, tech_norm, lac, bs_id)
GROUP BY
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  f.cell_id,
  c.center_lon,
  c.center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  cls.classification_v2;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_profile_lac;
CREATE TABLE rebuild3_sample_meta.r2_profile_lac AS
SELECT
  f.operator_code,
  f.tech_norm,
  f.lac,
  count(*) AS total_records,
  count(DISTINCT f.bs_id) AS total_bs,
  count(DISTINCT f.cell_id) AS total_cells,
  count(DISTINCT f.dev_id) AS total_devices,
  count(DISTINCT date_trunc('day', f.report_time)) FILTER (WHERE f.report_time IS NOT NULL) AS active_days,
  percentile_cont(0.5) within group (order by f.lon_final) FILTER (WHERE f.lon_final IS NOT NULL) AS center_lon,
  percentile_cont(0.5) within group (order by f.lat_final) FILTER (WHERE f.lat_final IS NOT NULL) AS center_lat,
  count(*) FILTER (WHERE f.gps_source = 'original') AS gps_original_cnt,
  count(*) FILTER (WHERE f.lon_final IS NOT NULL) AS gps_valid_cnt,
  round(count(*) FILTER (WHERE f.gps_source = 'original')::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE f.lon_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS gps_valid_ratio,
  count(*) FILTER (WHERE f.signal_fill_source = 'original') AS signal_original_cnt,
  count(*) FILTER (WHERE f.rsrp_final IS NOT NULL) AS signal_valid_cnt,
  round(count(*) FILTER (WHERE f.signal_fill_source = 'original')::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  round(count(*) FILTER (WHERE f.rsrp_final IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_valid_ratio,
  avg(f.rsrp_final)::numeric(12,2) AS rsrp_avg,
  avg(f.rsrq_final)::numeric(12,2) AS rsrq_avg,
  avg(f.sinr_final)::numeric(12,2) AS sinr_avg
FROM rebuild3_sample_meta.r2_dwd_fact_enriched f
GROUP BY 1,2,3;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_cell_state;
CREATE TABLE rebuild3_sample_meta.r2_cell_state AS
SELECT
  md5('r2-cell|' || cs.operator_code || '|' || cs.tech_norm || '|' || cs.lac || '|' || cs.cell_id::text) AS object_id,
  cs.operator_code,
  cs.tech_norm,
  cs.lac,
  cs.bs_id,
  cs.cell_id,
  CASE
    WHEN cs.record_count < 5 THEN 'waiting'
    WHEN cs.record_count >= 5 AND (coalesce(cs.valid_gps_count, 0) < 10 OR cs.distinct_device_count < 2) THEN 'observing'
    ELSE 'active'
  END AS lifecycle_state,
  CASE
    WHEN cls.classification_v2 = 'dynamic_bs' THEN 'dynamic'
    WHEN cls.classification_v2 = 'collision_suspected' THEN 'collision_suspect'
    WHEN cls.classification_v2 = 'collision_confirmed' THEN 'collision_confirmed'
    WHEN cls.classification_v2 = 'collision_uncertain' THEN 'collision_suspect'
    WHEN coalesce(cr.gps_anomaly, false) THEN 'gps_bias'
    ELSE 'healthy'
  END AS health_state,
  (cs.record_count >= 5 AND cs.distinct_device_count >= 1 AND cs.active_days >= 1) AS existence_eligible,
  (
    coalesce(cls.classification_v2, '') NOT IN ('dynamic_bs', 'collision_suspected', 'collision_confirmed', 'collision_uncertain')
    AND coalesce(cr.gps_anomaly, false) = false
    AND coalesce(cr.gps_count, 0) >= 10
    AND cs.distinct_device_count >= 2
    AND cs.active_days >= 1
    AND coalesce(pc.gps_p90_dist_m, 999999) <= 1500
  ) AS anchorable,
  (
    coalesce(cls.classification_v2, '') NOT IN ('dynamic_bs', 'collision_suspected', 'collision_confirmed', 'collision_uncertain')
    AND coalesce(cr.gps_anomaly, false) = false
    AND coalesce(cr.gps_count, 0) >= 20
    AND cs.distinct_device_count >= 2
    AND cs.active_days >= 3
    AND coalesce(pc.signal_original_ratio, 0) >= 0.5
    AND coalesce(pc.gps_p90_dist_m, 999999) <= 1500
  ) AS baseline_eligible,
  cs.record_count,
  coalesce(cr.gps_count, cs.valid_gps_count) AS gps_count,
  cs.distinct_device_count AS device_count,
  cs.active_days,
  coalesce(pc.center_lon, cs.gps_center_lon) AS centroid_lon,
  coalesce(pc.center_lat, cs.gps_center_lat) AS centroid_lat,
  pc.gps_p50_dist_m,
  pc.gps_p90_dist_m,
  pc.gps_original_ratio,
  pc.signal_original_ratio,
  CASE
    WHEN cls.classification_v2 IN ('single_large', 'normal_spread') THEN ARRAY[cls.classification_v2]
    WHEN cls.classification_v2 IS NOT NULL THEN ARRAY[cls.classification_v2]
    WHEN coalesce(cr.gps_anomaly, false) THEN ARRAY['gps_bias']
    ELSE ARRAY[]::text[]
  END AS anomaly_tags
FROM rebuild3_sample_meta.r2_dim_cell_stats cs
LEFT JOIN rebuild3_sample_meta.r2_dim_cell_refined cr
  ON cs.operator_code = cr.operator_code
 AND cs.tech_norm = cr.tech_norm
 AND cs.lac = cr.lac
 AND cs.cell_id = cr.cell_id
LEFT JOIN rebuild3_sample_meta.r2_bs_classification_ref cls
  ON cs.operator_code = cls.operator_code
 AND cs.tech_norm = cls.tech_norm
 AND cs.lac = cls.lac
 AND cs.bs_id = cls.bs_id
LEFT JOIN rebuild3_sample_meta.r2_profile_cell pc
  ON cs.operator_code = pc.operator_code
 AND cs.tech_norm = pc.tech_norm
 AND cs.lac = pc.lac
 AND cs.bs_id = pc.bs_id
 AND cs.cell_id = pc.cell_id;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_bs_state;
CREATE TABLE rebuild3_sample_meta.r2_bs_state AS
SELECT
  md5('r2-bs|' || b.operator_code || '|' || b.tech_norm || '|' || b.lac || '|' || b.bs_id::text) AS object_id,
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  CASE WHEN b.record_count >= 5 THEN 'active' ELSE 'observing' END AS lifecycle_state,
  CASE
    WHEN cls.classification_v2 = 'dynamic_bs' THEN 'dynamic'
    WHEN cls.classification_v2 = 'collision_suspected' THEN 'collision_suspect'
    WHEN cls.classification_v2 = 'collision_confirmed' THEN 'collision_confirmed'
    WHEN cls.classification_v2 = 'collision_uncertain' THEN 'collision_suspect'
    WHEN b.gps_quality = 'Unusable' THEN 'insufficient'
    ELSE 'healthy'
  END AS health_state,
  (b.record_count >= 5) AS existence_eligible,
  (
    coalesce(cls.classification_v2, '') NOT IN ('dynamic_bs', 'collision_suspected', 'collision_confirmed', 'collision_uncertain')
    AND b.gps_quality = 'Usable'
    AND coalesce(p.signal_original_ratio, 0) >= 0.3
  ) AS anchorable,
  (
    coalesce(cls.classification_v2, '') NOT IN ('dynamic_bs', 'collision_suspected', 'collision_confirmed', 'collision_uncertain')
    AND b.gps_quality = 'Usable'
    AND b.total_gps_points >= 20
    AND b.max_active_days >= 3
    AND coalesce(p.signal_original_ratio, 0) >= 0.5
  ) AS baseline_eligible,
  b.cell_count,
  count(c.object_id) FILTER (WHERE c.lifecycle_state = 'active') AS active_cell_count,
  b.record_count::bigint,
  b.total_gps_points::bigint AS gps_count,
  b.distinct_device_count::bigint AS device_count,
  b.max_active_days::integer AS active_days,
  b.gps_center_lon AS center_lon,
  b.gps_center_lat AS center_lat,
  b.gps_p50_dist_m,
  b.gps_p90_dist_m,
  p.gps_original_ratio,
  p.signal_original_ratio,
  CASE WHEN cls.classification_v2 IS NOT NULL THEN ARRAY[cls.classification_v2] ELSE ARRAY[]::text[] END AS anomaly_tags
FROM rebuild3_sample_meta.r2_dim_bs_refined b
LEFT JOIN rebuild3_sample_meta.r2_bs_classification_ref cls USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN rebuild3_sample_meta.r2_profile_bs p USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN rebuild3_sample_meta.r2_cell_state c USING (operator_code, tech_norm, lac, bs_id)
GROUP BY
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  b.record_count,
  b.gps_quality,
  b.total_gps_points,
  b.max_active_days,
  b.cell_count,
  b.distinct_device_count,
  b.gps_center_lon,
  b.gps_center_lat,
  b.gps_p50_dist_m,
  b.gps_p90_dist_m,
  p.gps_original_ratio,
  p.signal_original_ratio,
  cls.classification_v2;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_lac_state;
CREATE TABLE rebuild3_sample_meta.r2_lac_state AS
WITH anomaly_flat AS (
  SELECT
    b.operator_code,
    b.tech_norm,
    b.lac,
    tag
  FROM rebuild3_sample_meta.r2_bs_state b
  CROSS JOIN LATERAL unnest(coalesce(b.anomaly_tags, ARRAY[]::text[])) AS tag
),
anomaly_agg AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    array_remove(array_agg(DISTINCT tag), NULL) AS anomaly_tags
  FROM anomaly_flat
  GROUP BY 1,2,3
)
SELECT
  md5('r2-lac|' || b.operator_code || '|' || b.tech_norm || '|' || b.lac) AS object_id,
  b.operator_code,
  b.tech_norm,
  b.lac,
  CASE WHEN sum(case when b.lifecycle_state = 'active' then 1 else 0 end) > 0 THEN 'active' ELSE 'observing' END AS lifecycle_state,
  CASE
    WHEN sum(case when b.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic') then 1 else 0 end) > 0 THEN 'collision_suspect'
    WHEN sum(case when b.lifecycle_state = 'active' then 1 else 0 end) = 0 THEN 'insufficient'
    ELSE 'healthy'
  END AS health_state,
  (count(*) > 0) AS existence_eligible,
  (sum(case when b.anchorable then 1 else 0 end) > 0) AS anchorable,
  (sum(case when b.baseline_eligible then 1 else 0 end) > 0) AS baseline_eligible,
  count(*) AS bs_count,
  sum(case when b.lifecycle_state = 'active' then 1 else 0 end) AS active_bs_count,
  sum(b.cell_count) AS cell_count,
  sum(b.record_count) AS record_count,
  sum(b.gps_count) AS gps_count,
  max(b.active_days) AS active_days,
  percentile_cont(0.5) within group (order by b.center_lon) FILTER (WHERE b.center_lon IS NOT NULL) AS center_lon,
  percentile_cont(0.5) within group (order by b.center_lat) FILTER (WHERE b.center_lat IS NOT NULL) AS center_lat,
  avg(b.gps_original_ratio)::numeric(12,4) AS gps_original_ratio,
  avg(b.signal_original_ratio)::numeric(12,4) AS signal_original_ratio,
  CASE
    WHEN sum(case when b.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic') then 1 else 0 end) > 0 THEN 'issue_present'
    WHEN sum(case when b.lifecycle_state = 'active' then 1 else 0 end) = 0 THEN 'coverage_insufficient'
    ELSE NULL
  END AS region_quality_label,
  coalesce(a.anomaly_tags, ARRAY[]::text[]) AS anomaly_tags
FROM rebuild3_sample_meta.r2_bs_state b
LEFT JOIN anomaly_agg a
  ON b.operator_code = a.operator_code
 AND b.tech_norm = a.tech_norm
 AND b.lac = a.lac
GROUP BY b.operator_code, b.tech_norm, b.lac, a.anomaly_tags;

DROP TABLE IF EXISTS rebuild3_sample_meta.r2_fact_semantic;
CREATE TABLE rebuild3_sample_meta.r2_fact_semantic AS
SELECT
  md5('r2|' || l."L0行ID"::text) AS standardized_event_id,
  l."L0行ID" AS source_row_id,
  l."原始记录ID" AS source_record_id,
  l.scenario,
  l.scope_type,
  l."上报时间" AS event_time,
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."基站ID" AS bs_id,
  l."CellID" AS cell_id,
  l."设备标识" AS dev_id,
  CASE
    WHEN l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL THEN 'fact_rejected'
    WHEN bs.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN 'fact_pending_issue'
    WHEN cs.lifecycle_state IN ('waiting', 'observing') THEN 'fact_pending_observation'
    ELSE 'fact_governed'
  END AS fact_route,
  cs.lifecycle_state,
  coalesce(cs.health_state, 'insufficient') AS health_state,
  coalesce(cs.anchorable, false) AS anchorable,
  coalesce(cs.baseline_eligible, false) AS baseline_eligible,
  CASE
    WHEN l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL THEN 'missing_operator_or_lac_or_cell'
    WHEN bs.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN 'object_level_issue'
    WHEN cs.lifecycle_state IN ('waiting', 'observing') THEN 'insufficient_object_evidence'
    ELSE 'governed_or_record_level_only'
  END AS route_reason,
  CASE
    WHEN cls.classification_v2 IN ('single_large', 'normal_spread') THEN ARRAY[cls.classification_v2]
    WHEN cls.classification_v2 IS NOT NULL THEN ARRAY[cls.classification_v2]
    WHEN coalesce(cs.health_state, 'healthy') = 'gps_bias' THEN ARRAY['gps_bias']
    ELSE ARRAY[]::text[]
  END AS anomaly_tags
FROM rebuild3_sample.source_l0_lac l
LEFT JOIN rebuild3_sample_meta.r2_cell_state cs
  ON l."运营商编码" = cs.operator_code
 AND l."标准制式" = cs.tech_norm
 AND l."LAC"::text = cs.lac
 AND l."CellID" = cs.cell_id
LEFT JOIN rebuild3_sample_meta.r2_bs_state bs
  ON l."运营商编码" = bs.operator_code
 AND l."标准制式" = bs.tech_norm
 AND l."LAC"::text = bs.lac
 AND l."基站ID" = bs.bs_id
LEFT JOIN rebuild3_sample_meta.r2_bs_classification_ref cls
  ON l."运营商编码" = cls.operator_code
 AND l."标准制式" = cls.tech_norm
 AND l."LAC"::text = cls.lac
 AND l."基站ID" = cls.bs_id;
