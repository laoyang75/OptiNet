-- Phase1 Observability Mart build script (S1 bootstrap)
-- Prerequisite: run sql/phase1_obs/01_obs_ddl.sql once.
-- Output: one new run_id snapshot in Y_codex_obs_* tables.

SET statement_timeout = 0;
SET jit = off;
SET TIME ZONE 'UTC';

BEGIN;

CREATE TEMP TABLE _obs_ctx ON COMMIT DROP AS
SELECT
  format('phase1_%s', to_char(clock_timestamp(), 'YYYYMMDD_HH24MISS'))::text AS run_id,
  clock_timestamp()::timestamptz AS snapshot_ts;

INSERT INTO public."Y_codex_obs_run_registry" (
  run_id, run_started_at, source_db, pipeline_version, run_status, notes
)
SELECT
  c.run_id,
  c.snapshot_ts,
  current_database(),
  'phase1_v1',
  'running',
  'Built from Layer_0~Layer_5 + S0 gate checks'
FROM _obs_ctx c;

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
cnt AS (
  SELECT
    (SELECT COUNT(*) FROM public."Y_codex_Layer0_Lac") AS l0_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered") AS l2_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer3_Step30_Master_BS_Library") AS l3_bs_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill") AS l4_step40_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer4_Final_Cell_Library") AS l4_final_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Lac_Profile") AS l5_lac_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile") AS l5_bs_rows,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile") AS l5_cell_rows
)
INSERT INTO public."Y_codex_obs_layer_snapshot" (
  run_id, layer_id, input_rows, output_rows, pass_flag, payload
)
SELECT
  ctx.run_id,
  v.layer_id,
  v.input_rows,
  v.output_rows,
  v.pass_flag,
  v.payload
FROM ctx
CROSS JOIN cnt
CROSS JOIN LATERAL (
  VALUES
    ('L0', NULL::bigint, cnt.l0_rows, cnt.l0_rows > 0, jsonb_build_object('table', 'Y_codex_Layer0_Lac')),
    ('L2', cnt.l0_rows, cnt.l2_rows, cnt.l2_rows > 0 AND cnt.l2_rows <= cnt.l0_rows, jsonb_build_object('table', 'Y_codex_Layer2_Step06_L0_Lac_Filtered')),
    ('L3', cnt.l2_rows, cnt.l3_bs_rows, cnt.l3_bs_rows > 0, jsonb_build_object('table', 'Y_codex_Layer3_Step30_Master_BS_Library', 'object_level', 'BS')),
    ('L4_Step40', cnt.l2_rows, cnt.l4_step40_rows, cnt.l4_step40_rows > 0, jsonb_build_object('table', 'Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill')),
    ('L4_Final', cnt.l4_step40_rows, cnt.l4_final_rows, cnt.l4_final_rows = cnt.l4_step40_rows, jsonb_build_object('table', 'Y_codex_Layer4_Final_Cell_Library')),
    ('L5_LAC', cnt.l4_final_rows, cnt.l5_lac_rows, cnt.l5_lac_rows > 0, jsonb_build_object('table', 'Y_codex_Layer5_Lac_Profile')),
    ('L5_BS', cnt.l4_final_rows, cnt.l5_bs_rows, cnt.l5_bs_rows > 0, jsonb_build_object('table', 'Y_codex_Layer5_BS_Profile')),
    ('L5_CELL', cnt.l4_final_rows, cnt.l5_cell_rows, cnt.l5_cell_rows > 0, jsonb_build_object('table', 'Y_codex_Layer5_Cell_Profile'))
) AS v(layer_id, input_rows, output_rows, pass_flag, payload);

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
m40 AS (
  SELECT * FROM public."Y_codex_Layer4_Step40_Gps_Metrics_All" WHERE shard_id = -1 LIMIT 1
),
m41 AS (
  SELECT * FROM public."Y_codex_Layer4_Step41_Signal_Metrics_All" WHERE shard_id = -1 LIMIT 1
)
INSERT INTO public."Y_codex_obs_quality_metric" (
  run_id, layer_id, metric_code, metric_value, unit, payload
)
SELECT
  ctx.run_id,
  x.layer_id,
  x.metric_code,
  x.metric_value,
  x.unit,
  x.payload
