from rebuild5.backend.app.maintenance import publish_cell


def test_publish_cell_library_leaves_multi_centroid_to_postgis_stage(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        publish_cell,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        publish_cell,
        'relation_exists',
        lambda _name: False,
    )
    monkeypatch.setattr(
        publish_cell,
        '_carry_forward_previous_cells',
        lambda **_kwargs: 0,
    )

    antitoxin = {
        'exit_retired_after_dormant_days': 30,
        'exit_high_density_min_30d': 20,
        'exit_dormant_days_high': 3,
        'exit_mid_density_min_30d': 10,
        'exit_dormant_days_mid': 7,
        'exit_dormant_days_low': 14,
        'antitoxin_max_centroid_shift_m': 500,
        'antitoxin_max_p90_ratio': 2.0,
        'antitoxin_max_dev_ratio': 3.0,
        'insufficient_min_days': 2,
        'stable_max_spread_m': 500,
        'collision_min_spread_m': 2200,
        'drift_collision_max_ratio': 0.3,
        'drift_migration_min_ratio': 0.7,
        'drift_large_coverage_max_spread_m': 2200,
        'is_dynamic_min_spread_m': 1500,
        'cell_scale_major_min_obs': 50,
        'cell_scale_major_min_devs': 10,
        'cell_scale_large_min_obs': 20,
        'cell_scale_large_min_devs': 5,
        'cell_scale_medium_min_obs': 10,
        'cell_scale_medium_min_devs': 3,
        'cell_scale_small_min_obs': 3,
    }

    publish_cell.publish_cell_library(
        run_id='maint_001',
        batch_id=7,
        snapshot_version='v7',
        snapshot_version_prev='v6',
        antitoxin=antitoxin,
    )

    insert_sql = calls[1][0]

    assert 'COALESCE(m.prev_is_multi_centroid, FALSE) AS is_multi_centroid' in insert_sql
    assert 'm.prev_centroid_pattern AS centroid_pattern' in insert_sql
    assert '(COALESCE(m.p90_radius_m, 0) >= %s) AS is_multi_centroid' not in insert_sql
