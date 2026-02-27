-- Layer_3 Step32：修正前后对比报表（收益、风险规模、碰撞疑似）
-- 输入：
--   - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
--   - public."Y_codex_Layer3_Step30_Master_BS_Library"
-- 输出：
--   - public."Y_codex_Layer3_Step32_Compare"（TABLE：v2 人类友好指标表，含 PASS/FAIL/WARN）
--   - public."Y_codex_Layer3_Step32_Compare_Raw"（TABLE：保留 v1 的聚合结果，便于排障）

/* ============================================================================
 * 会话级性能参数（PG15 / 264GB / 40核 / SSD）
 * 参考：lac_enbid_project/服务器配置与SQL调优建议.md
 * ==========================================================================*/
SET statement_timeout = 0;
SET work_mem = '2GB';
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;
SET jit = off;

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step32_Compare";
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step32_Compare_Raw";

CREATE TABLE public."Y_codex_Layer3_Step32_Compare_Raw" AS
WITH
params AS (
  SELECT
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw
),
base AS (
  SELECT
    t.*
  FROM public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" t
  CROSS JOIN params p
  WHERE
    (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
),
gps_gain AS (
  SELECT
    'GPS_GAIN'::text AS report_section,
    operator_id_raw,
    tech_norm,
    report_date,

    count(*)::bigint AS row_cnt,

    count(*) FILTER (WHERE gps_status = 'Missing')::bigint AS missing_cnt_before,
    count(*) FILTER (WHERE gps_status = 'Drift')::bigint AS drift_cnt_before,
    count(*) FILTER (WHERE gps_status = 'Verified')::bigint AS verified_cnt_before,

    count(*) FILTER (WHERE gps_status = 'Missing' AND gps_status_final = 'Verified')::bigint AS missing_to_filled_cnt,
    count(*) FILTER (WHERE gps_status = 'Drift' AND gps_status_final = 'Verified')::bigint AS drift_to_corrected_cnt,

    count(*) FILTER (WHERE gps_status IN ('Verified','Drift'))::bigint AS has_gps_before_cnt,
    count(*) FILTER (WHERE gps_status_final = 'Verified')::bigint AS has_gps_after_cnt,

    count(*) FILTER (WHERE gps_source = 'Augmented_from_BS')::bigint AS filled_from_usable_bs_cnt,
    count(*) FILTER (WHERE gps_source = 'Augmented_from_Risk_BS')::bigint AS filled_from_risk_bs_cnt,
    count(*) FILTER (WHERE gps_source = 'Not_Filled')::bigint AS not_filled_cnt
  FROM base
  GROUP BY 2,3,4
),
bs_risk AS (
  -- 风险规模以 Step30（站级）为准；按运营商切片时需把 shared_operator_list 拆开
  SELECT
    'BS_RISK'::text AS report_section,
    op.operator_id_raw,
    s.tech_norm,
    NULL::date AS report_date,

    count(*)::bigint AS bs_cnt,
    count(*) FILTER (WHERE s.gps_valid_level = 'Unusable')::bigint AS unusable_bs_cnt,
    count(*) FILTER (WHERE s.gps_valid_level = 'Risk')::bigint AS risk_bs_cnt,
    count(*) FILTER (WHERE s.gps_valid_level = 'Usable')::bigint AS usable_bs_cnt,

    count(*) FILTER (WHERE s.is_collision_suspect = 1)::bigint AS collision_suspect_bs_cnt,
    count(*) FILTER (WHERE s.is_multi_operator_shared)::bigint AS multi_operator_shared_bs_cnt
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
  CROSS JOIN LATERAL unnest(string_to_array(s.shared_operator_list, ',')) AS op(operator_id_raw)
  GROUP BY 2,3
),
unioned AS (
  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    row_cnt,
    missing_cnt_before,
    drift_cnt_before,
    verified_cnt_before,
    missing_to_filled_cnt,
    drift_to_corrected_cnt,
    has_gps_before_cnt,
    has_gps_after_cnt,
    filled_from_usable_bs_cnt,
    filled_from_risk_bs_cnt,
    not_filled_cnt,
    NULL::bigint AS bs_cnt,
    NULL::bigint AS unusable_bs_cnt,
    NULL::bigint AS risk_bs_cnt,
    NULL::bigint AS usable_bs_cnt,
    NULL::bigint AS collision_suspect_bs_cnt,
    NULL::bigint AS multi_operator_shared_bs_cnt
  FROM gps_gain

  UNION ALL

  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    NULL::bigint AS row_cnt,
    NULL::bigint AS missing_cnt_before,
    NULL::bigint AS drift_cnt_before,
    NULL::bigint AS verified_cnt_before,
    NULL::bigint AS missing_to_filled_cnt,
    NULL::bigint AS drift_to_corrected_cnt,
    NULL::bigint AS has_gps_before_cnt,
    NULL::bigint AS has_gps_after_cnt,
    NULL::bigint AS filled_from_usable_bs_cnt,
    NULL::bigint AS filled_from_risk_bs_cnt,
    NULL::bigint AS not_filled_cnt,
    bs_cnt,
    unusable_bs_cnt,
    risk_bs_cnt,
    usable_bs_cnt,
    collision_suspect_bs_cnt,
    multi_operator_shared_bs_cnt
  FROM bs_risk
)
SELECT * FROM unioned;

ANALYZE public."Y_codex_Layer3_Step32_Compare_Raw";


-- v2：人类友好指标表（方案 A）
CREATE TABLE public."Y_codex_Layer3_Step32_Compare" AS
WITH
thresholds AS (
  SELECT
    -- 仅做“口径一致性与趋势”验收：不把业务阈值写死为阻断（可在报告中 WARN）
    0::numeric AS dummy
),
gps_gain AS (
  SELECT *
  FROM public."Y_codex_Layer3_Step32_Compare_Raw"
  WHERE report_section = 'GPS_GAIN'
),
bs_risk AS (
  SELECT *
  FROM public."Y_codex_Layer3_Step32_Compare_Raw"
  WHERE report_section = 'BS_RISK'
),
metrics_gps AS (
  SELECT
    'GPS_GAIN'::text AS report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    'HAS_GPS_BEFORE'::text AS metric_code,
    '修正前有GPS规模（含Verified/Drift）'::text AS metric_name_cn,
    '数值仅用于对比；不做阻断'::text AS expected_rule_cn,
    has_gps_before_cnt::numeric AS actual_value_num,
    'PASS'::text AS pass_flag,
    NULL::text AS remark_cn
  FROM gps_gain

  UNION ALL

  SELECT
    'GPS_GAIN', operator_id_raw, tech_norm, report_date,
    'HAS_GPS_AFTER',
    '修正后有GPS规模（Verified）',
    '必须：after >= before（不允许回填导致可用GPS减少）',
    has_gps_after_cnt::numeric,
    CASE WHEN has_gps_after_cnt >= has_gps_before_cnt THEN 'PASS' ELSE 'FAIL' END,
    CASE WHEN has_gps_after_cnt >= has_gps_before_cnt THEN NULL ELSE '检查 Step31 gps_status_final/gps_source 逻辑' END
  FROM gps_gain

  UNION ALL

  SELECT
    'GPS_GAIN', operator_id_raw, tech_norm, report_date,
    'MISSING_TO_FILLED',
    'Missing→Filled 数量',
    '必须：0 <= missing_to_filled <= missing_cnt_before',
    missing_to_filled_cnt::numeric,
    CASE WHEN missing_to_filled_cnt BETWEEN 0 AND missing_cnt_before THEN 'PASS' ELSE 'FAIL' END,
    NULL
  FROM gps_gain

  UNION ALL

  SELECT
    'GPS_GAIN', operator_id_raw, tech_norm, report_date,
    'DRIFT_TO_CORRECTED',
    'Drift→Corrected 数量',
    '必须：0 <= drift_to_corrected <= drift_cnt_before',
    drift_to_corrected_cnt::numeric,
    CASE WHEN drift_to_corrected_cnt BETWEEN 0 AND drift_cnt_before THEN 'PASS' ELSE 'FAIL' END,
    NULL
  FROM gps_gain

  UNION ALL

  SELECT
    'GPS_GAIN', operator_id_raw, tech_norm, report_date,
    'FILLED_FROM_RISK_BS',
    '来自 Risk 基站的回填数量',
    '不阻断；建议关注规模与 TopN（报告 WARN）',
    filled_from_risk_bs_cnt::numeric,
    'WARN',
    '若占比过高：评估 Step30 Risk 判定/阈值'
  FROM gps_gain
),
metrics_bs AS (
  SELECT
    'BS_RISK'::text AS report_section,
    operator_id_raw,
    tech_norm,
    NULL::date AS report_date,
    'BS_TOTAL'::text AS metric_code,
    '基站总数（按运营商拆分口径）'::text AS metric_name_cn,
    '数值仅用于对比；不做阻断'::text AS expected_rule_cn,
    bs_cnt::numeric AS actual_value_num,
    'PASS'::text AS pass_flag,
    NULL::text AS remark_cn
  FROM bs_risk

  UNION ALL

  SELECT
    'BS_RISK', operator_id_raw, tech_norm, NULL::date,
    'BS_RISK_CNT',
    'Risk 基站数',
    '不阻断；需报告 TopN（报告 WARN）',
    risk_bs_cnt::numeric,
    'WARN',
    NULL
  FROM bs_risk

  UNION ALL

  SELECT
    'BS_RISK', operator_id_raw, tech_norm, NULL::date,
    'BS_COLLISION_SUSPECT_CNT',
    '碰撞疑似基站数',
    '不阻断；需报告 TopN（报告 WARN）',
    collision_suspect_bs_cnt::numeric,
    'WARN',
    NULL
  FROM bs_risk
),
unioned AS (
  SELECT * FROM metrics_gps
  UNION ALL
  SELECT * FROM metrics_bs
)
SELECT * FROM unioned;

ANALYZE public."Y_codex_Layer3_Step32_Compare";
