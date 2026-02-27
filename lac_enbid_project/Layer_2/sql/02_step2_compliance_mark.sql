-- Layer_2 Step2：合规标记（行级绝对合规）+ 合规前后对比报表
-- 输入：
--   public."Y_codex_Layer2_Step00_Gps_Std"
-- 输出：
--   public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
--   public."Y_codex_Layer2_Step02_Compliance_Diff"

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

-- 性能辅助（幂等）：与 Step00 重复也无妨，确保本地迭代不会漏建索引
CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_gps_base_ts_std
  ON public."Y_codex_Layer0_Gps_base" USING brin (ts_std);

CREATE INDEX IF NOT EXISTS brin_y_codex_layer0_lac_ts_std
  ON public."Y_codex_Layer0_Lac" USING brin (ts_std);

CREATE INDEX IF NOT EXISTS ix_y_codex_layer0_lac_join_keys_raw
  ON public."Y_codex_Layer0_Lac" ("运营商id", tech, lac_dec, cell_id_dec);

-- 兼容重跑：如果历史上把合规明细物化成 TABLE，这里会自动清理后再建 VIEW
DO $$
BEGIN
  IF to_regclass('public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'Y_codex_Layer2_Step02_Gps_Compliance_Marked'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    ELSE
      EXECUTE 'DROP TABLE public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"';
    END IF;
  END IF;

  -- 清理旧命名（历史遗留）
  IF to_regclass('public.d_step2_gps_compliance_marked') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'd_step2_gps_compliance_marked'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public.d_step2_gps_compliance_marked';
    ELSE
      EXECUTE 'DROP TABLE public.d_step2_gps_compliance_marked';
    END IF;
  END IF;
  IF to_regclass('public.rpt_step2_compliance_diff') IS NOT NULL THEN
    IF EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'rpt_step2_compliance_diff'
        AND c.relkind = 'v'
    ) THEN
      EXECUTE 'DROP VIEW public.rpt_step2_compliance_diff';
    ELSE
      EXECUTE 'DROP TABLE public.rpt_step2_compliance_diff';
    END IF;
  END IF;
END $$;

