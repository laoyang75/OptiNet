from fastapi.testclient import TestClient

from rebuild5.backend.app.main import app


client = TestClient(app)


def test_run_endpoint_returns_pipeline_summary(monkeypatch) -> None:
    from rebuild5.backend.app.routers import etl as etl_router

    monkeypatch.setattr(
        etl_router,
        'run_step1_pipeline',
        lambda: {'run_id': 'step1_001', 'parsed_record_count': 10, 'cleaned_record_count': 8, 'filled_record_count': 8},
    )

    response = client.post('/api/etl/run')

    assert response.status_code == 200
    assert response.json()['data']['run_id'] == 'step1_001'
    assert response.json()['error'] is None


def test_source_endpoint_wraps_query_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import etl as etl_router

    monkeypatch.setattr(
        etl_router,
        'get_etl_source_payload',
        lambda: {'sources': [{'source_id': 'sample_6lac_raw_lac'}], 'summary': {'source_count': 1}},
    )

    response = client.get('/api/etl/source')

    assert response.status_code == 200
    assert response.json()['data']['summary']['source_count'] == 1
    assert response.json()['error'] is None
