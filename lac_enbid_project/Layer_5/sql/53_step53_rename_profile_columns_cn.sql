-- Layer_5 Step53：把 Layer_5 三张画像表字段改为中文表头（仅重命名，不重跑聚合）
--
-- 为什么你会看到 “字段 operator_id_raw 不存在”？
-- - 说明这张表你之前已经把列名改成中文了（operator_id_raw 已被重命名为 “运营商ID”）
-- - 本脚本已做成幂等：若旧列不存在或新列已存在，会自动跳过
--
-- 注意：
-- - 本脚本只改列名，不会修正活跃天数/百分比/小数位等“计算口径”；
--   那些需要重跑 Step50/51/52（因为是 SELECT 结果本身）。

SET statement_timeout = 0;
SET jit = off;

DO $$
DECLARE
  r record;
  t text;
BEGIN
  -- ========== LAC ==========
  t := 'Y_codex_Layer5_Lac_Profile';
  FOR r IN
    SELECT * FROM (VALUES
      ('operator_id_raw','运营商ID'),
      ('tech_norm','制式'),
      ('lac_dec_final','LAC'),
      ('row_cnt','行数'),
      ('first_cell_ts_utc','最早时间UTC'),
      ('last_cell_ts_utc','最晚时间UTC'),
      ('active_days_utc','活跃天数UTC'),
      ('distinct_bs_cnt','BS去重数'),
      ('distinct_cell_cnt','CELL去重数'),
      ('gps_present_cnt','GPS有效行数'),
      ('gps_missing_cnt','GPS缺失行数'),
      ('gps_present_ratio','GPS有效率'),
      ('center_lon','GPS中心经度'),
      ('center_lat','GPS中心纬度'),
      ('lon_min','经度最小'),
      ('lon_max','经度最大'),
      ('lat_min','纬度最小'),
      ('lat_max','纬度最大'),
      ('gps_p50_dist_m','GPS距离P50_米'),
      ('gps_p90_dist_m','GPS距离P90_米'),
      ('gps_max_dist_m','GPS距离MAX_米'),
      ('sig_rsrp_nonnull_cnt','RSRP非空行数'),
      ('sig_rsrq_nonnull_cnt','RSRQ非空行数'),
      ('sig_sinr_nonnull_cnt','SINR非空行数'),
      ('sig_rssi_nonnull_cnt','RSSI非空行数'),
      ('sig_dbm_nonnull_cnt','DBM非空行数'),
      ('sig_asu_level_nonnull_cnt','ASU_LEVEL非空行数'),
      ('sig_level_nonnull_cnt','LEVEL非空行数'),
      ('sig_ss_nonnull_cnt','SS非空行数'),
      ('sig_rsrp_nonnull_ratio','RSRP有效率'),
      ('sig_rsrq_nonnull_ratio','RSRQ有效率'),
      ('sig_sinr_nonnull_ratio','SINR有效率'),
      ('sig_dbm_nonnull_ratio','DBM有效率'),
      ('native_any_signal_row_cnt','原生有信号行数'),
      ('native_no_signal_row_cnt','原生无信号行数'),
      ('need_fill_row_cnt','需要补齐行数'),
      ('filled_row_cnt','补齐成功行数'),
      ('filled_by_cell_nearest_row_cnt','补齐_同CELL_行数'),
      ('filled_by_bs_top_cell_nearest_row_cnt','补齐_BS_TOP_行数'),
      ('fill_failed_row_cnt','补齐失败行数'),
      ('missing_field_before_sum','缺失字段数_补前合计'),
      ('missing_field_after_sum','缺失字段数_补后合计'),
      ('filled_field_sum','补齐字段数合计'),
      ('multi_operator_bs_cnt','多运营商BS去重数'),
      ('has_multi_operator_bs','多运营商BS标记'),
      ('is_low_sample','样本不足'),
      ('has_gps_profile','有GPS画像'),
      ('is_gps_unstable','GPS不稳定')
    ) AS v(old_name,new_name)
  LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.old_name
    ) AND NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.new_name
    ) THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I RENAME COLUMN %I TO %I', t, r.old_name, r.new_name);
      EXCEPTION
        WHEN undefined_table THEN
          NULL;
        WHEN undefined_column THEN
          NULL;
        WHEN duplicate_column THEN
          NULL;
      END;
    END IF;
  END LOOP;

  -- ========== BS ==========
  t := 'Y_codex_Layer5_BS_Profile';
  FOR r IN
    SELECT * FROM (VALUES
      ('operator_id_raw','运营商ID'),
      ('tech_norm','制式'),
      ('lac_dec_final','LAC'),
      ('bs_id_final','BS'),
      ('wuli_fentong_bs_key','物理分桶BS键'),
      ('row_cnt','行数'),
      ('first_cell_ts_utc','最早时间UTC'),
      ('last_cell_ts_utc','最晚时间UTC'),
      ('active_days_utc','活跃天数UTC'),
      ('distinct_cell_cnt','CELL去重数'),
      ('gps_present_cnt','GPS有效行数'),
      ('gps_missing_cnt','GPS缺失行数'),
      ('gps_present_ratio','GPS有效率'),
      ('center_lon','GPS中心经度'),
      ('center_lat','GPS中心纬度'),
      ('gps_p50_dist_m','GPS距离P50_米'),
      ('gps_p90_dist_m','GPS距离P90_米'),
      ('gps_max_dist_m','GPS距离MAX_米'),
      ('sig_rsrp_nonnull_cnt','RSRP非空行数'),
      ('sig_rsrq_nonnull_cnt','RSRQ非空行数'),
      ('sig_sinr_nonnull_cnt','SINR非空行数'),
      ('sig_rssi_nonnull_cnt','RSSI非空行数'),
      ('sig_dbm_nonnull_cnt','DBM非空行数'),
      ('sig_asu_level_nonnull_cnt','ASU_LEVEL非空行数'),
      ('sig_level_nonnull_cnt','LEVEL非空行数'),
      ('sig_ss_nonnull_cnt','SS非空行数'),
      ('sig_rsrp_nonnull_ratio','RSRP有效率'),
      ('sig_rsrq_nonnull_ratio','RSRQ有效率'),
      ('sig_sinr_nonnull_ratio','SINR有效率'),
      ('sig_dbm_nonnull_ratio','DBM有效率'),
      ('native_any_signal_row_cnt','原生有信号行数'),
      ('native_no_signal_row_cnt','原生无信号行数'),
      ('need_fill_row_cnt','需要补齐行数'),
      ('filled_row_cnt','补齐成功行数'),
      ('filled_by_cell_nearest_row_cnt','补齐_同CELL_行数'),
      ('filled_by_bs_top_cell_nearest_row_cnt','补齐_BS_TOP_行数'),
      ('fill_failed_row_cnt','补齐失败行数'),
      ('missing_field_before_sum','缺失字段数_补前合计'),
      ('missing_field_after_sum','缺失字段数_补后合计'),
      ('filled_field_sum','补齐字段数合计'),
      ('is_bs_id_lt_256','BS_ID<256标记'),
      ('is_multi_operator_shared','多运营商共享标记'),
      ('shared_operator_cnt','共享运营商数'),
      ('shared_operator_list','共享运营商列表'),
      ('is_low_sample','样本不足'),
      ('has_gps_profile','有GPS画像'),
      ('is_gps_unstable','GPS不稳定')
    ) AS v(old_name,new_name)
  LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.old_name
    ) AND NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.new_name
    ) THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I RENAME COLUMN %I TO %I', t, r.old_name, r.new_name);
      EXCEPTION
        WHEN undefined_table THEN
          NULL;
        WHEN undefined_column THEN
          NULL;
        WHEN duplicate_column THEN
          NULL;
      END;
    END IF;
  END LOOP;

  -- ========== CELL ==========
  t := 'Y_codex_Layer5_Cell_Profile';
  FOR r IN
    SELECT * FROM (VALUES
      ('operator_id_raw','运营商ID'),
      ('tech_norm','制式'),
      ('lac_dec_final','LAC'),
      ('bs_id_final','BS'),
      ('cell_id_dec','CELL'),
      ('row_cnt','行数'),
      ('first_cell_ts_utc','最早时间UTC'),
      ('last_cell_ts_utc','最晚时间UTC'),
      ('active_days_utc','活跃天数UTC'),
      ('gps_present_cnt','GPS有效行数'),
      ('gps_missing_cnt','GPS缺失行数'),
      ('gps_present_ratio','GPS有效率'),
      ('center_lon','GPS中心经度'),
      ('center_lat','GPS中心纬度'),
      ('gps_p50_dist_m','GPS距离P50_米'),
      ('gps_p90_dist_m','GPS距离P90_米'),
      ('gps_max_dist_m','GPS距离MAX_米'),
      ('sig_rsrp_nonnull_cnt','RSRP非空行数'),
      ('sig_rsrq_nonnull_cnt','RSRQ非空行数'),
      ('sig_sinr_nonnull_cnt','SINR非空行数'),
      ('sig_rssi_nonnull_cnt','RSSI非空行数'),
      ('sig_dbm_nonnull_cnt','DBM非空行数'),
      ('sig_asu_level_nonnull_cnt','ASU_LEVEL非空行数'),
      ('sig_level_nonnull_cnt','LEVEL非空行数'),
      ('sig_ss_nonnull_cnt','SS非空行数'),
      ('sig_rsrp_nonnull_ratio','RSRP有效率'),
      ('sig_rsrq_nonnull_ratio','RSRQ有效率'),
      ('sig_sinr_nonnull_ratio','SINR有效率'),
      ('sig_dbm_nonnull_ratio','DBM有效率'),
      ('native_any_signal_row_cnt','原生有信号行数'),
      ('native_no_signal_row_cnt','原生无信号行数'),
      ('need_fill_row_cnt','需要补齐行数'),
      ('filled_row_cnt','补齐成功行数'),
      ('filled_by_cell_nearest_row_cnt','补齐_同CELL_行数'),
      ('filled_by_bs_top_cell_nearest_row_cnt','补齐_BS_TOP_行数'),
      ('fill_failed_row_cnt','补齐失败行数'),
      ('missing_field_before_sum','缺失字段数_补前合计'),
      ('missing_field_after_sum','缺失字段数_补后合计'),
      ('filled_field_sum','补齐字段数合计'),
      ('is_bs_id_lt_256','BS_ID<256标记'),
      ('is_multi_operator_shared','多运营商共享标记'),
      ('shared_operator_cnt','共享运营商数'),
      ('shared_operator_list','共享运营商列表'),
      ('is_low_sample','样本不足'),
      ('has_gps_profile','有GPS画像'),
      ('is_gps_unstable','GPS不稳定')
    ) AS v(old_name,new_name)
  LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.old_name
    ) AND NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name=r.new_name
    ) THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I RENAME COLUMN %I TO %I', t, r.old_name, r.new_name);
      EXCEPTION
        WHEN undefined_table THEN
          NULL;
        WHEN undefined_column THEN
          NULL;
        WHEN duplicate_column THEN
          NULL;
      END;
    END IF;
  END LOOP;
