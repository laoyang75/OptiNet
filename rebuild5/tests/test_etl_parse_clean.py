from rebuild5.backend.app.etl import clean as etl_clean
from rebuild5.backend.app.etl import parse as etl_parse


def test_parse_ss1_requires_native_gps_info_type(monkeypatch) -> None:
    execute_calls = []

    monkeypatch.setattr(
        etl_parse,
        'execute',
        lambda sql, params=None: execute_calls.append((sql, params)),
    )

    etl_parse._parse_ss1('rebuild5.raw_gps', 'raw_gps', 'rebuild5.etl_ss1')

    parse_sql = next(
        sql for sql, _ in execute_calls
        if 'CREATE TABLE rebuild5.etl_ss1 AS' in sql
    )

    assert "WHEN c.gps_info_type IN ('gps', '1')" in parse_sql
    assert "c.gps_block != '0'" in parse_sql


def test_clean_rules_apply_native_gps_guard_to_all_sources() -> None:
    rule_13 = next(rule for rule in etl_clean.ODS_RULES if rule['id'] == 'ODS-013')
    rule_14 = next(rule for rule in etl_clean.ODS_RULES if rule['id'] == 'ODS-014')

    assert "cell_origin = 'cell_infos'" not in rule_13['where']
    assert "cell_origin = 'cell_infos'" not in rule_14['where']
    assert rule_13['where'] == "gps_info_type IS NULL OR gps_info_type NOT IN ('gps', '1')"
    assert rule_14['where'] == "gps_valid = false AND lon_raw IS NOT NULL"
