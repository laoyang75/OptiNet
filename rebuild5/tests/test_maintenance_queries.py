from rebuild5.backend.app.maintenance import queries as maintenance_queries
from rebuild5.backend.app.maintenance.queries import build_maintenance_stats_payload


SUMMARY = {
    'run_id': 'maint_001',
    'dataset_key': 'sample_6lac',
    'snapshot_version': 'v3',
    'snapshot_version_prev': 'v2',
    'published_cell_count': 4200,
    'published_bs_count': 1200,
    'published_lac_count': 100,
    'collision_cell_count': 12,
    'multi_centroid_cell_count': 18,
    'dynamic_cell_count': 25,
    'anomaly_bs_count': 61,
}

DRIFT_ROWS = [
    {'drift_pattern': 'stable', 'count': 3900},
    {'drift_pattern': 'collision', 'count': 12},
    {'drift_pattern': 'migration', 'count': 16},
]


def test_build_maintenance_stats_payload_shapes_summary_for_governance_pages() -> None:
    payload = build_maintenance_stats_payload(SUMMARY, DRIFT_ROWS)

    assert payload == {
        'version': {
            'run_id': 'maint_001',
            'dataset_key': 'sample_6lac',
            'snapshot_version': 'v3',
            'snapshot_version_prev': 'v2',
        },
        'summary': {
            'published_cell_count': 4200,
            'published_bs_count': 1200,
            'published_lac_count': 100,
            'collision_cell_count': 12,
            'multi_centroid_cell_count': 18,
            'dynamic_cell_count': 25,
            'anomaly_bs_count': 61,
        },
        'drift_distribution': {
            'stable': 3900,
            'collision': 12,
            'migration': 16,
            'insufficient': 0,
            'large_coverage': 0,
            'moderate_drift': 0,
        },
    }


def test_get_maintenance_cells_payload_supports_dormant_and_retired(monkeypatch) -> None:
    calls = []

    def fake_paginate(sql, page=1, page_size=50):
        calls.append(sql)
        return {'items': [], 'page': page, 'page_size': page_size, 'total_count': 0, 'total_pages': 0}

    monkeypatch.setattr(maintenance_queries, 'paginate', fake_paginate)
    monkeypatch.setattr(maintenance_queries, '_safe_fetchall', lambda *args, **kwargs: [])

    maintenance_queries.get_maintenance_cells_payload(kind='dormant')
    maintenance_queries.get_maintenance_cells_payload(kind='retired')

    assert "lifecycle_state = 'dormant'" in calls[0]
    assert "lifecycle_state = 'retired'" in calls[1]
