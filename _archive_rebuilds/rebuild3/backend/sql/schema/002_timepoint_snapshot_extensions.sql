SET statement_timeout = 0;

DO $$
DECLARE
  s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['rebuild3_meta', 'rebuild3_sample_meta'] LOOP
    EXECUTE format('ALTER TABLE %I.run ADD COLUMN IF NOT EXISTS scenario_key text', s);
    EXECUTE format('ALTER TABLE %I.run ADD COLUMN IF NOT EXISTS scenario_label text', s);
    EXECUTE format('ALTER TABLE %I.run ADD COLUMN IF NOT EXISTS init_days integer', s);
    EXECUTE format('ALTER TABLE %I.run ADD COLUMN IF NOT EXISTS step_hours integer', s);
    EXECUTE format('ALTER TABLE %I.run ADD COLUMN IF NOT EXISTS snapshot_source text', s);

    EXECUTE format('ALTER TABLE %I.batch ADD COLUMN IF NOT EXISTS scenario_key text', s);
    EXECUTE format('ALTER TABLE %I.batch ADD COLUMN IF NOT EXISTS timepoint_role text', s);
    EXECUTE format('ALTER TABLE %I.batch ADD COLUMN IF NOT EXISTS batch_seq integer', s);
    EXECUTE format('ALTER TABLE %I.batch ADD COLUMN IF NOT EXISTS snapshot_at timestamptz', s);

    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.run (scenario_key, created_at DESC)', 'idx_' || s || '_run_scenario_created', s);
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.batch (run_id, batch_seq)', 'idx_' || s || '_batch_run_seq', s);
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.batch (scenario_key, snapshot_at DESC)', 'idx_' || s || '_batch_scenario_snapshot', s);
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.batch (timepoint_role, snapshot_at DESC)', 'idx_' || s || '_batch_role_snapshot', s);
  END LOOP;
END
$$;

CREATE OR REPLACE VIEW rebuild3_meta.v_flow_snapshot_timepoints AS
SELECT
  r.run_id,
  r.run_type,
  r.status AS run_status,
  r.scenario_key,
  r.scenario_label,
  r.init_days,
  r.step_hours,
  r.window_start AS run_window_start,
  r.window_end AS run_window_end,
  b.batch_id,
  b.batch_type,
  b.status AS batch_status,
  b.timepoint_role,
  b.batch_seq,
  b.snapshot_at,
  b.window_start AS batch_window_start,
  b.window_end AS batch_window_end,
  b.baseline_version,
  b.is_rerun
FROM rebuild3_meta.run r
JOIN rebuild3_meta.batch b
  ON b.run_id = r.run_id
WHERE r.scenario_key IS NOT NULL
ORDER BY r.created_at DESC, b.batch_seq ASC, b.snapshot_at ASC;

