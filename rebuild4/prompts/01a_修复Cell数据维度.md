# Step 01a: Cell 数据维度（样本模式）

## 前置条件
- ETL 已完成（`etl_filled` 表存在，687,788 条，66 列）
- 阅读 `99_系统上下文.md` 了解数据库结构和样本 LAC 定义
- 阅读 `docs/01_etl/00_总览.md` 了解 ETL 产出

## 工具要求
- 你必须使用 `PG17 MCP` 执行所有 SQL
- 你必须使用 Playwright 检查页面

## 目标

从 ETL 产出表 `rebuild4.etl_filled` 聚合计算 Cell 维度指标，与 rebuild2 画像数据对比验证。

Cell 是最小分析单元，每个 Cell 由 `(operator_code, lac, cell_id)` 唯一标识。

## 数据来源

**主表**：`rebuild4.etl_filled`（ETL 补齐后的最终产出）

关键字段映射：

| 用途 | 字段 | 说明 |
|------|------|------|
| 运营商 | `operator_filled` | 补齐后的运营商编码 |
| LAC | `lac_filled` | 补齐后的 LAC |
| CellID | `cell_id` | 小区标识（bigint） |
| 基站ID | `bs_id` | 派生字段，4G=cell_id/256, 5G=cell_id/4096 |
| 制式 | `tech_norm` | 4G/5G/2G/3G |
| 经度 | `lon_filled` | 补齐后的经度 |
| 纬度 | `lat_filled` | 补齐后的纬度 |
| GPS有效 | `gps_valid` | 经纬度在有效范围内 |
| RSRP | `rsrp_filled` | 补齐后的信号强度 |
| 设备ID | `dev_id` | 设备标识 |
| 上报时间 | `ts_std` | 标准化时间戳 |

**注意**：使用补齐后的字段（`*_filled`），而非原始字段。

**对比参考**：`rebuild4.sample_dim_cell`（rebuild2 产出）、`rebuild4.sample_cell_profile`（rebuild2 画像）

## 修复步骤

### 1.1 从 etl_filled 聚合 Cell 基础指标

```sql
-- 按 (operator, lac, cell_id) 聚合
SELECT
    operator_filled AS operator_code,
    lac_filled::text AS lac,
    bs_id::text AS bs_id,
    cell_id::text AS cell_id,
    tech_norm,
    COUNT(*) AS record_count,
    COUNT(*) FILTER (WHERE lon_filled IS NOT NULL) AS gps_valid_count,
    COUNT(DISTINCT dev_id) AS distinct_dev_id,
    EXTRACT(EPOCH FROM MAX(ts_std) - MIN(ts_std)) / 3600.0 AS observed_span_hours,
    COUNT(DISTINCT DATE(ts_std)) AS active_days,
    AVG(lon_filled) FILTER (WHERE lon_filled IS NOT NULL) AS gps_center_lon,
    AVG(lat_filled) FILTER (WHERE lat_filled IS NOT NULL) AS gps_center_lat,
    AVG(rsrp_filled) FILTER (WHERE rsrp_filled IS NOT NULL) AS rsrp_avg,
    COUNT(*) FILTER (WHERE lon_raw IS NOT NULL AND gps_valid)::numeric
        / NULLIF(COUNT(*), 0) AS gps_original_ratio,
    COUNT(*) FILTER (WHERE rsrp IS NOT NULL)::numeric
        / NULLIF(COUNT(*), 0) AS signal_original_ratio
FROM rebuild4.etl_filled
WHERE cell_id IS NOT NULL
GROUP BY operator_filled, lac_filled, bs_id, cell_id, tech_norm
```

### 1.2 计算 GPS P90 半径

```sql
-- 每个 Cell 的 GPS 点到中心的距离 P90
-- 使用曼哈顿距离近似：(|lon-center_lon|*85300 + |lat-center_lat|*111000)
PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY distance_m) AS p90_radius_m
```

### 1.3 GPS 异常检测

对比 rebuild2 的异常标记（`sample_dim_cell.gps_anomaly`），同时用以下规则自行判断：
- Cell 到所属 BS 中心距离过大（4G > 2000m，5G > 1000m）
- P90 半径 > 2500m

### 1.4 生命周期评估

| 状态 | 条件 |
|------|------|
| waiting | gps_valid_count < 10 或 distinct_dev_id < 2 |
| observing | 满足基本条件但不满足 anchorable |
| active | anchorable = true |

anchorable 条件：gps_valid_count >= 10, distinct_dev_id >= 2, p90_radius_m < 1500, observed_span_hours >= 24

## 验证

与 rebuild2 对比：
- record_count 差异 < 5%（因为 ETL 来源不同）
- GPS 中心坐标差异 < 100m（rebuild2 用分箱中位数，我们用 AVG）
- GPS 异常标记一致性 > 95%
- 生命周期分布合理

## UI

在 `docs/02_profile/` 下建文档。在前端画像页面展示 Cell 维度数据。

## 完成标志
- [ ] 从 etl_filled 聚合的 Cell 指标全部非空
- [ ] GPS 中心和 P90 半径计算完成
- [ ] 异常检测与 rebuild2 对比验证
- [ ] 生命周期状态基于规则计算
- [ ] 文档完成（docs/02_profile/01_cell.md）

## 完成后
继续执行 `01b_修复BS_LAC派生.md`
