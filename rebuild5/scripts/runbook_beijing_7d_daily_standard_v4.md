# Standard Runbook V4: Step 5 优化与多质心研究基线

本文件是基于 V3 跑通后形成的 V4 基线。

适用范围：

1. Step 5 结构优化后的样例验证
2. 在不影响正式库的前提下，做远程隔离库验证
3. 对当前 `batch7` 数据开展多质心 / 迁移 / 双质心研究

当前约束：

- 正式 PG17 数据库运行在 Docker 容器中
- 当前远程实例**未启用 PostGIS**
- 因此：
  - Step 5 优化验证走远程隔离数据库
  - 多质心研究先走 Python 离线研究
  - PostGIS 版正式入库流程等容器补扩展后再切换

---

## 1. V4 的核心变化

相比 V3，V4 先做两件事：

1. **Step 5 内部结构优化**
   - `cell_metrics_base`
   - `cell_radius_stats`
   - `cell_activity_stats`
   - `cell_drift_stats`
   - `cell_metrics_window`
2. **多质心研究从正式入库逻辑中拆出来**
   - 当前先做研究表/报告
   - 不直接重写正式 `trusted_cell_library`

也就是说，V4 不是直接把“多质心算法”硬塞回当前生产主链，而是：

```text
优化 Step 5
  -> 远程隔离库样例验证
  -> 对正式 batch7 做研究
  -> 研究确认后，再决定最终写回策略
```

---

## 2. 当前环境

远程服务器：

- `ssh root@192.168.200.217`

PG17 容器：

- `pg17-test`

主要数据库：

- 正式库：`ip_loc2`
- Step 5 样例验证库：`ip_loc2_step5_smoke`

说明：

- `ip_loc2_step5_smoke` 用于跑 Step 2~5 样例验证
- 正式库 `ip_loc2` 只用于读取当前 `batch7` 研究输入

---

## 3. Phase A：Step 5 优化样例验证

### 3.1 准备 smoke 样例表

在远程容器内把正式库样例表复制到 smoke 库：

```bash
ssh root@192.168.200.217
docker exec pg17-test sh -lc '
  pg_dump -U postgres -d ip_loc2 -Fc -t rebuild5.etl_cleaned_top10_lac_sample -f /tmp/etl_cleaned_top10_lac_sample.dump &&
  pg_restore -U postgres -d ip_loc2_step5_smoke /tmp/etl_cleaned_top10_lac_sample.dump
'
```

### 3.2 reset smoke 库下游状态

```bash
cd /Users/yangcongan/cursor/WangYou_Data
psql "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_step5_smoke" \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

### 3.3 跑 7 天样例

```bash
cd /Users/yangcongan/cursor/WangYou_Data
REBUILD5_PG_DSN="postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_step5_smoke" \
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5.etl_cleaned_top10_lac_sample \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

### 3.4 通过标准

与 V3 一样，但额外检查 Step 5 分阶段耗时日志：

- `step2/3/4/5` 都到 `batch7`
- `batch3` 起真实 `Path A` 出现
- `step4_run_stats` 中 `donor_matched_count`、`gps_filled`、`gps_anomaly_count` 起量
- `step5_run_stats` 中 `published_*`、`multi_centroid_cell_count`、`anomaly_bs_count` 起量
- 日志中能看到：
  - `daily_centroids`
  - `metrics_base`
  - `metrics_radius`
  - `metrics_activity`
  - `drift_metrics`
  - `anomaly_summary`
  - `publish_cell`
  - `collision`
  - `bs_lac`

---

## 4. Phase B：batch7 多质心研究

### 4.1 当前口径

研究输入来自正式库 `ip_loc2`：

- `trusted_cell_library(batch7)`
- `cell_sliding_window`

研究对象：

- `p90_radius_m >= 800`
- 按 `p90_radius_m DESC, window_obs_count DESC, distinct_dev_id DESC`
  取前 100 个 Cell

### 4.2 当前执行方式

由于远程无 PostGIS，本轮先用 Python 研究脚本：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
rebuild5/.venv_research/bin/python rebuild5/scripts/research_multicentroid_batch7.py \
  --dsn "postgresql://postgres:123456@192.168.200.217:5433/ip_loc2"
```

输出：

- `rebuild5/docs/fix2/multicentroid_batch7_top100_results.json`
- `rebuild5/docs/fix2/multicentroid_batch7_top100_report.md`

### 4.3 研究目标

把样本拆成至少以下几类：

- `single_large_coverage`
- `dual_centroid`
- `migration_like`
- `collision_like`
- `dynamic_multi`

并与当前系统标签对比：

- `is_multi_centroid`
- `is_dynamic`
- `drift_pattern`

---

## 5. Phase C：当前数据处理方案

### 5.1 本轮不直接改正式结果

当前阶段只输出：

- 研究报告
- 候选处理方案
- 写回策略建议

不直接修改：

- `trusted_cell_library(batch7)`
- `cell_centroid_detail(batch7)`

### 5.2 确认后再做的动作

等研究确认后，再新增一轮针对 `batch7` 的定向处理：

1. 先落研究结果表
2. 再把确认过的 `dual_centroid / migration_like / collision_like` 写回正式库
3. 最后把这套逻辑并回正式 V4 生产链

---

## 6. 未来正式版（PostGIS）

等远程容器支持 PostGIS 后，再把研究逻辑迁到 PG 内：

### 6.1 技术路线

1. 在 PG17 容器中安装/启用 PostGIS
2. 使用 `ST_ClusterDBSCAN`
3. 结果写入 `cell_centroid_detail`
4. `publish_cell` 读取聚类结果决定：
   - `is_multi_centroid`
   - `is_dynamic`
   - `drift_pattern` 的最终收口

### 6.2 成本控制

正式链不能全量跑所有 Cell，只跑候选集：

- `p90_radius_m >= 800`
- 或 `gps_anomaly_type IS NOT NULL`
- 或 `is_dynamic`
- 或 `is_collision`

后续增量化：

- 只重算新候选和最近变化的 Cell

---

## 7. 当前结论

V4 当前的执行语义是：

```text
Step 5 结构优化先落地
  -> 在远程 smoke 库上跑样例验证
  -> 对正式 batch7 做 100 个 Cell 的多质心研究
  -> 你确认报告后
  -> 再做 batch7 的定向写回
  -> 最后再升级为正式 PostGIS 版生产流程
```

也就是说，V4 现在是“优化 + 研究 + 可控写回”的基线，不是“马上覆盖线上正式数据”的基线。

