-- Full reset for rebuild5 V3 rerun baseline.
--
-- Scope:
--   - Clears Step 1 -> Step 5 derived outputs and run stats
--   - Keeps source legacy tables intact
--   - Keeps raw_gps/raw_gps_full_backup to be managed by the caller script
--   - Intended for the automated Step1->Step5 day-by-day full rerun

DROP VIEW IF EXISTS rb5.etl_filled;

DROP TABLE IF EXISTS rb5.etl_ci;
DROP TABLE IF EXISTS rb5.etl_ss1;
DROP TABLE IF EXISTS rb5.etl_clean_stage;
DROP TABLE IF EXISTS rb5.etl_cleaned;
DROP TABLE IF EXISTS rb5.etl_cleaned_daily_cumulative;

DO $$
BEGIN
    IF to_regclass('rb5.candidate_cell_pool') IS NOT NULL THEN
        TRUNCATE TABLE rb5.candidate_cell_pool;
    END IF;
    IF to_regclass('rb5.trusted_snapshot_cell') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_snapshot_cell;
    END IF;
    IF to_regclass('rb5.trusted_snapshot_bs') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_snapshot_bs;
    END IF;
    IF to_regclass('rb5.trusted_snapshot_lac') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_snapshot_lac;
    END IF;
    IF to_regclass('rb5.snapshot_diff_cell') IS NOT NULL THEN
        TRUNCATE TABLE rb5.snapshot_diff_cell;
    END IF;
    IF to_regclass('rb5.snapshot_diff_bs') IS NOT NULL THEN
        TRUNCATE TABLE rb5.snapshot_diff_bs;
    END IF;
    IF to_regclass('rb5.snapshot_diff_lac') IS NOT NULL THEN
        TRUNCATE TABLE rb5.snapshot_diff_lac;
    END IF;
END $$;

DROP TABLE IF EXISTS rb5.path_a_records;
DROP TABLE IF EXISTS rb5.step2_batch_input;
DROP TABLE IF EXISTS rb5._step2_cell_input;
DROP TABLE IF EXISTS rb5._profile_path_a_candidates;
DROP TABLE IF EXISTS rb5._profile_path_b_cells;
DROP TABLE IF EXISTS rb5._profile_path_b_records;
DROP TABLE IF EXISTS rb5.profile_obs;
DROP TABLE IF EXISTS rb5._profile_centroid;
DROP TABLE IF EXISTS rb5._profile_devs;
DROP TABLE IF EXISTS rb5._profile_radius;
DROP TABLE IF EXISTS rb5.profile_base;

DROP TABLE IF EXISTS rb5.enriched_records;
DROP TABLE IF EXISTS rb5.gps_anomaly_log;
DROP TABLE IF EXISTS rb5.candidate_seed_history;
DROP TABLE IF EXISTS rb5.snapshot_seed_records;
DROP TABLE IF EXISTS rb5._snapshot_seed_new_cells;

DO $$
BEGIN
    IF to_regclass('rb5.trusted_cell_library') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_cell_library;
    END IF;
    IF to_regclass('rb5.trusted_bs_library') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_bs_library;
    END IF;
    IF to_regclass('rb5.trusted_lac_library') IS NOT NULL THEN
        TRUNCATE TABLE rb5.trusted_lac_library;
    END IF;
    IF to_regclass('rb5.collision_id_list') IS NOT NULL THEN
        TRUNCATE TABLE rb5.collision_id_list;
    END IF;
    IF to_regclass('rb5.cell_centroid_detail') IS NOT NULL THEN
        TRUNCATE TABLE rb5.cell_centroid_detail;
    END IF;
    IF to_regclass('rb5.bs_centroid_detail') IS NOT NULL THEN
        TRUNCATE TABLE rb5.bs_centroid_detail;
    END IF;
END $$;

DROP TABLE IF EXISTS rb5.cell_daily_centroid;
DROP TABLE IF EXISTS rb5.cell_metrics_window;
DROP TABLE IF EXISTS rb5.cell_anomaly_summary;
DO $$
BEGIN
    IF to_regclass('rb5.cell_sliding_window') IS NOT NULL THEN
        TRUNCATE TABLE rb5.cell_sliding_window;
    END IF;
END $$;

DELETE FROM rb5_meta.step1_run_stats;
DELETE FROM rb5_meta.step2_run_stats;
DELETE FROM rb5_meta.step3_run_stats;
DELETE FROM rb5_meta.step4_run_stats;
DELETE FROM rb5_meta.step5_run_stats;

DELETE FROM rb5_meta.run_log
WHERE run_type IN ('bootstrap', 'step1', 'pipeline', 'enrichment', 'maintenance');