END $$;

-- ========== EN Views（无论是否已改名，统一重建） ==========
DROP VIEW IF EXISTS public."Y_codex_Layer5_Lac_Profile_EN";
DROP VIEW IF EXISTS public."Y_codex_Layer5_BS_Profile_EN";
DROP VIEW IF EXISTS public."Y_codex_Layer5_Cell_Profile_EN";

CREATE OR REPLACE VIEW public."Y_codex_Layer5_Lac_Profile_EN" AS
SELECT
  "运营商ID" AS operator_id_raw,
  "制式" AS tech_norm,
  "LAC" AS lac_dec_final,
  "行数" AS row_cnt,
  "最早时间UTC" AS first_cell_ts_utc,
  "最晚时间UTC" AS last_cell_ts_utc,
  "活跃天数UTC" AS active_days_utc,
  "BS去重数" AS distinct_bs_cnt,
  "CELL去重数" AS distinct_cell_cnt,
  "GPS有效行数" AS gps_present_cnt,
  "GPS缺失行数" AS gps_missing_cnt,
  "GPS有效率" AS gps_present_ratio,
  "GPS中心经度" AS center_lon,
  "GPS中心纬度" AS center_lat,
  "经度最小" AS lon_min,
  "经度最大" AS lon_max,
  "纬度最小" AS lat_min,
  "纬度最大" AS lat_max,
  "GPS距离P50_米" AS gps_p50_dist_m,
  "GPS距离P90_米" AS gps_p90_dist_m,
  "GPS距离MAX_米" AS gps_max_dist_m,
  "RSRP非空行数" AS sig_rsrp_nonnull_cnt,
  "RSRQ非空行数" AS sig_rsrq_nonnull_cnt,
  "SINR非空行数" AS sig_sinr_nonnull_cnt,
  "RSSI非空行数" AS sig_rssi_nonnull_cnt,
  "DBM非空行数" AS sig_dbm_nonnull_cnt,
  "ASU_LEVEL非空行数" AS sig_asu_level_nonnull_cnt,
  "LEVEL非空行数" AS sig_level_nonnull_cnt,
  "SS非空行数" AS sig_ss_nonnull_cnt,
  "RSRP有效率" AS sig_rsrp_nonnull_ratio,
  "RSRQ有效率" AS sig_rsrq_nonnull_ratio,
  "SINR有效率" AS sig_sinr_nonnull_ratio,
  "DBM有效率" AS sig_dbm_nonnull_ratio,
  "原生有信号行数" AS native_any_signal_row_cnt,
  "原生无信号行数" AS native_no_signal_row_cnt,
  "需要补齐行数" AS need_fill_row_cnt,
  "补齐成功行数" AS filled_row_cnt,
  "补齐_同CELL_行数" AS filled_by_cell_nearest_row_cnt,
  "补齐_BS_TOP_行数" AS filled_by_bs_top_cell_nearest_row_cnt,
  "补齐失败行数" AS fill_failed_row_cnt,
  "缺失字段数_补前合计" AS missing_field_before_sum,
  "缺失字段数_补后合计" AS missing_field_after_sum,
  "补齐字段数合计" AS filled_field_sum,
  "多运营商BS去重数" AS multi_operator_bs_cnt,
  "多运营商BS标记" AS has_multi_operator_bs,
  "样本不足" AS is_low_sample,
  "有GPS画像" AS has_gps_profile,
  "GPS不稳定" AS is_gps_unstable
