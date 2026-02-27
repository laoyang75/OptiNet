-- 临时检查表：cell_id = 5918736 在全库中的分布
--
-- 用途：
--   - 专门抽取 `cell_id = 5918736` 的所有 4G/5G 记录，写入一张临时检查表，
--     方便你查看它在不同运营商 / LAC 下的分布，以及对应的 16 进制 LAC、ENBID/基站ID 等。
--
-- 说明：
--   - 源表：public."网优cell项目_清洗补齐库_v1"
--   - 仅保留 tech 为 4G/5G 的记录（与 L1 规则一致）。
--   - 同时给出 L1-LAC / L1-CELL 合规标记，方便判断哪些记录本来就在 L1 范围内。
--
-- 使用方式（在 psql 中）：
--   \i Agent_Workspace/sql/tmp_cell_5918736_inspect_v1.sql
--   SELECT * FROM public.tmp_cell_5918736_inspect_v1
--   ORDER BY "运营商id", lac_dec, cell_id_dec
--   LIMIT 200;

BEGIN;

DROP TABLE IF EXISTS public.tmp_cell_5918736_inspect_v1;

CREATE TABLE public.tmp_cell_5918736_inspect_v1 AS
WITH base AS (
  SELECT
    t.*,
    lower(t.tech) AS tech_norm,

    -- 数值化 LAC
    CASE
      WHEN t."原始lac" IS NOT NULL
       AND btrim(t."原始lac") <> ''
       AND btrim(t."原始lac") ~ '^[0-9]+$'
      THEN t."原始lac"::bigint
      ELSE NULL
    END AS lac_dec,

    -- 数值化 cell_id
    CASE
      WHEN t.cell_id IS NOT NULL
       AND btrim(t.cell_id::text) <> ''
       AND btrim(t.cell_id::text) ~ '^[0-9]+$'
      THEN t.cell_id::bigint
      ELSE NULL
    END AS cell_id_dec,

    -- L1-LAC 合规标记
    (
      t."运营商id" IN ('46000','46001','46011','46015','46020') AND
      t."原始lac" IS NOT NULL AND
      btrim(t."原始lac") <> '' AND
      btrim(t."原始lac") ~ '^[0-9]+$' AND
      lower(t.tech) IN ('4g','5g')
    ) AS is_lac_L1_valid,

    -- L1-CELL 合规标记
    (
      t."运营商id" IN ('46000','46001','46011','46015','46020') AND
      t."原始lac" IS NOT NULL AND
      btrim(t."原始lac") <> '' AND
      btrim(t."原始lac") ~ '^[0-9]+$' AND
      lower(t.tech) IN ('4g','5g') AND
      t.cell_id IS NOT NULL AND
      btrim(t.cell_id::text) <> '' AND
      btrim(t.cell_id::text) ~ '^[0-9]+$' AND
      t.cell_id::bigint > 0 AND
      t.cell_id::bigint <> 2147483647
    ) AS is_cell_L1_valid

  FROM public."网优cell项目_清洗补齐库_v1" t
  WHERE t.cell_id IS NOT NULL
    AND btrim(t.cell_id::text) <> ''
    AND btrim(t.cell_id::text) ~ '^[0-9]+$'
    AND t.cell_id::bigint = 5918736
    AND lower(t.tech) IN ('4g','5g')
)
SELECT
  b.*,
  to_hex(b.cell_id_dec) AS cell_id_hex,
  CASE WHEN b.lac_dec IS NOT NULL THEN to_hex(b.lac_dec) END AS lac_hex,

  -- 4G/5G 基站ID（4G: ENBID; 5G: gNB ID）
  CASE
    WHEN b.tech_norm = '4g' AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec / 256::bigint
    WHEN b.tech_norm = '5g' AND b.cell_id_dec IS NOT NULL THEN b.cell_id_dec / 4096::bigint
    ELSE NULL
  END AS bs_id_dec,
  CASE
    WHEN b.tech_norm IN ('4g','5g')
     AND b.cell_id_dec IS NOT NULL THEN to_hex(
       CASE
         WHEN b.tech_norm = '4g' THEN b.cell_id_dec / 256::bigint
         WHEN b.tech_norm = '5g' THEN b.cell_id_dec / 4096::bigint
       END
     )
  END AS bs_id_hex,

  -- 小区号：4G=cell_id%256，5G=cell_id%4096
  CASE
    WHEN b.tech_norm = '4g' AND b.cell_id_dec IS NOT NULL THEN (b.cell_id_dec % 256::bigint)::integer
    WHEN b.tech_norm = '5g' AND b.cell_id_dec IS NOT NULL THEN (b.cell_id_dec % 4096::bigint)::integer
    ELSE NULL
  END AS cell_local_id

FROM base b;

COMMIT;
