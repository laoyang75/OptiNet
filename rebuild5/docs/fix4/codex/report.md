# Fix4 当前阶段报告

时间：2026-04-13  
范围：当前阶段只验证 `batch1-3`，不宣称已完成 7 天最终版

## 当前状态

这一轮已经把两类问题拆开处理：

1. 工程问题
   - `Step2 path A / path B` 分流是否正常
   - `Step4 donor` 是否真正能从 `Step5` 已发布池里补数
   - `Step5 PostGIS` 是否存在结构性性能瓶颈
2. 研究问题
   - 质心主中心如何抗离群点
   - 多质心触发是否过敏

当前阶段已经完成的，是一版可运行的整合实现，并在共享样例上完整重跑 `batch1-3`。

## 已验证事实

### 1. Step2 分流正常

当前整合版 `batch1-3` 的分流结果：

| batch | pathA | pathB | pathB_cell | pathC |
|---|---:|---:|---:|---:|
| 1 | 0 | 292,872 | 13,490 | 334 |
| 2 | 235,711 | 57,905 | 7,672 | 184 |
| 3 | 247,441 | 23,953 | 4,748 | 210 |

这说明：

- `Step2` 已经正常把已发布对象送进 `path A`
- 当前不存在“Step2 没有转发已入库对象”的程序性问题

### 2. Step4 donor 闭环已经打通

旧链路的问题不是 donor 不在正式库，而是 `Step4` 又把 donor 缩成了 `donor_anchor_eligible` 子池。

修复后 `batch1-3`：

| batch | total_path_a | donor_matched | gps_filled |
|---|---:|---:|---:|
| 1 | 0 | 0 | 0 |
| 2 | 235,711 | 235,711 | 14,362 |
| 3 | 247,441 | 247,441 | 15,161 |

这说明：

- 第二轮不再出现“完全没有补数”
- donor gate 工程问题已解决

### 3. Step5 PostGIS 结构性瓶颈已解决

在 `batch3` 真实状态上，旧版 `publish_cell_centroid_detail()`：

- 总耗时 `369.925s`
- 其中 `_cell_centroid_valid_clusters` 一段占 `362.312s`

把这段从一个大 CTE 拆成物理阶段表后：

- `publish_cell_centroid_detail()` 单段耗时降到 `12.743s`
- 同时整段 `batch3 Step5` 回到 `13s`

当前 `batch1-3 Step5`：

| batch | Step5 |
|---|---:|
| 1 | 8s |
| 2 | 10s |
| 3 | 13s |

### 4. 当前整合版已完整跑通 batch1-3

`batch1-3` 当前都已完整执行完毕，没有新的程序性中断。

## 当前质心方案

### 1. Step2 主中心

主中心不再直接用全部 GPS 点计算，而是：

1. 对分钟级 GPS 点做 `SnapToGrid`
2. 选主热点格子作为 seed
3. 计算每个点到 seed 的距离
4. 按 `keep_quantile` 选核心点，并做最小/最大半径截断
5. 只用核心点重算 `center/p50/p90`

### 2. Step5 窗口中心

`Step5` 在 `cell_sliding_window` 上复用同一套核心点逻辑，重算维护态质心和半径。

### 3. 多质心候选

为了不把异常对象直接过滤掉，多质心候选不只看过滤后的 `p90`，还会看：

- `raw_p90_radius_m`
- `max_spread_m`
- `core_outlier_ratio`
- `gps_anomaly_type`

### 4. 多质心分类

当前分类会结合：

- 稳定簇数
- 簇间最大距离
- 日期重叠天数
- 主次簇切换次数
- 次簇占比下限

当前次簇占比门槛已经加到：

- `classification_min_secondary_share = 0.15`

同时 `is_multi_centroid` 已与 `centroid_pattern` 对齐，不再仅靠 `stable_cluster_count >= 2` 粗打标。

## 当前仍未定稿的部分

工程闭环已经成立，但研究结论还没完全收口。

当前 `batch3` 的结果：

- `multi_centroid_cell_count = 113`
- `centroid_pattern` 分布：
  - `<null> = 9681`
  - `dual_cluster = 106`
  - `multi_cluster = 7`

这说明：

- 多质心已经不是“完全识别不出来”
- 但 `dual_cluster` 仍偏多，还需要继续研究是否过敏

## 当前判断

当前最稳妥的判断是：

1. 工程上，这一版已经可用，能稳定跑完 `batch1-3`
2. 性能上，`Step5 PostGIS` 的结构性瓶颈已经被打穿
3. 研究上，质心与多质心边界仍需继续收敛

## 后续建议

如果下一步继续：

1. 先基于当前版本扩到 `batch4-7` 做完整样例验证
2. 再根据 `batch4-7` 的 `dual_cluster / multi_cluster / moving / migration` 分布继续收紧口径

当前阶段不建议：

- 再把 donor 闭环和多质心研究混在一起改
- 再把 `Step5` 性能和分类边界混成同一轮处理
