SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

DROP TABLE IF EXISTS rebuild3_meta.r2_full_route_summary;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_lac_state;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_bs_state;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_cell_state;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_profile_lac;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_profile_cell;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_profile_bs;
DROP TABLE IF EXISTS rebuild3_meta.r2_full_bs_classification_ref;

CREATE TABLE rebuild3_meta.r2_full_bs_classification_ref AS
SELECT
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m
FROM rebuild2.dim_bs_refined b
LEFT JOIN rebuild2._research_bs_classification_v2 cls
  ON b.operator_code = cls.operator_code
 AND b.tech_norm = cls.tech_norm
 AND b.lac = cls.lac
 AND b.bs_id = cls.bs_id;

CREATE INDEX IF NOT EXISTS idx_r2_full_bs_classification_ref
  ON rebuild3_meta.r2_full_bs_classification_ref (operator_code, tech_norm, lac, bs_id);

CREATE TABLE rebuild3_meta.r2_full_profile_bs AS
SELECT
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  b.record_count::bigint AS total_records,
  b.distinct_device_count::bigint AS total_devices,
  b.cell_count::bigint AS total_cells,
  b.max_active_days::integer AS active_days,
  b.gps_center_lon AS center_lon,
  b.gps_center_lat AS center_lat,
  b.gps_p50_dist_m,
  b.gps_p90_dist_m,
  b.gps_max_dist_m,
  b.total_gps_points::bigint AS gps_valid_cnt,
  round(b.total_gps_points::numeric / nullif(b.record_count, 0), 4) AS gps_valid_ratio,
  r.gps_original_ratio,
  r.signal_original_ratio,
  r.rsrp_avg,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m
FROM rebuild2.dim_bs_refined b
LEFT JOIN rebuild3.stg_bs_ratio r
  ON b.operator_code = r.operator_code
 AND b.tech_norm = r.tech_norm
 AND b.lac = r.lac
 AND b.bs_id = r.bs_id
LEFT JOIN rebuild3_meta.r2_full_bs_classification_ref cls
  ON b.operator_code = cls.operator_code
 AND b.tech_norm = cls.tech_norm
 AND b.lac = cls.lac
 AND b.bs_id = cls.bs_id;

CREATE INDEX IF NOT EXISTS idx_r2_full_profile_bs
  ON rebuild3_meta.r2_full_profile_bs (operator_code, tech_norm, lac, bs_id);

CREATE TABLE rebuild3_meta.r2_full_profile_cell AS
SELECT
  cs.operator_code,
  cs.tech_norm,
  cs.lac,
  cs.bs_id,
  cs.cell_id,
  cs.record_count::bigint AS total_records,
  cs.distinct_device_count::bigint AS total_devices,
  cs.active_days,
  coalesce(cr.gps_center_lon, cs.gps_center_lon) AS center_lon,
  coalesce(cr.gps_center_lat, cs.gps_center_lat) AS center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  coalesce(cr.gps_count, cs.valid_gps_count)::bigint AS gps_valid_cnt,
  round(coalesce(cr.gps_count, cs.valid_gps_count)::numeric / nullif(cs.record_count, 0), 4) AS gps_valid_ratio,
  r.gps_original_ratio,
  r.signal_original_ratio,
  r.rsrp_avg,
  cls.classification_v2 AS bs_classification
FROM rebuild2.dim_cell_stats cs
LEFT JOIN rebuild2.dim_cell_refined cr
  ON cs.operator_code = cr.operator_code
 AND cs.tech_norm = cr.tech_norm
 AND cs.lac = cr.lac
 AND cs.cell_id = cr.cell_id
LEFT JOIN rebuild3.stg_cell_dist d
  ON cs.operator_code = d.operator_code
 AND cs.tech_norm = d.tech_norm
 AND cs.lac = d.lac
 AND cs.bs_id = d.bs_id
 AND cs.cell_id = d.cell_id
LEFT JOIN rebuild3.stg_cell_ratio r
  ON cs.operator_code = r.operator_code
 AND cs.tech_norm = r.tech_norm
 AND cs.lac = r.lac
 AND cs.bs_id = r.bs_id
 AND cs.cell_id = r.cell_id
LEFT JOIN rebuild3_meta.r2_full_bs_classification_ref cls
  ON cs.operator_code = cls.operator_code
 AND cs.tech_norm = cls.tech_norm
 AND cs.lac = cls.lac
 AND cs.bs_id = cls.bs_id;

CREATE INDEX IF NOT EXISTS idx_r2_full_profile_cell
  ON rebuild3_meta.r2_full_profile_cell (operator_code, tech_norm, lac, bs_id, cell_id);

