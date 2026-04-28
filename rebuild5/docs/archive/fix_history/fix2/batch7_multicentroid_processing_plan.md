# Batch7 多质心研究结果的当前数据处理方案

## 1. 当前约束

本轮只做研究与方案，不直接修改正式 `batch7` 结果。

原因：

1. 远程 PG17 容器当前没有 PostGIS 扩展
2. 当前 UI 正在同步开发，直接重写正式标签会影响联调
3. 研究显示当前 `is_multi_centroid` 对大半径 Cell 明显偏宽，需要先确认标签边界

---

## 2. 研究结论摘要

研究样本：

- 来源：`trusted_cell_library(batch7)`
- 条件：`p90_radius_m >= 800`
- 排序：`p90_radius_m DESC, window_obs_count DESC, distinct_dev_id DESC`
- 前 100 个 Cell

研究结果：

- `single_large_coverage`: 94
- `dual_centroid`: 4
- `migration_like`: 1
- `collision_like`: 1
- `dynamic_multi`: 0（在主参数集 `eps=250m` 下）

当前系统标签：

- `is_multi_centroid=true`: 100 / 100
- `is_dynamic=true`: 63 / 100

结论：

- 当前 `is_multi_centroid` 明显过宽
- 当前 `is_dynamic` 也偏保守地吸收了大量“大面积但单中心”的对象
- 直接把研究结果覆盖到正式库前，必须先确认标签边界和写回策略

---

## 3. 建议的中间产物

先不要改 `rebuild5.trusted_cell_library`，而是新增一层“研究结果表”：

### 3.1 候选表

`rebuild5_research.batch7_multicentroid_candidates`

字段建议：

- `batch_id`
- `operator_code / lac / bs_id / cell_id / tech_norm`
- `p90_radius_m`
- `window_obs_count`
- `active_days`
- `distinct_dev_id`
- `drift_pattern`
- `gps_anomaly_type`
- `is_multi_centroid_current`
- `is_dynamic_current`
- `candidate_rank`

### 3.2 研究结果表

`rebuild5_research.batch7_multicentroid_results`

字段建议：

- `batch_id`
- `operator_code / lac / bs_id / cell_id / tech_norm`
- `research_class`
- `cluster_count_stable`
- `pair_max_distance_m`
- `primary_cluster_share`
- `secondary_cluster_share`
- `primary_cluster_days`
- `secondary_cluster_days`
- `current_drift_pattern`
- `current_is_multi_centroid`
- `current_is_dynamic`
- `review_status`
- `review_note`

### 3.3 研究细表

`rebuild5_research.batch7_multicentroid_cluster_detail`

字段建议：

- `batch_id`
- `operator_code / lac / bs_id / cell_id / tech_norm`
- `cluster_id`
- `center_lon / center_lat`
- `obs_count`
- `dev_count`
- `active_days`
- `share_ratio`
- `radius_m`
- `is_primary`

---

## 4. 正式写回策略

等你确认研究结果后，再对正式 `batch7` 做一轮“最后处理”：

### 4.1 保守写回

只处理研究里最稳定的几类：

- `collision_like`
- `migration_like`
- `dual_centroid`

不直接写回：

- 边界不稳定的 `dynamic_multi`
- 只有单中心但大半径的 `single_large_coverage`

### 4.2 写回规则建议

#### `collision_like`

- `is_multi_centroid = true`
- `is_dynamic = true`
- `drift_pattern = 'collision'`
- 同时把两个稳定簇写入 `cell_centroid_detail`

#### `migration_like`

- `is_multi_centroid = true`
- `is_dynamic = true`
- `drift_pattern = 'migration'`
- 保留主簇为当前对外服务质心

#### `dual_centroid`

- `is_multi_centroid = true`
- `is_dynamic = false`
- `drift_pattern` 保留原值或收口为 `large_coverage`
- 把两个稳定簇写入 `cell_centroid_detail`

#### `single_large_coverage`

- `is_multi_centroid = false`
- `is_dynamic` 不自动提升
- 维持单中心，只在报告里标注“面积大但未见稳定双簇”

---

## 5. 未来正式上线的低成本方案

### 5.1 候选集收缩

每轮都只分析：

- `p90_radius_m >= 800`
- 或 `gps_anomaly_type IS NOT NULL`
- 或 `is_dynamic`
- 或 `is_collision`

### 5.2 增量化

未来每轮不要全量重做，只重算：

- 本轮新进候选集的 Cell
- `p90_radius_m` 变化显著的 Cell
- `gps_anomaly_type` 发生变化的 Cell
- 当前 `cell_centroid_detail` 已存在但最近 2 批窗口显著变化的 Cell

### 5.3 技术实现

正式版优先顺序：

1. 远程 PG17 容器补装 PostGIS
2. 用 `ST_ClusterDBSCAN` 或等价方案在 PG 内生成簇
3. 把研究表并入 `cell_centroid_detail`
4. 再把标签判定接回 `publish_cell`

---

## 6. 当前建议

当前阶段最稳妥的动作是：

1. 保留当前正式 `batch7` 不改
2. 先使用研究结果表和报告进行人工确认
3. 你确认标签边界后，再做一次只针对 `batch7` 的定向写回
4. 最后把这套方案收口到生产版 V4 runbook

