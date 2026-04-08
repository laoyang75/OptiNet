-- Layer_3 Step36（可选附加）：疑似异常 BS ID 标注（bs_id=0/1/过短 hex 等）
--
-- 目的：
-- - 主链路（Step30~34）不强行修复上游解析/口径问题，只保证“可追溯 + 可标注 + 可排除”。
-- - 本脚本把疑似异常的 BS ID 统一标注出来，供后续复核与治理使用。
--
-- 输入：
-- - public."Y_codex_Layer3_Final_BS_Profile"（最终 BS 画像库；含 bs_id_hex）
--
-- 输出：
-- - public."Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked"
--
-- 判定口径（保守，宁可漏标不误杀）：
-- - bs_id=0：占位/非法（理论上不应进入最终交付，但可能在中间链路出现）
-- - bs_id=1：强疑似占位/解析异常（你明确要单独关注）
-- - 4G：bs_id_hex 长度 < 4（对应 bs_id < 4096，通常不符合常见 eNBID 量级）
-- - 5G：bs_id_hex 长度 < 5（5G 的 bs_id_hex 常见为 5~6 位；4 位样本极少，先标注）
--
-- 说明：
-- - 本表只做标注，不参与 Gate-0，不影响主链路产物。

/* ============================================================================
 * 会话级性能参数（轻量脚本）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked";

CREATE TABLE public."Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked" AS
WITH base AS (
  SELECT
    tech_norm,
    bs_id,
    bs_id_hex,
    lac_dec_final,
    wuli_fentong_bs_key,
    is_multi_operator_shared,
    shared_operator_cnt,
    shared_operator_list,
    operator_id_raw
  FROM public."Y_codex_Layer3_Final_BS_Profile"
),
agg AS (
  SELECT
    tech_norm,
    bs_id,
    max(bs_id_hex) AS bs_id_hex,
    lac_dec_final,
    wuli_fentong_bs_key,
    bool_or(is_multi_operator_shared) AS is_multi_operator_shared,
    max(shared_operator_cnt)::int AS shared_operator_cnt,
    max(shared_operator_list) AS shared_operator_list,
    count(DISTINCT operator_id_raw)::int AS operator_cnt,
    array_to_string(array_agg(DISTINCT operator_id_raw ORDER BY operator_id_raw), ',') AS operator_list
  FROM base
  GROUP BY 1,2,4,5
),
flagged AS (
  SELECT
    a.*,
    length(a.bs_id_hex) AS bs_id_hex_len,
    CASE
      WHEN a.bs_id = 0 THEN 'BS_ID_ZERO'
      WHEN a.bs_id = 1 THEN 'BS_ID_ONE'
      WHEN a.tech_norm = '4G' AND length(a.bs_id_hex) < 4 THEN 'BS_ID_HEX_LEN_LT4_4G'
      WHEN a.tech_norm = '5G' AND length(a.bs_id_hex) < 5 THEN 'BS_ID_HEX_LEN_LT5_5G'
      ELSE NULL
    END AS anomaly_reason
  FROM agg a
)
SELECT *
FROM flagged
WHERE anomaly_reason IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_step36_bs_id_anomaly_key
  ON public."Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked";
