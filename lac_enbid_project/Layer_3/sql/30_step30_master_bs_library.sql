-- Layer_3 Step30：基站主库（站级画像 + 共建标记 + 基站中心点/GPS质量）
-- 输入依赖（Layer_2 冻结）：
--   - public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"  （提供“可信 GPS 点”样本）
--   - public."Y_codex_Layer2_Step04_Master_Lac_Lib"         （可信 LAC 白名单）
--   - public."Y_codex_Layer2_Step05_CellId_Stats_DB"        （cell->lac 映射证据底座）
--   - public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" （碰撞/错归并风险监测清单）
--   - public."Y_codex_Layer2_Step06_L0_Lac_Filtered"        （可信明细库，用于覆盖时间画像）
--
-- 输出：
--   - public."Y_codex_Layer3_Step30_Master_BS_Library"（TABLE）
--
-- 说明：
-- - 本步仅使用“Verified + 合法经纬度 + 非(0,0)”的 GPS 点参与聚合；
-- - 物理分桶键：wuli_fentong_bs_key = tech_norm|bs_id|lac_dec_final
-- - 中心点算法：简单鲁棒 v2（点级中位中心点 → 以半径阈值剔除漂移点 → 重算）

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

DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30_Master_BS_Library";

CREATE TABLE public."Y_codex_Layer3_Step30_Master_BS_Library" AS
WITH
params AS (
  SELECT
    -- 冒烟开关：true=只跑一个日期/一个运营商（3~10 分钟级），false=全量
    COALESCE(current_setting('codex.is_smoke', true), 'false')::boolean AS is_smoke,
    COALESCE((NULLIF(current_setting('codex.smoke_report_date', true), ''))::date, date '2025-12-01') AS smoke_report_date,
    COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000')::text AS smoke_operator_id_raw,

    -- 距离阈值（米）：本轮默认值，后续按分布评估迭代（不要散落在 SQL 里）
    2500.0::double precision AS outlier_remove_if_dist_m_gt,
    1500.0::double precision AS collision_if_p90_dist_m_gt,

    -- 信号优先中心点（用户确认）：
    -- - 先选信号好的 Top50/Top20；若信号点不足，则选“信号有效点”Top80%；
    -- - 若有效信号点不足（<min），回退到“全量点中位数中心”。
    50::int AS signal_keep_top50_n,
    20::int AS signal_keep_top20_n,
    0.8::double precision AS signal_keep_ratio_if_low_cnt,
    5::int AS signal_min_points_for_signal_center,

    -- 结构性并行策略：PostgreSQL 并行查询常被 Gather/Finalize/Window/Agg 掐断，表现为 workers 长期 MessageQueueSend + leader 单核跑。
    -- 这里提供“分片并发”开关：用 wuli_fentong_bs_key 做一致性 hash，把桶切成 N 份，多会话并发跑（每份独立产出），最后合并。
    -- 用法示例（每个会话跑一份）：
    --   SELECT set_config('codex.shard_count','8', true);
    --   SELECT set_config('codex.shard_id','0', true);  -- 0..7
    --   -- 建议同时把 max_parallel_workers_per_gather 调低到 0~2，避免“查询内并行”与“分片并发”叠加导致 MQ 争用
    COALESCE((NULLIF(current_setting('codex.shard_count', true), ''))::int, 1) AS shard_count,
    COALESCE((NULLIF(current_setting('codex.shard_id', true), ''))::int, 0) AS shard_id,

    -- 性能关键：将连续分位数（percentile_cont）替换为“分桶加权分位数”近似，以避免超大规模排序/临时文件爆炸。
    -- - center_bin_scale：经纬度分桶精度（10000 => 0.0001° ≈ 11m）
    -- - dist_bin_m：距离分桶精度（米）
    10000::int AS center_bin_scale,
    10::int AS dist_bin_m
),
bucket_universe AS (
  -- 以 Step06 可信明细库为“基站桶全集”（即使没有 Verified GPS 点，也要能标记为 Unusable）
  SELECT
    t.tech_norm,
    t.bs_id,
    t.lac_dec_final,
    (t.tech_norm || '|' || t.bs_id::text || '|' || t.lac_dec_final::text) AS wuli_fentong_bs_key,
    count(DISTINCT t.operator_id_raw)::int AS shared_operator_cnt,
    array_to_string(array_agg(DISTINCT t.operator_id_raw ORDER BY t.operator_id_raw), ',') AS shared_operator_list,
    min(t.ts_std) AS first_seen_ts,
    max(t.ts_std) AS last_seen_ts,
    count(DISTINCT t.report_date)::int AS active_days
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" t
  CROSS JOIN params p
  WHERE
    t.tech_norm IN ('4G','5G')
    AND t.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND t.bs_id IS NOT NULL
    AND t.bs_id <> 0
    AND t.cell_id_dec IS NOT NULL
    AND t.cell_id_dec <> 0
    AND t.lac_dec_final IS NOT NULL
    AND (
      p.shard_count <= 1
      OR ((mod(hashtextextended((t.tech_norm || '|' || t.bs_id::text || '|' || t.lac_dec_final::text), 0), p.shard_count) + p.shard_count) % p.shard_count) = p.shard_id
    )
    AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR t.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t.operator_id_raw = p.smoke_operator_id_raw)
  GROUP BY 1,2,3
),
trusted_lac AS (
  SELECT operator_id_raw, tech_norm, lac_dec
  FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  WHERE is_trusted_lac
),
map_unique AS (
  -- Step05 是 “cell->lac 证据底座”；Step30 仅在“唯一映射”时才回填 lac（否则置空）
  -- 这里不再用 DISTINCT ON + 大排序：直接用 min/max 判断是否唯一（性能更稳）。
  SELECT
    operator_id_raw,
    tech_norm,
    cell_id_dec,
    CASE WHEN min(lac_dec) = max(lac_dec) THEN min(lac_dec) END AS lac_dec_from_map
  FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
  GROUP BY 1,2,3
),
gps_points_raw AS (
  SELECT
    m.operator_id_raw,
    m.operator_group_hint,
    m.tech_norm,
    COALESCE(
      m.bs_id,
      CASE
        WHEN m.tech_norm='4G' AND m.cell_id_dec IS NOT NULL THEN floor(m.cell_id_dec / 256.0)::bigint
        WHEN m.tech_norm='5G' AND m.cell_id_dec IS NOT NULL THEN floor(m.cell_id_dec / 4096.0)::bigint
      END
    ) AS bs_id,
    m.cell_id_dec,
    m.lac_dec,
    m.report_date,
    m.ts_std,
    m.lon::double precision AS lon,
    m.lat::double precision AS lat,
    m.sig_rsrp
  FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" m
  CROSS JOIN params p
  WHERE
    m.is_compliant
    AND m.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND m.tech_norm IN ('4G','5G')
    AND m.cell_id_dec IS NOT NULL
    AND m.cell_id_dec <> 0
    -- Verified + 合法经纬度 + 非(0,0)（等价口径：Step00/Step02 的 has_gps=true）
    AND m.has_gps
    -- 口径补强：仅保留“中国境内”坐标（避免明显越界/跨洲坐标污染中心点）
    AND m.lon::double precision BETWEEN 73.0 AND 135.0
    AND m.lat::double precision BETWEEN 3.0 AND 54.0
    AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR m.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR m.operator_id_raw = p.smoke_operator_id_raw)
),
gps_points_lac_final AS (
  SELECT
    g.*,
    CASE
      WHEN tl.lac_dec IS NOT NULL THEN g.lac_dec
      ELSE mu.lac_dec_from_map
    END AS lac_dec_final
  FROM gps_points_raw g
  LEFT JOIN trusted_lac tl
    ON g.operator_id_raw=tl.operator_id_raw
   AND g.tech_norm=tl.tech_norm
   AND g.lac_dec=tl.lac_dec
  LEFT JOIN map_unique mu
    ON g.operator_id_raw=mu.operator_id_raw
   AND g.tech_norm=mu.tech_norm
   AND g.cell_id_dec=mu.cell_id_dec
  WHERE
    (
      CASE
        WHEN tl.lac_dec IS NOT NULL THEN g.lac_dec
        ELSE mu.lac_dec_from_map
      END
    ) IS NOT NULL
),
gps_points AS (
  SELECT
    g.*,
    (g.tech_norm || '|' || g.bs_id::text || '|' || g.lac_dec_final::text) AS wuli_fentong_bs_key,
    CASE
      WHEN g.sig_rsrp IN (-110, -1) OR g.sig_rsrp >= 0 THEN NULL::int
      ELSE g.sig_rsrp
    END AS sig_rsrp_clean
  FROM gps_points_lac_final g
  CROSS JOIN params p
  WHERE
    g.bs_id IS NOT NULL
    AND (
      p.shard_count <= 1
      OR ((mod(hashtextextended((g.tech_norm || '|' || g.bs_id::text || '|' || g.lac_dec_final::text), 0), p.shard_count) + p.shard_count) % p.shard_count) = p.shard_id
    )
),
gps_bucket_stats AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    count(DISTINCT (g.operator_id_raw, g.cell_id_dec))::int AS gps_valid_cell_cnt,
    count(*)::bigint AS gps_valid_point_cnt
  FROM gps_points g
  GROUP BY 1,2,3,4
),
bucket_base AS (
  SELECT
    u.tech_norm,
    u.bs_id,
    u.lac_dec_final,
    u.wuli_fentong_bs_key,

    u.shared_operator_cnt,
    u.shared_operator_list,

    COALESCE(g.gps_valid_cell_cnt, 0)::int AS gps_valid_cell_cnt,
    COALESCE(g.gps_valid_point_cnt, 0)::bigint AS gps_valid_point_cnt,

    u.first_seen_ts,
    u.last_seen_ts,
    u.active_days
  FROM bucket_universe u
  LEFT JOIN gps_bucket_stats g
    ON g.tech_norm=u.tech_norm
   AND g.bs_id=u.bs_id
   AND g.lac_dec_final=u.lac_dec_final
   AND g.wuli_fentong_bs_key=u.wuli_fentong_bs_key
),
sig_meta AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    count(*) FILTER (WHERE g.sig_rsrp_clean IS NOT NULL)::int AS sig_valid_cnt
  FROM gps_points g
  GROUP BY 1,2,3,4
),
sig_policy AS (
  SELECT
    m.*,
    CASE
      WHEN m.sig_valid_cnt >= p.signal_keep_top50_n THEN 'TOP50'
      WHEN m.sig_valid_cnt >= p.signal_keep_top20_n THEN 'TOP20'
      WHEN m.sig_valid_cnt >= 1 THEN 'TOP80PCT'
      ELSE 'ALL'
    END AS sig_keep_mode,
    CASE
      WHEN m.sig_valid_cnt >= p.signal_keep_top50_n THEN greatest(0.0, 1.0 - (p.signal_keep_top50_n::double precision / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= p.signal_keep_top20_n THEN greatest(0.0, 1.0 - (p.signal_keep_top20_n::double precision / m.sig_valid_cnt::double precision))
      WHEN m.sig_valid_cnt >= 1 THEN (1.0 - p.signal_keep_ratio_if_low_cnt) -- 0.2：丢弃最差20%，保留最好80%
      ELSE NULL::double precision
    END AS keep_percentile
  FROM sig_meta m
  CROSS JOIN params p
),
sig_hist AS (
  -- sig_rsrp_clean 是整型 dBm（负值）：用直方图替代 percentile_cont 的大排序
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.sig_rsrp_clean::int AS sig_rsrp_clean,
    count(*)::bigint AS cnt
  FROM gps_points g
  WHERE g.sig_rsrp_clean IS NOT NULL
  GROUP BY 1,2,3,4,5
),
sig_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.sig_rsrp_clean
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM sig_hist h
),
sig_target AS (
  SELECT
    p.*,
    CASE
      WHEN p.keep_percentile IS NULL OR p.sig_valid_cnt <= 0 THEN NULL::bigint
      ELSE greatest(1::bigint, ceil(p.keep_percentile * p.sig_valid_cnt::double precision)::bigint)
    END AS sig_target_pos
  FROM sig_policy p
),
sig_threshold AS (
  SELECT
    t.tech_norm,
    t.bs_id,
    t.lac_dec_final,
    t.wuli_fentong_bs_key,
    t.sig_valid_cnt,
    t.sig_keep_mode,
    t.keep_percentile,
    min(r.sig_rsrp_clean)::double precision AS sig_rsrp_threshold
  FROM sig_target t
  LEFT JOIN sig_rank r
    ON r.tech_norm=t.tech_norm
   AND r.bs_id=t.bs_id
   AND r.lac_dec_final=t.lac_dec_final
   AND r.wuli_fentong_bs_key=t.wuli_fentong_bs_key
   AND t.sig_target_pos IS NOT NULL
   AND r.cum_cnt >= t.sig_target_pos
  GROUP BY 1,2,3,4,5,6,7
),
seed_points AS (
  SELECT
    g.*,
    st.sig_keep_mode,
    st.sig_valid_cnt,
    st.sig_rsrp_threshold,
    CASE
      WHEN st.sig_keep_mode = 'ALL' THEN true
      WHEN st.sig_rsrp_threshold IS NULL THEN false
      ELSE (g.sig_rsrp_clean IS NOT NULL AND g.sig_rsrp_clean >= st.sig_rsrp_threshold)
    END AS is_in_signal_seed
  FROM gps_points g
  LEFT JOIN sig_threshold st
    ON st.tech_norm=g.tech_norm
   AND st.bs_id=g.bs_id
   AND st.lac_dec_final=g.lac_dec_final
   AND st.wuli_fentong_bs_key=g.wuli_fentong_bs_key
),
seed_points_binned AS (
  SELECT
    s.*,
    round(s.lon * p.center_bin_scale)::int AS lon_bin,
    round(s.lat * p.center_bin_scale)::int AS lat_bin
  FROM seed_points s
  CROSS JOIN params p
),
center_init_all_lon_hist AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.lon_bin,
    count(*)::bigint AS cnt
  FROM seed_points_binned g
  GROUP BY 1,2,3,4,5
),
center_init_all_lon_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.lon_bin
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM center_init_all_lon_hist h
),
center_init_all_lat_hist AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.lat_bin,
    count(*)::bigint AS cnt
  FROM seed_points_binned g
  GROUP BY 1,2,3,4,5
),
center_init_all_lat_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.lat_bin
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM center_init_all_lat_hist h
),
center_init_all_lon AS (
  SELECT
    lo.tech_norm,
    lo.bs_id,
    lo.lac_dec_final,
    lo.wuli_fentong_bs_key,
    max(lo.total_cnt)::int AS all_point_cnt,
    ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ((lo.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS center_lon_all
  FROM center_init_all_lon_rank lo
  CROSS JOIN params p
  GROUP BY 1,2,3,4, p.center_bin_scale
),
center_init_all_lat AS (
  SELECT
    la.tech_norm,
    la.bs_id,
    la.lac_dec_final,
    la.wuli_fentong_bs_key,
    ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ((la.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS center_lat_all
  FROM center_init_all_lat_rank la
  CROSS JOIN params p
  GROUP BY 1,2,3,4, p.center_bin_scale
),
center_init_all AS (
  SELECT
    lo.tech_norm,
    lo.bs_id,
    lo.lac_dec_final,
    lo.wuli_fentong_bs_key,
    lo.all_point_cnt,
    lo.center_lon_all,
    la.center_lat_all
  FROM center_init_all_lon lo
  JOIN center_init_all_lat la
    ON la.tech_norm=lo.tech_norm
   AND la.bs_id=lo.bs_id
   AND la.lac_dec_final=lo.lac_dec_final
   AND la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
),
center_init_sig_lon_hist AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.lon_bin,
    count(*)::bigint AS cnt
  FROM seed_points_binned g
  WHERE g.is_in_signal_seed
  GROUP BY 1,2,3,4,5
),
center_init_sig_lon_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.lon_bin
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM center_init_sig_lon_hist h
),
center_init_sig_lat_hist AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.lat_bin,
    count(*)::bigint AS cnt
  FROM seed_points_binned g
  WHERE g.is_in_signal_seed
  GROUP BY 1,2,3,4,5
),
center_init_sig_lat_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.lat_bin
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM center_init_sig_lat_hist h
),
center_init_sig_lon AS (
  SELECT
    lo.tech_norm,
    lo.bs_id,
    lo.lac_dec_final,
    lo.wuli_fentong_bs_key,
    max(lo.total_cnt)::int AS sig_point_cnt,
    ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ((lo.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS center_lon_sig
  FROM center_init_sig_lon_rank lo
  CROSS JOIN params p
  GROUP BY 1,2,3,4, p.center_bin_scale
),
center_init_sig_lat AS (
  SELECT
    la.tech_norm,
    la.bs_id,
    la.lac_dec_final,
    la.wuli_fentong_bs_key,
    ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ((la.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS center_lat_sig
  FROM center_init_sig_lat_rank la
  CROSS JOIN params p
  GROUP BY 1,2,3,4, p.center_bin_scale
),
center_init_sig AS (
  SELECT
    lo.tech_norm,
    lo.bs_id,
    lo.lac_dec_final,
    lo.wuli_fentong_bs_key,
    lo.sig_point_cnt,
    lo.center_lon_sig,
    la.center_lat_sig
  FROM center_init_sig_lon lo
  JOIN center_init_sig_lat la
    ON la.tech_norm=lo.tech_norm
   AND la.bs_id=lo.bs_id
   AND la.lac_dec_final=lo.lac_dec_final
   AND la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
),
center_init AS (
  SELECT
    a.tech_norm,
    a.bs_id,
    a.lac_dec_final,
    a.wuli_fentong_bs_key,
    CASE
      WHEN coalesce(s.sig_point_cnt, 0) >= p.signal_min_points_for_signal_center THEN s.center_lon_sig
      ELSE a.center_lon_all
    END AS center_lon_init,
    CASE
      WHEN coalesce(s.sig_point_cnt, 0) >= p.signal_min_points_for_signal_center THEN s.center_lat_sig
      ELSE a.center_lat_all
    END AS center_lat_init
  FROM center_init_all a
  LEFT JOIN center_init_sig s
    ON s.tech_norm=a.tech_norm
   AND s.bs_id=a.bs_id
   AND s.lac_dec_final=a.lac_dec_final
   AND s.wuli_fentong_bs_key=a.wuli_fentong_bs_key
  CROSS JOIN params p
),
point_dist_init AS (
  SELECT
    g.tech_norm,
    g.bs_id,
    g.lac_dec_final,
    g.wuli_fentong_bs_key,
    g.operator_id_raw,
    g.cell_id_dec,
    g.lon,
    g.lat,
    g.sig_rsrp_clean,
    g.is_in_signal_seed,
    c.center_lon_init,
    c.center_lat_init,
    CASE
      WHEN c.center_lon_init IS NULL OR c.center_lat_init IS NULL THEN NULL::double precision
      ELSE
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(g.lat - c.center_lat_init) / 2.0), 2)
            + cos(radians(c.center_lat_init)) * cos(radians(g.lat))
              * power(sin(radians(g.lon - c.center_lon_init) / 2.0), 2)
          )
        )
    END AS dist_m_init
  FROM seed_points g
  JOIN center_init c
    ON c.tech_norm=g.tech_norm
   AND c.bs_id=g.bs_id
   AND c.lac_dec_final=g.lac_dec_final
   AND c.wuli_fentong_bs_key=g.wuli_fentong_bs_key
),
metric_init AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    max(dist_m_init) AS gps_max_dist_m_init
  FROM point_dist_init
  WHERE dist_m_init IS NOT NULL
  GROUP BY 1,2,3,4
),
point_keep_flag AS (
  SELECT
    d.*,
    m.gps_max_dist_m_init,
    CASE
      WHEN m.gps_max_dist_m_init IS NULL THEN true
      WHEN m.gps_max_dist_m_init <= p.outlier_remove_if_dist_m_gt THEN true
      ELSE (d.dist_m_init <= p.outlier_remove_if_dist_m_gt)
    END AS is_kept
  FROM point_dist_init d
  JOIN metric_init m
    ON m.tech_norm=d.tech_norm
   AND m.bs_id=d.bs_id
   AND m.lac_dec_final=d.lac_dec_final
   AND m.wuli_fentong_bs_key=d.wuli_fentong_bs_key
  CROSS JOIN params p
),
kept_stats AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    count(*) filter (where is_kept)::bigint AS kept_point_cnt,
    count(*) filter (where not is_kept)::bigint AS removed_point_cnt,
    count(DISTINCT (operator_id_raw, cell_id_dec)) filter (where is_kept)::int AS kept_cell_cnt
  FROM point_keep_flag
  GROUP BY 1,2,3,4
),
point_after AS (
  SELECT
    p.*,
    CASE
      WHEN ks.kept_point_cnt > 0 THEN p.is_kept
      ELSE true
    END AS is_kept_effective
  FROM point_keep_flag p
  JOIN kept_stats ks
    ON ks.tech_norm=p.tech_norm
   AND ks.bs_id=p.bs_id
   AND ks.lac_dec_final=p.lac_dec_final
   AND ks.wuli_fentong_bs_key=p.wuli_fentong_bs_key
),
center_final AS (
  WITH
  all_center_lon_hist AS (
    SELECT
      a.tech_norm,
      a.bs_id,
      a.lac_dec_final,
      a.wuli_fentong_bs_key,
      round(a.lon * p.center_bin_scale)::int AS lon_bin,
      count(*)::bigint AS cnt
    FROM point_after a
    CROSS JOIN params p
    WHERE a.is_kept_effective
    GROUP BY 1,2,3,4,5
  ),
  all_center_lon_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
        ORDER BY h.lon_bin
      ) AS cum_cnt,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ) AS total_cnt
    FROM all_center_lon_hist h
  ),
  all_center_lat_hist AS (
    SELECT
      a.tech_norm,
      a.bs_id,
      a.lac_dec_final,
      a.wuli_fentong_bs_key,
      round(a.lat * p.center_bin_scale)::int AS lat_bin,
      count(*)::bigint AS cnt
    FROM point_after a
    CROSS JOIN params p
    WHERE a.is_kept_effective
    GROUP BY 1,2,3,4,5
  ),
  all_center_lat_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
        ORDER BY h.lat_bin
      ) AS cum_cnt,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ) AS total_cnt
    FROM all_center_lat_hist h
  ),
  all_center_lon AS (
    SELECT
      lo.tech_norm,
      lo.bs_id,
      lo.lac_dec_final,
      lo.wuli_fentong_bs_key,
      max(lo.total_cnt)::int AS all_kept_cnt,
      ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ((lo.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS bs_center_lon_all
    FROM all_center_lon_rank lo
    CROSS JOIN params p
    GROUP BY 1,2,3,4, p.center_bin_scale
  ),
  all_center_lat AS (
    SELECT
      la.tech_norm,
      la.bs_id,
      la.lac_dec_final,
      la.wuli_fentong_bs_key,
      ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ((la.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS bs_center_lat_all
    FROM all_center_lat_rank la
    CROSS JOIN params p
    GROUP BY 1,2,3,4, p.center_bin_scale
  ),
  all_center AS (
    SELECT
      lo.tech_norm,
      lo.bs_id,
      lo.lac_dec_final,
      lo.wuli_fentong_bs_key,
      lo.all_kept_cnt,
      lo.bs_center_lon_all,
      la.bs_center_lat_all
    FROM all_center_lon lo
    JOIN all_center_lat la
      ON la.tech_norm=lo.tech_norm
     AND la.bs_id=lo.bs_id
     AND la.lac_dec_final=lo.lac_dec_final
     AND la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
  ),
  sig_center_lon_hist AS (
    SELECT
      a.tech_norm,
      a.bs_id,
      a.lac_dec_final,
      a.wuli_fentong_bs_key,
      round(a.lon * p.center_bin_scale)::int AS lon_bin,
      count(*)::bigint AS cnt
    FROM point_after a
    CROSS JOIN params p
    WHERE a.is_kept_effective AND a.is_in_signal_seed
    GROUP BY 1,2,3,4,5
  ),
  sig_center_lon_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
        ORDER BY h.lon_bin
      ) AS cum_cnt,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ) AS total_cnt
    FROM sig_center_lon_hist h
  ),
  sig_center_lat_hist AS (
    SELECT
      a.tech_norm,
      a.bs_id,
      a.lac_dec_final,
      a.wuli_fentong_bs_key,
      round(a.lat * p.center_bin_scale)::int AS lat_bin,
      count(*)::bigint AS cnt
    FROM point_after a
    CROSS JOIN params p
    WHERE a.is_kept_effective AND a.is_in_signal_seed
    GROUP BY 1,2,3,4,5
  ),
  sig_center_lat_rank AS (
    SELECT
      h.*,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
        ORDER BY h.lat_bin
      ) AS cum_cnt,
      sum(h.cnt) OVER (
        PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ) AS total_cnt
    FROM sig_center_lat_hist h
  ),
  sig_center_lon AS (
    SELECT
      lo.tech_norm,
      lo.bs_id,
      lo.lac_dec_final,
      lo.wuli_fentong_bs_key,
      max(lo.total_cnt)::int AS sig_kept_cnt,
      ((min(lo.lon_bin) FILTER (WHERE lo.cum_cnt >= ((lo.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS bs_center_lon_sig
    FROM sig_center_lon_rank lo
    CROSS JOIN params p
    GROUP BY 1,2,3,4, p.center_bin_scale
  ),
  sig_center_lat AS (
    SELECT
      la.tech_norm,
      la.bs_id,
      la.lac_dec_final,
      la.wuli_fentong_bs_key,
      ((min(la.lat_bin) FILTER (WHERE la.cum_cnt >= ((la.total_cnt + 1) / 2)))::double precision) / p.center_bin_scale::double precision AS bs_center_lat_sig
    FROM sig_center_lat_rank la
    CROSS JOIN params p
    GROUP BY 1,2,3,4, p.center_bin_scale
  ),
  sig_center AS (
    SELECT
      lo.tech_norm,
      lo.bs_id,
      lo.lac_dec_final,
      lo.wuli_fentong_bs_key,
      lo.sig_kept_cnt,
      lo.bs_center_lon_sig,
      la.bs_center_lat_sig
    FROM sig_center_lon lo
    JOIN sig_center_lat la
      ON la.tech_norm=lo.tech_norm
     AND la.bs_id=lo.bs_id
     AND la.lac_dec_final=lo.lac_dec_final
     AND la.wuli_fentong_bs_key=lo.wuli_fentong_bs_key
  )
  SELECT
    ac.tech_norm,
    ac.bs_id,
    ac.lac_dec_final,
    ac.wuli_fentong_bs_key,
    max(ks.removed_point_cnt)::bigint AS outlier_removed_cnt,
    CASE
      WHEN coalesce(sc.sig_kept_cnt, 0) >= p.signal_min_points_for_signal_center THEN sc.bs_center_lon_sig
      ELSE ac.bs_center_lon_all
    END AS bs_center_lon,
    CASE
      WHEN coalesce(sc.sig_kept_cnt, 0) >= p.signal_min_points_for_signal_center THEN sc.bs_center_lat_sig
      ELSE ac.bs_center_lat_all
    END AS bs_center_lat
  FROM all_center ac
  LEFT JOIN sig_center sc
    ON sc.tech_norm=ac.tech_norm
   AND sc.bs_id=ac.bs_id
   AND sc.lac_dec_final=ac.lac_dec_final
   AND sc.wuli_fentong_bs_key=ac.wuli_fentong_bs_key
  JOIN kept_stats ks
    ON ks.tech_norm=ac.tech_norm
   AND ks.bs_id=ac.bs_id
   AND ks.lac_dec_final=ac.lac_dec_final
   AND ks.wuli_fentong_bs_key=ac.wuli_fentong_bs_key
  CROSS JOIN params p
  GROUP BY
    ac.tech_norm,
    ac.bs_id,
    ac.lac_dec_final,
    ac.wuli_fentong_bs_key,
    ac.bs_center_lon_all,
    ac.bs_center_lat_all,
    sc.sig_kept_cnt,
    sc.bs_center_lon_sig,
    sc.bs_center_lat_sig,
    p.signal_min_points_for_signal_center
),
point_dist_final AS (
  SELECT
    a.tech_norm,
    a.bs_id,
    a.lac_dec_final,
    a.wuli_fentong_bs_key,
    a.cell_id_dec,
    a.lon,
    a.lat,
    c.bs_center_lon,
    c.bs_center_lat,
    c.outlier_removed_cnt,
    CASE
      WHEN c.bs_center_lon IS NULL OR c.bs_center_lat IS NULL THEN NULL::double precision
      ELSE
        6371000.0 * 2.0 * asin(
          sqrt(
            power(sin(radians(a.lat - c.bs_center_lat) / 2.0), 2)
            + cos(radians(c.bs_center_lat)) * cos(radians(a.lat))
              * power(sin(radians(a.lon - c.bs_center_lon) / 2.0), 2)
          )
        )
    END AS dist_m
  FROM point_after a
  JOIN center_final c
    ON c.tech_norm=a.tech_norm
   AND c.bs_id=a.bs_id
   AND c.lac_dec_final=a.lac_dec_final
   AND c.wuli_fentong_bs_key=a.wuli_fentong_bs_key
  WHERE a.is_kept_effective
),
dist_hist AS (
  SELECT
    d.tech_norm,
    d.bs_id,
    d.lac_dec_final,
    d.wuli_fentong_bs_key,
    (floor(d.dist_m / p.dist_bin_m::double precision)::bigint * p.dist_bin_m::bigint)::bigint AS dist_bin_m,
    count(*)::bigint AS cnt
  FROM point_dist_final d
  CROSS JOIN params p
  WHERE d.dist_m IS NOT NULL
  GROUP BY 1,2,3,4,5
),
dist_rank AS (
  SELECT
    h.*,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
      ORDER BY h.dist_bin_m
    ) AS cum_cnt,
    sum(h.cnt) OVER (
      PARTITION BY h.tech_norm, h.bs_id, h.lac_dec_final, h.wuli_fentong_bs_key
    ) AS total_cnt
  FROM dist_hist h
),
dist_pcts AS (
  SELECT
    r.tech_norm,
    r.bs_id,
    r.lac_dec_final,
    r.wuli_fentong_bs_key,
    ((min(r.dist_bin_m) FILTER (WHERE r.cum_cnt >= ((r.total_cnt + 1) / 2)))::double precision) AS gps_p50_dist_m,
    ((min(r.dist_bin_m) FILTER (WHERE r.cum_cnt >= ((r.total_cnt * 9 + 9) / 10)))::double precision) AS gps_p90_dist_m
  FROM dist_rank r
  GROUP BY 1,2,3,4
),
metric_final_base AS (
  SELECT
    tech_norm,
    bs_id,
    lac_dec_final,
    wuli_fentong_bs_key,
    max(outlier_removed_cnt)::bigint AS outlier_removed_cnt,
    max(bs_center_lon) AS bs_center_lon,
    max(bs_center_lat) AS bs_center_lat,
    max(dist_m) AS gps_max_dist_m
  FROM point_dist_final
  WHERE dist_m IS NOT NULL
  GROUP BY 1,2,3,4
),
metric_final AS (
  SELECT
    b.tech_norm,
    b.bs_id,
    b.lac_dec_final,
    b.wuli_fentong_bs_key,
    b.outlier_removed_cnt,
    b.bs_center_lon,
    b.bs_center_lat,
    p.gps_p50_dist_m,
    p.gps_p90_dist_m,
    b.gps_max_dist_m
  FROM metric_final_base b
  LEFT JOIN dist_pcts p
    ON p.tech_norm=b.tech_norm
   AND p.bs_id=b.bs_id
   AND p.lac_dec_final=b.lac_dec_final
   AND p.wuli_fentong_bs_key=b.wuli_fentong_bs_key
),
anomaly_cell_cnt AS (
  SELECT
    s.tech_norm,
    s.bs_id,
    s.lac_dec_final,
    (s.tech_norm || '|' || s.bs_id::text || '|' || s.lac_dec_final::text) AS wuli_fentong_bs_key,
    count(DISTINCT (s.operator_id_raw, s.cell_id_dec))::bigint AS anomaly_cell_cnt
  FROM public."Y_codex_Layer2_Step06_L0_Lac_Filtered" s
  CROSS JOIN params p
  JOIN public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" a
    ON a.operator_id_raw=s.operator_id_raw
   AND a.tech_norm=s.tech_norm
   AND a.cell_id_dec=s.cell_id_dec
  WHERE
    s.tech_norm IN ('4G','5G')
    AND s.operator_id_raw IN ('46000','46001','46011','46015','46020')
    AND s.bs_id IS NOT NULL
    AND s.lac_dec_final IS NOT NULL
    AND s.cell_id_dec IS NOT NULL
    AND (
      p.shard_count <= 1
      OR ((mod(hashtextextended((s.tech_norm || '|' || s.bs_id::text || '|' || s.lac_dec_final::text), 0), p.shard_count) + p.shard_count) % p.shard_count) = p.shard_id
    )
    AND (NOT p.is_smoke OR p.smoke_report_date IS NULL OR s.report_date = p.smoke_report_date)
    AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR s.operator_id_raw = p.smoke_operator_id_raw)
  GROUP BY 1,2,3,4
)
SELECT
  b.tech_norm,
  b.bs_id,
  b.wuli_fentong_bs_key,
  b.lac_dec_final,

  -- 共建/共用
  b.shared_operator_cnt,
  b.shared_operator_list,
  (b.shared_operator_cnt > 1) AS is_multi_operator_shared,

  -- GPS 有效性分级（按“基站下有效 GPS 的 cell 来源数量”）
  -- 注意：若触发漂移点剔除，则 cell_cnt/point_cnt 基于“剔除后保留点”计算
  COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) AS gps_valid_cell_cnt,
  COALESCE(ks.kept_point_cnt, b.gps_valid_point_cnt) AS gps_valid_point_cnt,
  CASE
    WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN 'Unusable'
    WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 1 THEN 'Risk'
    ELSE 'Usable'
  END AS gps_valid_level,

  -- 中心点与离散度（Unusable 置空）
  CASE WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN NULL ELSE m.bs_center_lon END AS bs_center_lon,
  CASE WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN NULL ELSE m.bs_center_lat END AS bs_center_lat,
  CASE WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN NULL ELSE m.gps_p50_dist_m END AS gps_p50_dist_m,
  CASE WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN NULL ELSE m.gps_p90_dist_m END AS gps_p90_dist_m,
  CASE WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) = 0 THEN NULL ELSE m.gps_max_dist_m END AS gps_max_dist_m,
  COALESCE(m.outlier_removed_cnt, 0) AS outlier_removed_cnt,

  -- 风险/碰撞
  CASE
    WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) <= 1 THEN 0
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0 THEN 1
    WHEN m.gps_p90_dist_m IS NULL THEN 0
    WHEN m.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN 1
    ELSE 0
  END::int AS is_collision_suspect,
  CASE
    WHEN COALESCE(ks.kept_cell_cnt, b.gps_valid_cell_cnt) <= 1 THEN NULL
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0 AND m.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN E'STEP05_MULTI_LAC_CELL\\073GPS_SCATTER_P90_GT_THRESHOLD'
    WHEN COALESCE(a.anomaly_cell_cnt, 0) > 0 THEN 'STEP05_MULTI_LAC_CELL'
    WHEN m.gps_p90_dist_m > p.collision_if_p90_dist_m_gt THEN 'GPS_SCATTER_P90_GT_THRESHOLD'
    ELSE NULL
  END AS collision_reason,
  COALESCE(a.anomaly_cell_cnt, 0) AS anomaly_cell_cnt,

  -- 覆盖时间画像（来自 Step06）
  b.first_seen_ts,
  b.last_seen_ts,
  b.active_days
