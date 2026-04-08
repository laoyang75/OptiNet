# Cell 画像 — 管道详解

## 输入

`rebuild4.etl_filled` — 687,788 条, 66 列

## 产出

`rebuild4.etl_dim_cell` — 21,898 个 Cell

## 独立观测点

核心概念：按 `(cell_id, minute)` 去重，同一分钟内的多条上报合并为一个点。

- 不含设备维度（设备上报是脉冲式，98% 间隔 < 5 分钟，设备维度无区分力）
- 1 分钟窗口 vs 1 小时窗口增加 21.6% 观测点，碰撞检出更多且经验证为真发现

## 质心算法

**中位数**（PERCENTILE_CONT 0.5），不用 AVG。

实测精度对比（1,752 Cell vs rebuild2）：
- 中位数: 偏差中位 8.6m
- AVG: 偏差中位 61.4m（差 7 倍）

中位数天然抗碰撞、抗噪声，对散布型 Cell 优势达 70 倍。

## 质量分级

| 等级 | 条件 | 覆盖率 | 精度(100m内) |
|------|------|--------|-------------|
| 优秀 | >= 8 obs + >= 3 设备 + P90 < 500m | 11.5% | 94.5% |
| 良好 | >= 3 obs + >= 2 设备 | 17.7% | 93.2% |
| 合格 | >= 1 obs | 68.5% | 93.4% |
| 不合格 | 0 obs | 2.3% | - |

## 漂移分类

基于 7 天日质心（当天 >= 3 个独立观测点），计算任意两天最大距离和首末净漂移。

| 类型 | 判定规则 | 数量 | 说明 |
|------|---------|------|------|
| stable | max_spread < 500m | 2,675 | 位置稳定 |
| collision | >2km, net/max<0.3 | 23 | CellID 碰撞，来回跳 |
| low_collision | 500m-2km, net/max<0.2 | 45 | 低级碰撞 |
| migration | >2km, net/max>0.7, 多设备 | 30 | 搬迁 |
| dynamic | >2km, net/max>0.7, <=3设备 | 4 | 动态(火车/移动基站) |
| large_coverage | 500m-2km, net/max>0.7, >5设备 | 61 | 大覆盖正常 |
| moderate_drift | 其他 500m-2km | 59 | 待观察 |
| insufficient | <2天质心 | 19,001 | 数据不足 |

### 碰撞分析结论

- PCI 和 freq_channel 在两个位置完全相同，无法通过射频参数区分
- 远端全部只有 1 台设备，近端多台 → 可用设备数投票确定主位置
- ss1 来源的 GPS 全在正常位置，碰撞只出现在 cell_infos 中

## 规模评估

| 等级 | 条件 | 数量 |
|------|------|------|
| major | >= 50 obs + >= 10 设备 | 508 |
| large | >= 20 obs + >= 5 设备 | 880 |
| medium | >= 10 obs + >= 3 设备 | 1,281 |
| small | >= 3 obs | 5,142 |
| micro | < 3 obs | 14,087 |

## 生命周期

| 状态 | 条件 | 数量 |
|------|------|------|
| active | >= 3 obs, >= 2 设备, P90<1500, span>=24h, 非碰撞 | 5,801 |
| observing | 基本条件满足但不满足 active | 597 |
| waiting | < 3 obs 或 < 2 设备 | 15,500 |

## 位置映射

使用 `rebuild2.dim_admin_area`（2,874 区县中心点），CROSS JOIN LATERAL 找最近区县。

## 完整字段清单

| 分组 | 字段 | 说明 |
|------|------|------|
| 维度键 | operator_code, operator_cn, lac, bs_id, cell_id, tech_norm | |
| 基础统计 | record_count, gps_valid_count, gps_original_count, distinct_dev_id, observed_span_hours, active_days | 原始记录级 |
| 独立观测 | independent_obs, independent_devs, independent_days | 1min 去重 |
| 质心 | center_lon, center_lat, p50_radius_m, p90_radius_m, dist_to_bs_m | 中位数法 |
| 信号 | rsrp_avg, rsrq_avg, sinr_avg | |
| 数据质量 | gps_original_ratio, gps_valid_ratio, signal_original_ratio, signal_valid_ratio | |
| 漂移 | drift_pattern, drift_max_spread_m, drift_net_m, drift_days | 日质心分析 |
| 分级 | position_grade, gps_confidence, signal_confidence, cell_scale | |
| 标记 | is_collision, is_dynamic, lifecycle_state, anchorable | |
| 位置 | province_name, city_name, district_name | |
