from rebuild5.backend.app.enrichment import pipeline as enrichment_pipeline
from rebuild5.backend.app.evaluation import pipeline as evaluation_pipeline
from rebuild5.backend.app.maintenance import cell_maintain as maintenance_cell_maintain
from rebuild5.backend.app.maintenance import pipeline as maintenance_pipeline
from rebuild5.backend.app.maintenance import window as maintenance_window
from rebuild5.backend.app.profile import pipeline as profile_pipeline


def test_build_path_a_records_carries_step2_selected_donor(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        profile_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(profile_pipeline, 'relation_exists', lambda _name: True)

    profile_pipeline.build_path_a_records(
        'run_001',
        antitoxin_thresholds={'collision_min_spread_m': 2200.0},
    )

    latest_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._path_a_latest_library AS' in sql
    )
    collision_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._path_a_collision_cells AS' in sql
    )
    candidate_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._profile_path_a_candidates AS' in sql
    )
    path_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5.path_a_records AS' in sql
    )

    assert 'FROM rebuild5.trusted_cell_library' in latest_sql
    assert 'WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)' in latest_sql
    assert 'FROM rebuild5.collision_id_list' in collision_sql
    assert 'WHERE batch_id = (SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5.trusted_cell_library)' in collision_sql
    assert 'donor_batch_id' in candidate_sql
    assert 'donor_center_lon' not in candidate_sql
    assert 'LEFT JOIN rebuild5._path_a_latest_library d' in path_sql
    assert 'c.donor_batch_id' in path_sql
    assert 'd.center_lon AS donor_center_lon' in path_sql


def test_get_step2_input_relation_prefers_daily_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_pipeline,
        'relation_exists',
        lambda name: name == profile_pipeline.STEP2_INPUT_SCOPE_RELATION,
    )

    assert profile_pipeline.get_step2_input_relation() == profile_pipeline.STEP2_INPUT_SCOPE_RELATION


def test_write_step2_run_stats_uses_scoped_input_count(monkeypatch) -> None:
    execute_calls = []
    queries = []

    monkeypatch.setattr(
        profile_pipeline,
        'relation_exists',
        lambda name: name == profile_pipeline.STEP2_INPUT_SCOPE_RELATION,
    )
    monkeypatch.setattr(
        profile_pipeline,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )

    def fake_fetchone(sql, params=None):
        queries.append((sql, params))
        if f'FROM {profile_pipeline.STEP2_INPUT_SCOPE_RELATION}' in sql:
            return {'cnt': 11}
        if 'FROM rebuild5.path_a_records' in sql:
            return {'cnt': 2}
        if 'FROM rebuild5._profile_path_a_candidates' in sql:
            return {
                'candidate_count': 1,
                'matched_count': 1,
                'pending_count': 0,
                'dropped_count': 0,
                'layer1_count': 1,
                'layer2_count': 0,
                'layer3_count': 0,
            }
        if 'FROM rebuild5._profile_path_b_cells' in sql:
            return {'cell_count': 3, 'record_count': 5}
        if 'FROM rebuild5.profile_base' in sql:
            return {
                'complete_cells': 1,
                'partial_cells': 2,
                'avg_gps_original_ratio': 0.5,
                'avg_signal_original_ratio': 0.5,
                'avg_independent_obs': 7.0,
                'avg_independent_devs': 3.0,
                'avg_observed_span_hours': 24.0,
                'avg_p50_radius_m': 100.0,
                'avg_p90_radius_m': 200.0,
            }
        return {}

    monkeypatch.setattr(profile_pipeline, 'fetchone', fake_fetchone)

    stats = profile_pipeline.write_step2_run_stats(
        run_id='step2_001',
        batch_id=1,
        previous_snapshot_version='v0',
    )

    assert stats['input_record_count'] == 11
    assert stats['path_a_record_count'] == 2
    assert stats['path_b_record_count'] == 5
    assert stats['path_c_drop_count'] == 4
    assert any(
        f'FROM {profile_pipeline.STEP2_INPUT_SCOPE_RELATION}' in sql
        for sql, _ in queries
    )
    assert all('FROM rebuild5.etl_cleaned' not in sql for sql, _ in queries)


