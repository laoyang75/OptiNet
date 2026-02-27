-- Layer_2 Step6：用可信 cell 映射反哺 L0_Lac（补齐/纠偏 LAC）+ 对比报表
-- 输入：
--   public."Y_codex_Layer2_Step00_Lac_Std"
--   public."Y_codex_Layer2_Step05_CellId_Stats_DB"
--   public."Y_codex_Layer2_Step00_Gps_Std" / public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
-- 输出：
--   public."Y_codex_Layer2_Step06_L0_Lac_Filtered" (TABLE：反哺后的可信明细库)
--   public."Y_codex_Layer2_Step06_GpsVsLac_Compare"

-- 重要：PG15 + Step00 是 VIEW（巨大输入）时，直接在 VIEW 上 join 容易触发 merge join/sort/hash spill，
--      造成 TB 级 temp_files（你这次看到的 temp_bytes=6TB 就是典型症状）。
--      本脚本采用“两段式”：
--        1) 把小表（Step04/Step05）预处理成小 TEMP 表 + 索引
--        2) 把 Step00_Lac_Std 在必要范围内先物化成 TEMP 表，再做 hash join 回填，避免大排序
--
-- 建议用 psql -f 执行整文件（某些控制台会按 ';' 拆分导致 DO 块失败）。

/* ============================================================================
 * 会话级性能参数（PG15 / 264GB / 40核 / SSD）
 * 参考：lac_enbid_project/服务器配置与SQL调优建议.md
 * ==========================================================================*/
SET statement_timeout = 0;
SET work_mem = '2GB';
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;
SET jit = off;

-- Step06 特殊覆盖：避免 merge join 大排序 + 避免并行 worker->leader 队列拥塞
SET enable_mergejoin = off;
SET enable_nestloop = off;
SET max_parallel_workers_per_gather = 0;

-- 重跑注意：Step06 明细对象固定为 TABLE；但历史遗留版本可能是 VIEW，需要按对象类型先删除再创建
DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer2_Step06_L0_Lac_Filtered"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step06_L0_Lac_Filtered'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step06_L0_Lac_Filtered"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"';
    END IF;
  END IF;

  -- 清理旧命名（历史遗留）
  IF to_regclass('public.d_step6_l0_lac_filtered') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'd_step6_l0_lac_filtered'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public.d_step6_l0_lac_filtered';
    ELSE
      EXECUTE 'DROP TABLE public.d_step6_l0_lac_filtered';
    END IF;
  END IF;
END $$;

-- ============================================================
-- Stage A：把小表预处理成“小而稳”的 TEMP 表（可索引、可 ANALYZE）
-- ============================================================

DROP TABLE IF EXISTS tmp_step06_trusted_lac;
CREATE TEMP TABLE tmp_step06_trusted_lac AS
SELECT DISTINCT operator_id_raw, tech_norm, lac_dec
FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
WHERE is_trusted_lac;

CREATE UNIQUE INDEX tmp_step06_trusted_lac_pk
  ON tmp_step06_trusted_lac (operator_id_raw, tech_norm, lac_dec);
ANALYZE tmp_step06_trusted_lac;


DROP TABLE IF EXISTS tmp_step06_map_choice_cnt;
CREATE TEMP TABLE tmp_step06_map_choice_cnt AS
SELECT operator_id_raw, tech_norm, cell_id_dec, count(*)::bigint AS lac_choice_cnt
FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
GROUP BY 1,2,3;

CREATE UNIQUE INDEX tmp_step06_map_choice_cnt_pk
  ON tmp_step06_map_choice_cnt (operator_id_raw, tech_norm, cell_id_dec);
ANALYZE tmp_step06_map_choice_cnt;


DROP TABLE IF EXISTS tmp_step06_map_best;
CREATE TEMP TABLE tmp_step06_map_best AS
SELECT DISTINCT ON (s.operator_id_raw, s.tech_norm, s.cell_id_dec)
  s.operator_id_raw,
  s.tech_norm,
  s.cell_id_dec,
  c.lac_choice_cnt,
  CASE WHEN c.lac_choice_cnt = 1 THEN s.lac_dec END AS lac_dec_from_map,
  s.record_count AS map_record_count,
  s.valid_gps_count AS map_valid_gps_count,
  s.distinct_device_count AS map_distinct_device_count,
  s.active_days AS map_active_days
FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
JOIN tmp_step06_map_choice_cnt c
  ON s.operator_id_raw=c.operator_id_raw
 AND s.tech_norm=c.tech_norm
 AND s.cell_id_dec=c.cell_id_dec
ORDER BY
  s.operator_id_raw, s.tech_norm, s.cell_id_dec,
  s.record_count DESC, s.valid_gps_count DESC, s.distinct_device_count DESC, s.active_days DESC, s.lac_dec ASC;

CREATE INDEX tmp_step06_map_best_join
  ON tmp_step06_map_best (operator_id_raw, tech_norm, cell_id_dec);
ANALYZE tmp_step06_map_best;


-- ============================================================
-- Stage B：物化 Step00（巨大 VIEW）到“必要范围”的 TEMP 表
-- ============================================================

DROP TABLE IF EXISTS tmp_step06_lac_scope;
CREATE TEMP TABLE tmp_step06_lac_scope AS
SELECT
  seq_id,
  "记录id",
  cell_ts,
  cell_ts_std,
  tech,
  "运营商id",
  "原始lac",
  cell_id,
  lac_dec,
  lac_hex,
  cell_id_dec,
  cell_id_hex,
  bs_id,
  sector_id,
  gps_raw,
  lon_raw,
  lat_raw,
  gps_final,
  lon,
  lat,
  gps_info_type,
  "数据来源",
  "北京来源",
  did,
  ts,
  ts_std,
  ip,
  sdk_ver,
  brand,
  model,
  oaid,
  parsed_from,
  match_status,
  is_connected,
  operator_id_raw,
  device_id,
  tech_norm,
  operator_group_hint,
  report_date,
  lac_len,
  cell_len,
  has_cellid,
  has_lac,
  has_gps,
  sig_rsrp,
  sig_rsrq,
  sig_sinr,
  sig_rssi,
  sig_dbm,
  sig_asu_level,
  sig_level,
  sig_ss
FROM public."Y_codex_Layer2_Step00_Lac_Std"
WHERE tech_norm IN ('4G','5G')
  AND operator_id_raw IN ('46000','46001','46011','46015','46020')
  AND cell_id_dec IS NOT NULL;

-- 注意：不默认给 tmp_step06_lac_scope 建索引（行数可能很大，建索引本身也会触发大排序/落盘）。
-- 若你确认机器内存/磁盘充足，且后续需要频繁按 key 查，可再手工补：CREATE INDEX ON tmp_step06_lac_scope(operator_id_raw, tech_norm, cell_id_dec);
ANALYZE tmp_step06_lac_scope;

-- ============================================================
-- Stage B.1：多 LAC 小区“收敛到主 LAC”（可选但建议）
-- 目的：
-- - 处理“同一 cell_id_dec 在 7 天内出现多个 lac_dec”的口径问题
-- 策略（用户确认）：
-- - 过滤无效信号：sig_rsrp = -110 视为无效/占位值（典型表现：全是 -110）
-- - 优先选择 good_sig_cnt = count(sig_rsrp <> -110) 最大的 LAC
-- - tie-break：用 Step04 的 lac_confidence_score（默认=valid_gps_count）更大者优先
-- ============================================================

