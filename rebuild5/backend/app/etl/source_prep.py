"""Dataset preparation for rebuild5 — configurable, no hardcoded dataset."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..core.database import execute, fetchone
from ..core.settings import settings


# ── Dataset configuration (loaded from config/dataset.yaml or defaults) ──

def _load_dataset_config() -> dict[str, Any]:
    config_path = Path(settings.config_dir) / 'dataset.yaml' if hasattr(settings, 'config_dir') else Path(__file__).resolve().parents[3] / 'config' / 'dataset.yaml'
    if config_path.exists():
        with config_path.open('r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_config() -> dict[str, Any]:
    cfg = _load_dataset_config()
    return {
        'dataset_key': cfg.get('dataset_key', 'beijing_7d'),
        'source_desc': cfg.get('source_desc', '北京 7 天全量'),
        'time_range': cfg.get('time_range', '2025-12-01 ~ 2025-12-07'),
        'legacy_gps_table': cfg.get('legacy_gps_table', 'legacy."网优项目_gps定位北京明细数据_20251201_20251207"'),
        'legacy_lac_table': cfg.get('legacy_lac_table', 'legacy."网优项目_lac定位北京明细数据_20251201_20251207"'),
    }


_cfg = _get_config()
DATASET_KEY = _cfg['dataset_key']


def build_schema_sql() -> str:
    return """
CREATE SCHEMA IF NOT EXISTS rebuild5;
CREATE SCHEMA IF NOT EXISTS rebuild5_meta;

