-- ============================================================================
-- 03_workbench_meta_ddl.sql
-- Complete DDL for workbench (19 tables) + meta (5 tables) schemas
-- Plus initialization data (step_registry + default parameter_set)
-- Idempotent: DROP IF EXISTS CASCADE + CREATE
-- Generated: 2026-03-24  (from 05_工作台元数据DDL.md)
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS workbench;
CREATE SCHEMA IF NOT EXISTS meta;

-- ============================================================================
-- WORKBENCH SCHEMA (19 tables)
-- Order: referenced tables first to satisfy foreign keys
-- ============================================================================

-- --------------------------------------------------------------------------
-- 1. wb_parameter_set (referenced by wb_run)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_parameter_set CASCADE;
CREATE TABLE workbench.wb_parameter_set (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,
    description         text,
    parameters          jsonb           NOT NULL,
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

COMMENT ON COLUMN workbench.wb_parameter_set.parameters IS
'Complete parameter snapshot as JSON. Keys: global, step4, step30, step31, step35, step40, step50, step51, step52';

-- --------------------------------------------------------------------------
-- 2. wb_rule_set (referenced by wb_run)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_rule_set CASCADE;
CREATE TABLE workbench.wb_rule_set (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,
    description         text,
    rules               jsonb           NOT NULL,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 3. wb_sql_bundle (referenced by wb_run)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_sql_bundle CASCADE;
CREATE TABLE workbench.wb_sql_bundle (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,
    description         text,
    file_manifest       jsonb           NOT NULL,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 4. wb_contract (referenced by wb_run)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_contract CASCADE;
CREATE TABLE workbench.wb_contract (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,
    description         text,
    contract_fields     jsonb           NOT NULL,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 5. wb_step_registry (referenced by wb_step_execution, wb_step_metric, wb_rule_hit)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_step_registry CASCADE;
CREATE TABLE workbench.wb_step_registry (
    step_id             text            PRIMARY KEY,
    step_order          integer         NOT NULL,
    step_name           text            NOT NULL,
    step_name_en        text            NOT NULL,
    layer               text            NOT NULL,
    is_main_chain       boolean         NOT NULL DEFAULT true,
    input_tables        text[]          NOT NULL,
    output_tables       text[]          NOT NULL,
    sql_file            text,
    description         text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 6. wb_run (central run registry, references version tables)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_run CASCADE;
CREATE TABLE workbench.wb_run (
    run_id              serial          PRIMARY KEY,
    run_mode            text            NOT NULL,
    origin_scope        text            NOT NULL DEFAULT 'layer0_start',
    started_at          timestamptz     NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text            NOT NULL DEFAULT 'running',
    duration_seconds    integer,

    parameter_set_id    integer         REFERENCES workbench.wb_parameter_set(id),
    rule_set_id         integer         REFERENCES workbench.wb_rule_set(id),
    sql_bundle_id       integer         REFERENCES workbench.wb_sql_bundle(id),
    contract_id         integer         REFERENCES workbench.wb_contract(id),
    baseline_id         integer         REFERENCES workbench.wb_baseline(id) DEFERRABLE INITIALLY DEFERRED,

    input_window_start  date,
    input_window_end    date,
    compare_run_id      integer,
    shard_count         integer         DEFAULT 1,

    rerun_from_step     text,
    sample_set_id       integer,
    pseudo_daily_anchor date,

    triggered_by        text,
    note                text,

    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_run_started ON workbench.wb_run(started_at DESC);
CREATE INDEX idx_wb_run_status  ON workbench.wb_run(status);

-- --------------------------------------------------------------------------
-- 7. wb_baseline (references wb_run)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_baseline CASCADE;
CREATE TABLE workbench.wb_baseline (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,
    description         text,
    source_run_id       integer         REFERENCES workbench.wb_run(run_id),
    frozen_at           timestamptz,
    is_active           boolean         NOT NULL DEFAULT false,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- Now add the deferred FK from wb_run -> wb_baseline
-- (wb_baseline was just created, so the FK added in wb_run via DEFERRABLE is valid)

-- --------------------------------------------------------------------------
-- 8. wb_step_execution
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_step_execution CASCADE;
CREATE TABLE workbench.wb_step_execution (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    started_at          timestamptz     NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text            NOT NULL DEFAULT 'running',
    duration_seconds    integer,
    output_row_count    bigint,
    error_message       text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_step_exec_run ON workbench.wb_step_execution(run_id, step_id);

-- --------------------------------------------------------------------------
-- 9. wb_step_metric
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_step_metric CASCADE;
CREATE TABLE workbench.wb_step_metric (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    metric_code         text            NOT NULL,
    metric_name         text            NOT NULL,
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    value_num           numeric,
    value_text          text,
    value_json          jsonb,
    unit                text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_step_metric_run  ON workbench.wb_step_metric(run_id, step_id);
CREATE INDEX idx_wb_step_metric_code ON workbench.wb_step_metric(metric_code);

-- --------------------------------------------------------------------------
-- 10. wb_layer_snapshot
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_layer_snapshot CASCADE;
CREATE TABLE workbench.wb_layer_snapshot (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    layer_id            text            NOT NULL,
    row_count           bigint,
    pass_flag           boolean,
    pass_note           text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_layer_snap_run ON workbench.wb_layer_snapshot(run_id);

-- --------------------------------------------------------------------------
-- 11. wb_gate_result
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_gate_result CASCADE;
CREATE TABLE workbench.wb_gate_result (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    gate_code           text            NOT NULL,
    gate_name           text            NOT NULL,
    severity            text            NOT NULL,
    expected_rule       text,
    actual_value        numeric,
    pass_flag           boolean         NOT NULL,
    remark              text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_gate_run  ON workbench.wb_gate_result(run_id);
CREATE INDEX idx_wb_gate_pass ON workbench.wb_gate_result(pass_flag);

-- --------------------------------------------------------------------------
-- 12. wb_anomaly_stats
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_anomaly_stats CASCADE;
CREATE TABLE workbench.wb_anomaly_stats (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    object_level        text            NOT NULL,
    anomaly_type        text            NOT NULL,
    total_count         bigint          NOT NULL,
    anomaly_count       bigint          NOT NULL,
    anomaly_ratio       numeric,
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_anomaly_run ON workbench.wb_anomaly_stats(run_id);

-- --------------------------------------------------------------------------
-- 13. wb_reconciliation
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_reconciliation CASCADE;
CREATE TABLE workbench.wb_reconciliation (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    check_code          text            NOT NULL,
    check_name          text            NOT NULL,
    source_label        text,
    target_label        text,
    source_value        numeric,
    target_value        numeric,
    diff_value          numeric,
    pass_flag           boolean         NOT NULL,
    remark              text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 14. wb_rule_hit
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_rule_hit CASCADE;
CREATE TABLE workbench.wb_rule_hit (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    rule_code           text            NOT NULL,
    rule_name           text            NOT NULL,
    rule_purpose        text,
    hit_count           bigint,
    total_count         bigint,
    hit_ratio           numeric,
    key_params          jsonb,
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_rule_hit_run ON workbench.wb_rule_hit(run_id, step_id);

-- --------------------------------------------------------------------------
-- 15. wb_issue_log
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_issue_log CASCADE;
CREATE TABLE workbench.wb_issue_log (
    id                  serial          PRIMARY KEY,
    run_id              integer         REFERENCES workbench.wb_run(run_id),
    severity            text            NOT NULL,
    category            text,
    title               text            NOT NULL,
    description         text,
    evidence_sql        text,
    status              text            NOT NULL DEFAULT 'open',
    owner               text,
    resolved_at         timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 16. wb_patch_log
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_patch_log CASCADE;
CREATE TABLE workbench.wb_patch_log (
    id                  serial          PRIMARY KEY,
    issue_id            integer         REFERENCES workbench.wb_issue_log(id),
    patch_name          text            NOT NULL,
    affected_steps      text[],
    affected_tables     text[],
    description         text,
    merge_status        text            NOT NULL DEFAULT 'pending',
    merged_at           timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 17. wb_sample_set
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_sample_set CASCADE;
CREATE TABLE workbench.wb_sample_set (
    id                  serial          PRIMARY KEY,
    name                text            NOT NULL,
    description         text,
    sample_type         text            NOT NULL,
    filter_criteria     jsonb           NOT NULL,
    object_ids          jsonb,
    created_by          text,
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

COMMENT ON COLUMN workbench.wb_sample_set.filter_criteria IS
'Example: {"operator_id_raw":"46000","tech_norm":"4G","is_collision_suspect":true,"bs_id_range":[100,500]}';

-- --------------------------------------------------------------------------
-- 18. wb_object_snapshot
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_object_snapshot CASCADE;
CREATE TABLE workbench.wb_object_snapshot (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    object_level        text            NOT NULL,
    object_key          text            NOT NULL,
    object_id           text            NOT NULL,
    object_label        text,
    payload             jsonb           NOT NULL,
    rule_hits           jsonb           NOT NULL DEFAULT '[]'::jsonb,
    created_at          timestamptz     NOT NULL DEFAULT now(),

    UNIQUE(run_id, step_id, object_key)
);

CREATE INDEX idx_wb_object_snapshot_run_step
    ON workbench.wb_object_snapshot(run_id, step_id);

-- --------------------------------------------------------------------------
-- 19. wb_sample_snapshot
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS workbench.wb_sample_snapshot CASCADE;
CREATE TABLE workbench.wb_sample_snapshot (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    sample_set_id       integer         NOT NULL REFERENCES workbench.wb_sample_set(id),
    source_table        text            NOT NULL,
    rank_order          integer         NOT NULL,
    object_key          text            NOT NULL,
    object_label        text,
    record_payload      jsonb           NOT NULL,
    rule_hits           jsonb           NOT NULL DEFAULT '[]'::jsonb,
    created_at          timestamptz     NOT NULL DEFAULT now(),

    UNIQUE(run_id, sample_set_id, object_key)
);

CREATE INDEX idx_wb_sample_snapshot_run_set
    ON workbench.wb_sample_snapshot(run_id, sample_set_id, rank_order);

-- ============================================================================
-- META SCHEMA (5 tables)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 18. meta_field_registry (referenced by health, mapping_rule, change_log)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS meta.meta_field_registry CASCADE;
CREATE TABLE meta.meta_field_registry (
    id                  serial          PRIMARY KEY,
    field_name          text            NOT NULL,
    field_name_cn       text,
    table_name          text            NOT NULL,
    schema_name         text            NOT NULL DEFAULT 'pipeline',
    data_type           text            NOT NULL,
    is_nullable         boolean         NOT NULL DEFAULT true,
    source_field        text,
    source_table        text,
    lifecycle_status    text            NOT NULL DEFAULT 'active',
    introduced_version  text,
    description         text,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),

    UNIQUE(schema_name, table_name, field_name)
);

CREATE INDEX idx_meta_field_table  ON meta.meta_field_registry(table_name);
CREATE INDEX idx_meta_field_status ON meta.meta_field_registry(lifecycle_status);

-- --------------------------------------------------------------------------
-- 19. meta_field_health
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS meta.meta_field_health CASCADE;
CREATE TABLE meta.meta_field_health (
    id                  bigserial       PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    run_id              integer         NOT NULL,
    batch_label         text,

    total_rows          bigint,
    null_count          bigint,
    null_rate           numeric,
    distinct_count      bigint,
    zero_count          bigint,

    min_value           numeric,
    max_value           numeric,
    avg_value           numeric,
    p50_value           numeric,
    stddev_value        numeric,

    distribution_drift  numeric,
    is_anomalous        boolean         NOT NULL DEFAULT false,
    anomaly_reason      text,

    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_health_field ON meta.meta_field_health(field_id, run_id);

-- --------------------------------------------------------------------------
-- 20. meta_field_mapping_rule
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS meta.meta_field_mapping_rule CASCADE;
CREATE TABLE meta.meta_field_mapping_rule (
    id                  serial          PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    rule_type           text            NOT NULL,
    rule_expression     text            NOT NULL,
    source_field        text,
    source_table        text,
    priority            integer         NOT NULL DEFAULT 0,
    is_active           boolean         NOT NULL DEFAULT true,
    version_tag         text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 21. meta_field_change_log
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS meta.meta_field_change_log CASCADE;
CREATE TABLE meta.meta_field_change_log (
    id                  bigserial       PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    change_type         text            NOT NULL,
    old_value           text,
    new_value           text,
    reason              text,
    changed_by          text,
    contract_version    text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_change_field ON meta.meta_field_change_log(field_id);

-- --------------------------------------------------------------------------
-- 22. meta_exposure_matrix
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS meta.meta_exposure_matrix CASCADE;
CREATE TABLE meta.meta_exposure_matrix (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL,
    object_level        text            NOT NULL,
    field_name          text            NOT NULL,
    total_objects       bigint          NOT NULL,
    exposed_objects     bigint          NOT NULL,
    exposure_rate       numeric,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_exposure_run ON meta.meta_exposure_matrix(run_id, object_level);

COMMIT;

-- ============================================================================
-- INITIALIZATION DATA
-- ============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Step registry (22 steps)
-- --------------------------------------------------------------------------
DELETE FROM workbench.wb_step_registry;

INSERT INTO workbench.wb_step_registry (step_id, step_order, step_name, step_name_en, layer, is_main_chain, input_tables, output_tables, sql_file) VALUES
('s0',  10, '数据标准化',     'Standardization',          'L2', true,  ARRAY['raw_records'],                     ARRAY['raw_records'],           '00_step0_std_views.sql'),
('s1',  20, '基础统计',       'Base Statistics',           'L2', true,  ARRAY['raw_records'],                     ARRAY['stats_base_raw'],        '01_step1_base_stats.sql'),
('s2',  30, '合规标记',       'Compliance Marking',        'L2', true,  ARRAY['raw_records'],                     ARRAY['fact_filtered'],          '02_step2_compliance_mark.sql'),
('s3',  40, 'LAC统计',        'LAC Statistics',            'L2', true,  ARRAY['fact_filtered'],                    ARRAY['stats_lac'],             '03_step3_lac_stats_db.sql'),
('s4',  50, '可信LAC',        'Trusted LAC Library',       'L2', true,  ARRAY['stats_lac'],                       ARRAY['dim_lac_trusted'],       '04_step4_master_lac_lib.sql'),
('s5',  60, 'Cell统计',       'Cell Statistics',           'L2', true,  ARRAY['fact_filtered','dim_lac_trusted'],  ARRAY['dim_cell_stats'],        '05_step5_cellid_stats_and_anomalies.sql'),
('s6',  70, '合规过滤',       'Compliance Filtering',      'L2', true,  ARRAY['raw_records','dim_cell_stats'],     ARRAY['fact_filtered'],         '06_step6_apply_mapping_and_compare.sql'),
('s30', 80, 'BS主库',         'Master BS Library',         'L3', true,  ARRAY['fact_filtered','dim_lac_trusted','dim_cell_stats'], ARRAY['dim_bs_trusted'], '30_step30_master_bs_library.sql'),
('s31', 90, 'GPS修正',        'GPS Correction',            'L3', true,  ARRAY['fact_filtered','dim_bs_trusted'],   ARRAY['fact_gps_corrected'],    '31_step31_cell_gps_fixed.sql'),
('s32', 100,'GPS对比',        'GPS Comparison',            'L3', true,  ARRAY['fact_gps_corrected','dim_bs_trusted'], ARRAY['compare_gps'],        '32_step32_compare.sql'),
('s33', 110,'信号补齐',       'Signal Fill',               'L3', true,  ARRAY['fact_gps_corrected'],              ARRAY['fact_signal_filled'],    '33_step33_signal_fill_simple.sql'),
('s34', 120,'信号对比',       'Signal Comparison',         'L3', true,  ARRAY['fact_signal_filled'],              ARRAY['compare_signal'],        '34_step34_signal_compare.sql'),
('s35', 130,'动态检测',       'Dynamic Cell Detection',    'L3', false, ARRAY['dim_bs_trusted','fact_gps_corrected'], ARRAY['profile_cell'],        '35_step35_dynamic_cell_bs_detection.sql'),
('s36', 140,'BS异常标记',     'BS ID Anomaly Mark',        'L3', false, ARRAY['dim_bs_trusted'],                  ARRAY['detect_anomaly_bs'],     '36_step36_bs_id_anomaly_mark.sql'),
('s37', 150,'碰撞不足标记',   'Collision Insufficient Mark','L3', false, ARRAY['dim_bs_trusted'],                 ARRAY['detect_collision'],      '37_step37_collision_data_insufficient_mark.sql'),
('s38', 160,'Cell映射交付',   'Cell-BS Map Delivery',      'L3', true,  ARRAY['dim_bs_trusted','fact_gps_corrected'], ARRAY['map_cell_bs'],        '40_layer3_delivery_bs_cell_tables.sql'),
('s40', 170,'完整回归GPS',    'Full Return GPS',           'L4', true,  ARRAY['raw_records','dim_bs_trusted','dim_lac_trusted','dim_cell_stats'], ARRAY['fact_final'], '40_step40_cell_gps_filter_fill.sql'),
('s41', 180,'完整回归信号',   'Full Return Signal',        'L4', true,  ARRAY['fact_final'],                      ARRAY['fact_final'],            '41_step41_cell_signal_fill.sql'),
('s42', 190,'最终对比',       'Final Comparison',          'L4', true,  ARRAY['raw_records','fact_final'],         ARRAY['compare_gps','compare_signal'], '42_step42_compare.sql'),
('s50', 200,'LAC画像',        'LAC Profile',               'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_lac'],           '50_step50_lac_profile.sql'),
('s51', 210,'BS画像',         'BS Profile',                'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_bs'],            '51_step51_bs_profile.sql'),
('s52', 220,'Cell画像',       'Cell Profile',              'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_cell'],          '52_step52_cell_profile.sql');

-- --------------------------------------------------------------------------
-- Default parameter set (P-001)
-- --------------------------------------------------------------------------
DELETE FROM workbench.wb_parameter_set WHERE version_tag = 'P-001';

INSERT INTO workbench.wb_parameter_set (version_tag, description, parameters) VALUES
('P-001', '初始参数集（基于现有SQL硬编码值）', '{
  "global": {
    "operator_whitelist": ["46000","46001","46011","46015","46020"],
    "tech_whitelist": ["4G","5G"],
    "china_bbox": {"lon_min":73,"lon_max":135,"lat_min":3,"lat_max":54},
    "lac_overflow_values": [65534,65535,16777214,16777215,2147483647],
    "rsrp_invalid_values": [-110,-1],
    "rsrp_max_valid": -1
  },
  "step4": {"active_days_threshold":7,"min_device_count":5,"min_device_count_5g":3,"report_count_percentile":80},
  "step30": {"outlier_dist_m":2500,"collision_p90_dist_m":1500,"signal_top_n":50,"center_bin_scale":10000},
  "step31": {"drift_dist_m":1500},
  "step35": {"min_bs_p90_m":5000,"min_half_major_dist_km":10,"min_effective_days":5,"grid_round_decimals":3,"min_day_major_share":0.50,"min_half_major_day_share":0.60},
  "step40": {"gps_dist_threshold_4g":1000,"gps_dist_threshold_5g":500},
  "step50": {"min_rows":5000,"gps_p90_warn_m":100000},
  "step51": {"min_rows":500,"gps_p90_warn_4g_m":1000,"gps_p90_warn_5g_m":500},
  "step52": {"min_rows":200,"gps_p90_warn_4g_m":1000,"gps_p90_warn_5g_m":500}
}'::jsonb);

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
DECLARE
    _wb  integer;
    _meta integer;
    _steps integer;
BEGIN
    SELECT count(*) INTO _wb
    FROM information_schema.tables
    WHERE table_schema = 'workbench' AND table_type = 'BASE TABLE';

    SELECT count(*) INTO _meta
    FROM information_schema.tables
    WHERE table_schema = 'meta' AND table_type = 'BASE TABLE';

    SELECT count(*) INTO _steps
    FROM workbench.wb_step_registry;

    RAISE NOTICE 'workbench schema: % tables', _wb;
    RAISE NOTICE 'meta schema: % tables', _meta;
    RAISE NOTICE 'step_registry rows: %', _steps;
END
$$;
