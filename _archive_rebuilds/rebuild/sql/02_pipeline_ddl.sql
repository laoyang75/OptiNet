-- ============================================================================
-- 02_pipeline_ddl.sql
-- Complete DDL for pipeline schema (18 tables)
-- Idempotent: DROP IF EXISTS + CREATE
-- Generated: 2026-03-24  (from PG17 information_schema introspection)
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS pipeline;

-- ============================================================================
-- 1. raw_records -- Layer 0 raw data intake
-- ============================================================================
DROP TABLE IF EXISTS pipeline.raw_records CASCADE;
CREATE TABLE pipeline.raw_records (
    seq_id              bigint,
    record_id           varchar(100),
    cell_ts_raw         text,
    cell_ts_std         timestamptz,
    tech                text,
    operator_id_cn      text,
    lac_raw_text        text,
    cell_id             text,
    lac_dec             bigint,
    lac_hex             text,
    cell_id_dec         bigint,
    cell_id_hex         text,
    bs_id               bigint,
    sector_id           bigint,
    gps_raw             varchar(200),
    lon_raw             double precision,
    lat_raw             double precision,
    gps_final           text,
    lon                 double precision,
    lat                 double precision,
    gps_info_type       varchar(45),
    data_source         varchar(45),
    beijing_source      varchar(45),
    did                 varchar(200),
    ts_raw              varchar(45),
    ts_std              timestamp,
    ip                  varchar(45),
    sdk_ver             varchar(45),
    brand               varchar(45),
    model               varchar(45),
    oaid                varchar(200),
    parsed_from         text,
    match_status        text,
    sig_rsrp            integer,
    sig_rsrq            integer,
    sig_sinr            integer,
    sig_rssi            integer,
    sig_dbm             integer,
    sig_asu_level       integer,
    sig_level           integer,
    sig_ss              integer,
    is_connected        boolean,
    source_table        text            NOT NULL,
    operator_id_raw     text
);

COMMENT ON TABLE pipeline.raw_records IS 'Layer0: raw data from MaxCompute, one row per observation record';

CREATE INDEX IF NOT EXISTS idx_raw_records_biz
    ON pipeline.raw_records (operator_id_raw, tech, lac_dec, cell_id_dec);
CREATE INDEX IF NOT EXISTS idx_raw_records_seq
    ON pipeline.raw_records (seq_id);

-- ============================================================================
-- 2. stats_base_raw -- Step 1 base statistics
-- ============================================================================
DROP TABLE IF EXISTS pipeline.stats_base_raw CASCADE;
CREATE TABLE pipeline.stats_base_raw (
    tech_norm           text,
    operator_id_raw     text,
    operator_group_hint text,
    parsed_from         text,
    row_cnt             bigint,
    cell_cnt            bigint,
    lac_cnt             bigint,
    device_cnt          bigint,
    no_cellid_rows      bigint,
    no_lac_rows         bigint,
    no_gps_rows         bigint,
    row_pct             numeric,
    no_cellid_pct       numeric,
    no_lac_pct          numeric,
    no_gps_pct          numeric
);

COMMENT ON TABLE pipeline.stats_base_raw IS 'Step1: base statistics per tech/operator/source breakdown';

-- ============================================================================
-- 3. stats_lac -- Step 3 LAC statistics
-- ============================================================================
DROP TABLE IF EXISTS pipeline.stats_lac CASCADE;
CREATE TABLE pipeline.stats_lac (
    operator_id_raw     text,
    operator_group_hint text,
    tech_norm           text,
    lac_dec             bigint,
    record_count        bigint,
    valid_gps_count     bigint,
    distinct_cellid_count bigint,
    distinct_device_count bigint,
    first_seen_ts       timestamp,
    last_seen_ts        timestamp,
    first_seen_date     date,
    last_seen_date      date,
    active_days         integer
);

COMMENT ON TABLE pipeline.stats_lac IS 'Step3: LAC-level aggregated statistics';

