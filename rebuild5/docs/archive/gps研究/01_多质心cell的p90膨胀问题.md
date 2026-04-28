# 多质心 Cell 的 p90 膨胀问题 — 初步研究

> 研究日期：2026-04-14
> 状态：初步结论，待策略汇总后统一修改

## 1. 问题发现

在 beijing_7d 数据集 batch 7 中，部分 cell 的 p90_radius_m 严重偏大，与主簇的真实定位精度不符。

### 样本 A：Cell 5731057665（单设备 GPS 漂移导致的假多质心）

| 指标 | 当前值 | 主簇实际 |
|------|--------|----------|
| p50 | 969m | 119.5m |
| p90 | 2587m | 168.6m |
| 膨胀倍数 | — | **~15x** |

- 主簇：(116.1785, 39.7093)，84 点 / 23 设备，真实半径 ~270m
- 污染源：单设备 `QYO4XIEPS2VXBVXVR`，114 个 GPS 点在 4.5km 外
- DBSCAN 分类：dual_cluster（但次簇实为单设备漂移）

### 样本 B：Cell 20209176582（真实双覆盖区）

| 指标 | 当前值 | 主簇实际 |
|------|--------|----------|
| p50 | 160m | 76.8m |
| p90 | 1919m | 391.4m |
| 膨胀倍数 | — | **~5x** |

- 主簇：(119.7341, 30.2159)，319 点 / 79 设备，DBSCAN 半径 797m
- 次簇：(119.7218, 30.2305)，148 点 / 42 设备，距主簇 1931m
- 次簇是真实覆盖区（42 设备、6 天均有观测）
- DBSCAN 分类：dual_cluster

## 2. 数据链路分析

### 当前计算流程

```
Step 5.0 window.py
  ├── cell_metrics_base: 全量 sliding_window 中位数 → center_lon/lat (粗)
  ├── cell_core_gps_stats: core filter (seed + keep_radius) → center_lon/lat (精)
  ├── cell_radius_stats: core 点到 core 中心的 P50/P90 → p50/p90
  └── cell_metrics_window: 合并以上 → 传给 publish

Step 5.3 publish_cell.py
  └── 从 cell_metrics_window 取 p50/p90 写入 trusted_cell_library

Step 5.3+ publish_bs_lac.py
  ├── DBSCAN 聚类 → 识别多簇
  ├── 主簇中心 → UPDATE library.center_lon/lat  ← 这步做了
  └── 主簇 p50/p90 → 没做，p50/p90 仍是 core filter 的全量值  ← 断裂点
```

### Core Filter 参数与问题

```yaml
core_position_filter:
  snap_grid_m: 200        # 种子网格
  keep_quantile: 0.8      # P80 分位
  keep_min_radius_m: 800  # 最小保留半径
  keep_max_radius_m: 3000 # 最大保留半径
```

对 Cell 5731057665：
- P80(距离) = 4723m → 截断到 3000m
- 保留 238/346 个点（排除 108 个 >3km 的极远点）
- 但 800-3000m 范围内的单设备漂移点仍被保留 → p90 膨胀

## 3. Step 4 → Step 5 反馈循环的断裂

### 设计意图

```
Step 5 计算质心 → 发布到 library
                        ↓
Step 4 用 library 质心做 GPS 异常检测 → gps_anomaly_log
                        ↓
Step 5 读 anomaly_log → 标记 gps_anomaly_type / antitoxin_hit
```

### 实际表现（Cell 5731057665）

| Batch | 异常设备 QYO4 点数 | Step 4 检出 | 进入 sliding_window | 参与质心计算 |
|-------|-------------------|-------------|--------------------|----|
| 2-5 | 不存在 | — | — | — |
| 6 | 80 条 | 42 条 (>2200m) | 全部 80 条 gps_valid=true | 是 |
| 7 | 151 条 | 102 条 (>2200m) | 全部 151 条 gps_valid=true | 是 |