FROM public."Y_codex_Layer5_Lac_Profile";

CREATE OR REPLACE VIEW public."Y_codex_Layer5_BS_Profile_EN" AS
SELECT
  "运营商ID" AS operator_id_raw,
  "制式" AS tech_norm,
  "LAC" AS lac_dec_final,
  "BS" AS bs_id_final,
  "物理分桶BS键" AS wuli_fentong_bs_key,
  "行数" AS row_cnt,
  "最早时间UTC" AS first_cell_ts_utc,
  "最晚时间UTC" AS last_cell_ts_utc,
  "活跃天数UTC" AS active_days_utc,
  "CELL去重数" AS distinct_cell_cnt,
  "GPS有效行数" AS gps_present_cnt,
  "GPS缺失行数" AS gps_missing_cnt,
  "GPS有效率" AS gps_present_ratio,
  "GPS中心经度" AS center_lon,
  "GPS中心纬度" AS center_lat,
  "GPS距离P50_米" AS gps_p50_dist_m,
  "GPS距离P90_米" AS gps_p90_dist_m,
  "GPS距离MAX_米" AS gps_max_dist_m,
  "RSRP非空行数" AS sig_rsrp_nonnull_cnt,
  "RSRQ非空行数" AS sig_rsrq_nonnull_cnt,
  "SINR非空行数" AS sig_sinr_nonnull_cnt,
  "RSSI非空行数" AS sig_rssi_nonnull_cnt,
  "DBM非空行数" AS sig_dbm_nonnull_cnt,
  "ASU_LEVEL非空行数" AS sig_asu_level_nonnull_cnt,
  "LEVEL非空行数" AS sig_level_nonnull_cnt,
  "SS非空行数" AS sig_ss_nonnull_cnt,
  "RSRP有效率" AS sig_rsrp_nonnull_ratio,
  "RSRQ有效率" AS sig_rsrq_nonnull_ratio,
  "SINR有效率" AS sig_sinr_nonnull_ratio,
  "DBM有效率" AS sig_dbm_nonnull_ratio,
  "原生有信号行数" AS native_any_signal_row_cnt,
  "原生无信号行数" AS native_no_signal_row_cnt,
  "需要补齐行数" AS need_fill_row_cnt,
  "补齐成功行数" AS filled_row_cnt,
  "补齐_同CELL_行数" AS filled_by_cell_nearest_row_cnt,
  "补齐_BS_TOP_行数" AS filled_by_bs_top_cell_nearest_row_cnt,
  "补齐失败行数" AS fill_failed_row_cnt,
  "缺失字段数_补前合计" AS missing_field_before_sum,
  "缺失字段数_补后合计" AS missing_field_after_sum,
  "补齐字段数合计" AS filled_field_sum,
  "疑似碰撞标记" AS is_collision_suspect,
  "严重碰撞桶标记" AS is_severe_collision,
  "碰撞原因" AS collision_reason,
  "GPS漂移行数" AS gps_drift_row_cnt,
  "GPS漂移占比" AS gps_drift_row_pct,
  "移动CELL去重数" AS dynamic_cell_cnt,
  "含移动CELL标记" AS has_dynamic_cell,
  "BS_ID<256标记" AS is_bs_id_lt_256,
  "多运营商共享标记" AS is_multi_operator_shared,
  "共享运营商数" AS shared_operator_cnt,
  "共享运营商列表" AS shared_operator_list,
  "样本不足" AS is_low_sample,
  "有GPS画像" AS has_gps_profile,
  "GPS不稳定" AS is_gps_unstable
