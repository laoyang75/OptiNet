# GPS 质心计算方式调研建议

> 本文档保留质心计算方法论和改进方向，供后续优化参考。
> 原数据分析部分（基于修复前错误数据）已移除。

---

## 一、当前实现

### 1.1 单批次质心（Step 2 profile_base）

```sql
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon,
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat,
```

**当前方法 = 中位数（Median）**，对离群点完全免疫。

### 1.2 跨批次合并（Step 3 候选池）

```sql
center_lon = (c.center_lon * c.gps_valid_count + h.center_lon * h.gps_valid_count)
           / (c.gps_valid_count + h.gps_valid_count)
```

**跨批次方法 = 各批中位数按 gps_valid_count 加权平均**。

### 1.3 当前方法的特点

| 阶段 | 方法 | 抗噪性 | 信息利用率 |
|------|------|--------|-----------|
| 单批次 | 中位数 | 强（完全免疫离群点） | 中（丢弃了点的分布信息） |
| 跨批次 | 加权平均 | 中（依赖单批中位数质量） | 高（充分利用历史） |

---

## 二、方法对比

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 纯中位数 | 对离群点完全免疫 | 多批次加权时丢失单批信息 | 单批少量点 |
| 加权平均 | 充分利用所有历史信息，样本越多越稳定 | 极端离群点会拉偏质心 | 数据已清洁后 |
| 中位数 + 加权（当前） | 单批抗噪，跨批累积 | 若单批中位数本身被污染，则带入错误起点 | 当前主链 |
| **带距离过滤的加权平均** | 同时抗噪且充分利用信息 | 需要定义过滤半径 | **推荐改进方向** |

---

## 三、推荐改进方案：两阶段质心法

### 3.1 单批次改进

在 Step 2 `build_profile_base` 中，将质心计算从一次中位数改为两阶段：

```sql
-- Phase 1：用中位数算粗质心（抗离群）
WITH rough_center AS (
    SELECT 
        cell_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS rough_lon,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS rough_lat
    FROM profile_obs 
    WHERE lon IS NOT NULL AND lat IS NOT NULL
    GROUP BY cell_id
),

-- Phase 2：只保留距粗质心 3000m 以内的点，再算精确质心
filtered_obs AS (
    SELECT o.* 
    FROM profile_obs o
    JOIN rough_center r ON r.cell_id = o.cell_id
    WHERE SQRT(
        POWER((o.lon - r.rough_lon) * 85300, 2) + 
        POWER((o.lat - r.rough_lat) * 111000, 2)
    ) < 3000
),

-- Phase 3：过滤后的点做最终质心
final_center AS (
    SELECT cell_id,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat
    FROM filtered_obs
    GROUP BY cell_id
)
```

### 3.2 过滤半径的选择依据

**建议过滤半径：3000m**

理由：
- 优秀 Cell 的 p90 < 500m，说明正常 Cell 的 99% 观测点在 1000m 以内
- 合格 Cell 的 p90 < 1500m，99% 的真实点不会超过 3000m
- 3000m 是保守裕量，能过滤 >3km 的极端漂移点（如隧道/室内 GPS 回放、设备定位漂移）
- 超过 3000m 的 GPS 点几乎可以确定不是该 Cell 的真实覆盖范围

### 3.3 同时改进 p90 计算

两阶段过滤不仅改善质心，也改善 p90 计算：

```sql
-- 用过滤后的点重新算 p50/p90
SELECT cell_id,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dist) AS p50_radius_m,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY dist) AS p90_radius_m
FROM (
    SELECT cell_id,
           SQRT(POWER((lon - center_lon) * 85300, 2) + 
                POWER((lat - center_lat) * 111000, 2)) AS dist
    FROM filtered_obs
    JOIN final_center USING (cell_id)
) t
GROUP BY cell_id
```

这样 p90 不再被单个极端离群点污染。

---

## 四、跨批次合并改进建议

### 4.1 保持现有加权平均（合理）

当前跨批次加权平均是合理的，前提是单批质心已经通过两阶段法清洁。

### 4.2 增加质心漂移检验

当两批质心距离 > 5000m 时，可能是碰撞或真实迁移，不应简单加权平均：

```python
# 合并时，如果两批质心距离 > threshold，选择观测量更多的那批
distance = sqrt((c.center_lon - h.center_lon)^2 * 85300^2 + 
                (c.center_lat - h.center_lat)^2 * 111000^2)
if distance > 5000:
    # 选择 gps_valid_count 更大的一方，而不是加权平均
    use_winner = c if c.gps_valid_count > h.gps_valid_count else h
```

这也为 Step 5 的碰撞检测和迁移判定提供了前置信号。

---

## 五、实施优先级

| 优先级 | 改进项 | 复杂度 | 收益 |
|--------|--------|--------|------|
| P0 | Bug 1 修复（p90 加权平均代替 GREATEST） | 低 | 解除 3.2万 Cell 错误阻断 |
| P1 | 单批次两阶段质心法 + p90 过滤 | 中 | 从源头消除脏 GPS 对质心和 p90 的影响 |
| P2 | 跨批次质心漂移检验 | 低 | 识别碰撞/迁移场景 |

> P0 已包含在 `fix3/02_晋级规则与数据逻辑修复.md` 中。
> P1、P2 属于后续精度优化，不阻塞当前重跑。