CREATE TABLE rebuild3_meta.r2_full_profile_lac AS
SELECT
  lp.operator_code,
  lp.tech_norm,
  lp.lac,
  lp.record_count::bigint AS total_records,
  lp.bs_count::bigint AS total_bs,
  lp.cell_count::bigint AS total_cells,
  lp.active_days,
  lp.center_lon,
  lp.center_lat,
  lp.gps_original_ratio,
  lp.signal_original_ratio
FROM rebuild3.stg_lac_profile lp;

CREATE INDEX IF NOT EXISTS idx_r2_full_profile_lac
  ON rebuild3_meta.r2_full_profile_lac (operator_code, tech_norm, lac);

CREATE TABLE rebuild3_meta.r2_full_cell_state AS
SELECT
  'cell|' || cs.operator_code || '|' || cs.tech_norm || '|' || cs.lac || '|' || cs.cell_id::text AS object_id,
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
FROM rebuild2.dim_cell_stats cs
LEFT JOIN rebuild2.dim_cell_refined cr
  ON cs.operator_code = cr.operator_code
 AND cs.tech_norm = cr.tech_norm
 AND cs.lac = cr.lac
 AND cs.cell_id = cr.cell_id
LEFT JOIN rebuild3_meta.r2_full_bs_classification_ref cls
  ON cs.operator_code = cls.operator_code
 AND cs.tech_norm = cls.tech_norm
 AND cs.lac = cls.lac
 AND cs.bs_id = cls.bs_id
LEFT JOIN rebuild3_meta.r2_full_profile_cell pc
  ON cs.operator_code = pc.operator_code
 AND cs.tech_norm = pc.tech_norm
 AND cs.lac = pc.lac
 AND cs.bs_id = pc.bs_id
 AND cs.cell_id = pc.cell_id;

CREATE INDEX IF NOT EXISTS idx_r2_full_cell_state_key
  ON rebuild3_meta.r2_full_cell_state (operator_code, tech_norm, lac, cell_id);
CREATE INDEX IF NOT EXISTS idx_r2_full_cell_state_bs
  ON rebuild3_meta.r2_full_cell_state (operator_code, tech_norm, lac, bs_id);

CREATE TABLE rebuild3_meta.r2_full_bs_state AS
WITH bs_child AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    bs_id,
    count(*) AS child_cell_count,
    count(*) FILTER (WHERE lifecycle_state = 'active') AS active_cell_count,
    count(*) FILTER (WHERE anchorable) AS anchorable_cell_count,
    count(*) FILTER (WHERE baseline_eligible) AS baseline_cell_count
  FROM rebuild3_meta.r2_full_cell_state
  GROUP BY 1,2,3,4
)
SELECT
  'bs|' || b.operator_code || '|' || b.tech_norm || '|' || b.lac || '|' || b.bs_id::text AS object_id,
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  CASE WHEN coalesce(bc.active_cell_count, 0) > 0 THEN 'active' ELSE 'observing' END AS lifecycle_state,
  CASE
    WHEN cls.classification_v2 = 'dynamic_bs' THEN 'dynamic'
    WHEN cls.classification_v2 = 'collision_suspected' THEN 'collision_suspect'
    WHEN cls.classification_v2 = 'collision_confirmed' THEN 'collision_confirmed'
    WHEN cls.classification_v2 = 'collision_uncertain' THEN 'collision_suspect'
    WHEN coalesce(bc.active_cell_count, 0) = 0 THEN 'insufficient'
    WHEN b.gps_quality = 'Unusable' THEN 'insufficient'
    ELSE 'healthy'
  END AS health_state,
  (coalesce(bc.child_cell_count, 0) > 0) AS existence_eligible,
  (coalesce(bc.anchorable_cell_count, 0) > 0) AS anchorable,
  (coalesce(bc.baseline_cell_count, 0) > 0) AS baseline_eligible,
  b.cell_count,
  coalesce(bc.active_cell_count, 0) AS active_cell_count,
  b.record_count::bigint AS record_count,
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
FROM rebuild2.dim_bs_refined b
LEFT JOIN rebuild3_meta.r2_full_bs_classification_ref cls
  ON b.operator_code = cls.operator_code
 AND b.tech_norm = cls.tech_norm
 AND b.lac = cls.lac
 AND b.bs_id = cls.bs_id
LEFT JOIN rebuild3_meta.r2_full_profile_bs p
  ON b.operator_code = p.operator_code
 AND b.tech_norm = p.tech_norm
 AND b.lac = p.lac
 AND b.bs_id = p.bs_id
LEFT JOIN bs_child bc
  ON b.operator_code = bc.operator_code
 AND b.tech_norm = bc.tech_norm
 AND b.lac = bc.lac
 AND b.bs_id = bc.bs_id;

