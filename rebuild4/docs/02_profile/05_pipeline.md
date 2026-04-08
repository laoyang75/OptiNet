# 画像构建管道 — 实现说明

## 做什么

`profile.py` 是画像管道的代码实现。从 `etl_filled` 出发，6 步构建完整的 Cell / BS / LAC 画像表。

SQL 驱动，Python 编排——和 ETL 的 `pipeline.py` 同一风格。

## 为什么不需要初始化

流式评估实验（详见 `06_流式评估.md`）证明：逐天累积的流式结果与全量批量计算**数学等价**：
- Day 7 质心偏差 = **0.00m**
- 生命周期一致率 = **98.9%**

因此删除了原来的 11 步初始化流程，直接用画像管道全量构建。

## 6 步管道

```
etl_filled (688K 条, 66 列)
    │
    ▼
┌─────────────────────────────────┐
│ Step 1: 独立观测点                │
│                                   │
│ 去重 key: (cell_id, minute)      │
│ 每分钟多条报文 → 1 个观测点      │
│ GPS 仅用原始有效值 (中国边界)     │
│ 信号仅用合理范围                  │
│                                   │
│ 产出: _pf_obs (158K 条)          │
└──────────────┬────────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Step 2: Cell 质心 + P50/P90      │
│                                   │
│ 2a: 中位数质心 PERCENTILE_CONT   │
│     (0.5), 不用 AVG              │
│ 2b: 独立设备数 (从原始数据去重)   │
│ 2c: P50/P90 半径 (距质心百分位)   │
│ 2d: BS 质心 → Cell→BS 距离       │
│                                   │
│ 产出: _pf_cell_centroid (20K 条) │
│       _pf_cell_radius            │
│       _pf_bs_center              │
└──────────────┬────────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Step 3: 漂移分析                  │
│                                   │
│ 3a: 每日质心 (按天聚合)           │
│ 3b: 漂移指标:                    │
│   · max_spread: 日质心最大跨度    │
│   · net_drift: 首尾距离           │
│   · ratio: net / max_spread      │
│ 3c: 分类:                        │
│   · collision: >=2.2km, ratio<0.3│
│   · stable: <500m                │
│   · migration: >=2.2km, ratio>0.7│
│   · large_coverage: 500m-2.2km   │
│   · moderate_drift: 其他          │
│   · insufficient: <2 天           │
│                                   │
│ 产出: _pf_cell_drift (20K 条)    │
└──────────────┬────────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Step 4: 组装 Cell 画像            │
│                                   │
│ 合并质心/半径/漂移/设备数         │
│ 计算:                            │
│ · position_grade (4 级)          │
│ · gps/signal_confidence (4 级)   │
│ · cell_scale (5 级)              │
│ · is_collision / is_dynamic      │
│ · lifecycle_state                │
│ · anchorable                     │
│ · 地理映射 (join sample_cell_profile)│
│                                   │
│ 产出: etl_dim_cell (20,394 条)   │
│  → active 5,920 / observing 607  │
│  → waiting 13,867                │
└──────────────┬────────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Step 5: BS 画像                   │
│                                   │
│ 从 etl_dim_cell 按 bs_id 聚合:   │
│ · 质心 = Cell 质心的中位数         │
│ · P50/P90 = Cell→BS 距离百分位    │
│ · classification: collision_bs /  │
│   dynamic_bs / large_spread /     │
│   normal_spread                   │
│ · lifecycle: 有 active Cell → active│
│                                   │
│ 产出: etl_dim_bs (11,942 条)     │
└──────────────┬────────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ Step 6: LAC 画像                  │
│                                   │
│ 从 etl_dim_bs 按 lac 聚合:       │
│ · 质心 = BS 质心的中位数          │
│ · anomaly_bs_ratio               │
│ · lifecycle: 有 active BS → active│
│                                   │
│ 产出: etl_dim_lac (1,270 条)     │
└─────────────────────────────────┘
```

最后清理所有 `_pf_*` 中间表。

## 生命周期判定规则

| 状态 | 条件 |
|------|------|
| `waiting` | independent_obs < 3 **或** distinct_dev_id < 2 |
| `active` | obs >= 3 且 devs >= 2 且 P90 < 1500m 且 span >= 24h 且非 collision |
| `observing` | 以上都不满足 |

## 锚点资格 (anchorable)

同时满足以下 5 条：
1. gps_valid_count >= 10
2. distinct_dev_id >= 2
3. p90_radius_m < 1500
4. observed_span_hours >= 24
5. drift_pattern != 'collision'