FROM public."Y_codex_Layer5_BS_Profile";

CREATE OR REPLACE VIEW public."Y_codex_Layer5_Cell_Profile_EN" AS
SELECT
  "运营商ID" AS operator_id_raw,
  "制式" AS tech_norm,
  "LAC" AS lac_dec_final,
  "BS" AS bs_id_final,
  "CELL" AS cell_id_dec,
  "行数" AS row_cnt,
  "最早时间UTC" AS first_cell_ts_utc,
  "最晚时间UTC" AS last_cell_ts_utc,
  "活跃天数UTC" AS active_days_utc,
  "GPS有效行数" AS gps_present_cnt,
  "GPS缺失行数" AS gps_missing_cnt,
  "GPS有效率" AS gps_present_ratio,
  "GPS中心经度" AS center_lon,
  "GPS中心纬度" AS center_lat,
  "GPS距离P50_米" AS gps_p50_dist_m,
  "GPS距离P90_米" AS gps_p90_dist_m,
  "GPS距离MAX_米" AS gps_max_dist_m,
  "RSRP非空行数" AS sig_rsrp_nonnull_cnt,
  "RSRQ非空行数" AS sig_rsrq_nonnull_cnt,
  "SINR非空行数" AS sig_sinr_nonnull_cnt,
  "RSSI非空行数" AS sig_rssi_nonnull_cnt,
  "DBM非空行数" AS sig_dbm_nonnull_cnt,
  "ASU_LEVEL非空行数" AS sig_asu_level_nonnull_cnt,
  "LEVEL非空行数" AS sig_level_nonnull_cnt,
  "SS非空行数" AS sig_ss_nonnull_cnt,
  "RSRP有效率" AS sig_rsrp_nonnull_ratio,
  "RSRQ有效率" AS sig_rsrq_nonnull_ratio,
  "SINR有效率" AS sig_sinr_nonnull_ratio,
  "DBM有效率" AS sig_dbm_nonnull_ratio,
  "原生有信号行数" AS native_any_signal_row_cnt,
  "原生无信号行数" AS native_no_signal_row_cnt,
  "需要补齐行数" AS need_fill_row_cnt,
  "补齐成功行数" AS filled_row_cnt,
  "补齐_同CELL_行数" AS filled_by_cell_nearest_row_cnt,
  "补齐_BS_TOP_行数" AS filled_by_bs_top_cell_nearest_row_cnt,
  "补齐失败行数" AS fill_failed_row_cnt,
  "缺失字段数_补前合计" AS missing_field_before_sum,
  "缺失字段数_补后合计" AS missing_field_after_sum,
  "补齐字段数合计" AS filled_field_sum,
  "疑似碰撞标记" AS is_collision_suspect,
  "严重碰撞桶标记" AS is_severe_collision,
  "碰撞原因" AS collision_reason,
  "GPS漂移行数" AS gps_drift_row_cnt,
  "GPS漂移占比" AS gps_drift_row_pct,
  "移动CELL标记" AS is_dynamic_cell,
  "移动原因" AS dynamic_reason,
  "移动半长轴KM" AS half_major_dist_km,
  "BS_ID<256标记" AS is_bs_id_lt_256,
  "多运营商共享标记" AS is_multi_operator_shared,
  "共享运营商数" AS shared_operator_cnt,
  "共享运营商列表" AS shared_operator_list,
  "样本不足" AS is_low_sample,
  "有GPS画像" AS has_gps_profile,
  "GPS不稳定" AS is_gps_unstable
FROM public."Y_codex_Layer5_Cell_Profile";
