# Fix4 Claude Runbook

## 1. 共享样例数据

使用以下三张共享表（已建好，不需导入）：

| 表名 | 行数 | 用途 |
|------|------|------|
| `rebuild5_fix4.raw_gps_shared_sample` | 1,232,037 | 原始 GPS（本轮未使用） |
| `rebuild5_fix4.etl_cleaned_shared_sample` | 1,937,395 | ETL 清洗后数据（主输入） |
| `rebuild5_fix4.focus_cells_shared` | 40 | 重点分析 Cell |

固定时间范围：`2025-12-01 ~ 2025-12-07`（7 批）

### 派生工作集

在共享原始表之上构建了以下派生表（`rebuild5_fix4` schema）：

| 派生表 | 说明 | 生命周期 |
|--------|------|---------|
| `c_window` | 累积滑动窗口 | 跨批持久 |
| `c_seed_grid` | 200m 网格聚合 | 每批重建 |
| `c_primary_seed` | 每 Cell 最密网格点 | 每批重建 |
| `c_seed_dist` | GPS 点到 seed 的距离 | 每批重建 |
| `c_cutoff` | 自适应裁剪半径 | 每批重建 |
| `c_core_pts` | 过滤后的核心点 | 每批重建 |
| `c_core_stats` | 核心点质心统计 | 每批重建 |
| `c_radius` | core p50/p90 | 每批重建 |
| `c_raw_radius` | raw p90（对比用） | 每批重建 |
| `c_cell_lib` | Cell library（所有批次） | 跨批持久 |

## 2. 执行 7 批 ETL / 日增量

### 手动逐批执行

每批包含 10 个步骤，必须按顺序执行：

```bash
DB="postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"
S="rebuild5_fix4"
B=1  # batch number
D1="2025-12-01"  # start date
D2="2025-12-02"  # end date (exclusive)

# 1. Load
psql "$DB" -c "INSERT INTO $S.c_window SELECT ${B}::int, ... FROM $S.etl_cleaned_shared_sample WHERE report_ts >= '$D1' AND report_ts < '$D2';"

# 2. Reindex window
psql "$DB" -c "DROP INDEX IF EXISTS $S.idx_cw_key; CREATE INDEX idx_cw_key ON $S.c_window (...); ANALYZE $S.c_window;"

# 3-9. Core filter pipeline (each step: CREATE TABLE → INDEX → ANALYZE)
# See fix4_claude_batch4to7.sh for complete SQL

# 10. Assemble cell library
psql "$DB" -c "INSERT INTO $S.c_cell_lib SELECT ..."

# 11. Cleanup intermediates
psql "$DB" -c "DROP TABLE IF EXISTS $S.c_seed_grid, $S.c_primary_seed, ..."
```

### 自动化脚本

```bash
bash rebuild5/scripts/fix4_claude_batch4to7.sh
```

## 3. 每批验证内容

### Batch 1 验证

```sql
-- Lifecycle 分布
SELECT lifecycle_state, count(*) FROM rebuild5_fix4.c_cell_lib WHERE batch_id=1 GROUP BY 1;
-- 期望: observing > qualified > excellent, 无 waiting

-- Focus cells 对比
SELECT f.source_bucket, round(c.raw_p90_radius_m::numeric) as raw, round(c.p90_radius_m::numeric) as core
FROM c_cell_lib c JOIN focus_cells_shared f USING (...) WHERE batch_id=1;
-- 期望: high_p90 组 raw >> core, moving/multi_cluster 组差异较小
```

### Batch 2 验证

```sql
-- Lifecycle 晋升
SELECT batch_id, lifecycle_state, count(*) FROM c_cell_lib WHERE batch_id IN (1,2) GROUP BY 1,2;
-- 期望: excellent 数量显著增长

-- Path A 模拟
-- batch 1 qualified+ cells 在 batch 2 是否有新数据
-- 期望: >95% 有新数据（可走 Path A）

-- Anchor eligible
SELECT count(*) FILTER (WHERE gps_valid_count>=10 AND distinct_dev_id>=2 AND p90_radius_m<1500 AND active_days>=2)
FROM c_cell_lib WHERE batch_id=2;
-- 期望: >0（batch 1 为 0 因 active_days<2）
```

### Batch 3 验证

确认模式稳定：excellent 持续增长，qualified 趋稳，observing 递减。

## 4. 中断恢复

### 如果某批中途失败

1. 检查哪些中间表已创建：
   ```sql
   SELECT tablename FROM pg_tables WHERE schemaname='rebuild5_fix4' AND tablename LIKE 'c_%';
   ```

2. 删除该批的中间表和 cell_lib 行：
   ```sql
   DROP TABLE IF EXISTS c_seed_grid, c_primary_seed, c_seed_dist, c_cutoff, c_core_pts, c_core_stats, c_radius, c_raw_radius;
   DELETE FROM c_cell_lib WHERE batch_id = <failed_batch>;
   ```

3. 删除该批加载到 window 的数据（如果需要重新加载）：
   ```sql
   DELETE FROM c_window WHERE batch_id = <failed_batch>;
   ```

4. 从该批重新开始。

### 如果有阻塞查询

```sql
-- 查看活跃查询
SELECT pid, state, query, now()-query_start AS duration 
FROM pg_stat_activity WHERE datname='ip_loc2' AND state='active';

-- 终止阻塞查询
SELECT pg_terminate_backend(<pid>);
```