CREATE OR REPLACE VIEW public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" AS
WITH base AS (
  SELECT *
  FROM public."Y_codex_Layer2_Step00_Gps_Std"
),
flags AS (
  SELECT
    b.*,
    COALESCE((b.operator_id_raw IN ('46000','46001','46011','46015','46020')), false) AS is_operator_in_scope,
    COALESCE((b.tech_norm IN ('4G','5G')), false) AS is_tech_4g5g,
    CASE
      WHEN b.lac_dec IS NOT NULL AND b.lac_dec > 0 THEN
        upper(to_hex(b.lac_dec)) NOT IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')
      ELSE false
    END AS is_lac_num_ok,
    CASE
      WHEN b.lac_dec IS NOT NULL AND b.lac_dec > 0 THEN
        upper(to_hex(b.lac_dec)) IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')
      ELSE false
    END AS is_lac_overflow_sentinel,
    CASE
      WHEN b.lac_dec IS NOT NULL AND b.lac_dec > 0 THEN char_length(to_hex(b.lac_dec))
    END AS lac_hex_len,
    CASE
      WHEN NOT (b.lac_dec IS NOT NULL AND b.lac_dec > 0) THEN false
      WHEN b.operator_id_raw IN ('46000','46015','46020') THEN char_length(to_hex(b.lac_dec)) IN (4,6)
      WHEN b.operator_id_raw IN ('46001','46011') THEN char_length(to_hex(b.lac_dec)) BETWEEN 4 AND 6
      ELSE false
    END AS is_lac_hex_len_ok,
    (b.cell_id_dec IS NOT NULL) AS has_cell_num,
    (b.cell_id_dec IS NOT NULL AND b.cell_id_dec > 0) AS is_cell_positive,
    (b.cell_id_dec = 2147483647) AS is_cell_overflow_2147483647,
    CASE
      WHEN b.tech_norm = '4G' THEN 268435455::bigint       -- 28-bit ECI
      WHEN b.tech_norm = '5G' THEN 68719476735::bigint     -- 36-bit NCI
    END AS cell_id_max_allowed,
    CASE
      WHEN b.cell_id_dec IS NULL THEN false
      WHEN b.tech_norm = '4G' THEN b.cell_id_dec BETWEEN 1 AND 268435455::bigint
      WHEN b.tech_norm = '5G' THEN b.cell_id_dec BETWEEN 1 AND 68719476735::bigint
      ELSE false
    END AS is_cell_range_ok
  FROM base b
),
marked AS (
  SELECT
    f.*,
    (f.is_operator_in_scope AND f.is_tech_4g5g AND f.is_lac_num_ok AND f.is_lac_hex_len_ok) AS is_l1_lac_ok,
    (
      f.is_operator_in_scope
      AND f.is_tech_4g5g
      AND f.is_lac_num_ok
      AND f.is_lac_hex_len_ok
      AND f.has_cell_num
      AND f.is_cell_positive
      AND NOT f.is_cell_overflow_2147483647
      AND f.is_cell_range_ok
    ) AS is_l1_cell_ok,
    (
      f.is_operator_in_scope
      AND f.is_tech_4g5g
      AND f.is_lac_num_ok
      AND f.is_lac_hex_len_ok
      AND f.has_cell_num
      AND f.is_cell_positive
      AND NOT f.is_cell_overflow_2147483647
      AND f.is_cell_range_ok
    ) AS is_compliant,
    array_to_string(
      array_remove(
        ARRAY[
          CASE WHEN NOT f.is_operator_in_scope THEN 'OPERATOR_OUT_OF_SCOPE' END,
          CASE WHEN NOT f.is_tech_4g5g THEN 'TECH_NOT_4G_5G' END,
          CASE WHEN NOT f.is_lac_num_ok THEN 'LAC_INVALID' END,
          CASE WHEN f.is_lac_overflow_sentinel THEN 'LAC_OVERFLOW_SENTINEL' END,
          CASE
            WHEN f.is_lac_num_ok AND NOT f.is_lac_hex_len_ok AND f.operator_id_raw IN ('46000','46015','46020')
              THEN 'LAC_HEXLEN_NOT_4_OR_6_FOR_CMCC'
          END,
          CASE
            WHEN f.is_lac_num_ok AND NOT f.is_lac_hex_len_ok AND f.operator_id_raw IN ('46001','46011')
              THEN 'LAC_HEXLEN_NOT_4_TO_6_FOR_CU_CT'
          END,
          CASE
            WHEN f.is_lac_num_ok AND NOT f.is_lac_hex_len_ok
             AND f.operator_id_raw NOT IN ('46000','46001','46011','46015','46020')
              THEN 'LAC_HEXLEN_RULE_NO_MATCH'
          END,
          CASE WHEN NOT f.has_cell_num THEN 'CELLID_NULL_OR_NONNUMERIC' END,
          CASE WHEN f.has_cell_num AND NOT f.is_cell_positive THEN 'CELLID_NONPOSITIVE' END,
          CASE WHEN f.is_cell_overflow_2147483647 THEN 'CELLID_OVERFLOW_2147483647' END,
          CASE
            WHEN f.has_cell_num AND f.is_cell_positive AND NOT f.is_cell_overflow_2147483647
             AND NOT f.is_cell_range_ok AND f.tech_norm = '4G'
              THEN 'CELLID_OUT_OF_RANGE_4G'
          END,
          CASE
            WHEN f.has_cell_num AND f.is_cell_positive AND NOT f.is_cell_overflow_2147483647
             AND NOT f.is_cell_range_ok AND f.tech_norm = '5G'
              THEN 'CELLID_OUT_OF_RANGE_5G'
          END
        ],
        NULL
      ),
      chr(59)
    ) AS non_compliant_reason
  FROM flags f
)
SELECT * FROM marked;


DROP TABLE IF EXISTS public."Y_codex_Layer2_Step02_Compliance_Diff";

CREATE TABLE public."Y_codex_Layer2_Step02_Compliance_Diff" AS
WITH m AS (
  SELECT * FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
),
by_dim AS (
  SELECT
    'BY_DIM'::text AS report_section,
    tech_norm,
    operator_id_raw,
    operator_group_hint,
    parsed_from,
    is_compliant,
    NULL::text AS non_compliant_reason,
    count(*)::bigint AS row_cnt
  FROM m
  GROUP BY 2,3,4,5,6
),
by_reason AS (
  SELECT
    'TOP_REASON'::text AS report_section,
    NULL::text AS tech_norm,
    NULL::text AS operator_id_raw,
    NULL::text AS operator_group_hint,
    NULL::text AS parsed_from,
    false AS is_compliant,
    non_compliant_reason,
    count(*)::bigint AS row_cnt
  FROM m
  WHERE NOT is_compliant
  GROUP BY non_compliant_reason
  ORDER BY row_cnt DESC
  LIMIT 50
),
unioned AS (
  SELECT * FROM by_dim
  UNION ALL
  SELECT * FROM by_reason
)
SELECT
  u.*,
  CASE
    WHEN u.report_section = 'BY_DIM' THEN round(u.row_cnt::numeric / nullif(sum(u.row_cnt) OVER (PARTITION BY u.report_section), 0), 8)
    ELSE round(u.row_cnt::numeric / nullif(sum(u.row_cnt) OVER (PARTITION BY u.report_section), 0), 8)
  END AS row_pct
