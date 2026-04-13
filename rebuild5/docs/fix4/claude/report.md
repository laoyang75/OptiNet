# Fix4 Claude 研究报告

## 1. 当前逻辑问题是什么

### 1.1 Cell 覆盖面积（p90）严重膨胀

当前主链 `window.py:build_cell_radius_stats()` 计算 p90 时使用 **全量 GPS 点**，无任何异常过滤。少量离群点会极端拉大 p90：

- 40 个 focus cells 中，high_p90 组的 raw_p90 中位数为 **175,767m**（175km），最大 **1,083,739m**（1,083km）
- 但同组 p50 中位数仅 **91m** — 说明 90% 以上的点都在百米范围内

根因：GPS 噪声（跨城设备、WiFi 定位偏差、单设备持续远端上报）在计算 p90 时没有被排除。

### 1.2 碰撞检测 `_detect_absolute_collision` 结构性失效

`trusted_cell_library` 的 PK 是 `(batch_id, operator_code, lac, cell_id, tech_norm)`，不含 `bs_id`，每个组合只有一行。`COUNT(DISTINCT bs_id) > 1` 永远不成立。该检测**从未触发过**。

547 个 p90 > 50km 且不在 `collision_id_list` 中的 Cell 完全没被检测到。

### 1.3 DBSCAN 候选集遗漏 `large_coverage`

`antitoxin_params.yaml` 中 `candidate_drift_patterns` 不含 `large_coverage`，导致被分类为 `large_coverage` 的 Cell 无法进入多质心分析（除非碰巧有其他异常标记）。

### 1.4 面积失真传导到 BS 层

BS 质心取下属 Cell 质心的中位数，BS p90 取 Cell 到 BS 质心距离的 90 分位。当 Cell 质心被噪声拉偏或 Cell p90 膨胀时，BS 层面积被连带放大。

## 2. 如何修复

### 2.1 Core Position Filter（已在 window.py 中实现）

采用"主热点种子 + 自适应裁剪半径"的两阶段过滤方案：

1. **Seed Grid**: 将 GPS 点 snap 到 200m 网格，找到每个 Cell 观测最密的网格点作为 seed
2. **Distance**: 计算每个 GPS 点到 seed 的距离
3. **Adaptive Cutoff**: cutoff = `GREATEST(800, LEAST(p80_distance, 3000))`
   - 最小 800m: 防止对紧凑 Cell 过度裁剪
   - 最大 3000m: 确保极端噪声被过滤
   - p80 自适应: 对展布较大的 Cell 保留更多点
4. **Core Points**: 只保留 `dist_to_seed <= cutoff` 的点
5. **Refined Centroid + p90**: 从 core points 计算最终质心和 p90

### 2.2 碰撞检测修复

将 `_detect_absolute_collision`（结构性失效）替换为 `_detect_geographic_collision`：从 `cell_centroid_detail`（DBSCAN 结果）中查找稳定簇间距 >= 20km 的 Cell，标记为碰撞。

### 2.3 候选集修复

`candidate_drift_patterns` 增加 `large_coverage`。

## 3. 为什么修复后能解决覆盖面积过大

Core position filter 的核心逻辑是：**以最密网格点为锚点，只保留距锚点 p80 距离以内的点**。

- 对于主簇紧凑但有远端噪声的 Cell：cutoff = 800m，远端噪声全部被过滤
- 对于展布较大的真实覆盖 Cell：cutoff 自适应到 p80（最大 3000m），保留真实覆盖
- 过滤后的 p90 反映的是**主簇的真实覆盖范围**，不再被极端异常值拉大

关键证据：Batch 7 中 raw_p90 > 100km 的 17 个 Cell，过滤后 core_p90 平均仅 **255m**。

## 4. 修复后面积变化

### 全量 Cell（Batch 7，18,132 个 Cell）

| p90 分桶 | Cell 数 | 平均 raw_p90 | 平均 core_p90 | 降幅 |
|----------|---------|-------------|--------------|------|
| < 500m | 14,257 | 147m | 132m | -10% |
| 500-1500m | 2,285 | 833m | 391m | -53% |
| 1500-5000m | 892 | 2,730m | 477m | -83% |
| 5k-100km | 681 | 14,633m | 351m | -98% |
| > 100km | 17 | 450,792m | 255m | -99.9% |

