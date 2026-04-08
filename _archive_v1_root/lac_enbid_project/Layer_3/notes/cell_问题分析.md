# Cell GPS 漂移问题分析报告

## 1. 问题背景

**分析对象**：`cell_id = 5694423043` (cell_id_hex = 1536A0003)

**问题描述**：
- 该 cell 的 GPS 点存在严重漂移，所有有效 GPS 点距离中心点均超过 2 公里
- 在去除 >50km 极端值后，20-50km 范围内仍存在大量分散的 GPS 点
- 需要判断是**站址搬迁**还是**碰撞/混桶**问题

**数据来源**：`public."Y_codex_Layer0_Lac"`

---

## 2. 基础统计

### 2.1 总体情况

| 指标 | Raw GPS | Final GPS | Final GPS (did去重) | Final GPS (坐标去重) |
|------|---------|-----------|---------------------|---------------------|
| **记录数** | 325 | 326 | 95 | 216 |
| **最小距离(m)** | 2,116.81 | 2,052.35 | 2,972.62 | 2,052.35 |
| **最大距离(m)** | 192,430.31 | 192,491.85 | 132,565.91 | 192,491.85 |
| **平均距离(m)** | 25,409.93 | 25,523.03 | 25,465.74 | 24,488.64 |
| **中位数距离(m)** | 26,796.76 | 26,877.41 | 28,513.44 | 21,037.76 |
| **P90距离(m)** | 39,233.18 | 39,337.77 | 37,532.32 | 39,336.77 |

### 2.2 中心点分析

| 中心点类型 | 经度 | 纬度 | 50km内点数 | 50km外点数 |
|-----------|------|------|-----------|-----------|
| **原始中心点** | 116.5543° | 39.8534° | 317 | 9 |
| **去掉>50km后新中心点** | 116.5373° | 39.8578° | - | - |
| **中心点偏移距离** | - | - | **1,533.93 米** | - |

**结论**：极端值（>50km）对中心点影响有限（约 1.5km 偏移），但去掉后统计指标略有改善。

### 2.3 半径分布（去掉>50km后新中心点）

| 半径范围 | 记录数 | 占比(%) | 最小距离(m) | 最大距离(m) | 平均距离(m) |
|---------|--------|---------|------------|------------|-------------|
| 1-2km | 1 | 0.31 | 1,575.87 | 1,575.87 | 1,575.87 |
| 2-5km | 9 | 2.76 | 3,013.43 | 4,975.14 | 4,650.83 |
| 5-10km | 60 | 18.40 | 5,063.71 | 9,657.69 | 6,688.97 |
| 10-20km | 70 | 21.47 | 10,017.81 | 18,851.14 | 15,558.04 |
| 20-50km | 177 | 54.29 | 20,043.62 | 49,470.76 | 32,537.75 |
| 50-100km | 4 | 1.23 | 51,426.86 | 84,754.69 | 62,293.17 |
| >100km | 5 | 1.53 | 104,594.21 | 191,886.59 | 136,415.35 |

**关键发现**：
- 97% 的点距离中心点超过 2km
- 54% 的点集中在 20-50km 范围内
- 问题主要来自大量 20-50km 范围内的点，而非少数极端值

---

## 3. 多质心分析方法

### 3.1 方法概述

**目标**：在去除极端值（>50km）后，分析 20-50km 范围内是否存在多个中心点，并判断是搬迁还是碰撞。

**步骤**：
1. 过滤数据：去除 >50km 的极端值
2. 提取范围：聚焦 20-50km 范围内的 GPS 点
3. 聚类分析：使用四分位数方法进行空间聚类
4. 时间分析：分析各聚类的时间分布特征
5. 综合判断：基于空间和时间特征判断问题类型

### 3.2 聚类算法

#### 方法：基于四分位数的空间聚类

```sql
-- 1. 计算20-50km范围内GPS点的经纬度四分位数
WITH cluster_seeds AS (
  SELECT 
    percentile_cont(0.25) WITHIN GROUP (ORDER BY lon) as lon_q25,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) as lon_q50,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY lon) as lon_q75,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY lat) as lat_q25,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) as lat_q50,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY lat) as lat_q75
  FROM range_20_50km
)

-- 2. 将点分配到4个聚类区域
CASE 
  WHEN lon <= lon_q25 AND lat <= lat_q25 THEN 'Cluster_1'
  WHEN lon <= lon_q50 AND lat <= lat_q50 AND NOT (lon <= lon_q25 AND lat <= lat_q25) THEN 'Cluster_2'
  WHEN lon <= lon_q75 AND lat <= lat_q75 AND NOT (lon <= lon_q50 AND lat <= lat_q50) THEN 'Cluster_3'
  ELSE 'Cluster_4'
END as cluster_id
```

