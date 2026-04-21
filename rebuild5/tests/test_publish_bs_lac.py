from rebuild5.backend.app.maintenance import publish_bs_lac


def test_publish_bs_library_uses_library_agg_with_matching_params(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        publish_bs_lac,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        publish_bs_lac,
        '_execute_with_session_settings',
        lambda **kwargs: calls.append((kwargs['sql'], kwargs.get('params'), tuple(kwargs['session_setup_sqls']))),
    )
    monkeypatch.setattr(publish_bs_lac, 'load_profile_params', lambda: {})
    monkeypatch.setattr(
        publish_bs_lac,
        'flatten_profile_thresholds',
        lambda _params: {
            'bs_excellent_min_excellent_cells': 1,
            'bs_qualified_min_qualified_cells': 2,
        },
    )

    publish_bs_lac.publish_bs_library(
        run_id='maint_001',
        batch_id=2,
        snapshot_version='v2',
        snapshot_version_prev='v1',
        antitoxin={'bs_max_cell_to_bs_distance_m': 1234.5},
    )

    sql, params, settings = calls[1]

    assert sql.count('%s') == len(params)
    assert 'FROM rebuild5.trusted_snapshot_bs' not in sql
    assert 'MAX(operator_cn) AS operator_cn' in sql
    assert 'FROM cell_agg c' in sql
    assert settings == ('SET enable_nestloop = off',)
    assert 'COUNT(*) FILTER (WHERE lifecycle_state = \'retired\') AS retired_cells' in sql
    assert 'WHEN c.total_cells > 0 AND c.total_cells = COALESCE(c.retired_cells, 0) THEN \'retired\'' in sql
    assert "WHEN c.excellent_cells >= 1 THEN 'excellent'" in sql
    assert "WHEN c.qualified_cells >= 2 THEN 'qualified'" in sql