CREATE INDEX IF NOT EXISTS idx_r2_full_bs_state_key
  ON rebuild3_meta.r2_full_bs_state (operator_code, tech_norm, lac, bs_id);

CREATE TABLE rebuild3_meta.r2_full_lac_state AS
WITH lac_bs AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    count(*) AS bs_obj_count,
    count(*) FILTER (WHERE lifecycle_state = 'active') AS active_bs_count,
    count(*) FILTER (WHERE anchorable) AS anchorable_bs_count,
    count(*) FILTER (WHERE baseline_eligible) AS baseline_bs_count,
    count(*) FILTER (WHERE health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic')) AS issue_bs_count
  FROM rebuild3_meta.r2_full_bs_state
  GROUP BY 1,2,3
),
anomaly_flat AS (
  SELECT
    b.operator_code,
    b.tech_norm,
    b.lac,
    tag
  FROM rebuild3_meta.r2_full_bs_state b
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
  'lac|' || lp.operator_code || '|' || lp.tech_norm || '|' || lp.lac AS object_id,
  lp.operator_code,
  lp.tech_norm,
  lp.lac,
  CASE WHEN coalesce(lb.active_bs_count, 0) > 0 THEN 'active' ELSE 'observing' END AS lifecycle_state,
  CASE
    WHEN coalesce(lb.issue_bs_count, 0) > 0 THEN 'collision_suspect'
    WHEN coalesce(lb.active_bs_count, 0) = 0 THEN 'insufficient'
    ELSE 'healthy'
  END AS health_state,
  (lp.total_records > 0) AS existence_eligible,
  (coalesce(lb.anchorable_bs_count, 0) > 0) AS anchorable,
  (coalesce(lb.baseline_bs_count, 0) > 0) AS baseline_eligible,
  lp.total_bs AS bs_count,
  coalesce(lb.active_bs_count, 0) AS active_bs_count,
  lp.total_cells AS cell_count,
  lp.total_records AS record_count,
  round(lp.total_records * coalesce(lp.gps_original_ratio, 0), 0)::bigint AS gps_count,
  lp.active_days,
  lp.center_lon,
  lp.center_lat,
  lp.gps_original_ratio,
  lp.signal_original_ratio,
  CASE
    WHEN coalesce(lb.issue_bs_count, 0) > 0 THEN 'issue_present'
    WHEN coalesce(lb.active_bs_count, 0) = 0 THEN 'coverage_insufficient'
    ELSE NULL
  END AS region_quality_label,
  coalesce(a.anomaly_tags, ARRAY[]::text[]) AS anomaly_tags
FROM rebuild3_meta.r2_full_profile_lac lp
LEFT JOIN lac_bs lb
  ON lp.operator_code = lb.operator_code
 AND lp.tech_norm = lb.tech_norm
 AND lp.lac = lb.lac
LEFT JOIN anomaly_agg a
  ON lp.operator_code = a.operator_code
 AND lp.tech_norm = a.tech_norm
 AND lp.lac = a.lac;

CREATE INDEX IF NOT EXISTS idx_r2_full_lac_state_key
  ON rebuild3_meta.r2_full_lac_state (operator_code, tech_norm, lac);

CREATE TABLE rebuild3_meta.r2_full_route_summary AS
SELECT
  fact_route,
  sum(row_count)::bigint AS row_count
FROM (
  SELECT
    CASE
      WHEN bs.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN 'fact_pending_issue'
      WHEN cs.lifecycle_state IN ('waiting', 'observing') THEN 'fact_pending_observation'
      ELSE 'fact_governed'
    END AS fact_route,
    cs.record_count AS row_count
  FROM rebuild3_meta.r2_full_cell_state cs
  LEFT JOIN rebuild3_meta.r2_full_bs_state bs
    ON cs.operator_code = bs.operator_code
   AND cs.tech_norm = bs.tech_norm
   AND cs.lac = bs.lac
   AND cs.bs_id = bs.bs_id

  UNION ALL

  SELECT
    'fact_pending_observation' AS fact_route,
    (
      (SELECT count(*)::bigint
       FROM rebuild2.l0_lac
       WHERE "运营商编码" IS NOT NULL
         AND "LAC" IS NOT NULL
         AND "CellID" IS NOT NULL)
      - coalesce((SELECT sum(record_count)::bigint FROM rebuild3_meta.r2_full_cell_state), 0)
    ) AS row_count

  UNION ALL

  SELECT
    'fact_rejected' AS fact_route,
    count(*)::bigint AS row_count
  FROM rebuild2.l0_lac l
  WHERE l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL
) x
GROUP BY fact_route;