DROP TABLE IF EXISTS tmp_step06_multilac_best;
CREATE TEMP TABLE tmp_step06_multilac_best AS
WITH
multilac_cells AS (
  SELECT operator_id_raw, tech_norm, cell_id_dec
  FROM tmp_step06_map_choice_cnt
  WHERE lac_choice_cnt > 1
),
cand AS (
  SELECT
    l.operator_id_raw,
    l.tech_norm,
    l.cell_id_dec,
    l.lac_dec,
    count(*)::bigint AS row_cnt,
    count(*) FILTER (WHERE l.sig_rsrp IS NOT NULL AND l.sig_rsrp NOT IN (-110, -1) AND l.sig_rsrp < 0)::bigint AS good_sig_cnt
  FROM tmp_step06_lac_scope l
  JOIN multilac_cells mc
    ON mc.operator_id_raw=l.operator_id_raw
   AND mc.tech_norm=l.tech_norm
   AND mc.cell_id_dec=l.cell_id_dec
  JOIN tmp_step06_trusted_lac tl
    ON tl.operator_id_raw=l.operator_id_raw
   AND tl.tech_norm=l.tech_norm
   AND tl.lac_dec=l.lac_dec
  WHERE l.lac_dec IS NOT NULL
  GROUP BY 1,2,3,4
),
ranked AS (
  SELECT
    c.*,
    coalesce(l4.lac_confidence_score, coalesce(l4.valid_gps_count,0)::bigint) AS lac_confidence_score,
    row_number() OVER (
      PARTITION BY c.operator_id_raw, c.tech_norm, c.cell_id_dec
      ORDER BY
        c.good_sig_cnt DESC,
        coalesce(l4.lac_confidence_score, coalesce(l4.valid_gps_count,0)::bigint) DESC,
        c.row_cnt DESC,
        c.lac_dec ASC
    )::int AS rn
  FROM cand c
  LEFT JOIN public."Y_codex_Layer2_Step04_Master_Lac_Lib" l4
    ON l4.operator_id_raw=c.operator_id_raw
   AND l4.tech_norm=c.tech_norm
   AND l4.lac_dec=c.lac_dec
   AND l4.is_trusted_lac
)
SELECT
  operator_id_raw,
  tech_norm,
  cell_id_dec,
  lac_dec AS best_lac_dec,
  row_cnt AS best_row_cnt,
  good_sig_cnt AS best_good_sig_cnt,
  lac_confidence_score AS best_lac_confidence_score
FROM ranked
WHERE rn=1;

CREATE UNIQUE INDEX tmp_step06_multilac_best_pk
  ON tmp_step06_multilac_best (operator_id_raw, tech_norm, cell_id_dec);
ANALYZE tmp_step06_multilac_best;


-- ============================================================
-- Stage C：生成 Step06 反哺后明细表（TABLE）
-- ============================================================

CREATE TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered" AS
WITH joined AS (
  SELECT
    l.*,
    mb.lac_choice_cnt,
    mb.lac_dec_from_map,
    mb.map_record_count,
    mb.map_valid_gps_count,
    mb.map_distinct_device_count,
    mb.map_active_days,
    (t_orig.lac_dec IS NOT NULL) AS is_original_lac_trusted,
    ml.best_lac_dec,
    CASE
      -- 多LAC收敛：优先使用主 LAC（即使原始 LAC 也是 trusted）
      WHEN mb.lac_choice_cnt > 1 AND ml.best_lac_dec IS NOT NULL THEN ml.best_lac_dec
      WHEN t_orig.lac_dec IS NOT NULL THEN l.lac_dec
      ELSE mb.lac_dec_from_map
    END AS lac_dec_final,
    CASE
      WHEN mb.lac_choice_cnt > 1 AND ml.best_lac_dec IS NOT NULL AND l.lac_dec IS DISTINCT FROM ml.best_lac_dec THEN 'MULTI_LAC_OVERRIDE'
      WHEN mb.lac_choice_cnt > 1 AND ml.best_lac_dec IS NOT NULL THEN 'MULTI_LAC_KEEP'
      WHEN t_orig.lac_dec IS NOT NULL THEN 'KEEP_TRUSTED_LAC'
      WHEN l.lac_dec IS NULL AND mb.lac_dec_from_map IS NOT NULL THEN 'BACKFILL_NULL_LAC'
      WHEN l.lac_dec IS NOT NULL AND mb.lac_dec_from_map IS NOT NULL THEN 'REPLACE_UNTRUSTED_LAC'
      WHEN l.lac_dec IS NULL AND mb.lac_dec_from_map IS NULL THEN 'NO_LAC_NO_MAPPING'
      WHEN l.lac_dec IS NOT NULL AND mb.lac_dec_from_map IS NULL THEN 'UNTRUSTED_LAC_NO_MAPPING'
      ELSE 'OTHER'
    END AS lac_enrich_status
  FROM tmp_step06_lac_scope l
  LEFT JOIN tmp_step06_map_best mb
    ON l.operator_id_raw = mb.operator_id_raw
   AND l.tech_norm = mb.tech_norm
   AND l.cell_id_dec = mb.cell_id_dec
  LEFT JOIN tmp_step06_multilac_best ml
    ON ml.operator_id_raw=l.operator_id_raw
   AND ml.tech_norm=l.tech_norm
   AND ml.cell_id_dec=l.cell_id_dec
  LEFT JOIN tmp_step06_trusted_lac t_orig
    ON l.operator_id_raw = t_orig.operator_id_raw
   AND l.tech_norm = t_orig.tech_norm
   AND l.lac_dec = t_orig.lac_dec
)
SELECT
  j.*,
  true AS is_final_lac_trusted,
  (j.lac_dec IS DISTINCT FROM j.lac_dec_final) AS is_lac_changed_by_mapping
