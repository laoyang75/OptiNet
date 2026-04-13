# Step 5 重构方案 v2

> 目标：以 `rebuild5/docs/05_画像维护.md` 为准，把当前 Step 5 收敛成“结构清晰、当前规模可直接跑通、结果与设计文档一致”的实现。  
> 当前阶段不考虑分表，不优先做超大规模优化；优先保证语义正确、阶段清楚、便于用 `10 个 LAC` 样例验证。

## 1. 本轮设计边界

本轮 Step 5 重构只解决三类问题：

1. 让 Cell / BS / LAC 的维护链严格按文档闭环
2. 让多质心、退出、防毒化、碰撞、窗口重算落到清晰阶段
3. 让当前规模下的执行模型更直接，不再把大量规则揉进少数大 SQL

本轮**不做**：

- 分表
- 大规模局部增量算法
- 复杂多质心算法优化
- 面向未来超大规模的存储架构

当前规模判断：

- `trusted_cell_library` 单批约几十万行
- `trusted_bs_library` 单批约十几万行
- 当前更适合“按批全量重算维护结果 + 只保留跨批窗口表”
- 不适合继续为了未来规模牺牲当前可读性

## 2. 当前实现与设计文档的主要偏差

### 2.1 已对齐的部分

- Step 5 已明确只读上一版正式库 / 当前批 Step 3 冻结快照
- `cell_sliding_window` 已是跨批持久表
- Cell -> BS -> LAC 的正式库上卷方向是对的
- `active_days_30d` / `consecutive_inactive_days` 已进入 Cell 正式库

### 2.2 仍未对齐的部分

- `cell_centroid_detail` / `bs_centroid_detail` 仍是单簇 stub，不符合文档里的“多簇独立记录”
- `gps_anomaly_type` 目前主要靠 `anomaly_count` 粗分，不符合文档里的 `drift / time_cluster / migration_suspect`
- BS / LAC 退出链路未真正落到正式库维护语义
- Step 5 统计表仍是 `step5_run_stats`，而文档写的是 `step5_maintenance_log`
- `publish_cell.py` 同时做合并、退出、防毒化、漂移、标签、carry-forward，结构过于混合

## 3. 重构目标

重构后的 Step 5 采用“持久窗口 + 批次阶段表 + 最终发布表”的模式。

### 3.1 设计原则

- 只把 `cell_sliding_window` 保留为跨批持久维护表
- 本批其余重算结果全部进入清晰命名的阶段表
- 最终正式库继续用 `trusted_*_library`
- 当前规模下优先使用 `CTAS / INSERT SELECT / ANALYZE`
- 不做行级细碎更新，尽量让每个阶段是“产一张清晰的新表”

### 3.2 目标链路

```text
Step 4 持久化结果
  + 上一版 trusted_*_library
  + 当前批 trusted_snapshot_*
  -> Step 5.0 窗口刷新
  -> Step 5.1 Cell 指标重算
  -> Step 5.2 GPS 异常时序归并
  -> Step 5.3 多质心明细
  -> Step 5.4 Cell 维护判定
  -> Step 5.5 Cell 正式库发布
  -> Step 5.6 collision_id_list + A 类真碰撞
  -> Step 5.7 BS 维护与发布
  -> Step 5.8 BS 多质心明细
  -> Step 5.9 LAC 维护与发布
```

## 4. 建议的阶段拆分

## 4.1 Step 5.0 窗口刷新

保留现有 `cell_sliding_window` 作为唯一跨批维护明细表。

### 输入

- 上一轮 `cell_sliding_window`
- 当前批 `enriched_records`

### 输出

- 更新后的 `cell_sliding_window`

### 规则

- 当前批 `enriched_records` 全量并入窗口
- 继续采用数据驱动时间参考，不使用 `NOW()`
- 当前实现先保留“最近 30 天”主裁剪规则
- 若后续补“数量优先窗口”，放在本阶段内部扩展，不外溢到下游

说明：

- 当前规模下，窗口刷新仍然是唯一必须持久维护的观测级表
- 其余指标都应该从窗口派生，不要再让多个模块各自解释“最近观测”

## 4.2 Step 5.1 Cell 指标重算

新增阶段表：

- `rebuild5.step5_cell_daily_centroid_stage`
- `rebuild5.step5_cell_metrics_stage`

