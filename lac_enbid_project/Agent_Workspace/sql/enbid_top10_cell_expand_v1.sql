-- ENBID / 基站分析：基于 4G `cell_id` TOP10 扩展到 ENBID 下所有 Cell
--
-- 用途：
--   1. 在 L1-CELL 合规视图 `public.v_cell_L1_stage1` 上，统计全网 4G `cell_id` TOP10（不区分运营商）。
--   2. 将这 10 个高频 4G `cell_id` 映射为 ENBID（4G：cell_id / 256）。
--   3. 回到原始大表 `public."网优cell项目_清洗补齐库_v1"`，在对应 ENBID + 运营商下，捞出所有 4G/5G 的 cell：
--        - 计算十进制 / 十六进制的 cell_id 和 LAC；
--        - 计算 ENBID / 基站ID（4G: /256, 5G: /4096）及小区号；
--        - 统计每个 cell 的上报次数；
--        - 统计每个 ENBID / 基站ID 下有多少个不同的 cell_id；
--        - 按 L1-LAC / L1-CELL 规则标记每条记录是否“合规”（用于识别过滤前的异常数据）。
--   4. 结果写入表：public.enbid_top10_cell_detail
--
-- 使用前提：
--   - 已在数据库中创建 L1-LAC / L1-CELL 视图：
--       * public.v_lac_L1_stage1   （见 Layer_1/Lac/Lac_Filter_Rules_v1.md）
--       * public.v_cell_L1_stage1  （见 Layer_1/Cell/Cell_Filter_Rules_v1.md 或 README）
--   - 源表为：public."网优cell项目_清洗补齐库_v1"
--
-- 使用方法（示例）：
--   \i Agent_Workspace/sql/enbid_top10_cell_expand_v1.sql
--   SELECT * FROM public.enbid_top10_cell_detail
--   ORDER BY is_seed_cell DESC, seed_rank, plmn_id, bs_id_dec, cell_id_dec;
--
-- 说明：
--   - 本脚本当前只以 **4G TOP10 cell_id** 作为种子（对应你之前觉得异常的 4G TOP 列表）。
--   - 如需改成 5G，只需把 `WHERE lower(t.tech) = '4g'` 改成 `'5g'`，并视需要调整除数（5G 仍用 4096）。

BEGIN;

-- 1. 结果表定义（如不存在则创建）
CREATE TABLE IF NOT EXISTS public.enbid_top10_cell_detail (
  tech_norm        text,      -- '4g' / '5g'
  plmn_id          text,      -- 运营商id（PLMN）
  is_seed_cell     boolean,   -- 是否为 TOP10 的那个 cell
  seed_rank        integer,   -- 在 TOP10 中的排名（1-10）

  cell_id_dec      bigint,    -- 十进制 cell_id
  cell_id_hex      text,      -- 十六进制 cell_id
  lac_dec          bigint,    -- 十进制 LAC
  lac_hex          text,      -- 十六进制 LAC

  bs_id_dec        bigint,    -- 4G: ENBID；5G: 基站ID（cell_id / 256 或 / 4096）
  bs_id_hex        text,      -- ENBID / 基站ID 的十六进制
  cell_local_id    integer,   -- 小区号：4G = cell_id % 256；5G = cell_id % 4096

  cnt_reports      bigint,    -- 该 cell 在 ENBID 范围内的记录数（上报次数）
  bs_cell_cnt      bigint,    -- 同一 ENBID / 基站ID 下的不同 cell_id 数量

  is_cell_L1_valid boolean,   -- 是否满足 L1-CELL 规则（格式 + 无效值过滤）
  is_lac_L1_valid  boolean    -- 是否满足 L1-LAC 规则（LAC 数值合规 + 制式 4G/5G）
);

-- 清空旧结果
TRUNCATE TABLE public.enbid_top10_cell_detail;