**优点**：
- 简单高效，适合大数据量
- 不需要预设聚类数量
- 能识别主要的空间聚集区域

**局限性**：
- 假设聚类呈矩形分布
- 可能无法识别复杂形状的聚类

### 3.3 聚类中心计算

对每个聚类，计算其中心点：

```sql
SELECT 
  cluster_id,
  AVG(lon) as center_lon,
  AVG(lat) as center_lat,
  COUNT(*) as point_count
FROM points_with_cluster
GROUP BY cluster_id
```

### 3.4 聚类间距离计算

使用 Haversine 公式计算聚类中心点之间的距离：

```sql
6371000 * acos(
  LEAST(1.0, 
    cos(radians(c1.center_lat)) * 
    cos(radians(c2.center_lat)) * 
    cos(radians(c2.center_lon - c1.center_lon)) + 
    sin(radians(c1.center_lat)) * 
    sin(radians(c2.center_lat))
  )
) as dist_m
```

---

## 4. 多质心分析结果

### 4.1 聚类识别

在去除 >50km 极端值后，20-50km 范围内识别出 **4 个主要聚类**：

| 聚类ID | 中心经度 | 中心纬度 | 点数 | 占比(%) | 首次出现 | 最后出现 | 活跃天数 |
|--------|---------|---------|------|---------|----------|----------|----------|
| **Cluster_4** | 116.6665° | 39.9111° | 83 | 47.70% | 2025-11-30 | 2025-12-06 | 7天 |
| **Cluster_3** | 116.8783° | 39.8000° | 46 | 26.44% | 2025-11-30 | 2025-12-06 | 7天 |
| **Cluster_1** | 116.1342° | 39.7340° | 38 | 21.84% | 2025-12-03 | 2025-12-06 | 4天 |
| **Cluster_2** | 116.3348° | 39.7411° | 7 | 4.02% | 2025-12-01 | 2025-12-06 | 4天 |

### 4.2 聚类间距离

| 聚类对 | 距离(km) |
|--------|---------|
| Cluster_1 ↔ Cluster_2 | 17.2 |
| Cluster_3 ↔ Cluster_4 | 21.9 |
| Cluster_2 ↔ Cluster_4 | 34.0 |
| Cluster_2 ↔ Cluster_3 | 46.9 |
| Cluster_1 ↔ Cluster_4 | 49.5 |
| Cluster_1 ↔ Cluster_3 | 64.0 |

**结论**：各聚类中心相距 17-64 公里，确认为不同的中心点。

### 4.3 时间分布分析

#### 按日期各聚类的分布：

| 日期 | Cluster_1 | Cluster_2 | Cluster_3 | Cluster_4 | 当日总点数 |
|------|-----------|-----------|-----------|-----------|-----------|
| 11-30 | 0 | 0 | 5 | 14 | 19 |
| 12-01 | 0 | 1 | 8 | 24 | 33 |
| 12-02 | 0 | 0 | 12 | 25 | 37 |
| 12-03 | 3 | 0 | 9 | 7 | 19 |
| 12-04 | 3 | 4 | 5 | 2 | 14 |
| 12-05 | **22** | 1 | 4 | 4 | 31 |
| 12-06 | 10 | 1 | 3 | 7 | 21 |

#### 时间特征统计：

| 聚类ID | 总点数 | 活跃天数 | 峰值比 | 时间特征判断 |
|--------|--------|----------|--------|-------------|
| Cluster_4 | 83 | 7天 | 2.11 | 时间分布中等 |
| Cluster_3 | 46 | 7天 | 1.83 | **时间分散(可能碰撞)** |
| Cluster_1 | 38 | 4天 | 2.32 | 时间分布中等 |
| Cluster_2 | 7 | 4天 | 2.29 | 时间分布中等 |

**峰值比** = 最大单日点数 / 平均每日点数

---

## 5. 判断逻辑：搬迁 vs 碰撞

### 5.1 判断标准

