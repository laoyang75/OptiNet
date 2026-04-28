# Batch7 多质心研究报告

- 生成时间: `2026-04-12T19:59:18.488349`
- 研究输入数据库: `postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
- 研究批次: `batch_id=7`
- 说明: 当前远程 PG17 实例未提供 PostGIS 扩展，本轮研究使用 Python + numpy 对 100 个候选 Cell 做离线聚类验证；后续正式入库实现再迁移到 PostGIS。

## 样本选择

- 候选范围: `trusted_cell_library(batch7)` 中 `p90_radius_m >= 800.0`
- 选样规则: 按 `p90_radius_m DESC, window_obs_count DESC, distinct_dev_id DESC` 取前 `100` 个 Cell
- 样本总窗口点数: `5141`
- 样本 `window_obs_count` 范围: `2 ~ 477`，均值 `53.15`

## 算法

- 主算法: 自定义 DBSCAN 风格密度聚类，`eps=250.0m`, `min_samples=4`
- 稳定簇规则: `obs_count >= max(5, total_obs*0.1)` 且 `active_days >= 2`
- 分类阈值: `collision_distance >= 20000.0m`, `migration_distance >= 500.0m`

## 研究结论

- `single_large_coverage`: `94`
- `collision_like`: `1`
- `dual_centroid`: `4`
- `migration_like`: `1`
- 当前系统 `is_multi_centroid=true` 数: `100`
- 研究判定 `stable_cluster>=2` 数: `6`
- 当前系统 `is_dynamic=true` 数: `63`
- 研究判定 `dynamic_multi` 数: `0`
- 稳定簇对最大质心间距: `1957464.3m`
- 稳定簇对平均质心间距: `326936.5m`

## 参数敏感性

- `eps=150m`: single=`89`, dual=`8`, migration=`1`, dynamic=`1`, collision=`1`
- `eps=250m`: single=`94`, dual=`4`, migration=`1`, dynamic=`0`, collision=`1`
- `eps=400m`: single=`95`, dual=`3`, migration=`1`, dynamic=`0`, collision=`1`

## 观察

- 当前生产标签对“大半径 Cell”明显偏保守：前 100 个研究样本中，系统几乎都已打 `is_multi_centroid=true`，但研究后可拆出更细的 `dual_centroid / migration_like / dynamic_multi / collision_like`。
- 真正的热点不是“是否存在多簇”，而是“多簇之间的距离 + 时间重叠关系”。这决定了它更像双质心、迁移还是碰撞。
- `window_obs_count` 和 `active_days` 很多样本都不高，说明未来正式方案必须先做候选集收缩，不能对全量 Cell 逐个做重聚类。

## 代表样本

### dual_centroid

- `46001|90137|188656|772735361|5G` `p90=1339882.5m`, `window_obs=30`, `stable_clusters=2`, `pairwise=0-1=897m/overlap2d`, `current=(large_coverage, multi=True, dynamic=False)`
- `46011|405533|405759|1661989135|5G` `p90=1142091.7m`, `window_obs=140`, `stable_clusters=2`, `pairwise=0-1=1259m/overlap2d`, `current=(migration, multi=True, dynamic=True)`
- `46001|421902|413108|1692090370|5G` `p90=642123.0m`, `window_obs=42`, `stable_clusters=2`, `pairwise=0-1=419m/overlap2d`, `current=(stable, multi=True, dynamic=False)`
- `46011|58660|111287|28489523|4G` `p90=430978.0m`, `window_obs=30`, `stable_clusters=2`, `pairwise=1-0=926m/overlap2d`, `current=(large_coverage, multi=True, dynamic=False)`

### migration_like

- `46000|2229516|1111079|4550979585|5G` `p90=1028752.8m`, `window_obs=32`, `stable_clusters=2`, `pairwise=0-2=653m/overlap1d`, `current=(large_coverage, multi=True, dynamic=False)`

### collision_like

- `46000|4308|889015|227588041|4G` `p90=1955417.2m`, `window_obs=45`, `stable_clusters=2`, `pairwise=1-0=1957464m/overlap2d`, `current=(migration, multi=True, dynamic=True)`

## 面向 PostGIS 的落地建议

- 远程容器当前没有 `postgis` 扩展；正式入库前，优先在 PG17 容器中补 `postgis`，然后把本脚本的候选集筛选逻辑迁移成 SQL。
- 推荐的 PG 内实现入口不是全量 Cell，而是 `trusted_cell_library(batch_id=t) WHERE p90_radius_m >= 800 OR gps_anomaly_type IS NOT NULL OR is_dynamic OR is_collision`。
- 聚类建议优先试 `ST_ClusterDBSCAN`，再把簇结果写回 `cell_centroid_detail`，后续标签在 publish 层判定。
- 未来线上增量化策略: 只重算 `p90_radius_m`/`gps_anomaly_type`/`drift_pattern` 发生变化的 Cell，历史稳定 Cell 直接复用上轮簇结果。