def test_publish_lac_library_uses_bs_library_agg_with_matching_params(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        publish_bs_lac,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(publish_bs_lac, 'load_profile_params', lambda: {})
    monkeypatch.setattr(
        publish_bs_lac,
        'flatten_profile_thresholds',
        lambda _params: {
            'lac_qualified_min_excellent_bs': 10,
            'lac_excellent_min_excellent_bs': 30,
        },
    )

    publish_bs_lac.publish_lac_library(
        run_id='maint_001',
        batch_id=2,
        snapshot_version='v2',
        snapshot_version_prev='v1',
    )

    sql, params = calls[1]

    assert sql.count('%s') == len(params)
    assert 'FROM rebuild5.trusted_snapshot_lac' not in sql
    assert 'MAX(operator_cn) AS operator_cn' in sql
    assert 'FROM bs_agg ba' in sql
    assert 'WHEN ba.total_bs > 0 AND ba.total_bs = COALESCE(ba.retired_bs, 0) THEN \'retired\'' in sql
    assert "WHEN COALESCE(ba.active_bs, 0) = 0 THEN 'dormant'" in sql
    assert "ELSE 'active'" in sql
    assert 'excellent_bs' in sql
    assert 'normal_bs' in sql
    assert 'anomaly_bs' in sql
    assert 'insufficient_bs' in sql
    assert 'normal_bs_sample AS (' in sql


def test_publish_cell_centroid_detail_uses_configured_postgis_cluster_rules(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        publish_bs_lac,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        publish_bs_lac,
        '_execute_with_session_settings',
        lambda **kwargs: calls.append((kwargs['sql'], kwargs.get('params'), tuple(kwargs['session_setup_sqls']))),
    )
    monkeypatch.setattr(
        publish_bs_lac,
        'flatten_antitoxin_thresholds',
        lambda _params: {
            'multi_centroid_trigger_min_p90_m': 800.0,
            'collision_min_spread_m': 2200.0,
        },
    )
    monkeypatch.setattr(
        publish_bs_lac,
        'load_antitoxin_params',
        lambda: {
            'postgis_centroid': {
                'lookback_batches': 6,
                'candidate_min_window_obs': 6,
                'candidate_min_active_days': 3,
                'candidate_min_p90_m': 900.0,
                'candidate_min_raw_p90_m': 950.0,
                'candidate_min_max_spread_m': 2300.0,
                'candidate_min_outlier_ratio': 0.2,
                'candidate_drift_patterns': ['migration', 'collision'],
                'snap_grid_m': 40.0,
                'cluster_eps_m': 260.0,
                'cluster_min_points': 5,
                'stable_min_obs': 7,
                'stable_min_share': 0.2,
                'stable_min_days': 4,
                'stable_min_devs': 3,
                'stable_single_device_max_total_devs': 1,
                'classification_min_secondary_share': 0.15,
                'dual_cluster_min_distance_m': 350.0,
                'migration_min_distance_m': 600.0,
                'migration_max_overlap_days': 2,
                'moving_min_overlap_days': 3,
                'moving_min_switches': 4,
                'multi_cluster_min_cluster_count': 4,
            }
        },
    )

    publish_bs_lac.publish_cell_centroid_detail(
        batch_id=7,
        snapshot_version='v7',
    )

    session_calls = [item for item in calls if len(item) == 3]
    exec_calls = [item for item in calls if len(item) == 2]

    insert_sql, insert_params, settings = next(
        item
        for item in session_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_clustered_grid AS' in item[0]
    )
    detail_insert_sql, detail_insert_params = next(
        item
        for item in exec_calls
        if 'INSERT INTO rebuild5.cell_centroid_detail' in item[0]
    )
    center_update_sql, center_update_params = next(
        item
        for item in exec_calls
        if 'SET center_lon = d.center_lon' in item[0]
    )
    classify_update_sql, classify_update_params = next(
        item
        for item in exec_calls
        if 'FROM rebuild5._cell_centroid_classification c' in item[0]
    )
    classification_stage_sql, _ = next(
        item
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_classification AS' in item[0]
    )

    assert insert_params is None
    assert settings == ('SET enable_nestloop = off',)
    points_sql, points_params = next(
        item
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_points AS' in item[0]
    )
    valid_clusters_sql, valid_clusters_params = next(
        item
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_valid_clusters AS' in item[0]
    )
    cluster_radius_sql, _ = next(
        item
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_radius AS' in item[0]
    )
    cluster_stats_sql, _ = next(
        item
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_cluster_stats AS' in item[0]
    )
    candidates_sql = next(
        item[0]
        for item in exec_calls
        if 'CREATE UNLOGGED TABLE rebuild5._cell_centroid_candidates AS' in item[0]
    )
    assert points_params is None
    assert detail_insert_params == (7, 'v7')
    assert 'LEFT JOIN rebuild5.cell_metrics_window m' in candidates_sql
    assert 'COALESCE(t.window_obs_count, 0) >= 6' in candidates_sql
    assert 'COALESCE(t.active_days, 0) >= 3' in candidates_sql
    assert 'COALESCE(t.p90_radius_m, 0) >= 900.0' in candidates_sql
    assert 'COALESCE(m.raw_p90_radius_m, 0) >= 950.0' in candidates_sql
    assert 'COALESCE(m.core_outlier_ratio, 0) >= 0.2' in candidates_sql
    assert "t.drift_pattern IN ('migration', 'collision')" in candidates_sql
    assert 't.gps_anomaly_type IS NOT NULL' in candidates_sql
    assert 'JOIN rebuild5.cell_sliding_window w' in points_sql
    assert 'w.batch_id BETWEEN 1 AND 7' in points_sql
    assert 'ST_SnapToGrid(' in points_sql
    assert '40.0' in points_sql
    assert 'eps => 260.0' in insert_sql
    assert 'minpoints => 5' in insert_sql
    assert 'MAX(' in cluster_radius_sql
    assert 'radius_m' in cluster_radius_sql
    assert 'share_ratio' in cluster_stats_sql
    assert 'FROM rebuild5._cell_centroid_ranked_clusters' in valid_clusters_sql
    assert 'WHERE valid_cluster_count > 1' in detail_insert_sql
    assert center_update_params == (7,)
    assert 'UPDATE rebuild5.trusted_cell_library AS t' in center_update_sql
    assert 'AND d.bs_id IS NOT DISTINCT FROM t.bs_id' in center_update_sql
    assert classify_update_params == (7,)
    assert 'secondary_share_ratio' in classification_stage_sql
    assert '>= 0.15' in classification_stage_sql
    assert "THEN 'multi_cluster'" in classification_stage_sql
    assert "THEN 'moving'" in classification_stage_sql
    assert "THEN 'migration'" in classification_stage_sql
    assert "THEN 'dual_cluster'" in classification_stage_sql
    assert "is_multi_centroid = COALESCE(c.centroid_pattern IS NOT NULL, FALSE)" in classify_update_sql
    assert "is_dynamic = COALESCE(c.centroid_pattern = 'moving', FALSE)" in classify_update_sql
    assert "centroid_pattern = c.centroid_pattern" in classify_update_sql


def test_publish_bs_centroid_detail_uses_child_cell_split(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        publish_bs_lac,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )

    publish_bs_lac.publish_bs_centroid_detail(
        batch_id=7,
        snapshot_version='v7',
        large_spread_threshold_m=2500.0,
    )

    insert_sql, insert_params = calls[1]
    update_sql, update_params = calls[2]

    assert insert_params == (7, 7, 'v7')
    assert 'JOIN rebuild5.trusted_cell_library t' in insert_sql
    assert 'WHERE cluster_count > 1' in insert_sql
    assert update_params == (7, 7)
    assert "classification = 'multi_centroid'" in update_sql