-- ============================================================================
-- 4. dim_lac_trusted -- Step 4 trusted LAC library
-- ============================================================================
DROP TABLE IF EXISTS pipeline.dim_lac_trusted CASCADE;
CREATE TABLE pipeline.dim_lac_trusted (
    operator_id_raw     text            NOT NULL,
    operator_group_hint text,
    tech_norm           text            NOT NULL,
    lac_dec             bigint          NOT NULL,
    record_count        bigint,
    valid_gps_count     bigint,
    distinct_cellid_count bigint,
    distinct_device_count bigint,
    first_seen_ts       timestamp,
    last_seen_ts        timestamp,
    first_seen_date     date,
    last_seen_date      date,
    active_days         integer,
    lac_confidence_score bigint,
    lac_confidence_rank integer,
    is_trusted_lac      boolean,

    UNIQUE (operator_id_raw, tech_norm, lac_dec)
);

COMMENT ON TABLE pipeline.dim_lac_trusted IS 'Step4: trusted LAC dimension with confidence scoring';

-- ============================================================================
-- 5. dim_cell_stats -- Step 5 cell statistics
-- ============================================================================
DROP TABLE IF EXISTS pipeline.dim_cell_stats CASCADE;
CREATE TABLE pipeline.dim_cell_stats (
    operator_id_raw     text            NOT NULL,
    operator_group_hint text,
    tech_norm           text            NOT NULL,
    lac_dec             bigint          NOT NULL,
    cell_id_dec         bigint          NOT NULL,
    record_count        bigint,
    valid_gps_count     bigint,
    distinct_device_count bigint,
    first_seen_ts       timestamp,
    last_seen_ts        timestamp,
    first_seen_date     date,
    last_seen_date      date,
    active_days         integer,
    gps_center_lon      double precision,
    gps_center_lat      double precision,

    UNIQUE (operator_id_raw, tech_norm, lac_dec, cell_id_dec)
);

COMMENT ON TABLE pipeline.dim_cell_stats IS 'Step5: cell-level aggregated statistics';

CREATE INDEX IF NOT EXISTS idx_dim_cell_stats_cell
    ON pipeline.dim_cell_stats (operator_id_raw, tech_norm, cell_id_dec);

-- ============================================================================
-- 6. fact_filtered -- Step 2/6 compliance-filtered fact records
-- ============================================================================
DROP TABLE IF EXISTS pipeline.fact_filtered CASCADE;
CREATE TABLE pipeline.fact_filtered (
    seq_id              bigint          NOT NULL PRIMARY KEY,
    record_id           varchar(100),
    cell_ts_raw         text,
    cell_ts_std         timestamptz,
    tech                text,
    operator_id_cn      text,
    lac_raw_text        text,
    cell_id             text,
    lac_dec             bigint,
    lac_hex             text,
    cell_id_dec         bigint,
    cell_id_hex         text,
    bs_id               bigint,
    sector_id           bigint,
    gps_raw             varchar(200),
    lon_raw             double precision,
    lat_raw             double precision,
    gps_final           text,
    lon                 double precision,
    lat                 double precision,
    gps_info_type       varchar(45),
    data_source         varchar(45),
    beijing_source      varchar(45),
    did                 varchar(200),
    ts_raw              varchar(45),
    ts_std              timestamp,
    ip                  varchar(45),
    sdk_ver             varchar(45),
    brand               varchar(45),
    model               varchar(45),
    oaid                varchar(200),
    parsed_from         text,
    match_status        text,
    is_connected        boolean,
    operator_id_raw     text,
    device_id           text,
    tech_norm           text,
    operator_group_hint text,
    report_date         date,
    lac_len             integer,
    cell_len            integer,
    has_cellid          boolean,
    has_lac             boolean,
    has_gps             boolean,
    sig_rsrp            integer,
    sig_rsrq            integer,
    sig_sinr            integer,
    sig_rssi            integer,
    sig_dbm             integer,
    sig_asu_level       integer,
    sig_level           integer,
    sig_ss              integer,
    lac_choice_cnt      bigint,
    lac_dec_from_map    bigint,
    is_original_lac_trusted boolean,
    best_lac_dec        bigint,
    lac_dec_final       bigint,
    lac_enrich_status   text,
    is_final_lac_trusted boolean,
    is_lac_changed_by_mapping boolean,
    lac_dec_raw         bigint,
    lac_hex_raw         text,
    lac_output_normalized boolean
);

COMMENT ON TABLE pipeline.fact_filtered IS 'Step2/6: compliance-filtered records with LAC enrichment';

CREATE INDEX IF NOT EXISTS idx_fact_filtered_biz
    ON pipeline.fact_filtered (operator_id_raw, tech_norm, lac_dec_final, cell_id_dec);
