-- Layer_4 Step44（可选）：标记 bs_id_final < 256 的异常记录（仅标记，不影响主链路）
--
-- 背景：正常 ENBID/gNB 通常对应 4 位 hex，因此十进制 bs_id 应满足 >=256（即 0x0100）。
-- 本步只做“落表标记”，用于后续复核/降权，不在 Layer_4 主链路中强制过滤。
--
-- 输入：
-- - public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"
--
-- 输出：
-- - public."Y_codex_Layer4_Step44_BsId_Lt_256_Detail"
-- - public."Y_codex_Layer4_Step44_BsId_Lt_256_Summary"

SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step44_BsId_Lt_256_Detail";
CREATE TABLE public."Y_codex_Layer4_Step44_BsId_Lt_256_Detail" AS
SELECT
  seq_id,
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  bs_id_final,
  lac_dec_final,
  wuli_fentong_bs_key,
  bs_shard_key,
  ts_std,
  lon_before_fix,
  lat_before_fix,
  lon_final,
  lat_final,
  gps_source,
  'bs_id_final BETWEEN 1 AND 255 (expected >=256 for 4-hex ENBID/gNB)'::text AS anomaly_reason
FROM public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"
WHERE bs_id_final BETWEEN 1 AND 255;

DROP TABLE IF EXISTS public."Y_codex_Layer4_Step44_BsId_Lt_256_Summary";
CREATE TABLE public."Y_codex_Layer4_Step44_BsId_Lt_256_Summary" AS
SELECT
  operator_id_raw,
  tech_norm,
  count(*)::bigint AS row_cnt,
  count(distinct bs_id_final)::bigint AS distinct_bs_cnt,
  min(bs_id_final)::bigint AS bs_id_min,
  max(bs_id_final)::bigint AS bs_id_max
FROM public."Y_codex_Layer4_Step44_BsId_Lt_256_Detail"
GROUP BY 1,2
ORDER BY row_cnt DESC;