FROM joined j
JOIN tmp_step06_trusted_lac t_final
  ON t_final.operator_id_raw = j.operator_id_raw
 AND t_final.tech_norm = j.tech_norm
 AND t_final.lac_dec = j.lac_dec_final
WHERE j.lac_dec_final IS NOT NULL;

ANALYZE public."Y_codex_Layer2_Step06_L0_Lac_Filtered";

-- 输出口径归一（重要）：
-- - lac_dec_final 才是最终可信 LAC，但很多人会直接看 lac_dec/lac_hex（原始透传字段，可能为 NULL/0/FFFF/7FFFFFFF 等异常）。
-- - 这里把“明显异常的原始透传字段”归一为最终值，并保留原始值到 lac_dec_raw/lac_hex_raw（仅对被修正行写入）。
ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_dec_raw bigint;
ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_hex_raw text;
ALTER TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  ADD COLUMN IF NOT EXISTS lac_output_normalized boolean;

UPDATE public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
SET
  lac_dec_raw = t.lac_dec,
  lac_hex_raw = t.lac_hex,
  lac_dec = t.lac_dec_final,
  lac_hex = upper(to_hex(t.lac_dec_final)),
  lac_output_normalized = true
WHERE
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

-- 信号字段清洗（用户确认）：
-- - sig_rsrp 的无效值统一置 NULL，便于后续 Step33/未来信号补数进行补齐。
--   已观测到的无效/占位值：-110、-1，以及非负数（>=0，明显不符合 RSRP dBm 取值）。
UPDATE public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
SET sig_rsrp = NULL
WHERE sig_rsrp IN (-110, -1) OR sig_rsrp >= 0;

ANALYZE public."Y_codex_Layer2_Step06_L0_Lac_Filtered";


-- 清理旧命名（历史遗留）
DROP TABLE IF EXISTS public.rpt_step6_gps_vs_lac_compare;

DROP TABLE IF EXISTS public."Y_codex_Layer2_Step06_GpsVsLac_Compare";

CREATE TABLE public."Y_codex_Layer2_Step06_GpsVsLac_Compare" AS
WITH gps_raw AS (
  SELECT
    'GPS_RAW'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec) FILTER (WHERE cell_id_dec IS NOT NULL)::bigint AS cell_cnt,
    count(DISTINCT lac_dec) FILTER (WHERE lac_dec IS NOT NULL)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step00_Gps_Std"
  GROUP BY 2,3,4
),
gps_compliant AS (
  SELECT
    'GPS_COMPLIANT'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
  WHERE is_compliant
  GROUP BY 2,3,4
),
lac_raw AS (
  SELECT
    'LAC_RAW'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec) FILTER (WHERE cell_id_dec IS NOT NULL)::bigint AS cell_cnt,
    count(DISTINCT lac_dec) FILTER (WHERE lac_dec IS NOT NULL)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step00_Lac_Std"
  GROUP BY 2,3,4
),
lac_eligible AS (
  SELECT
    'LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec) FILTER (WHERE lac_dec IS NOT NULL)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM tmp_step06_lac_scope
  GROUP BY 2,3,4
),
lac_supplemented AS (
  SELECT
    'LAC_SUPPLEMENTED_TRUSTED'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec_final)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  GROUP BY 2,3,4
),
lac_supplemented_backfilled AS (
  SELECT
    'LAC_SUPPLEMENTED_BACKFILLED'::text AS dataset,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec_final)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
  WHERE lac_enrich_status IN ('BACKFILL_NULL_LAC','REPLACE_UNTRUSTED_LAC')
  GROUP BY 2,3,4
),
lac_cell_no_operator AS (
  SELECT
    'LAC_RAW_HAS_CELL_NO_OPERATOR'::text AS dataset,
    tech_norm,
    'NO_OPERATOR'::text AS operator_id_raw,
    'NO_OPERATOR'::text AS operator_group_hint,
    count(*)::bigint AS row_cnt,
    count(DISTINCT cell_id_dec)::bigint AS cell_cnt,
    count(DISTINCT lac_dec) FILTER (WHERE lac_dec IS NOT NULL)::bigint AS lac_cnt,
    count(DISTINCT device_id) FILTER (WHERE device_id IS NOT NULL)::bigint AS device_cnt
  FROM public."Y_codex_Layer2_Step00_Lac_Std"
  WHERE tech_norm IN ('4G','5G')
    AND cell_id_dec IS NOT NULL
    AND operator_id_raw IS NULL
  GROUP BY 2
)
SELECT * FROM gps_raw
UNION ALL
SELECT * FROM gps_compliant
UNION ALL
SELECT * FROM lac_raw
UNION ALL
SELECT * FROM lac_eligible
UNION ALL
SELECT * FROM lac_supplemented
UNION ALL
SELECT * FROM lac_supplemented_backfilled
UNION ALL
SELECT * FROM lac_cell_no_operator
ORDER BY dataset, row_cnt DESC;

