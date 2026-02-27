-- Layer_2 Step0：标准化视图（不改原表，仅派生字段）
-- 输入：
--   public."Y_codex_Layer0_Gps_base"
--   public."Y_codex_Layer0_Lac"
-- 输出：
--   public."Y_codex_Layer2_Step00_Gps_Std"
--   public."Y_codex_Layer2_Step00_Lac_Std"

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

-- 性能辅助（幂等）：首次创建可能耗时较长；后续重跑会自动跳过
-- 1) 按日期切片（冒烟/分批）更友好
CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_gps_base_ts_std
  ON public."Y_codex_Layer0_Gps_base" USING brin (ts_std);

CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_lac_ts_std
  ON public."Y_codex_Layer0_Lac" USING brin (ts_std);

-- 2) Step06 join 加速（注意：operator_id_raw 在视图里做了 btrim/NULLIF，若需极致性能建议后续迭代改为表达式索引或物化）
CREATE INDEX IF NOT EXISTS ix_y_codex_layer0_lac_join_keys_raw
  ON public."Y_codex_Layer0_Lac" ("运营商id", tech, lac_dec, cell_id_dec);

-- 依赖注意：Step02 合规视图依赖 Step00 标准化视图；重跑 Step00 前需先删 Step02 视图，否则 DROP Step00 会失败
DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step02_Gps_Compliance_Marked'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    END IF;
  END IF;
END $$;

