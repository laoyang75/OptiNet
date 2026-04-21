from rebuild5.backend.app.maintenance import label_engine


def test_run_label_engine_uses_full_window_raw_gps_and_writes_authoritative_labels(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        label_engine,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        label_engine,
        'load_antitoxin_params',
        lambda: {
            'postgis_centroid': {
                'candidate_min_window_obs': 6,
                'candidate_min_active_days': 3,
                'candidate_min_p90_m': 900.0,
                'candidate_min_raw_p90_m': 950.0,
                'candidate_min_max_spread_m': 2300.0,
                'candidate_min_outlier_ratio': 0.2,
                'candidate_drift_patterns': ['migration', 'large_coverage'],
            }
        },
    )
    monkeypatch.setattr(
        label_engine,
        'load_label_rules_params',
        lambda _params: {
            'stable_max_p90_m': 1200.0,
            'large_coverage_max_p90_m': 10000.0,
            'collision_min_dist_m': 100000.0,
            'dual_cluster_max_dist_m': 5000.0,
            'dual_cluster_min_overlap_ratio': 0.5,
            'migration_max_overlap_ratio': 0.0,
            'migration_min_post_days': 2,
            'dynamic_min_span_m': 5000.0,
            'dynamic_min_line_ratio': 0.3,
            'dynamic_max_distance_cv': 0.5,
            'dynamic_max_avg_dwell_days': 2.0,
        },
    )
    monkeypatch.setattr(
        label_engine,
        'load_multi_centroid_v2_params',
        lambda _params: {
            'dbscan_eps_m': 260.0,
            'dbscan_min_points': 5,
            'min_cluster_dev_day_pts': 10,
            'multi_centroid_entry_p90_m': 1300.0,
            'min_total_dedup_pts': 8,
            'min_total_devs': 3,
            'min_total_active_days': 3,
            'coord_scale_lon': 85300.0,
            'coord_scale_lat': 111000.0,
            'only_raw_gps': True,
            'dedup_by': ('cell', 'dev', 'date'),
        },
    )

    label_engine.run_label_engine(batch_id=7, snapshot_version='v7')

    candidates_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._label_candidates AS' in sql
    )
    input_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._label_input_points AS' in sql
    )
    cluster_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._label_clustered_points AS' in sql
    )
    detail_sql = next(
        sql for sql, _ in calls
        if 'INSERT INTO rebuild5.cell_centroid_detail' in sql
    )
    update_sql = next(
        sql for sql, _ in calls
        if 'UPDATE rebuild5.trusted_cell_library AS t' in sql
    )

    assert 'COALESCE(t.p90_radius_m, 0) >= 1300.0' in candidates_sql
    assert 'WITH source_meta AS (' in input_sql
    assert 'JOIN rebuild5.cell_sliding_window w' in input_sql
    assert 'FROM rebuild5.enriched_records' in input_sql
    assert 'FROM rebuild5.snapshot_seed_records' in input_sql
    assert "e.gps_fill_source_final = 'raw_gps'" in input_sql
    assert 'SELECT DISTINCT ON (' in input_sql
    assert 'DATE(w.event_time_std)' in input_sql
    assert 'ST_ClusterDBSCAN(' in cluster_sql
    assert 'eps => 260.0' in cluster_sql
    assert 'minpoints => 5' in cluster_sql
    assert 'WHERE valid_cluster_count > 1' in detail_sql
    assert 'SET drift_pattern = l.label' in update_sql
    assert "WHEN l.label IN ('dual_cluster', 'migration') THEN l.label" in update_sql
    assert "WHEN l.label IN ('dynamic', 'uncertain') THEN 'multi_cluster'" in update_sql
    assert 'is_multi_centroid = (COALESCE(l.k_eff, 0) >= 3)' in update_sql
    assert "is_dynamic = (l.label = 'dynamic')" in update_sql
