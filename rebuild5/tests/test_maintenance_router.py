from fastapi.testclient import TestClient

from rebuild5.backend.app.main import app


client = TestClient(app)


def test_maintenance_stats_endpoint_wraps_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import maintenance as maintenance_router

    monkeypatch.setattr(
        maintenance_router,
        'get_maintenance_stats_payload',
        lambda: {'summary': {'published_cell_count': 10}, 'drift_distribution': {'stable': 10}},
    )

    response = client.get('/api/maintenance/stats')

    assert response.status_code == 200
    assert response.json()['data']['summary']['published_cell_count'] == 10
    assert response.json()['error'] is None


def test_enrichment_stats_endpoint_wraps_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import enrichment as enrichment_router

    monkeypatch.setattr(
        enrichment_router,
        'get_enrichment_stats_payload',
        lambda: {'summary': {'total_path_a': 12}, 'coverage': {'gps_fill_rate': 0.75}},
    )

    response = client.get('/api/enrichment/stats')

    assert response.status_code == 200
    assert response.json()['data']['summary']['total_path_a'] == 12
    assert response.json()['error'] is None
