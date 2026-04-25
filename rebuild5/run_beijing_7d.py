import os, sys
PROJECT_ROOT = '/Users/yangcongan/cursor/WangYou_Data'
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print("=== Step 0: 数据准备 ===")
from rebuild5.backend.app.etl.source_prep import prepare_current_dataset
from rebuild5.backend.app.core.database import fetchone, fetchall, execute

result = prepare_current_dataset()
print('数据准备完成:', result)

row = fetchone('SELECT COUNT(*) AS cnt FROM rb5.raw_gps')
print(f"合并去重后: {row['cnt']} 行")
assert int(row['cnt']) > 20_000_000, f"行数异常: {row['cnt']}"
row2 = fetchone('SELECT COUNT(*) AS cnt FROM rb5.raw_lac')
assert int(row2['cnt']) == 0, "raw_lac 应为空"

print("=== Step 1: ETL ===")
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
result = run_step1_pipeline()
print('Step 1 完成:', result)

parsed = fetchone('SELECT COUNT(*) AS cnt FROM rb5.etl_parsed')
cleaned = fetchone('SELECT COUNT(*) AS cnt FROM rb5.etl_cleaned')
print(f"解析后: {parsed['cnt']}, 清洗后: {cleaned['cnt']}")
assert int(parsed['cnt']) > int(cleaned['cnt']), "清洗应有过滤"
assert int(cleaned['cnt']) > 20_000_000, "清洗后数据量应大于2000万"

ratio = int(cleaned['cnt']) / int(parsed['cnt'])
print(f"清洗通过率: {ratio:.4f}")
assert ratio > 0.95, f"通过率异常: {ratio}"

coverage = fetchone('''
    SELECT
        COUNT(*) FILTER (WHERE cell_id IS NOT NULL)::float / COUNT(*) AS cell_id_rate,
        COUNT(*) FILTER (WHERE lac IS NOT NULL)::float / COUNT(*) AS lac_rate,
        COUNT(*) FILTER (WHERE lon_raw IS NOT NULL AND gps_valid)::float / COUNT(*) AS gps_rate,
        COUNT(*) FILTER (WHERE event_time_std IS NOT NULL)::float / COUNT(*) AS event_time_rate
    FROM rb5.etl_cleaned
''')
print(f"覆盖率 - cell_id: {coverage['cell_id_rate']:.4f}, lac: {coverage['lac_rate']:.4f}, gps: {coverage['gps_rate']:.4f}, event_time: {coverage['event_time_rate']:.4f}")
assert float(coverage['cell_id_rate']) > 0.99, "cell_id 覆盖率应 > 99%"
assert float(coverage['event_time_rate']) > 0.99, "event_time 覆盖率应 > 99%"

execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_cell ON rb5.etl_cleaned (cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_op_lac_cell ON rb5.etl_cleaned (operator_filled, lac_filled, cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_bs ON rb5.etl_cleaned (bs_id)')
execute('CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rb5.etl_cleaned (record_id)')
print('Step 1 索引创建完成')

print("=== Step 2+3: 路由分流 + 流式评估 ===")
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
result = run_profile_pipeline()
print('Step 2+3 完成:', result)

print(f"Path A: {result['path_a_record_count']}, Path B cells: {result['path_b_cell_count']}, Path C: {result['path_c_drop_count']}")
total = result['path_a_record_count'] + result['path_b_record_count'] + result['path_c_drop_count']
print(f"总计: {total}")

states = fetchall('''
    SELECT lifecycle_state, COUNT(*) AS cnt
    FROM rb5.trusted_snapshot_cell
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_snapshot_cell)
    GROUP BY lifecycle_state ORDER BY cnt DESC
''')
for s in states:
    print(f"  {s['lifecycle_state']}: {s['cnt']}")

sample = fetchone('''
    SELECT cell_id, center_lon, center_lat, p50_radius_m, p90_radius_m, independent_obs
    FROM rb5.trusted_snapshot_cell
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_snapshot_cell)
      AND lifecycle_state = 'excellent' AND p90_radius_m IS NOT NULL
    ORDER BY independent_obs DESC LIMIT 1
''')
if sample:
    print(f"质心验证 cell {sample['cell_id']}: center=({sample['center_lon']:.4f}, {sample['center_lat']:.4f}), P50={sample['p50_radius_m']:.1f}m, P90={sample['p90_radius_m']:.1f}m, obs={sample['independent_obs']}")
    assert float(sample['p50_radius_m']) < float(sample['p90_radius_m']), "P50 应 < P90"
    assert float(sample['p90_radius_m']) < 500, f"excellent Cell P90 应 < 500m, 实际 {sample['p90_radius_m']}"
    assert 73 < float(sample['center_lon']) < 135, "经度应在中国范围"
    assert 3 < float(sample['center_lat']) < 54, "纬度应在中国范围"

execute('CREATE INDEX IF NOT EXISTS idx_path_a_cell ON rb5.path_a_records (cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_path_a_op_cell ON rb5.path_a_records (operator_filled, lac_filled, cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_snapshot_cell_batch ON rb5.trusted_snapshot_cell (batch_id, cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_snapshot_bs_batch ON rb5.trusted_snapshot_bs (batch_id, bs_id)')
print('Step 2+3 索引创建完成')

print("=== Step 4: 知识补数 ===")
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
result = run_enrichment_pipeline()
print('Step 4 完成:', result)

enriched = fetchone('SELECT COUNT(*) AS cnt FROM rb5.enriched_records WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.enriched_records)')
anomaly = fetchone('SELECT COUNT(*) AS cnt FROM rb5.gps_anomaly_log WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.gps_anomaly_log)')
print(f"补数记录: {enriched['cnt']}, GPS异常: {anomaly['cnt']}")

if result['total_path_a'] > 0:
    print(f"GPS 补数率: {result['gps_fill_rate']:.4f}")
    print(f"信号补数率: {result['signal_fill_rate']:.4f}")
    assert result['gps_fill_rate'] < 0.5, "GPS 补数率不应超过 50%"

execute('CREATE INDEX IF NOT EXISTS idx_enriched_cell ON rb5.enriched_records (cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_enriched_batch ON rb5.enriched_records (batch_id)')
execute('CREATE INDEX IF NOT EXISTS idx_enriched_op_cell ON rb5.enriched_records (operator_code, lac, bs_id, cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_anomaly_cell ON rb5.gps_anomaly_log (cell_id)')
print('Step 4 索引创建完成')

print("=== Step 5: 画像维护 ===")
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
result = run_maintenance_pipeline()
print('Step 5 完成:', result)

print(f"Cell 库: {result['published_cell_count']}, BS 库: {result['published_bs_count']}, LAC 库: {result['published_lac_count']}")

states = fetchall('''
    SELECT lifecycle_state, COUNT(*) FROM rb5.trusted_cell_library
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_cell_library)
    GROUP BY lifecycle_state
''')
for s in states:
    print(f"  Cell {s['lifecycle_state']}: {s['count']}")
    assert s['lifecycle_state'] in ('qualified', 'excellent'), f"不应有 {s['lifecycle_state']} 进入可信库"

bs_states = fetchall('''
    SELECT lifecycle_state, COUNT(*) FROM rb5.trusted_bs_library
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_bs_library)
    GROUP BY lifecycle_state
''')
for s in bs_states:
    assert s['lifecycle_state'] == 'qualified', f"BS 库不应有 {s['lifecycle_state']}"

print(f"碰撞 Cell: {result['collision_cell_count']}, 多质心: {result['multi_centroid_cell_count']}")

drifts = fetchall('''
    SELECT drift_pattern, COUNT(*) AS cnt FROM rb5.trusted_cell_library
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_cell_library)
    GROUP BY drift_pattern ORDER BY cnt DESC
''')
for d in drifts:
    print(f"  漂移 {d['drift_pattern']}: {d['cnt']}")

window = fetchone('''
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE window_obs_count > 0) AS has_window,
           AVG(window_obs_count) FILTER (WHERE window_obs_count > 0) AS avg_window
    FROM rb5.trusted_cell_library
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_cell_library)
''')
if window['has_window'] is not None and window['has_window'] > 0:
    print(f"有窗口数据: {window['has_window']}/{window['total']}, 平均窗口量: {window['avg_window']:.1f}")
else:
    print(f"有窗口数据: 0/{window['total']}, 平均窗口量: 0")

bs_sample = fetchone('''
    SELECT bs_id, center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m, total_cells
    FROM rb5.trusted_bs_library
    WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_bs_library)
      AND center_lon IS NOT NULL
    ORDER BY total_cells DESC LIMIT 1
''')
if bs_sample:
    print(f"BS 质心验证 bs {bs_sample['bs_id']}: center=({bs_sample['center_lon']:.4f}, {bs_sample['center_lat']:.4f}), P50={bs_sample['gps_p50_dist_m']:.0f}m, P90={bs_sample['gps_p90_dist_m']:.0f}m, cells={bs_sample['total_cells']}")
    assert 73 < float(bs_sample['center_lon']) < 135, "BS 经度异常"

execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_cell ON rb5.trusted_cell_library (batch_id, cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_op ON rb5.trusted_cell_library (batch_id, operator_code)')
execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_lac ON rb5.trusted_cell_library (batch_id, lac)')
execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_bs ON rb5.trusted_cell_library (batch_id, bs_id)')
execute('CREATE INDEX IF NOT EXISTS idx_tcl_batch_state ON rb5.trusted_cell_library (batch_id, lifecycle_state)')
execute('CREATE INDEX IF NOT EXISTS idx_tbl_batch_bs ON rb5.trusted_bs_library (batch_id, bs_id)')
execute('CREATE INDEX IF NOT EXISTS idx_tbl_batch_lac ON rb5.trusted_bs_library (batch_id, lac)')
execute('CREATE INDEX IF NOT EXISTS idx_tll_batch_lac ON rb5.trusted_lac_library (batch_id, lac)')
execute('CREATE INDEX IF NOT EXISTS idx_collision_cell ON rb5.collision_id_list (cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_centroid_cell ON rb5.cell_centroid_detail (cell_id)')
execute('CREATE INDEX IF NOT EXISTS idx_centroid_bs ON rb5.bs_centroid_detail (bs_id)')
print('Step 5 索引创建完成')

print("=== 最终总览 ===")
summary = fetchone('''
    SELECT
        (SELECT COUNT(*) FROM rb5.raw_gps) AS raw_count,
        (SELECT COUNT(*) FROM rb5.etl_cleaned) AS cleaned_count,
        (SELECT COUNT(*) FROM rb5.path_a_records) AS path_a_count,
        (SELECT COUNT(*) FROM rb5.enriched_records WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.enriched_records)) AS enriched_count,
        (SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_cell_library)) AS cell_count,
        (SELECT COUNT(*) FROM rb5.trusted_bs_library WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_bs_library)) AS bs_count,
        (SELECT COUNT(*) FROM rb5.trusted_lac_library WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_lac_library)) AS lac_count,
        (SELECT COUNT(DISTINCT lac) FROM rb5.trusted_cell_library WHERE batch_id = (SELECT MAX(batch_id) FROM rb5.trusted_cell_library)) AS distinct_lacs
''')
print('=== 北京 7 天全量处理总览 ===')
print(f"原始合并: {summary['raw_count']}")
print(f"ETL 清洗后: {summary['cleaned_count']}")
print(f"Path A 命中: {summary['path_a_count']}")
print(f"Step 4 补数: {summary['enriched_count']}")
print(f"可信 Cell 库: {summary['cell_count']}")
print(f"可信 BS 库: {summary['bs_count']}")
print(f"可信 LAC 库: {summary['lac_count']}")
print(f"覆盖 LAC 数: {summary['distinct_lacs']}")
