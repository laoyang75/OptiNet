# GPS 噪声过滤策略汇总 — 业界调研

> 研究日期：2026-04-14
> 来源：PostGIS 文档、Mozilla Ichnaea、OpenCelliD 论文、MDPI Sensors 论文等
> 目的：为 Step 5 质心精度改进提供策略选项，统一评估后再修改

---

## 一、鲁棒质心估计（替代简单中位数）

### 1. ST_GeometricMedian（几何中位数 / Weiszfeld 算法）

- **原理**：最小化到所有点距离之和（L1-median），而非距离平方和（L2/均值）。对离群点惩罚为线性而非二次，远比均值鲁棒
- **PostGIS**：直接可用 `ST_GeometricMedian(ST_Collect(geom))`，支持 M 值作为权重
- **最佳场景**：单质心 cell 有少量远距离离群
- **局限**：仍假设单质心，对真正多质心无效
- **SQL 示例**：
```sql
SELECT cell_id,
       ST_GeometricMedian(ST_Collect(geom)) AS robust_center
FROM observations
GROUP BY cell_id;
```

### 2. MAD 过滤（Median Absolute Deviation）

- **原理**：计算每点到中位数的距离，再取这些距离的中位数作为 MAD。阈值 = `median + k × MAD`（k 通常取 3），超出即离群
- **PostGIS**：手动 SQL 实现，用 `percentile_cont(0.5)` 计算中位数后筛选
- **最佳场景**：数据近似正态但有重尾
- **局限**：一维方法，需转换为距离

### 3. IQR / Tukey Fences

- **原理**：对距离计算 Q1/Q3，排除 `< Q1 - 1.5*IQR` 或 `> Q3 + 1.5*IQR` 的点
- **PostGIS**：纯 SQL 窗口函数
- **最佳场景**：快速粗筛
- **局限**：忽略空间关系，对多质心会误删合法点

### 4. 截断均值（Trimmed Mean）

- **原理**：排除最远 5-10% 的点后取均值
- **PostGIS**：SQL `PERCENT_RANK()` 后过滤
- **最佳场景**：简单，对少量离群有效
- **局限**：固定截断比例，无法自适应

---

## 二、聚类方法（处理多质心 + 分离噪声）

### 5. DBSCAN（当前已在用）

- **原理**：密度聚类，eps（邻域距离）+ minPoints 两参数，稀疏点标记为噪声
- **PostGIS**：`ST_ClusterDBSCAN(geom, eps, minpoints) OVER()`
- **当前配置**：eps=250m, minpoints=4, snap_grid=50m
- **优势**：天然分离噪声，多簇识别
- **局限**：eps 固定，不同 cell 最优 eps 可能不同

### 6. HDBSCAN（层次化 DBSCAN）

- **原理**：不需要固定 eps，自动适应不同密度，通过 cluster stability 提取最优聚类
- **最佳场景**：不同 cell 覆盖范围差异大时（城区小、郊区大），无需逐 cell 调参
- **局限**：PostGIS 无内置支持，需 Python (`hdbscan` 库) 或 PL/Python
- **评估**：效果可能优于 DBSCAN，但引入 Python 依赖，实施成本高

### 7. OPTICS

- **原理**：类似 DBSCAN 但生成可达性图谱，可在不同密度阈值下提取簇
- **局限**：不如 HDBSCAN 自动化，PostGIS 不支持
- **评估**：对我们场景 HDBSCAN 更适合，OPTICS 可跳过

### 8. 两阶段聚类法（行业推荐实践）

- **原理**：
  1. DBSCAN 粗分簇 + 去噪
  2. 对每个簇内用 Geometric Median 精确定位
- **最佳场景**：最通用的多质心场景，兼顾去噪和精度
- **PostGIS**：完全可实现（DBSCAN 分簇 → 按簇 ST_GeometricMedian）
- **参考**：论文中用于处理扇区天线的 120° 扇形覆盖
- **评估**：**非常适合我们的场景，且改动最小**

---

## 三、单设备 GPS 漂移检测

### 9. 速度阈值法

- **原理**：计算同一设备相邻两点的隐含速度 = 距离/时间差，超阈值即 GPS 跳点
- **Ichnaea 实践**：speed ≥ 50 m/s → weight=0 丢弃；5-50 m/s → 对数衰减
- **PostGIS**：`ST_Distance` + `LAG()` 窗口函数
- **评估**：我们的数据有 dev_id + event_time_std，可实现

### 10. 距离跳变检测

- **原理**：静止设备 GPS 突然跳 30-100m，超过缓冲区阈值即过滤
- **PostGIS**：`ST_DWithin()` 或距离计算
- **评估**：适合补充检测，但需要假设设备大致静止

### 11. GPS 精度半径过滤

- **原理**：GPS 报告的 accuracy 过大时降权或丢弃
- **Ichnaea 阈值**：Cell 1000m, WiFi 200m, Bluetooth 100m
- **评估**：我们的原始数据中没有 accuracy 字段，**不适用**

---

## 四、设备级加权与封顶

### 12. 每设备观测上限（Per-device Capping） ⭐

- **原理**：限制单设备对某 cell 贡献的最大观测数（如每设备最多 N 条）
- **实现**：`ROW_NUMBER() OVER (PARTITION BY cell_id, dev_id ORDER BY ...) <= N`
- **最佳场景**：众包数据中设备分布极不均匀时（如单设备贡献 33% 的点）
- **PostGIS**：极高，纯 SQL
- **评估**：**针对 Cell 5731057665 这类问题的直接解药**

### 13. 两层聚合（设备多样性加权）⭐

- **原理**：
  1. 第一层：每设备内聚合（取该设备的 geometric median）
  2. 第二层：设备间聚合（设备级质心再做 geometric median）
