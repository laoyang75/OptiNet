SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

TRUNCATE TABLE
  rebuild3.fact_standardized,
  rebuild3.fact_governed,
  rebuild3.fact_pending_observation,
  rebuild3.fact_pending_issue,
  rebuild3.fact_rejected,
  rebuild3.obj_cell,
  rebuild3.obj_bs,
  rebuild3.obj_lac,
  rebuild3.obj_state_history,
  rebuild3.obj_relation_history,
  rebuild3.baseline_cell,
  rebuild3.baseline_bs,
  rebuild3.baseline_lac;

TRUNCATE TABLE
  rebuild3_meta.run,
  rebuild3_meta.batch,
  rebuild3_meta.baseline_version,
  rebuild3_meta.batch_snapshot,
  rebuild3_meta.batch_flow_summary,
  rebuild3_meta.batch_decision_summary,
  rebuild3_meta.batch_anomaly_summary,
  rebuild3_meta.batch_baseline_refresh_log,
  rebuild3_meta.compare_result;

INSERT INTO rebuild3_meta.run (
  run_id, run_type, status, window_start, window_end, contract_version, rule_set_version, baseline_version, note
)
VALUES (
  'RUN-FULL-20251201-20251207-V1',
  'full_initialization',
  'running',
  '2025-12-01 00:00:00+08',
  '2025-12-07 23:59:59+08',
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  'full initialization using rebuild2 l0_lac fast path'
);

INSERT INTO rebuild3_meta.batch (
  batch_id, run_id, batch_type, status, window_start, window_end, source_name,
  contract_version, rule_set_version, baseline_version, input_rows, output_rows, is_rerun
)
SELECT
  'BATCH-FULL-20251201-20251207-V1',
  'RUN-FULL-20251201-20251207-V1',
  'full_init',
  'running',
  '2025-12-01 00:00:00+08',
  '2025-12-07 23:59:59+08',
  'rebuild2.l0_lac',
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  count(*),
  null,
  false
FROM rebuild2.l0_lac;

DROP TABLE IF EXISTS rebuild3.stg_bs_classification_ref;
CREATE TABLE rebuild3.stg_bs_classification_ref AS
SELECT
  b.operator_code,
  b.tech_norm,
  b.lac,
  b.bs_id,
  cls.classification_v2,
  cls.device_cross_rate,
  cls.static_cell_span_m,
  CASE
    WHEN cls.classification_v2 = 'dynamic_bs' THEN 'dynamic'
    WHEN cls.classification_v2 = 'collision_suspected' THEN 'collision_suspect'
    WHEN cls.classification_v2 = 'collision_confirmed' THEN 'collision_confirmed'
    WHEN cls.classification_v2 = 'collision_uncertain' THEN 'collision_suspect'
    ELSE NULL
  END AS mapped_health_state
FROM rebuild2.dim_bs_refined b
LEFT JOIN rebuild2._research_bs_classification_v2 cls
  ON b.operator_code = cls.operator_code
 AND b.tech_norm = cls.tech_norm
 AND b.lac = cls.lac
 AND b.bs_id = cls.bs_id;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_bs_classification_ref
  ON rebuild3.stg_bs_classification_ref (operator_code, tech_norm, lac, bs_id);

DROP TABLE IF EXISTS rebuild3.stg_cell_dist;
CREATE TABLE rebuild3.stg_cell_dist AS
SELECT
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."基站ID" AS bs_id,
  l."CellID" AS cell_id,
  percentile_cont(0.5) within group (
    order by sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))::numeric
  ) AS gps_p50_dist_m,
  percentile_cont(0.9) within group (
    order by sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))::numeric
  ) AS gps_p90_dist_m,
  max(sqrt(power((l."经度" - c.gps_center_lon) * 85300, 2) + power((l."纬度" - c.gps_center_lat) * 111000, 2))::numeric) AS gps_max_dist_m
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_cell_refined c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND l."GPS有效"
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54
  AND c.gps_center_lon IS NOT NULL
