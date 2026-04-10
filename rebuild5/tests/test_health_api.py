from fastapi.testclient import TestClient

from rebuild5.backend.app.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get('/api/system/health')

    assert response.status_code == 200
    assert response.json() == {
        "data": {"status": "ok", "service": "rebuild5-backend"},
        "meta": {"service": "rebuild5", "version": "0.1.0"},
        "error": None,
    }
