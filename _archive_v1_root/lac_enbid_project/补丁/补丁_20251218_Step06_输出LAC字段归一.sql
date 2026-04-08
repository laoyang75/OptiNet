-- 补丁：Step06 输出 LAC 字段归一（不重跑流水线版）
-- 背景：
-- - public."Y_codex_Layer2_Step06_L0_Lac_Filtered" 的设计里同时存在：
--   - 原始透传字段：lac_dec / lac_hex（来自 Step00_Lac_Std，可能为 NULL/0/FFFF/7FFFFFFF 等异常）
--   - 反哺结果字段：lac_dec_final（强制命中 Step04 白名单，才是“最终可信 LAC”）
-- - 如果你直接看 lac_hex/lac_dec，会误以为“补丁没生效”；实际上 lac_dec_final 已纠偏成功。
--
-- 目的：
-- - 对 Step06 明细表做一次“输出口径归一”：让 lac_dec/lac_hex 代表最终可信值（=lac_dec_final）。
-- - 同时保留原始值到 lac_dec_raw/lac_hex_raw（仅对被修正的行写入）。
--
-- 注意：
-- - 这是现网补丁，不需要重跑 Step00~Step06。
-- - 只会更新少量异常行（lac_dec/lac_hex 为 NULL/0/溢出占位值）。
-- - 建议用 psql -f 执行整文件，并保留输出作为审计记录。

SET statement_timeout = 0;

ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_dec_raw bigint;

ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_hex_raw text;

ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_output_normalized boolean;

WITH bad_hex AS (
  SELECT unnest(ARRAY['FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF']) AS hx
)
SELECT
  count(*) AS total_rows,
  count(*) FILTER (WHERE lac_dec IS NULL) AS lac_dec_null_rows,
  count(*) FILTER (WHERE lac_dec = 0) AS lac_dec_zero_rows,
  count(*) FILTER (WHERE lac_hex IS NULL OR btrim(lac_hex) = '') AS lac_hex_null_rows,
  count(*) FILTER (WHERE upper(lac_hex) IN (SELECT hx FROM bad_hex)) AS lac_hex_sentinel_rows,
  count(*) FILTER (WHERE lac_dec_final IN (65534,65535,16777214,16777215,2147483647)) AS lac_dec_final_sentinel_rows
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered";

UPDATE public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
SET
  lac_dec_raw = t.lac_dec,
  lac_hex_raw = t.lac_hex,
  lac_dec = t.lac_dec_final,
  lac_hex = upper(to_hex(t.lac_dec_final)),
  lac_output_normalized = true
WHERE
  -- 仅修正“原始透传字段明显异常”的行
  (
    t.lac_dec IS NULL
    OR t.lac_dec <= 0
    OR t.lac_dec IN (65534,65535,16777214,16777215,2147483647)
    OR t.lac_hex IS NULL
    OR btrim(t.lac_hex) = ''
    OR upper(t.lac_hex) IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')
  )
  AND t.lac_dec_final IS NOT NULL
  AND coalesce(t.lac_output_normalized, false) = false;

ANALYZE public."Y_codex_Layer2_Step06_L0_Lac_Filtered";

WITH bad_hex AS (
  SELECT unnest(ARRAY['FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF']) AS hx
)
SELECT
  count(*) AS total_rows,
  count(*) FILTER (WHERE lac_dec IS NULL) AS lac_dec_null_rows_after,
  count(*) FILTER (WHERE lac_dec = 0) AS lac_dec_zero_rows_after,
  count(*) FILTER (WHERE lac_hex IS NULL OR btrim(lac_hex) = '') AS lac_hex_null_rows_after,
  count(*) FILTER (WHERE upper(lac_hex) IN (SELECT hx FROM bad_hex)) AS lac_hex_sentinel_rows_after,
  count(*) FILTER (WHERE lac_output_normalized) AS normalized_rows_after
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered";

