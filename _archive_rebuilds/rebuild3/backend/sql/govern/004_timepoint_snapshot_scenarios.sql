SET statement_timeout = 0;
SET work_mem = '256MB';

-- Speed up repeated scenario scans by event time.
CREATE INDEX IF NOT EXISTS idx_rebuild2_l0_lac_report_time
  ON rebuild2.l0_lac ("上报时间");

CREATE OR REPLACE PROCEDURE rebuild3_meta.run_timepoint_snapshot_scenario(
  p_scenario_key text,
  p_init_days integer,
  p_step_hours integer DEFAULT 2,
  p_window_start timestamptz DEFAULT NULL,
  p_window_end timestamptz DEFAULT NULL,
  p_contract_version text DEFAULT 'rebuild3-contract-v1',
  p_rule_set_version text DEFAULT 'rebuild3-rule-set-v1',
  p_note text DEFAULT NULL,
  p_reset_existing boolean DEFAULT true
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_start_time timestamptz;
  v_end_time timestamptz;
  v_scenario_key text;
  v_scenario_label text;
  v_run_token text;
  v_run_id text;
  v_baseline_version text;
  v_total_buckets integer;
  v_init_bucket integer;
  v_bucket_no integer;
  v_batch_seq integer;
  v_batch_id text;
  v_batch_type text;
  v_timepoint_role text;
  v_batch_start timestamptz;
  v_batch_end timestamptz;
  v_snapshot_at timestamptz;
  v_input_rows bigint;
  v_output_rows bigint;
  v_total_rows bigint;
  v_invalid_rows bigint;
  v_pending_observation_rows bigint;
  v_pending_issue_rows bigint;
  v_rejected_rows bigint;
  v_governed_rows bigint;
  v_obj_cell bigint;
  v_obj_bs bigint;
  v_obj_lac bigint;
  v_baseline_cell bigint;
  v_baseline_bs bigint;
  v_baseline_lac bigint;
  v_cell_baseline_ratio numeric;
  v_bs_baseline_ratio numeric;
  v_lac_baseline_ratio numeric;
BEGIN
  IF p_scenario_key IS NULL OR btrim(p_scenario_key) = '' THEN
    RAISE EXCEPTION 'scenario_key is required';
  END IF;
  IF p_init_days < 1 THEN
    RAISE EXCEPTION 'init_days must be >= 1, got %', p_init_days;
  END IF;
  IF p_step_hours < 1 THEN
    RAISE EXCEPTION 'step_hours must be >= 1, got %', p_step_hours;
  END IF;

  SELECT
    COALESCE(p_window_start, min("上报时间")),
    COALESCE(p_window_end, max("上报时间"))
  INTO v_start_time, v_end_time
  FROM rebuild2.l0_lac;

  IF v_start_time IS NULL OR v_end_time IS NULL THEN
    RAISE EXCEPTION 'rebuild2.l0_lac has no usable event_time range';
  END IF;
  IF v_start_time >= v_end_time THEN
    RAISE EXCEPTION 'window_start must be earlier than window_end';
  END IF;

  v_scenario_key := upper(regexp_replace(btrim(p_scenario_key), '[^A-Za-z0-9]+', '_', 'g'));
  v_scenario_label := format('init_%sd_step_%sh', p_init_days, p_step_hours);
  v_run_token := to_char(clock_timestamp(), 'YYYYMMDDHH24MISSMS');
  v_run_id := format('RUN-SCN-%s-%s', v_scenario_key, v_run_token);
  v_baseline_version := format('BASELINE-SCN-%s-%s', v_scenario_key, v_run_token);

  v_total_buckets := greatest(
    1,
    ceil(extract(epoch FROM (v_end_time - v_start_time)) / 3600.0 / p_step_hours)::int
  );
  v_init_bucket := least(v_total_buckets - 1, ((p_init_days * 24) / p_step_hours) - 1);
  IF v_init_bucket < 0 THEN
    v_init_bucket := 0;
  END IF;

  IF p_reset_existing THEN
    DELETE FROM rebuild3_meta.batch_snapshot s
    USING rebuild3_meta.batch b, rebuild3_meta.run r
    WHERE s.batch_id = b.batch_id
      AND b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.batch_flow_summary s
    USING rebuild3_meta.batch b, rebuild3_meta.run r
    WHERE s.batch_id = b.batch_id
      AND b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.batch_decision_summary s
    USING rebuild3_meta.batch b, rebuild3_meta.run r
    WHERE s.batch_id = b.batch_id
      AND b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.batch_anomaly_summary s
    USING rebuild3_meta.batch b, rebuild3_meta.run r
    WHERE s.batch_id = b.batch_id
      AND b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.batch_baseline_refresh_log s
    USING rebuild3_meta.batch b, rebuild3_meta.run r
    WHERE s.batch_id = b.batch_id
      AND b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.batch b
    USING rebuild3_meta.run r
    WHERE b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.baseline_version b
    USING rebuild3_meta.run r
    WHERE b.run_id = r.run_id
      AND r.scenario_key = v_scenario_key;

    DELETE FROM rebuild3_meta.run
    WHERE scenario_key = v_scenario_key;
  END IF;

  INSERT INTO rebuild3_meta.run (
    run_id,
    run_type,
    status,
    scenario_key,
    scenario_label,
    init_days,
    step_hours,
    snapshot_source,
    window_start,
    window_end,
    contract_version,
    rule_set_version,
    baseline_version,
    note
  )
  VALUES (
    v_run_id,
    'scenario_replay',
    'running',
    v_scenario_key,
    v_scenario_label,
    p_init_days,
    p_step_hours,
    'rebuild2.l0_lac',
    v_start_time,
    v_end_time,
    p_contract_version,
    p_rule_set_version,
    v_baseline_version,
    COALESCE(p_note, format('timepoint snapshot scenario: %s', v_scenario_label))
  );

  CREATE TEMP TABLE tmp_scenario_events ON COMMIT DROP AS
  SELECT
    "上报时间" AS event_time,
    floor(extract(epoch FROM ("上报时间" - v_start_time)) / 3600.0 / p_step_hours)::int AS bucket_no,
    ("运营商编码" IS NOT NULL AND "LAC" IS NOT NULL AND "CellID" IS NOT NULL) AS valid_key,
    COALESCE("GPS有效", false) AS gps_valid,
    ("经度" BETWEEN 73 AND 135 AND "纬度" BETWEEN 3 AND 54) AS gps_in_china,
    "运营商编码"::text AS operator_code,
    "标准制式"::text AS tech_norm,
    "LAC"::text AS lac,
    "基站ID"::text AS bs_id,
    "CellID"::text AS cell_id
  FROM rebuild2.l0_lac
  WHERE "上报时间" >= v_start_time
    AND "上报时间" <= v_end_time;

  CREATE INDEX tmp_scenario_events_bucket_idx ON tmp_scenario_events (bucket_no);
  CREATE INDEX tmp_scenario_events_cell_idx ON tmp_scenario_events (bucket_no, operator_code, tech_norm, lac, bs_id, cell_id) WHERE valid_key;
  ANALYZE tmp_scenario_events;

  CREATE TEMP TABLE tmp_bucket_cum ON COMMIT DROP AS
  WITH series AS (
    SELECT generate_series(0, v_total_buckets - 1) AS bucket_no
  ),
  per_bucket AS (
    SELECT
      bucket_no,
      count(*)::bigint AS total_rows,
      count(*) FILTER (WHERE NOT valid_key)::bigint AS invalid_rows,
      count(*) FILTER (WHERE valid_key AND NOT gps_valid)::bigint AS pending_observation_rows,
      count(*) FILTER (WHERE valid_key AND gps_valid AND NOT gps_in_china)::bigint AS pending_issue_rows,
      count(*) FILTER (WHERE valid_key)::bigint AS valid_rows
    FROM tmp_scenario_events
    GROUP BY bucket_no
  )
  SELECT
    s.bucket_no,
    sum(COALESCE(p.total_rows, 0)) OVER (ORDER BY s.bucket_no) AS total_rows_cum,
    sum(COALESCE(p.invalid_rows, 0)) OVER (ORDER BY s.bucket_no) AS invalid_rows_cum,
    sum(COALESCE(p.pending_observation_rows, 0)) OVER (ORDER BY s.bucket_no) AS pending_observation_rows_cum,
    sum(COALESCE(p.pending_issue_rows, 0)) OVER (ORDER BY s.bucket_no) AS pending_issue_rows_cum,
    sum(COALESCE(p.valid_rows, 0)) OVER (ORDER BY s.bucket_no) AS valid_rows_cum,
    COALESCE(p.total_rows, 0) AS total_rows_batch,
    COALESCE(p.valid_rows, 0) AS valid_rows_batch
  FROM series s
  LEFT JOIN per_bucket p
    ON p.bucket_no = s.bucket_no;

  CREATE TEMP TABLE tmp_cell_cum ON COMMIT DROP AS
  WITH first_seen AS (
    SELECT
      operator_code, tech_norm, lac, bs_id, cell_id,
      min(bucket_no) AS first_bucket
    FROM tmp_scenario_events
    WHERE valid_key
      AND operator_code IS NOT NULL
      AND tech_norm IS NOT NULL
      AND lac IS NOT NULL
      AND bs_id IS NOT NULL
      AND cell_id IS NOT NULL
    GROUP BY 1, 2, 3, 4, 5
  ),
  series AS (
    SELECT generate_series(0, v_total_buckets - 1) AS bucket_no
  ),
  per_bucket AS (
    SELECT first_bucket AS bucket_no, count(*)::bigint AS new_cells
    FROM first_seen
    GROUP BY first_bucket
  )
  SELECT
    s.bucket_no,
    sum(COALESCE(p.new_cells, 0)) OVER (ORDER BY s.bucket_no) AS obj_cell_cum
  FROM series s
  LEFT JOIN per_bucket p
    ON p.bucket_no = s.bucket_no;

  CREATE TEMP TABLE tmp_bs_cum ON COMMIT DROP AS
  WITH first_seen AS (
    SELECT
      operator_code, tech_norm, lac, bs_id,
      min(bucket_no) AS first_bucket
    FROM tmp_scenario_events
    WHERE valid_key
      AND operator_code IS NOT NULL
      AND tech_norm IS NOT NULL
      AND lac IS NOT NULL
      AND bs_id IS NOT NULL
    GROUP BY 1, 2, 3, 4
  ),
  series AS (
    SELECT generate_series(0, v_total_buckets - 1) AS bucket_no
  ),
  per_bucket AS (
    SELECT first_bucket AS bucket_no, count(*)::bigint AS new_bs
    FROM first_seen
    GROUP BY first_bucket
  )
  SELECT
    s.bucket_no,
    sum(COALESCE(p.new_bs, 0)) OVER (ORDER BY s.bucket_no) AS obj_bs_cum
  FROM series s
  LEFT JOIN per_bucket p
    ON p.bucket_no = s.bucket_no;

  CREATE TEMP TABLE tmp_lac_cum ON COMMIT DROP AS
  WITH first_seen AS (
    SELECT
      operator_code, tech_norm, lac,
      min(bucket_no) AS first_bucket
    FROM tmp_scenario_events
    WHERE valid_key
      AND operator_code IS NOT NULL
      AND tech_norm IS NOT NULL
      AND lac IS NOT NULL
    GROUP BY 1, 2, 3
  ),
  series AS (
    SELECT generate_series(0, v_total_buckets - 1) AS bucket_no
  ),
  per_bucket AS (
    SELECT first_bucket AS bucket_no, count(*)::bigint AS new_lac
    FROM first_seen
    GROUP BY first_bucket
  )
  SELECT
    s.bucket_no,
    sum(COALESCE(p.new_lac, 0)) OVER (ORDER BY s.bucket_no) AS obj_lac_cum
  FROM series s
  LEFT JOIN per_bucket p
    ON p.bucket_no = s.bucket_no;

  SELECT
    COALESCE((SELECT count(*)::numeric FROM rebuild3.baseline_cell) / NULLIF((SELECT count(*)::numeric FROM rebuild3.obj_cell), 0), 0.65),
    COALESCE((SELECT count(*)::numeric FROM rebuild3.baseline_bs) / NULLIF((SELECT count(*)::numeric FROM rebuild3.obj_bs), 0), 0.70),
    COALESCE((SELECT count(*)::numeric FROM rebuild3.baseline_lac) / NULLIF((SELECT count(*)::numeric FROM rebuild3.obj_lac), 0), 0.75)
  INTO v_cell_baseline_ratio, v_bs_baseline_ratio, v_lac_baseline_ratio;

  FOR v_bucket_no IN v_init_bucket .. (v_total_buckets - 1) LOOP
    IF v_bucket_no = v_init_bucket THEN
      v_batch_seq := 0;
      v_batch_type := 'scenario_init';
      v_timepoint_role := 'init';
      v_batch_start := v_start_time;
      v_batch_end := least(v_end_time, v_start_time + make_interval(hours => (v_bucket_no + 1) * p_step_hours));
      v_batch_id := format('BATCH-SCN-%s-%s-INIT', v_scenario_key, v_run_token);
      SELECT
        COALESCE(sum(total_rows_batch), 0)::bigint,
        COALESCE(sum(valid_rows_batch), 0)::bigint
      INTO v_input_rows, v_output_rows
      FROM tmp_bucket_cum
      WHERE bucket_no <= v_bucket_no;
    ELSE
      v_batch_seq := v_bucket_no - v_init_bucket;
      v_batch_type := 'scenario_roll_2h';
      v_timepoint_role := 'rolling_2h';
      v_batch_start := v_start_time + make_interval(hours => v_bucket_no * p_step_hours);
      v_batch_end := least(v_end_time, v_start_time + make_interval(hours => (v_bucket_no + 1) * p_step_hours));
      v_batch_id := format(
        'BATCH-SCN-%s-%s-R2H-%s',
        v_scenario_key,
        v_run_token,
        lpad(v_batch_seq::text, 3, '0')
      );
      SELECT
        COALESCE(total_rows_batch, 0)::bigint,
        COALESCE(valid_rows_batch, 0)::bigint
      INTO v_input_rows, v_output_rows
      FROM tmp_bucket_cum
      WHERE bucket_no = v_bucket_no;
    END IF;

    v_snapshot_at := v_batch_end;

    SELECT
      c.total_rows_cum,
      c.invalid_rows_cum,
      c.pending_observation_rows_cum,
      c.pending_issue_rows_cum,
      cc.obj_cell_cum,
      bc.obj_bs_cum,
      lc.obj_lac_cum
    INTO
      v_total_rows,
      v_invalid_rows,
      v_pending_observation_rows,
      v_pending_issue_rows,
      v_obj_cell,
      v_obj_bs,
      v_obj_lac
    FROM tmp_bucket_cum c
    JOIN tmp_cell_cum cc USING (bucket_no)
    JOIN tmp_bs_cum bc USING (bucket_no)
    JOIN tmp_lac_cum lc USING (bucket_no)
    WHERE c.bucket_no = v_bucket_no;

    v_rejected_rows := COALESCE(v_invalid_rows, 0);
    v_governed_rows := greatest(
      COALESCE(v_total_rows, 0) - COALESCE(v_rejected_rows, 0)
      - COALESCE(v_pending_observation_rows, 0)
      - COALESCE(v_pending_issue_rows, 0),
      0
    );
    v_baseline_cell := floor(COALESCE(v_obj_cell, 0) * COALESCE(v_cell_baseline_ratio, 0.65))::bigint;
    v_baseline_bs := floor(COALESCE(v_obj_bs, 0) * COALESCE(v_bs_baseline_ratio, 0.70))::bigint;
    v_baseline_lac := floor(COALESCE(v_obj_lac, 0) * COALESCE(v_lac_baseline_ratio, 0.75))::bigint;

    INSERT INTO rebuild3_meta.batch (
      batch_id,
      run_id,
      batch_type,
      status,
      scenario_key,
      timepoint_role,
      batch_seq,
      snapshot_at,
      window_start,
      window_end,
      source_name,
      contract_version,
      rule_set_version,
      baseline_version,
      input_rows,
      output_rows,
      is_rerun
    )
    VALUES (
      v_batch_id,
      v_run_id,
      v_batch_type,
      'completed',
      v_scenario_key,
      v_timepoint_role,
      v_batch_seq,
      v_snapshot_at,
      v_batch_start,
      v_batch_end,
      'rebuild2.l0_lac',
      p_contract_version,
      p_rule_set_version,
      v_baseline_version,
      v_input_rows,
      v_output_rows,
      false
    );

    INSERT INTO rebuild3_meta.batch_snapshot (batch_id, stage_name, metric_name, metric_value)
    VALUES
      (v_batch_id, 'input', 'fact_standardized', COALESCE(v_total_rows, 0)),
      (v_batch_id, 'routing', 'fact_governed', COALESCE(v_governed_rows, 0)),
      (v_batch_id, 'routing', 'fact_pending_observation', COALESCE(v_pending_observation_rows, 0)),
      (v_batch_id, 'routing', 'fact_pending_issue', COALESCE(v_pending_issue_rows, 0)),
      (v_batch_id, 'routing', 'fact_rejected', COALESCE(v_rejected_rows, 0)),
      (v_batch_id, 'objects', 'obj_cell', COALESCE(v_obj_cell, 0)),
      (v_batch_id, 'objects', 'obj_bs', COALESCE(v_obj_bs, 0)),
      (v_batch_id, 'objects', 'obj_lac', COALESCE(v_obj_lac, 0)),
      (v_batch_id, 'baseline', 'baseline_cell', COALESCE(v_baseline_cell, 0)),
      (v_batch_id, 'baseline', 'baseline_bs', COALESCE(v_baseline_bs, 0)),
      (v_batch_id, 'baseline', 'baseline_lac', COALESCE(v_baseline_lac, 0))
    ON CONFLICT (batch_id, stage_name, metric_name) DO UPDATE
    SET metric_value = EXCLUDED.metric_value,
        created_at = now();

    INSERT INTO rebuild3_meta.batch_flow_summary (batch_id, fact_layer, row_count, row_ratio)
    VALUES
      (v_batch_id, 'fact_governed', COALESCE(v_governed_rows, 0), round(COALESCE(v_governed_rows, 0)::numeric / nullif(COALESCE(v_total_rows, 0), 0), 4)),
      (v_batch_id, 'fact_pending_observation', COALESCE(v_pending_observation_rows, 0), round(COALESCE(v_pending_observation_rows, 0)::numeric / nullif(COALESCE(v_total_rows, 0), 0), 4)),
      (v_batch_id, 'fact_pending_issue', COALESCE(v_pending_issue_rows, 0), round(COALESCE(v_pending_issue_rows, 0)::numeric / nullif(COALESCE(v_total_rows, 0), 0), 4)),
      (v_batch_id, 'fact_rejected', COALESCE(v_rejected_rows, 0), round(COALESCE(v_rejected_rows, 0)::numeric / nullif(COALESCE(v_total_rows, 0), 0), 4))
    ON CONFLICT (batch_id, fact_layer) DO UPDATE
    SET row_count = EXCLUDED.row_count,
        row_ratio = EXCLUDED.row_ratio,
        created_at = now();

    INSERT INTO rebuild3_meta.batch_anomaly_summary (batch_id, anomaly_level, anomaly_name, object_count, fact_count)
    VALUES
      (v_batch_id, 'record', 'gps_outlier', NULL::bigint, COALESCE(v_pending_issue_rows, 0)),
      (v_batch_id, 'record', 'gps_missing', NULL::bigint, COALESCE(v_pending_observation_rows, 0)),
      (v_batch_id, 'record', 'structural_rejected', NULL::bigint, COALESCE(v_rejected_rows, 0)),
      (v_batch_id, 'cell_object', 'active', COALESCE(v_obj_cell, 0), NULL::bigint),
      (v_batch_id, 'bs_object', 'active', COALESCE(v_obj_bs, 0), NULL::bigint),
      (v_batch_id, 'lac_object', 'active', COALESCE(v_obj_lac, 0), NULL::bigint)
    ON CONFLICT (batch_id, anomaly_level, anomaly_name) DO UPDATE
    SET object_count = EXCLUDED.object_count,
        fact_count = EXCLUDED.fact_count,
        created_at = now();

    INSERT INTO rebuild3_meta.batch_baseline_refresh_log (batch_id, baseline_version, refresh_reason, triggered)
    VALUES (
      v_batch_id,
      v_baseline_version,
      CASE WHEN v_timepoint_role = 'init' THEN 'scenario_initialization' ELSE 'rolling_2h_snapshot' END,
      (v_timepoint_role = 'init')
    )
    ON CONFLICT (batch_id) DO UPDATE
    SET baseline_version = EXCLUDED.baseline_version,
        refresh_reason = EXCLUDED.refresh_reason,
        triggered = EXCLUDED.triggered,
        created_at = now();

    IF v_timepoint_role = 'init' THEN
      INSERT INTO rebuild3_meta.baseline_version (
        baseline_version, run_id, batch_id, rule_set_version, refresh_reason, object_count
      )
      VALUES (
        v_baseline_version,
        v_run_id,
        v_batch_id,
        p_rule_set_version,
        'scenario_initialization',
        COALESCE(v_baseline_cell, 0) + COALESCE(v_baseline_bs, 0) + COALESCE(v_baseline_lac, 0)
      )
      ON CONFLICT (baseline_version) DO UPDATE
      SET run_id = EXCLUDED.run_id,
          batch_id = EXCLUDED.batch_id,
          rule_set_version = EXCLUDED.rule_set_version,
          refresh_reason = EXCLUDED.refresh_reason,
          object_count = EXCLUDED.object_count,
          created_at = now();
    END IF;
  END LOOP;

  UPDATE rebuild3_meta.run
  SET status = 'completed',
      baseline_version = v_baseline_version
  WHERE run_id = v_run_id;
END;
$$;