ANALYZE public."Y_codex_Layer2_Step06_GpsVsLac_Compare";

COMMENT ON TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered" IS
'Step06 LAC 路反哺后明细（TABLE）：在 5PLMN+4G/5G+has_cell 范围内，以 Step05 映射（operator+tech+cell -> lac）对 LAC 路进行 lac 补齐/纠偏，输出 lac_dec_final，并仅保留最终 lac 在 Step04 可信白名单内的记录。';

COMMENT ON TABLE public."Y_codex_Layer2_Step06_GpsVsLac_Compare" IS
'Step06 对比报表：GPS_RAW/GPS_COMPLIANT/LAC_RAW/LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL/LAC_SUPPLEMENTED_TRUSTED/LAC_SUPPLEMENTED_BACKFILLED/LAC_RAW_HAS_CELL_NO_OPERATOR 的行数、去重 cell/lac/设备数，用于评估合规库→映射→反哺的覆盖与补齐效果。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".dataset IS
'数据集 (Dataset): GPS_RAW / GPS_COMPLIANT / LAC_RAW / LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL / LAC_SUPPLEMENTED_TRUSTED / LAC_SUPPLEMENTED_BACKFILLED / LAC_RAW_HAS_CELL_NO_OPERATOR';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".tech_norm IS '制式_标准化 (Normalized tech)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".operator_id_raw IS '运营商id_细粒度 (Raw operator id)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".operator_group_hint IS '运营商组_提示 (Operator group hint)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".row_cnt IS '行数 (Row count)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".cell_cnt IS '去重cell数 (Distinct cell_id_dec)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".lac_cnt IS '去重LAC数 (Distinct lac_dec or lac_dec_final by dataset)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step06_GpsVsLac_Compare".device_cnt IS '设备数 (Distinct device_id)';


-- 验证 SQL（至少 3 条）
-- 1) 反哺后 LAC 行数（应 <= LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL）
-- select
--   (select sum(row_cnt) from public."Y_codex_Layer2_Step06_GpsVsLac_Compare" where dataset='LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL') as eligible_rows,
--   (select sum(row_cnt) from public."Y_codex_Layer2_Step06_GpsVsLac_Compare" where dataset='LAC_SUPPLEMENTED_TRUSTED') as supplemented_rows;
-- 2) 反哺后最终 LAC 必须落在 Step04 白名单内（应为 0）
-- select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" f
-- left join public."Y_codex_Layer2_Step04_Master_Lac_Lib" t
--   on f.operator_id_raw=t.operator_id_raw and f.tech_norm=t.tech_norm and f.lac_dec_final=t.lac_dec
-- where t.lac_dec is null;
-- 3) 对比报表数据集是否都有输出
-- select dataset, sum(row_cnt) from public."Y_codex_Layer2_Step06_GpsVsLac_Compare" group by 1 order by 1;
