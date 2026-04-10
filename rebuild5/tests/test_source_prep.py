from rebuild5.backend.app.etl.source_prep import (
    LEGACY_GPS_TABLE,
    LEGACY_LAC_TABLE,
    TARGET_LACS,
    build_dataset_registry_row,
    build_schema_sql,
    build_source_registry_rows,
)


EXPECTED_TARGET_LACS = ('4176', '6402', '6411', '73733', '405512', '2097233')


def test_target_lacs_match_frozen_sample_scope() -> None:
    assert TARGET_LACS == EXPECTED_TARGET_LACS


def test_schema_sql_contains_required_schemas_and_tables() -> None:
    sql = build_schema_sql()

    assert 'CREATE SCHEMA IF NOT EXISTS rebuild5;' in sql
    assert 'CREATE SCHEMA IF NOT EXISTS rebuild5_meta;' in sql
    assert 'CREATE TABLE IF NOT EXISTS rebuild5_meta.dataset_registry' in sql
    assert 'CREATE TABLE IF NOT EXISTS rebuild5_meta.source_registry' in sql
    assert 'CREATE TABLE IF NOT EXISTS rebuild5_meta.run_log' in sql
    assert 'CREATE TABLE IF NOT EXISTS rebuild5_meta.step1_run_stats' in sql


def test_build_dataset_registry_row_marks_sample_as_current() -> None:
    row = build_dataset_registry_row(raw_record_count=420000)

    assert row['dataset_key'] == 'sample_6lac'
    assert row['record_count'] == 420000
    assert row['lac_scope'] == ','.join(EXPECTED_TARGET_LACS)
    assert row['is_current'] is True


def test_build_source_registry_rows_use_frozen_legacy_tables() -> None:
    rows = build_source_registry_rows(raw_lac_count=123, raw_gps_count=456)

    assert rows == [
        {
            'source_id': 'sample_6lac_raw_lac',
            'source_name': '6 LAC 样本 - LAC 原表子集',
            'source_table': LEGACY_LAC_TABLE,
            'source_type': 'lac_raw',
            'row_count': 123,
        },
        {
            'source_id': 'sample_6lac_raw_gps',
            'source_name': '6 LAC 样本 - GPS 原表子集',
            'source_table': LEGACY_GPS_TABLE,
            'source_type': 'gps_raw',
            'row_count': 456,
        },
    ]