def test_build_current_cell_snapshot_uses_previous_batch_collision_flags(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        evaluation_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        evaluation_pipeline,
        'relation_exists',
        lambda name: name == 'rebuild5.collision_id_list',
    )

    thresholds = {
        'waiting_min_obs': 3,
        'excellent_min_obs': 30,
        'qualified_min_obs': 10,
        'anchorable_min_gps_valid_count': 10,
        'anchorable_min_distinct_devices': 2,
        'anchorable_max_p90': 1500.0,
        'anchorable_min_span_hours': 24.0,
        'gps_confidence_high_min_gps': 20,
        'gps_confidence_high_min_devs': 3,
        'gps_confidence_medium_min_gps': 10,
        'gps_confidence_medium_min_devs': 2,
        'gps_confidence_low_min_gps': 1,
        'signal_confidence_high_min_signal': 20,
        'signal_confidence_medium_min_signal': 10,
        'signal_confidence_low_min_signal': 1,
    }

    evaluation_pipeline.build_current_cell_snapshot(
        run_id='step3_001',
        batch_id=3,
        snapshot_version='v3',
        previous_batch_id=2,
        previous_snapshot_version='v2',
        thresholds=thresholds,
    )

    snapshot_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._snapshot_current_cell AS' in sql
    )

    assert 'FROM rebuild5.collision_id_list WHERE batch_id = 2 AND cell_id IS NOT NULL' in snapshot_sql
    eval_input_sql = next(
        sql for sql, _ in calls
        if 'CREATE UNLOGGED TABLE rebuild5._candidate_eval_input AS' in sql
    )
    assert 'SELECT DISTINCT ON (operator_code, lac, cell_id, tech_norm)' in eval_input_sql
    assert 'FULL OUTER JOIN historical_pool h' in eval_input_sql
    assert 'AND h.tech_norm IS NOT DISTINCT FROM c.tech_norm' in eval_input_sql
    assert 'COALESCE(LEAST(c.first_obs_at, h.first_obs_at), c.first_obs_at, h.first_obs_at) AS first_obs_at' in eval_input_sql
    assert 'GREATEST(COALESCE(c.independent_devs, 0), COALESCE(h.independent_devs, 0))' in eval_input_sql
    assert 'COALESCE(c.active_days, 0) + COALESCE(h.active_days, 0) AS active_days' in eval_input_sql


def test_update_candidate_pool_deduplicates_profile_base_before_upsert(monkeypatch) -> None:
    calls = []
    queries = []

    monkeypatch.setattr(
        evaluation_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        evaluation_pipeline,
        'relation_exists',
        lambda name: name == 'rebuild5._candidate_eval_input',
    )
    def fake_fetchone(sql, params=None):
        queries.append((sql, params))
        if 'SELECT COUNT(*) AS cnt FROM pruned' in sql:
            return {'cnt': 0}
        return {}

    monkeypatch.setattr(evaluation_pipeline, 'fetchone', fake_fetchone)

    stats = evaluation_pipeline._update_candidate_pool(batch_id=3)

    upsert_sql = next(
        sql for sql, _ in calls
        if 'INSERT INTO rebuild5.candidate_cell_pool' in sql
    )
    prune_sql = next(
        sql for sql, _ in queries
        if 'DELETE FROM rebuild5.candidate_cell_pool' in sql and 'first_seen_batch_id' in sql
    )

    assert 'FROM rebuild5._candidate_eval_input p' in upsert_sql
    assert 'JOIN rebuild5._snapshot_current_cell s' in upsert_sql
    assert 'AND p.tech_norm IS NOT DISTINCT FROM s.tech_norm' in upsert_sql
    assert 'ON CONFLICT (operator_code, lac, cell_id, tech_norm)' in upsert_sql
    assert 'active_days = EXCLUDED.active_days' in upsert_sql
    assert 'first_seen_batch_id' in prune_sql
    assert stats['waiting_pruned_count'] == 0