GROUP BY 1,2,3,4,5;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_cell_dist
  ON rebuild3.stg_cell_dist (operator_code, tech_norm, lac, bs_id, cell_id);

DROP TABLE IF EXISTS rebuild3.stg_cell_ratio;
CREATE TABLE rebuild3.stg_cell_ratio AS
SELECT
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."基站ID" AS bs_id,
  l."CellID" AS cell_id,
  round(count(*) FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110))::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  avg(CASE WHEN l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110) THEN l."RSRP" END)::numeric(12,2) AS rsrp_avg
FROM rebuild2.l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
GROUP BY 1,2,3,4,5;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_cell_ratio
  ON rebuild3.stg_cell_ratio (operator_code, tech_norm, lac, bs_id, cell_id);

DROP TABLE IF EXISTS rebuild3.stg_cell_profile;
CREATE TABLE rebuild3.stg_cell_profile AS
SELECT
  cs.operator_code,
  cs.operator_cn,
  cs.tech_norm,
  cs.lac,
  cs.bs_id,
  cs.cell_id,
  cs.sector_id,
  cs.record_count,
  cs.distinct_device_count AS device_count,
  cs.active_days,
  coalesce(cr.gps_count, cs.valid_gps_count) AS gps_count,
  coalesce(cr.gps_center_lon, cs.gps_center_lon) AS center_lon,
  coalesce(cr.gps_center_lat, cs.gps_center_lat) AS center_lat,
  d.gps_p50_dist_m,
  d.gps_p90_dist_m,
  d.gps_max_dist_m,
  r.gps_original_ratio,
  r.signal_original_ratio,
  r.rsrp_avg,
  coalesce(cr.gps_anomaly, false) AS gps_anomaly,
  cr.dist_to_bs_m,
  cr.bs_gps_quality
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
 AND cs.cell_id = r.cell_id;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_cell_profile
  ON rebuild3.stg_cell_profile (operator_code, tech_norm, lac, bs_id, cell_id);

DROP TABLE IF EXISTS rebuild3.stg_bs_ratio;
CREATE TABLE rebuild3.stg_bs_ratio AS
SELECT
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  l."基站ID" AS bs_id,
  round(count(*) FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110))::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  avg(CASE WHEN l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110) THEN l."RSRP" END)::numeric(12,2) AS rsrp_avg
FROM rebuild2.l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
GROUP BY 1,2,3,4;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_bs_ratio
  ON rebuild3.stg_bs_ratio (operator_code, tech_norm, lac, bs_id);

DROP TABLE IF EXISTS rebuild3.stg_bs_profile;
CREATE TABLE rebuild3.stg_bs_profile AS
SELECT
  b.operator_code,
  b.operator_cn,
  b.tech_norm,
  b.lac,
  b.bs_id,
  b.cell_count,
  b.record_count::bigint AS record_count,
  b.distinct_device_count::bigint AS device_count,
  b.max_active_days::integer AS active_days,
  b.gps_center_lon AS center_lon,
  b.gps_center_lat AS center_lat,
  b.total_gps_points::bigint AS gps_count,
  b.gps_p50_dist_m,
  b.gps_p90_dist_m,
  b.gps_max_dist_m,
  b.gps_quality,
  r.gps_original_ratio,
  r.signal_original_ratio,
  r.rsrp_avg
FROM rebuild2.dim_bs_refined b
LEFT JOIN rebuild3.stg_bs_ratio r
  ON b.operator_code = r.operator_code
 AND b.tech_norm = r.tech_norm
 AND b.lac = r.lac
 AND b.bs_id = r.bs_id;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_bs_profile
  ON rebuild3.stg_bs_profile (operator_code, tech_norm, lac, bs_id);

