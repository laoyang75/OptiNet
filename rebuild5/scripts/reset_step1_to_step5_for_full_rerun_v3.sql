-- Full reset for rebuild5 V3 rerun baseline.
--
-- Scope:
--   - Clears Step 1 -> Step 5 derived outputs and run stats
--   - Keeps source legacy tables intact
--   - Keeps raw_gps/raw_gps_full_backup to be managed by the caller script
--   - Intended for the automated Step1->Step5 day-by-day full rerun

DROP VIEW IF EXISTS rebuild5.etl_filled;

DROP TABLE IF EXISTS rebuild5.etl_ci;
DROP TABLE IF EXISTS rebuild5.etl_ss1;
DROP TABLE IF EXISTS rebuild5.etl_clean_stage;
DROP TABLE IF EXISTS rebuild5.etl_cleaned;
DROP TABLE IF EXISTS rebuild5.etl_cleaned_daily_cumulative;

TRUNCATE TABLE rebuild5.candidate_cell_pool;

TRUNCATE TABLE rebuild5.trusted_snapshot_cell;
TRUNCATE TABLE rebuild5.trusted_snapshot_bs;
TRUNCATE TABLE rebuild5.trusted_snapshot_lac;

TRUNCATE TABLE rebuild5.snapshot_diff_cell;
TRUNCATE TABLE rebuild5.snapshot_diff_bs;
TRUNCATE TABLE rebuild5.snapshot_diff_lac;

DROP TABLE IF EXISTS rebuild5.path_a_records;
DROP TABLE IF EXISTS rebuild5.step2_batch_input;
DROP TABLE IF EXISTS rebuild5._profile_path_a_candidates;
DROP TABLE IF EXISTS rebuild5._profile_path_b_cells;
DROP TABLE IF EXISTS rebuild5._profile_path_b_records;
DROP TABLE IF EXISTS rebuild5.profile_obs;
DROP TABLE IF EXISTS rebuild5._profile_centroid;
DROP TABLE IF EXISTS rebuild5._profile_devs;
DROP TABLE IF EXISTS rebuild5._profile_radius;
DROP TABLE IF EXISTS rebuild5.profile_base;

DROP TABLE IF EXISTS rebuild5.enriched_records;
DROP TABLE IF EXISTS rebuild5.gps_anomaly_log;
DROP TABLE IF EXISTS rebuild5.candidate_seed_history;
DROP TABLE IF EXISTS rebuild5.snapshot_seed_records;

TRUNCATE TABLE rebuild5.trusted_cell_library;
TRUNCATE TABLE rebuild5.trusted_bs_library;
TRUNCATE TABLE rebuild5.trusted_lac_library;
TRUNCATE TABLE rebuild5.collision_id_list;
TRUNCATE TABLE rebuild5.cell_centroid_detail;
TRUNCATE TABLE rebuild5.bs_centroid_detail;

DROP TABLE IF EXISTS rebuild5.cell_daily_centroid;
DROP TABLE IF EXISTS rebuild5.cell_metrics_window;
DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary;
TRUNCATE TABLE rebuild5.cell_sliding_window;

DELETE FROM rebuild5_meta.step1_run_stats;
DELETE FROM rebuild5_meta.step2_run_stats;
DELETE FROM rebuild5_meta.step3_run_stats;
DELETE FROM rebuild5_meta.step4_run_stats;
DELETE FROM rebuild5_meta.step5_run_stats;

DELETE FROM rebuild5_meta.run_log
WHERE run_type IN ('bootstrap', 'step1', 'pipeline', 'enrichment', 'maintenance');
