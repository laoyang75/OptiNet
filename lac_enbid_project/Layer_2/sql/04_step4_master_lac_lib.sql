-- Layer_2 Step4：可信 LAC（active_days=7 + 规模门槛）
-- 输入：
--   public."Y_codex_Layer2_Step03_Lac_Stats_DB"
-- 输出：
--   public."Y_codex_Layer2_Step04_Master_Lac_Lib"

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

-- 性能辅助（幂等）：与 Step00 重复也无妨，确保本地迭代不会漏建索引
CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_gps_base_ts_std
  ON public."Y_codex_Layer0_Gps_base" USING brin (ts_std);
CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_lac_ts_std
  ON public."Y_codex_Layer0_Lac" USING brin (ts_std);
CREATE INDEX IF NOT EXISTS ix_y_codex_layer0_lac_join_keys_raw
  ON public."Y_codex_Layer0_Lac" ("运营商id", tech, lac_dec, cell_id_dec);

-- 清理旧命名（历史遗留）
DROP TABLE IF EXISTS public.d_step4_master_lac_lib;

DROP TABLE IF EXISTS public."Y_codex_Layer2_Step04_Master_Lac_Lib";

CREATE TABLE public."Y_codex_Layer2_Step04_Master_Lac_Lib" AS
WITH base AS (
  SELECT
    s.*,
    CASE
      WHEN s.operator_id_raw IN ('46000','46015','46020') THEN 'CMCC_FAMILY'
      WHEN s.operator_id_raw = '46001' THEN 'CUCC'
      WHEN s.operator_id_raw = '46011' THEN 'CTCC'
      ELSE 'OTHER'
    END AS op_group,
    CASE
      WHEN s.operator_id_raw IN ('46001','46011') AND s.tech_norm = '5G' THEN 3
      ELSE 5
    END AS device_min_required
  FROM public."Y_codex_Layer2_Step03_Lac_Stats_DB" s
  WHERE s.active_days = 7
    -- 明确剔除 LAC 溢出/占位值（避免被误纳入“可信LAC白名单”）
    AND s.lac_dec NOT IN (65534,65535,16777214,16777215,2147483647)
),
p80 AS (
  SELECT
    op_group,
    tech_norm,
    ceil(percentile_cont(0.8) WITHIN GROUP (ORDER BY record_count))::bigint AS p80_reports_min
  FROM base
  GROUP BY 1,2
),
scored AS (
  SELECT b.*, p.p80_reports_min
  FROM base b
  JOIN p80 p USING (op_group, tech_norm)
),
filtered AS (
  SELECT *
  FROM scored
  WHERE
    -- 46015/46020 数据量偏小：仅保留稳定性（7天），免除设备/上报门槛
    operator_id_raw IN ('46015','46020')
    OR (
      distinct_device_count >= device_min_required
      AND record_count >= p80_reports_min
    )
)
SELECT
  operator_id_raw,
  operator_group_hint,
  tech_norm,
  lac_dec,
  record_count,
  valid_gps_count,
  distinct_cellid_count,
  distinct_device_count,
  first_seen_ts,
  last_seen_ts,
  first_seen_date,
  last_seen_date,
  active_days,
  coalesce(valid_gps_count, 0)::bigint AS lac_confidence_score,
  dense_rank() OVER (
    PARTITION BY operator_id_raw, tech_norm
    ORDER BY coalesce(valid_gps_count, 0) DESC, coalesce(record_count, 0) DESC, lac_dec ASC
  )::int AS lac_confidence_rank,
  true AS is_trusted_lac
FROM filtered;

CREATE UNIQUE INDEX IF NOT EXISTS ux_y_codex_layer2_step04_master_lac_pk
  ON public."Y_codex_Layer2_Step04_Master_Lac_Lib" (operator_id_raw, tech_norm, lac_dec);

ANALYZE public."Y_codex_Layer2_Step04_Master_Lac_Lib";

COMMENT ON TABLE public."Y_codex_Layer2_Step04_Master_Lac_Lib" IS
'Step04 可信LAC集合：在 Step03 有效LAC汇总库中筛选 active_days=7 的稳定LAC，并叠加规模门槛（设备数>=5 且上报量>=P80；CU/CT 的5G设备门槛放宽为>=3；46015/46020 仅要求7天稳定），作为 Step05 构建映射的白名单。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".lac_dec IS 'LAC十进制 (LAC decimal)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".record_count IS '总上报次数 (Total records in Step03 for this key)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".valid_gps_count IS '有效GPS次数 (Records with has_gps=true in Step03)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".distinct_cellid_count IS '关联小区数 (Distinct cell_id_dec in Step03)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".distinct_device_count IS '关联设备数 (Distinct device_id in Step03)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".first_seen_ts IS '首次出现时间 (First seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".last_seen_ts IS '最后出现时间 (Last seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".first_seen_date IS '首次出现日期 (First seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".last_seen_date IS '最后出现日期 (Last seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".active_days IS '活跃天数 (Distinct report_date count; trusted set uses max(active_days))';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".lac_confidence_score IS
'LAC区域置信度分数 (LAC confidence score): 默认采用 valid_gps_count（7天内有效GPS上报量）作为置信度；用于多LAC小区收敛时的 tie-break。';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".lac_confidence_rank IS
'LAC区域置信度排名 (LAC confidence rank): 在 (operator_id_raw, tech_norm) 分组内按 lac_confidence_score desc 排名（稳定 tie-break）。';
COMMENT ON COLUMN public."Y_codex_Layer2_Step04_Master_Lac_Lib".is_trusted_lac IS
'是否可信LAC (Trusted LAC flag): true';


-- 验证 SQL（至少 3 条）
-- 1) 可信集合中 active_days 必须等于 Step3 最大值
-- select count(*) from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
-- where active_days <> (select max(active_days) from public."Y_codex_Layer2_Step03_Lac_Stats_DB");
-- 2) 主键重复检查（应返回 0 行）
-- select operator_id_raw, tech_norm, lac_dec, count(*) from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
-- group by 1,2,3 having count(*)>1;
-- 3) 可信 LAC 数量
-- select count(*) as trusted_lac_cnt from public."Y_codex_Layer2_Step04_Master_Lac_Lib";
