-- 补丁_20251219_Layer2_Step06_多LAC按信号有效上报量收敛.sql
--
-- 目标：
-- - 解决“同一 cell_id_dec 出现多个 lac_dec（多LAC）”的口径问题：
--   对多LAC小区，收敛到一个“主 LAC”，避免同一小区在 Layer_2/3 被拆成多个桶。
--
-- 设计（用户确认）：
-- 1) 过滤无效信息：sig_rsrp 的无效值（-110、-1、以及非负数>=0）不计入有效信号
-- 2) 7天上报量排序：优先选择 good_sig_cnt 最大的 LAC
-- 3) tie-break：用 LAC 库（Step04）的 valid_gps_count 作为“区域置信度”更大者优先
--
-- 影响面（本库实测）：
-- - 多LAC小区：79 个；涉及 Step06 约 15k 行
-- - 实际会被改写 LAC 的明细行：约 482 行（很小）
--
-- 执行建议：
-- - 用 psql -f 执行整文件（避免某些控制台多语句切分问题）
-- - 默认包含 Step31 的局部同步（只更新受影响的 482 行），不做 Step30 全量重跑

SET statement_timeout = 0;

BEGIN;

-- 0) 给 LAC 库增加“置信度”字段（不改变既有口径，仅补充可解释字段）
ALTER TABLE public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  ADD COLUMN IF NOT EXISTS lac_confidence_score bigint;
ALTER TABLE public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  ADD COLUMN IF NOT EXISTS lac_confidence_rank int;

WITH ranked AS (
  SELECT
    operator_id_raw,
    tech_norm,
    lac_dec,
    coalesce(valid_gps_count, 0)::bigint AS lac_confidence_score,
    dense_rank() OVER (
      PARTITION BY operator_id_raw, tech_norm
      ORDER BY coalesce(valid_gps_count, 0) DESC, coalesce(record_count, 0) DESC, lac_dec ASC
    )::int AS lac_confidence_rank
  FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  WHERE is_trusted_lac
)
UPDATE public."Y_codex_Layer2_Step04_Master_Lac_Lib" t
SET
  lac_confidence_score = r.lac_confidence_score,
  lac_confidence_rank = r.lac_confidence_rank
FROM ranked r
WHERE t.operator_id_raw=r.operator_id_raw
  AND t.tech_norm=r.tech_norm
  AND t.lac_dec=r.lac_dec;

