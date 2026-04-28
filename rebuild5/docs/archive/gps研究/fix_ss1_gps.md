# Fix: ss1 解析未过滤 gps_info_type 导致非 GPS 坐标混入

> 发现日期：2026-04-14
> 状态：待修复
> 影响：etl_parsed → etl_cleaned → enriched_records → cell_sliding_window → 质心计算全链路

## 1. 问题描述

设计文档要求 `gps_valid = true` 仅限 `gps_info_type IN ('1', 'gps')`（原生 GPS），代码中 cell_infos 解析正确执行了此规则，但 **ss1 解析路径遗漏了该检查**，导致 ss1 来源的 type 2/4/5/null 记录只要有坐标就被标记为 gps_valid=true。

## 2. 代码定位

**文件**：`rebuild5/backend/app/etl/parse.py`

### cell_infos 解析（第 104 行）— 正确

```sql
CASE WHEN r."gps_info_type" IN ('gps','1') THEN true ELSE false END AS gps_valid
```

### ss1 解析（第 277 行）— 有问题

```sql
CASE WHEN c.gps_block != '0' AND c.gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN true ELSE false END AS gps_valid
```

只检查了 gps_block 是否有坐标格式，**没有检查 gps_info_type**。

### 清洗规则 ODS-013（clean.py 第 25 行）— 只补救了 cell_infos

```python
"where": "cell_origin = 'cell_infos' AND (gps_info_type IS NULL OR gps_info_type NOT IN ('gps', '1'))"
```

条件限定了 `cell_origin = 'cell_infos'`，ss1 来源不受此规则保护。

## 3. 影响数据量

### etl_parsed 阶段（ss1 来源被错误标记为 gps_valid=true）

| gps_info_type | gps_valid=true 数量 | 应为 |
|---|---|---|
| 5（网络定位） | 77,488 | false |
| null | 73,044 | false |
| 4（基站定位） | 44,297 | false |
| 2（WiFi定位） | 13,160 | false |
| **合计** | **207,989** | |

### etl_cleaned 阶段（经 fill 扩展后）

| gps_info_type | gps_valid=true 数量 |
|---|---|
| 5 | 548,011 |
| 4 | 290,644 |
| 2 | 93,660 |
| null | 463,909 |
| **合计** | **~1,396,224** |

注：etl_cleaned 中 null 类型的 463,909 条中也有一部分来自 ss1。

### 精度影响

在稳定 cell（p90 < 200m, 设备 > 20）上的误差对比：

| gps_info_type | median 误差 | p90 误差 | 评估 |
|---|---|---|---|
| 1（GPS） | 69m | 416m | 正常 |
| gps（GPS） | 70m | 761m | 正常 |
| 4（基站定位） | 46m | 565m | 偏大 |
| 2（WiFi） | 84m | **3,647m** | 严重 |
| 5（网络/IP定位） | 233m | **13,726m** | 极差 |

type 5 的 p90 误差达 **13.7km**，这些点以 gps_valid=true 进入了质心计算。

## 4. 修复方案

### 方案 A：修改 ss1 解析（推荐）

在 `parse.py` 第 277 行加入 gps_info_type 检查：

```sql
-- 修改前
CASE WHEN c.gps_block != '0' AND c.gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN true ELSE false END AS gps_valid

-- 修改后
CASE WHEN c.gps_info_type IN ('gps', '1')
      AND c.gps_block != '0'
      AND c.gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN true ELSE false END AS gps_valid
```

### 方案 B：扩展清洗规则 ODS-013

将 `cell_origin = 'cell_infos'` 条件去掉，使规则覆盖所有来源：

```python
-- 修改前
"where": "cell_origin = 'cell_infos' AND (gps_info_type IS NULL OR gps_info_type NOT IN ('gps', '1'))"

-- 修改后
"where": "gps_info_type IS NULL OR gps_info_type NOT IN ('gps', '1')"
```

### 建议

两个方案都做：方案 A 从源头阻断，方案 B 作为兜底。修复后需要重跑 Step 1（ETL），下游全部重算。

## 5. 验证方法

修复后检查：

```sql
-- 应该返回 0 行
SELECT gps_info_type, count(*)
FROM rebuild5.etl_cleaned
WHERE gps_valid = true
  AND gps_info_type NOT IN ('1', 'gps')
GROUP BY gps_info_type;
```