DROP TABLE IF EXISTS rebuild3.stg_lac_profile;
CREATE TABLE rebuild3.stg_lac_profile AS
SELECT
  l."运营商编码" AS operator_code,
  l."标准制式" AS tech_norm,
  l."LAC"::text AS lac,
  count(*) AS record_count,
  count(DISTINCT l."基站ID") AS bs_count,
  count(DISTINCT l."CellID") AS cell_count,
  count(DISTINCT date_trunc('day', l."上报时间")) FILTER (WHERE l."上报时间" IS NOT NULL) AS active_days,
  percentile_cont(0.5) within group (order by l."经度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS center_lon,
  percentile_cont(0.5) within group (order by l."纬度") FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54) AS center_lat,
  round(count(*) FILTER (WHERE l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110))::numeric / nullif(count(*), 0), 4) AS signal_original_ratio
FROM rebuild2.l0_lac l
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
GROUP BY 1,2,3;

CREATE INDEX IF NOT EXISTS idx_rebuild3_stg_lac_profile
  ON rebuild3.stg_lac_profile (operator_code, tech_norm, lac);

INSERT INTO rebuild3.obj_cell (
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, lifecycle_state, health_state,
  existence_eligible, anchorable, baseline_eligible, record_count, gps_count, device_count,
  active_days, centroid_lon, centroid_lat, gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio,
  signal_original_ratio, anomaly_tags, parent_bs_object_id, run_id, batch_id, baseline_version, sample_scope_tag
)
SELECT
  'cell|' || cp.operator_code || '|' || cp.tech_norm || '|' || cp.lac || '|' || cp.cell_id::text,
  cp.operator_code,
  cp.tech_norm,
  cp.lac,
  cp.bs_id,
  cp.cell_id,
  CASE
    WHEN cp.record_count < 5 THEN 'waiting'
    WHEN cp.record_count >= 5 AND (cp.gps_count < 10 OR cp.device_count < 2) THEN 'observing'
    ELSE 'active'
  END AS lifecycle_state,
  CASE
    WHEN br.mapped_health_state IS NOT NULL THEN br.mapped_health_state
    WHEN coalesce(cp.gps_p90_dist_m, 0) > 1500 THEN 'gps_bias'
    ELSE 'healthy'
  END AS health_state,
  (cp.record_count >= 5 AND cp.device_count >= 1 AND cp.active_days >= 1),
  (
    br.mapped_health_state IS NULL
    AND cp.gps_count >= 10 AND cp.device_count >= 2 AND cp.active_days >= 1
    AND coalesce(cp.gps_p90_dist_m, 999999) <= 1500
  ) AS anchorable,
  (
    br.mapped_health_state IS NULL
    AND cp.gps_count >= 20 AND cp.device_count >= 2 AND cp.active_days >= 3
    AND coalesce(cp.signal_original_ratio, 0) >= 0.5
    AND coalesce(cp.gps_p90_dist_m, 999999) <= 1500
  ) AS baseline_eligible,
  cp.record_count,
  cp.gps_count,
  cp.device_count,
  cp.active_days,
  cp.center_lon,
  cp.center_lat,
  cp.gps_p50_dist_m,
  cp.gps_p90_dist_m,
  cp.gps_original_ratio,
  cp.signal_original_ratio,
  CASE
    WHEN br.classification_v2 IN ('single_large', 'normal_spread') THEN ARRAY[br.classification_v2]
    WHEN br.classification_v2 IS NOT NULL THEN ARRAY[br.classification_v2]
    WHEN coalesce(cp.gps_p90_dist_m, 0) > 1500 THEN ARRAY['gps_bias']
    ELSE ARRAY[]::text[]
  END,
  'bs|' || cp.operator_code || '|' || cp.tech_norm || '|' || cp.lac || '|' || cp.bs_id::text,
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1',
  'BASELINE-FULL-V1',
  null
