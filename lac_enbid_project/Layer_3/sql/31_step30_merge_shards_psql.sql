\set ON_ERROR_STOP on
\timing on

-- Step30 分片合并（psql 专用）
-- 用法：
--   psql "$DATABASE_URL" -v shard_count=16 -f lac_enbid_project/Layer_3/sql/31_step30_merge_shards_psql.sql
--
-- 说明：
-- - 合并会生成标准主表 `public."Y_codex_Layer3_Step30_Master_BS_Library"` 并重建 `Step30_Gps_Level_Stats`
-- - 分片表命名约定：Y_codex_Layer3_Step30_Master_BS_Library__shard_00 .. __shard_15

\if :{?shard_count}
\else
  \echo 'ERROR: missing -v shard_count=<N>'
  \quit 2
\endif

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 动态拼接 UNION ALL 并执行
WITH union_sql AS (
  SELECT string_agg(
           format('SELECT * FROM public.\"Y_codex_Layer3_Step30_Master_BS_Library__shard_%s\"', lpad(i::text, 2, '0')),
           E'\nUNION ALL\n'
         ) AS body
  FROM generate_series(0, (:'shard_count')::int - 1) AS i
),
final_sql AS (
  SELECT format('CREATE TABLE public.\"Y_codex_Layer3_Step30_Master_BS_Library\" AS\n%s;', body) AS sql
  FROM union_sql
)
SELECT sql FROM final_sql \gexec

ANALYZE public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 重建统计表（只做一次，避免分片重复统计）
DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30_Gps_Level_Stats";

CREATE TABLE public."Y_codex_Layer3_Step30_Gps_Level_Stats" AS
WITH base AS (
  SELECT
    s.tech_norm,
    op.operator_id_raw,
    s.gps_valid_level,
    count(*)::bigint AS bs_cnt
  FROM public."Y_codex_Layer3_Step30_Master_BS_Library" s
  CROSS JOIN LATERAL unnest(string_to_array(s.shared_operator_list, ',')) AS op(operator_id_raw)
  GROUP BY 1,2,3
),
scored AS (
  SELECT
    b.*,
    round((b.bs_cnt::numeric / nullif(sum(b.bs_cnt) OVER (PARTITION BY b.tech_norm, b.operator_id_raw), 0))::numeric, 8) AS bs_pct
  FROM base b
)
SELECT * FROM scored;

ANALYZE public."Y_codex_Layer3_Step30_Gps_Level_Stats";
