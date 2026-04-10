from fastapi.testclient import TestClient

from rebuild5.backend.app.main import app


client = TestClient(app)


def test_profile_run_endpoint_wraps_pipeline_result(monkeypatch) -> None:
    from rebuild5.backend.app.routers import profile as profile_router

    monkeypatch.setattr(
        profile_router,
        'run_profile_pipeline',
        lambda: {'run_id': 'profile_001', 'dataset_key': 'sample_6lac', 'snapshot_version': 'v1'},
    )

    response = client.post('/api/routing/run')

    assert response.status_code == 200
    assert response.json()['data']['run_id'] == 'profile_001'
    assert response.json()['error'] is None


def test_profile_routing_endpoint_returns_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import profile as profile_router

    monkeypatch.setattr(
        profile_router,
        'get_routing_payload',
        lambda: {'summary': {'input_record_count': 10}, 'rules': {'collision_match_gps_threshold_m': 2200}},
    )

    response = client.get('/api/routing/stats')

    assert response.status_code == 200
    assert response.json()['data']['summary']['input_record_count'] == 10
    assert response.json()['error'] is None


def test_evaluation_overview_endpoint_returns_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import evaluation as evaluation_router

    monkeypatch.setattr(
        evaluation_router,
        'get_evaluation_overview_payload',
        lambda batch_id=None: {'snapshot_version': 'v1', 'cell_distribution': {'waiting': 1, 'observing': 2, 'qualified': 3, 'excellent': 0, 'dormant': 0, 'retired': 0}},
    )

    response = client.get('/api/evaluation/overview')

    assert response.status_code == 200
    assert response.json()['data']['snapshot_version'] == 'v1'
    assert response.json()['error'] is None
