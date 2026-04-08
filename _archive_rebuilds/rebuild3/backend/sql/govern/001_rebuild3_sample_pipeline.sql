SET statement_timeout = 0;
SET work_mem = '256MB';

TRUNCATE TABLE
  rebuild3_sample.fact_standardized,
  rebuild3_sample.fact_governed,
  rebuild3_sample.fact_pending_observation,
  rebuild3_sample.fact_pending_issue,
  rebuild3_sample.fact_rejected,
  rebuild3_sample.obj_cell,
  rebuild3_sample.obj_bs,
  rebuild3_sample.obj_lac,
  rebuild3_sample.obj_state_history,
  rebuild3_sample.obj_relation_history,
  rebuild3_sample.baseline_cell,
  rebuild3_sample.baseline_bs,
  rebuild3_sample.baseline_lac;

TRUNCATE TABLE
  rebuild3_sample_meta.run,
  rebuild3_sample_meta.batch,
  rebuild3_sample_meta.baseline_version,
  rebuild3_sample_meta.batch_snapshot,
  rebuild3_sample_meta.batch_flow_summary,
  rebuild3_sample_meta.batch_decision_summary,
  rebuild3_sample_meta.batch_anomaly_summary,
  rebuild3_sample_meta.batch_baseline_refresh_log,
  rebuild3_sample_meta.compare_result;

INSERT INTO rebuild3_sample_meta.run (
  run_id, run_type, status, window_start, window_end, contract_version, rule_set_version, baseline_version, note
)
VALUES (
  'RUN-SAMPLE-20251201-20251207-V1',
  'sample_validation',
  'running',
  '2025-12-01 00:00:00+08',
  '2025-12-07 23:59:59+08',
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-SAMPLE-V1',
  'same-sample rebuild2 vs rebuild3 validation'
);

INSERT INTO rebuild3_sample_meta.batch (
  batch_id, run_id, batch_type, status, window_start, window_end, source_name,
  contract_version, rule_set_version, baseline_version, input_rows, output_rows, is_rerun
)
SELECT
  'BATCH-SAMPLE-20251201-20251207-V1',
  'RUN-SAMPLE-20251201-20251207-V1',
  'sample_init',
  'running',
  '2025-12-01 00:00:00+08',
  '2025-12-07 23:59:59+08',
  'rebuild3_sample.source_l0_lac',
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'BASELINE-SAMPLE-V1',
  count(*),
  null,
  false
FROM rebuild3_sample.source_l0_lac;

INSERT INTO rebuild3_sample.fact_standardized (
  standardized_event_id, source_name, source_row_id, source_record_id, event_time,
  operator_code, tech_norm, lac, bs_id, cell_id, dev_id, raw_lon, raw_lat, gps_valid,
  rsrp_raw, rsrq_raw, sinr_raw, dbm_raw, structural_valid, route_reason, sample_scope_tag,
  contract_version, rule_set_version, run_id, batch_id
)
SELECT
  md5('r3|' || l."L0行ID"::text),
  'source_l0_lac',
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
  l.scenario,
  'rebuild3-contract-v1',
  'rebuild3-rule-set-v1',
  'RUN-SAMPLE-20251201-20251207-V1',
  'BATCH-SAMPLE-20251201-20251207-V1'
FROM rebuild3_sample.source_l0_lac l;

DROP TABLE IF EXISTS rebuild3_sample.stg_bs_classification_ref;
CREATE TABLE rebuild3_sample.stg_bs_classification_ref AS
SELECT
  bs.operator_code,
  bs.tech_norm,
  bs.lac,
  bs.bs_id,
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
FROM (
  SELECT DISTINCT operator_code, tech_norm, lac, bs_id
  FROM rebuild3_sample.fact_standardized
  WHERE structural_valid
) bs
LEFT JOIN rebuild2._research_bs_classification_v2 cls
  ON bs.operator_code = cls.operator_code
 AND bs.tech_norm = cls.tech_norm
 AND bs.lac = cls.lac
 AND bs.bs_id = cls.bs_id;