## 分级规则速查

### position_grade

| 等级 | 条件 |
|------|------|
| excellent | obs >= 8, devs >= 3, P90 < 500m |
| good | obs >= 3, devs >= 2 |
| qualified | obs >= 1 |
| unqualified | gps_valid = 0 |

### cell_scale

| 等级 | 条件 |
|------|------|
| major | obs >= 50, devs >= 10 |
| large | obs >= 20, devs >= 5 |
| medium | obs >= 10, devs >= 3 |
| small | obs >= 3 |
| micro | obs < 3 |

### gps_confidence

| 等级 | 条件 |
|------|------|
| high | gps_valid >= 20, devs >= 3 |
| medium | gps_valid >= 10, devs >= 2 |
| low | gps_valid >= 1 |
| none | gps_valid = 0 |

## 硬编码阈值清单

以下阈值当前写死在 `profile.py` 的 SQL 中：

| 阈值 | 值 | 用途 | 所在步骤 |
|------|-----|------|---------|
| GPS 有效经度 | 73 ~ 135 | 中国边界过滤 | Step 1 |
| GPS 有效纬度 | 3 ~ 54 | 中国边界过滤 | Step 1 |
| RSRP 范围 | -156 ~ 0 | 信号合理性 | Step 1 |
| 经度→米系数 | 85,300 | 距离计算 (北京) | Step 2/3 |
| 纬度→米系数 | 111,000 | 距离计算 | Step 2/3 |
| collision 阈值 | 2,200m | 碰撞判定 | Step 3 |
| stable 阈值 | 500m | 稳定判定 | Step 3 |
| collision ratio | < 0.3 | 碰撞比率 | Step 3 |
| P90 active 门槛 | 1,500m | 生命周期 | Step 4 |
| 观测跨度门槛 | 24h | 生命周期 | Step 4 |
| obs 最低要求 | 3 | waiting→observing | Step 4 |
| devs 最低要求 | 2 | waiting→observing | Step 4 |
| anchorable GPS | 10 | 锚点资格 | Step 4 |
| BS 距离异常 | 2,500m | BS 分类 | Step 5 |

## 中间表

全部使用 `rebuild4._pf_*` 前缀，运行结束后自动 DROP：

| 表 | 用途 | 估计行数 |
|----|------|---------|
| `_pf_obs` | 分钟级独立观测 | ~158K |
| `_pf_cell_centroid` | Cell 质心 + 基础统计 | ~20K |
| `_pf_cell_devs` | Cell 独立设备数 | ~20K |
| `_pf_cell_radius` | P50/P90 半径 | ~20K |
| `_pf_bs_center` | BS 质心 | ~12K |
| `_pf_daily_centroid` | 每日质心 | ~80K |
| `_pf_cell_drift` | 漂移分类 | ~20K |

## 数据表

| 表 | Schema | 说明 |
|----|--------|------|
| `etl_filled` | rebuild4 | 输入 (688K 条, 66 列) |
| `etl_dim_cell` | rebuild4 | Cell 画像 (20,394 条, 42 列) |
| `etl_dim_bs` | rebuild4 | BS 画像 (11,942 条, 38 列) |
| `etl_dim_lac` | rebuild4 | LAC 画像 (1,270 条) |

## 代码位置

| 文件 | 职责 |
|------|------|
| `backend/app/etl/profile.py` | 画像构建主入口 `run_profile()` |
| `backend/app/etl/pipeline.py` | ETL 主入口，`run_etl(build_profile=True)` 触发画像 |
| `backend/app/routers/profiles.py` | 画像查询 API (只读) |

## 样本统计

全量运行结果 (2026-04-08):

| 指标 | 值 |
|------|-----|
| 独立观测点 | 158,486 |
| Cell 总数 | 20,394 |
| Cell active | 5,920 (29.0%) |
| Cell observing | 607 (3.0%) |
| Cell waiting | 13,867 (68.0%) |
| collision Cell | 138 |
| BS 总数 | 11,942 |
| LAC 总数 | 1,270 |

6 个样本 LAC 子集 (用于与 rebuild2 对比):

| 指标 | 新画像 | rebuild2 参考 |
|------|--------|-------------|
| Cell 总数 | 3,603 | 3,751 |
| Cell active | 2,524 | ~1,381 |
| BS 总数 | 1,128 | 1,095 |
| 质心中位偏差 vs rebuild2 | 19.3m | — |