-- 兼容重跑：如果历史上把 Step00 物化成 TABLE，这里会自动清理后再建 VIEW
DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer2_Step00_Gps_Std"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step00_Gps_Std'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step00_Gps_Std"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step00_Gps_Std"';
    END IF;
  END IF;

  IF to_regclass('public."Y_codex_Layer2_Step00_Lac_Std"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step00_Lac_Std'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step00_Lac_Std"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step00_Lac_Std"';
    END IF;
  END IF;

  -- 清理旧命名（历史遗留）
  IF to_regclass('public.v_layer2_gps_std') IS NOT NULL THEN
    EXECUTE 'DROP VIEW public.v_layer2_gps_std';
  END IF;
  IF to_regclass('public.v_layer2_lac_std') IS NOT NULL THEN
    EXECUTE 'DROP VIEW public.v_layer2_lac_std';
  END IF;
END $$;

CREATE OR REPLACE VIEW public."Y_codex_Layer2_Step00_Gps_Std" AS
WITH base AS (
  SELECT
    t.*,
    NULLIF(btrim(t."运营商id"), '') AS operator_id_raw,
    COALESCE(NULLIF(btrim(t.did), ''), NULLIF(btrim(t.oaid), '')) AS device_id
  FROM public."Y_codex_Layer0_Gps_base" t
)
SELECT
  b.*,
  CASE
    WHEN b.tech = '4G' THEN '4G'
    WHEN b.tech = '5G' THEN '5G'
    WHEN b.tech IN ('2G','3G') THEN '2_3G'
    ELSE '其他'
  END AS tech_norm,
  CASE
    WHEN b.operator_id_raw IN ('46000','46015','46020') THEN 'CMCC'
    WHEN b.operator_id_raw = '46001' THEN 'CUCC'
    WHEN b.operator_id_raw = '46011' THEN 'CTCC'
    ELSE 'OTHER'
  END AS operator_group_hint,
  (b.ts_std::date) AS report_date,
  CASE
    WHEN b."原始lac" IS NOT NULL AND btrim(b."原始lac") <> '' THEN length(btrim(b."原始lac"))
  END AS lac_len,
  CASE
    WHEN b.cell_id IS NOT NULL AND btrim(b.cell_id) <> '' THEN length(btrim(b.cell_id))
  END AS cell_len,
  (b.cell_id_dec IS NOT NULL) AS has_cellid,
  (b.lac_dec IS NOT NULL) AS has_lac,
  (
    b.lon IS NOT NULL
    AND b.lat IS NOT NULL
    AND b.lon BETWEEN -180 AND 180
    AND b.lat BETWEEN -90 AND 90
    AND NOT (b.lon = 0 AND b.lat = 0)
  ) AS has_gps
FROM base b;


CREATE OR REPLACE VIEW public."Y_codex_Layer2_Step00_Lac_Std" AS
WITH base AS (
  SELECT
    t.*,
    NULLIF(btrim(t."运营商id"), '') AS operator_id_raw,
    COALESCE(NULLIF(btrim(t.did), ''), NULLIF(btrim(t.oaid), '')) AS device_id
  FROM public."Y_codex_Layer0_Lac" t
)
SELECT
  b.*,
  CASE
    WHEN b.tech = '4G' THEN '4G'
    WHEN b.tech = '5G' THEN '5G'
    WHEN b.tech IN ('2G','3G') THEN '2_3G'
    ELSE '其他'
  END AS tech_norm,
  CASE
    WHEN b.operator_id_raw IN ('46000','46015','46020') THEN 'CMCC'
    WHEN b.operator_id_raw = '46001' THEN 'CUCC'
    WHEN b.operator_id_raw = '46011' THEN 'CTCC'
    ELSE 'OTHER'
  END AS operator_group_hint,
  (b.ts_std::date) AS report_date,
  CASE
    WHEN b."原始lac" IS NOT NULL AND btrim(b."原始lac") <> '' THEN length(btrim(b."原始lac"))
  END AS lac_len,
  CASE
    WHEN b.cell_id IS NOT NULL AND btrim(b.cell_id) <> '' THEN length(btrim(b.cell_id))
  END AS cell_len,
  (b.cell_id_dec IS NOT NULL) AS has_cellid,
  (b.lac_dec IS NOT NULL) AS has_lac,
  (
    b.lon IS NOT NULL
    AND b.lat IS NOT NULL
    AND b.lon BETWEEN -180 AND 180
    AND b.lat BETWEEN -90 AND 90
    AND NOT (b.lon = 0 AND b.lat = 0)
  ) AS has_gps
FROM base b;

COMMENT ON VIEW public."Y_codex_Layer2_Step00_Gps_Std" IS
'Step00 标准化视图（GPS 路）：统一派生 tech_norm/operator_id_raw/report_date/has_* 等字段，后续 Step01~Step06 统一口径使用。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".tech_norm IS
'制式_标准化 (Normalized tech): 4G/5G/2_3G/其他';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".operator_id_raw IS
'运营商id_细粒度 (Raw operator id): NULLIF(btrim("运营商id"),'''')';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".operator_group_hint IS
'运营商组_提示 (Operator group hint): CMCC/CUCC/CTCC/OTHER';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".report_date IS
'上报日期 (Report date): ts_std::date';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".device_id IS
'设备ID (Device id): coalesce(did, oaid)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".lac_len IS
'lac长度 (Length of raw LAC string): 用于排查，不作为硬过滤';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".cell_len IS
'cell长度 (Length of raw cell string): 用于排查，不作为硬过滤';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".has_cellid IS
'是否有cell (Has cell_id_dec): cell_id_dec is not null';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".has_lac IS
'是否有lac (Has lac_dec): lac_dec is not null';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Gps_Std".has_gps IS
'是否有gps (Has valid lon/lat): 合法范围且不为(0,0)';

COMMENT ON VIEW public."Y_codex_Layer2_Step00_Lac_Std" IS
'Step00 标准化视图（LAC 路）：统一派生 tech_norm/operator_id_raw/report_date/has_* 等字段，供 Step06 与对比报表使用。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".tech_norm IS
'制式_标准化 (Normalized tech): 4G/5G/2_3G/其他';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".operator_id_raw IS
'运营商id_细粒度 (Raw operator id): NULLIF(btrim("运营商id"),'''')';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".operator_group_hint IS
'运营商组_提示 (Operator group hint): CMCC/CUCC/CTCC/OTHER';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".report_date IS
'上报日期 (Report date): ts_std::date';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".device_id IS
'设备ID (Device id): coalesce(did, oaid)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".lac_len IS
'lac长度 (Length of raw LAC string): 用于排查，不作为硬过滤';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".cell_len IS
'cell长度 (Length of raw cell string): 用于排查，不作为硬过滤';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".has_cellid IS
'是否有cell (Has cell_id_dec): cell_id_dec is not null';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".has_lac IS
'是否有lac (Has lac_dec): lac_dec is not null';
COMMENT ON COLUMN public."Y_codex_Layer2_Step00_Lac_Std".has_gps IS
'是否有gps (Has valid lon/lat): 合法范围且不为(0,0)';

-- 验证 SQL（至少 3 条）
-- 1) 行数一致性
-- select (select count(*) from public."Y_codex_Layer0_Gps_base") as gps_l0_rows,
--        (select count(*) from public."Y_codex_Layer2_Step00_Gps_Std") as gps_std_rows;
-- 2) tech_norm 分布
-- select tech_norm, count(*) from public."Y_codex_Layer2_Step00_Gps_Std" group by 1 order by 2 desc;
-- 3) operator_group_hint 分布
-- select operator_group_hint, count(*) from public."Y_codex_Layer2_Step00_Gps_Std" group by 1 order by 2 desc;
