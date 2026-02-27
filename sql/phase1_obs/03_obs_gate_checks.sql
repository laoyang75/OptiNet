-- Phase1 gate checks (automation-friendly)
-- Usage:
-- 1) Run with latest run_id in obs tables (first query), or
-- 2) Copy individual SQL blocks as standalone gate probes.

SET statement_timeout = 0;
SET jit = off;

-- A) Latest run summary
WITH latest AS (
  SELECT run_id
  FROM public."Y_codex_obs_run_registry"
  ORDER BY run_started_at DESC
  LIMIT 1
)
SELECT
  g.gate_code,
  g.gate_name,
  g.actual_value,
  g.expected_value,
  g.diff_value,
  g.pass_flag
FROM public."Y_codex_obs_gate_result" g
JOIN latest l ON l.run_id = g.run_id
ORDER BY g.gate_code;

-- B) Row conservation: Step40 vs Final
SELECT
  (SELECT COUNT(*) FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill") AS step40_cnt,
  (SELECT COUNT(*) FROM public."Y_codex_Layer4_Final_Cell_Library") AS final_cnt,
  (
    (SELECT COUNT(*) FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill")
    -
    (SELECT COUNT(*) FROM public."Y_codex_Layer4_Final_Cell_Library")
  ) AS diff_cnt;

-- C) Reconciliation: _All vs fact
WITH m AS (
  SELECT * FROM public."Y_codex_Layer4_Step40_Gps_Metrics_All" WHERE shard_id = -1 LIMIT 1
),
f AS (
  SELECT
    COUNT(*) FILTER (WHERE gps_source = 'Not_Filled') AS fact_not_filled,
    COUNT(*) FILTER (WHERE gps_source = 'Augmented_from_BS_SevereCollision') AS fact_severe_fill,
    COUNT(*) FILTER (WHERE is_bs_id_lt_256 IS TRUE) AS fact_bs_id_lt_256
  FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"
)
SELECT
  m.gps_not_filled_cnt, f.fact_not_filled, (m.gps_not_filled_cnt - f.fact_not_filled) AS diff_not_filled,
  m.gps_fill_from_bs_severe_collision_cnt, f.fact_severe_fill, (m.gps_fill_from_bs_severe_collision_cnt - f.fact_severe_fill) AS diff_severe_fill,
  m.bs_id_lt_256_row_cnt, f.fact_bs_id_lt_256, (m.bs_id_lt_256_row_cnt - f.fact_bs_id_lt_256) AS diff_bs_id_lt_256
FROM m CROSS JOIN f;

-- D) Layer5 contract field existence
SELECT
  table_name,
  column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('Y_codex_Layer5_BS_Profile', 'Y_codex_Layer5_Cell_Profile')
  AND column_name IN ('BS_ID<256标记', '多运营商共享标记', '共享运营商数', '共享运营商列表')
ORDER BY table_name, column_name;

-- E) Invalid LAC leakage
SELECT
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_Lac_Profile"  WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_lac_invalid,
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile"   WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_bs_invalid,
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "LAC" IS NULL OR "LAC" <= 0 OR "LAC" IN (65534,65535,16777214,16777215,2147483647)) AS l5_cell_invalid;

-- F) Label closure
SELECT
  (SELECT COUNT(*) FROM (SELECT operator_id_raw, tech_norm, lac_dec_final, bs_id_final FROM public."Y_codex_Layer4_Final_Cell_Library" WHERE is_collision_suspect = 1 GROUP BY 1,2,3,4) t) AS l4_collision_bs,
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_BS_Profile" WHERE "疑似碰撞标记" IS TRUE) AS l5_collision_bs,
  (SELECT COUNT(*) FROM (SELECT operator_id_raw, tech_norm, lac_dec_final, cell_id_dec FROM public."Y_codex_Layer4_Final_Cell_Library" WHERE is_severe_collision IS TRUE GROUP BY 1,2,3,4) t) AS l4_severe_cell,
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "严重碰撞桶标记" IS TRUE) AS l5_severe_cell,
  (SELECT COUNT(*) FROM (SELECT operator_id_raw, tech_norm, lac_dec_final, cell_id_dec FROM public."Y_codex_Layer4_Final_Cell_Library" WHERE is_dynamic_cell = 1 AND tech_norm IN ('4G', '5G') AND operator_id_raw IN ('46000','46001','46011','46015','46020') AND lac_dec_final > 0 AND bs_id_final > 0 AND cell_id_dec > 0 GROUP BY 1,2,3,4) t) AS l4_dynamic_cell_filtered,
  (SELECT COUNT(*) FROM public."Y_codex_Layer5_Cell_Profile" WHERE "移动CELL标记" IS TRUE) AS l5_dynamic_cell;

