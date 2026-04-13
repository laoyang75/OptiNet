# Step 5 优化与样例验证报告

## 1. 背景

本轮优化目标不是改变 Step 5 业务口径，而是：

1. 把 Step 5 中最难定位的中间计算拆成可独立检查的阶段表
2. 让慢点从“隐式 UPDATE 链”显式暴露成少数几个阶段
3. 在不影响当前正式库的前提下，先在远程隔离库完成样例验证

验证环境：

- 远程服务器：`192.168.200.217`
- PG17 容器：`pg17-test`
- 隔离验证库：`ip_loc2_step5_smoke`
- 样例输入：`rebuild5.etl_cleaned_top10_lac_sample`

本轮**没有重启**远程数据库或 Docker 容器。

---

## 2. 代码改动

### 2.1 metrics / drift stage 化

涉及文件：

- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/cell_maintain.py`
- `rebuild5/backend/app/maintenance/pipeline.py`

新增或显式物化的中间表：

- `rebuild5.cell_metrics_base`
- `rebuild5.cell_radius_stats`
- `rebuild5.cell_activity_stats`
- `rebuild5.cell_drift_stats`
- `rebuild5.cell_metrics_window`

改动原则：

- 保留现有 SQL 口径
- 把“先算 base / radius / activity / drift，再 join 收口”的结构显式化
- 每张中间表都可以单独 `SELECT COUNT(*)`、`AVG(...)` 核对

### 2.2 Step 5 调度与索引补强

`maintenance/pipeline.py` 中的 Step 5 调度顺序改为：

1. `refresh_sliding_window`
2. `build_daily_centroids`
3. `build_cell_metrics_base`
4. `build_cell_radius_stats`
5. `build_cell_activity_stats`
6. `build_cell_drift_stats`
7. `build_cell_metrics_window`
8. `compute_gps_anomaly_summary`
9. `publish_cell_library`
10. `detect_collisions`
11. `publish_cell_centroid_detail`
12. `publish_bs_library`
13. `publish_bs_centroid_detail`
14. `publish_lac_library`

补充的热点索引：

- `idx_csw_lookup`
- `idx_cdc_cell_date`
- `idx_cdc_lookup`
- `idx_cmw_cell`
- `idx_cmw_lookup`
- `idx_cas_cell`
- `idx_cas_lookup`

同时增加了分阶段耗时日志，便于直接看到热点落在哪一段。

### 2.3 多质心细表候选收紧

涉及文件：

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`

本轮没有引入最终 PostGIS 聚类，只做了低风险收紧：

1. `publish_cell_centroid_detail()` 不再只靠 `is_multi_centroid` 进候选
2. 候选改为：
   - `p90_radius_m >= trigger`
   - 或 `gps_anomaly_type IS NOT NULL`
   - 或 `is_collision`
   - 或 `is_dynamic`
3. 在 `cell_daily_centroid` join 中补上 `bs_id`
4. 先物化 `candidate_days`
5. 会话级关闭 `nestloop`

这一步的目标是让候选更贴近真正的大半径/异常 Cell，并减少不必要的日质心扫描。

---

## 3. 自动化护栏

通过的针对性测试：

- `test_build_cell_metrics_window_joins_materialized_stage_tables`
- `test_build_cell_drift_stats_materializes_single_ctas`
- `test_publish_cell_centroid_detail_uses_daily_centroid_split`
- `test_refresh_sliding_window_uses_dedicated_worker_count`
- `test_run_maintenance_pipeline_keeps_step5_run_stats_history`

样例验证入口：

- `REBUILD5_PG_DSN=.../ip_loc2_step5_smoke python3 rebuild5/scripts/run_daily_increment_batch_loop.py ...`

---

## 4. 样例验证结果

样例链已在远程隔离库 `ip_loc2_step5_smoke` 完整跑到 `batch7`。

### 4.1 Step 2

| batch | input | Path A | Path B | Path C |
|------|------:|------:|------:|------:|
| 1 | 293,206 | 0 | 292,872 | 334 |
| 2 | 293,800 | 0 | 293,593 | 207 |
| 3 | 271,604 | 205,201 | 66,176 | 227 |
| 4 | 265,725 | 211,822 | 53,692 | 211 |
| 5 | 264,187 | 213,654 | 50,330 | 203 |
| 6 | 272,704 | 222,869 | 49,685 | 150 |
| 7 | 276,169 | 229,384 | 46,661 | 124 |