CREATE INDEX IF NOT EXISTS idx_fact_filtered_date
    ON pipeline.fact_filtered (report_date);

-- ============================================================================
-- 7. dim_bs_trusted -- Step 30 master BS library
-- ============================================================================
DROP TABLE IF EXISTS pipeline.dim_bs_trusted CASCADE;
CREATE TABLE pipeline.dim_bs_trusted (
    tech_norm           text            NOT NULL,
    bs_id               bigint          NOT NULL,
    wuli_fentong_bs_key text,
    lac_dec_final       bigint          NOT NULL,
    shared_operator_cnt integer,
    shared_operator_list text,
    is_multi_operator_shared boolean,
    gps_valid_cell_cnt  integer,
    gps_valid_point_cnt bigint,
    gps_valid_level     text,
    bs_center_lon       double precision,
    bs_center_lat       double precision,
    gps_p50_dist_m      double precision,
    gps_p90_dist_m      double precision,
    gps_max_dist_m      double precision,
    outlier_removed_cnt bigint,
    is_collision_suspect boolean,
    collision_reason    text,
    anomaly_cell_cnt    bigint,
    first_seen_ts       timestamp,
    last_seen_ts        timestamp,
    active_days         integer,

    UNIQUE (tech_norm, bs_id, lac_dec_final)
);

COMMENT ON TABLE pipeline.dim_bs_trusted IS 'Step30: master base-station dimension with GPS/collision profiles';

CREATE INDEX IF NOT EXISTS idx_dim_bs_collision
    ON pipeline.dim_bs_trusted (is_collision_suspect);
CREATE INDEX IF NOT EXISTS idx_dim_bs_gps_level
    ON pipeline.dim_bs_trusted (gps_valid_level);

-- ============================================================================
-- 8. fact_gps_corrected -- Step 31 GPS-corrected fact
-- ============================================================================
DROP TABLE IF EXISTS pipeline.fact_gps_corrected CASCADE;
CREATE TABLE pipeline.fact_gps_corrected (
    src_seq_id          bigint          NOT NULL PRIMARY KEY,
    src_record_id       varchar(100),
    operator_id_raw     text,
    operator_group_hint text,
    tech_norm           text,
    bs_id               bigint,
    sector_id           bigint,
    cell_id_dec         bigint,
    lac_dec_final       bigint,
    wuli_fentong_bs_key text,
    gps_status          text,
    gps_status_final    text,
    gps_source          text,
    is_from_risk_bs     boolean,
    gps_dist_to_bs_m    double precision,
    lon_raw             double precision,
    lat_raw             double precision,
    lon_final           double precision,
    lat_final           double precision,
    gps_valid_level     text,
    is_collision_suspect boolean,
    is_multi_operator_shared boolean,
    shared_operator_list text,
    shared_operator_cnt integer,
    ts_std              timestamp,
    report_date         date,
    sig_rsrp            integer,
    sig_rsrq            integer,
    sig_sinr            integer,
    sig_rssi            integer,
    sig_dbm             integer,
    sig_asu_level       integer,
    sig_level           integer,
    sig_ss              integer,
    parsed_from         text,
    match_status        text,
    data_source         varchar(45),
    beijing_source      varchar(45),
    did                 varchar(200)
);

COMMENT ON TABLE pipeline.fact_gps_corrected IS 'Step31: records with GPS coordinates corrected to BS center when drifted';

CREATE INDEX IF NOT EXISTS idx_fact_gps_biz
    ON pipeline.fact_gps_corrected (operator_id_raw, tech_norm, bs_id, cell_id_dec);
CREATE INDEX IF NOT EXISTS idx_fact_gps_date
    ON pipeline.fact_gps_corrected (report_date);

-- ============================================================================
-- 9. compare_gps -- Step 32 GPS comparison report
-- ============================================================================
DROP TABLE IF EXISTS pipeline.compare_gps CASCADE;
CREATE TABLE pipeline.compare_gps (
    report_section      text,
    operator_id_raw     text,
    tech_norm           text,
    report_date         date,
    metric_code         text,
    metric_name_cn      text,
    expected_rule_cn    text,
    actual_value_num    numeric,
    pass_flag           text,
    remark_cn           text
);