FROM ctx
CROSS JOIN LATERAL (
  VALUES
    ('L4', 'row_cnt', (SELECT row_cnt::numeric FROM m40), 'rows', jsonb_build_object('source', 'Y_codex_Layer4_Step40_Gps_Metrics_All')),
    ('L4', 'gps_missing_cnt', (SELECT gps_missing_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'gps_drift_cnt', (SELECT gps_drift_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'gps_fill_from_bs_cnt', (SELECT gps_fill_from_bs_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'gps_fill_from_bs_severe_collision_cnt', (SELECT gps_fill_from_bs_severe_collision_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'gps_fill_from_risk_bs_cnt', (SELECT gps_fill_from_risk_bs_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'gps_not_filled_cnt', (SELECT gps_not_filled_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'severe_collision_row_cnt', (SELECT severe_collision_row_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'bs_id_lt_256_row_cnt', (SELECT bs_id_lt_256_row_cnt::numeric FROM m40), 'rows', '{}'::jsonb),
    ('L4', 'need_fill_row_cnt', (SELECT need_fill_row_cnt::numeric FROM m41), 'rows', jsonb_build_object('metric_semantics', 'at_least_one_signal_field_missing_before')),
    ('L4', 'filled_by_cell_nearest_row_cnt', (SELECT filled_by_cell_nearest_row_cnt::numeric FROM m41), 'rows', '{}'::jsonb),
    ('L4', 'filled_by_bs_top_cell_row_cnt', (SELECT filled_by_bs_top_cell_row_cnt::numeric FROM m41), 'rows', '{}'::jsonb),
    ('L4', 'missing_field_before_sum', (SELECT missing_field_before_sum::numeric FROM m41), 'fields', '{}'::jsonb),
    ('L4', 'missing_field_after_sum', (SELECT missing_field_after_sum::numeric FROM m41), 'fields', '{}'::jsonb),
    ('L4', 'filled_field_sum', (SELECT filled_field_sum::numeric FROM m41), 'fields', '{}'::jsonb)
) AS x(layer_id, metric_code, metric_value, unit, payload);

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
a AS (
  SELECT
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "疑似碰撞标记" IS TRUE) AS bs_collision_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "严重碰撞桶标记" IS TRUE) AS bs_severe_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "含移动CELL标记" IS TRUE) AS bs_dynamic_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "BS_ID<256标记" IS TRUE) AS bs_id_lt_256_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "多运营商共享标记" IS TRUE) AS bs_multi_shared_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "疑似碰撞标记" IS TRUE) AS cell_collision_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "严重碰撞桶标记" IS TRUE) AS cell_severe_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "移动CELL标记" IS TRUE) AS cell_dynamic_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "BS_ID<256标记" IS TRUE) AS cell_bs_id_lt_256_cnt,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "多运营商共享标记" IS TRUE) AS cell_multi_shared_cnt
)
INSERT INTO public."Y_codex_obs_anomaly_stats" (
  run_id, object_level, anomaly_code, obj_cnt, payload
)
SELECT
  ctx.run_id,
  v.object_level,
  v.anomaly_code,
  v.obj_cnt,
  '{}'::jsonb
