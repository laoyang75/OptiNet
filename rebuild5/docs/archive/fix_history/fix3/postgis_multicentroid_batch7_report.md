# Batch7 PostGIS 多质心 / 迁移 / 碰撞研究报告

- 生成时间: `2026-04-12T16:06:15.782570+00:00`
- 研究输入数据库: `postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
- 研究批次: `batch_id=7`
- 基线参数: `eps250_mp4_grid50`

## 1. 样本选择方法

研究不是简单取 `p90` 最大前 100，而是先按真实标签分层，再做去重抽样。

- 基础候选范围: `trusted_cell_library(batch7)` 中 `p90_radius_m >= 800m` 的大半径 Cell
- 高质量主样本: `window_obs_count >= 20` 且 `active_days >= 3`，覆盖 `stable / large_coverage / migration / collision / moderate_drift`
- 脏信号补样: 额外纳入 `gps_anomaly_type IS NOT NULL` 与 `drift_pattern=insufficient` 的低观测异常样本
- 极端值补样: 额外纳入 `p90_radius_m >= 1500m` 的超大半径对象

- 最终样本 Cell 数: `66`
- 最终样本观测点数: `29567`
- 样本中 4G/5G: `19` / `47`
- 样本中 `gps_anomaly_type IS NOT NULL`: `46`

### 1.1 分层覆盖

| 分层 | 样本 Cell | 4G | 5G | p50 window_obs | p50 active_days |
|---|---:|---:|---:|---:|---:|
| large_coverage | 12 | 0 | 12 | 594.5 | 5.0 |
| stable_large | 12 | 1 | 11 | 1092.0 | 5.0 |
| collision | 10 | 3 | 7 | 502.5 | 5.0 |
| migration | 10 | 2 | 8 | 466.5 | 5.0 |
| gps_anomaly | 8 | 0 | 8 | 1113.0 | 5.0 |
| moderate_drift | 8 | 4 | 4 | 190.0 | 5.0 |
| top_radius | 8 | 7 | 1 | 37.0 | 4.0 |
| low_obs_dirty | 6 | 2 | 4 | 6.0 | 1.0 |

### 1.2 当前 drift_pattern 覆盖

| drift_pattern | 样本 Cell | anomaly Cell |
|---|---:|---:|
| migration | 14 | 10 |
| stable | 14 | 11 |
| collision | 12 | 5 |
| large_coverage | 12 | 7 |
| moderate_drift | 8 | 7 |
| insufficient | 6 | 6 |

## 2. PostGIS 研究方法

### 2.1 空间处理顺序

1. 从 `cell_sliding_window` 提取真实 GPS 观测，只保留 `gps_valid=true` 且经纬度非空的记录。
2. 把 WGS84 点转成 `EPSG:3857` 的米制 geometry，用于 `ST_ClusterDBSCAN` 和 `ST_SnapToGrid`。
3. 先用 `ST_SnapToGrid(geom_m, 50m)` 压掉抖动，再对每个 Cell 分区执行 `ST_ClusterDBSCAN`。
4. 对每个簇统计 `obs/dev/active_days/share_ratio`，并用这些稳定性指标过滤掉小簇、单设备簇和短时簇。
5. 对稳定簇再算 `ST_Centroid`、`ST_ConvexHull`、`ST_Area`、簇间 `ST_Distance` 和日期重叠度。

### 2.2 脏信号定义

- `ST_ClusterDBSCAN` 输出 `cluster_id IS NULL` 的噪声点，视为一级脏信号。
- 即便被聚成簇，只要 `obs_count < max(5, total_obs*10%)`、或 `dev_count < 2`、或 `active_days < 2`，视为不稳定簇，仍在最终质心计算前过滤。
- 主质心、多质心、迁移、碰撞的分类只基于稳定簇，不直接把噪声点或不稳定簇纳入最终中心。

### 2.3 基线参数

- `eps = 250m`
- `minpoints = 4`
- `snap_to_grid = 50m`
- `stable cluster`: `obs >= max(5, total_obs*0.10)`, `dev >= 2`, `active_days >= 2`
- `collision_distance = 20000m`
- `migration_max_overlap_days = 1`

## 3. 参数敏感性

| 参数组 | single_large | single_noise | dirty_sparse | dual | migration | collision | dynamic_multi |
|---|---:|---:|---:|---:|---:|---:|---:|
| eps150_mp3_grid50 | 23 | 24 | 9 | 7 | 0 | 1 | 2 |
| eps250_mp4_grid50 | 28 | 20 | 9 | 7 | 0 | 1 | 1 |
| eps400_mp4_grid50 | 30 | 21 | 9 | 5 | 0 | 1 | 0 |

观察：
- `eps=150` 更容易把相邻热点拆成多个簇，`dual_centroid / dirty_sparse` 会偏多。
- `eps=400` 会明显吞并邻近热点，`single_large_coverage` 会偏多，迁移和双质心会被低估。
- `eps=250, minpoints=4` 在“稳定双簇能保留下来、单设备噪声不会轻易晋级”为目标下更平衡。

## 4. 基线结果

| 类别 | Cell 数 |
|---|---:|
| single_large_coverage | 28 |
| single_with_noise | 20 |
| dirty_sparse | 9 |
| dual_centroid | 7 |
| migration_like | 0 |
| collision_like | 1 |
| dynamic_multi | 1 |

- `filtered_noise_ratio >= 0.35` 的样本数: `30`
- `stable_cluster_count = 0` 的样本数: `9`
- 当前系统 `is_multi_centroid=true` 的样本数: `66`
- 研究判定 `stable_cluster_count >= 2` 的样本数: `9`

## 5. 代表 case

### single_large_coverage

- `46000|2097289|1404331|5752139779|5G` p90=6967.2m, window_obs=1367, total_obs=1153, stable_clusters=1, noise_ratio=0.18, max_centroid_distance=0.0m, overlap_days=0, current=(stable, multi=True, dynamic=False, anomaly=drift)
- `46000|2097173|1400836|5737824258|5G` p90=1034.3m, window_obs=1279, total_obs=1137, stable_clusters=1, noise_ratio=0.13, max_centroid_distance=0.0m, overlap_days=0, current=(stable, multi=True, dynamic=False, anomaly=time_cluster)
- `46000|2097243|1435174|5878472706|5G` p90=1733.1m, window_obs=1072, total_obs=1051, stable_clusters=1, noise_ratio=0.32, max_centroid_distance=0.0m, overlap_days=0, current=(stable, multi=True, dynamic=False, anomaly=None)

### single_with_noise

- `46000|2097268|1376891|5639745539|5G` p90=2375.6m, window_obs=1081, total_obs=1069, stable_clusters=1, noise_ratio=0.36, max_centroid_distance=0.0m, overlap_days=0, current=(large_coverage, multi=True, dynamic=True, anomaly=drift)
- `46000|2097215|1000036|4096147457|5G` p90=1336.3m, window_obs=826, total_obs=759, stable_clusters=1, noise_ratio=0.54, max_centroid_distance=0.0m, overlap_days=0, current=(large_coverage, multi=True, dynamic=True, anomaly=None)
- `46000|2097285|1392580|5704007681|5G` p90=3152.3m, window_obs=786, total_obs=750, stable_clusters=1, noise_ratio=0.49, max_centroid_distance=0.0m, overlap_days=0, current=(collision, multi=True, dynamic=True, anomaly=time_cluster)

### dirty_sparse

- `46001|6423|17006|4353668|4G` p90=1903113.9m, window_obs=29, total_obs=29, stable_clusters=0, noise_ratio=1.00, max_centroid_distance=0.0m, overlap_days=0, current=(migration, multi=True, dynamic=True, anomaly=None)
- `46001|102417|157428|644826243|5G` p90=997594.2m, window_obs=18, total_obs=17, stable_clusters=0, noise_ratio=1.00, max_centroid_distance=0.0m, overlap_days=0, current=(insufficient, multi=True, dynamic=False, anomaly=drift)
- `46001|6969|114385|29282617|4G` p90=2171750.4m, window_obs=16, total_obs=16, stable_clusters=0, noise_ratio=1.00, max_centroid_distance=0.0m, overlap_days=0, current=(collision, multi=True, dynamic=True, anomaly=None)

### dual_centroid

- `46000|2097290|1420485|5818306561|5G` p90=2419.9m, window_obs=1075, total_obs=968, stable_clusters=2, noise_ratio=0.11, max_centroid_distance=2528.2m, overlap_days=5, current=(stable, multi=True, dynamic=False, anomaly=drift)
- `46001|73740|132326|542007553|5G` p90=995.6m, window_obs=929, total_obs=826, stable_clusters=2, noise_ratio=0.02, max_centroid_distance=993.5m, overlap_days=3, current=(large_coverage, multi=True, dynamic=False, anomaly=None)
- `46000|2097201|1404542|5753004065|5G` p90=1485.7m, window_obs=523, total_obs=514, stable_clusters=2, noise_ratio=0.18, max_centroid_distance=1421.4m, overlap_days=4, current=(large_coverage, multi=True, dynamic=False, anomaly=drift)

### collision_like

- `46000|4308|889015|227588041|4G` p90=1955417.2m, window_obs=45, total_obs=41, stable_clusters=2, noise_ratio=0.07, max_centroid_distance=1955203.1m, overlap_days=2, current=(migration, multi=True, dynamic=True, anomaly=None)

### dynamic_multi

- `46001|98310|140668|576176387|5G` p90=1385.8m, window_obs=573, total_obs=524, stable_clusters=3, noise_ratio=0.09, max_centroid_distance=1609.6m, overlap_days=4, current=(large_coverage, multi=True, dynamic=True, anomaly=None)

## 6. 推荐正式实现方案

### 6.1 候选集收缩

- 只对 `p90_radius_m >= 800m`、或 `gps_anomaly_type IS NOT NULL`、或 `is_dynamic`、或 `drift_pattern IN (collision, migration, moderate_drift)` 的 Cell 进入 PostGIS 研究链。
- `window_obs_count < 5` 或 `active_days < 2` 的对象不直接做多质心结论，只进入“dirty/insufficient”观察池。

### 6.2 PG 内实现顺序

1. `candidate_cells`：从 `trusted_cell_library(batch=t)` 选候选集。
2. `candidate_obs`：从 `cell_sliding_window` 提取有效 GPS，并生成 `geom_4326`、`geom_m`。
3. `clustered_points`：`ST_SnapToGrid` 后按 Cell 分区跑 `ST_ClusterDBSCAN`。
4. `cluster_stats`：按簇聚合 `obs/dev/active_days/share_ratio`，算 `ST_Centroid / ST_ConvexHull / ST_Area`。
5. `stable_clusters`：过滤掉噪声簇和不稳定簇。
6. `cell_cluster_summary`：算稳定簇数、簇间最大距离、日期重叠天数、主次簇占比。
7. `cell_centroid_detail`：只把稳定簇写入细表；主簇作为主质心，对外服务只默认返回主簇。

### 6.3 分类判定建议

- `dirty_sparse`: 没有稳定簇，或稳定证据完全不足。
- `single_large_coverage`: 只有 1 个稳定簇，允许存在少量噪声点，但噪声不会进入最终质心。
- `single_with_noise`: 只有 1 个稳定簇，但过滤掉的噪声/不稳定簇占比偏高，应保留异常标签而不是直接升为多质心。
- `dual_centroid`: 恰好 2 个稳定簇，簇间距离明显，且时间上存在持续重叠。
- `migration_like`: 2 个稳定簇，但重叠天数很低，更像阶段性搬迁而不是长期双中心。
- `collision_like`: 2 个及以上稳定簇，且任意稳定簇间距超过 20km。
- `dynamic_multi`: 3 个及以上稳定簇，或多簇长期交替出现。

### 6.4 坐标与函数建议

- `ST_ClusterDBSCAN` 和 `ST_SnapToGrid` 用米制 `geometry`，推荐先 `ST_Transform(..., 3857)`。
- 报告距离和簇间距离用 `ST_Distance(geography)`，减少经纬度尺度误差。
- 面积类指标用 `ST_Area`，可以对 `ST_ConvexHull` 结果做 geography/投影后再算。

### 6.5 成本与增量化

- 候选集外的稳定 Cell 直接复用已有结果，不做全量聚类。
- 增量重算触发条件建议收口到：`p90` 显著变化、`gps_anomaly_type` 变化、`drift_pattern` 变化、新进候选集。
- `cell_centroid_detail` 可以作为下一批的先验簇库，新点优先按距离归属到已有稳定簇，再决定是否触发重聚类。

## 7. 本轮结论

- PostGIS 已能在 PG 内完成候选筛选、簇生成、簇特征统计和分类判定，不需要长期依赖 Python 离线聚类。
- 研究结果已经形成，但还没有并入主链，也没有触发 smoke 全流程或正式 7 天重跑。
- 下一步必须先人工确认这套分类边界与参数，再进入整合验证。
