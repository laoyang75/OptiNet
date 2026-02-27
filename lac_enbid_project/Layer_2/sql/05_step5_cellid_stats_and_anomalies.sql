-- Layer_2 Step5：可信映射统计底座 + Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac
-- 输入：
--   public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" (is_compliant=true)
--   public."Y_codex_Layer2_Step04_Master_Lac_Lib"
-- 输出：
--   public."Y_codex_Layer2_Step05_CellId_Stats_DB"
--   public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"

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

-- 重跑注意：Step06（可能是 VIEW/TABLE）会依赖 Step05 映射表；重跑 Step05 前需先删 Step06 输出对象，避免 DROP Step05 失败
-- 若你的 SQL 控制台会按 ';' 拆分导致 DO 块失败，请用 psql -f 执行整文件，或手工删除 Step06 输出对象后再跑 Step05。
DO $$
BEGIN
  -- Step06 对比表（TABLE）
  IF to_regclass('public."Y_codex_Layer2_Step06_GpsVsLac_Compare"') IS NOT NULL THEN
    EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step06_GpsVsLac_Compare"';
  END IF;
  IF to_regclass('public.rpt_step6_gps_vs_lac_compare') IS NOT NULL THEN
    EXECUTE 'DROP TABLE public.rpt_step6_gps_vs_lac_compare';
  END IF;

  -- Step06 明细对象（可能是 VIEW/TABLE）
  IF to_regclass('public."Y_codex_Layer2_Step06_L0_Lac_Filtered"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step06_L0_Lac_Filtered'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step06_L0_Lac_Filtered"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"';
    END IF;
  END IF;

  -- 清理旧命名（历史遗留）
  IF to_regclass('public.d_step6_l0_lac_filtered') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'd_step6_l0_lac_filtered'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public.d_step6_l0_lac_filtered';
    ELSE
      EXECUTE 'DROP TABLE public.d_step6_l0_lac_filtered';
    END IF;
  END IF;
END $$;

-- 重跑注意：anomaly 视图依赖映射表，需先删视图再删表
DROP VIEW IF EXISTS public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac";
DROP VIEW IF EXISTS public.anomaly_cell_multi_lac; -- 旧命名（历史遗留）

-- 清理旧命名（历史遗留）
DROP TABLE IF EXISTS public.d_step5_cellid_stats_db;

DROP TABLE IF EXISTS public."Y_codex_Layer2_Step05_CellId_Stats_DB";

CREATE TABLE public."Y_codex_Layer2_Step05_CellId_Stats_DB" AS
SELECT
  m.operator_id_raw,
  m.operator_group_hint,
  m.tech_norm,
  m.lac_dec,
  m.cell_id_dec,
  count(*)::bigint AS record_count,
  count(*) FILTER (WHERE m.has_gps)::bigint AS valid_gps_count,
  count(DISTINCT m.device_id) FILTER (WHERE m.device_id IS NOT NULL)::bigint AS distinct_device_count,
  min(m.ts_std) AS first_seen_ts,
  max(m.ts_std) AS last_seen_ts,
  min(m.report_date) AS first_seen_date,
  max(m.report_date) AS last_seen_date,
  count(DISTINCT m.report_date)::int AS active_days,
  avg(m.lon) FILTER (WHERE m.has_gps)::double precision AS gps_center_lon,
  avg(m.lat) FILTER (WHERE m.has_gps)::double precision AS gps_center_lat
FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" m
JOIN public."Y_codex_Layer2_Step04_Master_Lac_Lib" l
  ON m.operator_id_raw = l.operator_id_raw
 AND m.tech_norm = l.tech_norm
 AND m.lac_dec = l.lac_dec
WHERE m.is_compliant
GROUP BY 1,2,3,4,5;

CREATE UNIQUE INDEX IF NOT EXISTS ux_y_codex_layer2_step05_cellid_stats_pk
  ON public."Y_codex_Layer2_Step05_CellId_Stats_DB" (operator_id_raw, tech_norm, lac_dec, cell_id_dec);

CREATE INDEX IF NOT EXISTS ix_y_codex_layer2_step05_cell_lookup
  ON public."Y_codex_Layer2_Step05_CellId_Stats_DB" (operator_id_raw, tech_norm, cell_id_dec);

ANALYZE public."Y_codex_Layer2_Step05_CellId_Stats_DB";


CREATE OR REPLACE VIEW public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" AS
SELECT
  operator_id_raw,
  operator_group_hint,
  tech_norm,
  cell_id_dec,
  count(DISTINCT lac_dec)::int AS lac_distinct_cnt,
  array_to_string(array_agg(DISTINCT lac_dec ORDER BY lac_dec), ',') AS lac_list,
  sum(record_count)::bigint AS record_count,
  min(first_seen_ts) AS first_seen_ts,
  max(last_seen_ts) AS last_seen_ts
FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
GROUP BY 1,2,3,4
HAVING count(DISTINCT lac_dec) > 1;


-- anomaly 查询样例
-- select * from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
-- order by lac_distinct_cnt desc, record_count desc
-- limit 100;

COMMENT ON TABLE public."Y_codex_Layer2_Step05_CellId_Stats_DB" IS
'Step05 可信映射统计底座：在 Step04 可信LAC白名单内，对 Step02 合规明细按 operator+tech+lac+cell 聚合，输出 record_count/valid_gps_count/active_days/first_last/distinct_device_count/gps_center。';

COMMENT ON VIEW public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" IS
'Step05 异常监测清单：同一 operator+tech+cell_id_dec 对应多个 lac_dec（lac_distinct_cnt>1），用于定位 cell↔lac 多对多异常。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".lac_dec IS 'LAC十进制 (LAC decimal)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".cell_id_dec IS 'Cell十进制 (Cell id decimal)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".record_count IS '总上报次数 (Total records in mapping key)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".valid_gps_count IS '有效GPS次数 (Records with has_gps=true)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".distinct_device_count IS '关联设备数 (Distinct device_id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".first_seen_ts IS '首次出现时间 (First seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".last_seen_ts IS '最后出现时间 (Last seen timestamp)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".first_seen_date IS '首次出现日期 (First seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".last_seen_date IS '最后出现日期 (Last seen report_date)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".active_days IS '活跃天数 (Distinct report_date count)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".gps_center_lon IS
'GPS中心经度 (GPS center longitude): avg(lon) over has_gps=true';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_CellId_Stats_DB".gps_center_lat IS
'GPS中心纬度 (GPS center latitude): avg(lat) over has_gps=true';

COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".cell_id_dec IS 'Cell十进制 (Cell id decimal)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".lac_distinct_cnt IS '关联LAC去重数 (Distinct lac_dec count; >1)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".lac_list IS 'LAC列表 (Sorted distinct lac_dec list, comma-separated)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".record_count IS '总上报次数 (Sum of mapping record_count across LACs)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".first_seen_ts IS '首次出现时间 (Min first_seen_ts across LACs)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac".last_seen_ts IS '最后出现时间 (Max last_seen_ts across LACs)';

-- 验证 SQL（至少 3 条）
-- 1) anomaly 必须全部 >1
-- select count(*) from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" where lac_distinct_cnt <= 1;
-- 2) valid_gps_count 不应超过 record_count
-- select count(*) from public."Y_codex_Layer2_Step05_CellId_Stats_DB" where valid_gps_count > record_count;
-- 3) 主键重复检查（应返回 0 行）
-- select operator_id_raw, tech_norm, lac_dec, cell_id_dec, count(*)
-- from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
-- group by 1,2,3,4 having count(*)>1;