CREATE TABLE IF NOT EXISTS rebuild5_meta.dataset_registry (
    dataset_key TEXT PRIMARY KEY,
    source_desc TEXT NOT NULL,
    imported_at TIMESTAMPTZ,
    record_count BIGINT NOT NULL,
    lac_scope TEXT NOT NULL,
    time_range TEXT NOT NULL,
    status TEXT NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    last_run_id TEXT,
    last_snapshot_version TEXT,
    last_run_status TEXT,
    last_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS rebuild5_meta.source_registry (
    source_id TEXT PRIMARY KEY,
    dataset_key TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_type TEXT NOT NULL,
    row_count BIGINT NOT NULL,
    status TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rebuild5_meta.run_log (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    dataset_key TEXT NOT NULL,
    snapshot_version TEXT,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    step_chain TEXT,
    result_summary JSONB,
    error TEXT
);

CREATE TABLE IF NOT EXISTS rebuild5_meta.step1_run_stats (
    run_id TEXT PRIMARY KEY,
    dataset_key TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    raw_record_count BIGINT NOT NULL DEFAULT 0,
    parsed_record_count BIGINT NOT NULL DEFAULT 0,
    cleaned_record_count BIGINT NOT NULL DEFAULT 0,
    filled_record_count BIGINT NOT NULL DEFAULT 0,
    clean_deleted_count BIGINT NOT NULL DEFAULT 0,
    clean_pass_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_count BIGINT NOT NULL DEFAULT 0,
    parse_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    fill_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_coverage_before JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    clean_rules JSONB NOT NULL DEFAULT '[]'::jsonb
);
""".strip()


def bootstrap_metadata_tables(execute_fn=execute) -> None:
    execute_fn(build_schema_sql())


def prepare_current_dataset(*, execute_fn=execute, fetchone_fn=fetchone) -> dict[str, Any]:
    """Prepare raw data tables for the dataset configured in ``config/dataset.yaml``.

    Note:
        rebuild5 currently runs in single-active dataset mode. Preparing a new
        dataset replaces the shared Step 0/1 tables instead of storing multiple
        datasets side by side for UI switching.

    Merges GPS and LAC legacy tables, deduplicates by 记录数唯一标识,
    and populates rebuild5.raw_gps (main input) and rebuild5.raw_lac (empty).
    """
    cfg = _get_config()
    run_id = f"prepare_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    bootstrap_metadata_tables(execute_fn=execute_fn)

    try:
        gps_table = cfg['legacy_gps_table']
        lac_table = cfg['legacy_lac_table']
        dataset_key = cfg['dataset_key']

        # Common columns (26 columns excluding the source-specific last column)
        common_cols = '''
            "记录数唯一标识", "数据来源dna或daa", "did", "ts", "ip", "pkg_name",
            "wifi_name", "wifi_mac", "sdk_ver", "gps上报时间", "主卡运营商id",
            "品牌", "机型", "gps_info_type", "原始上报gps", "cell_infos", "ss1",
            "当前数据最终经度", "当前数据最终纬度", "android_ver", "cpu_info",
            "基带版本信息", "arp_list", "压力", "imei", "oaid"
        '''

        # Merge and deduplicate
        execute_fn('DROP TABLE IF EXISTS rebuild5.raw_gps')
        execute_fn(
            f"""
            CREATE TABLE rebuild5.raw_gps AS
            SELECT DISTINCT ON ("记录数唯一标识") {common_cols}
            FROM (
                SELECT {common_cols} FROM {gps_table}
                UNION ALL
                SELECT {common_cols} FROM {lac_table}
            ) combined
            ORDER BY "记录数唯一标识"
            """
        )
        execute_fn('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_record_id ON rebuild5.raw_gps ("记录数唯一标识")')
        execute_fn('CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts ON rebuild5.raw_gps (ts)')
        execute_fn('DROP TABLE IF EXISTS rebuild5.raw_lac')

        counts = fetchone_fn(
            "SELECT COUNT(*) AS raw_gps_count FROM rebuild5.raw_gps"
        ) or {'raw_gps_count': 0}
        raw_record_count = int(counts['raw_gps_count'])

        # Registry
        execute_fn('UPDATE rebuild5_meta.dataset_registry SET is_current = FALSE')
        execute_fn('DELETE FROM rebuild5_meta.dataset_registry WHERE dataset_key = %s', (dataset_key,))
        execute_fn(
            """
            INSERT INTO rebuild5_meta.dataset_registry (
                dataset_key, source_desc, imported_at, record_count, lac_scope, time_range,
                status, is_current, last_run_id, last_snapshot_version, last_run_status, last_updated_at
            ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dataset_key, cfg['source_desc'], raw_record_count,
                'all', cfg['time_range'], 'ready', True,
                run_id, 'v0', 'completed', datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ),
        )

        execute_fn('DELETE FROM rebuild5_meta.source_registry WHERE dataset_key = %s', (dataset_key,))
        execute_fn(
            """
            INSERT INTO rebuild5_meta.source_registry (
                source_id, dataset_key, source_name, source_table, source_type, row_count, status, imported_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                f'{dataset_key}_merged', dataset_key,
                f'{cfg["source_desc"]} - 合并去重', 'rebuild5.raw_gps',
                'merged', int(counts['raw_gps_count']), 'active',
            ),
        )

        summary = {
            'dataset_key': dataset_key,
            'raw_gps_count': int(counts['raw_gps_count']),
            'raw_record_count': raw_record_count,
        }

        execute_fn('DELETE FROM rebuild5_meta.run_log WHERE run_id = %s', (run_id,))
        execute_fn(
            """
            INSERT INTO rebuild5_meta.run_log (
                run_id, run_type, dataset_key, snapshot_version, status,
                started_at, finished_at, step_chain, result_summary, error
            ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, %s::jsonb, %s)
            """,
            (run_id, 'bootstrap', dataset_key, 'v0', 'completed',
             'prepare-dataset', json.dumps(summary, ensure_ascii=False), None),
        )
        return {'run_id': run_id, **summary}
    except Exception as exc:
        execute_fn('DELETE FROM rebuild5_meta.run_log WHERE run_id = %s', (run_id,))
        execute_fn(
            """
            INSERT INTO rebuild5_meta.run_log (
                run_id, run_type, dataset_key, snapshot_version, status,
                started_at, finished_at, step_chain, result_summary, error
            ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, %s::jsonb, %s)
            """,
            (run_id, 'bootstrap', cfg['dataset_key'], 'v0', 'failed',
             'prepare-dataset', json.dumps({'dataset_key': cfg['dataset_key']}, ensure_ascii=False), str(exc)),
        )
        raise


def prepare_sample_dataset(*, execute_fn=execute, fetchone_fn=fetchone) -> dict[str, Any]:
    """Backward-compatible alias for historical scripts and runbooks."""
    return prepare_current_dataset(execute_fn=execute_fn, fetchone_fn=fetchone_fn)
