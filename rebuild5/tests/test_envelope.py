from rebuild5.backend.app.core.envelope import success_envelope, error_envelope


def test_success_envelope_has_expected_shape() -> None:
    payload = success_envelope({"value": 1}, meta={"dataset_key": "sample_6lac"})

    assert payload == {
        "data": {"value": 1},
        "meta": {"dataset_key": "sample_6lac"},
        "error": None,
    }


def test_error_envelope_has_expected_shape() -> None:
    payload = error_envelope("STEP_NOT_READY", "Step 2 尚未运行", meta={"dataset_key": "sample_6lac"})

    assert payload == {
        "data": None,
        "meta": {"dataset_key": "sample_6lac"},
        "error": {
            "code": "STEP_NOT_READY",
            "message": "Step 2 尚未运行",
        },
    }