### 4.2 Step 4

| batch | total_path_a | donor_matched | gps_filled | gps_anomaly |
|------|-------------:|--------------:|-----------:|------------:|
| 1 | 0 | 0 | 0 | 0 |
| 2 | 0 | 0 | 0 | 0 |
| 3 | 205,201 | 201,833 | 11,625 | 3,162 |
| 4 | 211,822 | 207,015 | 12,122 | 3,429 |
| 5 | 213,654 | 207,823 | 12,437 | 3,478 |
| 6 | 222,869 | 215,829 | 11,618 | 2,983 |
| 7 | 229,384 | 221,649 | 11,886 | 3,039 |

### 4.3 Step 5

| batch | published_cell | published_bs | published_lac | multi_centroid | dynamic | anomaly_bs |
|------|---------------:|-------------:|--------------:|---------------:|--------:|-----------:|
| 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | 6,462 | 3,526 | 21 | 536 | 0 | 0 |
| 3 | 7,767 | 4,050 | 21 | 730 | 0 | 3 |
| 4 | 8,470 | 4,326 | 21 | 851 | 60 | 4 |
| 5 | 8,956 | 4,479 | 21 | 917 | 136 | 12 |
| 6 | 9,389 | 4,607 | 22 | 948 | 218 | 39 |
| 7 | 9,699 | 4,717 | 22 | 1,010 | 298 | 57 |

结论：

- `batch3` 起真实 `Path A` 出现，符合样例验证标准
- `Step 4` 起量正常，`donor_matched / gps_filled / gps_anomaly_count` 均非 0
- `Step 5` 发布量连续增长，`multi_centroid / dynamic / anomaly_bs` 均起量
- 优化后样例结果口径与之前验证值一致，没有出现回归

---

## 5. 耗时观察

本轮优化后，Step 5 已能直接看到各阶段耗时。

代表批次：

### batch3

- `daily_centroids = 4s`
- `metrics_base = 1s`
- `metrics_radius = 2s`
- `metrics_activity = 1s`
- `drift_metrics = 1s`
- `anomaly_summary = 2s`
- `publish_cell = 1s`
- `collision = 2s`
- `bs_lac = 0s`

### batch6

- `daily_centroids = 9s`
- `metrics_base = 3s`
- `metrics_radius = 5s`
- `metrics_activity = 2s`
- `drift_metrics = 2s`
- `anomaly_summary = 2s`
- `publish_cell = 1s`
- `collision = 28s`
- `bs_lac = 0s`

### batch7

- `daily_centroids = 10s`
- `metrics_base = 3s`
- `metrics_radius = 6s`
- `metrics_activity = 2s`
- `drift_metrics = 2s`
- `anomaly_summary = 2s`
- `publish_cell = 1s`
- `collision = 2s`
- `bs_lac = 0s`

### 观察

1. 原先“难拆的 metrics UPDATE 链”已经被拆开，可以明确看到：
   - `daily_centroids`
   - `metrics_radius`
   - `collision`
   是当前更值得继续优化的阶段
2. 在样例规模下，`publish_cell_centroid_detail / publish_bs_lac` 已不再是主瓶颈
3. `collision` 在个别批次会出现明显抖动（如 batch4 / batch6），说明下一轮优化重点应该转向碰撞链，而不是继续纠结 metrics 主体

---

## 6. 结论

本轮 Step 5 优化已经完成了第一阶段目标：

1. **结构上**：把 metrics / drift 的中间结果显式物化
2. **验证上**：在远程隔离库 `ip_loc2_step5_smoke` 跑通了完整 7 天样例
3. **结果上**：样例业务口径未回归
4. **调试性上**：热点已经能清楚定位到具体阶段

下一轮继续优化时，优先级建议是：

1. `detect_collisions()`  
2. `daily_centroids` / `metrics_radius`
3. 再决定是否继续拆 `publish_cell`