-- 1) 生成“多LAC收敛”决策表（可先看决策再决定是否继续 UPDATE）
CREATE TABLE IF NOT EXISTS public."Y_patch_L2_Step06_MultiLac_Candidates_20251219" (
  operator_id_raw text NOT NULL,
  tech_norm text NOT NULL,
  cell_id_dec bigint NOT NULL,
  lac_dec bigint NOT NULL,
  row_cnt bigint NOT NULL,
  good_sig_cnt bigint NOT NULL,
  bad_sig_cnt bigint NOT NULL,
  p50_sig_rsrp double precision,
  lac_confidence_score bigint,
  lac_confidence_rank int,
  rn int NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public."Y_patch_L2_Step06_MultiLac_BestLac_20251219" (
  operator_id_raw text NOT NULL,
  tech_norm text NOT NULL,
  cell_id_dec bigint NOT NULL,
  best_lac_dec bigint NOT NULL,
  best_row_cnt bigint NOT NULL,
  best_good_sig_cnt bigint NOT NULL,
  best_bad_sig_cnt bigint NOT NULL,
  best_p50_sig_rsrp double precision,
  best_lac_confidence_score bigint,
  best_lac_confidence_rank int,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (operator_id_raw, tech_norm, cell_id_dec)
);

TRUNCATE public."Y_patch_L2_Step06_MultiLac_Candidates_20251219";
TRUNCATE public."Y_patch_L2_Step06_MultiLac_BestLac_20251219";

WITH
anomaly_cells AS (
  SELECT operator_id_raw, tech_norm, cell_id_dec
  FROM public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
),
cell_lac_sig AS (
  SELECT
    t.operator_id_raw,
    t.tech_norm,
    t.cell_id_dec,
    t.lac_dec_final AS lac_dec,
    count(*)::bigint AS row_cnt,
    count(*) FILTER (WHERE t.sig_rsrp IS NOT NULL AND t.sig_rsrp NOT IN (-110, -1) AND t.sig_rsrp < 0)::bigint AS good_sig_cnt,
    count(*) FILTER (WHERE t.sig_rsrp IS NOT NULL AND (t.sig_rsrp IN (-110, -1) OR t.sig_rsrp >= 0))::bigint AS bad_sig_cnt,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY t.sig_rsrp) FILTER (WHERE t.sig_rsrp IS NOT NULL) AS p50_sig_rsrp
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
  JOIN anomaly_cells a
    ON a.operator_id_raw=t.operator_id_raw
   AND a.tech_norm=t.tech_norm
   AND a.cell_id_dec=t.cell_id_dec
  GROUP BY 1,2,3,4
),
ranked AS (
  SELECT
    s.*,
    l.lac_confidence_score,
    l.lac_confidence_rank,
    row_number() OVER (
      PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec
      ORDER BY
        s.good_sig_cnt DESC,
        coalesce(l.lac_confidence_score, 0) DESC,
        s.row_cnt DESC,
        s.lac_dec ASC
    )::int AS rn
  FROM cell_lac_sig s
  LEFT JOIN public."Y_codex_Layer2_Step04_Master_Lac_Lib" l
    ON l.operator_id_raw=s.operator_id_raw
   AND l.tech_norm=s.tech_norm
   AND l.lac_dec=s.lac_dec
   AND l.is_trusted_lac
)
INSERT INTO public."Y_patch_L2_Step06_MultiLac_Candidates_20251219" (
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  lac_dec,
  row_cnt,
  good_sig_cnt,
  bad_sig_cnt,
  p50_sig_rsrp,
  lac_confidence_score,
  lac_confidence_rank,
  rn
)
SELECT
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  lac_dec,
  row_cnt,
  good_sig_cnt,
  bad_sig_cnt,
  p50_sig_rsrp,
  lac_confidence_score,
  lac_confidence_rank,
  rn
FROM ranked;

INSERT INTO public."Y_patch_L2_Step06_MultiLac_BestLac_20251219" (
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  best_lac_dec,
  best_row_cnt,
  best_good_sig_cnt,
  best_bad_sig_cnt,
  best_p50_sig_rsrp,
  best_lac_confidence_score,
  best_lac_confidence_rank
)
SELECT
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  lac_dec AS best_lac_dec,
  row_cnt AS best_row_cnt,
  good_sig_cnt AS best_good_sig_cnt,
  bad_sig_cnt AS best_bad_sig_cnt,
  p50_sig_rsrp AS best_p50_sig_rsrp,
  lac_confidence_score AS best_lac_confidence_score,
  lac_confidence_rank AS best_lac_confidence_rank
FROM public."Y_patch_L2_Step06_MultiLac_Candidates_20251219"
WHERE rn=1
ON CONFLICT (operator_id_raw, tech_norm, cell_id_dec) DO NOTHING;

-- 1.1 决策预览（Top10）
SELECT
  b.operator_id_raw,
  b.tech_norm,
  b.cell_id_dec,
  b.best_lac_dec,
  b.best_row_cnt,
  b.best_good_sig_cnt,
  b.best_bad_sig_cnt,
  b.best_p50_sig_rsrp,
  b.best_lac_confidence_score,
  b.best_lac_confidence_rank
FROM public."Y_patch_L2_Step06_MultiLac_BestLac_20251219" b
ORDER BY b.best_good_sig_cnt DESC, b.best_row_cnt DESC
LIMIT 10;

