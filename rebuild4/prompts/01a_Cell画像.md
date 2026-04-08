# Step 01a: Cell 画像管道

## 背景

画像是 rebuild4 的第二步处理管道（ETL 之后）。为每个 Cell 建立特征参数，作为流转系统的判断基础。Cell 画像完成后，BS 和 LAC 在其基础上聚合派生。

## 前置条件

- `etl_filled` 表存在（687,788 条，66 列）
- 阅读 `99_系统上下文.md`、`docs/02_profile/00_总览.md`、`docs/02_profile/01_cell.md`

## 核心算法决策（经数据验证）

### 独立观测点

`(cell_id, minute)` 去重，不含设备维度。设备上报是脉冲式（98% 间隔 < 5min），时间窗口差异极小，1min 窗口比 1h 增加 21.6% 观测点且碰撞检出更真实。

### 质心

中位数（PERCENTILE_CONT 0.5）。比 AVG 精度高 7-70 倍（实测），天然抗碰撞和噪声。

### 质量门槛

| 等级 | 条件 | 精度 |
|------|------|------|
| 优秀 | >= 8 obs + >= 3 设备 + P90<500m | 94.5% |
| 良好 | >= 3 obs + >= 2 设备 | 93.2% |
| 合格 | >= 1 obs | 93.4% |

### 漂移分类

基于日质心的 `net_drift / max_spread` 比率：碰撞(<0.3) / 搬迁(>0.7) / 动态(>0.7+少设备)。

碰撞 Cell 的 PCI/freq 在两个位置完全相同，无法用射频参数区分，但远端全部只有 1 台设备（可用设备数投票）。

## 计算步骤

1. **S1 基础聚合** — 从 etl_filled GROUP BY，原始记录级统计
2. **S2 独立观测点** — 1min 去重表 → 聚合 obs/devs/days
3. **S3 中位数质心** — 从去重表算 PERCENTILE_CONT 0.5 + P50/P90
4. **S4 BS距离** — BS 中心(中位数) → Cell-BS 距离
5. **S5 漂移分类** — 日质心 → max_spread/net_drift → 8 类
6. **S6 质量分级** — position_grade + confidence
7. **S7 规模评估** — cell_scale
8. **S8 生命周期 + 位置映射** — lifecycle + dim_admin_area

## 产出

`rebuild4.etl_dim_cell` — 21,898 个 Cell，40+ 字段

## 完成后

继续 `01b_BS画像.md`
