# L1-LAC：北京 L0 源表筛选规则 v1

> 目标：把北京两张 L0 标准表按既有 L1-LAC 规则筛出合规子集。规则本身与 `Layer_1/Lac/Lac_Filter_Rules_v1.md` 完全一致，仅替换输入表与输出视图名。

## 1. 输入

- GPS 源 L0 表：`public."Y_codex_Layer0_Gps_base"`
- LAC 源 L0 表：`public."Y_codex_Layer0_Lac"`

两表均需包含标准字段：`"运营商id"`, `"原始lac"`, `tech`。

## 2. 输出视图

- GPS 源 L1-LAC 合规起点：`public.v_l0_gps_bj_L1_lac_stage1`
- LAC 源 L1-LAC 合规起点：`public.v_l0_lac_bj_L1_lac_stage1`

## 3. 可直接执行的 SQL

```sql
-- GPS 源
CREATE OR REPLACE VIEW public.v_l0_gps_bj_L1_lac_stage1 AS
SELECT t.*
FROM public."Y_codex_Layer0_Gps_base" t
WHERE
  t."运营商id" IN ('46000','46001','46011','46015','46020')
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$'
  AND upper(to_hex(btrim(t."原始lac")::bigint)) NOT IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')
  AND lower(t.tech) IN ('4g','5g');

-- LAC 源
CREATE OR REPLACE VIEW public.v_l0_lac_bj_L1_lac_stage1 AS
SELECT t.*
FROM public."Y_codex_Layer0_Lac" t
WHERE
  t."运营商id" IN ('46000','46001','46011','46015','46020')
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$'
  AND upper(to_hex(btrim(t."原始lac")::bigint)) NOT IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')
  AND lower(t.tech) IN ('4g','5g');
```