COMMENT ON TABLE pipeline.compare_gps IS 'Step32/42: GPS before-vs-after comparison metrics report';

-- ============================================================================
-- 10. fact_signal_filled -- Step 33 signal-filled fact
-- ============================================================================
DROP TABLE IF EXISTS pipeline.fact_signal_filled CASCADE;
CREATE TABLE pipeline.fact_signal_filled (
    src_seq_id          bigint          NOT NULL PRIMARY KEY,
    src_record_id       varchar(100),
    operator_id_raw     text,
    operator_group_hint text,
    tech_norm           text,
    bs_id               bigint,
    sector_id           bigint,
    cell_id_dec         bigint,
    lac_dec_final       bigint,
    wuli_fentong_bs_key text,
    report_date         date,
    ts_std              timestamp,
    gps_status          text,
    gps_status_final    text,
    gps_source          text,
    is_from_risk_bs     boolean,
    lon_final           double precision,
    lat_final           double precision,
    signal_fill_source  text,
    signal_missing_before_cnt integer,
    signal_missing_after_cnt  integer,
    sig_rsrp_final      integer,
    sig_rsrq_final      integer,
    sig_sinr_final      integer,
    sig_rssi_final      integer,
    sig_dbm_final       integer,
    sig_asu_level_final integer,
    sig_level_final     integer,
    sig_ss_final        integer
);

COMMENT ON TABLE pipeline.fact_signal_filled IS 'Step33: records with missing signal fields filled from same-cell/BS-top donors';

CREATE INDEX IF NOT EXISTS idx_fact_signal_biz
    ON pipeline.fact_signal_filled (operator_id_raw, tech_norm, bs_id);
CREATE INDEX IF NOT EXISTS idx_fact_signal_source
    ON pipeline.fact_signal_filled (signal_fill_source);

-- ============================================================================
-- 11. compare_signal -- Step 34 signal comparison report
-- ============================================================================
DROP TABLE IF EXISTS pipeline.compare_signal CASCADE;
CREATE TABLE pipeline.compare_signal (
    report_section      text,
    operator_id_raw     text,
    tech_norm           text,
    report_date         date,
    signal_fill_source  text,
    metric_code         text,
    metric_name_cn      text,
    expected_rule_cn    text,
    actual_value_num    numeric,
    pass_flag           text,
    remark_cn           text
);

COMMENT ON TABLE pipeline.compare_signal IS 'Step34/42: signal before-vs-after comparison metrics report';

-- ============================================================================
-- 12. detect_collision -- Step 37 collision / data-insufficient detection
-- ============================================================================
DROP TABLE IF EXISTS pipeline.detect_collision CASCADE;
CREATE TABLE pipeline.detect_collision (
    tech_norm           text,
    bs_id               bigint,
    lac_dec_final       bigint,
    wuli_fentong_bs_key text,
    shared_operator_cnt integer,
    shared_operator_list text,
    is_multi_operator_shared boolean,
    gps_valid_level     text,
    gps_valid_cell_cnt  integer,
    gps_valid_point_cnt bigint,
    active_days         integer,
    gps_p50_dist_m      double precision,
    gps_p90_dist_m      double precision,
    gps_max_dist_m      double precision,
    is_collision_suspect boolean,
    collision_reason    text,
    low_point_bucket    text,
    triage_reason       text,
    triage_action       text
);

COMMENT ON TABLE pipeline.detect_collision IS 'Step37: BS-level collision suspect and data-insufficient triage';

-- ============================================================================
-- 13. detect_anomaly_bs -- Step 36 BS ID anomaly marking
-- ============================================================================
DROP TABLE IF EXISTS pipeline.detect_anomaly_bs CASCADE;
CREATE TABLE pipeline.detect_anomaly_bs (
    tech_norm           text,
    bs_id               bigint,
    bs_id_hex           text,
    lac_dec_final       bigint,
    wuli_fentong_bs_key text,
    is_multi_operator_shared boolean,
    shared_operator_cnt integer,
    shared_operator_list text,
    operator_cnt        integer,
    operator_list       text,
    bs_id_hex_len       integer,
    anomaly_reason      text
);

COMMENT ON TABLE pipeline.detect_anomaly_bs IS 'Step36: BS ID anomaly markers (short hex, multi-operator, etc.)';

