# LAC 画像页 设计文档

## 页面定位

LAC 画像页是 rebuild3 治理工作台中面向「位置区」（Location Area Code）的专用画像/档案页面。区别于通用的对象浏览页（03_objects.html），本页聚焦 LAC 维度的区域级统计与健康诊断。

## 状态模型（P0）

### 主状态字段

| 字段 | 类型 | 说明 |
|------|------|------|
| lifecycle_state | 主状态 | 活跃 / 休眠 / 退役 |
| health_state | 主状态 | 健康 / 数据不足 / 碰撞嫌疑 / 碰撞确认 / 动态 / 迁移嫌疑 / GPS偏差 |
| region_quality_label | 区域质量标签 | 覆盖不足 等，灰色标签展示，独立于 health_state |
| anchorable | 资格 | 可锚定 / 不可锚定 |

**重要：** "覆盖不足"不再作为 health_state，而是独立的区域质量标签列。健康状态列只允许上述 7 个值。

### 资格判定规则

- anchorable（可锚定）：区域内健康 BS 占比达标，且不存在碰撞确认/碰撞嫌疑 BS

## 页面结构

### 1. 搜索栏

- 顶部提供 LAC 编号搜索输入框
- 支持精确匹配和模糊匹配
- 搜索后表格筛选至匹配结果

### 2. 汇总卡片

两组汇总：

| 卡片 | 指标 | 说明 |
|------|------|------|
| LAC 总数 | 总数 / 活跃 / 休眠 / 退役 | 按 lifecycle_state 分组 |
| 区域健康状态 | 健康 / 数据不足 / 碰撞嫌疑 / 碰撞确认 / ... | 按 health_state 分组 |

### 3. 主表格

15 列，覆盖 LAC 的基本属性、层级统计、数据质量指标：

| 列名 | 数据来源 | 说明 | 列性质 |
|------|----------|------|--------|
| 运营商 | obj_lac.operator | 中国移动/联通/电信 | 属性 |
| 制式 | obj_lac.rat | 4G/5G | 属性 |
| LAC | obj_lac.lac_id | 位置区编号 | 属性 |
| 位置 | obj_lac.location_name | 区域名称，可能为空 | 属性 |
| 生命周期 | obj_lac.lifecycle_state | 活跃/休眠/退役 | **主状态** |
| 健康状态 | obj_lac.health_state | 健康/数据不足/碰撞嫌疑/碰撞确认/动态/迁移嫌疑/GPS偏差 | **主状态** |
| 区域质量标签 | obj_lac.region_quality_label | 覆盖不足 等，灰色标签展示 | **独立标签** |
| 资格 | obj_lac.anchorable | 可锚定 / 不可锚定 | **主状态** |
| Cell 数 | 聚合统计 | 区域内 Cell 总数 | 统计 |
| BS 数 | 聚合统计 | 区域内 BS 总数 | 统计 |
| 面积 km² | obj_lac.area_km2 | 区域覆盖面积 | 统计 |
| 异常 BS 占比 | 计算字段 | 异常分类 BS 数 / BS 总数 | 统计 |
| GPS 原始率 | 聚合统计 | 有原始 GPS 的记录占比 | 统计 |
| 信号原始率 | 聚合统计 | 有原始信号值的记录占比 | 统计 |
| RSRP 均值 | 聚合统计 | 区域内 RSRP 加权均值 | 统计 |

### 4. 行展开详情

点击表格行展开下方详情面板，包含四个区块：

#### 4.1 基本信息
运营商、制式、位置、面积。

#### 4.2 区域内 Cell / BS 统计
Cell 总数、BS 总数、活跃 Cell、活跃 BS。

#### 4.3 异常 BS 命中
按异常分类拆分：动态 BS、碰撞确认、碰撞嫌疑、面积大、GPS 噪声。以及整体异常 BS 占比。

#### 4.4 GPS / 信号来源构成
- GPS 来源堆叠条：原始 / Cell 补齐 / BS 补齐 / BS 风险补齐
- 信号来源堆叠条：原始 / Cell 补齐 / BS 补齐

### 5. 口径说明

每个展开详情底部附带口径说明区域，解释当前 LAC 的具体计算逻辑和特殊情况。

### 6. 分页

底部分页控件，每页 8 条，显示总数和当前页码。

## 数据依赖

- `obj_lac` 表：LAC 注册信息、lifecycle_state、health_state、region_quality_label、anchorable、位置
- `obj_bs` 表：聚合统计异常分类
- `obj_cell` 表：聚合统计 Cell 数量
- `fact_governed` / `fact_pending_*` 表：聚合统计记录数、GPS/信号来源构成
- `baseline_*` 表：基线参考值

## 与其他页面的关系

- 从「对象浏览」(03_objects.html) 可跳转至本页
- 从「基线/画像」(07_baseline_profile.html) 可跳转至本页
- 本页行内可链接至 BS 画像页 (10_bs_profile.html) 和 Cell 画像页 (11_cell_profile.html)
- 异常 BS 可链接至异常工作台 (06_anomaly_workspace.html)
