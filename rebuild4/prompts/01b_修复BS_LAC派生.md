# Step 01b: BS/LAC 派生（样本模式）

## 前置条件
- `01a` Cell 数据维度已完成
- 阅读 `99_系统上下文.md`

## 工具要求
- 你必须使用 `PG17 MCP` 执行所有 SQL
- 你必须使用 Playwright 检查页面

## 目标

BS 从 Cell 聚合派生，LAC 从 BS 聚合派生。层级关系：

```
LAC（位置区）
└── BS（基站）= cell_id / 256 (4G) 或 / 4096 (5G)
    └── Cell（小区）= 最小单元
```

## 数据来源

**Cell 维度表**：01a 步骤产出的 Cell 聚合结果
**对比参考**：`rebuild4.sample_dim_bs`、`rebuild4.sample_bs_profile`

## BS 派生（从 Cell 聚合）

### 2.1 基础指标

```sql
SELECT operator_code, lac, bs_id, tech_norm,
    COUNT(*) AS cell_count,
    COUNT(*) FILTER (WHERE lifecycle_state = 'active') AS active_cell_count,
    SUM(record_count) AS record_count,
    SUM(distinct_dev_id) AS total_devices,
    MAX(active_days) AS active_days,
    AVG(gps_center_lon) FILTER (WHERE gps_center_lon IS NOT NULL) AS gps_center_lon,
    AVG(gps_center_lat) FILTER (WHERE gps_center_lat IS NOT NULL) AS gps_center_lat,
    AVG(rsrp_avg) AS rsrp_avg,
    AVG(gps_original_ratio) AS gps_original_ratio,
    AVG(signal_original_ratio) AS signal_original_ratio
FROM cell_dimension  -- 01a 的产出
GROUP BY operator_code, lac, bs_id, tech_norm
```

### 2.2 BS GPS 精算

- GPS P50/P90：BS 下所有 Cell 的 GPS 中心到 BS 中心的距离分位数
- area_km2：BS 覆盖面积估算

### 2.3 BS 分类 (classification_v2)

从 `rebuild4.sample_bs_profile` 获取 rebuild2 的分类结果作为参考：
- `normal_spread`：正常分布
- `single_large`：单大覆盖
- `dynamic_bs`：动态基站（碰撞嫌疑）

同时用自有规则判断：设备交叉率高 + 面积大 → dynamic_bs

### 2.4 BS 生命周期

| 状态 | 条件 |
|------|------|
| active | active_cell_count > 0 |
| observing | 有 Cell 但无 active Cell |
| waiting | 无 Cell |

## LAC 派生（从 BS 聚合）

### 2.5 LAC 基础指标

```sql
SELECT operator_code, lac, tech_norm,
    COUNT(*) AS bs_count,
    COUNT(*) FILTER (WHERE lifecycle_state = 'active') AS active_bs_count,
    SUM(active_cell_count) AS active_cell_count,
    SUM(record_count) AS record_count,
    AVG(gps_center_lon) AS gps_center_lon,
    AVG(gps_center_lat) AS gps_center_lat,
    AVG(rsrp_avg) AS rsrp_avg,
    ROUND(COUNT(*) FILTER (WHERE health_state != 'healthy')::numeric / NULLIF(COUNT(*), 0), 4) AS anomaly_bs_ratio
FROM bs_dimension  -- 2.1 的产出
GROUP BY operator_code, lac, tech_norm
```

## 验证

与 rebuild2 对比：
- BS 的 active_cell_count 与 rebuild2 cell_count 接近
- classification_v2 一致
- LAC 聚合数字合理

## UI

画像页面展示 Cell/BS/LAC 三层数据。

## 完成标志
- [ ] BS 从 Cell 正确聚合
- [ ] BS 分类与 rebuild2 对比验证
- [ ] LAC 从 BS 正确聚合
- [ ] 文档完成（docs/02_profile/02_bs.md, 03_lac.md）

## 完成后
继续执行 `02_修复初始化11步.md`
