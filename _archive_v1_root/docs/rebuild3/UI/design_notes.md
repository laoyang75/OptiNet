# rebuild3 UI 设计决策与信息架构总说明

---

## 1. 对项目的理解

### rebuild3 是什么

rebuild3 是一套**本地动态治理系统**，围绕移动通信基础设施数据（Cell / BS / LAC）进行持续的对象注册、事件分流、状态流转、版本绑定和基线冻结。它不是一次性的静态跑批工具，而是一个有生命周期管理能力的治理工作台。

系统的核心循环是：**源数据进入 -> 标准化 -> 四分流（governed / pending_observation / pending_issue / rejected）-> 对象证据累计 -> 批末统一决策（晋升/降级/级联）-> baseline 冻结 -> 供下一批次复用**。

### 与传统 Step 流程页的根本区别

| 维度 | 旧 Step 模式 | rebuild3 |
|------|-------------|----------|
| 组织主语 | 处理步骤（Step 1/2/3...） | 治理对象（Cell/BS/LAC）+ 决策 + 事实 + 基线 |
| 时间模型 | 一次性跑完 | 初始化 + 2小时增量持续运行 |
| 状态表达 | 单维或隐式 | 二维（lifecycle_state x health_state）+ 三类资格 |
| 数据基线 | 无版本概念 | 严格的 run/batch/baseline 版本绑定 |
| 异常处理 | 过滤掉 | 分流、留痕、复核、状态转移 |

### UI 最需要服务的核心决策

1. **准入决策** — 新出现的 Cell 是否应该被接纳进系统？证据是否充分？
2. **健康判断** — 已有对象当前是否可信？能否做锚点？能否进 baseline？
3. **异常处置** — collision / dynamic / migration 等问题对象如何复核和处理？
4. **基线管理** — 当前 baseline 版本是否需要刷新？刷新后与上一版有什么差异？
5. **收敛验证** — 初始化 + 增量的结果是否与全量初始化收敛？

---

## 2. 信息架构总方案

### 主导航结构

```
rebuild3 工作台
├── 仪表盘 (Dashboard)           ← 系统全局概览，一级页面
├── 运行中心 (Run Center)         ← run/batch/baseline 管理，一级页面
├── 对象浏览 (Objects)            ← Cell/BS/LAC 列表与筛选，一级页面
│   └── 对象详情 (Object Detail)  ← 侧边抽屉或子页面
├── 等待池 (Waiting Pool)         ← waiting/observing 对象管理，一级页面
├── 异常看板 (Anomaly Board)      ← 问题对象集中管理，一级页面
├── 批次审查 (Batch Review)       ← 日更决策与四分流审查，一级页面
├── 基线管理 (Baseline)           ← baseline/profile 版本管理，一级页面
└── 回放对比 (Replay)             ← 收敛性验证与对比，一级页面
```

### 为什么这样分组

1. **仪表盘**独立为首页 — 用户打开系统后第一件事是"看全局健康状态"，不是看某个具体页面。仪表盘提供系统脉搏，引导用户进入需要关注的区域。

2. **运行中心**独立 — run / batch / baseline 是系统的时间轴和版本轴，它不属于任何单一对象页面，需要独立管理。

3. **对象浏览**是核心 — Cell / BS / LAC 是系统主语。对象列表是最高频使用页面，对象详情通过侧边抽屉展开，避免跳转丢失上下文。

4. **等待池**独立于对象浏览 — waiting / observing 对象有独特的"距门槛差距"信息和"建议动作"，不适合混在全量对象列表里。

5. **异常看板**独立 — 问题对象的审查逻辑（collision / dynamic / migration）与正常对象浏览完全不同，需要独立的工作流。

6. **批次审查**独立 — 围绕"决策"而非"对象"组织，展示四分流结果、晋升/降级列表、时间线。

7. **基线管理**独立 — baseline 版本对比是专门的审查任务。