#### 站址搬迁的特征：
1. **时间序列性**：不同中心点按时间顺序出现，存在明显的时间分界
2. **时间集中**：每个中心点的数据集中在特定时间段
3. **时间不重叠**：不同中心点的时间段基本不重叠或重叠很少
4. **空间连续性**：中心点之间可能存在一定的空间关联（搬迁路径）

#### 碰撞/混桶的特征：
1. **时间重叠**：多个中心点同时存在，时间分布重叠
2. **时间分散**：各中心点的数据在时间上分散分布
3. **空间离散**：中心点之间距离较远，无明显空间关联
4. **无明显时间分界**：无法找到清晰的时间分界点

### 5.2 本案例判断

#### 证据支持"碰撞/混桶"：

1. **多中心同时存在**
   - Cluster_3 和 Cluster_4 从 11-30 持续到 12-06，时间完全重叠
   - 7 天观测期内，多个聚类同时存在

2. **时间分布分散**
   - Cluster_3 峰值比 1.83，7 天均有数据，无明显时间集中
   - Cluster_4 峰值比 2.11，时间分布相对均匀

3. **空间距离大**
   - 各聚类中心相距 17-64 公里，远超正常 cell 覆盖范围
   - 无明显空间连续性

#### 部分证据支持"搬迁"：

1. **Cluster_1 出现较晚**
   - 12-03 首次出现，12-05 达到峰值（22 点）
   - 但与其他聚类存在时间重叠（12-03 至 12-06）

### 5.3 最终判断

**结论：更倾向于碰撞/混桶**

**理由**：
1. 主要聚类（Cluster_3、Cluster_4）时间重叠且分散，不符合搬迁的时间序列特征
2. 空间上存在多个相距较远的中心点（17-64km），更可能是不同基站的数据混入
3. Cluster_1 虽然出现较晚，但与其他聚类存在时间重叠，更像是另一个碰撞源而非搬迁

---

## 6. 建议与后续处理

### 6.1 数据质量检查

1. **检查 bs_id 分布**：各聚类是否对应不同的 bs_id
2. **检查 lac 分布**：是否存在多 LAC 映射异常
3. **检查 cell_id 映射**：是否存在 cell_id 映射错误

### 6.2 处理策略

1. **按聚类分别处理**：不要使用单一中心点，而是按聚类分别计算中心点
2. **数据过滤**：如果确认是碰撞，考虑过滤掉明显不属于该 cell 的数据
3. **标记异常**：在数据中标记此类异常 cell，后续处理时特殊对待

### 6.3 方法优化

1. **改进聚类算法**：可以尝试 K-means 或 DBSCAN 等更精确的聚类方法
2. **时间窗口分析**：按时间窗口分析，识别是否存在时间分界
3. **多维度验证**：结合 bs_id、lac、信号强度等多维度信息进行验证

---

## 7. SQL 查询模板

### 7.1 基础过滤与中心点计算

```sql
-- 步骤1：过滤极端值，计算新中心点
WITH filtered_data AS (
  SELECT 
    l.lon,
    l.lat,
    l.ts_std,
    l."记录id",
    (6371000 * acos(
      LEAST(1.0, 
        cos(radians(c.center_lat)) * 
        cos(radians(l.lat)) * 
        cos(radians(l.lon - c.center_lon)) + 
        sin(radians(c.center_lat)) * 
        sin(radians(l.lat))
      )
    )) as dist_m
  FROM public."Y_codex_Layer0_Lac" l
  CROSS JOIN (
    SELECT 
      AVG(lon) as center_lon,
      AVG(lat) as center_lat
    FROM public."Y_codex_Layer0_Lac"
    WHERE cell_id_dec = <cell_id>
      AND lon IS NOT NULL 
      AND lat IS NOT NULL
  ) c
  WHERE l.cell_id_dec = <cell_id>
    AND l.lon IS NOT NULL 
    AND l.lat IS NOT NULL
    AND (6371000 * acos(
      LEAST(1.0, 
        cos(radians(c.center_lat)) * 
        cos(radians(l.lat)) * 
        cos(radians(l.lon - c.center_lon)) + 
        sin(radians(c.center_lat)) * 
        sin(radians(l.lat))
      )
    )) <= 50000
),
filtered_center AS (
  SELECT 
    AVG(lon) as center_lon,
    AVG(lat) as center_lat
  FROM filtered_data
  WHERE dist_m <= 50000
)
```

