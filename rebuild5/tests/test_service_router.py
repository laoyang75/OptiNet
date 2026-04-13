from fastapi.testclient import TestClient

from rebuild5.backend.app.main import app


client = TestClient(app)


def test_service_search_endpoint_wraps_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import service as service_router

    monkeypatch.setattr(
        service_router,
        'search_service_payload',
        lambda q=None, level='cell', operator_code=None, page=1, page_size=50: {
            'query': {'q': q or '', 'level': level, 'operator_code': operator_code},
            'items': [{'level': 'cell', 'cell_id': 1001}],
        },
    )

    response = client.get('/api/service/search?q=1001')

    assert response.status_code == 200
    assert response.json()['data']['items'][0]['cell_id'] == 1001
    assert response.json()['error'] is None


def test_service_cell_endpoint_wraps_payload(monkeypatch) -> None:
    from rebuild5.backend.app.routers import service as service_router

    monkeypatch.setattr(
        service_router,
        'get_service_cell_payload',
        lambda cell_id, operator_code=None, lac=None, tech_norm=None: {
            'cell_id': cell_id,
            'operator_code': operator_code or '46000',
            'lac': lac,
            'tech_norm': tech_norm,
            'lifecycle_state': 'excellent',
        },
    )

    response = client.get('/api/service/cell/1001?operator_code=46000&lac=123&tech_norm=5G')

    assert response.status_code == 200
    assert response.json()['data']['cell_id'] == 1001
    assert response.json()['data']['operator_code'] == '46000'
    assert response.json()['data']['lac'] == 123
    assert response.json()['data']['tech_norm'] == '5G'
    assert response.json()['error'] is None
