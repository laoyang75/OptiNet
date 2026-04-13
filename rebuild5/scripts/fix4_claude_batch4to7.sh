#!/bin/bash
# Fix4 Claude: Run batches 4-7 (pattern verified in batch 1-3)
set -e
DB="postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"
S="rebuild5_fix4"

run_batch() {
    local B=$1
    local D1=$2
    local D2=$3
    echo "=== Batch $B: $D1 ==="
    local T0=$(date +%s)

    # Load
    psql "$DB" -c "INSERT INTO $S.c_window SELECT ${B}::int, operator_code, lac, bs_id, cell_id, tech_norm, dev_id, report_ts, gps_valid, lon_filled, lat_filled FROM $S.etl_cleaned_shared_sample WHERE report_ts >= '$D1' AND report_ts < '$D2';"
    echo "  loaded"

    # Reindex
    psql "$DB" -c "DROP INDEX IF EXISTS $S.idx_cw_key; CREATE INDEX idx_cw_key ON $S.c_window (operator_code, lac, bs_id, cell_id, tech_norm); ANALYZE $S.c_window;"

    # Seed grid
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_seed_grid AS SELECT operator_code, lac, bs_id, cell_id, tech_norm, ST_SnapToGrid(ST_Transform(ST_SetSRID(ST_MakePoint(lon_final, lat_final), 4326), 3857), 200) AS snap_geom, COUNT(*) AS obs_count FROM $S.c_window WHERE gps_valid AND lon_final IS NOT NULL GROUP BY 1,2,3,4,5,6; CREATE INDEX ON $S.c_seed_grid (operator_code, lac, bs_id, cell_id, tech_norm); ANALYZE $S.c_seed_grid;"
    echo "  seed_grid done"

    # Primary seed
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_primary_seed AS SELECT DISTINCT ON (operator_code, lac, bs_id, cell_id, tech_norm) operator_code, lac, bs_id, cell_id, tech_norm, snap_geom FROM $S.c_seed_grid ORDER BY operator_code, lac, bs_id, cell_id, tech_norm, obs_count DESC; CREATE INDEX ON $S.c_primary_seed (operator_code, lac, bs_id, cell_id, tech_norm); ANALYZE $S.c_primary_seed;"

    # Seed distance
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_seed_dist AS SELECT w.operator_code, w.lac, w.bs_id, w.cell_id, w.tech_norm, w.dev_id, w.event_time_std, w.lon_final, w.lat_final, ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(w.lon_final, w.lat_final), 4326), 3857), s.snap_geom) AS dist_to_seed_m FROM $S.c_window w JOIN $S.c_primary_seed s USING (operator_code, lac, bs_id, cell_id, tech_norm) WHERE w.gps_valid AND w.lon_final IS NOT NULL; CREATE INDEX ON $S.c_seed_dist (operator_code, lac, bs_id, cell_id, tech_norm); ANALYZE $S.c_seed_dist;"
    echo "  distance done"

    # Cutoff
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_cutoff AS SELECT operator_code, lac, bs_id, cell_id, tech_norm, GREATEST(800, LEAST(COALESCE(PERCENTILE_CONT(0.8) WITHIN GROUP (ORDER BY dist_to_seed_m), 800), 3000)) AS keep_radius_m, COUNT(*) AS total_pts FROM $S.c_seed_dist GROUP BY 1,2,3,4,5; CREATE INDEX ON $S.c_cutoff (operator_code, lac, bs_id, cell_id, tech_norm);"

    # Core points
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_core_pts AS SELECT d.*, c.keep_radius_m FROM $S.c_seed_dist d JOIN $S.c_cutoff c USING (operator_code, lac, bs_id, cell_id, tech_norm) WHERE d.dist_to_seed_m <= c.keep_radius_m; CREATE INDEX ON $S.c_core_pts (operator_code, lac, bs_id, cell_id, tech_norm); ANALYZE $S.c_core_pts;"
    echo "  core_pts done"

    # Core stats
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_core_stats AS SELECT operator_code, lac, bs_id, cell_id, tech_norm, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS center_lon, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) AS center_lat, COUNT(*) AS core_gps_count, COUNT(DISTINCT dev_id) AS distinct_dev_id, COUNT(DISTINCT DATE(event_time_std)) AS active_days, COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text)) AS independent_obs, COUNT(*) AS window_obs_count, MAX(keep_radius_m) AS keep_radius_m FROM $S.c_core_pts GROUP BY 1,2,3,4,5;"

    # Radius
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_radius AS SELECT p.operator_code, p.lac, p.bs_id, p.cell_id, p.tech_norm, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY SQRT(POWER((p.lon_final-s.center_lon)*85300,2)+POWER((p.lat_final-s.center_lat)*111000,2))) AS p50_radius_m, PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY SQRT(POWER((p.lon_final-s.center_lon)*85300,2)+POWER((p.lat_final-s.center_lat)*111000,2))) AS p90_radius_m FROM $S.c_core_pts p JOIN $S.c_core_stats s USING (operator_code, lac, bs_id, cell_id, tech_norm) GROUP BY 1,2,3,4,5;"

    # Raw radius
    psql "$DB" -c "CREATE UNLOGGED TABLE $S.c_raw_radius AS SELECT d.operator_code, d.lac, d.bs_id, d.cell_id, d.tech_norm, PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY SQRT(POWER((d.lon_final-s.center_lon)*85300,2)+POWER((d.lat_final-s.center_lat)*111000,2))) AS raw_p90_radius_m FROM $S.c_seed_dist d JOIN $S.c_core_stats s USING (operator_code, lac, bs_id, cell_id, tech_norm) GROUP BY 1,2,3,4,5;"
    echo "  radius done"

    # Assemble
    psql "$DB" -c "INSERT INTO $S.c_cell_lib SELECT ${B}::int, s.operator_code, s.lac, s.bs_id, s.cell_id, s.tech_norm, CASE WHEN s.independent_obs >= 30 THEN 'excellent' WHEN s.independent_obs >= 10 THEN 'qualified' WHEN s.independent_obs >= 1 THEN 'observing' ELSE 'waiting' END, s.center_lon, s.center_lat, r.p50_radius_m, r.p90_radius_m, rr.raw_p90_radius_m, s.independent_obs, s.distinct_dev_id, s.core_gps_count, s.active_days, s.window_obs_count, co.total_pts, s.core_gps_count, co.total_pts - s.core_gps_count, s.keep_radius_m FROM $S.c_core_stats s JOIN $S.c_radius r USING (operator_code, lac, bs_id, cell_id, tech_norm) JOIN $S.c_raw_radius rr USING (operator_code, lac, bs_id, cell_id, tech_norm) JOIN $S.c_cutoff co USING (operator_code, lac, bs_id, cell_id, tech_norm);"

    # Cleanup
    psql "$DB" -c "DROP TABLE IF EXISTS $S.c_seed_grid, $S.c_primary_seed, $S.c_seed_dist, $S.c_cutoff, $S.c_core_pts, $S.c_core_stats, $S.c_radius, $S.c_raw_radius;"

    local T1=$(date +%s)
    echo "  Batch $B done in $((T1-T0))s"
}

run_batch 4 "2025-12-04" "2025-12-05"
run_batch 5 "2025-12-05" "2025-12-06"
run_batch 6 "2025-12-06" "2025-12-07"
run_batch 7 "2025-12-07" "2025-12-08"

echo "=== Final summary ==="
psql "$DB" -c "SELECT batch_id, count(*) AS total, count(*) FILTER (WHERE lifecycle_state='observing') AS obs, count(*) FILTER (WHERE lifecycle_state='qualified') AS qual, count(*) FILTER (WHERE lifecycle_state='excellent') AS exc FROM $S.c_cell_lib GROUP BY 1 ORDER BY 1;"