-- 2. 主逻辑：4G TOP10 → ENBID → ENBID 下所有 Cell（含异常标记）
INSERT INTO public.enbid_top10_cell_detail (
  tech_norm,
  plmn_id,
  is_seed_cell,
  seed_rank,
  cell_id_dec,
  cell_id_hex,
  lac_dec,
  lac_hex,
  bs_id_dec,
  bs_id_hex,
  cell_local_id,
  cnt_reports,
  bs_cell_cnt,
  is_cell_L1_valid,
  is_lac_L1_valid
)
WITH
-- 2.1 在 L1-CELL 视图上，只取 4G，用来算 TOP10
cell_l1 AS (
  SELECT
    lower(t.tech)       AS tech_norm,
    t."运营商id"        AS plmn_id,
    t.cell_id::bigint   AS cell_id_dec
  FROM public.v_cell_L1_stage1 t
  WHERE lower(t.tech) = '4g'
),
-- 2.2 按 cell_id 聚合，计算全网（5 个 PLMN 合并）的 4G TOP10
top10_global AS (
  SELECT
    c.cell_id_dec,
    COUNT(*) AS cnt_reports_global,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS seed_rank
  FROM cell_l1 c
  GROUP BY c.cell_id_dec
  ORDER BY cnt_reports_global DESC
  LIMIT 10
),
-- 2.3 对于 TOP10 中的每个 cell_id，拆分到各运营商，保留 per-PLMN 统计
seed_by_plmn AS (
  SELECT
    c.tech_norm,
    c.plmn_id,
    c.cell_id_dec,
    g.seed_rank,
    g.cnt_reports_global,
    COUNT(*) AS cnt_reports_plmn
  FROM cell_l1 c
  JOIN top10_global g
    ON c.cell_id_dec = g.cell_id_dec
  GROUP BY c.tech_norm, c.plmn_id, c.cell_id_dec, g.seed_rank, g.cnt_reports_global
),
-- 2.4 给种子 cell 算 ENBID / 基站ID（当前 seeds 只有 4G：cell_id / 256）
seed_bs AS (
  SELECT
    s.tech_norm,
    s.plmn_id,
    s.cell_id_dec,
    s.seed_rank,
    s.cnt_reports_global,
    s.cnt_reports_plmn,
    CASE
      WHEN s.tech_norm = '4g' THEN s.cell_id_dec / 256::bigint
      WHEN s.tech_norm = '5g' THEN s.cell_id_dec / 4096::bigint
      ELSE NULL
    END AS bs_id_dec
  FROM seed_by_plmn s
),
-- 2.5 原始大表 + L1 规则标记（用于区分“过滤前的异常”）
base AS (
  SELECT
    b.*,
    lower(b.tech) AS tech_norm,
    b."运营商id"  AS plmn_id,

    -- 数值化 LAC
    CASE
      WHEN b."原始lac" IS NOT NULL
       AND btrim(b."原始lac") <> ''
       AND btrim(b."原始lac") ~ '^[0-9]+$'
      THEN b."原始lac"::bigint
      ELSE NULL
    END AS lac_dec,

    -- 数值化 cell_id
    CASE
      WHEN b.cell_id IS NOT NULL
       AND btrim(b.cell_id::text) <> ''
       AND btrim(b.cell_id::text) ~ '^[0-9]+$'
      THEN b.cell_id::bigint
      ELSE NULL
    END AS cell_id_dec,

    -- L1-LAC 规则（见 Layer_1/Lac/Lac_Filter_Rules_v1.md）
    (
      b."运营商id" IN ('46000','46001','46011','46015','46020') AND
      b."原始lac" IS NOT NULL AND
      btrim(b."原始lac") <> '' AND
      btrim(b."原始lac") ~ '^[0-9]+$' AND
      lower(b.tech) IN ('4g','5g')
    ) AS is_lac_L1_valid,

    -- L1-CELL 规则（见 Layer_1/Cell/Cell_Filter_Rules_v1.md）
    (
      b."运营商id" IN ('46000','46001','46011','46015','46020') AND
      b."原始lac" IS NOT NULL AND
      btrim(b."原始lac") <> '' AND
      btrim(b."原始lac") ~ '^[0-9]+$' AND
      lower(b.tech) IN ('4g','5g') AND
      b.cell_id IS NOT NULL AND
      btrim(b.cell_id::text) <> '' AND
      btrim(b.cell_id::text) ~ '^[0-9]+$' AND
      b.cell_id::bigint > 0 AND
      b.cell_id::bigint <> 2147483647
    ) AS is_cell_L1_valid

  FROM public."网优cell项目_清洗补齐库_v1" b
  WHERE lower(b.tech) IN ('4g','5g')
),
-- 2.6 在原始数据上，根据制式计算 ENBID / 基站ID + 小区号
base_with_bs AS (
  SELECT
    b.*,
    CASE
      WHEN b.tech_norm = '4g'
       AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec / 256::bigint
      WHEN b.tech_norm = '5g'
       AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec / 4096::bigint
      ELSE NULL
    END AS bs_id_dec,
    CASE
      WHEN b.tech_norm = '4g'
       AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec % 256::bigint
      WHEN b.tech_norm = '5g'
       AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec % 4096::bigint
      ELSE NULL
    END AS cell_local_id
  FROM base b
),
-- 2.7 在每个 (运营商, ENBID/基站ID) 下，挑出所有 cell（包括 4G/5G），并标记哪些是种子 cell
seed_and_neighbors AS (
  SELECT
    b.tech_norm,
    b.plmn_id,
    b.lac_dec,
    b.cell_id_dec,
    b.bs_id_dec,
    b.cell_local_id,
    b.is_cell_L1_valid,
    b.is_lac_L1_valid,

    s.seed_rank,
    s.cell_id_dec       AS seed_cell_id_dec,
    s.cnt_reports_global,
    s.cnt_reports_plmn,

    (b.cell_id_dec = s.cell_id_dec
     AND b.tech_norm = s.tech_norm) AS is_seed_cell

  FROM base_with_bs b
  JOIN seed_bs s
    ON b.tech_norm = s.tech_norm
   AND b.plmn_id   = s.plmn_id
   AND b.bs_id_dec = s.bs_id_dec
),
-- 2.8 每个 cell 在该 ENBID / 基站ID 范围内的上报次数
cell_stats AS (
  SELECT
    tech_norm,
    plmn_id,
    lac_dec,
    cell_id_dec,
    bs_id_dec,
    cell_local_id,
    is_cell_L1_valid,
    is_lac_L1_valid,
    seed_rank,
    seed_cell_id_dec,
    MAX(cnt_reports_global) AS seed_cnt_global,  -- 对同一 seed_rank 恒定
    MAX(cnt_reports_plmn)   AS seed_cnt_plmn,    -- 对同一 (seed_rank, plmn) 恒定
    BOOL_OR(is_seed_cell)   AS is_seed_cell,
    COUNT(*)                AS cnt_reports
  FROM seed_and_neighbors
  GROUP BY
    tech_norm,
    plmn_id,
    lac_dec,
    cell_id_dec,
    bs_id_dec,
    cell_local_id,
    is_cell_L1_valid,
    is_lac_L1_valid,
    seed_rank,
    seed_cell_id_dec
),
-- 2.9 每个 ENBID / 基站ID 下有多少个不同的 cell_id（用于判断“这个 ENBID 下 cell 是否异常地多”）
bs_stats AS (
  SELECT
    tech_norm,
    plmn_id,
    bs_id_dec,
    COUNT(DISTINCT cell_id_dec) AS bs_cell_cnt
  FROM cell_stats
  GROUP BY tech_norm, plmn_id, bs_id_dec
)
-- 2.10 写入结果表
SELECT
  c.tech_norm,
  c.plmn_id,
  c.is_seed_cell,
  c.seed_rank,

  c.cell_id_dec,
  CASE WHEN c.cell_id_dec IS NOT NULL THEN to_hex(c.cell_id_dec) END AS cell_id_hex,
  c.lac_dec,
  CASE WHEN c.lac_dec IS NOT NULL THEN to_hex(c.lac_dec) END         AS lac_hex,

  c.bs_id_dec,
  CASE WHEN c.bs_id_dec IS NOT NULL THEN to_hex(c.bs_id_dec) END     AS bs_id_hex,
  c.cell_local_id::integer,

  c.cnt_reports,
  b.bs_cell_cnt,

  c.is_cell_L1_valid,
  c.is_lac_L1_valid
FROM cell_stats c
LEFT JOIN bs_stats b
  ON c.tech_norm = b.tech_norm
 AND c.plmn_id   = b.plmn_id
 AND c.bs_id_dec = b.bs_id_dec;

COMMIT;
