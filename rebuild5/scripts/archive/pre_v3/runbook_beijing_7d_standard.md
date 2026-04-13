# 验证性重放 Runbook: `rebuild5` 北京 7 天批次重跑

本 runbook 是当前 `rebuild5` 的**验证性重放**运行手册，用于：

- 北京 7 天数据集的 clean rerun
- batch 级顺序重放
- 固定数据集上的多轮链路验证

它不是产品“按天增量处理”的标准 runbook。

生产语义请使用：

- `rebuild5/scripts/runbook_beijing_7d_daily_standard.md`

本 runbook **取代** 以下历史文档作为执行标准：

- `rebuild5/scripts/runbook_beijing_7d.md`
- `rebuild5/scripts/runbook_step2_to_step5_clean_rerun.md`

## 0. 设计与实现结论

本轮复核结论：

- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/04_知识补数.md`
- `rebuild5/docs/05_画像维护.md`

以上 03/04/05 设计文档当前仍然成立，**没有发现需要修订设计逻辑的证据**。

已确认的问题都属于以下两类：

- `实现偏离设计`
  - Step 2 donor 没有完整透传到 `path_a_records`
  - Step 2/3 没有严格按上一版读取 `collision_id_list`
  - Step 3 `step3_run_stats` 用 current-only 统计，漏掉最终 snapshot 的 carry-forward
  - Step 5 同 batch rerun 时错误读取了当前 batch 作为 `snapshot_version_prev`
- `执行层问题`
  - `publish_bs_library` 取错 `Nested Loop` 计划，导致分钟级卡顿
  - `trusted_*_library` autovacuum 干扰 rerun
  - Step 4 / Step 5 运行时，大中间表没有及时回收，导致 PG 数据卷空间压力

当前标准基线已包含这些修复，不需要再修改 03/04/05 需求文档。

## 1. 基本原则

- `Step 1` 只在其自身证据失效时才重跑；当前北京 7 天场景默认复用现有 `raw_gps` / `etl_cleaned`
- batch 必须顺序推进，不能跳批
- `batch2`、`batch3` 是稳定性门槛；只要任一轮异常，必须停下来定位
- `path_a_records` 行数应以 `rebuild5_meta.step2_run_stats.path_a_record_count` 为准
- `Step 4` 完成后，应立即释放 Step 2 大表
- `Step 5` 完成后，应立即释放 Step 4/5 临时大表
- `cell_sliding_window` 是跨批次持久窗口，**只能在 clean rerun 时清空**，不能在批间清空

## 2. 执行前检查

### 2.1 数据基线

```sql
SELECT
    (SELECT COUNT(*) FROM rebuild5.raw_gps) AS raw_gps,
    (SELECT COUNT(*) FROM rebuild5.etl_cleaned) AS etl_cleaned;
```

北京 7 天当前基线应为：

- `raw_gps = 25442069`
- `etl_cleaned = 45314465`

### 2.2 运行会话

执行前确认没有残留活跃任务：

```sql
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS age, LEFT(query, 120) AS query_head
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state <> 'idle'
ORDER BY query_start;
```

### 2.3 关键表策略

当前代码基线已固化以下策略：

- `trusted_cell_library / trusted_bs_library / trusted_lac_library` 关闭 autovacuum
- Step 5 在发布 BS 前显式 `ANALYZE trusted_cell_library`
- `publish_bs_library` 在 session 级禁用 `enable_nestloop`
- `cell_sliding_window` 保持 logged + 默认 autovacuum 语义

## 3. Clean Rerun（保留 Step 1）

适用于从 `Step 2 → Step 5` 全部重建。

```sql
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

## 4. 标准批次循环

### 4.1 Step 2 + Step 3

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
result = run_profile_pipeline()
print(result)
"
```

验证：

```sql
SELECT
    run_id,
    batch_id,
    snapshot_version,
    trusted_snapshot_version_prev,
    profile_base_cell_count,
    evaluated_cell_count,
    waiting_cell_count,
    observing_cell_count,
    qualified_cell_count,
    excellent_cell_count,
    bs_qualified_count,
    lac_qualified_count,
    finished_at
FROM rebuild5_meta.step3_run_stats
ORDER BY batch_id;

SELECT
    batch_id,
    path_a_record_count,
    path_b_record_count,
    path_b_cell_count,
    path_c_drop_count
FROM rebuild5_meta.step2_run_stats
ORDER BY batch_id;
```

### 4.2 Step 4

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.enrichment.pipeline import run_enrichment_pipeline
result = run_enrichment_pipeline()
print(result)
"
```

验证：

```sql
SELECT
    run_id,
    batch_id,
    snapshot_version,
    snapshot_version_prev,
    total_path_a,
    donor_matched_count,
    gps_filled,
    gps_anomaly_count,
    finished_at
FROM rebuild5_meta.step4_run_stats
ORDER BY batch_id;
```

### 4.3 Step 4 后空间回收（强制）

