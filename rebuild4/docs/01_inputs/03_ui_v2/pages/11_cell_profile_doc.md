# Cell 画像页 设计文档

## 页面定位

Cell 画像页是 rebuild3 治理工作台中面向「小区」（Cell）的专用画像/档案页面。Cell 是治理模型中最细粒度的对象，每个 Cell 归属于一个 BS，每个 BS 归属于一个 LAC。本页聚焦 Cell 维度的 GPS 精度、生命周期状态、事实分流分布。

## 状态模型（P0）

### 主状态字段

| 字段 | 类型 | 说明 |
|------|------|------|
| lifecycle_state | 主状态 | 活跃 / 等待中 / 观察中 / 休眠 |
| health_state | 主状态 | 健康 / 数据不足 / 碰撞嫌疑 / 碰撞确认 / 动态 / 迁移嫌疑 / GPS偏差 |
| anchorable | 资格 | 可锚定 / 不可锚定 |
| baseline_eligible | 资格 | 基线合格 / 基线不合格 |

### 参考信息（降级为解释层）

| 字段 | 原名 | 说明 |
|------|------|------|
| bs_classification_v2 | 异常分类（所属 BS） → 旧分类（来自BS，参考） | rebuild2 遗留分类，灰色文字展示 |
| gps_confidence | GPS 可信度 → GPS 可信度（参考） | rebuild2 遗留字段，灰色文字展示 |

**重要：** 旧分类来自所属 BS 的 classification_v2，Cell 自身不再有独立的"动态/固定"列。旧分类和 GPS 可信度降级为灰色参考列。

### 事实去向统计（必须使用全称）

展开详情中的事实去向统计必须使用以下全称：

- `fact_governed`
- `fact_pending_observation`
- `fact_pending_issue`
- `fact_rejected`

## 页面结构

### 1. 搜索栏

- 支持按 Cell ID、BS ID 或 LAC 搜索
- 精确匹配和前缀匹配

### 2. 筛选器

六个筛选维度：

| 筛选项 | 可选值 | 说明 |
|--------|--------|------|
| 运营商 | 全部/中国移动/中国联通/中国电信 | 按运营商过滤 |
| 制式 | 全部/4G/5G | 按网络制式过滤 |
| LAC | 全部/具体 LAC 编号 | 按所属 LAC 过滤 |
| BS | 全部/具体 BS ID | 按所属 BS 过滤 |
| 健康状态 | 全部/健康/数据不足/碰撞嫌疑/碰撞确认/动态/迁移嫌疑/GPS偏差 | 按健康状态过滤 |
| 资格 | 全部/可锚定/不可锚定/基线合格/基线不合格 | 按资格过滤 |

### 3. 汇总卡片

| 卡片 | 指标 |
|------|------|
| Cell 总数 | 总数 + 活跃/等待中/观察中/休眠 分布 |
| 健康状态分布 | 健康/数据不足/碰撞嫌疑/碰撞确认/动态/GPS偏差 |

### 4. 主表格

15 列，支持点击表头排序：

| 列名 | 说明 | 列性质 |
|------|------|--------|
| 运营商 | 中国移动/联通/电信 | 属性 |
| 制式 | 4G/5G | 属性 |
| LAC | 所属 LAC 编号 | 属性 |
| BS ID | 所属 BS 标识 | 属性 |
| Cell ID | 小区标识 | 属性 |
| 生命周期 | 活跃/等待中/观察中/休眠 | **主状态** |
| 健康状态 | 健康/数据不足/碰撞嫌疑/碰撞确认/动态/迁移嫌疑/GPS偏差 | **主状态** |
| 资格 | 可锚定/不可锚定 + 基线合格/基线不合格 | **主状态** |
| 记录数 | 累计事实记录数 | 统计 |
| P90(m) | GPS 点到质心的 P90 距离 | 质量指标 |
| GPS 原始率 | 有原始 GPS 的记录占比 | 质量指标 |
| 信号原始率 | 有原始信号值的记录占比 | 质量指标 |
| RSRP | RSRP 均值 (dBm) | 质量指标 |
| 旧分类（来自BS，参考） | 继承自所属 BS 的 classification_v2 | **参考信息，灰色** |
| GPS 可信度（参考） | 高/中/低/无 | **参考信息，灰色** |

### 5. 行展开详情

点击行展开四个区块，清楚区分三个维度：

#### 5.1 GPS 中心点 + 空间精度（画像质量维度）
- 原始质心坐标（本批次计算）
- 基线质心坐标（上一版基线）
- 偏差距离
- P50/P90/最大距离

#### 5.2 对象状态
- lifecycle_state、health_state、anchorable、baseline_eligible
- 分隔线下方：旧分类（来自所属 BS，rebuild2 参考信息），灰色文字

#### 5.3 画像质量（GPS / 信号来源构成）
- GPS 来源堆叠条：原始 / Cell 补齐 / BS 补齐 / BS 风险补齐
- 信号来源堆叠条：原始 / Cell 补齐 / BS 补齐

#### 5.4 最近事实去向（必须使用全称）
四路分流的迷你条形图：
- fact_governed
- fact_pending_observation
- fact_pending_issue
- fact_rejected

### 6. 口径说明

每个详情面板底部附带口径说明，解释当前 Cell 的特殊情况和计算逻辑。

### 7. 分页

底部分页控件，每页 10 条。

## Cell 生命周期

| 状态 | 含义 | 事实路由 |
|------|------|----------|
| 等待中 | 新发现，积累数据中 | fact_pending_observation |
| 观察中 | 已有一定数据，待晋升 | fact_pending_observation |
| 活跃 | 已晋升，正常使用 | fact_governed（健康时） |
| 休眠 | 连续 7 天无记录 | 不参与基线计算 |

## 数据依赖

- `obj_cell` 表：Cell 注册信息、lifecycle_state、health_state、anchorable、baseline_eligible
- `obj_bs` 表：所属 BS 的 classification_v2（旧分类）、gps_confidence（旧）
- `fact_governed` / `fact_pending_*` / `fact_rejected` 表：事实分布统计
- `baseline_cell` 表：质心坐标、P50/P90
- `baseline_bs` 表：BS 级质心（用于补齐计算）

## 与其他页面的关系

- 从 BS 画像页 (10_bs_profile.html) 可跳转查看 BS 下的 Cell 列表
- 从 LAC 画像页 (09_lac_profile.html) 可跳转查看区域内 Cell
- 从对象浏览 (03_objects.html) 可跳转查看单个 Cell
- 异常 Cell 可链接至异常工作台 (06_anomaly_workspace.html)
- 等待/观察中 Cell 可链接至等待/观察工作台 (05_observation_workspace.html)