FROM ctx
CROSS JOIN a
CROSS JOIN LATERAL (
  VALUES
    ('BS', 'collision', a.bs_collision_cnt),
    ('BS', 'severe_collision', a.bs_severe_cnt),
    ('BS', 'dynamic_cell', a.bs_dynamic_cnt),
    ('BS', 'bs_id_lt_256', a.bs_id_lt_256_cnt),
    ('BS', 'multi_operator_shared', a.bs_multi_shared_cnt),
    ('CELL', 'collision', a.cell_collision_cnt),
    ('CELL', 'severe_collision', a.cell_severe_cnt),
    ('CELL', 'dynamic_cell', a.cell_dynamic_cnt),
    ('CELL', 'bs_id_lt_256', a.cell_bs_id_lt_256_cnt),
    ('CELL', 'multi_operator_shared', a.cell_multi_shared_cnt)
) AS v(object_level, anomaly_code, obj_cnt);

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
f AS (
  SELECT
    COUNT(*) FILTER (WHERE gps_source = 'Not_Filled')::numeric AS fact_not_filled,
    COUNT(*) FILTER (WHERE gps_source = 'Augmented_from_BS_SevereCollision')::numeric AS fact_severe_fill,
    COUNT(*) FILTER (WHERE is_bs_id_lt_256 IS TRUE)::numeric AS fact_bs_id_lt_256
  FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"
),
m AS (
  SELECT
    row_cnt::numeric AS metric_row_cnt,
    gps_not_filled_cnt::numeric AS metric_not_filled,
    gps_fill_from_bs_severe_collision_cnt::numeric AS metric_severe_fill,
    bs_id_lt_256_row_cnt::numeric AS metric_bs_id_lt_256
  FROM public."Y_codex_Layer4_Step40_Gps_Metrics_All"
  WHERE shard_id = -1
  LIMIT 1
),
g AS (
  SELECT
    (SELECT COUNT(*)::numeric FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill") AS step40_cnt,
    (SELECT COUNT(*)::numeric FROM public."Y_codex_Layer4_Final_Cell_Library") AS final_cnt,
    (SELECT COUNT(*)::numeric FROM public."Y_codex_Layer5_Lac_Profile"  WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_lac_invalid,
    (SELECT COUNT(*)::numeric FROM public."Y_codex_Layer5_BS_Profile"   WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_bs_invalid,
    (SELECT COUNT(*)::numeric FROM public."Y_codex_Layer5_Cell_Profile" WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_cell_invalid
),
cols AS (
  SELECT
    (SELECT COUNT(*)::numeric
     FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name IN ('Y_codex_Layer5_BS_Profile', 'Y_codex_Layer5_Cell_Profile')
       AND column_name IN ('BS_ID<256标记', '多运营商共享标记', '共享运营商数', '共享运营商列表')) AS cn_contract_cols,
    (SELECT COUNT(*)::numeric
     FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name IN ('Y_codex_Layer5_BS_Profile_EN', 'Y_codex_Layer5_Cell_Profile_EN')
       AND column_name IN ('is_bs_id_lt_256', 'is_multi_operator_shared', 'shared_operator_cnt', 'shared_operator_list')) AS en_contract_cols
)
INSERT INTO public."Y_codex_obs_reconciliation" (
  run_id, check_code, lhs_value, rhs_value, diff_value, pass_flag, details
)
SELECT
  ctx.run_id,
  v.check_code,
  v.lhs_value,
  v.rhs_value,
  v.diff_value,
  v.pass_flag,
  v.details
FROM ctx
CROSS JOIN f
CROSS JOIN m
CROSS JOIN g
CROSS JOIN cols
CROSS JOIN LATERAL (
  VALUES
    ('step40_vs_final_rows', g.step40_cnt, g.final_cnt, g.step40_cnt - g.final_cnt, (g.step40_cnt = g.final_cnt), jsonb_build_object('gate', 'row_conservation')),
    ('gps_not_filled_vs_fact', m.metric_not_filled, f.fact_not_filled, m.metric_not_filled - f.fact_not_filled, (m.metric_not_filled = f.fact_not_filled), jsonb_build_object('gate', 'reconciliation')),
    ('severe_fill_vs_fact', m.metric_severe_fill, f.fact_severe_fill, m.metric_severe_fill - f.fact_severe_fill, (m.metric_severe_fill = f.fact_severe_fill), jsonb_build_object('gate', 'reconciliation')),
    ('bs_id_lt_256_vs_fact', m.metric_bs_id_lt_256, f.fact_bs_id_lt_256, m.metric_bs_id_lt_256 - f.fact_bs_id_lt_256, (m.metric_bs_id_lt_256 = f.fact_bs_id_lt_256), jsonb_build_object('gate', 'reconciliation')),
    ('invalid_lac_l5_lac', g.l5_lac_invalid, 0::numeric, g.l5_lac_invalid, (g.l5_lac_invalid = 0), jsonb_build_object('table', 'Y_codex_Layer5_Lac_Profile')),
    ('invalid_lac_l5_bs', g.l5_bs_invalid, 0::numeric, g.l5_bs_invalid, (g.l5_bs_invalid = 0), jsonb_build_object('table', 'Y_codex_Layer5_BS_Profile')),
    ('invalid_lac_l5_cell', g.l5_cell_invalid, 0::numeric, g.l5_cell_invalid, (g.l5_cell_invalid = 0), jsonb_build_object('table', 'Y_codex_Layer5_Cell_Profile')),
    ('contract_fields_cn', cols.cn_contract_cols, 8::numeric, cols.cn_contract_cols - 8::numeric, (cols.cn_contract_cols = 8), jsonb_build_object('scope', 'Layer5 Chinese base tables')),
    ('contract_fields_en', cols.en_contract_cols, 8::numeric, cols.en_contract_cols - 8::numeric, (cols.en_contract_cols = 8), jsonb_build_object('scope', 'Layer5 EN views'))
) AS v(check_code, lhs_value, rhs_value, diff_value, pass_flag, details);

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
cnt AS (
  SELECT
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile") AS bs_total,
    (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile") AS cell_total
),
schema_hits AS (
  SELECT
    table_name,
    column_name
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND (
      (table_name = 'Y_codex_Layer5_BS_Profile' AND column_name IN ('BS_ID<256标记', '多运营商共享标记', '共享运营商数', '共享运营商列表'))
      OR
      (table_name = 'Y_codex_Layer5_Cell_Profile' AND column_name IN ('BS_ID<256标记', '多运营商共享标记', '共享运营商数', '共享运营商列表'))
    )
)
INSERT INTO public."Y_codex_obs_exposure_matrix" (
  run_id, object_level, field_code, exposed_flag, true_obj_cnt, total_obj_cnt, note
)
SELECT
  ctx.run_id,
  v.object_level,
  v.field_code,
  v.exposed_flag,
  v.true_obj_cnt,
  v.total_obj_cnt,
  v.note
FROM ctx
CROSS JOIN cnt
CROSS JOIN LATERAL (
  VALUES
    ('BS', 'is_bs_id_lt_256',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_BS_Profile' AND column_name = 'BS_ID<256标记'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "BS_ID<256标记" IS TRUE),
      cnt.bs_total,
      'Mapped from Layer4 is_bs_id_lt_256'),
    ('BS', 'is_multi_operator_shared',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_BS_Profile' AND column_name = '多运营商共享标记'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "多运营商共享标记" IS TRUE),
      cnt.bs_total,
      'Mapped from Layer4/Layer3 shared operator mark'),
    ('BS', 'shared_operator_cnt',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_BS_Profile' AND column_name = '共享运营商数'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE COALESCE("共享运营商数", 0) > 1),
      cnt.bs_total,
      'Count of shared operators'),
    ('BS', 'shared_operator_list',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_BS_Profile' AND column_name = '共享运营商列表'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "共享运营商列表" IS NOT NULL AND btrim("共享运营商列表") <> ''),
      cnt.bs_total,
      'Readable shared operator list'),
    ('CELL', 'is_bs_id_lt_256',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_Cell_Profile' AND column_name = 'BS_ID<256标记'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "BS_ID<256标记" IS TRUE),
      cnt.cell_total,
      'Mapped from parent BS/cell records'),
    ('CELL', 'is_multi_operator_shared',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_Cell_Profile' AND column_name = '多运营商共享标记'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "多运营商共享标记" IS TRUE),
      cnt.cell_total,
      'Mapped from parent BS/cell records'),
    ('CELL', 'shared_operator_cnt',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_Cell_Profile' AND column_name = '共享运营商数'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE COALESCE("共享运营商数", 0) > 1),
      cnt.cell_total,
      'Count of shared operators'),
    ('CELL', 'shared_operator_list',
      EXISTS (SELECT 1 FROM schema_hits WHERE table_name = 'Y_codex_Layer5_Cell_Profile' AND column_name = '共享运营商列表'),
      (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "共享运营商列表" IS NOT NULL AND btrim("共享运营商列表") <> ''),
      cnt.cell_total,
      'Readable shared operator list')
) AS v(object_level, field_code, exposed_flag, true_obj_cnt, total_obj_cnt, note);

WITH
ctx AS (SELECT run_id FROM _obs_ctx),
latest AS (
  SELECT
    run_id,
    check_code,
    lhs_value,
    rhs_value,
    diff_value,
    pass_flag
  FROM public."Y_codex_obs_reconciliation"
  WHERE run_id = (SELECT run_id FROM _obs_ctx)
)
INSERT INTO public."Y_codex_obs_gate_result" (
  run_id, gate_code, gate_name, actual_value, expected_value, diff_value, pass_flag, evidence_sql, payload
)
SELECT
  l.run_id,
  l.check_code,
  CASE l.check_code
    WHEN 'step40_vs_final_rows' THEN '行数守恒：Step40 vs Final'
    WHEN 'gps_not_filled_vs_fact' THEN '对账：Not_Filled 指标一致'
    WHEN 'severe_fill_vs_fact' THEN '对账：Severe Fill 指标一致'
    WHEN 'bs_id_lt_256_vs_fact' THEN '对账：bs_id_lt_256 指标一致'
    WHEN 'invalid_lac_l5_lac' THEN '无效LAC泄漏：L5_LAC'
    WHEN 'invalid_lac_l5_bs' THEN '无效LAC泄漏：L5_BS'
    WHEN 'invalid_lac_l5_cell' THEN '无效LAC泄漏：L5_CELL'
    WHEN 'contract_fields_cn' THEN 'Layer5 字段存在性：中文底表'
    WHEN 'contract_fields_en' THEN 'Layer5 字段存在性：EN 视图'
    ELSE l.check_code
  END AS gate_name,
  l.lhs_value,
  l.rhs_value,
  l.diff_value,
  l.pass_flag,
  'sql/phase1_obs/03_obs_gate_checks.sql' AS evidence_sql,
  jsonb_build_object('source', 'Y_codex_obs_reconciliation')
FROM latest l;

UPDATE public."Y_codex_obs_run_registry" r
SET
  run_finished_at = clock_timestamp(),
  run_status = CASE
    WHEN EXISTS (
      SELECT 1
      FROM public."Y_codex_obs_gate_result" g
      WHERE g.run_id = r.run_id
        AND g.pass_flag IS FALSE
    ) THEN 'failed'
    ELSE 'passed'
  END
WHERE r.run_id = (SELECT run_id FROM _obs_ctx);

COMMIT;

SELECT
  run_id,
  run_status,
  run_started_at,
  run_finished_at
FROM public."Y_codex_obs_run_registry"
WHERE run_id = (SELECT run_id FROM _obs_ctx);

