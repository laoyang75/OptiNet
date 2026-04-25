"""Step 5 stats collection and run-log writers."""
from __future__ import annotations

import json
from typing import Any

from ..core.database import execute, fetchone
from ..etl.source_prep import DATASET_KEY


def collect_step5_stats(
    *, run_id: str, batch_id: int,
    snapshot_version: str, snapshot_version_prev: str,
) -> dict[str, Any]:
    row = fetchone(
        """
        SELECT
            (SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id = %s) AS published_cell_count,
            (SELECT COUNT(*) FROM rb5.trusted_bs_library WHERE batch_id = %s) AS published_bs_count,
            (SELECT COUNT(*) FROM rb5.trusted_lac_library WHERE batch_id = %s) AS published_lac_count,
            (SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id = %s AND is_collision) AS collision_cell_count,
            (SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id = %s AND is_multi_centroid) AS multi_centroid_cell_count,
            (SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id = %s AND is_dynamic) AS dynamic_cell_count,
            (SELECT COUNT(*) FROM rb5.trusted_bs_library WHERE batch_id = %s
                AND classification IN ('large_spread', 'dynamic_bs')) AS anomaly_bs_count
        """,
        (batch_id, batch_id, batch_id, batch_id, batch_id, batch_id, batch_id),
    ) or {}
    return {
        'run_id': run_id,
        'batch_id': batch_id,
        'dataset_key': DATASET_KEY,
        'snapshot_version': snapshot_version,
        'snapshot_version_prev': snapshot_version_prev,
        'status': 'completed',
        'published_cell_count': int(row.get('published_cell_count') or 0),
        'published_bs_count': int(row.get('published_bs_count') or 0),
        'published_lac_count': int(row.get('published_lac_count') or 0),
        'collision_cell_count': int(row.get('collision_cell_count') or 0),
        'multi_centroid_cell_count': int(row.get('multi_centroid_cell_count') or 0),
        'dynamic_cell_count': int(row.get('dynamic_cell_count') or 0),
        'anomaly_bs_count': int(row.get('anomaly_bs_count') or 0),
    }


def write_step5_stats(stats: dict[str, Any]) -> None:
    execute('DELETE FROM rb5_meta.step5_run_stats WHERE run_id = %s', (stats['run_id'],))
    execute(
        """
        INSERT INTO rb5_meta.step5_run_stats (
            run_id, batch_id, dataset_key, snapshot_version, snapshot_version_prev, status,
            started_at, finished_at,
            published_cell_count, published_bs_count, published_lac_count,
            collision_cell_count, multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            NOW(), NOW(),
            %s, %s, %s,
            %s, %s, %s, %s
        )
        """,
        (
            stats['run_id'], stats['batch_id'], stats['dataset_key'],
            stats['snapshot_version'], stats['snapshot_version_prev'], stats['status'],
            stats['published_cell_count'], stats['published_bs_count'], stats['published_lac_count'],
            stats['collision_cell_count'], stats['multi_centroid_cell_count'],
            stats['dynamic_cell_count'], stats['anomaly_bs_count'],
        ),
    )


def write_run_log(*, run_id: str, snapshot_version: str,
                  status: str, result_summary: dict[str, Any]) -> None:
    execute('DELETE FROM rb5_meta.run_log WHERE run_id = %s', (run_id,))
    execute(
        """
        INSERT INTO rb5_meta.run_log (
            run_id, run_type, dataset_key, snapshot_version, status,
            started_at, finished_at, step_chain, result_summary, error
        ) VALUES (
            %s, %s, %s, %s, %s,
            NOW(), NOW(), %s, %s::jsonb, NULL
        )
        """,
        (run_id, 'maintenance', DATASET_KEY, snapshot_version, status,
         'step5', json.dumps(result_summary, ensure_ascii=False)),
    )