8. **回放对比**独立 — 收敛性验证是特定的验证工作流。

### 页面层级说明

| 类型 | 页面 |
|------|------|
| 一级页面（主导航） | 仪表盘、运行中心、对象浏览、等待池、异常看板、批次审查、基线管理、回放对比 |
| 详情抽屉 | 对象详情（Cell/BS/LAC）、异常事件详情、baseline 版本详情 |
| 弹层/对话框 | 筛选器高级面板、对比条件选择器、操作确认 |

---

## 3. 关键状态表达方案

### 3.1 lifecycle_state 视觉表达

| 状态 | 颜色 | 徽标样式 | 说明 |
|------|------|---------|------|
| `waiting` | Amber-400 | 实心圆点 + 文字 | 黄色调，表示"进入系统但证据不足" |
| `observing` | Amber-500 | 实心圆点 + 文字 + 进度条 | 略深的黄色，带累计进度指示 |
| `active` | Green-500 | 实心圆点 + 文字 | 绿色，表示正式活跃 |
| `dormant` | Gray-400 | 空心圆点 + 文字 | 灰色，表示休眠 |
| `retired` | Gray-300 | 删除线 + 文字 | 浅灰 + 删除线，表示已退役 |
| `rejected` | Red-500 | 实心圆点 + 文字 | 红色，表示被拒收 |

### 3.2 health_state 视觉表达

| 状态 | 颜色 | 图标 | 说明 |
|------|------|------|------|
| `healthy` | Green-500 | 对勾 | 健康 |
| `insufficient` | Gray-400 | 问号 | 数据不足 |
| `gps_bias` | Orange-400 | 定位偏移图标 | GPS 偏差 |
| `collision_suspect` | Orange-500 | 警告三角 | 碰撞嫌疑 |
| `collision_confirmed` | Red-500 | 禁止图标 | 碰撞确认 |
| `dynamic` | Blue-400 | 移动箭头 | 动态/移动对象 |
| `migration_suspect` | Purple-400 | 迁移箭头 | 迁移嫌疑 |

### 3.3 watch 派生 UI 状态

当 `lifecycle_state = active` 且 `health_state != healthy` 时，在对象卡片和列表行上显示：
- 橙色边框高亮
- 右上角显示 "WATCH" 小徽标（橙色背景白色文字）
- 列表中该行有左侧橙色竖线标记

### 3.4 锚点禁用态（anchorable = false）

- 在对象卡片中显示 "锚点禁用" 灰色标签，带锁定图标
- 列表中锚点列显示灰色锁图标
- 详情面板中明确列出禁用原因

### 3.5 baseline 禁用态（baseline_eligible = false）

- 在对象卡片中显示 "基线禁用" 灰色标签，带排除图标
- 列表中基线列显示灰色排除图标
- 详情面板中明确列出禁用原因

### 3.6 事实层状态避免混淆

| 事实层 | 背景色 | 左侧竖线色 | 图标 | 文案 |
|--------|--------|-----------|------|------|
| `fact_governed` | Green-50 | Green-500 | 对勾 | 已治理 |
| `fact_pending_observation` | Amber-50 | Amber-500 | 时钟 | 观察中 |
| `fact_pending_issue` | Orange-50 | Orange-500 | 警告 | 待复核 |
| `fact_rejected` | Red-50 | Red-500 | 禁止 | 已拒收 |

关键区分策略：
- **waiting vs issue**：waiting 用黄色时钟（"正在积累证据"），issue 用橙色警告（"有问题待处理"）
- **observing vs issue**：observing 带进度条（"接近门槛"），issue 无进度条（"需要人工关注"）
- **rejected vs issue**：rejected 用红色 + 删除线（"已终结"），issue 仍可流转

---

## 4. 核心组件边界建议

### 4.1 页面组件清单

