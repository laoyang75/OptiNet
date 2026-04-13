# Fix4 工程闭环固化（batch1-2）

时间：2026-04-13  
环境：`ip_loc2_fix4_codex`  
输入：`rebuild5_fix4_work.etl_cleaned_shared_sample_local`  
范围：只验证 `2025-12-01 ~ 2025-12-02`

## 本次先解决的工程问题

先不讨论质心研究口径，只处理一个工程闭环问题：

- `Step2` 已经把命中正式库的记录正常分流到 `path A`
- 但 `Step4` 在实际补数时，又把 donor 限制成了 `donor_anchor_eligible=true`
- 这导致“已经进入 Step5 正式库的对象”并不等于“Step4 可以补数的 donor 池”

也就是说，旧链路的问题不是 `Step2` 没分流，而是 `Step4` 又把 `Step5` 池缩成了 `anchor_eligible` 子池。

## 根因证据

### 1. Step2 确实已经把 donor 带进来了

`path_a_records` 已经从正式库把 donor 审计字段带入，包括：

- `donor_batch_id`
- `donor_snapshot_version`
- `donor_center_lon`
- `donor_center_lat`
- `donor_anchor_eligible`

代码位置：

- [profile/pipeline.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/profile/pipeline.py:902)

### 2. 旧版 Step4 又把 donor 缩成 anchor 子池

旧版 `_insert_enriched_records()` 和 `_insert_gps_anomaly_log()` 的 donor 使用条件，实际都绑在：

- `COALESCE(p.donor_anchor_eligible, FALSE)`

这意味着：

- donor 虽然已经命中正式库
- 但只要 `anchor_eligible=false`
- Step4 就不会用这个 donor 做补数或异常对比

### 3. batch1 为什么会让 batch2 donor=0

在当前样例上，`batch1` 已毕业的 `5746` 个 cell 中：

- `gps_valid_count >= 10`：`5069`
- `distinct_dev_id >= 2`：`5627`
- `p90 < 1500m`：`5722`
- `observed_span_hours >= 24`：`0`
- 四项同时满足：`0`

因此旧版 donor gate 在 `batch2` 会把 donor 全部挡掉。

`anchor_eligible` 的定义位置：

- [evaluation/pipeline.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/evaluation/pipeline.py:558)

## 工程修复

本次只改 `Step4` donor 使用条件，不改 `Step3/Step5` 的业务定义。

### 修复原则

- `path A` 命中的 donor，既然已经是已发布正式库对象，就可以作为 Step4 补数 donor
- `anchor_eligible` 保留为审计字段，但不再作为 Step4 的二次准入门槛

### 代码改动

#### Step4 填充值

把 donor 使用条件从：

- `COALESCE(p.donor_anchor_eligible, FALSE)`

改为：

- `p.donor_batch_id IS NOT NULL`

这样 GPS、RSRP、RSRQ、SINR、pressure、operator、LAC、tech 的 donor 补值都直接基于已命中的 published donor。

代码位置：

- [enrichment/pipeline.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/enrichment/pipeline.py:163)

#### Step4 统计

把以下统计同样改成基于 `donor_batch_id IS NOT NULL`：

- `donor_matched_count`
- `donor_excellent_count`
- `donor_qualified_count`
- `collision_skip_anomaly_count`

代码位置：

- [enrichment/pipeline.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/enrichment/pipeline.py:346)

#### 测试

同步把 enrichment 的守卫测试更新为“任何 matched published donor 都可用”。

## batch1-2 验证结果

### Step2 / Step3

| batch | pathA | pathB | pathB_cell | pathC | waiting | qualified | excellent | anchor_eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 292,872 | 13,490 | 334 | 0 | 3,807 | 1,939 | 0 |
| 2 | 235,711 | 57,905 | 7,672 | 184 | 0 | 6,337 | 2,084 | 1,976 |

结论：

- `Step2` 分流正常
- `waiting=0` 不是当前工程阻塞点
- `batch2` 已经大量进入 `path A`

### Step4

| batch | total_path_a | donor_matched | gps_filled | gps_anomaly |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 |
| 2 | 235,711 | 235,711 | 14,362 | 6,450 |

关键结论：

- 修复后 `batch2 donor_matched_count` 从旧版 `0` 变成 `235,711`
- 这证明 donor 闭环已经打通
- 当前样例上“第二轮仍无补数”的工程问题已被解决

### Step5

| batch | published_cell | multi_centroid | dynamic | anomaly_bs | Step5_done |
|---|---:|---:|---:|---:|---:|
| 1 | 5,746 | 0 | 0 | 13 | 5s |
| 2 | 8,421 | 0 | 0 | 20 | 7s |

## 当前质心方案是什么

这部分还在研究中，但当前实现已经有一个明确方案，不是空白：

### Step2 主中心

`build_profile_base()` 不再直接拿全部 GPS 点算质心，而是：

1. 先把分钟级 GPS 点做 `SnapToGrid`
2. 选每个 cell 的主热点网格作为 seed
3. 计算每个点到 seed 的距离
4. 按 `keep_quantile` 取核心半径，并做 `min/max radius` 截断
5. 只用核心点重算 `center_lon/center_lat/p50/p90`

代码位置：

- [profile/pipeline.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/profile/pipeline.py:1023)

### Step5 窗口中心

`build_cell_core_gps_stats()` 在滑动窗口上复用同一思路：

1. `cell_sliding_window` 做主热点 seed
2. 计算窗口内点到 seed 的距离
3. 取核心点
4. 用核心点重算维护态质心和半径

代码位置：

- [maintenance/window.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/maintenance/window.py:197)

### Step5 多质心候选

为了避免“核心过滤把异常 cell 从候选里洗掉”，PostGIS 候选不只看维护后的 `p90`，还会额外看：

- `raw_p90_radius_m`
- `max_spread_m`
- `core_outlier_ratio`
- `gps_anomaly_type`

代码位置：

- [maintenance/publish_bs_lac.py](/Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/maintenance/publish_bs_lac.py:139)

## 质心方案当前状态

当前状态不是“已定稿”，而是“工程上已经有可运行方案，但研究上还没收口”。

已确认的点：

- 核心点过滤可以显著压掉极端离群点
- 这个方案已经真正接进 `Step2` 和 `Step5`

还没收口的点：

- 多质心候选触发仍偏敏感
- `dual_cluster / multi_cluster` 的触发边界还需要继续调
- `p80`、seed 半径上下限、候选触发条件还需要单独研究，不应再和 donor 工程闭环混在一起

## 下一步建议

下一步应继续分开做：

1. 工程线：保持 donor gate 修复，避免回退
2. 研究线：单独收敛质心和多质心触发，不再混改 Step4 donor 逻辑