DROP TABLE IF EXISTS rebuild3_sample.stg_cell_profile;
CREATE TABLE rebuild3_sample.stg_cell_profile AS
WITH center AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    bs_id,
    cell_id,
    percentile_cont(0.5) within group (order by raw_lon) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lon,
    percentile_cont(0.5) within group (order by raw_lat) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lat
  FROM rebuild3_sample.fact_standardized
  WHERE structural_valid
  GROUP BY 1,2,3,4,5
),
dist AS (
  SELECT
    f.operator_code,
    f.tech_norm,
    f.lac,
    f.bs_id,
    f.cell_id,
    percentile_cont(0.5) within group (order by sqrt(power((f.raw_lon - c.center_lon) * 85300, 2) + power((f.raw_lat - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_p50_dist_m,
    percentile_cont(0.9) within group (order by sqrt(power((f.raw_lon - c.center_lon) * 85300, 2) + power((f.raw_lat - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_p90_dist_m
  FROM rebuild3_sample.fact_standardized f
  JOIN center c USING (operator_code, tech_norm, lac, bs_id, cell_id)
  WHERE f.structural_valid
  GROUP BY 1,2,3,4,5
)
SELECT
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  f.cell_id,
  count(*) AS record_count,
  count(DISTINCT f.dev_id) AS device_count,
  count(DISTINCT date_trunc('day', f.event_time)) FILTER (WHERE f.event_time IS NOT NULL) AS active_days,
  count(*) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_count,
  center.center_lon,
  center.center_lat,
  dist.gps_p50_dist_m,
  dist.gps_p90_dist_m,
  round(count(*) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE f.rsrp_raw IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  avg(f.rsrp_raw)::numeric(12,2) AS rsrp_avg,
  string_agg(DISTINCT f.sample_scope_tag, ',') AS scenario_tags
FROM rebuild3_sample.fact_standardized f
LEFT JOIN center USING (operator_code, tech_norm, lac, bs_id, cell_id)
LEFT JOIN dist USING (operator_code, tech_norm, lac, bs_id, cell_id)
WHERE f.structural_valid
GROUP BY 1,2,3,4,5,10,11,12,13;

DROP TABLE IF EXISTS rebuild3_sample.stg_bs_profile;
CREATE TABLE rebuild3_sample.stg_bs_profile AS
WITH center AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    bs_id,
    percentile_cont(0.5) within group (order by raw_lon) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lon,
    percentile_cont(0.5) within group (order by raw_lat) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lat
  FROM rebuild3_sample.fact_standardized
  WHERE structural_valid
  GROUP BY 1,2,3,4
),
dist AS (
  SELECT
    f.operator_code,
    f.tech_norm,
    f.lac,
    f.bs_id,
    percentile_cont(0.5) within group (order by sqrt(power((f.raw_lon - c.center_lon) * 85300, 2) + power((f.raw_lat - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_p50_dist_m,
    percentile_cont(0.9) within group (order by sqrt(power((f.raw_lon - c.center_lon) * 85300, 2) + power((f.raw_lat - c.center_lat) * 111000, 2))::numeric) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_p90_dist_m
  FROM rebuild3_sample.fact_standardized f
  JOIN center c USING (operator_code, tech_norm, lac, bs_id)
  WHERE f.structural_valid
  GROUP BY 1,2,3,4
)
SELECT
  f.operator_code,
  f.tech_norm,
  f.lac,
  f.bs_id,
  count(*) AS record_count,
  count(DISTINCT f.dev_id) AS device_count,
  count(DISTINCT f.cell_id) AS cell_count,
  count(DISTINCT date_trunc('day', f.event_time)) FILTER (WHERE f.event_time IS NOT NULL) AS active_days,
  count(*) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54) AS gps_count,
  center.center_lon,
  center.center_lat,
  dist.gps_p50_dist_m,
  dist.gps_p90_dist_m,
  round(count(*) FILTER (WHERE f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE f.rsrp_raw IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  avg(f.rsrp_raw)::numeric(12,2) AS rsrp_avg,
  string_agg(DISTINCT f.sample_scope_tag, ',') AS scenario_tags
FROM rebuild3_sample.fact_standardized f
LEFT JOIN center USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN dist USING (operator_code, tech_norm, lac, bs_id)
WHERE f.structural_valid
GROUP BY 1,2,3,4,10,11,12,13;

DROP TABLE IF EXISTS rebuild3_sample.stg_lac_profile;
CREATE TABLE rebuild3_sample.stg_lac_profile AS
SELECT
  operator_code,
  tech_norm,
  lac,
  count(*) AS record_count,
  count(DISTINCT bs_id) AS bs_count,
  count(DISTINCT cell_id) AS cell_count,
  count(DISTINCT date_trunc('day', event_time)) FILTER (WHERE event_time IS NOT NULL) AS active_days,
  percentile_cont(0.5) within group (order by raw_lon) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lon,
  percentile_cont(0.5) within group (order by raw_lat) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54) AS center_lat,
  round(count(*) FILTER (WHERE gps_valid AND raw_lon BETWEEN 73 AND 135 AND raw_lat BETWEEN 3 AND 54)::numeric / nullif(count(*), 0), 4) AS gps_original_ratio,
  round(count(*) FILTER (WHERE rsrp_raw IS NOT NULL)::numeric / nullif(count(*), 0), 4) AS signal_original_ratio,
  string_agg(DISTINCT sample_scope_tag, ',') AS scenario_tags
FROM rebuild3_sample.fact_standardized
WHERE structural_valid
GROUP BY 1,2,3;

DROP TABLE IF EXISTS rebuild3_sample.stg_signal_fact;
DROP TABLE IF EXISTS rebuild3_sample.stg_signal_ordered;
CREATE TABLE rebuild3_sample.stg_signal_ordered AS
WITH gps_fixed AS (
  SELECT
    f.standardized_event_id,
    f.source_name,
    f.source_row_id,
    f.source_record_id,
    f.event_time,
    f.operator_code,
    f.tech_norm,
    f.lac,
    f.bs_id,
    f.cell_id,
    f.dev_id,
    CASE
      WHEN f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54 AND cp.center_lon IS NOT NULL
           AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic')
           AND coalesce(cp.gps_p90_dist_m, 999999) <= 1500
        THEN f.raw_lon
      WHEN cp.center_lon IS NOT NULL AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN cp.center_lon
      WHEN bp.center_lon IS NOT NULL THEN bp.center_lon
      ELSE NULL
    END AS lon_final,
    CASE
      WHEN f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54 AND cp.center_lon IS NOT NULL
           AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic')
           AND coalesce(cp.gps_p90_dist_m, 999999) <= 1500
        THEN f.raw_lat
      WHEN cp.center_lon IS NOT NULL AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN cp.center_lat
      WHEN bp.center_lon IS NOT NULL THEN bp.center_lat
      ELSE NULL
    END AS lat_final,
    CASE
      WHEN f.gps_valid AND f.raw_lon BETWEEN 73 AND 135 AND f.raw_lat BETWEEN 3 AND 54 AND cp.center_lon IS NOT NULL
           AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic')
           AND coalesce(cp.gps_p90_dist_m, 999999) <= 1500
        THEN 'original'
      WHEN cp.center_lon IS NOT NULL AND coalesce(br.mapped_health_state, 'healthy') NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic') THEN 'cell_center'
      WHEN bp.center_lon IS NOT NULL THEN 'bs_center'
      ELSE 'not_filled'
    END AS gps_source,
    f.rsrp_raw,
    f.rsrq_raw,
    f.sinr_raw,
    f.dbm_raw,
    f.sample_scope_tag
  FROM rebuild3_sample.fact_standardized f
  LEFT JOIN rebuild3_sample.stg_cell_profile cp USING (operator_code, tech_norm, lac, bs_id, cell_id)
  LEFT JOIN rebuild3_sample.stg_bs_profile bp USING (operator_code, tech_norm, lac, bs_id)
  LEFT JOIN rebuild3_sample.stg_bs_classification_ref br USING (operator_code, tech_norm, lac, bs_id)
  WHERE f.structural_valid
)
SELECT
  g.*,
  row_number() OVER (
    PARTITION BY g.operator_code, g.tech_norm, g.lac, g.cell_id
    ORDER BY g.event_time NULLS FIRST, g.source_row_id
  ) AS seq_no
FROM gps_fixed g;

CREATE INDEX IF NOT EXISTS idx_r3_signal_ordered_partition_seq
  ON rebuild3_sample.stg_signal_ordered (operator_code, tech_norm, lac, cell_id, seq_no);

ANALYZE rebuild3_sample.stg_signal_ordered;

CREATE TABLE rebuild3_sample.stg_signal_fact AS
WITH windowed AS (
  SELECT
    g.standardized_event_id,
    g.source_name,
    g.source_row_id,
    g.source_record_id,
    g.event_time,
    g.operator_code,
    g.tech_norm,
    g.lac,
    g.bs_id,
    g.cell_id,
    g.dev_id,
    g.lon_final,
    g.lat_final,
    g.gps_source,
    g.rsrp_raw,
    g.rsrq_raw,
    g.sinr_raw,
    g.dbm_raw,
    g.sample_scope_tag,
    prev_rsrp.rsrp AS rsrp_lag,
    next_rsrp.rsrp AS rsrp_lead,
    prev_rsrq.rsrq AS rsrq_lag,
    next_rsrq.rsrq AS rsrq_lead,
    prev_sinr.sinr AS sinr_lag,
    next_sinr.sinr AS sinr_lead,
    prev_dbm.dbm AS dbm_lag,
    next_dbm.dbm AS dbm_lead
  FROM rebuild3_sample.stg_signal_ordered g
  LEFT JOIN LATERAL (
    SELECT o.rsrp_raw AS rsrp
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.rsrp_raw IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_rsrp ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrp_raw AS rsrp
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.rsrp_raw IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_rsrp ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrq_raw AS rsrq
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.rsrq_raw IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_rsrq ON true
  LEFT JOIN LATERAL (
    SELECT o.rsrq_raw AS rsrq
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.rsrq_raw IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_rsrq ON true
  LEFT JOIN LATERAL (
    SELECT o.sinr_raw AS sinr
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.sinr_raw IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_sinr ON true
  LEFT JOIN LATERAL (
    SELECT o.sinr_raw AS sinr
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.sinr_raw IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_sinr ON true
  LEFT JOIN LATERAL (
    SELECT o.dbm_raw AS dbm
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no < g.seq_no
      AND o.dbm_raw IS NOT NULL
    ORDER BY o.seq_no DESC
    LIMIT 1
  ) prev_dbm ON true
  LEFT JOIN LATERAL (
    SELECT o.dbm_raw AS dbm
    FROM rebuild3_sample.stg_signal_ordered o
    WHERE o.operator_code = g.operator_code
      AND o.tech_norm = g.tech_norm
      AND o.lac = g.lac
      AND o.cell_id = g.cell_id
      AND o.seq_no > g.seq_no
      AND o.dbm_raw IS NOT NULL
    ORDER BY o.seq_no ASC
    LIMIT 1
  ) next_dbm ON true
),
main_cell AS (
  SELECT DISTINCT ON (operator_code, tech_norm, lac, bs_id)
    operator_code,
    tech_norm,
    lac,
    bs_id,
    cell_id AS main_cell_id
  FROM (
    SELECT operator_code, tech_norm, lac, bs_id, cell_id, count(*) AS cnt
    FROM windowed
    WHERE rsrp_raw IS NOT NULL AND rsrp_raw < 0 AND rsrp_raw NOT IN (-1, -110)
    GROUP BY 1,2,3,4,5
  ) x
  ORDER BY operator_code, tech_norm, lac, bs_id, cnt DESC
),
main_signal AS (
  SELECT DISTINCT ON (w.operator_code, w.tech_norm, w.lac, w.bs_id)
    w.operator_code,
    w.tech_norm,
    w.lac,
    w.bs_id,
    w.rsrp_raw AS bs_rsrp,
    w.rsrq_raw AS bs_rsrq,
    w.sinr_raw AS bs_sinr,
    w.dbm_raw AS bs_dbm
  FROM windowed w
  JOIN main_cell m
    ON w.operator_code = m.operator_code
   AND w.tech_norm = m.tech_norm
   AND w.lac = m.lac
   AND w.cell_id = m.main_cell_id
  WHERE w.rsrp_raw IS NOT NULL AND w.rsrp_raw < 0 AND w.rsrp_raw NOT IN (-1, -110)
  ORDER BY w.operator_code, w.tech_norm, w.lac, w.bs_id, w.event_time DESC, w.source_row_id DESC
)
SELECT
  w.*,
  coalesce(
    CASE WHEN w.rsrp_raw IS NOT NULL AND w.rsrp_raw < 0 AND w.rsrp_raw NOT IN (-1, -110) THEN w.rsrp_raw END,
    w.rsrp_lag,
    w.rsrp_lead,
    ms.bs_rsrp
  ) AS rsrp_final,
  coalesce(CASE WHEN w.rsrq_raw IS NOT NULL THEN w.rsrq_raw END, w.rsrq_lag, w.rsrq_lead, ms.bs_rsrq) AS rsrq_final,
  coalesce(CASE WHEN w.sinr_raw IS NOT NULL THEN w.sinr_raw END, w.sinr_lag, w.sinr_lead, ms.bs_sinr) AS sinr_final,
  coalesce(CASE WHEN w.dbm_raw IS NOT NULL THEN w.dbm_raw END, w.dbm_lag, w.dbm_lead, ms.bs_dbm) AS dbm_final,
  CASE
    WHEN w.rsrp_raw IS NOT NULL AND w.rsrp_raw < 0 AND w.rsrp_raw NOT IN (-1, -110) THEN 'original'
    WHEN coalesce(w.rsrp_lag, w.rsrp_lead) IS NOT NULL THEN 'cell_fill'
    WHEN ms.bs_rsrp IS NOT NULL THEN 'bs_fill'
    ELSE 'unfilled'
  END AS signal_source
FROM windowed w
LEFT JOIN main_signal ms
  ON w.operator_code = ms.operator_code
 AND w.tech_norm = ms.tech_norm
 AND w.lac = ms.lac
 AND w.bs_id = ms.bs_id;

INSERT INTO rebuild3_sample.obj_cell (
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, lifecycle_state, health_state,
  existence_eligible, anchorable, baseline_eligible, record_count, gps_count, device_count,
  active_days, centroid_lon, centroid_lat, gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio,
  signal_original_ratio, anomaly_tags, parent_bs_object_id, run_id, batch_id, baseline_version, sample_scope_tag
)
SELECT
  md5('cell|' || cp.operator_code || '|' || cp.tech_norm || '|' || cp.lac || '|' || cp.cell_id::text),
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
    WHEN cp.gps_p90_dist_m > 1500 THEN 'gps_bias'
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
    WHEN cp.gps_p90_dist_m > 1500 THEN ARRAY['gps_bias']
    ELSE ARRAY[]::text[]
  END,
  md5('bs|' || cp.operator_code || '|' || cp.tech_norm || '|' || cp.lac || '|' || cp.bs_id::text),
  'RUN-SAMPLE-20251201-20251207-V1',
  'BATCH-SAMPLE-20251201-20251207-V1',
  'BASELINE-SAMPLE-V1',
  cp.scenario_tags
FROM rebuild3_sample.stg_cell_profile cp
LEFT JOIN rebuild3_sample.stg_bs_classification_ref br USING (operator_code, tech_norm, lac, bs_id);

INSERT INTO rebuild3_sample.obj_bs (
  object_id, operator_code, tech_norm, lac, bs_id, lifecycle_state, health_state,
  existence_eligible, anchorable, baseline_eligible, cell_count, active_cell_count,
  record_count, gps_count, device_count, active_days, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio, anomaly_tags,
  parent_lac_object_id, run_id, batch_id, baseline_version, sample_scope_tag
)
SELECT
  md5('bs|' || bp.operator_code || '|' || bp.tech_norm || '|' || bp.lac || '|' || bp.bs_id::text),
  bp.operator_code,
  bp.tech_norm,
  bp.lac,
  bp.bs_id,
  CASE WHEN bp.record_count >= 5 THEN 'active' ELSE 'observing' END,
  CASE
    WHEN br.mapped_health_state IS NOT NULL THEN br.mapped_health_state
    WHEN bp.gps_count < 3 THEN 'insufficient'
    WHEN bp.gps_p90_dist_m > 4000 THEN 'insufficient'
    ELSE 'healthy'
  END,
  (bp.record_count >= 5),
  (
    br.mapped_health_state IS NULL
    AND bp.gps_count >= 10
    AND coalesce(bp.gps_p90_dist_m, 999999) <= 1500
    AND coalesce(bp.signal_original_ratio, 0) >= 0.3
  ),
  (
    br.mapped_health_state IS NULL
    AND bp.gps_count >= 20
    AND bp.active_days >= 3
    AND coalesce(bp.signal_original_ratio, 0) >= 0.5
    AND coalesce(bp.gps_p90_dist_m, 999999) <= 1500
  ),
  bp.cell_count,
  count(c.object_id) FILTER (WHERE c.lifecycle_state = 'active'),
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
  md5('lac|' || bp.operator_code || '|' || bp.tech_norm || '|' || bp.lac),
  'RUN-SAMPLE-20251201-20251207-V1',
  'BATCH-SAMPLE-20251201-20251207-V1',
  'BASELINE-SAMPLE-V1',
  bp.scenario_tags
FROM rebuild3_sample.stg_bs_profile bp
LEFT JOIN rebuild3_sample.stg_bs_classification_ref br USING (operator_code, tech_norm, lac, bs_id)
LEFT JOIN rebuild3_sample.obj_cell c USING (operator_code, tech_norm, lac, bs_id)
GROUP BY 1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23,24,28;

INSERT INTO rebuild3_sample.obj_lac (
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
  FROM rebuild3_sample.obj_bs
  GROUP BY 1,2,3
),
lac_signal AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    count(*) FILTER (WHERE gps_source = 'original') AS gps_original_count
  FROM rebuild3_sample.stg_signal_fact
  GROUP BY 1,2,3
),
lac_cls AS (
  SELECT
    operator_code,
    tech_norm,
    lac,
    array_remove(array_agg(DISTINCT classification_v2), NULL) AS anomaly_tags
  FROM rebuild3_sample.stg_bs_classification_ref
  GROUP BY 1,2,3
)
SELECT
  md5('lac|' || lp.operator_code || '|' || lp.tech_norm || '|' || lp.lac),
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
  coalesce(ls.gps_original_count, 0),
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
  'RUN-SAMPLE-20251201-20251207-V1',
  'BATCH-SAMPLE-20251201-20251207-V1',
  'BASELINE-SAMPLE-V1',
  lp.scenario_tags
FROM rebuild3_sample.stg_lac_profile lp
LEFT JOIN lac_bs lb USING (operator_code, tech_norm, lac)
LEFT JOIN lac_signal ls USING (operator_code, tech_norm, lac)
LEFT JOIN lac_cls lc USING (operator_code, tech_norm, lac);

INSERT INTO rebuild3_sample.obj_state_history (object_type, object_id, lifecycle_state, health_state, anchorable, baseline_eligible, changed_reason, run_id, batch_id)
SELECT 'cell', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'sample_init_snapshot', run_id, batch_id
FROM rebuild3_sample.obj_cell
UNION ALL
SELECT 'bs', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'sample_init_snapshot', run_id, batch_id
FROM rebuild3_sample.obj_bs
UNION ALL
SELECT 'lac', object_id, lifecycle_state, health_state, anchorable, baseline_eligible, 'sample_init_snapshot', run_id, batch_id
FROM rebuild3_sample.obj_lac;

INSERT INTO rebuild3_sample.obj_relation_history (relation_type, parent_object_id, child_object_id, relation_status, changed_reason, run_id, batch_id)
SELECT 'bs_cell', parent_bs_object_id, object_id, 'active', 'sample_init_snapshot', run_id, batch_id
FROM rebuild3_sample.obj_cell
UNION ALL
SELECT 'lac_bs', parent_lac_object_id, object_id, 'active', 'sample_init_snapshot', run_id, batch_id
FROM rebuild3_sample.obj_bs;

INSERT INTO rebuild3_sample.fact_rejected (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  rejection_reason, sample_scope_tag, contract_version, rule_set_version, run_id, batch_id
)
SELECT
  standardized_event_id,
  source_name,
  event_time,
  operator_code,
  tech_norm,
  lac,
  bs_id,
  cell_id,
  dev_id,
  route_reason,
  sample_scope_tag,
  contract_version,
  rule_set_version,
  run_id,
  batch_id
FROM rebuild3_sample.fact_standardized
WHERE structural_valid = false;

INSERT INTO rebuild3_sample.fact_pending_issue (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  health_state, anomaly_tags, baseline_eligible, route_reason, sample_scope_tag, contract_version,
  rule_set_version, baseline_version, run_id, batch_id
)
SELECT
  s.standardized_event_id,
  s.source_name,
  s.event_time,
  s.operator_code,
  s.tech_norm,
  s.lac,
  s.bs_id,
  s.cell_id,
  s.dev_id,
  c.health_state,
  c.anomaly_tags,
  false,
  'object_level_issue',
  s.sample_scope_tag,
  s.contract_version,
  s.rule_set_version,
  'BASELINE-SAMPLE-V1',
  s.run_id,
  s.batch_id
FROM rebuild3_sample.fact_standardized s
JOIN rebuild3_sample.obj_cell c
  ON s.operator_code = c.operator_code
 AND s.tech_norm = c.tech_norm
 AND s.lac = c.lac
 AND s.cell_id = c.cell_id
WHERE s.structural_valid
  AND c.health_state IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias');

INSERT INTO rebuild3_sample.fact_pending_observation (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  route_reason, missing_layer, anomaly_tags, sample_scope_tag, contract_version, rule_set_version,
  baseline_version, run_id, batch_id
)
SELECT
  s.standardized_event_id,
  s.source_name,
  s.event_time,
  s.operator_code,
  s.tech_norm,
  s.lac,
  s.bs_id,
  s.cell_id,
  s.dev_id,
  'insufficient_object_evidence',
  CASE WHEN c.lifecycle_state = 'waiting' THEN 'existence' ELSE 'anchorable' END,
  c.anomaly_tags,
  s.sample_scope_tag,
  s.contract_version,
  s.rule_set_version,
  'BASELINE-SAMPLE-V1',
  s.run_id,
  s.batch_id
FROM rebuild3_sample.fact_standardized s
JOIN rebuild3_sample.obj_cell c
  ON s.operator_code = c.operator_code
 AND s.tech_norm = c.tech_norm
 AND s.lac = c.lac
 AND s.cell_id = c.cell_id
WHERE s.structural_valid
  AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
  AND c.lifecycle_state IN ('waiting', 'observing');

INSERT INTO rebuild3_sample.fact_governed (
  standardized_event_id, source_name, event_time, operator_code, tech_norm, lac, bs_id, cell_id, dev_id,
  lon_final, lat_final, gps_source, signal_source, anomaly_tags, baseline_eligible, route_reason,
  sample_scope_tag, contract_version, rule_set_version, baseline_version, run_id, batch_id
)
SELECT
  s.standardized_event_id,
  s.source_name,
  s.event_time,
  s.operator_code,
  s.tech_norm,
  s.lac,
  s.bs_id,
  s.cell_id,
  s.dev_id,
  sf.lon_final,
  sf.lat_final,
  sf.gps_source,
  sf.signal_source,
  c.anomaly_tags,
  c.baseline_eligible,
  CASE
    WHEN cardinality(c.anomaly_tags) > 0 THEN 'record_level_anomaly_but_governed'
    ELSE 'healthy_or_manageable_record'
  END,
  s.sample_scope_tag,
  s.contract_version,
  s.rule_set_version,
  'BASELINE-SAMPLE-V1',
  s.run_id,
  s.batch_id
FROM rebuild3_sample.fact_standardized s
JOIN rebuild3_sample.obj_cell c
  ON s.operator_code = c.operator_code
 AND s.tech_norm = c.tech_norm
 AND s.lac = c.lac
 AND s.cell_id = c.cell_id
LEFT JOIN rebuild3_sample.stg_signal_fact sf
  ON s.standardized_event_id = sf.standardized_event_id
WHERE s.structural_valid
  AND c.health_state NOT IN ('collision_suspect', 'collision_confirmed', 'dynamic', 'gps_bias')
  AND c.lifecycle_state NOT IN ('waiting', 'observing');

INSERT INTO rebuild3_sample.baseline_cell (
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, baseline_version, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, bs_id, cell_id, 'BASELINE-SAMPLE-V1', centroid_lon, centroid_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
FROM rebuild3_sample.obj_cell
WHERE baseline_eligible;

INSERT INTO rebuild3_sample.baseline_bs (
  object_id, operator_code, tech_norm, lac, bs_id, baseline_version, center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, bs_id, 'BASELINE-SAMPLE-V1', center_lon, center_lat,
  gps_p50_dist_m, gps_p90_dist_m, gps_original_ratio, signal_original_ratio
FROM rebuild3_sample.obj_bs
WHERE baseline_eligible;

INSERT INTO rebuild3_sample.baseline_lac (
  object_id, operator_code, tech_norm, lac, baseline_version, center_lon, center_lat, gps_original_ratio, signal_original_ratio
)
SELECT
  object_id, operator_code, tech_norm, lac, 'BASELINE-SAMPLE-V1', center_lon, center_lat, gps_original_ratio, signal_original_ratio
FROM rebuild3_sample.obj_lac
WHERE baseline_eligible;

INSERT INTO rebuild3_sample_meta.baseline_version (
  baseline_version, run_id, batch_id, rule_set_version, refresh_reason, object_count
)
SELECT
  'BASELINE-SAMPLE-V1',
  'RUN-SAMPLE-20251201-20251207-V1',
  'BATCH-SAMPLE-20251201-20251207-V1',
  'rebuild3-rule-set-v1',
  'sample_initial_baseline',
  (SELECT count(*) FROM rebuild3_sample.baseline_cell) + (SELECT count(*) FROM rebuild3_sample.baseline_bs) + (SELECT count(*) FROM rebuild3_sample.baseline_lac);

INSERT INTO rebuild3_sample_meta.batch_flow_summary (batch_id, fact_layer, row_count, row_ratio)
SELECT
  'BATCH-SAMPLE-20251201-20251207-V1',
  fact_layer,
  row_count,
  round(row_count::numeric / nullif(total_rows, 0), 4)
FROM (
  SELECT 'fact_governed' AS fact_layer, (SELECT count(*) FROM rebuild3_sample.fact_governed) AS row_count,
         (SELECT count(*) FROM rebuild3_sample.fact_standardized) AS total_rows
  UNION ALL
  SELECT 'fact_pending_observation', (SELECT count(*) FROM rebuild3_sample.fact_pending_observation), (SELECT count(*) FROM rebuild3_sample.fact_standardized)
  UNION ALL
  SELECT 'fact_pending_issue', (SELECT count(*) FROM rebuild3_sample.fact_pending_issue), (SELECT count(*) FROM rebuild3_sample.fact_standardized)
  UNION ALL
  SELECT 'fact_rejected', (SELECT count(*) FROM rebuild3_sample.fact_rejected), (SELECT count(*) FROM rebuild3_sample.fact_standardized)
) x;

INSERT INTO rebuild3_sample_meta.batch_decision_summary (batch_id, decision_name, object_type, object_count)
SELECT 'BATCH-SAMPLE-20251201-20251207-V1', 'lifecycle_distribution', 'cell:' || lifecycle_state, count(*) FROM rebuild3_sample.obj_cell GROUP BY lifecycle_state
UNION ALL
SELECT 'BATCH-SAMPLE-20251201-20251207-V1', 'lifecycle_distribution', 'bs:' || lifecycle_state, count(*) FROM rebuild3_sample.obj_bs GROUP BY lifecycle_state
UNION ALL
SELECT 'BATCH-SAMPLE-20251201-20251207-V1', 'lifecycle_distribution', 'lac:' || lifecycle_state, count(*) FROM rebuild3_sample.obj_lac GROUP BY lifecycle_state;

INSERT INTO rebuild3_sample_meta.batch_anomaly_summary (batch_id, anomaly_level, anomaly_name, object_count, fact_count)
SELECT 'BATCH-SAMPLE-20251201-20251207-V1', 'object', health_state, count(*), NULL
FROM rebuild3_sample.obj_bs
GROUP BY health_state
UNION ALL
SELECT 'BATCH-SAMPLE-20251201-20251207-V1', 'record', tag, NULL, count(*)
FROM (
  SELECT unnest(anomaly_tags) AS tag FROM rebuild3_sample.fact_governed
  UNION ALL
  SELECT unnest(anomaly_tags) AS tag FROM rebuild3_sample.fact_pending_issue
  UNION ALL
  SELECT unnest(anomaly_tags) AS tag FROM rebuild3_sample.fact_pending_observation
) t
GROUP BY tag;

INSERT INTO rebuild3_sample_meta.batch_baseline_refresh_log (batch_id, baseline_version, refresh_reason, triggered)
VALUES ('BATCH-SAMPLE-20251201-20251207-V1', 'BASELINE-SAMPLE-V1', 'sample_initial_baseline', true);

INSERT INTO rebuild3_sample_meta.batch_snapshot (batch_id, stage_name, metric_name, metric_value)
VALUES
  ('BATCH-SAMPLE-20251201-20251207-V1', 'input', 'fact_standardized', (SELECT count(*) FROM rebuild3_sample.fact_standardized)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'routing', 'fact_governed', (SELECT count(*) FROM rebuild3_sample.fact_governed)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'routing', 'fact_pending_observation', (SELECT count(*) FROM rebuild3_sample.fact_pending_observation)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'routing', 'fact_pending_issue', (SELECT count(*) FROM rebuild3_sample.fact_pending_issue)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'routing', 'fact_rejected', (SELECT count(*) FROM rebuild3_sample.fact_rejected)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'objects', 'obj_cell', (SELECT count(*) FROM rebuild3_sample.obj_cell)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'objects', 'obj_bs', (SELECT count(*) FROM rebuild3_sample.obj_bs)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'objects', 'obj_lac', (SELECT count(*) FROM rebuild3_sample.obj_lac)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'baseline', 'baseline_cell', (SELECT count(*) FROM rebuild3_sample.baseline_cell)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'baseline', 'baseline_bs', (SELECT count(*) FROM rebuild3_sample.baseline_bs)),
  ('BATCH-SAMPLE-20251201-20251207-V1', 'baseline', 'baseline_lac', (SELECT count(*) FROM rebuild3_sample.baseline_lac));

UPDATE rebuild3_sample_meta.batch
SET status = 'completed',
    output_rows = (SELECT count(*) FROM rebuild3_sample.fact_governed)
WHERE batch_id = 'BATCH-SAMPLE-20251201-20251207-V1';

UPDATE rebuild3_sample_meta.run
SET status = 'completed'
WHERE run_id = 'RUN-SAMPLE-20251201-20251207-V1';
