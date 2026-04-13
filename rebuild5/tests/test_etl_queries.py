from rebuild5.backend.app.etl.queries import build_clean_rule_rows, build_etl_stats_payload


LATEST_STATS = {
    'run_id': 'step1_20260409_001',
    'dataset_key': 'sample_6lac',
    'raw_record_count': 300,
    'parsed_record_count': 900,
    'cleaned_record_count': 840,
    'filled_record_count': 840,
    'clean_deleted_count': 60,
    'clean_pass_rate': 0.9333,
    'field_coverage': {
        'cell_id': 1.0,
        'lac': 0.98,
        'operator_code': 0.92,
        'lon_raw': 0.70,
        'lat_raw': 0.70,
        'rsrp': 0.73,
        'tech_norm': 0.88,
    },
    'clean_rules': [
        {
            'id': 'ODS-006',
            'name': 'CellID=0 删行',
            'desc': '无有效小区标识',
            'violations': 12,
            'deleted_rows': 12,
            'pass_rate': 0.96,
        }
    ],
}

SOURCES = [
    {'source_id': 'sample_6lac_raw_lac'},
    {'source_id': 'sample_6lac_raw_gps'},
]


def test_build_etl_stats_payload_exposes_frontend_summary_fields() -> None:
    payload = build_etl_stats_payload(LATEST_STATS, SOURCES)

    assert payload == {
        'source_count': 2,
        'raw_record_count': 300,
        'parsed_record_count': 900,
        'cleaned_record_count': 840,
        'filled_record_count': 840,
        'clean_pass_rate': 0.9333,
        'field_coverage': LATEST_STATS['field_coverage'],
    }


def test_build_clean_rule_rows_uses_frontend_field_names() -> None:
    rows = build_clean_rule_rows(LATEST_STATS['clean_rules'])

    assert rows == [
        {
            'rule_id': 'ODS-006',
            'rule_name': 'CellID=0 删行',
            'description': '无有效小区标识',
            'hit_count': 12,
            'drop_count': 12,
            'pass_rate': 0.96,
        }
    ]
