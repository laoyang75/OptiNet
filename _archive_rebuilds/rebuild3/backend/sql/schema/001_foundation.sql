SET statement_timeout = 0;

CREATE SCHEMA IF NOT EXISTS rebuild3;
CREATE SCHEMA IF NOT EXISTS rebuild3_meta;
CREATE SCHEMA IF NOT EXISTS rebuild3_sample;
CREATE SCHEMA IF NOT EXISTS rebuild3_sample_meta;

DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['rebuild3', 'rebuild3_sample'] LOOP
    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.fact_standardized (
        standardized_event_id text PRIMARY KEY,
        source_name text NOT NULL,
        source_row_id bigint,
        source_record_id text,
        event_time timestamptz,
        operator_code text,
        tech_norm text,
        lac text,
        bs_id bigint,
        cell_id bigint,
        dev_id text,
        raw_lon double precision,
        raw_lat double precision,
        gps_valid boolean,
        rsrp_raw integer,
        rsrq_raw integer,
        sinr_raw integer,
        dbm_raw integer,
        structural_valid boolean NOT NULL,
        route_reason text,
        sample_scope_tag text,
        contract_version text,
        rule_set_version text,
        run_id text,
        batch_id text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.fact_governed (
        standardized_event_id text PRIMARY KEY,
        source_name text NOT NULL,
        event_time timestamptz,
        operator_code text,
        tech_norm text,
        lac text,
        bs_id bigint,
        cell_id bigint,
        dev_id text,
        lon_final double precision,
        lat_final double precision,
        gps_source text,
        signal_source text,
        anomaly_tags text[],
        baseline_eligible boolean,
        route_reason text,
        sample_scope_tag text,
        contract_version text,
        rule_set_version text,
        baseline_version text,
        run_id text,
        batch_id text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.fact_pending_observation (
        standardized_event_id text PRIMARY KEY,
        source_name text NOT NULL,
        event_time timestamptz,
        operator_code text,
        tech_norm text,
        lac text,
        bs_id bigint,
        cell_id bigint,
        dev_id text,
        route_reason text,
        missing_layer text,
        anomaly_tags text[],
        sample_scope_tag text,
        contract_version text,
        rule_set_version text,
        baseline_version text,
        run_id text,
        batch_id text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.fact_pending_issue (
        standardized_event_id text PRIMARY KEY,
        source_name text NOT NULL,
        event_time timestamptz,
        operator_code text,
        tech_norm text,
        lac text,
        bs_id bigint,
        cell_id bigint,
        dev_id text,
        health_state text,
        anomaly_tags text[],
        baseline_eligible boolean,
        route_reason text,
        sample_scope_tag text,
        contract_version text,
        rule_set_version text,
        baseline_version text,
        run_id text,
        batch_id text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.fact_rejected (
        standardized_event_id text PRIMARY KEY,
        source_name text NOT NULL,
        event_time timestamptz,
        operator_code text,
        tech_norm text,
        lac text,
        bs_id bigint,
        cell_id bigint,
        dev_id text,
        rejection_reason text,
        sample_scope_tag text,
        contract_version text,
        rule_set_version text,
        run_id text,
        batch_id text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.obj_cell (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        bs_id bigint,
        cell_id bigint NOT NULL,
        lifecycle_state text NOT NULL,
        health_state text NOT NULL,
        existence_eligible boolean NOT NULL,
        anchorable boolean NOT NULL,
        baseline_eligible boolean NOT NULL,
        record_count bigint NOT NULL,
        gps_count bigint NOT NULL,
        device_count bigint NOT NULL,
        active_days integer NOT NULL,
        centroid_lon double precision,
        centroid_lat double precision,
        gps_p50_dist_m numeric,
        gps_p90_dist_m numeric,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        anomaly_tags text[],
        parent_bs_object_id text,
        run_id text NOT NULL,
        batch_id text NOT NULL,
        baseline_version text,
        sample_scope_tag text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.obj_bs (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        bs_id bigint NOT NULL,
        lifecycle_state text NOT NULL,
        health_state text NOT NULL,
        existence_eligible boolean NOT NULL,
        anchorable boolean NOT NULL,
        baseline_eligible boolean NOT NULL,
        cell_count bigint NOT NULL,
        active_cell_count bigint NOT NULL,
        record_count bigint NOT NULL,
        gps_count bigint NOT NULL,
        device_count bigint NOT NULL,
        active_days integer NOT NULL,
        center_lon double precision,
        center_lat double precision,
        gps_p50_dist_m numeric,
        gps_p90_dist_m numeric,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        anomaly_tags text[],
        parent_lac_object_id text,
        run_id text NOT NULL,
        batch_id text NOT NULL,
        baseline_version text,
        sample_scope_tag text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.obj_lac (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        lifecycle_state text NOT NULL,
        health_state text NOT NULL,
        existence_eligible boolean NOT NULL,
        anchorable boolean NOT NULL,
        baseline_eligible boolean NOT NULL,
        bs_count bigint NOT NULL,
        active_bs_count bigint NOT NULL,
        cell_count bigint NOT NULL,
        record_count bigint NOT NULL,
        gps_count bigint NOT NULL,
        active_days integer NOT NULL,
        center_lon double precision,
        center_lat double precision,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        region_quality_label text,
        anomaly_tags text[],
        run_id text NOT NULL,
        batch_id text NOT NULL,
        baseline_version text,
        sample_scope_tag text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.obj_state_history (
        history_id bigserial PRIMARY KEY,
        object_type text NOT NULL,
        object_id text NOT NULL,
        lifecycle_state text,
        health_state text,
        anchorable boolean,
        baseline_eligible boolean,
        changed_reason text,
        run_id text NOT NULL,
        batch_id text NOT NULL,
        changed_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.obj_relation_history (
        history_id bigserial PRIMARY KEY,
        relation_type text NOT NULL,
        parent_object_id text,
        child_object_id text,
        relation_status text,
        changed_reason text,
        run_id text NOT NULL,
        batch_id text NOT NULL,
        changed_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.baseline_cell (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        bs_id bigint,
        cell_id bigint NOT NULL,
        baseline_version text NOT NULL,
        center_lon double precision,
        center_lat double precision,
        gps_p50_dist_m numeric,
        gps_p90_dist_m numeric,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.baseline_bs (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        bs_id bigint NOT NULL,
        baseline_version text NOT NULL,
        center_lon double precision,
        center_lat double precision,
        gps_p50_dist_m numeric,
        gps_p90_dist_m numeric,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.baseline_lac (
        object_id text PRIMARY KEY,
        operator_code text NOT NULL,
        tech_norm text NOT NULL,
        lac text NOT NULL,
        baseline_version text NOT NULL,
        center_lon double precision,
        center_lat double precision,
        gps_original_ratio numeric,
        signal_original_ratio numeric,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);
  END LOOP;

  FOREACH s IN ARRAY ARRAY['rebuild3_meta', 'rebuild3_sample_meta'] LOOP
    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.run (
        run_id text PRIMARY KEY,
        run_type text NOT NULL,
        status text NOT NULL,
        scenario_key text,
        scenario_label text,
        init_days integer,
        step_hours integer,
        snapshot_source text,
        window_start timestamptz,
        window_end timestamptz,
        contract_version text NOT NULL,
        rule_set_version text NOT NULL,
        baseline_version text,
        note text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch (
        batch_id text PRIMARY KEY,
        run_id text NOT NULL,
        batch_type text NOT NULL,
        status text NOT NULL,
        scenario_key text,
        timepoint_role text,
        batch_seq integer,
        snapshot_at timestamptz,
        window_start timestamptz,
        window_end timestamptz,
        source_name text,
        contract_version text NOT NULL,
        rule_set_version text NOT NULL,
        baseline_version text,
        input_rows bigint,
        output_rows bigint,
        is_rerun boolean NOT NULL DEFAULT false,
        rerun_source_batch text,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.baseline_version (
        baseline_version text PRIMARY KEY,
        run_id text NOT NULL,
        batch_id text NOT NULL,
        rule_set_version text NOT NULL,
        refresh_reason text,
        object_count bigint,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch_snapshot (
        batch_id text NOT NULL,
        stage_name text NOT NULL,
        metric_name text NOT NULL,
        metric_value numeric NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (batch_id, stage_name, metric_name)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch_flow_summary (
        batch_id text NOT NULL,
        fact_layer text NOT NULL,
        row_count bigint NOT NULL,
        row_ratio numeric,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (batch_id, fact_layer)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch_decision_summary (
        batch_id text NOT NULL,
        decision_name text NOT NULL,
        object_type text,
        object_count bigint NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (batch_id, decision_name, object_type)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch_anomaly_summary (
        batch_id text NOT NULL,
        anomaly_level text NOT NULL,
        anomaly_name text NOT NULL,
        object_count bigint,
        fact_count bigint,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (batch_id, anomaly_level, anomaly_name)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.batch_baseline_refresh_log (
        batch_id text PRIMARY KEY,
        baseline_version text NOT NULL,
        refresh_reason text NOT NULL,
        triggered boolean NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.asset_table_catalog (
        asset_name text PRIMARY KEY,
        table_schema text NOT NULL,
        table_name text NOT NULL,
        table_type text NOT NULL,
        grain_desc text,
        primary_key_desc text,
        refresh_mode text,
        upstream_desc text,
        retention_policy text,
        owner_domain text,
        is_core boolean NOT NULL DEFAULT false,
        status text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.asset_field_catalog (
        asset_name text NOT NULL,
        field_name text NOT NULL,
        field_label_cn text,
        layer_name text,
        data_type text,
        is_nullable boolean,
        is_core boolean NOT NULL DEFAULT false,
        source_desc text,
        semantic_desc text,
        status text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asset_name, field_name)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.asset_usage_map (
        asset_type text NOT NULL,
        asset_name text NOT NULL,
        consumer_type text NOT NULL,
        consumer_name text NOT NULL,
        usage_role text NOT NULL,
        usage_desc text,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asset_type, asset_name, consumer_type, consumer_name)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.asset_migration_decision (
        asset_type text NOT NULL,
        asset_name text NOT NULL,
        decision text NOT NULL,
        target_asset text,
        decision_reason text,
        owner_note text,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asset_type, asset_name)
      )
    $sql$, s);

    EXECUTE format($sql$
      CREATE TABLE IF NOT EXISTS %I.compare_result (
        compare_scope text NOT NULL,
        metric_group text NOT NULL,
        metric_name text NOT NULL,
        rebuild2_value text,
        rebuild3_value text,
        diff_value numeric,
        diff_ratio numeric,
        diff_type text,
        severity text,
        is_blocking boolean NOT NULL DEFAULT false,
        explanation text,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (compare_scope, metric_group, metric_name)
      )
    $sql$, s);
  END LOOP;
END $$;