def test_write_step3_run_stats_counts_final_snapshot(monkeypatch) -> None:
    calls = []
    queries = []

    monkeypatch.setattr(
        evaluation_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )

    def fake_fetchone(sql, params=None):
        queries.append((sql, params))
        if 'FROM rebuild5.profile_base' in sql:
            return {'cnt': 10}
        if 'FROM rebuild5.trusted_snapshot_cell' in sql:
            return {
                'total': 20,
                'waiting_count': 5,
                'observing_count': 3,
                'qualified_count': 7,
                'excellent_count': 5,
                'anchor_count': 12,
            }
        if 'FROM rebuild5.trusted_snapshot_bs' in sql:
            return {'waiting_count': 1, 'observing_count': 2, 'excellent_count': 4, 'qualified_count': 3}
        if 'FROM rebuild5.trusted_snapshot_lac' in sql:
            return {'waiting_count': 4, 'observing_count': 5, 'excellent_count': 2, 'qualified_count': 6}
        if 'FROM rebuild5.snapshot_diff_cell' in sql:
            return {
                'new_count': 8,
                'promoted_count': 2,
                'demoted_count': 1,
                'eligibility_changed_count': 3,
                'geometry_changed_count': 4,
                'new_qualified_count': 5,
                'new_excellent_count': 6,
            }
        return {}

    monkeypatch.setattr(evaluation_pipeline, 'fetchone', fake_fetchone)

    stats = evaluation_pipeline.write_step3_run_stats(
        run_id='step3_002',
        batch_id=2,
        snapshot_version='v2',
        previous_snapshot_version='v1',
        waiting_pruned_count=4,
        dormant_marked_count=0,
    )

    assert any('FROM rebuild5.trusted_snapshot_cell' in sql for sql, _ in queries)
    assert any('FROM rebuild5.trusted_snapshot_bs' in sql for sql, _ in queries)
    assert any('FROM rebuild5.trusted_snapshot_lac' in sql for sql, _ in queries)
    assert all('FROM rebuild5._snapshot_current_cell' not in sql for sql, _ in queries)
    assert stats['evaluated_cell_count'] == 20
    assert stats['qualified_cell_count'] == 7
    assert stats['excellent_cell_count'] == 5
    assert stats['bs_excellent_count'] == 4
    assert stats['bs_qualified_count'] == 3
    assert stats['lac_excellent_count'] == 2
    assert stats['lac_qualified_count'] == 6
    assert stats['waiting_pruned_cell_count'] == 4


