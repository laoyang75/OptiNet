"""API integration tests using FastAPI TestClient."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

BASE = "http://test"
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_pipeline_overview():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["total_tables"] == 18
    assert data["total_rows"] > 0


@pytest.mark.asyncio
async def test_steps_list():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/steps")
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) == 22
    assert steps[0]["step_id"] == "s0"


@pytest.mark.asyncio
async def test_step_detail():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/steps/s4")
    assert r.status_code == 200
    assert r.json()["step_name"] == "可信LAC"


@pytest.mark.asyncio
async def test_step_parameters():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/steps/s30/parameters")
    assert r.status_code == 200
    data = r.json()
    assert data["parameter_set"] == "P-001"
    assert data["step"]["outlier_dist_m"] == 2500


@pytest.mark.asyncio
async def test_step_io_summary():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/steps/s4/io-summary")
    assert r.status_code == 200
    tables = r.json()["tables"]
    assert any(t["table_name"] == "dim_lac_trusted" for t in tables)


@pytest.mark.asyncio
async def test_dim_lac_trusted():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/dim/lac-trusted?page_size=5")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 881
    assert len(data["data"]) == 5


@pytest.mark.asyncio
async def test_dim_lac_trusted_filter():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/dim/lac-trusted?operator=46000&tech=4G")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0
    for item in data["data"]:
        assert item["operator_id_raw"] == "46000"
        assert item["tech_norm"] == "4G"


@pytest.mark.asyncio
async def test_dim_bs_trusted():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/dim/bs-trusted?page_size=3")
    assert r.status_code == 200
    assert r.json()["total"] == 138121


@pytest.mark.asyncio
async def test_dim_bs_collision_filter():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/dim/bs-trusted?collision_only=true&page_size=3")
    assert r.status_code == 200
    for item in r.json()["data"]:
        assert item["is_collision_suspect"] is True


@pytest.mark.asyncio
async def test_profile_lac():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/profile/lac")
    assert r.status_code == 200
    assert r.json()["total"] == 878


@pytest.mark.asyncio
async def test_profile_bs():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/profile/bs?page_size=3")
    assert r.status_code == 200
    assert r.json()["total"] == 163778


@pytest.mark.asyncio
async def test_profile_cell():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/profile/cell?dynamic_only=true&page_size=5")
    assert r.status_code == 200
    for item in r.json()["data"]:
        assert item["is_dynamic_cell"] is True


@pytest.mark.asyncio
async def test_layer_snapshot():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/metrics/layer-snapshot")
    assert r.status_code == 200
    layers = r.json()
    assert len(layers) == 12
    raw = next(l for l in layers if l["layer_id"] == "L0_raw")
    assert raw["row_count"] > 200_000_000


@pytest.mark.asyncio
async def test_step_summary():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/metrics/step-summary")
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) >= 7


@pytest.mark.asyncio
async def test_anomaly_summary():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/metrics/anomaly-summary")
    assert r.status_code == 200
    anomalies = r.json()
    assert len(anomalies) == 9


@pytest.mark.asyncio
async def test_stats_operator_tech():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/pipeline/stats/operator-tech")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0
    total = sum(d["row_count"] for d in data)
    assert total > 30_000_000


@pytest.mark.asyncio
async def test_create_and_get_run():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.post("/api/v1/runs", json={
            "run_mode": "full_rerun",
            "note": "test run from pytest"
        })
        assert r.status_code == 201
        run = r.json()
        run_id = run["run_id"]
        assert run["status"] == "running"

        r2 = await c.get(f"/api/v1/runs/{run_id}")
        assert r2.status_code == 200
        assert r2.json()["run_id"] == run_id

        r3 = await c.patch(f"/api/v1/runs/{run_id}/status?status=completed")
        assert r3.status_code == 200

        r4 = await c.get(f"/api/v1/runs/{run_id}")
        assert r4.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_runs_list():
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r = await c.get("/api/v1/runs")
    assert r.status_code == 200
    assert r.json()["total"] >= 1
