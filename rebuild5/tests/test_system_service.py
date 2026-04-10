from rebuild5.backend.app.services.system import build_system_config_payload, list_run_logs


DATASETS = [
    {
        "dataset_key": "sample_6lac",
        "source_desc": "6 LAC 样本",
        "imported_at": "2026-04-09T00:00:00+08:00",
        "record_count": 420000,
        "lac_scope": "4176,6402,6411,73733,405512,2097233",
        "time_range": "2025-12-01 ~ 2025-12-07",
        "status": "ready",
        "is_current": True,
        "last_run_id": "run_20260409_001",
        "last_snapshot_version": "v1",
        "last_run_status": "published",
        "last_updated_at": "2026-04-09 02:00:00",
    }
]

RULES = {
    "profile": {"cell": {"qualified": {"min_independent_obs": 3}}},
    "antitoxin": {"collision": {"min_spread_m": 2200}},
    "retention": {"waiting": {"max_inactive_batches": 3}},
}


def test_build_system_config_payload_shapes_current_version() -> None:
    payload = build_system_config_payload(DATASETS, RULES)

    assert payload["current_version"] == {
        "dataset_key": "sample_6lac",
        "run_id": "run_20260409_001",
        "snapshot_version": "v1",
        "status": "published",
        "updated_at": "2026-04-09 02:00:00",
    }
    assert payload["datasets"][0]["dataset_key"] == "sample_6lac"
    assert payload["params"]["profile"]["cell"]["qualified"]["min_independent_obs"] == 3


def test_list_run_logs_returns_empty_when_metadata_table_missing() -> None:
    def missing_run_log(_: str, params=None) -> list[dict]:
        raise RuntimeError('relation "rebuild5_meta.run_log" does not exist')

    assert list_run_logs(fetchall_fn=missing_run_log) == []
