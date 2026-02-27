-- Layer_2 Step1：基础统计（Raw + ValidCell 两套）
-- 输入：
--   public."Y_codex_Layer2_Step00_Gps_Std"
-- 输出：
--   public."Y_codex_Layer2_Step01_BaseStats_Raw"
--   public."Y_codex_Layer2_Step01_BaseStats_ValidCell"

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
DROP TABLE IF EXISTS public.rpt_step1_base_stats_raw;
DROP TABLE IF EXISTS public.rpt_step1_base_stats_valid_cell;

DROP TABLE IF EXISTS public."Y_codex_Layer2_Step01_BaseStats_Raw";

CREATE TABLE public."Y_codex_Layer2_Step01_BaseStats_Raw" AS
WITH agg AS (
  SELECT
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    parsed_from,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec) FILTER (WHERE cell_id_dec IS NOT NULL)::bigint AS cell_cnt,
    count(DISTINCT lac_dec) FILTER (WHERE lac_dec IS NOT NULL)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt,
    count(*) FILTER (WHERE NOT has_cellid)::bigint AS no_cellid_rows,
    count(*) FILTER (WHERE NOT has_lac)::bigint AS no_lac_rows,
    count(*) FILTER (WHERE NOT has_gps)::bigint AS no_gps_rows
  FROM public."Y_codex_Layer2_Step00_Gps_Std"
  GROUP BY 1,2,3,4
)
SELECT
  a.*,
  round(a.row_cnt::numeric / nullif(sum(a.row_cnt) OVER (), 0), 8) AS row_pct,
  round(a.no_cellid_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_cellid_pct,
  round(a.no_lac_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_lac_pct,
  round(a.no_gps_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_gps_pct
FROM agg a;

ANALYZE public."Y_codex_Layer2_Step01_BaseStats_Raw";


DROP TABLE IF EXISTS public."Y_codex_Layer2_Step01_BaseStats_ValidCell";

CREATE TABLE public."Y_codex_Layer2_Step01_BaseStats_ValidCell" AS
WITH base AS (
  SELECT *
  FROM public."Y_codex_Layer2_Step00_Gps_Std" t
  WHERE
    -- L1-CELL 起点规则（来自 Layer_1/Cell/Cell_Filter_Rules_v1.md）
    t.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND t.tech_norm IN ('4G','5G')
    AND t.lac_dec IS NOT NULL
    AND t.lac_dec > 0
    AND t.cell_id_dec IS NOT NULL
    AND t.cell_id_dec > 0
    AND t.cell_id_dec <> 2147483647
),
agg AS (
  SELECT
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    parsed_from,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt,
    count(*) FILTER (WHERE NOT has_cellid)::bigint AS no_cellid_rows,
    count(*) FILTER (WHERE NOT has_lac)::bigint AS no_lac_rows,
    count(*) FILTER (WHERE NOT has_gps)::bigint AS no_gps_rows
  FROM base
  GROUP BY 1,2,3,4
)
SELECT
  a.*,
  round(a.row_cnt::numeric / nullif(sum(a.row_cnt) OVER (), 0), 8) AS row_pct,
  round(a.no_cellid_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_cellid_pct,
  round(a.no_lac_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_lac_pct,
  round(a.no_gps_rows::numeric / nullif(a.row_cnt, 0), 8) AS no_gps_pct
FROM agg a;

ANALYZE public."Y_codex_Layer2_Step01_BaseStats_ValidCell";

COMMENT ON TABLE public."Y_codex_Layer2_Step01_BaseStats_Raw" IS
'Step01 基础统计（RAW）：对 Step00 标准化 GPS 明细按 tech/operator/parsed_from 聚合统计行数、去重 cell/lac/设备、缺值结构。';
COMMENT ON TABLE public."Y_codex_Layer2_Step01_BaseStats_ValidCell" IS
'Step01 基础统计（VALID_CELL）：在 RAW 基础上仅应用 Layer_1 Cell 的数值合规起点规则后再聚合统计，用于 Step02 合规前后对比。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".parsed_from IS '解析来源 (Parsed source)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".row_cnt IS '行数 (Row count)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".row_pct IS '行占比 (Row percentage within RAW)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".cell_cnt IS '去重小区数 (Distinct cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".lac_cnt IS '去重LAC数 (Distinct lac_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".device_cnt IS '设备数 (Distinct device_id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_cellid_rows IS '无cell行数 (Rows without cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_lac_rows IS '无lac行数 (Rows without lac_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_gps_rows IS '无gps行数 (Rows without valid GPS)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_cellid_pct IS '无cell占比 (Share of rows without cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_lac_pct IS '无lac占比 (Share of rows without lac_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_Raw".no_gps_pct IS '无gps占比 (Share of rows without valid GPS)';

COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".parsed_from IS '解析来源 (Parsed source)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".row_cnt IS '行数 (Row count)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".row_pct IS '行占比 (Row percentage within VALID_CELL)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".cell_cnt IS '去重小区数 (Distinct cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".lac_cnt IS '去重LAC数 (Distinct lac_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".device_cnt IS '设备数 (Distinct device_id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_cellid_rows IS '无cell行数 (Should be ~0 after filtering)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_lac_rows IS '无lac行数 (Should be ~0 after filtering)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_gps_rows IS '无gps行数 (Rows without valid GPS)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_cellid_pct IS '无cell占比 (Should be ~0 after filtering)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_lac_pct IS '无lac占比 (Should be ~0 after filtering)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step01_BaseStats_ValidCell".no_gps_pct IS '无gps占比 (Share of rows without valid GPS)';


-- 验证 SQL（至少 3 条）
-- 1) raw 汇总行数应等于输入行数
-- select (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw") as rpt_rows,
--        (select count(*) from public."Y_codex_Layer2_Step00_Gps_Std") as input_rows;
-- 2) valid_cell 行数应 <= raw
-- select (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_ValidCell") as valid_cell_rows,
--        (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw") as raw_rows;
-- 3) parsed_from 分布（raw）
-- select parsed_from, sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw" group by 1 order by 2 desc;