FROM bucket_base b
LEFT JOIN metric_final m
  ON m.tech_norm=b.tech_norm
 AND m.bs_id=b.bs_id
 AND m.lac_dec_final=b.lac_dec_final
 AND m.wuli_fentong_bs_key=b.wuli_fentong_bs_key
LEFT JOIN kept_stats ks
  ON ks.tech_norm=b.tech_norm
 AND ks.bs_id=b.bs_id
 AND ks.lac_dec_final=b.lac_dec_final
 AND ks.wuli_fentong_bs_key=b.wuli_fentong_bs_key
LEFT JOIN anomaly_cell_cnt a
  ON a.tech_norm=b.tech_norm
 AND a.bs_id=b.bs_id
 AND a.lac_dec_final=b.lac_dec_final
 AND a.wuli_fentong_bs_key=b.wuli_fentong_bs_key
CROSS JOIN params p;

ANALYZE public."Y_codex_Layer3_Step30_Master_BS_Library";

-- Step30 必须输出的统计表：GPS 可用性分级分布（按运营商/tech）
-- 说明：Step30 主表是“物理分桶”口径；统计按运营商切片时需要拆 shared_operator_list。
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
    round(b.bs_cnt::numeric / nullif(sum(b.bs_cnt) OVER (PARTITION BY b.tech_norm, b.operator_id_raw), 0), 8) AS bs_pct
  FROM base b
)
SELECT * FROM scored;

ANALYZE public."Y_codex_Layer3_Step30_Gps_Level_Stats";
