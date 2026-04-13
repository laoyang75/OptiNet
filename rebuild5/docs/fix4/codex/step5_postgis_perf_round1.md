# Step5 PostGIS 瓶颈单独分析（Round 1）

时间：2026-04-13  
环境：`ip_loc2_fix4_codex`  
范围：只看 `Step5 PostGIS`，不讨论 `Step4` 补数

## 结论

这轮已经定位清楚：

- 瓶颈不在候选规模本身
- 也不在 `ST_ClusterDBSCAN`
- 而在 `publish_cell_centroid_detail()` 里把稳定簇统计全部塞进一个超大 CTAS：
  - `CREATE UNLOGGED TABLE rebuild5._cell_centroid_valid_clusters AS ...`

把这段大 CTE 拆成物理阶段表后，`batch3` 的 PostGIS 主体时间从分钟级直接降到秒级。

## 真实数据规模（batch3）

在 `batch3` 上直接量到的阶段规模：

- 候选 Cell：`2214`
- 原始点：`145,554`
- 网格点：`35,008`
- labelled_points：`145,554`

这个规模不算小，但也没有大到需要 `6` 分钟以上才能完成稳定簇统计。

## 改造前

在真实 `batch3` 状态上，单独跑一次 `publish_cell_centroid_detail()` 的阶段计时：

- `POSTGIS_TOTAL = 369.925s`
- 其中：
  - `01_candidates = 0.084s`
  - `02_points = 0.489s`
  - `03_grid_points = 0.244s`
  - `04_clustered_grid = 0.191s`
  - `05_labelled_points = 0.181s`
  - `06_valid_clusters = 362.312s`

结论：

- 几乎全部时间都耗在 `06_valid_clusters`
- 前面的候选、取点、网格化、DBSCAN 都很轻

## 拆分验证

把 `valid_clusters` 这段手工拆成 7 个物理阶段表后，`batch3` 的单段耗时如下：

- `06a_cell_totals = 0.303s`
- `06b_cluster_base = 0.422s`
- `06c_cluster_centers = 0.067s`
- `06d_cluster_radius = 0.381s`
- `06e_cluster_stats = 0.093s`
- `06f_filtered = 0.059s`
- `06g_ranked = 0.088s`

结论：

- 真正的计算量并不大
- 旧写法慢，主要是 PG 在一个大 CTE 里做重聚合、窗口函数和 join 时的执行结构很差
- 拆成物理阶段表后，同一批数据只要几秒

## 已落地代码改动

我已经把这轮优化写进代码，不再保留“大 CTE 一把算完”的旧结构。

### 1. 稳定簇分阶段落表

当前 `publish_cell_centroid_detail()` 已拆成：

- `_cell_centroid_cell_totals`
- `_cell_centroid_cluster_base`
- `_cell_centroid_cluster_centers`
- `_cell_centroid_cluster_radius`
- `_cell_centroid_cluster_stats`
- `_cell_centroid_filtered_clusters`
- `_cell_centroid_ranked_clusters`
- `_cell_centroid_valid_clusters`

代码位置：

- [publish_bs_lac.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/maintenance/publish_bs_lac.py:321)

### 2. batch3 真实整体验证

用正式脚本入口只重跑 `2025-12-03` 的 `Step5`：

- `Step5 done = 13s`

子步骤输出：

- `daily_centroids = 7s`
- `metrics_base = 1s`
- `core_gps = 3s`
- `metrics_radius = 5s`
- `metrics_activity = 3s`
- `drift_metrics = 1s`
- `anomaly_summary = 1s`
- `collision = 1s`
- `done = 13s`

说明：

- 旧版在 `batch3` 上的 `publish_cell_centroid_detail()` 单段要 `369.9s`
- 现在整段 `Step5` 已经回到 `13s`
- 这说明这轮优化不是“局部 SQL 看起来快”，而是已经传导到整个 `Step5`

## 当前判断

这轮纯 `Step5 PostGIS` 分析已经能给出明确判断：

1. 旧瓶颈是 SQL 结构问题，不是单纯候选量问题
2. 把稳定簇统计拆成物理阶段表是有效优化
3. 下一轮如果继续做性能，不该再优先纠缠 `DBSCAN` 参数，而应继续沿着“阶段物化 + 轻量 join + 避免大 CTE”这条线做

## 当前残留

这轮只解决了 `Step5 PostGIS` 的工程瓶颈，没有处理这些研究问题：

- `dual_cluster / multi_cluster` 的触发是否过敏
- 质心核心点过滤是否会把部分正常双簇压扁
- `raw_p90 / core_outlier_ratio` 的候选触发边界是否需要继续收敛

这些应继续单独研究，不要再和 `Step4 donor` 或 `Step5 PostGIS` 性能混在一起。
