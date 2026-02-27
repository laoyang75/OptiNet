# L1-CELL：北京 L0 源表筛选规则 v1

> 目标：在北京两张 L0 标准表的基础上，按既有 L1-CELL 规则筛出 cell_id 合规子集。规则与 `Layer_1/Cell/Cell_Filter_Rules_v1.md` 一致，仅替换输入表与输出视图名。

## 1. 输入

- GPS 源 L0 表：`public.l0_gps_bj_detail_20251201_20251207_v1`
- LAC 源 L0 表：`public.l0_lac_bj_detail_20251201_20251207_v1`

两表均需包含标准字段：`"运营商id"`, `"原始lac"`, `cell_id`, `tech`。

## 2. 输出视图

- GPS 源 L1-CELL 合规起点：`public.v_l0_gps_bj_L1_cell_stage1`
- LAC 源 L1-CELL 合规起点：`public.v_l0_lac_bj_L1_cell_stage1`

## 3. 可直接执行的 SQL

```sql
-- GPS 源
CREATE OR REPLACE VIEW public.v_l0_gps_bj_L1_cell_stage1 AS
SELECT t.*
FROM public.l0_gps_bj_detail_20251201_20251207_v1 t
WHERE
  t."运营商id" IN ('46000','46001','46011','46015','46020')
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$'
  AND lower(t.tech) IN ('4g','5g')
  AND t.cell_id IS NOT NULL
  AND btrim(t.cell_id::text) <> ''
  AND btrim(t.cell_id::text) ~ '^[0-9]+$'
  AND t.cell_id::bigint > 0
  AND t.cell_id::bigint <> 2147483647;

-- LAC 源
CREATE OR REPLACE VIEW public.v_l0_lac_bj_L1_cell_stage1 AS
SELECT t.*
FROM public.l0_lac_bj_detail_20251201_20251207_v1 t
WHERE
  t."运营商id" IN ('46000','46001','46011','46015','46020')
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$'
  AND lower(t.tech) IN ('4g','5g')
  AND t.cell_id IS NOT NULL
  AND btrim(t.cell_id::text) <> ''
  AND btrim(t.cell_id::text) ~ '^[0-9]+$'
  AND t.cell_id::bigint > 0
  AND t.cell_id::bigint <> 2147483647;
```

