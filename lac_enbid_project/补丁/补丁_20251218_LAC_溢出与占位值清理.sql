-- 补丁：LAC 溢出/占位值清理（不重跑流水线版）
-- 适用：当前数据库已跑完 Layer_2（Step03~Step06）但发现 LAC 中混入明显异常值：
--   - hex: FFFF / FFFE / FFFFFE / FFFFFF / 7FFFFFFF
--   - dec: 65535 / 65534 / 16777214 / 16777215 / 2147483647
--
-- 目的：
-- 1) 从“可信LAC白名单”中剔除这些值，避免被误当作可信
-- 2) 清理已落地的 Step05/Step06 结果中与这些 LAC 相关的数据
--
-- 注意：
-- - 这不是重跑；只是对“现网已生成结果”做最小修正。
-- - 如果你后续会重跑 Step02~Step06（按新规则），本补丁可不执行。
-- - 建议用 psql -f 执行整文件，并保留输出作为审计记录。

SET statement_timeout = 0;

WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES
    (65534),(65535),(16777214),(16777215),(2147483647)
  ) AS v(x)
)
SELECT
  (SELECT count(*) FROM public."Y_codex_Layer2_Step03_Lac_Stats_DB" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step03_bad_keys,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step04_bad_keys,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step05_bad_keys,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" s JOIN bad_lac b ON b.lac_dec=s.lac_dec_final) AS step06_bad_rows;

-- 1) Step04：可信 LAC 白名单剔除
WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES (65534),(65535),(16777214),(16777215),(2147483647)) AS v(x)
)
DELETE FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib" t
USING bad_lac b
WHERE t.lac_dec = b.lac_dec;

-- 2) Step05：映射底座剔除（避免异常 LAC 参与 cell_id 映射）
WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES (65534),(65535),(16777214),(16777215),(2147483647)) AS v(x)
)
DELETE FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" t
USING bad_lac b
WHERE t.lac_dec = b.lac_dec;

-- 3) Step06：反哺后明细库剔除（最终 LAC 不允许为异常值）
WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES (65534),(65535),(16777214),(16777215),(2147483647)) AS v(x)
)
DELETE FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
USING bad_lac b
WHERE t.lac_dec_final = b.lac_dec;

-- 4) Step03：汇总库剔除（用于报表/审计一致性；不影响已生成 Step04/05/06 的结果）
WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES (65534),(65535),(16777214),(16777215),(2147483647)) AS v(x)
)
DELETE FROM public."Y_codex_Layer2_Step03_Lac_Stats_DB" t
USING bad_lac b
WHERE t.lac_dec = b.lac_dec;

ANALYZE public."Y_codex_Layer2_Step03_Lac_Stats_DB";
ANALYZE public."Y_codex_Layer2_Step04_Master_Lac_Lib";
ANALYZE public."Y_codex_Layer2_Step05_CellId_Stats_DB";
ANALYZE public."Y_codex_Layer2_Step06_L0_Lac_Filtered";

WITH bad_lac AS (
  SELECT x::bigint AS lac_dec
  FROM (VALUES
    (65534),(65535),(16777214),(16777215),(2147483647)
  ) AS v(x)
)
SELECT
  (SELECT count(*) FROM public."Y_codex_Layer2_Step03_Lac_Stats_DB" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step03_bad_keys_after,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step04_bad_keys_after,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s JOIN bad_lac b ON b.lac_dec=s.lac_dec) AS step05_bad_keys_after,
  (SELECT count(*) FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" s JOIN bad_lac b ON b.lac_dec=s.lac_dec_final) AS step06_bad_rows_after;