### 7.2 聚类分析

```sql
-- 步骤2：提取20-50km范围，进行聚类
WITH range_20_50km AS (
  SELECT 
    lon,
    lat,
    ts_std,
    "记录id",
    dist_m
  FROM filtered_data
  WHERE dist_m >= 20000 AND dist_m <= 50000
),
cluster_seeds AS (
  SELECT 
    percentile_cont(0.25) WITHIN GROUP (ORDER BY lon) as lon_q25,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) as lon_q50,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY lon) as lon_q75,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY lat) as lat_q25,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) as lat_q50,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY lat) as lat_q75
  FROM range_20_50km
),
points_with_cluster AS (
  SELECT 
    r.*,
    CASE 
      WHEN r.lon <= s.lon_q25 AND r.lat <= s.lat_q25 THEN 'Cluster_1'
      WHEN r.lon <= s.lon_q50 AND r.lat <= s.lat_q50 AND NOT (r.lon <= s.lon_q25 AND r.lat <= s.lat_q25) THEN 'Cluster_2'
      WHEN r.lon <= s.lon_q75 AND r.lat <= s.lat_q75 AND NOT (r.lon <= s.lon_q50 AND r.lat <= s.lat_q50) THEN 'Cluster_3'
      ELSE 'Cluster_4'
    END as cluster_id
  FROM range_20_50km r
  CROSS JOIN cluster_seeds s
)
```

### 7.3 时间分析

```sql
-- 步骤3：时间分布分析
WITH daily_cluster_dist AS (
  SELECT 
    DATE(ts_std) as report_date,
    cluster_id,
    COUNT(*) as daily_count
  FROM points_with_cluster
  WHERE ts_std IS NOT NULL
  GROUP BY DATE(ts_std), cluster_id
),
cluster_time_analysis AS (
  SELECT 
    cluster_id,
    COUNT(DISTINCT report_date) as active_days,
    MIN(report_date) as first_date,
    MAX(report_date) as last_date,
    SUM(daily_count) as total_points,
    ROUND(AVG(daily_count)::numeric, 2) as avg_daily_points,
    MAX(daily_count) as max_daily_count,
    ROUND((MAX(daily_count)::numeric / NULLIF(AVG(daily_count), 0))::numeric, 2) as peak_ratio
  FROM daily_cluster_dist
  GROUP BY cluster_id
)
SELECT 
  cluster_id,
  total_points,
  active_days,
  first_date,
  last_date,
  peak_ratio,
  CASE 
    WHEN peak_ratio > 3 AND active_days < 5 THEN '时间集中(可能搬迁)'
    WHEN active_days > 5 AND peak_ratio < 2 THEN '时间分散(可能碰撞)'
    ELSE '时间分布中等'
  END as time_feature
FROM cluster_time_analysis
ORDER BY total_points DESC;
```

---

## 8. 使用说明

### 8.1 适用范围

本方法适用于：
- GPS 漂移严重的 cell（中位数距离 > 10km）
- 需要判断是搬迁还是碰撞的场景
- 数据量较大（>100 条记录）的 cell

### 8.2 参数调整

可以根据实际情况调整以下参数：
- **极端值阈值**：默认 50km，可根据实际情况调整
- **分析范围**：默认 20-50km，可调整为其他范围
- **聚类数量**：默认 4 个，可根据数据分布调整
- **峰值比阈值**：用于判断时间集中度，默认 3.0

### 8.3 结果解读

1. **聚类数量**：如果只有 1-2 个主要聚类，可能是搬迁；如果 3+ 个聚类，更可能是碰撞
2. **时间分布**：时间集中（峰值比 > 3）且不重叠，可能是搬迁；时间分散且重叠，可能是碰撞
3. **空间距离**：聚类间距离 < 10km，可能是搬迁；> 20km，更可能是碰撞

---

## 9. 后续工作

1. **批量分析**：使用相同方法分析其他问题 cell
2. **方法优化**：根据批量分析结果优化聚类算法和判断标准
3. **自动化**：将分析方法封装为函数或脚本，便于批量处理
4. **验证**：通过人工验证部分结果，评估方法准确性

---

**创建时间**：2025-12-24  
**分析方法版本**：v1.0  
**分析对象**：cell_id = 5694423043


