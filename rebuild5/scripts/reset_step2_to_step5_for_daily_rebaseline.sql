-- Reset Step 2 -> Step 5 state for a true daily-increment rebaseline.
--
-- Scope:
--   - Keeps Step 0 / Step 1 outputs (`raw_gps`, `etl_cleaned`)
--   - Clears every downstream batch artifact that would make the next run start
--     from batch7+ instead of rebuilding batch1..N in product semantics
--
-- Run only after confirming the existing batch history is validation replay,
-- not a product daily lineage.

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
DROP TABLE IF EXISTS rebuild5._profile_seed_grid;
DROP TABLE IF EXISTS rebuild5._profile_primary_seed;
DROP TABLE IF EXISTS rebuild5._profile_seed_distance;
DROP TABLE IF EXISTS rebuild5._profile_core_cutoff;
DROP TABLE IF EXISTS rebuild5._profile_core_points;
DROP TABLE IF EXISTS rebuild5._profile_core_gps;
DROP TABLE IF EXISTS rebuild5._profile_counts;
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
DROP TABLE IF EXISTS rebuild5.cell_core_seed_grid;
DROP TABLE IF EXISTS rebuild5.cell_core_primary_seed;
DROP TABLE IF EXISTS rebuild5.cell_core_seed_distance;
DROP TABLE IF EXISTS rebuild5.cell_core_cutoff;
DROP TABLE IF EXISTS rebuild5.cell_core_points;
DROP TABLE IF EXISTS rebuild5.cell_core_gps_stats;
TRUNCATE TABLE rebuild5.cell_sliding_window;

DELETE FROM rebuild5_meta.step2_run_stats;
DELETE FROM rebuild5_meta.step3_run_stats;
DELETE FROM rebuild5_meta.step4_run_stats;
DELETE FROM rebuild5_meta.step5_run_stats;

-- Optional: archive or clear run_log separately if the UI should no longer show
-- the validation replay history. Keeping run_log is safe for pipeline behavior.
-- DELETE FROM rebuild5_meta.run_log
-- WHERE dataset_key = 'beijing_7d'
--   AND run_type IN ('pipeline', 'enrichment', 'maintenance');
