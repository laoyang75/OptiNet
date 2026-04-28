# PostGIS 质心研究报告

- 生成时间: `2026-04-13T00:07:29.404058+08:00`
- 研究数据库: `postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
- 研究批次: `batch_id=7`
- 主参数集: `eps250_mp4_g25`

## 样本选择

- 不是只取“大 p90 前 100”。本轮使用分层抽样，按 `stable_reference / gps_anomaly / large_coverage / multi_flag / migration_dynamic / collision` 六类各取高观测、高活跃样本。
- 入样门槛: `window_obs_count >= 20` 且 `active_days >= 3`。
- 每层上限: `25`。

- `collision`: `cells=25`, `window_obs_avg=464.2`, `p90_avg=41847.2m`
- `gps_anomaly`: `cells=25`, `window_obs_avg=2142.5`, `p90_avg=205.4m`
- `large_coverage`: `cells=25`, `window_obs_avg=658.6`, `p90_avg=964.3m`
- `migration_dynamic`: `cells=25`, `window_obs_avg=489.5`, `p90_avg=5161.8m`
- `multi_flag`: `cells=25`, `window_obs_avg=1094.6`, `p90_avg=3323.5m`
- `stable_reference`: `cells=25`, `window_obs_avg=2304.4`, `p90_avg=96.0m`

- 研究总样本: `150` 个 Cell，`33001` 个 GPS 点。

## 方法

- 先把候选 Cell 的 `cell_sliding_window(batch7)` GPS 点投到 `EPSG:3857`，再用 `ST_SnapToGrid(..., 25m)` 降低抖动。
- 主聚类函数使用 `ST_ClusterDBSCAN`，参数敏感性比较 `eps=150/250/400m, minpoints=4`。
- 将 `cluster_id IS NULL` 的点视为 DBSCAN 噪声点，作为“脏信号候选”。
- 稳定簇定义: `obs_count >= max(5, total_points*10%)` 且 `dev_count >= 2` 且 `active_days >= 2`。
- 分类规则基于稳定簇数量、簇间距离、日重叠天数、主导簇切换次数、噪声占比，而不是只看 `is_multi_centroid` 或 `p90`。

## 参数敏感性

- `eps150_mp4_g25`: single_stable=149
- `eps250_mp4_g25`: single_stable=149
- `eps400_mp4_g25`: single_stable=149

## 主参数结论

- 候选样本数: `149`
- `dirty_signal`: `0`
- `single_large_coverage`: `0`
- `dual_centroid`: `0`
- `multi_centroid`: `0`
- `migration_like`: `0`
- `dynamic_multi`: `0`
- `collision_like`: `0`

## 当前标签对比

- `single_stable`: `cells=149`, `current_multi=68`, `current_dynamic=49`, `current_anomaly=78`

## 代表样本


## 推荐方案

- 候选集不要全量做聚类，只处理 `is_collision / is_dynamic / is_multi_centroid / gps_anomaly_type IS NOT NULL / drift_pattern in (large_coverage, migration, collision)` 和高活跃 stable 参考样本。
- 正式聚类口径建议固定为 `ST_SnapToGrid(25m) + ST_ClusterDBSCAN(eps=250m, minpoints=4)`。
- 质心计算前先丢掉 DBSCAN 噪声点；正式对外质心取主稳定簇质心，而不是所有点或所有簇的平均。
- 分类顺序建议: `collision_like -> multi_centroid -> dynamic_multi -> migration_like -> dual_centroid -> dirty_signal -> single_large_coverage / single_stable`。
- `is_multi_centroid` 不应再用 `p90` 单阈值触发，应该改成“存在 2 个及以上稳定簇”。
- `dirty_signal` 应作为质心前置过滤层，而不是等到最终标签阶段才处理。

## 成本与增量化

- 建议把本轮研究表保留在 `rebuild5_research`，正式实现只对候选 Cell 增量重算。
- 增量触发条件建议收敛到: `p90_radius_m` 大幅变化、`gps_anomaly_type` 变化、`is_dynamic/is_collision` 变化、新进入候选集。
- 对稳定单簇 Cell 复用上一轮聚类结果，只更新窗口点和主簇统计，不重复全量 DBSCAN。
