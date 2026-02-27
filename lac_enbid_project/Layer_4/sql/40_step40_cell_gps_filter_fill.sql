-- Layer_4 Step40：基于 BS 库对 Layer0 明细做 GPS 过滤 + 按 BS 回填（严重碰撞桶仍回填但强标注）
--
-- 输入：
-- - public."Y_codex_Layer0_Lac"（原始明细）
-- - public."Y_codex_Layer3_Step30_Master_BS_Library"（可信 BS 库：中心点 + 风险/碰撞/共建标记）
-- - public."Y_codex_Layer2_Step04_Master_Lac_Lib"（可信 LAC 白名单，用于 lac_dec_final）
-- - public."Y_codex_Layer2_Step05_CellId_Stats_DB"（cell->lac 映射证据，用于 lac_dec_final）
--
-- 输出：
-- - public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"（或 shard 表）
-- - public."Y_codex_Layer4_Step40_Gps_Metrics"（或 shard 表）
--
-- 关键口径（城市模式默认）：
-- - 4G dist_threshold_m=1000；5G dist_threshold_m=500
-- - 严重碰撞桶：仍回填 GPS，但强标注 is_severe_collision/collision_reason/gps_source（用于可见性与下游降权/过滤）
--
-- 性能说明：
-- - 支持按 BS 分片（bs_shard_key=tech_norm|bs_id_final；codex.shard_count/shard_id），便于按 BS 并行处理。

/* ============================================================================
 * 会话级性能参数（建议按机器调整）
 * ==========================================================================*/
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET maintenance_work_mem = '2GB';
SET max_parallel_workers_per_gather = 8;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;

DO $$
DECLARE
  shard_count int := COALESCE(NULLIF(current_setting('codex.shard_count', true), '')::int, 1);
  shard_id int := COALESCE(NULLIF(current_setting('codex.shard_id', true), '')::int, 0);
  is_smoke boolean := COALESCE(NULLIF(current_setting('codex.is_smoke', true), '')::boolean, false);
  smoke_date date := COALESCE(NULLIF(current_setting('codex.smoke_date', true), '')::date, date '2025-12-01');
  smoke_operator text := COALESCE(NULLIF(current_setting('codex.smoke_operator_id_raw', true), ''), '46000');

  out_table text := CASE
    WHEN shard_count > 1 THEN format('Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__shard_%s', lpad(shard_id::text, 2, '0'))
    ELSE 'Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill'
  END;
  metric_table text := CASE
    WHEN shard_count > 1 THEN format('Y_codex_Layer4_Step40_Gps_Metrics__shard_%s', lpad(shard_id::text, 2, '0'))
    ELSE 'Y_codex_Layer4_Step40_Gps_Metrics'
  END;
  idx_key_name text := CASE
    WHEN shard_count > 1 THEN format('idx_l4_s40_key_s%s', lpad(shard_id::text, 2, '0'))
    ELSE 'idx_l4_s40_key'
  END;
  idx_cell_ts_name text := CASE
    WHEN shard_count > 1 THEN format('idx_l4_s40_cell_ts_s%s', lpad(shard_id::text, 2, '0'))
    ELSE 'idx_l4_s40_cell_ts'
  END;
