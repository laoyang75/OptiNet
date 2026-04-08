-- mapping_issue_audit_step05_multilac_20251219.sql
--
-- 用途：输出“映射/口径问题”的核心明细（多 LAC 小区），用于人工点查。
-- 数据源：
--   - public."Y_codex_Layer2_Step05_CellId_Stats_DB"
--   - public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
-- 可选：
--   - public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"（仅对少量 top cell 做明细分布）

-- 1) 总体规模：多 LAC 小区分布
WITH cell_lac_cnt AS (
  SELECT operator_id_raw, tech_norm, cell_id_dec,
         count(*)::int AS lac_choice_cnt,
         sum(record_count)::bigint AS total_record_count,
         sum(valid_gps_count)::bigint AS total_valid_gps_count
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
  WHERE operator_id_raw IS NOT NULL AND tech_norm IS NOT NULL AND cell_id_dec IS NOT NULL AND lac_dec IS NOT NULL
  GROUP BY 1,2,3
)
SELECT
  lac_choice_cnt,
  count(*)::bigint AS cell_cnt,
  sum(total_record_count)::bigint AS total_record_cnt,
  sum(total_valid_gps_count)::bigint AS total_valid_gps_cnt
FROM cell_lac_cnt
WHERE lac_choice_cnt >= 2
GROUP BY 1
ORDER BY lac_choice_cnt DESC;