FROM rebuild3.stg_cell_profile cp
LEFT JOIN rebuild3.stg_bs_classification_ref br
  ON cp.operator_code = br.operator_code
 AND cp.tech_norm = br.tech_norm
 AND cp.lac = br.lac
 AND cp.bs_id = br.bs_id;

CREATE INDEX IF NOT EXISTS idx_rebuild3_obj_cell_key
  ON rebuild3.obj_cell (operator_code, tech_norm, lac, cell_id);
CREATE INDEX IF NOT EXISTS idx_rebuild3_obj_cell_bs
  ON rebuild3.obj_cell (operator_code, tech_norm, lac, bs_id);

INSERT INTO rebuild3.obj_bs (
  object_id, operator_code, tech_norm, lac, bs_id, lifecycle_state, health_state,
  existence_eligible, anchorable, baseline_eligible, cell_count, active_cell_count,
  record_count, gps_count, device_count, active_days, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio, anomaly_tags,
  parent_lac_object_id, run_id, batch_id, baseline_version, sample_scope_tag
)
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
  FROM rebuild3.obj_cell
  GROUP BY 1,2,3,4
)
SELECT
  'bs|' || bp.operator_code || '|' || bp.tech_norm || '|' || bp.lac || '|' || bp.bs_id::text,
  bp.operator_code,
  bp.tech_norm,
  bp.lac,
  bp.bs_id,
  CASE WHEN coalesce(bc.active_cell_count, 0) > 0 THEN 'active' ELSE 'observing' END,
  CASE
    WHEN br.mapped_health_state IS NOT NULL THEN br.mapped_health_state
    WHEN coalesce(bc.active_cell_count, 0) = 0 THEN 'insufficient'
    WHEN bp.gps_count < 3 THEN 'insufficient'
    WHEN coalesce(bp.gps_p90_dist_m, 0) > 4000 THEN 'insufficient'
    ELSE 'healthy'
  END,
  (coalesce(bc.child_cell_count, 0) > 0),
  (coalesce(bc.anchorable_cell_count, 0) > 0),
  (coalesce(bc.baseline_cell_count, 0) > 0),
  bp.cell_count,
  coalesce(bc.active_cell_count, 0),
  bp.record_count,
  bp.gps_count,
  bp.device_count,
  bp.active_days,
  bp.center_lon,
  bp.center_lat,
  bp.gps_p50_dist_m,
  bp.gps_p90_dist_m,
  bp.gps_original_ratio,
  bp.signal_original_ratio,
  CASE WHEN br.classification_v2 IS NOT NULL THEN ARRAY[br.classification_v2] ELSE ARRAY[]::text[] END,
  'lac|' || bp.operator_code || '|' || bp.tech_norm || '|' || bp.lac,
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1',
  'BASELINE-FULL-V1',
  null
FROM rebuild3.stg_bs_profile bp
LEFT JOIN rebuild3.stg_bs_classification_ref br
  ON bp.operator_code = br.operator_code
 AND bp.tech_norm = br.tech_norm
 AND bp.lac = br.lac
 AND bp.bs_id = br.bs_id
LEFT JOIN bs_child bc
  ON bp.operator_code = bc.operator_code
 AND bp.tech_norm = bc.tech_norm
 AND bp.lac = bc.lac
 AND bp.bs_id = bc.bs_id;

CREATE INDEX IF NOT EXISTS idx_rebuild3_obj_bs_key
  ON rebuild3.obj_bs (operator_code, tech_norm, lac, bs_id);