**断裂点**：`gps_anomaly_log` 只用于统计标签（`gps_anomaly_type`, `antitoxin_hit`），不回写 `gps_valid`，不阻止点进入 sliding_window。

## 4. DBSCAN 多质心分析的现状

### 算法流程

1. 候选筛选：p90 ≥ 800m 或 max_spread ≥ 2200m 或有异常标记
2. 从 sliding_window 取 gps_valid 的 GPS 点
3. 50m 网格 snap → ST_ClusterDBSCAN(eps=250m, minpoints=4)
4. 簇过滤：obs ≥ 5, dev ≥ 2, active_days ≥ 2
5. 排名 → 分类 → 主簇质心回写 center_lon/lat

### 做得好的

- 正确识别了物理簇结构
- 单设备漂移点因 `dev_count < 2` 被过滤（Cell A 的 far_west 簇）
- 主簇中心回写到 library

### 缺失的

- **p50/p90 未从主簇重算** — 仍然使用 core filter 的全量值
- 因此即使 DBSCAN 正确识别了主簇，发布的精度指标仍然被噪声/次簇拉高

## 5. 初步结论

### 核心改进方向

**在 Step 5 的 DBSCAN 流程末尾，对 `is_multi_centroid = true` 的 cell，用主簇标记的点重算 p50/p90 并 UPDATE 回 library。**

理由：
1. DBSCAN 已经做了精确的簇分割，数据已有
2. 只需在 `publish_cell_centroid_detail` 末尾增加一个 UPDATE
3. 只影响多质心 cell（batch 7 中 5307 个），不改变单簇 cell 行为
4. 次簇信息保留在 `cell_centroid_detail`，不丢失

### 预期效果

| Cell | 当前 p90 | 主簇重算 p90 | 改善 |
|------|---------|-------------|------|
| 5731057665 (假多质心) | 2587m | 169m | 15x |
| 20209176582 (真多质心) | 1919m | 391m | 5x |

### 待研究的其他策略

以下策略需要进一步调研后统一决策：

1. **设备级权重/上限**：单设备最多贡献 N 个点，防止 GPS 漂移设备主导
2. **异常检测结果回写**：Step 4 检出的异常点是否应翻转 gps_valid
3. **Core filter 参数调优**：keep_max_radius_m 从 3000 降低
4. **HDBSCAN / OPTICS 替代 DBSCAN**：自适应密度聚类
5. **Weighted median**：基于设备多样性的加权中位数
6. **业界实践**：OpenCelliD 等众包基站定位项目的降噪策略

## 6. 两个样本的详细数据

### Cell 5731057665 — GPS 点空间分布

| 区域 | 点数 | 设备数 | 说明 |
|------|------|--------|------|
| core (116.16-116.183, 39.70-39.715) | 93 | 25 | 真实位置 |
| east (>116.183) | 47 | 13 | 邻近区域 |
| mid_north (39.715-39.725) | 61 | 3 | 少设备次簇 |
| north (>39.725) | 31 | 2 | 单设备为主 |
| far_west (<116.16) | 114 | **1** | 单设备漂移 |

污染设备 `QYO4XIEPS2VXBVXVR`：
- Batch 6 首次出现，80 条记录，GPS 均值 (116.1365, 39.6956)，距主簇 4.5km
- Batch 7 继续，151 条记录
- Step 4 分别检出 42 / 102 条异常（>2200m），但未阻止

### Cell 20209176582 — GPS 点空间分布

| 区域 | 点数 | 设备数 | 天数 |
|------|------|--------|------|
| 主簇 (≤800m) | 319 | 79 | 6 |
| 次簇 (≤1.2km) | 148 | 42 | 6 |
| 噪声 | 32 | 11 | 6 |

次簇特征：42 个独立设备、6 天均有观测、top 设备最多 19 点/4 天 — 确认为真实覆盖区。

两簇距离：1931m。
