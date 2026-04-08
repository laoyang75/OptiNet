-- Phase1 Observability Mart DDL (S1 bootstrap)
-- Scope: create read-optimized tables for dashboard/API, decoupled from Layer_0~Layer_5 core outputs.

SET statement_timeout = 0;
SET jit = off;

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_run_registry" (
  run_id text PRIMARY KEY,
  run_started_at timestamptz NOT NULL,
  run_finished_at timestamptz,
  source_db text NOT NULL DEFAULT current_database(),
  pipeline_version text NOT NULL DEFAULT 'phase1_v1',
  run_status text NOT NULL DEFAULT 'running',
  notes text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_layer_snapshot" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  layer_id text NOT NULL,
  input_rows bigint,
  output_rows bigint,
  pass_flag boolean NOT NULL DEFAULT true,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, layer_id)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_rule_hit" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  layer_id text NOT NULL,
  rule_code text NOT NULL,
  hit_rows bigint NOT NULL,
  hit_ratio numeric(9,4),
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, layer_id, rule_code)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_quality_metric" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  layer_id text NOT NULL,
  metric_code text NOT NULL,
  metric_value numeric(20,6) NOT NULL,
  unit text NOT NULL DEFAULT 'rows',
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, layer_id, metric_code)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_anomaly_stats" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  object_level text NOT NULL,
  anomaly_code text NOT NULL,
  obj_cnt bigint NOT NULL,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, object_level, anomaly_code)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_reconciliation" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  check_code text NOT NULL,
  lhs_value numeric(20,6) NOT NULL,
  rhs_value numeric(20,6) NOT NULL,
  diff_value numeric(20,6) NOT NULL,
  pass_flag boolean NOT NULL,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, check_code)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_exposure_matrix" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  object_level text NOT NULL,
  field_code text NOT NULL,
  exposed_flag boolean NOT NULL,
  true_obj_cnt bigint,
  total_obj_cnt bigint,
  note text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, object_level, field_code)
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_issue_log" (
  issue_id bigserial PRIMARY KEY,
  run_id text REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE SET NULL,
  severity text NOT NULL,
  layer_id text NOT NULL,
  title text NOT NULL,
  evidence_sql text,
  status text NOT NULL DEFAULT 'new',
  owner text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_patch_log" (
  patch_id bigserial PRIMARY KEY,
  issue_id bigint REFERENCES public."Y_codex_obs_issue_log"(issue_id) ON DELETE SET NULL,
  run_id text REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE SET NULL,
  change_type text NOT NULL,
  change_summary text NOT NULL,
  owner text,
  verified_flag boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS public."Y_codex_obs_gate_result" (
  run_id text NOT NULL REFERENCES public."Y_codex_obs_run_registry"(run_id) ON DELETE CASCADE,
  gate_code text NOT NULL,
  gate_name text NOT NULL,
  actual_value numeric(20,6),
  expected_value numeric(20,6),
  diff_value numeric(20,6),
  pass_flag boolean NOT NULL,
  evidence_sql text,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, gate_code)
);

CREATE INDEX IF NOT EXISTS idx_obs_run_registry_started_at
  ON public."Y_codex_obs_run_registry"(run_started_at DESC);

CREATE INDEX IF NOT EXISTS idx_obs_layer_snapshot_layer
  ON public."Y_codex_obs_layer_snapshot"(layer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_obs_quality_metric_layer_metric
  ON public."Y_codex_obs_quality_metric"(layer_id, metric_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_obs_gate_result_pass
  ON public."Y_codex_obs_gate_result"(pass_flag, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_obs_issue_status
  ON public."Y_codex_obs_issue_log"(status, severity, updated_at DESC);