-- 2) Top10：按 LAC 个数 + 规模（总记录数）
WITH stats AS (
  SELECT
    s.*,
    sum(s.record_count) OVER (PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec) AS total_record_count,
    sum(s.valid_gps_count) OVER (PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec) AS total_valid_gps_count,
    row_number() OVER (
      PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec
      ORDER BY s.record_count DESC, s.valid_gps_count DESC, s.distinct_device_count DESC, s.active_days DESC, s.lac_dec ASC
    ) AS rn
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
  JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
    ON a.operator_id_raw=s.operator_id_raw
   AND a.tech_norm=s.tech_norm
   AND a.cell_id_dec=s.cell_id_dec
),
main AS (SELECT * FROM stats WHERE rn=1),
second AS (SELECT * FROM stats WHERE rn=2)
SELECT
  a.operator_id_raw,
  a.tech_norm,
  a.cell_id_dec,
  a.lac_distinct_cnt,
  a.lac_list,
  m.total_record_count,
  m.total_valid_gps_count,
  a.first_seen_ts,
  a.last_seen_ts,
  m.lac_dec AS top1_lac_dec,
  m.record_count AS top1_record_cnt,
  round((m.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top1_share,
  s2.lac_dec AS top2_lac_dec,
  s2.record_count AS top2_record_cnt,
  round((s2.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top2_share,
  round(
    (
      6371000.0 * 2.0 * asin(
        sqrt(
          power(sin(radians((s2.gps_center_lat - m.gps_center_lat) / 2.0)), 2)
          + cos(radians(m.gps_center_lat)) * cos(radians(s2.gps_center_lat))
            * power(sin(radians((s2.gps_center_lon - m.gps_center_lon) / 2.0)), 2)
        )
      )
    )::numeric,
    1
  ) AS top1_top2_center_dist_m
FROM public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
JOIN main m
  ON m.operator_id_raw=a.operator_id_raw AND m.tech_norm=a.tech_norm AND m.cell_id_dec=a.cell_id_dec
JOIN second s2
  ON s2.operator_id_raw=a.operator_id_raw AND s2.tech_norm=a.tech_norm AND s2.cell_id_dec=a.cell_id_dec
ORDER BY a.lac_distinct_cnt DESC, m.total_record_count DESC
LIMIT 10;

-- 3) Top20：最像真问题（Top2 占比 >= 5%，按中心点距离排序）
WITH stats AS (
  SELECT
    s.*,
    sum(s.record_count) OVER (PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec) AS total_record_count,
    row_number() OVER (
      PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec
      ORDER BY s.record_count DESC, s.valid_gps_count DESC, s.distinct_device_count DESC, s.active_days DESC, s.lac_dec ASC
    ) AS rn
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
  JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
    ON a.operator_id_raw=s.operator_id_raw
   AND a.tech_norm=s.tech_norm
   AND a.cell_id_dec=s.cell_id_dec
),
main AS (SELECT * FROM stats WHERE rn=1),
second AS (SELECT * FROM stats WHERE rn=2)
SELECT
  m.operator_id_raw,
  m.tech_norm,
  m.cell_id_dec,
  m.lac_dec AS top1_lac_dec,
  round((m.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top1_share,
  s2.lac_dec AS top2_lac_dec,
  round((s2.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top2_share,
  round(
    (
      6371000.0 * 2.0 * asin(
        sqrt(
          power(sin(radians((s2.gps_center_lat - m.gps_center_lat) / 2.0)), 2)
          + cos(radians(m.gps_center_lat)) * cos(radians(s2.gps_center_lat))
            * power(sin(radians((s2.gps_center_lon - m.gps_center_lon) / 2.0)), 2)
        )
      )
    )::numeric,
    1
  ) AS top1_top2_center_dist_m,
  m.total_record_count
FROM main m
JOIN second s2
  ON s2.operator_id_raw=m.operator_id_raw AND s2.tech_norm=m.tech_norm AND s2.cell_id_dec=m.cell_id_dec
WHERE (s2.record_count::numeric / nullif(m.total_record_count,0)) >= 0.05
ORDER BY top1_top2_center_dist_m DESC NULLS LAST
LIMIT 20;

-- 4) 对某个 cell 点查：列出该 cell 的全部 LAC 候选明细
-- select *
-- from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
-- where operator_id_raw='46000' and tech_norm='4G' and cell_id_dec=126936197
-- order by record_count desc, valid_gps_count desc, lac_dec;

-- 5) （可选）对“最像真问题”的 Top10 cell，去 Step31 看它在不同 lac_dec_final 下的分布（行数很小）
WITH stats AS (
  SELECT
    s.*,
    sum(s.record_count) OVER (PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec) AS total_record_count,
    row_number() OVER (
      PARTITION BY s.operator_id_raw, s.tech_norm, s.cell_id_dec
      ORDER BY s.record_count DESC, s.valid_gps_count DESC, s.distinct_device_count DESC, s.active_days DESC, s.lac_dec ASC
    ) AS rn
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB" s
  JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
    ON a.operator_id_raw=s.operator_id_raw
   AND a.tech_norm=s.tech_norm
   AND a.cell_id_dec=s.cell_id_dec
),
main AS (SELECT * FROM stats WHERE rn=1),
second AS (SELECT * FROM stats WHERE rn=2),
serious_cells AS (
  SELECT
    m.operator_id_raw,
    m.tech_norm,
    m.cell_id_dec,
    round((m.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top1_share,
    round((s2.record_count::numeric / nullif(m.total_record_count,0))::numeric, 4) AS top2_share,
    round(
      (
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians((s2.gps_center_lat - m.gps_center_lat) / 2.0)), 2)
            + cos(radians(m.gps_center_lat)) * cos(radians(s2.gps_center_lat))
              * power(sin(radians((s2.gps_center_lon - m.gps_center_lon) / 2.0)), 2)
          )
        )
      )::numeric,
      1
    ) AS top1_top2_center_dist_m
  FROM main m
  JOIN second s2
    ON s2.operator_id_raw=m.operator_id_raw AND s2.tech_norm=m.tech_norm AND s2.cell_id_dec=m.cell_id_dec
  WHERE (s2.record_count::numeric / nullif(m.total_record_count,0)) >= 0.05
  ORDER BY top1_top2_center_dist_m DESC NULLS LAST
  LIMIT 10
)
SELECT
  sc.operator_id_raw,
  sc.tech_norm,
  sc.cell_id_dec,
  sc.top1_share,
  sc.top2_share,
  sc.top1_top2_center_dist_m,
  s31.lac_dec_final,
  s31.bs_id,
  count(*)::bigint AS row_cnt,
  count(*) FILTER (WHERE s31.gps_status='Verified')::bigint AS verified_cnt,
  count(*) FILTER (WHERE s31.gps_status='Drift')::bigint AS drift_cnt,
  count(*) FILTER (WHERE s31.gps_status='Missing')::bigint AS missing_cnt
FROM serious_cells sc
JOIN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" s31
  ON s31.operator_id_raw=sc.operator_id_raw
 AND s31.tech_norm=sc.tech_norm
 AND s31.cell_id_dec=sc.cell_id_dec
GROUP BY 1,2,3,4,5,6,7,8
ORDER BY sc.top1_top2_center_dist_m DESC, row_cnt DESC;