INSERT INTO rebuild3.obj_lac (
  object_id, operator_code, tech_norm, lac, lifecycle_state, health_state,
  existence_eligible, anchorable, baseline_eligible, bs_count, active_bs_count, cell_count,
  record_count, gps_count, active_days, center_lon, center_lat, gps_original_ratio,
  signal_original_ratio, region_quality_label, anomaly_tags, run_id, batch_id, baseline_version, sample_scope_tag
)
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
  FROM rebuild3.obj_bs
  GROUP BY 1,2,3
),
lac_cls AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    array_remove(array_agg(DISTINCT classification_v2), NULL) AS anomaly_tags
  FROM rebuild3.stg_bs_classification_ref
  GROUP BY 1,2,3
)
SELECT
  'lac|' || lp.operator_code || '|' || lp.tech_norm || '|' || lp.lac,
  lp.operator_code,
  lp.tech_norm,
  lp.lac,
  CASE WHEN coalesce(lb.active_bs_count, 0) > 0 THEN 'active' ELSE 'observing' END,
  CASE
    WHEN coalesce(lb.issue_bs_count, 0) > 0 THEN 'collision_suspect'
    WHEN coalesce(lb.active_bs_count, 0) = 0 THEN 'insufficient'
    ELSE 'healthy'
  END,
  (coalesce(lb.bs_obj_count, 0) > 0),
  (coalesce(lb.anchorable_bs_count, 0) > 0),
  (coalesce(lb.baseline_bs_count, 0) > 0),
  lp.bs_count,
  coalesce(lb.active_bs_count, 0),
  lp.cell_count,
  lp.record_count,
  round(lp.record_count * coalesce(lp.gps_original_ratio, 0), 0)::bigint,
  lp.active_days,
  lp.center_lon,
  lp.center_lat,
  lp.gps_original_ratio,
  lp.signal_original_ratio,
  CASE
    WHEN coalesce(lb.issue_bs_count, 0) > 0 THEN 'issue_present'
    WHEN coalesce(lb.active_bs_count, 0) = 0 THEN 'coverage_insufficient'
    ELSE NULL
  END,
  coalesce(lc.anomaly_tags, ARRAY[]::text[]),
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1',
  'BASELINE-FULL-V1',
  null
FROM rebuild3.stg_lac_profile lp
LEFT JOIN lac_bs lb
  ON lp.operator_code = lb.operator_code
 AND lp.tech_norm = lb.tech_norm
 AND lp.lac = lb.lac
LEFT JOIN lac_cls lc
  ON lp.operator_code = lc.operator_code
 AND lp.tech_norm = lc.tech_norm
 AND lp.lac = lc.lac;

INSERT INTO rebuild3.obj_state_history (object_type, object_id, lifecycle_state, health_state, anchorable, baseline_eligible, changed_reason, run_id, batch_id)
SELECT 'cell', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'full_init_snapshot', run_id, batch_id
FROM rebuild3.obj_cell
UNION ALL
SELECT 'bs', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'full_init_snapshot', run_id, batch_id
FROM rebuild3.obj_bs
UNION ALL
SELECT 'lac', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'full_init_snapshot', run_id, batch_id
FROM rebuild3.obj_lac;

INSERT INTO rebuild3.obj_relation_history (relation_type, parent_object_id, child_object_id, relation_status, changed_reason, run_id, batch_id)
SELECT 'bs_cell', parent_bs_object_id, object_id, 'active', 'full_init_snapshot', run_id, batch_id
FROM rebuild3.obj_cell
UNION ALL
SELECT 'lac_bs', parent_lac_object_id, object_id, 'active', 'full_init_snapshot', run_id, batch_id
FROM rebuild3.obj_bs;