-- 2) 生成“本次会被改写的明细行清单”（只会很少）
DROP TABLE IF EXISTS tmp_step06_to_change;
CREATE TEMP TABLE tmp_step06_to_change AS
SELECT
  t.seq_id,
  t."记录id" AS src_record_id,
  t.operator_id_raw,
  t.tech_norm,
  t.bs_id,
  t.cell_id_dec,
  t.lac_dec_final AS old_lac_dec_final,
  b.best_lac_dec AS new_lac_dec_final
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
JOIN public."Y_patch_L2_Step06_MultiLac_BestLac_20251219" b
  ON b.operator_id_raw=t.operator_id_raw
 AND b.tech_norm=t.tech_norm
 AND b.cell_id_dec=t.cell_id_dec
WHERE t.lac_dec_final IS DISTINCT FROM b.best_lac_dec;

SELECT count(*)::bigint AS will_change_row_cnt FROM tmp_step06_to_change;

-- 3) 备份（只备份“即将被改写”的行）
CREATE TABLE IF NOT EXISTS public."Y_patch_backup_L2_Step06_MultiLac_20251219" AS
SELECT *
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
WHERE false;

INSERT INTO public."Y_patch_backup_L2_Step06_MultiLac_20251219"
SELECT t.*
FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
JOIN tmp_step06_to_change c
  ON c.seq_id=t.seq_id
WHERE NOT EXISTS (
  SELECT 1
  FROM public."Y_patch_backup_L2_Step06_MultiLac_20251219" b
  WHERE b.seq_id=t.seq_id
);

-- 4) 执行改写：把多LAC小区收敛到 best_lac_dec
UPDATE public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
SET
  -- 保留原始输出字段（若之前未写入 raw，则补一份）
  lac_dec_raw = COALESCE(t.lac_dec_raw, t.lac_dec),
  lac_hex_raw = COALESCE(t.lac_hex_raw, t.lac_hex),

  -- 统一输出到主 LAC
  lac_dec_final = c.new_lac_dec_final,
  lac_dec = c.new_lac_dec_final,
  lac_hex = upper(to_hex(c.new_lac_dec_final)),

  -- 标记：本次为多LAC收敛导致的改写
  lac_enrich_status = 'MULTI_LAC_OVERRIDE_BY_CONFIDENCE',
  is_lac_changed_by_mapping = true,
  is_final_lac_trusted = true,
  lac_output_normalized = true
FROM tmp_step06_to_change c
WHERE t.seq_id=c.seq_id;

-- 4.1 校验：改写后，异常 cell 是否仍存在多LAC（应为 0）
WITH after_cnt AS (
  SELECT
    t.operator_id_raw,
    t.tech_norm,
    t.cell_id_dec,
    count(DISTINCT t.lac_dec_final)::int AS lac_distinct_after
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
  JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
    ON a.operator_id_raw=t.operator_id_raw AND a.tech_norm=t.tech_norm AND a.cell_id_dec=t.cell_id_dec
  GROUP BY 1,2,3
)
SELECT
  count(*) FILTER (WHERE lac_distinct_after > 1)::int AS still_multi_lac_cell_cnt,
  count(*)::int AS total_anomaly_cell_cnt
FROM after_cnt;

COMMIT;

-- 5) （可选但建议）同步 Layer_3 Step31（只更新受影响行；不重跑 CTAS）
-- 注意：若你尚未执行 Layer_3，则可跳过本段。
BEGIN;