`Step 5` 不再需要以下 Step 2 大表。保留 live 表只会额外占用几十 GB 空间。

必须在确认 `step2_run_stats` / `step4_run_stats` 已落库后执行：

```sql
DROP TABLE IF EXISTS rebuild5.path_a_records;
DROP TABLE IF EXISTS rebuild5.profile_obs;
DROP TABLE IF EXISTS rebuild5.profile_base;
```

说明：

- `path_a_records` 行数后续一律从 `rebuild5_meta.step2_run_stats.path_a_record_count` 读取
- `candidate_cell_pool`、`trusted_snapshot_*` 不能在此阶段删除

### 4.4 Step 5

```bash
cd /Users/yangcongan/cursor/WangYou_Data && python3 -c "
from rebuild5.backend.app.maintenance.pipeline import run_maintenance_pipeline
result = run_maintenance_pipeline()
print(result)
"
```

验证：

```sql
SELECT
    run_id,
    batch_id,
    snapshot_version,
    snapshot_version_prev,
    published_cell_count,
    published_bs_count,
    published_lac_count,
    collision_cell_count,
    multi_centroid_cell_count,
    dynamic_cell_count,
    anomaly_bs_count,
    finished_at
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS cnt
FROM rebuild5.trusted_cell_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS cnt
FROM rebuild5.trusted_bs_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS cnt
FROM rebuild5.trusted_lac_library
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS cnt
FROM rebuild5.cell_sliding_window
GROUP BY batch_id
ORDER BY batch_id;
```

### 4.5 Step 5 后空间回收（当前调试口径）

`Step 5` 完成后，仅清理本批运行期中间表；`Step 4` 明细结果保留用于观察：

```sql
DROP TABLE IF EXISTS rebuild5.cell_daily_centroid;
DROP TABLE IF EXISTS rebuild5.cell_metrics_window;
DROP TABLE IF EXISTS rebuild5.cell_anomaly_summary;
```

说明：

- `cell_sliding_window` 不能删除
- `enriched_records` / `gps_anomaly_log` 当前按 `batch_id` 持久保留
- `trusted_*_library`、`collision_id_list` 不能删除

## 5. 批次门槛

### batch1

目标：

- 建立首版 `trusted_*_library`
- `step5.snapshot_version_prev = v0`

### batch2

目标：

- `step3` 最终 snapshot 统计必须与 batch1 可比，不能再出现 current-only 误报
- `step4.total_path_a > 0`
- `step4.donor_matched_count = step4.total_path_a`
- `step5.published_bs_count > 0`
- `step5.published_lac_count > 0`

### batch3

目标：

- 再次验证连续两轮链路稳定
- 若 batch2、batch3 都正常，再推进剩余批次

## 6. 异常处理规则

### 6.1 设计问题

只有当 03/04/05 文档自身互相冲突时，才改设计文档。

当前已确认：

- `snapshot` 是冻结视图
- `library` 是正式发布库
- `Step 3` 负责冻结视图
- `Step 5` 负责维护并发布正式库
- `BS` 必须从维护后的 Cell 上卷
- `LAC` 必须从维护后的 BS 上卷

### 6.2 实现/执行问题

优先按实现偏离或执行层问题处理：

- `Step 2 Path A` 异常偏慢：优先检查 `trusted_cell_library` / `collision_id_list` 统计与索引
- `Step 4` 卡在 `extend`：先确认 `enriched_records` 空间，再检查并行度
- `Step 5 publish_bs_library` 异常偏慢：先确认 `enable_nestloop=off` 修复仍在
- `Step 5` 报空间不足：优先确认 `path_a_records / profile_obs / profile_base` 已在 Step 4 后释放

### 6.3 rerun 当前 batch 的 Step 5

只允许删除当前 batch 的 Step 5 发布结果，再重跑当前 batch Step 5：

```sql
DELETE FROM rebuild5.cell_sliding_window WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.trusted_cell_library WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.trusted_bs_library WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.trusted_lac_library WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.collision_id_list WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.cell_centroid_detail WHERE batch_id = <batch_id>;
DELETE FROM rebuild5.bs_centroid_detail WHERE batch_id = <batch_id>;
DELETE FROM rebuild5_meta.step5_run_stats WHERE batch_id = <batch_id>;
```

不能动 `< 当前 batch` 的已发布库。

## 7. 推荐顺序

北京 7 天标准执行顺序：

1. clean rerun（保留 Step 1）
2. 跑 batch1
3. 跑 batch2
4. 若 batch2 正常，跑 batch3
5. 若 batch3 正常，继续剩余批次
6. 全部完成后再做汇总归档

## 8. 历史文档处理

以下文档保留为历史参考，不再作为执行标准：

- `rebuild5/scripts/runbook_beijing_7d.md`
- `rebuild5/scripts/runbook_step2_to_step5_clean_rerun.md`

它们只能用于查看历史背景，不能再直接照单执行。
