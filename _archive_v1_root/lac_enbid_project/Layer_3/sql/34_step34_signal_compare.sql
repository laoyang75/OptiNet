-- Layer_3 Step34：信号补齐摸底报表
-- 输入：
--   - public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
-- 输出：
--   - public."Y_codex_Layer3_Step34_Signal_Compare"（TABLE：v2 人类友好指标表，含 PASS/FAIL/WARN）
--   - public."Y_codex_Layer3_Step34_Signal_Compare_Raw"（TABLE：保留 v1 的聚合结果）

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

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step34_Signal_Compare";
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step34_Signal_Compare_Raw";

CREATE TABLE public."Y_codex_Layer3_Step34_Signal_Compare_Raw" AS
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
  FROM public."Y_codex_Layer3_Step33_Signal_Fill_Simple" t
  CROSS JOIN params p
  WHERE
    (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
),
by_dim AS (
  SELECT
    'BY_DIM'::text AS report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    signal_fill_source,
    count(*)::bigint AS row_cnt,
    avg(signal_missing_before_cnt)::numeric(18,6) AS avg_missing_before,
    avg(signal_missing_after_cnt)::numeric(18,6) AS avg_missing_after,
    sum(signal_missing_before_cnt)::bigint AS sum_missing_before,
    sum(signal_missing_after_cnt)::bigint AS sum_missing_after
  FROM base
  GROUP BY 2,3,4,5
),
overall AS (
  SELECT
    'OVERALL'::text AS report_section,
    NULL::text AS operator_id_raw,
    NULL::text AS tech_norm,
    NULL::date AS report_date,
    signal_fill_source,
    count(*)::bigint AS row_cnt,
    avg(signal_missing_before_cnt)::numeric(18,6) AS avg_missing_before,
    avg(signal_missing_after_cnt)::numeric(18,6) AS avg_missing_after,
    sum(signal_missing_before_cnt)::bigint AS sum_missing_before,
    sum(signal_missing_after_cnt)::bigint AS sum_missing_after
  FROM base
  GROUP BY 5
)
SELECT * FROM by_dim
UNION ALL
SELECT * FROM overall;

ANALYZE public."Y_codex_Layer3_Step34_Signal_Compare_Raw";

-- v2：人类友好指标表（方案 A）
CREATE TABLE public."Y_codex_Layer3_Step34_Signal_Compare" AS
WITH base AS (
  SELECT *
  FROM public."Y_codex_Layer3_Step34_Signal_Compare_Raw"
),
metrics AS (
  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    signal_fill_source,
    'SUM_MISSING_BEFORE'::text AS metric_code,
    '补齐前缺失字段总量'::text AS metric_name_cn,
    '数值仅用于对比；不做阻断'::text AS expected_rule_cn,
    sum_missing_before::numeric AS actual_value_num,
    'PASS'::text AS pass_flag,
    NULL::text AS remark_cn
  FROM base

  UNION ALL

  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    signal_fill_source,
    'SUM_MISSING_AFTER',
    '补齐后缺失字段总量',
    '必须：after <= before（补齐不允许使缺失变多）',
    sum_missing_after::numeric,
    CASE WHEN sum_missing_after <= sum_missing_before THEN 'PASS' ELSE 'FAIL' END,
    CASE WHEN sum_missing_after <= sum_missing_before THEN NULL ELSE '检查 Step33 补齐逻辑/字段映射' END
  FROM base

  UNION ALL

  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    signal_fill_source,
    'AVG_MISSING_BEFORE',
    '单行平均缺失字段数（补齐前）',
    '数值仅用于对比；不做阻断',
    avg_missing_before::numeric,
    'PASS',
    NULL
  FROM base

  UNION ALL

  SELECT
    report_section,
    operator_id_raw,
    tech_norm,
    report_date,
    signal_fill_source,
    'AVG_MISSING_AFTER',
    '单行平均缺失字段数（补齐后）',
    '必须：after <= before（补齐不允许使缺失变多）',
    avg_missing_after::numeric,
    CASE WHEN avg_missing_after <= avg_missing_before THEN 'PASS' ELSE 'FAIL' END,
    NULL
  FROM base
)
SELECT * FROM metrics;

ANALYZE public."Y_codex_Layer3_Step34_Signal_Compare";
