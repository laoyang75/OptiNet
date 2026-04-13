# 已废弃：Step 2 → Step 5 Clean Rerun Runbook

本文件保留为历史记录，不再作为执行标准。

当前标准 runbook 请使用：

- `rebuild5/scripts/runbook_beijing_7d_standard.md`

# Step 2 → Step 5 Clean Rerun Runbook

前提：

- `Step 1` 保留
- 本 runbook 只清空并重建 `Step 2 → Step 5`
- 在执行前，先阅读：
  - `rebuild5/docs/fix/round3_impact_assessment_and_rerun_plan.md`

## 1. 清理 Step 2 → Step 5 产物

```sql
-- Step 5 / Step 4 / Step 3 / Step 2 产物清理
TRUNCATE TABLE rebuild5.candidate_cell_pool;

TRUNCATE TABLE rebuild5.trusted_snapshot_cell;
TRUNCATE TABLE rebuild5.trusted_snapshot_bs;
TRUNCATE TABLE rebuild5.trusted_snapshot_lac;

TRUNCATE TABLE rebuild5.snapshot_diff_cell;
TRUNCATE TABLE rebuild5.snapshot_diff_bs;
TRUNCATE TABLE rebuild5.snapshot_diff_lac;

DROP TABLE IF EXISTS rebuild5.path_a_records;
DROP TABLE IF EXISTS rebuild5._profile_path_a_candidates;
DROP TABLE IF EXISTS rebuild5._profile_path_b_cells;
DROP TABLE IF EXISTS rebuild5._profile_path_b_records;
DROP TABLE IF EXISTS rebuild5.profile_obs;
DROP TABLE IF EXISTS rebuild5._profile_centroid;
DROP TABLE IF EXISTS rebuild5._profile_devs;
DROP TABLE IF EXISTS rebuild5._profile_radius;
DROP TABLE IF EXISTS rebuild5.profile_base;

DROP TABLE IF EXISTS rebuild5.enriched_records;
DROP TABLE IF EXISTS rebuild5.gps_anomaly_log;

TRUNCATE TABLE rebuild5.trusted_cell_library;
TRUNCATE TABLE rebuild5.trusted_bs_library;
TRUNCATE TABLE rebuild5.trusted_lac_library;
TRUNCATE TABLE rebuild5.collision_id_list;
TRUNCATE TABLE rebuild5.cell_centroid_detail;
TRUNCATE TABLE rebuild5.bs_centroid_detail;

DROP TABLE IF EXISTS rebuild5.cell_daily_centroid;
DROP TABLE IF EXISTS rebuild5.cell_metrics_window;
DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary;
TRUNCATE TABLE rebuild5.cell_sliding_window;

DELETE FROM rebuild5_meta.step2_run_stats;
DELETE FROM rebuild5_meta.step3_run_stats;
DELETE FROM rebuild5_meta.step4_run_stats;
DELETE FROM rebuild5_meta.step5_run_stats;
```

## 2. 首轮运行

Step 2 + Step 3:

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
result = run_profile_pipeline()
print(result)
"
```

Step 4:

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
result = run_enrichment_pipeline()
print(result)
"
```

Step 5:

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
result = run_maintenance_pipeline()
print(result)
"
```

## 3. 第二轮运行

重复执行：

1. `run_profile_pipeline()`
2. `run_enrichment_pipeline()`
3. `run_maintenance_pipeline()`

## 4. 第三轮运行

重复执行：

1. `run_profile_pipeline()`
2. `run_enrichment_pipeline()`
3. `run_maintenance_pipeline()`

## 5. 验证 SQL

```sql
-- Step 3
SELECT run_id, batch_id, snapshot_version, finished_at
FROM rebuild5_meta.step3_run_stats
ORDER BY batch_id;

-- Step 4
SELECT run_id, batch_id, snapshot_version, finished_at
FROM rebuild5_meta.step4_run_stats
ORDER BY batch_id;

-- Step 5
SELECT batch_id, COUNT(*) AS cells
FROM rebuild5.trusted_cell_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS bs
FROM rebuild5.trusted_bs_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS lacs
FROM rebuild5.trusted_lac_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS rows
FROM rebuild5.cell_sliding_window
GROUP BY batch_id
ORDER BY batch_id;
```

## 6. 审查重点

- `batch_id=2` 和 `batch_id=3` 是否都产出了 `trusted_bs_library` 与 `trusted_lac_library`
- 第三轮是否还能稳定完成 `candidate_cell_pool` 更新
- `cell_sliding_window` 是否只保留最近窗口内数据
- 若仍有慢点，优先看：
  - `build_path_a_records`
  - `run_enrichment_pipeline`
  - `publish_bs_library`