WITH
params AS (
  SELECT 1500.0::double precision AS drift_if_dist_m_gt
),
china AS (
  SELECT 73.0::double precision AS lon_min, 135.0::double precision AS lon_max,
         3.0::double precision AS lat_min, 54.0::double precision AS lat_max
)
UPDATE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s
SET
  lac_dec_final = c.new_lac_dec_final,
  wuli_fentong_bs_key = (s.tech_norm || '|' || s.bs_id::text || '|' || c.new_lac_dec_final::text),

  -- 重新挂载基站属性（基于新的 wuli_fentong_bs_key）
  gps_valid_level = bs.gps_valid_level,
  is_collision_suspect = bs.is_collision_suspect,
  is_multi_operator_shared = bs.is_multi_operator_shared,
  shared_operator_list = bs.shared_operator_list,
  shared_operator_cnt = bs.shared_operator_cnt,
  is_from_risk_bs = CASE WHEN bs.gps_valid_level = 'Risk' THEN 1 ELSE 0 END::int,

  gps_dist_to_bs_m = CASE
    WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN NULL::double precision
    WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN NULL::double precision
    WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
    ELSE
      6371000.0 * 2.0 * asin(
        sqrt(
          power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
          + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
            * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
        )
      )
  END,

  gps_status = CASE
    WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
    WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN 'Missing'
    WHEN (
      CASE
        WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
        ELSE
          6371000.0 * 2.0 * asin(
            sqrt(
              power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
              + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
            )
          )
      END
    ) > p.drift_if_dist_m_gt THEN 'Drift'
    ELSE 'Verified'
  END,

  gps_source = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN 'Original_Verified'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level = 'Usable'
    THEN 'Augmented_from_BS'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level = 'Risk'
    THEN 'Augmented_from_Risk_BS'
    ELSE 'Not_Filled'
  END,

  gps_status_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN 'Verified'
    WHEN bs.bs_center_lon IS NOT NULL
     AND bs.bs_center_lat IS NOT NULL
     AND bs.gps_valid_level IN ('Usable','Risk')
    THEN 'Verified'
    ELSE 'Missing'
  END,

  lon_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN s.lon_raw
    WHEN bs.bs_center_lon IS NOT NULL AND bs.bs_center_lat IS NOT NULL AND bs.gps_valid_level IN ('Usable','Risk') THEN bs.bs_center_lon
    ELSE s.lon_raw
  END,
  lat_final = CASE
    WHEN (
      CASE
        WHEN s.lon_raw IS NULL OR s.lat_raw IS NULL THEN 'Missing'
        WHEN NOT (s.lon_raw::double precision BETWEEN cbox.lon_min AND cbox.lon_max AND s.lat_raw::double precision BETWEEN cbox.lat_min AND cbox.lat_max) THEN 'Missing'
        WHEN (
          CASE
            WHEN bs.bs_center_lon IS NULL OR bs.bs_center_lat IS NULL THEN NULL::double precision
            ELSE
              6371000.0 * 2.0 * asin(
                sqrt(
                  power(sin(radians(s.lat_raw - bs.bs_center_lat) / 2.0), 2)
                  + cos(radians(bs.bs_center_lat)) * cos(radians(s.lat_raw))
                    * power(sin(radians(s.lon_raw - bs.bs_center_lon) / 2.0), 2)
                )
              )
          END
        ) > p.drift_if_dist_m_gt THEN 'Drift'
        ELSE 'Verified'
      END
    ) = 'Verified' THEN s.lat_raw
    WHEN bs.bs_center_lon IS NOT NULL AND bs.bs_center_lat IS NOT NULL AND bs.gps_valid_level IN ('Usable','Risk') THEN bs.bs_center_lat
    ELSE s.lat_raw
  END
FROM tmp_step06_to_change c
CROSS JOIN params p
CROSS JOIN china cbox
LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" bs
  ON bs.tech_norm=s.tech_norm
 AND bs.bs_id=s.bs_id
 AND bs.wuli_fentong_bs_key=(s.tech_norm || '|' || s.bs_id::text || '|' || c.new_lac_dec_final::text)
WHERE s.src_seq_id=c.seq_id;

COMMIT;

-- 6) 执行后建议（很快）
-- 6.1 检查多LAC是否已收敛（应为 0）
-- select count(*) from (
--   select operator_id_raw, tech_norm, cell_id_dec, count(distinct lac_dec_final) as cnt
--   from public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
--   where (operator_id_raw, tech_norm, cell_id_dec) in (select operator_id_raw, tech_norm, cell_id_dec from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac")
--   group by 1,2,3
-- ) t where cnt > 1;
--
-- 6.2 如需刷新 Step32（快）
-- psql -f lac_enbid_project/Layer_3/sql/32_step32_compare.sql