```
views/
├── DashboardView.vue          # 仪表盘
├── RunCenterView.vue          # 运行中心
├── ObjectsListView.vue        # 对象浏览
├── ObjectDetailView.vue       # 对象详情（也可作为抽屉）
├── WaitingPoolView.vue        # 等待/观察池
├── AnomalyBoardView.vue       # 异常看板
├── BatchReviewView.vue        # 批次审查
├── BaselineView.vue           # 基线管理
└── ReplayView.vue             # 回放对比
```

### 4.2 共享组件清单

```
components/shared/
├── StatusBadge.vue            # lifecycle_state 徽标
├── HealthBadge.vue            # health_state 徽标
├── QualificationTags.vue      # anchorable + baseline_eligible 标签组
├── WatchIndicator.vue         # watch 派生态指示器
├── FactLayerBadge.vue         # 事实层徽标
├── ObjectCard.vue             # 对象卡片（列表/网格通用）
├── MetricCard.vue             # 指标卡
├── DataTable.vue              # 通用数据表格（排序/分页）
├── Timeline.vue               # 状态变更时间线
├── ProgressBar.vue            # 门槛进度条
├── EmptyState.vue             # 空状态
├── ErrorState.vue             # 错误状态
├── LoadingState.vue           # 加载状态
├── Pagination.vue             # 分页器
└── VersionBind.vue            # run/batch/baseline 版本绑定展示
```

### 4.3 详情抽屉组件

```
components/drawers/
├── CellDetailDrawer.vue       # Cell 详情抽屉
├── BsDetailDrawer.vue         # BS 详情抽屉
├── LacDetailDrawer.vue        # LAC 详情抽屉
├── AnomalyDetailDrawer.vue    # 异常事件详情抽屉
└── BaselineDetailDrawer.vue   # Baseline 版本详情抽屉
```

### 4.4 筛选器组件

```
components/filters/
├── ObjectFilter.vue           # 对象筛选（类型/状态/健康/资格）
├── BatchSelector.vue          # 批次切换器
├── BaselineVersionSelector.vue # baseline 版本切换器
├── TimeRangeFilter.vue        # 时间范围筛选
├── AnomalyTypeFilter.vue      # 异常类型筛选
└── CompareConditionPanel.vue  # 回放对比条件面板
```

### 4.5 图表组件

```
components/charts/
├── FunnelChart.vue            # 四分流漏斗图
├── TrendChart.vue             # 趋势折线图
├── DistributionChart.vue      # 分布图（直方图/箱线图）
├── ConvergenceChart.vue       # 收敛对比图
├── SpatialScatter.vue         # 空间散点图（BS 中心点）
└── StateFlowSankey.vue        # 状态流转桑基图
```

### 4.6 共享状态边界（Pinia vs 局部状态）

**Pinia 全局 Store：**
- `useRunStore` — 当前 run/batch 上下文、活跃批次列表
- `useBaselineStore` — 当前 baseline 版本、版本列表
- `useFilterStore` — 全局筛选条件（跨页面保持）
- `useDrawerStore` — 抽屉开关状态、当前详情对象

**局部状态（组件内）：**
- 表格排序/分页状态
- 图表交互状态
- 表单临时输入
- 加载/错误状态

---

## 5. 样本场景映射

### 5.1 正常 active 对象

**映射页面**：对象浏览列表
- 列表行显示绿色 `active` 徽标 + 绿色 `healthy` 图标
- 锚点列显示绿色对勾，baseline 列显示绿色对勾
- 点击展开详情抽屉，显示完整画像和历史

### 5.2 即将晋升的 waiting / observing Cell

**映射页面**：等待池
- 卡片式布局，每个 Cell 显示：
  - Amber `waiting` 或 `observing` 徽标
  - 门槛进度条（GPS点数 8/10、设备数 1/2、天数 2/3）
  - 缺口高亮显示（红色标记未达标项）
  - 建议动作按钮："继续观察" / "手动晋升" / "转问题"
- observing 的卡片比 waiting 的进度条更满，视觉上更接近绿色

### 5.3 collision_suspect