BEGIN
  EXECUTE format('DROP TABLE IF EXISTS public.%I', out_table);
  EXECUTE format($sql$
    CREATE TABLE public.%I AS
    WITH
    params AS (
      SELECT
        %L::boolean AS is_smoke,
        %L::date AS smoke_date,
        %L::text AS smoke_operator_id_raw,
        %s::int AS shard_count,
        %s::int AS shard_id,

        -- 城市阈值（本轮固定，未来按 lac 放大/缩小）
        1000.0::double precision AS city_dist_threshold_4g_m,
        500.0::double precision AS city_dist_threshold_5g_m,
        true::boolean AS is_city_mode,

        -- 中国粗框（与 Layer_3 一致）
        73.0::double precision AS china_lon_min,
        135.0::double precision AS china_lon_max,
        3.0::double precision AS china_lat_min,
        54.0::double precision AS china_lat_max
    ),
    trusted_lac AS (
      SELECT operator_id_raw, tech_norm, lac_dec
      FROM public."Y_codex_Layer2_Step04_Master_Lac_Lib"
      WHERE is_trusted_lac
    ),
    map_unique AS (
      SELECT
        operator_id_raw,
        tech_norm,
        cell_id_dec,
        CASE WHEN min(lac_dec) = max(lac_dec) THEN min(lac_dec) END AS lac_dec_from_map
      FROM public."Y_codex_Layer2_Step05_CellId_Stats_DB"
      GROUP BY 1,2,3
    ),
    base AS (
      SELECT
        t.*,
        t."运营商id"::text AS operator_id_raw,
        t.tech::text AS tech_norm,
        COALESCE(
          t.bs_id,
          CASE
            WHEN t.tech='4G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 256.0)::bigint
            WHEN t.tech='5G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 4096.0)::bigint
          END
        ) AS bs_id_final,
        CASE
          WHEN tl.lac_dec IS NOT NULL THEN t.lac_dec
          ELSE mu.lac_dec_from_map
        END AS lac_dec_final
      FROM public."Y_codex_Layer0_Lac" t
      CROSS JOIN params p
      LEFT JOIN trusted_lac tl
        ON tl.operator_id_raw=t."运营商id"::text
       AND tl.tech_norm=t.tech::text
       AND tl.lac_dec=t.lac_dec
      LEFT JOIN map_unique mu
        ON mu.operator_id_raw=t."运营商id"::text
       AND mu.tech_norm=t.tech::text
       AND mu.cell_id_dec=t.cell_id_dec
      WHERE
        t.tech IN ('4G','5G')
        AND t."运营商id" IN ('46000','46001','46011','46015','46020')
        AND t.cell_id_dec IS NOT NULL AND t.cell_id_dec > 0
        AND COALESCE(
              t.bs_id,
              CASE
                WHEN t.tech='4G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 256.0)::bigint
                WHEN t.tech='5G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 4096.0)::bigint
              END
            ) IS NOT NULL
        AND COALESCE(
              t.bs_id,
              CASE
                WHEN t.tech='4G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 256.0)::bigint
                WHEN t.tech='5G' AND t.cell_id_dec IS NOT NULL THEN floor(t.cell_id_dec / 4096.0)::bigint
              END
            ) > 0
        AND (NOT p.is_smoke OR p.smoke_date IS NULL OR t.ts_std::date = p.smoke_date)
        AND (NOT p.is_smoke OR p.smoke_operator_id_raw IS NULL OR t."运营商id"::text = p.smoke_operator_id_raw)
    ),
    keyed AS (
      SELECT
        b.*,
        CASE
          WHEN b.lac_dec_final IS NOT NULL THEN concat_ws('|', b.tech_norm, b.bs_id_final::text, b.lac_dec_final::text)
          ELSE NULL::text
        END AS wuli_fentong_bs_key,
        concat_ws('|', b.tech_norm, b.bs_id_final::text) AS bs_shard_key
      FROM base b
      CROSS JOIN params p
      WHERE
        p.shard_count <= 1
        OR ((mod(hashtextextended(concat_ws('|', b.tech_norm, b.bs_id_final::text), 0), p.shard_count) + p.shard_count) %% p.shard_count) = p.shard_id
    ),
    joined AS (
      SELECT
        k.*,
        bs.gps_valid_level,
        bs.bs_center_lon,
        bs.bs_center_lat,
        bs.is_collision_suspect,
        bs.collision_reason,
        bs.gps_valid_point_cnt AS bs_gps_valid_point_cnt,
        bs.gps_p50_dist_m AS bs_gps_p50_dist_m,
        bs.anomaly_cell_cnt AS bs_anomaly_cell_cnt,
        bs.is_multi_operator_shared,
        bs.shared_operator_list,
        bs.shared_operator_cnt
      FROM keyed k
      LEFT JOIN public."Y_codex_Layer3_Step30_Master_BS_Library" bs
        ON bs.tech_norm = k.tech_norm
       AND bs.bs_id = k.bs_id_final
       AND bs.wuli_fentong_bs_key = k.wuli_fentong_bs_key
    ),
    dist_calc AS (
      SELECT
        j.*,
        CASE
          WHEN j.lon IS NULL OR j.lat IS NULL THEN false
          WHEN j.lon BETWEEN (SELECT china_lon_min FROM params) AND (SELECT china_lon_max FROM params)
           AND j.lat BETWEEN (SELECT china_lat_min FROM params) AND (SELECT china_lat_max FROM params)
          THEN true
          ELSE false
        END AS gps_in_china,
        CASE
          WHEN j.lon IS NULL OR j.lat IS NULL THEN NULL::double precision
          WHEN j.bs_center_lon IS NULL OR j.bs_center_lat IS NULL THEN NULL::double precision
          ELSE
            6371000.0 * 2.0 * asin(
              sqrt(
                power(sin(radians(j.lat - j.bs_center_lat) / 2.0), 2)
                + cos(radians(j.bs_center_lat)) * cos(radians(j.lat))
                  * power(sin(radians(j.lon - j.bs_center_lon) / 2.0), 2)
              )
            )
        END AS gps_dist_to_bs_m,
        CASE
          WHEN j.tech_norm = '4G' THEN (SELECT city_dist_threshold_4g_m FROM params)
          WHEN j.tech_norm = '5G' THEN (SELECT city_dist_threshold_5g_m FROM params)
          ELSE NULL::double precision
        END AS dist_threshold_m
      FROM joined j
    ),
    classified AS (
      SELECT
        d.*,
        CASE
          WHEN d.is_collision_suspect = 1
           AND d.gps_valid_level = 'Usable'
           AND COALESCE(d.bs_anomaly_cell_cnt, 0) = 0
           AND COALESCE(d.bs_gps_valid_point_cnt, 0) >= 50
           AND COALESCE(d.bs_gps_p50_dist_m, 0) >= 5000
          THEN true
          ELSE false
        END AS is_severe_collision,
        CASE
          WHEN d.lon IS NULL OR d.lat IS NULL THEN 'Missing'
          WHEN d.gps_in_china IS NOT TRUE THEN 'Missing'
          WHEN d.gps_dist_to_bs_m IS NOT NULL AND d.dist_threshold_m IS NOT NULL AND d.gps_dist_to_bs_m > d.dist_threshold_m THEN 'Drift'
          ELSE 'Verified'
        END AS gps_status,
        CASE WHEN d.gps_valid_level = 'Risk' THEN 1 ELSE 0 END::int AS is_from_risk_bs
      FROM dist_calc d
    ),
    fixed AS (
      SELECT
        c.*,
        c.lon AS lon_before_fix,
        c.lat AS lat_before_fix,
        CASE WHEN c.bs_id_final BETWEEN 1 AND 255 THEN true ELSE false END AS is_bs_id_lt_256,
        CASE
          WHEN c.gps_status='Verified' THEN 'keep_raw'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level IN ('Usable','Risk')
           AND c.is_severe_collision IS TRUE
          THEN 'fill_bs_severe_collision'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level='Usable'
           AND c.is_severe_collision IS NOT TRUE
          THEN 'fill_bs'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level='Risk'
          THEN 'fill_risk_bs'
          ELSE 'not_filled'
        END AS gps_fix_strategy,
        CASE
          WHEN c.gps_status='Verified' THEN c.lon
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level IN ('Usable','Risk')
          THEN c.bs_center_lon
          ELSE NULL::double precision
        END AS lon_final,
        CASE
          WHEN c.gps_status='Verified' THEN c.lat
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level IN ('Usable','Risk')
          THEN c.bs_center_lat
          ELSE NULL::double precision
        END AS lat_final,
        CASE
          WHEN c.gps_status='Verified' THEN 'Original_Verified'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level='Usable'
           AND c.is_severe_collision IS TRUE
          THEN 'Augmented_from_BS_SevereCollision'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level='Usable'
           AND c.is_severe_collision IS NOT TRUE
          THEN 'Augmented_from_BS'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level='Risk'
          THEN 'Augmented_from_Risk_BS'
          ELSE 'Not_Filled'
        END AS gps_source,
        CASE
          WHEN c.gps_status='Verified' THEN 'Verified'
          WHEN c.gps_status IN ('Missing','Drift')
           AND c.bs_center_lon IS NOT NULL AND c.bs_center_lat IS NOT NULL
           AND c.gps_valid_level IN ('Usable','Risk')
          THEN 'Verified'
          ELSE 'Missing'
        END AS gps_status_final
        -- 信号清洗：避免在 CTAS 中制造重复列名；清洗会在落表后以 UPDATE 方式执行
      FROM classified c
    )
    SELECT
      f.*
    FROM fixed f
  $sql$, out_table, is_smoke, smoke_date, smoke_operator, shard_count, shard_id);

  -- 信号清洗（最小规则：rsrp 占位值置空；其余字段后续评估）
  EXECUTE format('UPDATE public.%I SET sig_rsrp = NULL WHERE sig_rsrp IN (-110, -1) OR sig_rsrp >= 0', out_table);

  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(wuli_fentong_bs_key)', idx_key_name, out_table);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(operator_id_raw, tech_norm, cell_id_dec, ts_std)', idx_cell_ts_name, out_table);
  EXECUTE format('ANALYZE public.%I', out_table);

  EXECUTE format('DROP TABLE IF EXISTS public.%I', metric_table);
  EXECUTE format($m$
    CREATE TABLE public.%I AS
    SELECT
      max(%s)::int AS shard_count,
      max(%s)::int AS shard_id,
      count(*)::bigint AS row_cnt,
      count(*) FILTER (WHERE gps_status='Missing')::bigint AS gps_missing_cnt,
      count(*) FILTER (WHERE gps_status='Drift')::bigint AS gps_drift_cnt,
      count(*) FILTER (WHERE gps_source='Augmented_from_BS')::bigint AS gps_fill_from_bs_cnt,
      count(*) FILTER (WHERE gps_source='Augmented_from_BS_SevereCollision')::bigint AS gps_fill_from_bs_severe_collision_cnt,
      count(*) FILTER (WHERE gps_source='Augmented_from_Risk_BS')::bigint AS gps_fill_from_risk_bs_cnt,
      count(*) FILTER (WHERE gps_source='Not_Filled')::bigint AS gps_not_filled_cnt,
      count(*) FILTER (WHERE is_severe_collision IS TRUE)::bigint AS severe_collision_row_cnt,
      count(*) FILTER (WHERE is_bs_id_lt_256 IS TRUE)::bigint AS bs_id_lt_256_row_cnt,
      count(*) FILTER (WHERE bs_id_final=1)::bigint AS bs_id_eq_1_row_cnt
    FROM public.%I;
  $m$, metric_table, shard_count, shard_id, out_table);
END $$;