-- ============================================================================
-- 14. map_cell_bs -- Layer 3 delivery: Cell-to-BS mapping
-- ============================================================================
DROP TABLE IF EXISTS pipeline.map_cell_bs CASCADE;
CREATE TABLE pipeline.map_cell_bs (
    operator_id_raw     text            NOT NULL,
    tech_norm           text            NOT NULL,
    cell_id_dec         bigint          NOT NULL,
    cell_id_hex         text,
    bs_id               bigint          NOT NULL,
    bs_id_hex           text,
    lac_dec_final       bigint,
    lac_hex             text,
    wuli_fentong_bs_key text,
    device_cnt          bigint,
    report_cnt          bigint,
    cell_total_report_cnt numeric,
    active_days         integer,
    first_seen_ts       timestamp,
    last_seen_ts        timestamp,
    bucket_cnt_per_cell bigint,
    is_ambiguous_mapping boolean,
    gps_valid_level     text,
    bs_center_lon       double precision,
    bs_center_lat       double precision,
    is_collision_suspect boolean,
    is_multi_operator_shared boolean,
    shared_operator_list text,

    UNIQUE (operator_id_raw, tech_norm, cell_id_dec, bs_id)
);

COMMENT ON TABLE pipeline.map_cell_bs IS 'Layer3 delivery: deterministic Cell-to-BS mapping table';

CREATE INDEX IF NOT EXISTS idx_map_cell_bs_lac
    ON pipeline.map_cell_bs (lac_dec_final);
CREATE INDEX IF NOT EXISTS idx_map_cell_bs_ambig
    ON pipeline.map_cell_bs (is_ambiguous_mapping);

-- ============================================================================
-- 15. fact_final -- Step 40/41 full-return final fact
-- ============================================================================
DROP TABLE IF EXISTS pipeline.fact_final CASCADE;
CREATE TABLE pipeline.fact_final (
    seq_id              bigint          NOT NULL PRIMARY KEY,
    record_id           varchar(100),
    cell_ts_std         timestamptz,
    tech                text,
    operator_id_cn      text,
    cell_id             text,
    lac_dec             bigint,
    cell_id_dec         bigint,
    bs_id               bigint,
    sector_id           bigint,
    lon_raw             double precision,
    lat_raw             double precision,
    data_source         varchar(45),
    beijing_source      varchar(45),
    did                 varchar(200),
    ts_std              timestamp,
    parsed_from         text,
    match_status        text,
    is_connected        boolean,
    operator_id_raw     text,
    tech_norm           text,
    bs_id_final         bigint,
    lac_dec_final       bigint,
    wuli_fentong_bs_key text,
    bs_shard_key        text,
    gps_valid_level     text,
    bs_center_lon       double precision,
    bs_center_lat       double precision,
    is_collision_suspect boolean,
    collision_reason    text,
    bs_gps_valid_point_cnt bigint,
    bs_gps_p50_dist_m   double precision,
    bs_anomaly_cell_cnt bigint,
    is_multi_operator_shared boolean,
    shared_operator_list text,
    shared_operator_cnt integer,
    gps_in_china        boolean,
    gps_dist_to_bs_m    double precision,
    dist_threshold_m    double precision,
    is_severe_collision boolean,
    gps_status          text,
    is_from_risk_bs     boolean,
    lon_before_fix      double precision,
    lat_before_fix      double precision,
    is_bs_id_lt_256     boolean,
    gps_fix_strategy    text,
    lon_final           double precision,
    lat_final           double precision,
    gps_source          text,
    gps_status_final    text,
    ts_fill             timestamp,
    bs_group_key        text,
    is_dynamic_cell     boolean,
    dynamic_reason      text,
    half_major_dist_km  double precision,
    has_any_signal      boolean,
    signal_missing_before_cnt integer,
    cell_donor_seq_id   bigint,
    bs_top_cell_id_dec  bigint,
    is_bs_top_cell      boolean,
    signal_donor_seq_id bigint,
    signal_fill_source  text,
    signal_donor_ts_fill timestamp,
    signal_donor_cell_id_dec bigint,
    sig_rsrp_final      integer,
    sig_rsrq_final      integer,
    sig_sinr_final      integer,
    sig_rssi_final      integer,
    sig_dbm_final       integer,
    sig_asu_level_final integer,
    sig_level_final     integer,
    sig_ss_final        integer,
    signal_missing_after_cnt integer,
    signal_filled_field_cnt  integer
);