def test_run_enrichment_pipeline_keeps_step4_run_stats_history(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        enrichment_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(enrichment_pipeline, 'ensure_enrichment_schema', lambda: None)
    monkeypatch.setattr(enrichment_pipeline, '_latest_step2', lambda: None)
    monkeypatch.setattr(enrichment_pipeline, 'relation_exists', lambda _name: False)
    monkeypatch.setattr(enrichment_pipeline, 'load_antitoxin_params', lambda: {})
    monkeypatch.setattr(
        enrichment_pipeline,
        'flatten_antitoxin_thresholds',
        lambda _params: {'collision_min_spread_m': 2200.0},
    )
    monkeypatch.setattr(enrichment_pipeline, 'write_step4_stats', lambda _stats: None)
    monkeypatch.setattr(enrichment_pipeline, 'write_run_log', lambda **_kwargs: None)

    enrichment_pipeline.run_enrichment_pipeline()

    assert all(
        'DROP TABLE IF EXISTS rebuild5_meta.step4_run_stats' not in sql
        for sql, _ in calls
    )
    assert all(
        'DROP TABLE IF EXISTS rebuild5.enriched_records' not in sql
        and 'DROP TABLE IF EXISTS rebuild5.gps_anomaly_log' not in sql
        for sql, _ in calls
    )


def test_insert_snapshot_seed_records_bridges_new_snapshot_cells(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        enrichment_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        enrichment_pipeline,
        'relation_exists',
        lambda name: name == 'rebuild5.candidate_seed_history',
    )

    enrichment_pipeline._insert_snapshot_seed_records(batch_id=7, run_id='enrich_001')

    sql, params = calls[0]
    assert 'INSERT INTO rebuild5.snapshot_seed_records' in sql
    assert 'FROM rebuild5.trusted_snapshot_cell s' in sql
    assert 'FROM rebuild5.trusted_cell_library' in sql
    assert 'FROM rebuild5.candidate_seed_history e' in sql
    assert 'new_snapshot_cells AS MATERIALIZED (' in sql
    assert 'e.batch_id <= 7' in sql
    assert "s.lifecycle_state IN ('qualified', 'excellent')" in sql
    assert 'p.cell_id IS NULL' in sql
    assert 'NOT EXISTS (' in sql and 'FROM rebuild5.enriched_records er' in sql
    assert params == ('enrich_001', enrichment_pipeline.DATASET_KEY)


def test_run_enrichment_pipeline_prepares_snapshot_seed_indexes_before_insert(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(enrichment_pipeline, 'ensure_enrichment_schema', lambda: None)
    monkeypatch.setattr(
        enrichment_pipeline,
        '_latest_step2',
        lambda: {'batch_id': 7, 'trusted_snapshot_version': 'v6'},
    )
    monkeypatch.setattr(
        enrichment_pipeline,
        'relation_exists',
        lambda name: name in {
            'rebuild5.path_a_records',
            'rebuild5.trusted_cell_library',
            'rebuild5.candidate_seed_history',
        },
    )
    monkeypatch.setattr(enrichment_pipeline, 'load_antitoxin_params', lambda: {})
    monkeypatch.setattr(
        enrichment_pipeline,
        'flatten_antitoxin_thresholds',
        lambda _params: {'collision_min_spread_m': 2200.0},
    )
    monkeypatch.setattr(
        enrichment_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(enrichment_pipeline, '_insert_enriched_records', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(enrichment_pipeline, '_insert_gps_anomaly_log', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(enrichment_pipeline, '_insert_snapshot_seed_records', lambda **_kwargs: calls.append(('SNAPSHOT_SEED_INSERT', None)))
    monkeypatch.setattr(enrichment_pipeline, '_collect_step4_stats', lambda **_kwargs: {'run_id': 'enrich_001', 'batch_id': 7, 'dataset_key': 'beijing_7d', 'snapshot_version': 'v7', 'snapshot_version_prev': 'v6', 'status': 'completed'})
    monkeypatch.setattr(enrichment_pipeline, 'write_step4_coverage', lambda **_kwargs: None)
    monkeypatch.setattr(enrichment_pipeline, 'write_step4_stats', lambda _stats: None)
    monkeypatch.setattr(enrichment_pipeline, 'write_run_log', lambda **_kwargs: None)

    enrichment_pipeline.run_enrichment_pipeline()

    sqls = [sql for sql, _ in calls]
    idx_pos = next(i for i, sql in enumerate(sqls) if 'idx_csh_join_batch' in sql)
    analyze_enriched_pos = next(i for i, sql in enumerate(sqls) if sql == 'ANALYZE rebuild5.enriched_records')
    analyze_csh_pos = next(i for i, sql in enumerate(sqls) if sql == 'ANALYZE rebuild5.candidate_seed_history')
    insert_pos = sqls.index('SNAPSHOT_SEED_INSERT')

    assert idx_pos < insert_pos
    assert analyze_enriched_pos < insert_pos
    assert analyze_csh_pos < insert_pos


def test_persist_candidate_seed_history_writes_path_b_records(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        profile_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(
        profile_pipeline,
        'get_step2_input_relation',
        lambda: profile_pipeline.STEP2_INPUT_SCOPE_RELATION,
    )

    profile_pipeline.persist_candidate_seed_history(batch_id=5, run_id='profile_001')

    delete_sql, delete_params = calls[0]
    insert_sql, insert_params = calls[1]
    analyze_sql, analyze_params = calls[2]

    assert delete_sql == 'DELETE FROM rebuild5.candidate_seed_history WHERE batch_id = %s'
    assert delete_params == (5,)
    assert 'INSERT INTO rebuild5.candidate_seed_history' in insert_sql
    assert f'FROM {profile_pipeline.STEP2_INPUT_SCOPE_RELATION} e' in insert_sql
    assert 'JOIN rebuild5._profile_path_b_cells c' in insert_sql
    assert 'LEFT JOIN rebuild5.path_a_records a' in insert_sql
    assert 'WHERE c.has_raw_gps' in insert_sql
    assert 'a.source_tid IS NULL' in insert_sql
    assert insert_params == (5, 'profile_001', profile_pipeline.DATASET_KEY, 'profile_001')
    assert analyze_sql == 'ANALYZE rebuild5.candidate_seed_history'
    assert analyze_params is None


def test_run_maintenance_pipeline_keeps_step5_run_stats_history(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        maintenance_pipeline,
        'execute',
        lambda sql, params=None: calls.append((sql, params)),
    )
    monkeypatch.setattr(maintenance_pipeline, 'ensure_maintenance_schema', lambda: None)
    monkeypatch.setattr(maintenance_pipeline, '_latest_step3', lambda: None)

    maintenance_pipeline.run_maintenance_pipeline()

    assert all(
        'DROP TABLE IF EXISTS rebuild5_meta.step5_run_stats' not in sql
        for sql, _ in calls
    )


def test_run_maintenance_pipeline_runs_label_engine_before_collision(monkeypatch) -> None:
    order = []

    monkeypatch.setattr(maintenance_pipeline, 'ensure_maintenance_schema', lambda: None)
    monkeypatch.setattr(
        maintenance_pipeline,
        '_latest_step3',
        lambda: {'batch_id': 9, 'snapshot_version': 'v9'},
    )
    monkeypatch.setattr(
        maintenance_pipeline,
        '_latest_published_snapshot_version',
        lambda **_kwargs: 'v8',
    )
    monkeypatch.setattr(maintenance_pipeline, 'load_antitoxin_params', lambda: {})
    monkeypatch.setattr(
        maintenance_pipeline,
        'flatten_antitoxin_thresholds',
        lambda _params: {
            'absolute_collision_min_distance_m': 20000.0,
            'bs_max_cell_to_bs_distance_m': 2500.0,
        },
    )
    monkeypatch.setattr(
        maintenance_pipeline,
        'execute',
        lambda sql, params=None: None,
    )
    monkeypatch.setattr(maintenance_pipeline, 'relation_exists', lambda _name: False)
    monkeypatch.setattr(maintenance_pipeline, 'refresh_sliding_window', lambda **_kwargs: order.append('refresh'))
    monkeypatch.setattr(maintenance_pipeline, 'build_daily_centroids', lambda **_kwargs: order.append('daily'))
    monkeypatch.setattr(maintenance_pipeline, 'build_cell_metrics_base', lambda **_kwargs: order.append('base'))
    monkeypatch.setattr(maintenance_pipeline, 'build_cell_core_gps_stats', lambda **_kwargs: order.append('core'))
    monkeypatch.setattr(maintenance_pipeline, 'build_cell_radius_stats', lambda: order.append('radius'))
    monkeypatch.setattr(maintenance_pipeline, 'compute_drift_metrics', lambda **_kwargs: order.append('drift'))
    monkeypatch.setattr(maintenance_pipeline, 'compute_gps_anomaly_summary', lambda **_kwargs: order.append('anomaly'))
    monkeypatch.setattr(maintenance_pipeline, 'publish_cell_library', lambda **_kwargs: order.append('publish_cell'))
    monkeypatch.setattr(maintenance_pipeline, 'run_label_engine', lambda **_kwargs: order.append('label_engine'))
    monkeypatch.setattr(maintenance_pipeline, 'detect_collisions', lambda **_kwargs: order.append('collision'))
    monkeypatch.setattr(maintenance_pipeline, 'publish_bs_library', lambda **_kwargs: order.append('publish_bs'))
    monkeypatch.setattr(maintenance_pipeline, 'publish_bs_centroid_detail', lambda **_kwargs: order.append('publish_bs_detail'))
    monkeypatch.setattr(maintenance_pipeline, 'publish_lac_library', lambda **_kwargs: order.append('publish_lac'))
    monkeypatch.setattr(
        maintenance_pipeline,
        'collect_step5_stats',
        lambda **_kwargs: {
            'run_id': 'maint_001',
            'batch_id': 9,
            'dataset_key': 'beijing_7d',
            'snapshot_version': 'v9',
            'snapshot_version_prev': 'v8',
            'status': 'completed',
            'published_cell_count': 1,
            'published_bs_count': 1,
            'published_lac_count': 1,
            'collision_cell_count': 0,
            'multi_centroid_cell_count': 0,
            'dynamic_cell_count': 0,
            'anomaly_bs_count': 0,
        },
    )
    monkeypatch.setattr(maintenance_pipeline, 'write_step5_stats', lambda _stats: None)
    monkeypatch.setattr(maintenance_pipeline, 'write_run_log', lambda **_kwargs: None)

    maintenance_pipeline.run_maintenance_pipeline()

    assert order.index('label_engine') < order.index('collision')
    assert order.index('collision') < order.index('publish_bs')


def test_step5_previous_snapshot_version_excludes_current_batch(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(maintenance_pipeline, 'relation_exists', lambda _name: True)

    def fake_fetchone(sql, params=None):
        calls.append((sql, params))
        return {'snapshot_version': 'v1'}

    monkeypatch.setattr(maintenance_pipeline, 'fetchone', fake_fetchone)

    snapshot_version = maintenance_pipeline._latest_published_snapshot_version(current_batch_id=2)

    assert snapshot_version == 'v1'
    assert any('WHERE batch_id < %s' in sql for sql, _ in calls)
    assert calls[0][1] == (2,)


def test_refresh_sliding_window_uses_dedicated_worker_count(monkeypatch) -> None:
    execute_calls = []
    parallel_calls = []

    monkeypatch.setattr(
        maintenance_window,
        'relation_exists',
        lambda name: name in {'rebuild5.enriched_records', 'rebuild5.snapshot_seed_records'},
    )
    monkeypatch.setattr(
        maintenance_window,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(
        maintenance_window,
        'parallel_execute',
        lambda sql, **kwargs: parallel_calls.append((sql, kwargs)),
    )

    maintenance_window.refresh_sliding_window(batch_id=4)

    assert execute_calls[0][0] == 'DELETE FROM rebuild5.cell_sliding_window WHERE batch_id = %s'
    assert len(parallel_calls) == 2
    assert parallel_calls[0][1]['num_workers'] == maintenance_window.SLIDING_WINDOW_INSERT_WORKERS
    assert 'tech_norm' in parallel_calls[0][0]
    assert 'FROM rebuild5.snapshot_seed_records' in parallel_calls[1][0]
    assert "'snapshot_seed'" in parallel_calls[1][0]
    assert f"INTERVAL '{maintenance_window.WINDOW_RETENTION_DAYS} days'" in execute_calls[1][0]
    assert f'obs_rank <= {maintenance_window.WINDOW_MIN_OBS}' in execute_calls[1][0]


def test_build_cell_metrics_window_joins_materialized_stage_tables(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        maintenance_window,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(
        maintenance_window,
        'relation_exists',
        lambda name: name == 'rebuild5.cell_drift_stats',
    )

    maintenance_window.build_cell_metrics_window(batch_id=9)

    create_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_metrics_window AS' in sql
    )
    assert 'FROM rebuild5.cell_metrics_base m' in create_sql
    assert 'LEFT JOIN rebuild5.cell_radius_stats r' in create_sql
    assert 'LEFT JOIN rebuild5.cell_core_gps_stats cg' in create_sql
    assert 'LEFT JOIN rebuild5.cell_drift_stats d' in create_sql
    assert 'WHERE m.batch_id = 9' in create_sql


def test_build_cell_core_gps_stats_uses_mad_filter_stages(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        maintenance_window,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(
        maintenance_window,
        'load_antitoxin_params',
        lambda: {
            'core_mad_filter': {
                'k_mad': 3.0,
                'k_mad_small': 2.5,
                'k_mad_medium': 1.5,
                'k_mad_large': 2.5,
                'small_upper': 50,
                'large_lower': 200,
                'min_pts': 10,
            }
        },
    )
    monkeypatch.setattr(
        maintenance_window,
        'load_core_mad_filter_params',
        lambda _params: {
            'k_mad': 3.0,
            'k_mad_small': 2.5,
            'k_mad_medium': 1.5,
            'k_mad_large': 2.5,
            'small_upper': 50,
            'large_lower': 200,
            'min_pts': 10,
        },
    )

    maintenance_window.build_cell_core_gps_stats(batch_id=9)

    dedup_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_gps_day_dedup AS' in sql
    )
    initial_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_initial_center AS' in sql
    )
    dist_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_point_distance AS' in sql
    )
    mad_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_mad_stats AS' in sql
    )
    points_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_points AS' in sql
    )
    final_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_core_gps_stats AS' in sql
    )

    assert 'SELECT DISTINCT ON (' in dedup_sql
    assert "COALESCE(NULLIF(w.dev_id, ''), w.record_id)" in dedup_sql
    assert 'DATE(w.event_time_std)' in dedup_sql
    assert 'PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) AS center_lon0' in initial_sql
    assert 'dist_to_center0_m' in dist_sql
    assert 'mad_dist_m' in mad_sql
    assert 'effective_k_mad' in mad_sql
    assert 'keep_threshold_m' in mad_sql
    assert 'WHEN m.total_pts < 50 THEN 2.5' in mad_sql
    assert 'WHEN m.total_pts < 200 THEN 1.5' in mad_sql
    assert 'CASE' in points_sql and 's.total_pts < s.min_pts THEN TRUE' in points_sql
    assert 'COUNT(*) FILTER (WHERE is_core) AS core_gps_valid_count' in final_sql
    assert 'PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE is_core)' in final_sql


def test_build_cell_radius_stats_aggregates_core_and_raw_metrics_in_single_pass(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        maintenance_window,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )

    maintenance_window.build_cell_radius_stats()

    final_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_radius_stats AS' in sql
    )

    assert 'WITH with_dist AS (' in final_sql
    assert 'FROM rebuild5.cell_core_points p' in final_sql
    assert 'FILTER (WHERE is_core) AS p50_radius_m' in final_sql
    assert 'FILTER (WHERE is_core) AS p90_radius_m' in final_sql
    assert 'AS raw_p90_radius_m' in final_sql
    assert 'COUNT(*) FILTER (WHERE is_core) AS core_gps_valid_count' in final_sql
    assert 'COUNT(*) AS raw_gps_valid_count' in final_sql
    assert 'COUNT(*) FILTER (WHERE is_core)::double precision / COUNT(*)' in final_sql


def test_build_profile_base_uses_device_day_dedup_and_adaptive_mad(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        profile_pipeline,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(profile_pipeline, '_disable_autovacuum', lambda _name: None)
    monkeypatch.setattr(
        profile_pipeline,
        'load_antitoxin_params',
        lambda: {
            'core_mad_filter': {
                'k_mad': 3.0,
                'k_mad_small': 2.5,
                'k_mad_medium': 1.5,
                'k_mad_large': 2.5,
                'small_upper': 50,
                'large_lower': 200,
                'min_pts': 10,
            }
        },
    )
    monkeypatch.setattr(
        profile_pipeline,
        'load_core_mad_filter_params',
        lambda _params: {
            'k_mad': 3.0,
            'k_mad_small': 2.5,
            'k_mad_medium': 1.5,
            'k_mad_large': 2.5,
            'small_upper': 50,
            'large_lower': 200,
            'min_pts': 10,
        },
    )

    profile_pipeline.build_profile_base('run_fix4')

    dedup_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5._profile_gps_day_dedup AS' in sql
    )
    mad_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5._profile_core_mad_stats AS' in sql
    )
    radius_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5._profile_radius AS' in sql
    )
    base_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.profile_base AS' in sql
    )

    assert 'SELECT DISTINCT ON (' in dedup_sql
    assert "COALESCE(NULLIF(dev_id, ''), record_id)" in dedup_sql
    assert 'DATE(event_time_std)' in dedup_sql
    assert 'effective_k_mad' in mad_sql
    assert 'WHEN m.total_pts < 50 THEN 2.5' in mad_sql
    assert 'WHEN m.total_pts < 200 THEN 1.5' in mad_sql
    assert 'FILTER (WHERE p.is_core) AS p90_radius_m' in radius_sql
    assert 'LEFT JOIN rebuild5._profile_core_gps g' in base_sql
    assert 'FROM rebuild5._profile_counts c' in base_sql


