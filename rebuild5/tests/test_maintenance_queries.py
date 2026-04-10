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