COMMENT ON TABLE pipeline.fact_final IS 'Step40/41: final enriched fact table with GPS correction + signal fill';

CREATE INDEX IF NOT EXISTS idx_fact_final_biz
    ON pipeline.fact_final (operator_id_raw, tech_norm, bs_id_final, cell_id_dec);
CREATE INDEX IF NOT EXISTS idx_fact_final_date
    ON pipeline.fact_final (ts_std);
CREATE INDEX IF NOT EXISTS idx_fact_final_lac
    ON pipeline.fact_final (lac_dec_final);

-- ============================================================================
-- 16. profile_lac -- Step 50 LAC profile
-- ============================================================================
DROP TABLE IF EXISTS pipeline.profile_lac CASCADE;
CREATE TABLE pipeline.profile_lac (
    operator_id_cn      text            NOT NULL,
    tech_norm           text            NOT NULL,
    lac_dec             bigint          NOT NULL,
    record_count        bigint,
    first_seen_ts       timestamptz,
    last_seen_ts        timestamptz,
    active_days         integer,
    distinct_bs_count   bigint,
    distinct_cell_count bigint,
    gps_valid_count     bigint,
    gps_missing_count   bigint,
    gps_valid_ratio     numeric,
    gps_center_lon      double precision,
    gps_center_lat      double precision,
    lon_min             double precision,
    lon_max             double precision,
    lat_min             double precision,
    lat_max             double precision,
    gps_dist_p50_m      numeric,
    gps_dist_p90_m      numeric,
    gps_dist_max_m      numeric,
    rsrp_nonnull_count  bigint,
    rsrq_nonnull_count  bigint,
    sinr_nonnull_count  bigint,
    rssi_nonnull_count  bigint,
    dbm_nonnull_count   bigint,
    asu_level_nonnull_count bigint,
    level_nonnull_count bigint,
    ss_nonnull_count    bigint,
    rsrp_valid_ratio    numeric,
    rsrq_valid_ratio    numeric,
    sinr_valid_ratio    numeric,
    dbm_valid_ratio     numeric,
    native_signal_count bigint,
    native_nosignal_count bigint,
    fill_needed_count   bigint,
    fill_success_count  bigint,
    fill_same_cell_count bigint,
    fill_bs_top_count   bigint,
    fill_failed_count   bigint,
    missing_fields_before bigint,
    missing_fields_after bigint,
    filled_fields_total bigint,
    multi_operator_bs_count bigint,
    has_multi_operator_bs boolean,
    is_insufficient_sample boolean,
    has_gps_profile     boolean,
    is_gps_unstable     boolean,

    UNIQUE (operator_id_cn, tech_norm, lac_dec)
);

COMMENT ON TABLE pipeline.profile_lac IS 'Step50: LAC-level quality & signal profile';

-- ============================================================================
-- 17. profile_bs -- Step 51 BS profile
-- ============================================================================
DROP TABLE IF EXISTS pipeline.profile_bs CASCADE;
CREATE TABLE pipeline.profile_bs (
    operator_id_cn      text            NOT NULL,
    tech_norm           text            NOT NULL,
    lac_dec             bigint          NOT NULL,
    bs_id               bigint          NOT NULL,
    wuli_fentong_bs_key text,
    record_count        bigint,
    first_seen_ts       timestamptz,
    last_seen_ts        timestamptz,
    active_days         integer,
    distinct_cell_count bigint,
    gps_valid_count     bigint,
    gps_missing_count   bigint,
    gps_valid_ratio     numeric,
    gps_center_lon      double precision,
    gps_center_lat      double precision,
    gps_dist_p50_m      numeric,
    gps_dist_p90_m      numeric,
    gps_dist_max_m      numeric,
    rsrp_nonnull_count  bigint,
    rsrq_nonnull_count  bigint,
    sinr_nonnull_count  bigint,
    rssi_nonnull_count  bigint,
    dbm_nonnull_count   bigint,
    asu_level_nonnull_count bigint,
    level_nonnull_count bigint,
    ss_nonnull_count    bigint,
    rsrp_valid_ratio    numeric,
    rsrq_valid_ratio    numeric,
    sinr_valid_ratio    numeric,
    dbm_valid_ratio     numeric,
    native_signal_count bigint,
    native_nosignal_count bigint,
    fill_needed_count   bigint,
    fill_success_count  bigint,
    fill_same_cell_count bigint,
    fill_bs_top_count   bigint,
    fill_failed_count   bigint,
    missing_fields_before bigint,
    missing_fields_after bigint,
    filled_fields_total bigint,
    is_collision_suspect boolean,
    is_severe_collision boolean,
    collision_reason    text,
    gps_drift_count     bigint,
    gps_drift_ratio     numeric,
    dynamic_cell_count  bigint,
    has_dynamic_cell    boolean,
    is_insufficient_sample boolean,
    has_gps_profile     boolean,
    is_gps_unstable     boolean,
    is_bs_id_lt_256     boolean,
    is_multi_operator_shared boolean,
    shared_operator_cnt integer,
    shared_operator_list text,

    UNIQUE (operator_id_cn, tech_norm, lac_dec, bs_id)
);

