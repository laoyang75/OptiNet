SET statement_timeout = 0;

DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['rebuild3', 'rebuild3_sample'] LOOP
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%1$s_fact_governed_object_scope ON %1$s.fact_governed (operator_code, tech_norm, lac, bs_id, cell_id) INCLUDE (gps_source, signal_source)',
      s
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%1$s_fact_pending_observation_object_scope ON %1$s.fact_pending_observation (operator_code, tech_norm, lac, bs_id, cell_id)',
      s
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%1$s_fact_pending_issue_object_scope ON %1$s.fact_pending_issue (operator_code, tech_norm, lac, bs_id, cell_id)',
      s
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%1$s_fact_rejected_object_scope ON %1$s.fact_rejected (operator_code, tech_norm, lac, bs_id, cell_id)',
      s
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%1$s_obj_state_history_lookup ON %1$s.obj_state_history (object_type, object_id, changed_at DESC)',
      s
    );
  END LOOP;
END $$;