INSERT INTO rebuild3.fact_standardized (
  standardized_event_id, source_name, source_row_id, source_record_id, event_time,
  operator_code, tech_norm, lac, bs_id, cell_id, dev_id, raw_lon, raw_lat, gps_valid,
  rsrp_raw, rsrq_raw, sinr_raw, dbm_raw, structural_valid, route_reason, sample_scope_tag,
  contract_version, rule_set_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."L0行ID",
  l."原始记录ID",
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  l."经度",
  l."纬度",
  l."GPS有效",
  l."RSRP",
  l."RSRQ",
  l."SINR",
  l."Dbm",
  (l."运营商编码" IS NOT NULL AND l."LAC" IS NOT NULL AND l."CellID" IS NOT NULL),
  CASE
    WHEN l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL THEN 'missing_operator_or_lac_or_cell'
    ELSE 'valid_key'
  END,
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l;

INSERT INTO rebuild3.fact_rejected (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  rejection_reason, sample_scope_tag, contract_version, rule_set_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  'missing_operator_or_lac_or_cell',
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l
WHERE l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL;

INSERT INTO rebuild3.fact_pending_issue (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  health_state, anomaly_tags, baseline_eligible, route_reason, sample_scope_tag, contract_version,
  rule_set_version, baseline_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  c.health_state,
  c.anomaly_tags,
  false,
  'object_level_issue',
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l
JOIN rebuild3.obj_cell c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND c.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias');

INSERT INTO rebuild3.fact_pending_observation (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  route_reason, missing_layer, anomaly_tags, sample_scope_tag, contract_version, rule_set_version,
  baseline_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  'insufficient_object_evidence',
  CASE WHEN c.lifecycle_state = 'waiting' THEN 'existence' ELSE 'anchorable' END,
  c.anomaly_tags,
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l
JOIN rebuild3.obj_cell c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
  AND c.lifecycle_state IN ('waiting', 'observing');

INSERT INTO rebuild3.fact_pending_observation (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  route_reason, missing_layer, anomaly_tags, sample_scope_tag, contract_version, rule_set_version,
  baseline_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  'missing_object_registration',
  'existence',
  ARRAY[]::text[],
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l
LEFT JOIN rebuild3.obj_cell c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND c.object_id IS NULL;

INSERT INTO rebuild3.fact_governed (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  lon_final, lat_final, gps_source, signal_source, anomaly_tags, baseline_eligible, route_reason,
  sample_scope_tag, contract_version, rule_set_version, baseline_version, run_id, batch_id
)
SELECT
  'r3|' || l."L0行ID"::text,
  'rebuild2.l0_lac',
  l."上报时间",
  l."运营商编码",
  l."标准制式",
  l."LAC"::text,
  l."基站ID",
  l."CellID",
  l."设备标识",
  CASE
    WHEN l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54
         AND coalesce(c.gps_p90_dist_m, 999999) <= 1500
      THEN l."经度"
    WHEN c.centroid_lon IS NOT NULL AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
      THEN c.centroid_lon
    WHEN b.center_lon IS NOT NULL
      THEN b.center_lon
    ELSE NULL
  END AS lon_final,
  CASE
    WHEN l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54
         AND coalesce(c.gps_p90_dist_m, 999999) <= 1500
      THEN l."纬度"
    WHEN c.centroid_lat IS NOT NULL AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
      THEN c.centroid_lat
    WHEN b.center_lat IS NOT NULL
      THEN b.center_lat
    ELSE NULL
  END AS lat_final,
  CASE
    WHEN l."GPS有效" AND l."经度" BETWEEN 73 AND 135 AND l."纬度" BETWEEN 3 AND 54
         AND coalesce(c.gps_p90_dist_m, 999999) <= 1500
      THEN 'original'
    WHEN c.centroid_lon IS NOT NULL AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
      THEN 'cell_center'
    WHEN b.center_lon IS NOT NULL
      THEN 'bs_center'
    ELSE 'not_filled'
  END AS gps_source,
  CASE
    WHEN l."RSRP" IS NOT NULL AND l."RSRP" < 0 AND l."RSRP" NOT IN (-1, -110) THEN 'original'
    ELSE 'unfilled'
  END AS signal_source,
  c.anomaly_tags,
  c.baseline_eligible,
  CASE
    WHEN cardinality(c.anomaly_tags) > 0 THEN 'record_level_anomaly_but_governed'
    ELSE 'healthy_or_manageable_record'
  END,
  null,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-FULL-V1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1'
FROM rebuild2.l0_lac l
JOIN rebuild3.obj_cell c
  ON l."运营商编码" = c.operator_code
 AND l."标准制式" = c.tech_norm
 AND l."LAC"::text = c.lac
 AND l."CellID" = c.cell_id
LEFT JOIN rebuild3.obj_bs b
  ON l."运营商编码" = b.operator_code
 AND l."标准制式" = b.tech_norm
 AND l."LAC"::text = b.lac
 AND l."基站ID" = b.bs_id
WHERE l."运营商编码" IS NOT NULL
  AND l."LAC" IS NOT NULL
  AND l."CellID" IS NOT NULL
  AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
  AND c.lifecycle_state NOT IN ('waiting', 'observing');

INSERT INTO rebuild3.baseline_cell (
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, baseline_version, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, 'BASELINE-FULL-V1', centroid_lon, centroid_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
FROM rebuild3.obj_cell
WHERE baseline_eligible;

INSERT INTO rebuild3.baseline_bs (
  object_id, operator_code, tech_norm, lac, bs_id, baseline_version, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, bs_id, 'BASELINE-FULL-V1', center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
FROM rebuild3.obj_bs
WHERE baseline_eligible;

INSERT INTO rebuild3.baseline_lac (
  object_id, operator_code, tech_norm, lac, baseline_version, center_lon, center_lat, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, 'BASELINE-FULL-V1', center_lon, center_lat, gps_original_ratio, signal_original_ratio
FROM rebuild3.obj_lac
WHERE baseline_eligible;

INSERT INTO rebuild3_meta.baseline_version (
  baseline_version, run_id, batch_id, rule_set_version, refresh_reason, object_count
)
SELECT
  'BASELINE-FULL-V1',
  'RUN-FULL-20251201-20251207-V1',
  'BATCH-FULL-20251201-20251207-V1',
  'rebuild3-rule-set-v1',
  'full_initial_baseline',
  (SELECT count(*) FROM rebuild3.baseline_cell)
    + (SELECT count(*) FROM rebuild3.baseline_bs)
    + (SELECT count(*) FROM rebuild3.baseline_lac);

INSERT INTO rebuild3_meta.batch_flow_summary (batch_id, fact_layer, row_count, row_ratio)
SELECT
  'BATCH-FULL-20251201-20251207-V1',
  fact_layer,
  row_count,
  round(row_count::numeric / nullif(total_rows, 0), 4)
FROM (
  SELECT 'fact_governed' AS fact_layer, (SELECT count(*) FROM rebuild3.fact_governed) AS row_count,
         (SELECT count(*) FROM rebuild3.fact_standardized) AS total_rows
  UNION ALL
  SELECT 'fact_pending_observation', (SELECT count(*) FROM rebuild3.fact_pending_observation), (SELECT count(*) FROM rebuild3.fact_standardized)
  UNION ALL
  SELECT 'fact_pending_issue', (SELECT count(*) FROM rebuild3.fact_pending_issue), (SELECT count(*) FROM rebuild3.fact_standardized)
  UNION ALL
  SELECT 'fact_rejected', (SELECT count(*) FROM rebuild3.fact_rejected), (SELECT count(*) FROM rebuild3.fact_standardized)
) x;

INSERT INTO rebuild3_meta.batch_decision_summary (batch_id, decision_name, object_type, object_count)
SELECT 'BATCH-FULL-20251201-20251207-V1', 'lifecycle_distribution', 'cell:' || lifecycle_state, count(*)
FROM rebuild3.obj_cell
GROUP BY lifecycle_state
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'lifecycle_distribution', 'bs:' || lifecycle_state, count(*)
FROM rebuild3.obj_bs
GROUP BY lifecycle_state
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'lifecycle_distribution', 'lac:' || lifecycle_state, count(*)
FROM rebuild3.obj_lac
GROUP BY lifecycle_state;

INSERT INTO rebuild3_meta.batch_anomaly_summary (batch_id, anomaly_level, anomaly_name, object_count, fact_count)
SELECT 'BATCH-FULL-20251201-20251207-V1', 'cell_object', health_state, count(*), NULL::bigint
FROM rebuild3.obj_cell
GROUP BY health_state
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'bs_object', health_state, count(*), NULL::bigint
FROM rebuild3.obj_bs
GROUP BY health_state
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'record', 'normal_spread', NULL::bigint, count(*)::bigint
FROM rebuild3.fact_governed
WHERE anomaly_tags && ARRAY['normal_spread']
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'record', 'single_large', NULL::bigint, count(*)::bigint
FROM rebuild3.fact_governed
WHERE anomaly_tags && ARRAY['single_large']
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'record', 'gps_fill', NULL::bigint, count(*)::bigint
FROM rebuild3.fact_governed
WHERE coalesce(gps_source, 'original') <> 'original'
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'record', 'signal_fill', NULL::bigint, count(*)::bigint
FROM rebuild3.fact_governed
WHERE coalesce(signal_source, 'original') <> 'original'
UNION ALL
SELECT 'BATCH-FULL-20251201-20251207-V1', 'record', 'structural_rejected', NULL::bigint, count(*)::bigint
FROM rebuild3.fact_rejected;

INSERT INTO rebuild3_meta.batch_baseline_refresh_log (batch_id, baseline_version, refresh_reason, triggered)
VALUES ('BATCH-FULL-20251201-20251207-V1', 'BASELINE-FULL-V1', 'full_initial_baseline', true);

INSERT INTO rebuild3_meta.batch_snapshot (batch_id, stage_name, metric_name, metric_value)
VALUES
  ('BATCH-FULL-20251201-20251207-V1', 'input', 'fact_standardized', (SELECT count(*) FROM rebuild3.fact_standardized)),
  ('BATCH-FULL-20251201-20251207-V1', 'routing', 'fact_governed', (SELECT count(*) FROM rebuild3.fact_governed)),
  ('BATCH-FULL-20251201-20251207-V1', 'routing', 'fact_pending_observation', (SELECT count(*) FROM rebuild3.fact_pending_observation)),
  ('BATCH-FULL-20251201-20251207-V1', 'routing', 'fact_pending_issue', (SELECT count(*) FROM rebuild3.fact_pending_issue)),
  ('BATCH-FULL-20251201-20251207-V1', 'routing', 'fact_rejected', (SELECT count(*) FROM rebuild3.fact_rejected)),
  ('BATCH-FULL-20251201-20251207-V1', 'objects', 'obj_cell', (SELECT count(*) FROM rebuild3.obj_cell)),
  ('BATCH-FULL-20251201-20251207-V1', 'objects', 'obj_bs', (SELECT count(*) FROM rebuild3.obj_bs)),
  ('BATCH-FULL-20251201-20251207-V1', 'objects', 'obj_lac', (SELECT count(*) FROM rebuild3.obj_lac)),
  ('BATCH-FULL-20251201-20251207-V1', 'baseline', 'baseline_cell', (SELECT count(*) FROM rebuild3.baseline_cell)),
  ('BATCH-FULL-20251201-20251207-V1', 'baseline', 'baseline_bs', (SELECT count(*) FROM rebuild3.baseline_bs)),
  ('BATCH-FULL-20251201-20251207-V1', 'baseline', 'baseline_lac', (SELECT count(*) FROM rebuild3.baseline_lac));

UPDATE rebuild3_meta.batch
SET status = 'completed',
    output_rows = (SELECT count(*) FROM rebuild3.fact_standardized)
WHERE batch_id = 'BATCH-FULL-20251201-20251207-V1';

UPDATE rebuild3_meta.run
SET status = 'completed'
WHERE run_id = 'RUN-FULL-20251201-20251207-V1';