FROM unioned u;

ANALYZE public."Y_codex_Layer2_Step02_Compliance_Diff";

COMMENT ON VIEW public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" IS
'Step02 合规标记明细（VIEW）：在 Step00 标准化 GPS 明细上按 Layer_1 起点规则做行级绝对合规打标，输出 is_compliant 与 non_compliant_reason。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_operator_in_scope IS
'运营商是否在范围内 (Operator in-scope): operator_id_raw ∈ {46000,46001,46011,46015,46020}';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_tech_4g5g IS
'制式是否为4G/5G (Tech is 4G/5G): tech_norm ∈ {4G,5G}';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_lac_num_ok IS
'LAC数值合规 (LAC numeric ok): lac_dec is not null and lac_dec > 0 and not in overflow sentinels (FFFF/FFFE/FFFFFE/FFFFFF/7FFFFFFF)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_lac_overflow_sentinel IS
'LAC是否命中溢出/占位值 (LAC overflow sentinel): upper(to_hex(lac_dec)) IN {FFFF,FFFE,FFFFFE,FFFFFF,7FFFFFFF}';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".lac_hex_len IS
'LAC十六进制位数 (LAC hex length): char_length(to_hex(lac_dec))';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_lac_hex_len_ok IS
'LAC十六进制位数合规 (LAC hex length ok): CMCC系 hex_len∈{4,6}; CU/CT hex_len∈[4,6]';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".has_cell_num IS
'Cell数值是否存在 (Cell numeric exists): cell_id_dec is not null';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_cell_positive IS
'Cell是否为正数 (Cell > 0): cell_id_dec > 0';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_cell_overflow_2147483647 IS
'Cell是否为溢出默认值 (Cell overflow sentinel): cell_id_dec = 2147483647';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".cell_id_max_allowed IS
'Cell最大允许值 (Cell max allowed): 4G<=268435455(28-bit ECI); 5G<=68719476735(36-bit NCI)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_cell_range_ok IS
'Cell范围合规 (Cell range ok): 4G cell_id_dec∈[1,268435455]; 5G cell_id_dec∈[1,68719476735]';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_l1_lac_ok IS
'是否L1_LAC合规 (L1 LAC ok): operator+tech+lac_num+lac_hex_len 四项合规';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_l1_cell_ok IS
'是否L1_CELL合规 (L1 Cell ok): 在 L1_LAC ok 基础上 cell 数值合规 + not 2147483647 + cell range ok';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".is_compliant IS
'是否合规 (Compliant flag): 当前口径等同 is_l1_cell_ok';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Gps_Compliance_Marked".non_compliant_reason IS
'不合规原因 (Non-compliant reasons): 多原因用 ; 拼接';

COMMENT ON TABLE public."Y_codex_Layer2_Step02_Compliance_Diff" IS
'Step02 合规前后对比报表：BY_DIM（按 tech/operator/source/is_compliant 聚合）+ TOP_REASON（Top 非合规原因），用于审计与定位。';

COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Compliance_Diff".report_section IS '报表分区 (Report section): BY_DIM / TOP_REASON';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Compliance_Diff".row_cnt IS '行数 (Row count)';
COMMENT ON COLUMN public."Y_codex_Layer2_Step02_Compliance_Diff".row_pct IS '占比 (Row percentage within section)';


-- 验证 SQL（至少 3 条）
-- 1) 合规/不合规计数
-- select is_compliant, count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" group by 1;
-- 2) 合规记录不应包含 NULL cell/lac 或非 4G/5G
-- select count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
-- where is_compliant and (lac_dec is null or cell_id_dec is null or tech_norm not in ('4G','5G'));
-- 3) 不合规原因 TopN
-- select non_compliant_reason, count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
-- where not is_compliant group by 1 order by 2 desc limit 20;
