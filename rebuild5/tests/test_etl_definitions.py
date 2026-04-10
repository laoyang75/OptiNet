from rebuild5.backend.app.etl.definitions import RAW_FIELD_DEFINITIONS, summarize_decisions


EXPECTED_PARSE_FIELDS = {"gps_info_type", "cell_infos", "ss1"}


def test_raw_field_definitions_match_frozen_counts() -> None:
    assert len(RAW_FIELD_DEFINITIONS) == 27
    assert summarize_decisions(RAW_FIELD_DEFINITIONS) == {
        "keep": 17,
        "parse": 3,
        "drop": 7,
    }


def test_expected_parse_fields_are_present() -> None:
    parse_fields = {field["name"] for field in RAW_FIELD_DEFINITIONS if field["decision"] == "parse"}

    assert parse_fields == EXPECTED_PARSE_FIELDS
