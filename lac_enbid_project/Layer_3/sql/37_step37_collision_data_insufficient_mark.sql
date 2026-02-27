-- Layer_3 Step37（可选附加）：数据不足导致的碰撞波动桶标注（7 天内不强结论）
--
-- 背景：
-- - Step30 的 `is_collision_suspect=1` 依赖桶内“可信 GPS 点”聚合出来的离散度指标。
-- - 当桶内用于建中心的可信点数过少（低样本）时，p90/max 容易被单点放大，导致“看起来很异常”的桶。
-- - 这类异常在 7 天窗口内不建议强行给出“混桶/碰撞”结论，应先标注为“数据不足”，等待更长窗口复核（例如 28 天）。
--
-- 输入：
-- - public."Y_codex_Layer3_Step30_Master_BS_Library"
--
-- 输出：
-- - public."Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS"
--
-- 默认口径（可按需调整）：
-- - 仅关注 `is_collision_suspect=1`
-- - 且 `gps_valid_point_cnt < 20`（用于建中心的可信 GPS 点数过少）

/* ============================================================================
 * 会话级性能参数（轻量脚本）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '256MB';

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS";

CREATE TABLE public."Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS" AS
WITH params AS (
  SELECT 20::int AS low_point_cnt_lt
),
base AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    shared_operator_cnt,
    shared_operator_list,
    is_multi_operator_shared,
    gps_valid_level,
    gps_valid_cell_cnt,
    gps_valid_point_cnt,
    active_days,
    gps_p50_dist_m,
    gps_p90_dist_m,
    gps_max_dist_m,
    is_collision_suspect,
    collision_reason
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library"
)
SELECT
  b.*,
  CASE
    WHEN b.gps_valid_point_cnt IS NULL THEN 'NULL'
    WHEN b.gps_valid_point_cnt < 5 THEN '<5'
    WHEN b.gps_valid_point_cnt < 10 THEN '5-9'
    WHEN b.gps_valid_point_cnt < 20 THEN '10-19'
    ELSE '>=20'
  END AS low_point_bucket,
  'DATA_INSUFFICIENT_7D'::text AS triage_reason,
  'WAIT_LONGER_WINDOW_RECHECK'::text AS triage_action
FROM base b
CROSS JOIN params p
WHERE
  b.is_collision_suspect = 1
  AND b.gps_valid_point_cnt < p.low_point_cnt_lt;

CREATE INDEX IF NOT EXISTS idx_step37_collision_low_sample_key
  ON public."Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS"(wuli_fentong_bs_key);

ANALYZE public."Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS";