### 职责

- 从窗口重算 `center_lon/lat`
- 重算 `p50_radius_m / p90_radius_m`
- 重算 `rsrp_avg / rsrq_avg / sinr_avg / pressure_avg`
- 重算 `window_obs_count / active_days_30d / consecutive_inactive_days / last_observed_at`
- 重算 `max_spread_m / net_drift_m / drift_ratio`

### 说明

- `daily_centroids` 和 `cell_metrics` 继续保留 SQL 主导
- 这些聚合完全适合数据库做
- 与正式发布解耦后，性能问题会更容易定位

## 4.3 Step 5.2 GPS 异常时序归并

新增阶段表：

- `rebuild5.step5_cell_gps_anomaly_stage`

### 输入

- 当前批 `gps_anomaly_log`
- `step5_cell_daily_centroid_stage`

### 输出字段

- `anomaly_count`
- `anomaly_days`
- `max_consecutive_anomaly_days`
- `peak_hour_ratio`
- `gps_anomaly_type`

### 当前建议

在本轮先做保守实现：

- `drift`：异常不连续，且无显著单向位移
- `migration_suspect`：异常连续，且与 `net_drift_m` 同向
- `time_cluster`：异常高度集中在单小时段

说明：

- 当前无需先做复杂时序模型
- 但不能继续只有 `anomaly_count -> migration_suspect/drift` 这一个粗逻辑

## 4.4 Step 5.3 多质心明细

新增阶段表：

- `rebuild5.step5_cell_centroid_cluster_stage`
- `rebuild5.step5_bs_centroid_cluster_stage`

### Cell 多质心简化方案

当前先采用“异常子集 + 日质心聚类”的简单版本，不直接上原始点重聚类。

#### 候选子集

满足任一条件即可进入：

- `p90_radius_m >= multi_centroid_trigger_min_p90_m`
- `drift_pattern <> 'stable'`
- `gps_anomaly_type IS NOT NULL`
- 命中 `collision_id_list`

#### 简化聚类口径

- 输入点：`step5_cell_daily_centroid_stage`
- 若同一 Cell 的日质心可以按明显距离断裂分成两组及以上，则判为多簇
- 以观测天数 + 观测量作为主簇判定依据

#### 输出要求

- `cell_centroid_detail` 不能再只有 `cluster_id=1`
- 至少要能输出：
  - `cluster_id`
  - `is_primary`
  - `center_lon/lat`
  - `obs_count`
  - `dev_count`
  - `share_ratio`

说明：

- 这版算法可以简单
- 但结果结构必须符合设计文档，后续才能继续优化算法而不改外部表语义

### BS 多质心简化方案

- 输入使用维护后的 Cell 主簇 / 次簇结果
- 仅对 `large_spread / multi_centroid / dynamic_bs` 候选 BS 做聚类
- 先形成 `bs_centroid_detail` 真多簇记录，算法可简单

## 4.5 Step 5.4 Cell 维护判定

新增阶段表：

- `rebuild5.step5_cell_publish_stage`

### 统一在这一阶段做的事情

- 当前批 snapshot Cell 与上一版 published Cell 的合并
- carry-forward
- 退出管理
- 防毒化
- 漂移分类
- `is_multi_centroid`
- `is_dynamic`
- `cell_scale`
- `gps_anomaly_type`

### 设计要求

- 所有 Cell 级判定只在这一处收口
- `publish_cell.py` 不再同时承担“计算 + 判定 + 发布”三种职责
- 发布动作只做“把 stage 落到正式表”

### lifecycle / baseline 规则

- `lifecycle_state` 的 `dormant / retired` 由 `active_days_30d + consecutive_inactive_days` 统一判
- `baseline_eligible` 由 Step 3 准入结果叠加防毒化 / 真碰撞阻断得出
- `anchor_eligible` 不在 Step 5 重新定义业务门槛；对当前批 snapshot 对象取 snapshot 值，对 carry-forward 对象沿用上一版，除非进入退出链路

## 4.6 Step 5.5 Cell 正式库发布

### 当前建议

当前规模下，`trusted_cell_library` 继续使用：

- `DELETE current batch`
- `INSERT FROM step5_cell_publish_stage`

不需要先做分表。

