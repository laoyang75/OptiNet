-- 性能分析表结构定义
-- 对应 step30fenxi.md 第 2 节

CREATE TABLE IF NOT EXISTS public.codex_perf_runs (
  run_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  application_name text NOT NULL,
  is_smoke boolean NOT NULL,
  smoke_report_date date,
  smoke_operator_id_raw text,
  guc jsonb,
  notes text
);

CREATE TABLE IF NOT EXISTS public.codex_perf_samples_activity (
  run_id text NOT NULL,
  ts timestamptz NOT NULL,
  pid int,
  leader_pid int,
  backend_type text,
  state text,
  wait_event_type text,
  wait_event text,
  q_age interval,
  query_prefix text
);

CREATE TABLE IF NOT EXISTS public.codex_perf_samples_dbstat (
  run_id text NOT NULL,
  ts timestamptz NOT NULL,
  temp_files bigint,
  temp_bytes bigint,
  blks_read bigint,
  blks_hit bigint,
  blk_read_time double precision,
  blk_write_time double precision
);

CREATE TABLE IF NOT EXISTS public.codex_perf_stage_summary (
  run_id text NOT NULL,
  stage_name text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz NOT NULL,
  elapsed_ms bigint NOT NULL,
  out_rows bigint,
  out_bytes bigint,
  temp_bytes_delta bigint,
  blks_read_delta bigint,
  notes text
);