**映射页面**：异常看板
- 橙色警告行，显示 `collision_suspect` 标签
- 关联 BS 信息，涉及的 Cell 列表
- 锚点列显示红色锁（已禁用）
- 操作区：标记为 confirmed / 解除嫌疑 / 查看证据

### 5.4 collision_confirmed

**映射页面**：异常看板
- 红色高亮行，显示 `collision_confirmed` 标签
- 锚点和 baseline 均显示禁用
- 所有关联事实已转入 `fact_pending_issue`
- 操作区：查看碰撞对象组、查看影响范围

### 5.5 dynamic

**映射页面**：异常看板
- 蓝色标签，显示移动箭头图标
- 说明文字："移动对象，可生成低精度画像但不进正式基线"
- 锚点禁用，baseline 禁用
- 可查看移动轨迹摘要

### 5.6 migration_suspect

**映射页面**：异常看板 + 对象详情
- 紫色标签，显示迁移箭头
- 对象详情中的关系历史时间线高亮显示关系变更
- 操作区：确认迁移 / 维持观察

### 5.7 fact_rejected

**映射页面**：批次审查
- 红色行，显示 `已拒收` 标签 + 删除线
- 拒收原因列
- 仅留痕，无后续操作

### 5.8 baseline 切换前后差异对象

**映射页面**：基线管理 + 回放对比
- 基线管理页中的"版本对比"视图
- 左右分栏对比两个 baseline 版本
- 差异对象高亮显示：新增（绿色）、移除（红色）、变更（橙色）
- 可展开查看单个对象在两个版本间的具体差异

---

## 6. 设计风险与建议

### 6.1 哪些文档内容会影响 UI 设计

1. **watch 不是持久化状态** — UI 必须通过读模型组合派生，不能期望后端直接返回 `watch` 字段
2. **三类资格独立** — 不能用一个"状态"字段同时表达存在、锚点、基线三种资格
3. **批末统一更新** — 批次处理过程中对象状态不变，UI 不应在批次运行中实时刷新对象状态
4. **研究期 vs 长期口径** — UI 中应标注哪些参数是研究期特有的，避免用户误以为是长期规则

### 6.2 最容易让用户混淆的状态

1. **waiting vs pending_observation** — 前者是 lifecycle 状态，后者是事实层。UI 必须用不同的视觉语言区分"对象在等待"和"事实在观察中"
2. **active + unhealthy vs issue** — active 但 health_state 异常的对象，与直接进入 issue 事实的区别。建议用 WATCH 徽标显式标注
3. **anchorable vs baseline_eligible** — 两者经常同时禁用但原因不同，需要在详情中分别列出禁用原因
4. **collision_suspect vs collision_confirmed** — 一个是待复核，一个是已确认。用橙色 vs 红色 + 不同图标区分

### 6.3 最容易做成"只是报表"的页面

1. **仪表盘** — 容易变成一堆数字卡。建议：加入"需要关注"区块，引导用户进入具体页面
2. **对象浏览** — 容易变成一个大表格。建议：加入卡片视图切换、快速筛选、内联操作
3. **基线管理** — 容易变成版本号列表。建议：加入版本对比、差异可视化、影响范围展示
4. **回放对比** — 容易变成一堆统计数字。建议：用对比图表、差异高亮、可下钻到具体对象

### 6.4 避免这些问题的建议

1. **每个页面至少有一个"行动区"** — 不只是看数据，还要能触发操作（筛选、标记、对比、导出）
2. **状态不只用文字，用颜色 + 图标 + 位置三重编码** — 避免用户需要逐字阅读状态文本
3. **关键决策信息前置** — 最重要的信息放在视线最先到达的位置（左上、标题行）
4. **提供上下文链接** — 在异常看板中可以直接跳转到对象详情，在批次审查中可以跳转到 baseline 对比
5. **用进度和差距代替纯数字** — 等待池中用进度条而不是纯数字展示"距门槛还差多少"