若后续执行计划仍差，可改为：

- `CREATE TABLE AS`
- `CREATE INDEX`
- `INSERT INTO trusted_cell_library`

但本质仍是“本批全量生成一份新发布结果”，不是行级补丁更新。

## 4.7 Step 5.6 碰撞体系

碰撞继续严格分层：

- B 类：`collision_id_list`
- A 类：`trusted_cell_library.is_collision`

### B 类

- 仍基于“同一 `cell_id` 对应多个 `(operator_code, lac)`”
- 保留给 Step 2 / Step 4 只读消费

### A 类

- 以 `(operator_code, tech_norm, lac, cell_id)` 为业务键
- 从 `step5_cell_publish_stage` / `trusted_cell_library` 中找多 BS 且簇间距离足够大的对象
- 命中后：
  - `is_collision=true`
  - `baseline_eligible=false`
  - `antitoxin_hit=true`

## 4.8 Step 5.7 BS 维护与发布

新增阶段表：

- `rebuild5.step5_bs_publish_stage`

### 输入

- 维护后的 Cell 发布 stage / 正式表
- `cell_centroid_detail`

### 输出

- `trusted_bs_library`
- `bs_centroid_detail`

### 规则

- 只从维护后的 Cell 上卷
- `classification` 在本阶段统一判定
- `window_active_cell_count` 在本阶段统一聚合
- BS 退出在本阶段补上，不再只保留 `qualified/observing`

## 4.9 Step 5.8 LAC 维护与发布

新增阶段表：

- `rebuild5.step5_lac_publish_stage`

### 输入

- 维护后的 BS stage / 正式表

### 输出

- `trusted_lac_library`

### 规则

- 只从维护后的 BS 上卷
- `active_bs_count / retired_bs_count / anomaly_bs_ratio / boundary_stability_score / trend` 全在这里统一收口
- LAC 退出链路也在本阶段真正实现

## 5. 执行模型建议

当前不做分表，采用下面的模型：

### 5.1 持久表

- `cell_sliding_window`
- `trusted_cell_library`
- `trusted_bs_library`
- `trusted_lac_library`
- `collision_id_list`
- `cell_centroid_detail`
- `bs_centroid_detail`

### 5.2 批次阶段表

- 统一使用 `step5_*_stage` 命名
- 每批开头删当前批或直接重建
- 阶段表全部可 `UNLOGGED`

### 5.3 优点

- 代码职责清楚
- SQL 执行计划更容易逐段分析
- 样例数据验证时能逐阶段对比
- 后续若要优化某一阶段，不会牵动整个 Step 5

## 6. 10 个 LAC 样例验证方案

样例表：

- `rebuild5.etl_cleaned_top10_lac_sample`

### 建议验证顺序

1. 用样例表从 Step 1 对应流程完整跑通
2. 对比旧 Step 5 与新 Step 5 在以下方面的一致性
3. 只要设计要求更高而旧实现明显缺失，以设计文档为准，不以旧结果为准

### 重点对比项

- `trusted_cell_library / trusted_bs_library / trusted_lac_library` 行数
- `collision_id_list` 规模
- Cell 生命周期分布
- `baseline_eligible` 分布
- `is_multi_centroid` 数量
- `cell_centroid_detail` 是否出现 `cluster_id > 1`
- `bs_centroid_detail` 是否出现 `cluster_id > 1`
- `gps_anomaly_type` 是否至少覆盖 `drift / migration_suspect / time_cluster`
- BS / LAC 是否出现真实退出状态

## 7. 本轮落地优先级

### P0

- Step 4 明细持久化
- Step 5 分阶段拆分设计定稿
- Cell / BS 多质心 detail 不再是单簇 stub

### P1

- Cell 维护 stage 重构
- GPS 异常时序归并
- BS / LAC 退出链路落地

### P2

- 多质心算法优化
- 更细的局部增量更新
- 未来分表 / 归档

## 8. 结论

当前 Step 5 不应继续围绕“加索引和调 worker”做微调，而应回到设计文档，把它收敛成：

- 一个持久窗口
- 若干批次阶段表
- 三层正式发布表
- 两层碰撞体系
- 真正可查询的多质心 detail

在当前数据规模下，这条路线最直接，也最符合设计文档。