### Focus Cells（40 个重点 Cell）

| 分组 | 平均 raw_p90 | 平均 core_p90 | 平均去除点数 |
|------|-------------|--------------|-------------|
| high_p90 (10) | 385,308m | 196m | 34.5 |
| high_obs (10) | 2,290m | 136m | 27.2 |
| moving (10) | 2,027m | 626m | 70.7 |
| multi_cluster (10) | 1,434m | 661m | 49.7 |

## 5. 修复后速度变化

### 7 批耗时（每批包含完整 core filter 流程）

| Batch | 窗口行数 | Cell 数 | 耗时 | 参考基线 |
|-------|---------|---------|------|---------|
| 1 | 274,837 | 13,306 | **4s** | — |
| 2 | 570,875 | 15,234 | **5s** | — |
| 3 | 844,197 | 16,135 | **18s** | 124s |
| 4 | 1,110,420 | 16,755 | **25s** | — |
| 5 | 1,374,614 | 17,290 | **30s** | 689s |
| 6 | 1,646,208 | 17,743 | **34s** | — |
| 7 | 1,937,395 | 18,132 | **40s** | — |

速度说明：
- 本测试只包含 core filter + cell library 构建，**不含** DBSCAN 多质心分析（独立步骤）
- 参考基线 batch 3 = 124s、batch 5 = 689s 包含完整 Step 5（含 DBSCAN）
- Core filter 本身仅占 Step 5 总耗时的一小部分

### 每步耗时分析（Batch 7 为例）

| 步骤 | 耗时估算 | 瓶颈原因 |
|------|---------|---------|
| Load window | ~3s | INSERT 291k 行 |
| Seed grid (PostGIS) | ~2s | ST_SnapToGrid + GROUP BY |
| Primary seed | <1s | DISTINCT ON |
| Seed distance (PostGIS) | ~5s | ST_Distance × 全量窗口 |
| Cutoff (PERCENTILE_CONT) | ~3s | p80 聚合 |
| Core points | ~2s | 距离过滤 JOIN |
| Core stats (PERCENTILE_CONT) | ~5s | 中位数质心 |
| Radius (PERCENTILE_CONT×2) | ~8s | p50 + p90 |
| Raw radius | ~5s | 对比用 |
| Assemble | <1s | JOIN + INSERT |

主要瓶颈是 **PERCENTILE_CONT** 和 **PostGIS ST_Distance/ST_Transform**，都是 CPU 密集型操作。

## 6. 还剩哪些问题没解决

### 6.1 DBSCAN 多质心分析未在本轮验证中运行

本轮验证了 core filter 的有效性和正确性，但没有在共享样例上实际运行 DBSCAN 多质心分析流程。DBSCAN 的 bug 修复（candidate_drift_patterns + geographic collision）已完成代码改动，但未在 7 批中端到端验证。

### 6.2 BS/LAC 发布策略

审计报告指出 BS/LAC 发布全部状态（含 observing），而 Cell 只发布 qualified+。经分析判定为**设计问题**而非 bug：BS 从已过滤 Cell 聚合，observing BS 代表下属 Cell 还不够成熟，保留它有治理价值。但建议确认这是否符合业务预期。

### 6.3 `large_coverage` 标签定义

`large_coverage` 需要分析但不是当前在线分类的第一优先级。Core filter 修复后，绝大多数 Cell 的 p90 已收敛到合理范围（< 1500m），`large_coverage` 的判定基准需要随之调整。

### 6.4 移动 Cell 的 core filter 可能过度裁剪

部分 moving cells 的 outlier 被 core filter 过滤后 p90 显著缩小（如 5710721027: 883m → 336m）。这对于真正的移动小区可能是过度裁剪。建议对已确认 `is_dynamic=true` 的 Cell 放宽 cutoff 或跳过 core filter。

### 6.5 窗口增长导致耗时线性增长

当前管道每批对全量窗口重新计算。随着窗口增长（batch 7 = 190 万行），seed_distance 和 radius 计算持续变慢。正式管道的窗口保鲜（14 天 trim + 1000 条最低保留）会控制窗口大小，但增量化 core filter（只对新增/变化 Cell 重算）是进一步优化方向。