def test_build_cell_drift_stats_materializes_single_ctas(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        maintenance_cell_maintain,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )

    maintenance_cell_maintain.build_cell_drift_stats(batch_id=6)

    create_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE UNLOGGED TABLE rebuild5.cell_drift_stats AS' in sql
    )
    assert 'WITH spread AS (' in create_sql
    assert 'FULL OUTER JOIN endpoints e' in create_sql
    assert 'LEAST(' in create_sql


def test_enrichment_insert_retries_with_lower_parallelism_on_enospc(monkeypatch) -> None:
    calls = []
    execute_calls = []

    def fake_parallel(sql, **kwargs):
        calls.append(kwargs['num_workers'])
        if len(calls) == 1:
            raise RuntimeError('parallel_execute 失败（1/12 个进程出错）: could not extend file x with FileFallocate(): No space left on device')

    monkeypatch.setattr(enrichment_pipeline, 'parallel_execute', fake_parallel)
    monkeypatch.setattr(
        enrichment_pipeline,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(enrichment_pipeline, 'ensure_enrichment_schema', lambda: execute_calls.append(('ensure_enrichment_schema', None)))

    enrichment_pipeline._insert_enriched_records(batch_id=2, run_id='enrich_001')

    assert calls == [enrichment_pipeline.NUM_WORKERS_INSERT, 4]
    assert (
        'DELETE FROM rebuild5.enriched_records WHERE batch_id = %s',
        (2,),
    ) in execute_calls
    assert (
        'DELETE FROM rebuild5.gps_anomaly_log WHERE batch_id = %s',
        (2,),
    ) in execute_calls


def test_enrichment_uses_any_matched_published_donor_for_fill(monkeypatch) -> None:
    sql_calls = []

    monkeypatch.setattr(
        enrichment_pipeline,
        'parallel_execute',
        lambda sql, **kwargs: sql_calls.append((sql, kwargs)),
    )

    enrichment_pipeline._insert_enriched_records(batch_id=3, run_id='enrich_anchor_guard')

    sql, kwargs = sql_calls[0]
    assert kwargs['num_workers'] == enrichment_pipeline.NUM_WORKERS_INSERT
    assert 'p.donor_batch_id IS NOT NULL' in sql
    assert 'CASE WHEN p.donor_batch_id IS NOT NULL THEN p.donor_center_lon END' in sql
    assert 'CASE WHEN p.donor_batch_id IS NOT NULL THEN p.donor_rsrp_avg END' in sql


def test_gps_anomaly_log_uses_any_matched_donor_with_center(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        enrichment_pipeline,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )
    monkeypatch.setattr(enrichment_pipeline, 'relation_exists', lambda _name: False)

    enrichment_pipeline._insert_gps_anomaly_log(
        batch_id=5,
        anomaly_threshold_m=2200.0,
        donor_batch_id=4,
    )

    sql, params = execute_calls[0]
    assert params == (2200.0, 5, 2200.0)
    assert 'e.donor_batch_id IS NOT NULL' in sql
    assert 'COALESCE(e.gps_valid, FALSE)' in sql
    assert 'AND NOT COALESCE(e.path_a_is_collision, FALSE)' in sql
    assert 'tech_norm' in sql
    assert 'COALESCE(e.donor_operator_code, e.operator_final, e.operator_code)' in sql
    assert 'COALESCE(e.donor_lac, e.lac_final, e.lac)' in sql
    assert 'COALESCE(e.donor_cell_id, e.cell_id)' in sql
    assert 'COALESCE(e.donor_tech_norm, e.tech_final, e.tech_norm)' in sql


def test_enriched_records_carries_path_a_collision_flag(monkeypatch) -> None:
    sql_calls = []

    monkeypatch.setattr(
        enrichment_pipeline,
        'parallel_execute',
        lambda sql, **kwargs: sql_calls.append((sql, kwargs)),
    )

    enrichment_pipeline._insert_enriched_records(batch_id=3, run_id='enrich_collision_flag')

    sql, _kwargs = sql_calls[0]
    assert 'path_a_is_collision' in sql
    assert 'p.path_a_is_collision' in sql
