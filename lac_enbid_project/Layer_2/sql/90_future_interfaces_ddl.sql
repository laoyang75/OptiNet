-- Layer_2：未来阶段接口预埋（仅字段结构示例，不在本轮实现数据写入）
-- 目的：
--   - 阶段二：Cleaned_Augmented_DB（清洗补齐库）
--   - 阶段三：Master_BS_Library（基站库）
--   - Final：Final_Master_DB（最终主库，含 gps_source 回填标记）

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

CREATE TABLE IF NOT EXISTS public.cleaned_augmented_db (
  src_seq_id bigint,
  src_record_id text,

  status text,              -- Verified / Corrected_LAC / New_CellID_Candidate / Unverified_Omitted
  data_source text,         -- APP / SS1 / ThirdParty / ...

  operator_id_raw text,
  tech_norm text,
  cell_id_dec bigint,

  original_lac bigint,
  corrected_lac bigint,

  gps_status text,          -- Verified / Drift / Missing
  gps_source text,          -- Original / Augmented_from_BS

  ts_std timestamp,
  report_date date,

  lon double precision,
  lat double precision
);


CREATE TABLE IF NOT EXISTS public.master_bs_library (
  bs_id bigint,
  sector_id bigint,

  operator_id_raw text,
  tech_norm text,

  bs_gps_center_lon double precision,
  bs_gps_center_lat double precision,

  associated_lac_list text,
  associated_lac_count int,

  cellid_count int,

  first_seen_ts timestamp,
  last_seen_ts timestamp,
  active_days int
);


CREATE TABLE IF NOT EXISTS public.final_master_db (
  src_seq_id bigint,
  src_record_id text,

  operator_id_raw text,
  tech_norm text,
  cell_id_dec bigint,

  lac_final bigint,
  lon_final double precision,
  lat_final double precision,

  gps_source text,          -- Original_Verified / Augmented_from_BS / ...
  gps_status text,          -- Verified / Drift / Missing
  status text,

  ts_std timestamp,
  report_date date
);