- **效果**：10 个设备各 1 条 ≈ 1 个设备 1000 条，天然去除单设备主导
- **PostGIS**：两层 SQL 聚合
- **评估**：**最优雅的解法之一，但改动较大**

### 14. Ichnaea 累积权重衰减

- **原理**：站点存储历史权重总和，新观测 / (历史 + 新) 计算位置调整比例，站点越成熟越稳定
- **最佳场景**：在线/增量更新
- **局限**：早期错误位置修正慢
- **评估**：我们是批量处理，不太适用

---

## 五、Ichnaea (Mozilla) 完整权重体系 — 行业参考

Ichnaea 的观测权重 = accuracy × age × speed × signal：

| 因子 | 满权重 (1.0) | 零权重 (丢弃) | 衰减方式 |
|------|-------------|-------------|---------|
| accuracy | ≤ 10m | ≥ 1000m(Cell) | 对数衰减 |
| age (采集到上报时差) | ≤ 2s | ≥ 20s | 对数衰减 |
| speed | ≤ 5 m/s | ≥ 50 m/s | 对数衰减 |
| signal | 平均信号强度 | 永不为 0 | 指数增减 |

其他机制：
- **移动站点阻断**：覆盖范围异常大 → 阻断 48h，频繁阻断 → 长期标记为移动站点
- **一致性检查**：多个观测互相验证
- **Cell Area 分组**：同 LAC 下 cell 组成区域，未知 cell 回退定位

---

## 六、策略适用性评估（结合我们的场景）

我们的特点：
- 数据源：众包 cell 信令（非 GPS 设备），有 lon/lat/dev_id/event_time/rsrp 等
- 处理方式：批量（每 batch 一天数据），滑动窗口 14 天
- 已有能力：DBSCAN 聚类、core filter、gps_anomaly_log
- 缺失字段：无 GPS accuracy

### 综合评估表

| 策略 | PostGIS 友好度 | 改动量 | 解决问题 | 优先级建议 |
|------|---------------|--------|---------|-----------|
| **主簇 p50/p90 重算** | 极高 | 小 | 多质心 cell p90 膨胀 | **P0** |
| **每设备 capping** | 极高 | 小 | 单设备主导质心 | **P1** |
| **两阶段法（DBSCAN + GeometricMedian）** | 高 | 中 | 簇内精度 + 抗离群 | **P2** |
| **两层聚合（设备内→设备间）** | 中 | 中 | 设备多样性加权 | P3 |
| **MAD/IQR 距离过滤** | 中 | 小 | 补充过滤中间距离离群 | P3 |
| **速度阈值** | 中 | 中 | 单设备 GPS 跳点 | P4 |
| **HDBSCAN** | 低 | 大 | 自适应密度聚类 | P5（长期） |
| **Ichnaea 多因子权重** | 中 | 大 | 综合质量评估 | P5（长期） |

### P0-P2 方案具体描述

**P0 — 主簇 p50/p90 重算（最小改动、立竿见影）**

在 `publish_cell_centroid_detail` 末尾，对 multi_centroid cell 用主簇标记点重算 p50/p90 并 UPDATE 回 library。已有 `_cell_centroid_labelled_points` 数据，只需增加一段 SQL。

**P1 — 每设备 capping**

在 `refresh_sliding_window` 或 `build_cell_metrics_base` 中，对每个 (cell_id, dev_id) 限制最多 N 条观测（如 N=20）。用 `ROW_NUMBER() OVER (PARTITION BY cell_id, dev_id ORDER BY event_time_std DESC) <= N` 过滤。

**P2 — 两阶段法增强**

将当前 DBSCAN 后的簇内质心从 `AVG(ST_X/Y)` 改为 `ST_GeometricMedian`，提高簇内抗离群能力。改动在 `_cell_centroid_cluster_base` 的聚合函数。

---

## 参考资料

- PostGIS: [ST_GeometricMedian](https://postgis.net/docs/ST_GeometricMedian.html), [ST_ClusterDBSCAN](https://postgis.net/docs/ST_ClusterDBSCAN.html)
- Crunchy Data: [PostGIS Clustering with DBSCAN](https://www.crunchydata.com/blog/postgis-clustering-with-dbscan)
- Mozilla Ichnaea: [Observations Algorithm](https://ichnaea.readthedocs.io/en/latest/algo/observations.html), [GitHub](https://github.com/mozilla/ichnaea)
- OpenCelliD: [Localizing Cell Towers from Crowdsourced Measurements (Master Thesis)](https://wiki.opencellid.org/images/e/ea/Localizing_Cell_Towers_from_Crowdsourced_Measurements_-_Johan_Alexander_Nordstrand_-_Master_Thesis.pdf)
- Diva Portal: [Cell Tower Localization using Crowdsourced Measurements (2024)](https://www.diva-portal.org/smash/get/diva2:1793709/FULLTEXT01.pdf)
- Rutgers: [Accuracy Characterization of Cell Tower Localization](https://www.winlab.rutgers.edu/~gruteser/papers/tower10.pdf)
- MDPI Sensors: [Crowdsourced Reconstruction of Cellular Networks](https://www.mdpi.com/1424-8220/23/1/352)
- PMC: [Big Data-Driven Cellular Information Detection](https://pmc.ncbi.nlm.nih.gov/articles/PMC6413000/)
- HDBSCAN: [How HDBSCAN Works](https://hdbscan.readthedocs.io/en/latest/how_hdbscan_works.html)
- MAD: [Using MAD to Find Outliers](https://eurekastatistics.com/using-the-median-absolute-deviation-to-find-outliers/)
- Mapscaping: [Spatial Clustering with PostGIS](https://mapscaping.com/examples-of-spatial-clustering-with-postgis/)
