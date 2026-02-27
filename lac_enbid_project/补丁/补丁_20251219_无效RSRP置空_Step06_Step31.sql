-- 补丁_20251219_无效RSRP置空_Step06_Step31.sql
--
-- 目标（用户确认）：
-- - sig_rsrp 的无效值（-110、-1、以及非负数>=0）不参与任何统计/补齐；直接置 NULL
-- - 后续由 Step33（cell/bs 聚合）或未来“补数”流程补齐
--
-- 注意：
-- - 这是“就地修正现有落表”的补丁；不替代主流程 SQL（主流程已在 Step06/Step31/Step33 内做了同等处理）。
-- - 全库 sig_rsrp=-110 行数不大，但 UPDATE 仍需扫描表；建议在低峰执行。

SET statement_timeout = 0;

BEGIN;

-- Layer_2 Step06 输出（下游 Step31/33 的输入）
UPDATE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
SET sig_rsrp = NULL
WHERE sig_rsrp IN (-110, -1) OR sig_rsrp >= 0;

-- Layer_3 Step31 输出（如已存在旧结果且仍含 -110）
UPDATE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
SET sig_rsrp = NULL
WHERE sig_rsrp IN (-110, -1) OR sig_rsrp >= 0;

COMMIT;

ANALYZE public."Y_codex_Layer2_Step06_L0_Lac_Filtered";
ANALYZE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- 执行后建议：
-- - 刷新 Step33/34（如你需要让 signal_fill_source / missing_before 体现这次置空带来的变化）
--   psql -f lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql
--   psql -f lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql
