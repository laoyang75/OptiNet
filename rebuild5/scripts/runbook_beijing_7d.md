# Runbook: 北京 7 天全量数据处理

## 概述

将北京 7 天 GPS + LAC 两个 legacy 原始表合并去重后，跑完 rebuild5 全流程（Step 0-5），生成完整的 Cell/BS/LAC 可信库画像。

- 合并后：25,442,069 行（rebuild5.raw_gps）
- dataset_key：`beijing_7d`
- 配置文件：`rebuild5/config/dataset.yaml`

### 数据流总览

```
legacy GPS/LAC 原始表
    → Step 0: 合并去重 → raw_gps（单源）
    → Step 1: 解析(ci+ss1) → etl_parsed → 清洗 → 补齐(三池模型) → etl_cleaned
    → Step 2: 路由分流 → path_a_records(携带donor) / path_b / path_c
             + 基础画像 → profile_base（Cell主键: operator_code, lac, cell_id）
    → Step 3: 评估 → snapshot(本轮结果) + candidate_cell_pool(waiting/observing连续池)
    → Step 4: 简单补数 → enriched_records + gps_anomaly_log（直读path_a的donor，不re-JOIN）
    → Step 5: 连续窗口维护 → trusted_cell/bs/lac_library + collision_id_list

首轮：没有可信库，Path A=0，Step 4 补数为 0
二轮：Step 5 产出的可信库作为 Step 2/4 的输入，Path A 开始命中
```

### 关键设计约束

- **Cell 主键**：`(operator_code, lac, cell_id)`，bs_id 只做维度字段
- **Step 4 不拥有版本选择权**：donor 由 Step 2 确认并写入 path_a_records
- **连续窗口**：cell_sliding_window 跨批持久，按数据时间轴裁剪（非 NOW()）
- **候选池**：candidate_cell_pool 持久保存 waiting/observing，跨轮次连续评估
- **A 类碰撞键**：`(operator_code, tech_norm, lac, cell_id)`

## 环境要求

- PostgreSQL 17（192.168.200.217:5433，Docker `--shm-size=8g`）
- PG 配置：shared_buffers=64GB, max_parallel_workers_per_gather=16, work_mem=512MB
- 磁盘空间：/data 至少 200GB 可用
- Python 3.12+

### 环境检查 [SQL/MCP]

```sql
-- 并行配置
SELECT name, setting FROM pg_settings
WHERE name IN ('shared_buffers', 'max_parallel_workers_per_gather', 'work_mem', 'jit');
-- 期望：shared_buffers=64GB, max_parallel_workers_per_gather=16, work_mem=512MB, jit=off

-- Docker shm
-- 在服务器执行：docker inspect pg17-test --format '{{.HostConfig.ShmSize}}'
-- 期望：>= 8589934592 (8GB)
```

### 监控 [SQL/MCP]

```sql
SELECT pid, state, LEFT(query, 80) AS query_head, now() - query_start AS duration,
       CASE WHEN leader_pid IS NOT NULL THEN 'worker' ELSE 'leader' END AS role
FROM pg_stat_activity
WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%' AND query NOT LIKE 'autovacuum%'
ORDER BY COALESCE(leader_pid, pid), pid;
```

**性能基线**：任何单步超过 10 分钟需要排查。

## 执行步骤

### Pre-Step: 清理旧表 [SQL/MCP]

```sql
-- 清理所有 Step 1-5 产物（保留 raw_gps）
DROP TABLE IF EXISTS rebuild5.etl_parsed CASCADE;
DROP TABLE IF EXISTS rebuild5.etl_clean_stage CASCADE;
DROP TABLE IF EXISTS rebuild5.etl_cleaned CASCADE;
DROP TABLE IF EXISTS rebuild5.etl_ci CASCADE;
DROP TABLE IF EXISTS rebuild5.etl_ss1 CASCADE;
DROP VIEW IF EXISTS rebuild5.etl_filled CASCADE;

DROP TABLE IF EXISTS rebuild5.path_a_records CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_path_a_candidates CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_path_b_cells CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_path_b_records CASCADE;
DROP TABLE IF EXISTS rebuild5.profile_obs CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_centroid CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_devs CASCADE;
DROP TABLE IF EXISTS rebuild5._profile_radius CASCADE;
DROP TABLE IF EXISTS rebuild5.profile_base CASCADE;

DROP TABLE IF EXISTS rebuild5.trusted_snapshot_cell CASCADE;
DROP TABLE IF EXISTS rebuild5.trusted_snapshot_bs CASCADE;
DROP TABLE IF EXISTS rebuild5.trusted_snapshot_lac CASCADE;
DROP TABLE IF EXISTS rebuild5.snapshot_diff_cell CASCADE;
DROP TABLE IF EXISTS rebuild5.snapshot_diff_bs CASCADE;
DROP TABLE IF EXISTS rebuild5.snapshot_diff_lac CASCADE;
DROP TABLE IF EXISTS rebuild5._snapshot_current_cell CASCADE;
DROP TABLE IF EXISTS rebuild5._snapshot_current_bs CASCADE;
DROP TABLE IF EXISTS rebuild5._snapshot_current_lac CASCADE;
DROP TABLE IF EXISTS rebuild5.candidate_cell_pool CASCADE;

DROP TABLE IF EXISTS rebuild5.enriched_records CASCADE;
DROP TABLE IF EXISTS rebuild5.gps_anomaly_log CASCADE;
DROP TABLE IF EXISTS rebuild5.step4_fill_coverage CASCADE;

DROP TABLE IF EXISTS rebuild5.trusted_cell_library CASCADE;
DROP TABLE IF EXISTS rebuild5.trusted_bs_library CASCADE;
DROP TABLE IF EXISTS rebuild5.trusted_lac_library CASCADE;
DROP TABLE IF EXISTS rebuild5.collision_id_list CASCADE;
DROP TABLE IF EXISTS rebuild5.cell_centroid_detail CASCADE;
DROP TABLE IF EXISTS rebuild5.bs_centroid_detail CASCADE;
DROP TABLE IF EXISTS rebuild5.cell_sliding_window CASCADE;
DROP TABLE IF EXISTS rebuild5.cell_daily_centroid CASCADE;
DROP TABLE IF EXISTS rebuild5.cell_metrics_window CASCADE;
DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary CASCADE;

DELETE FROM rebuild5_meta.step1_run_stats;
DELETE FROM rebuild5_meta.step2_run_stats;
DELETE FROM rebuild5_meta.step3_run_stats;
DELETE FROM rebuild5_meta.step5_run_stats;
DELETE FROM rebuild5_meta.run_log;
```

---

### Step 1: ETL [BASH]

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
result = run_step1_pipeline()
print('Step 1 完成:', result)
"
```

验证 [SQL/MCP]：
```sql
SELECT
    (SELECT COUNT(*) FROM rebuild5.etl_cleaned) AS cleaned;
-- 应 > 40,000,000

-- 补齐效果（三池模型）
SELECT
    COUNT(*) FILTER (WHERE gps_fill_source = 'raw_gps') AS gps_raw,
    COUNT(*) FILTER (WHERE gps_fill_source = 'ss1_own') AS gps_ss1,
    COUNT(*) FILTER (WHERE gps_fill_source = 'same_cell') AS gps_filled,
    COUNT(*) FILTER (WHERE gps_fill_source = 'none') AS gps_none,
    COUNT(*) FILTER (WHERE operator_fill_source = 'same_cell') AS op_filled,
    COUNT(*) FILTER (WHERE lac_fill_source = 'same_cell') AS lac_filled
FROM rebuild5.etl_cleaned;
```

索引 [SQL/MCP]：
```sql
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_cell ON rebuild5.etl_cleaned (cell_id);
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_op_lac_cell ON rebuild5.etl_cleaned (operator_filled, lac_filled, cell_id);
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_bs ON rebuild5.etl_cleaned (bs_id);
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_record ON rebuild5.etl_cleaned (record_id);
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_path_lookup ON rebuild5.etl_cleaned (operator_filled, lac_filled, bs_id, cell_id, tech_norm);
ANALYZE rebuild5.etl_cleaned;
```

---

### Step 2+3: 路由分流 + 评估 [BASH]

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
result = run_profile_pipeline()
print('Step 2+3 完成:')
for k, v in result.items():
    print(f'  {k}: {v}')
"
```

验证 [SQL/MCP]：
```sql
-- 首轮 Path A 应为 0
SELECT
    (SELECT COUNT(*) FROM rebuild5.path_a_records) AS path_a,
    (SELECT COUNT(*) FROM rebuild5.profile_base) AS profile_base;

-- profile_base 不应有 bs_id 参与主键分裂
SELECT operator_code, lac, cell_id, COUNT(*) AS cnt
FROM rebuild5.profile_base
GROUP BY operator_code, lac, cell_id
HAVING COUNT(*) > 1
LIMIT 5;
-- 应返回 0 行（同一 Cell 不应有多行）

-- path_a_records 应携带 donor 字段
SELECT donor_batch_id, donor_cell_id, donor_center_lon
FROM rebuild5.path_a_records
WHERE donor_cell_id IS NOT NULL
LIMIT 3;

-- 候选池
SELECT lifecycle_state, COUNT(*) FROM rebuild5.candidate_cell_pool GROUP BY lifecycle_state;

-- Cell 快照分布
SELECT lifecycle_state, COUNT(*) AS cnt
FROM rebuild5.trusted_snapshot_cell
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_snapshot_cell)
GROUP BY lifecycle_state ORDER BY cnt DESC;
```

---

### Step 4: 知识补数 [BASH]

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
result = run_enrichment_pipeline()
print('Step 4 完成:')
for k, v in result.items():
    print(f'  {k}: {v}')
"
```

验证 [SQL/MCP]：
```sql
-- 首轮 Path A=0 时补数应全为 0
SELECT total_path_a, donor_matched_count, gps_filled, rsrp_filled
FROM rebuild5_meta.step4_run_stats
ORDER BY run_id DESC LIMIT 1;
```

---

### Step 5: 画像维护 [BASH]

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
import time
start = time.time()
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
result = run_maintenance_pipeline()
elapsed = time.time() - start
print(f'Step 5 完成 (耗时 {elapsed:.0f}s):')
for k, v in result.items():
    print(f'  {k}: {v}')
"
```

验证 [SQL/MCP]：
```sql
-- 发布规模
SELECT
    (SELECT COUNT(*) FROM rebuild5.trusted_cell_library WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)) AS cells,
    (SELECT COUNT(*) FROM rebuild5.trusted_bs_library WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_bs_library)) AS bs,
    (SELECT COUNT(*) FROM rebuild5.trusted_lac_library WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_lac_library)) AS lacs,
    (SELECT COUNT(*) FROM rebuild5.collision_id_list WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.collision_id_list)) AS collisions;

-- 连续窗口检查
SELECT COUNT(*) AS window_rows,
       MIN(event_time_std) AS earliest,
       MAX(event_time_std) AS latest
FROM rebuild5.cell_sliding_window;
```

---

### 二轮运行

首轮产出可信库后，重跑 Step 2-5 让 Path A 命中。

Step 2+3 [BASH]：
```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
result = run_profile_pipeline()
print(f'二轮 Step 2+3: Path A={result[\"path_a_record_count\"]}, Path B cells={result[\"path_b_cell_count\"]}')
"
```

验证 [SQL/MCP]：
```sql
SELECT COUNT(*) AS path_a FROM rebuild5.path_a_records;
-- 二轮应 > 0

-- Step 4 不应 re-JOIN：确认 path_a_records 有 donor 字段
SELECT COUNT(*) FILTER (WHERE donor_batch_id IS NOT NULL) AS has_donor,
       COUNT(*) AS total
FROM rebuild5.path_a_records;
```

Step 4 [BASH]：
```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
result = run_enrichment_pipeline()
print('二轮 Step 4:', {k: v for k, v in result.items() if 'filled' in k or 'matched' in k or 'anomaly' in k})
"
```

Step 5 [BASH]：
```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
result = run_maintenance_pipeline()
print('二轮 Step 5:', result)
"
```

二轮完成后验证：
```sql
-- 连续窗口应包含两轮数据
SELECT batch_id, COUNT(*) AS rows FROM rebuild5.cell_sliding_window GROUP BY batch_id;

-- 可信库可被下一轮读取
SELECT batch_id, COUNT(*) AS cells
FROM rebuild5.trusted_cell_library
GROUP BY batch_id ORDER BY batch_id;
```

---

## 重跑前检查清单

- [ ] Docker shm-size >= 8GB
- [ ] PG shared_buffers >= 64GB, max_parallel_workers_per_gather >= 8
- [ ] database.py 的 get_conn() 没有 SET 禁用并行
- [ ] 磁盘空间 > 200GB
- [ ] 任何单步超过 10 分钟需要排查
