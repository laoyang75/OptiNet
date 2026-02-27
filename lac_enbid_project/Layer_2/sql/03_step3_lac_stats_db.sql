-- Layer_2 Step3：有效 LAC 汇总库（LAC 维度统计主表）
-- 输入：
--   public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" (is_compliant=true)
-- 输出：
--   public."Y_codex_Layer2_Step03_Lac_Stats_DB"

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
DROP TABLE IF EXISTS public.d_step3_lac_stats_db;

DROP TABLE IF EXISTS public."Y_codex_Layer2_Step03_Lac_Stats_DB";

CREATE TABLE public."Y_codex_Layer2_Step03_Lac_Stats_DB" AS
SELECT
  operator_id_raw,
  operator_group_hint,
  tech_norm,
  lac_dec,
  count(*)::bigint AS record_count,
  count(*) FILTER (WHERE has_gps)::bigint AS valid_gps_count,
  count(DISTINCT cell_id_dec)::bigint AS distinct_cellid_count,
  count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS distinct_device_count,
  min(ts_std) AS first_seen_ts,
  max(ts_std) AS last_seen_ts,
  min(report_date) AS first_seen_date,
  max(report_date) AS last_seen_date,
  count(DISTINCT report_date)::int AS active_days
FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
WHERE is_compliant
GROUP BY 1,2,3,4;

CREATE UNIQUE INDEX IF NOT EXISTS ux_y_codex_layer2_step03_lac_stats_pk
  ON public."Y_codex_Layer2_Step03_Lac_Stats_DB" (operator_id_raw, tech_norm, lac_dec);

ANALYZE public."Y_codex_Layer2_Step03_Lac_Stats_DB";

COMMENT ON TABLE public."Y_codex_Layer2_Step03_Lac_Stats_DB" IS
'Step03 有效LAC汇总库：仅基于 Step02 合规数据按 operator_id_raw+tech_norm+lac_dec 聚合，输出 record_count/valid_gps_count/active_days/first_last/distinct_* 等统计。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".lac_dec IS 'LAC十进制 (LAC decimal)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".record_count IS '总上报次数 (Total records in compliant set)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".valid_gps_count IS '有效GPS次数 (Records with has_gps=true)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".distinct_cellid_count IS '关联小区数 (Distinct cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".distinct_device_count IS '关联设备数 (Distinct device_id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".first_seen_ts IS '首次出现时间 (First seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".last_seen_ts IS '最后出现时间 (Last seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".first_seen_date IS '首次出现日期 (First seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".last_seen_date IS '最后出现日期 (Last seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step03_Lac_Stats_DB".active_days IS '活跃天数 (Distinct report_date count within window)';


-- 验证 SQL（至少 3 条）
-- 1) record_count 汇总应等于合规有效行数
-- select (select sum(record_count) from public."Y_codex_Layer2_Step03_Lac_Stats_DB") as lac_rollup_rows,
--        (select count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" where is_compliant) as compliant_rows;
-- 2) active_days 范围检查
-- select min(active_days), max(active_days) from public."Y_codex_Layer2_Step03_Lac_Stats_DB";
-- 3) 主键重复检查（应返回 0 行）
-- select operator_id_raw, tech_norm, lac_dec, count(*) from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
-- group by 1,2,3 having count(*)>1;