COMMENT ON TABLE pipeline.profile_bs IS 'Step51: BS-level quality, signal & risk profile';

CREATE INDEX IF NOT EXISTS idx_profile_bs_collision
    ON pipeline.profile_bs (is_collision_suspect);
CREATE INDEX IF NOT EXISTS idx_profile_bs_unstable
    ON pipeline.profile_bs (is_gps_unstable);

-- ============================================================================
-- 18. profile_cell -- Step 52 Cell profile
-- ============================================================================
DROP TABLE IF EXISTS pipeline.profile_cell CASCADE;
CREATE TABLE pipeline.profile_cell (
    operator_id_cn      text            NOT NULL,
    tech_norm           text            NOT NULL,
    lac_dec             bigint          NOT NULL,
    bs_id               bigint          NOT NULL,
    cell_id_dec         bigint          NOT NULL,
    record_count        bigint,
    first_seen_ts       timestamptz,
    last_seen_ts        timestamptz,
    active_days         integer,
    gps_valid_count     bigint,
    gps_missing_count   bigint,
    gps_valid_ratio     numeric,
    gps_center_lon      double precision,
    gps_center_lat      double precision,
    gps_dist_p50_m      numeric,
    gps_dist_p90_m      numeric,
    gps_dist_max_m      numeric,
    rsrp_nonnull_count  bigint,
    rsrq_nonnull_count  bigint,
    sinr_nonnull_count  bigint,
    rssi_nonnull_count  bigint,
    dbm_nonnull_count   bigint,
    asu_level_nonnull_count bigint,
    level_nonnull_count bigint,
    ss_nonnull_count    bigint,
    rsrp_valid_ratio    numeric,
    rsrq_valid_ratio    numeric,
    sinr_valid_ratio    numeric,
    dbm_valid_ratio     numeric,
    native_signal_count bigint,
    native_nosignal_count bigint,
    fill_needed_count   bigint,
    fill_success_count  bigint,
    fill_same_cell_count bigint,
    fill_bs_top_count   bigint,
    fill_failed_count   bigint,
    missing_fields_before bigint,
    missing_fields_after bigint,
    filled_fields_total bigint,
    is_collision_suspect boolean,
    is_severe_collision boolean,
    collision_reason    text,
    gps_drift_count     bigint,
    gps_drift_ratio     numeric,
    is_dynamic_cell     boolean,
    dynamic_reason      text,
    half_major_dist_km  double precision,
    is_insufficient_sample boolean,
    has_gps_profile     boolean,
    is_gps_unstable     boolean,
    is_bs_id_lt_256     boolean,
    is_multi_operator_shared boolean,
    shared_operator_cnt integer,
    shared_operator_list text,

    UNIQUE (operator_id_cn, tech_norm, lac_dec, bs_id, cell_id_dec)
);

COMMENT ON TABLE pipeline.profile_cell IS 'Step52: cell-level quality, signal & risk profile';

CREATE INDEX IF NOT EXISTS idx_profile_cell_dynamic
    ON pipeline.profile_cell (is_dynamic_cell);

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
DECLARE
    _cnt integer;
BEGIN
    SELECT count(*) INTO _cnt
    FROM information_schema.tables
    WHERE table_schema = 'pipeline' AND table_type = 'BASE TABLE';

    RAISE NOTICE 'pipeline schema: % tables created', _cnt;
END
$$;
