# rebuild3 UI v2 设计说明文档

> 版本：v2（流式治理工作台导向）
> 日期：2026-04-03

---

## 1. 对 rebuild3 UI 目的的理解

### rebuild3 是什么

rebuild3 是一套**本地流式治理工作台**，围绕移动通信基础设施数据（Cell / BS / LAC）进行持续的对象注册、事件分流、状态流转、版本绑定和基线冻结。它的核心循环是：

```
源数据进入 → 标准化 → 四分流 → 对象证据累计 → 批末统一决策 → baseline 冻结 → 供下一批次复用
```

### UI 的第一目标

帮助用户回答：

1. 当前 run / batch / baseline 是什么
2. 当前批次的数据流到了哪里
3. 哪个节点的数量变化最大
4. waiting / issue / rejected 是否在堆积
5. 哪类对象失去了锚点或 baseline 资格
6. 修复后哪些节点变化符合预期

### rebuild3 不是什么

- 不是静态报表系统
- 不是旧 Step 流程的换皮版
- 不是以回放对比为第一入口的验证器
- 不是假设每次都全量重跑、没有状态承接的一次性系统

---

## 2. 用户如何使用这套 UI

### 日常使用主链路

```
启动器（确认服务正常）
  ↓
流转总览（看当前批次流向、关键 delta、问题入口）
  ↓
定位异常节点（某层数量突增、某类 health_state 扩张）
  ↓
从节点下钻到对象和证据（批次级变化 → 对象列表 → 对象详情）
  ↓
决定动作（继续观察 / 转问题 / 修复逻辑 / 触发局部重跑）
  ↓
修复后回来看变化（变化是否发生在预期节点）
```

### 长期运行语义

- 用户会修逻辑、调规则、重跑部分批次
- 本质上不会每次都完全重跑
- UI 必须支持"局部重跑 + 状态承接 + 修复后观察变化"

### 第一次重构阶段的辅助链路

回放对比是**验证模式**，用于：局部修复后的定向核对、旧版本结果对照、解释差异。它不主导系统使用流程。

---

## 3. 主导航与页面优先级

### 主导航结构

侧边栏分为三组，用分隔线区分：

```
rebuild3 流式治理工作台

【主流程层】
├── 流转总览                              ← 首页，流程图视图，当前批次完整处理链路
├── 流转快照                              ← 时间快照视图，3列对照（初始化后 + 自定义1 + 自定义2）
├── 运行/批次中心                         ← 批次 delta、节点变化、趋势
├── 对象浏览                              ← Cell/BS/LAC 列表与筛选（治理视角）
│   └── 对象详情                          ← 单对象深度诊断
├── 等待/观察工作台                       ← 三层资格推进（存在/锚点/基线）
├── 异常工作台                            ← 对象级异常 + 记录级异常双视角
├── 基线/画像                             ← 触发原因、影响范围、生效时序

【画像视角层】
├── LAC 画像                              ← 区域级画像、统一 health_state、区域质量标签
├── BS 画像                               ← 空间锚点画像、P50/P90、旧分类降级为解释层
├── Cell 画像                             ← 最小治理单元、三维度展示（状态/质量/事实）

【支撑治理层】
├── 基础数据治理                          ← 字段目录、表目录、实际使用、迁移状态（新增）
├── 验证/对照                             ← 收敛验证（降级为辅助模块）+ 热层稳定性
├── 初始化数据                            ← 3天冷启动流程与结果、进入增量链路说明
└── 启动器                                ← 独立页面，运维控制面板
```

说明：
- 流转总览提供两个视图（流程图版 + 时间快照版），通过视图切换按钮互相跳转
- 时间快照版每次批次完成后数据记录到 `batch_snapshot` 表，用户可选择任意时间点查看
- LAC/BS/Cell 画像页是数据质量视角，与对象浏览页的治理状态视角互补
- 所有页面支持搜索功能（按 LAC/BS/Cell 主键搜索）
- 所有页面统一 lifecycle_state、health_state、三层资格（存在/anchorable/baseline_eligible）
- rebuild2 旧分类（classification_v2/gps_confidence/signal_confidence）降级为解释层
- 四分流全部使用全称（fact_governed / fact_pending_observation / fact_pending_issue / fact_rejected）
- 基线原则在相关页面显式可见："当前批次只读取上一版冻结 baseline，新版仅供下一批次使用"

### 为什么首页必须是"流转总览"

传统 Dashboard 给的是静态 KPI 快照——几个数字、几个环图、一个批次列表。这对于一个**流式治理系统**远远不够。

流转总览的核心区别在于：

1. **强制展示当前批次的四分流去向**，不只是总量
2. **强制展示 delta**（相对上一批次的变化），不只是存量
3. **强制展示问题入口**（变化最大的节点、最值得处理的问题），不只是概览
4. **强制展示上下文**（run_id / batch_id / baseline_version / rule_set_version），让用户知道自己在看什么

### 为什么回放对比要降级为验证模块

回放对比在第一次重构验证时很重要，但它不应主导整个产品：

1. 日常使用中，用户更多是观察流转、发现异常、修复逻辑、看变化
2. 如果回放对比主导 IA，容易让系统退化为"每次全量重跑 + 看最终结果"的心智
3. 长期来看，局部重跑 + 状态承接才是核心工作方式

### 页面优先级排序

```
流转总览 > 批次与节点变化 > 对象/等待/异常下钻 > baseline 判断 > 验证对照
```

先看**流动与变化**，再看**对象与原因**，最后才看**验证与对照**。

---

## 4. 每个页面主要服务什么决策

| 页面 | 核心决策 | 用户在这里回答什么 |
|------|---------|-----------------|
| 流转总览 | 当前态势感知 | 今天/当前批次发生了什么？哪里变化最大？该先看哪里？ |
| 运行/批次中心 | 批次变化诊断 | 哪个批次异常？四分流比例怎么变了？趋势是好转还是恶化？ |
| 对象浏览 | 对象状态审查 | 哪些对象健康/异常/等待？哪些失去锚点资格？ |
| 对象详情 | 单对象深度诊断 | 这个对象为什么处于当前状态？证据链是什么？ |
| 等待/观察工作台 | 推进与判断 | 距离晋升还差什么？是前进/停滞/回退？该转问题吗？ |
| 异常工作台 | 问题处置 | 这个异常影响了什么？严重吗？下游连锁反应？ |
| 基线/画像 | 基线判断 | 为什么刷新/没刷新？变化来自哪里？稳定性风险？ |
| 验证/对照 | 修复验证 | 修复后结果变好了吗？差异可解释吗？ |

---

## 5. 关键状态表达方案

### 5.1 lifecycle_state 视觉表达

| 状态 | 颜色 | 徽标样式 | 设计说明 |
|------|------|---------|---------|
| `waiting` | Amber-400 (#FBBF24) | 实心圆点 + "等待" | 黄色调，"进入系统但证据不足" |
| `observing` | Amber-500 (#F59E0B) | 实心圆点 + "观察" + 迷你进度条 | 略深黄色，带累计进度暗示"接近门槛" |
| `active` | Green-500 (#22C55E) | 实心圆点 + "活跃" | 绿色，正式活跃 |
| `dormant` | Gray-400 (#9CA3AF) | 空心圆点 + "休眠" | 灰色，休眠状态 |
| `retired` | Gray-300 (#D1D5DB) | 删除线文字 + "退役" | 浅灰 + 删除线 |
| `rejected` | Red-500 (#EF4444) | 实心圆点 + "拒收" | 红色，已拒收 |

### 5.2 health_state 视觉表达

| 状态 | 颜色 | 图标 | 场景 |
|------|------|------|------|
| `healthy` | Green-500 | ✓ 对勾 | 正常可信 |
| `insufficient` | Gray-400 | ? 问号 | 数据不足 |
| `gps_bias` | Orange-400 | ⊕ 偏移标记 | GPS 偏差 |
| `collision_suspect` | Orange-500 | △ 警告三角 | 碰撞嫌疑，待复核 |
| `collision_confirmed` | Red-500 | ⊘ 禁止 | 碰撞确认 |
| `dynamic` | Blue-400 | → 移动箭头 | 移动对象 |
| `migration_suspect` | Purple-400 | ⇢ 迁移箭头 | 迁移嫌疑 |

### 5.3 watch 派生 UI 状态

当 `lifecycle_state = active` 且 `health_state != healthy` 时：
- 对象卡片/行显示**橙色左边框**
- 右上角显示 **"WATCH"** 小徽标（橙色底白色字）
- 列表中该行有微弱的橙色背景底色

与"真正 healthy"的区分：active + healthy 显示纯绿色，没有任何橙色元素；active + watch 总是带橙色标记。

### 5.4 anchorable / baseline_eligible 资格表达

| 资格 | true 表达 | false 表达 |
|------|----------|-----------|
| `anchorable` | 绿色锚点图标 | 灰色锁定图标 + "锚点禁用" 标签 |
| `baseline_eligible` | 绿色基线图标 | 灰色排除图标 + "基线禁用" 标签 |

详情面板中必须列出禁用的具体原因（哪条规则/哪类异常导致）。

### 5.5 事实层状态表达

| 事实层 | 左边框色 | 背景色 | 图标 | 标签文字 |
|--------|---------|--------|------|---------|
| `fact_governed` | Green-500 | Green-50 | ✓ | 已治理 |
| `fact_pending_observation` | Amber-500 | Amber-50 | ⏱ 时钟 | 观察中 |
| `fact_pending_issue` | Orange-500 | Orange-50 | ⚠ 警告 | 待复核 |
| `fact_rejected` | Red-500 | Red-50 | ⊘ 禁止 | 已拒收 |

### 5.6 系统运行状态表达

| 状态 | 表达 |
|------|------|
| 批次冻结中 | 顶部全局条显示蓝色脉冲 + "批次处理中 batch-xxx" |
| 局部重跑中 | 顶部全局条显示紫色 + "重跑中" + 受影响批次范围 |
| 回放验证中 | 顶部全局条显示灰蓝色 + "验证模式" |

### 5.7 如何避免状态混淆

| 容易混淆的对 | 区分策略 |
|-------------|---------|
| `waiting` vs `observing` | waiting 只有圆点无进度条；observing 带迷你进度条暗示"接近门槛"；observing 的黄色略深 |
| `observing` vs `issue` | observing 是黄色+时钟（正在积累）；issue 是橙色+警告（有问题待处理）；进度条只出现在 observing |
| `issue` vs `rejected` | issue 是橙色（仍可流转、可复核）；rejected 是红色+删除线（已终结、不可恢复） |
| "active 但 watch" vs "真正 healthy" | active+healthy = 纯绿色无标记；active+watch = 绿色 lifecycle 徽标 + 橙色 WATCH 徽标 + 橙色左边框 |

---

## 6. 组件边界建议

### 6.1 页面组件

```
views/
├── FlowOverviewView.vue          # 流转总览（首页）
├── RunBatchCenterView.vue         # 运行/批次中心
├── ObjectsListView.vue            # 对象浏览
├── ObjectDetailView.vue           # 对象详情（抽屉或子页）
├── ObservationWorkspaceView.vue   # 等待/观察工作台
├── AnomalyWorkspaceView.vue       # 异常工作台
├── BaselineProfileView.vue        # 基线/画像
└── ValidationCompareView.vue      # 验证/对照
```

### 6.2 共享组件

```
components/shared/
├── LifecycleBadge.vue             # lifecycle_state 徽标
├── HealthBadge.vue                # health_state 徽标
├── WatchIndicator.vue             # watch 派生态标记
├── QualificationTags.vue          # anchorable + baseline_eligible 标签组
├── FactLayerBadge.vue             # 事实层徽标
├── DeltaIndicator.vue             # delta 展示组件（↑↓箭头 + 变化量 + 配色）
├── MetricCardWithDelta.vue        # 带 delta 的指标卡（当前值 + 本批新增 + 较上批 delta）
├── BatchFlowDiagram.vue           # 四分流可视化（输入 → 四路分流 + 节点标注）
├── RerunBadge.vue                 # 重跑标记徽标（区分正常批次/重跑批次）
├── ObjectCard.vue                 # 对象卡片
├── DataTable.vue                  # 通用数据表格（排序/分页/行点击）
├── StatusTimeline.vue             # 状态变更时间线
├── ProgressBar.vue                # 门槛进度条
├── VersionContext.vue             # run/batch/baseline 版本上下文条
├── EmptyState.vue                 # 空状态
├── ErrorState.vue                 # 错误状态
└── GlobalStatusBar.vue            # 顶部全局状态条（批次处理中/重跑中/验证模式）
```

### 6.3 详情抽屉

```
components/drawers/
├── CellDetailDrawer.vue
├── BsDetailDrawer.vue
├── LacDetailDrawer.vue
├── AnomalyDetailDrawer.vue
└── BaselineDetailDrawer.vue
```

### 6.4 筛选器

```
components/filters/
├── ObjectFilter.vue               # 类型/状态/健康/资格筛选
├── BatchSelector.vue              # 批次切换器
├── BaselineVersionSelector.vue    # baseline 版本切换器
├── AnomalyTypeFilter.vue          # 异常类型筛选
└── CompareConditionPanel.vue      # 对比条件面板
```

### 6.5 图表组件

```
components/charts/
├── FlowSankeyChart.vue            # 四分流桑基/漏斗图
├── BatchTrendChart.vue            # 批次趋势折线图
├── DistributionChart.vue          # 分布图
├── ConvergenceChart.vue           # 收敛对比图
└── SpatialScatterChart.vue        # 空间散点图
```

### 6.6 Pinia Store 边界

| Store | 职责 | 跨页面共享 |
|-------|------|-----------|
| `useRunContextStore` | 当前 run_id / batch_id / baseline_version / rule_set_version | 是 |
| `useFilterStore` | 全局筛选条件 | 是 |
| `useDrawerStore` | 抽屉开关状态、当前详情对象 | 是 |

局部状态（组件内管理）：表格排序/分页、图表交互、表单输入、加载/错误状态。

---

## 7. 读模型建议

### 7.1 流转总览读模型

```
GET /api/flow-overview
→ {
    context: { run_id, batch_id, window_start, window_end, baseline_version, rule_set_version },
    current_batch_flow: { input_count, governed, pending_observation, pending_issue, rejected },
    promotions: { promoted_count, demoted_count, cascade_updates },
    baseline_refresh: { triggered, reason },
    delta_vs_previous: {
      waiting_delta, observing_delta, issue_delta, rejected_delta,
      health_distribution_change, anchorable_change, baseline_eligible_change
    },
    top_changes: [ { node, metric, current, previous, delta } ],
    priority_issues: [ { type, count, severity, link } ]
  }
```

### 7.2 批次中心读模型

```
GET /api/batches?run_id=xxx
→ [ {
    batch_id, window_start, window_end, is_rerun, rerun_source_batch,
    input_count, flow_distribution: { governed, pending_obs, pending_issue, rejected },
    promotions, demotions, cascade_updates,
    delta_vs_previous: { ... },
    baseline_refresh_triggered
  } ]
```

### 7.3 对象列表读模型

```
GET /api/objects?type=cell&lifecycle=active&page=1
→ {
    items: [ {
      object_key, object_type, lifecycle_state, health_state,
      anchorable, baseline_eligible, watch,
      last_active_time, sample_count, device_count, active_days,
      parent_key, child_count, anomaly_tags,
      recent_batch_delta: { fact_governed_count, fact_pending_count }
    } ],
    total, page, page_size
  }
```

### 7.4 对象详情读模型

```
GET /api/objects/:key/detail
→ {
    snapshot: { ... 当前快照 },
    profile_summary: { centroid, radius_p90, signal_stats },
    state_history: [ { batch_id, from_state, to_state, reason } ],
    relation_history: [ { batch_id, change_type, related_object } ],
    recent_facts: [ { batch_id, fact_layer, count } ],
    qualification_reasons: { anchorable_reason, baseline_eligible_reason },
    related_anomalies: [ { anomaly_type, severity, batch_id } ],
    downstream_impact: { affected_bs, affected_lac, affected_baseline_candidates }
  }
```

### 7.5 等待/观察工作台读模型

```
GET /api/observation-workspace?sort=progress_desc
→ [ {
    cell_key, first_seen_time, lifecycle_state,
    current_gps_points, required_gps_points,
    current_devices, required_devices,
    active_days, required_days,
    centroid, radius_p90,
    progress_percent,
    recent_batches_trend: [ { batch_id, new_points, cumulative } ],
    trend_direction: "advancing" | "stalled" | "regressing",
    suggested_action: "continue" | "promote" | "to_issue" | "reject",
    stall_batches: 3
  } ]
```

### 7.6 异常工作台读模型

```
GET /api/anomaly-workspace
→ {
    summary: { total, by_type: { collision_suspect: 12, ... }, by_severity: { ... } },
    items: [ {
      object_key, anomaly_type, severity, health_state,
      discovered_batch, anchorable, baseline_eligible,
      last_evidence_update, evidence_trend,
      downstream_objects: [ { key, type, impact } ],
      suggested_action
    } ]
  }
```

### 7.7 基线/画像读模型

```
GET /api/baseline/current
→ {
    baseline_version, rule_set_version, created_at,
    object_coverage: { cell: 12847, bs: 3421, lac: 156 },
    grade_distribution: { ... },
    gps_confidence_distribution: { ... },
    anomaly_ratio,
    refresh_trigger: { reason, source_batch, trigger_conditions },
    diff_vs_previous: {
      added_objects: 23, removed_objects: 5, changed_objects: 41,
      major_changes: [ { object_key, change_type, detail } ]
    },
    stability_risk: { score, risk_factors: [ ... ] }
  }
```

### 7.8 验证/对照读模型

```
GET /api/validation/compare?run_a=xxx&run_b=yyy
→ {
    object_convergence: { overlap_ratio, only_a, only_b, both },
    spatial_convergence: { centroid_diff_p50, centroid_diff_p90, radius_diff },
    signal_convergence: { rsrp_diff, rsrq_diff, sinr_diff },
    anomaly_convergence: { agreement_ratio, disagreements: [...] },
    decision_convergence: { flow_agreement_ratio },
    major_diff_objects: [ { key, metric, value_a, value_b, diff } ]
  }
```

---

## 8. 当前设计容易滑回报表化/对比化的风险点

### 风险 1：首页退化为 KPI 仪表盘

**症状**：几个数字卡 + 环形图 + 批次列表就结束
**防止方法**：强制包含四分流可视化、delta 指标、问题入口三个区块

### 风险 2：回放对比重新主导 IA

**症状**：用户打开系统第一反应是找"对比"按钮
**防止方法**：验证/对照放在导航最后一项；首页不放对比入口

### 风险 3：只展示总量不展示变化

**症状**：指标卡只有一个孤立数字
**防止方法**：所有 MetricCard 硬性要求三行格式：当前值 | 本批新增 | 较上批 delta

### 风险 4：等待池做成候选列表

**症状**：一个大表格，列了所有 waiting 对象，没有进度和建议
**防止方法**：每个候选对象必须显示门槛进度条、推进趋势、建议动作

### 风险 5：异常看板只罗列问题

**症状**：一个异常对象表格，没有影响路径
**防止方法**：每个异常必须展示下游影响（影响了几个对象/事实/baseline 候选）

### 风险 6：页面孤立无下钻

**症状**：页面没有可点击的入口跳转到相关页面
**防止方法**：严格实现下钻路径清单（见第 9 节）

---

## 9. 必须实现的下钻路径

```
流转总览 → 四分流任一节点 → 该批次该层事实列表
流转总览 → 变化最大节点 → 对应页面（等待池 / 异常 / 对象）
流转总览 → delta 异常指标 → 批次中心对应批次
批次中心 → 某批次晋升列表 → 对象详情
批次中心 → 某批次四分流 → 该层事实明细
等待池 → 某候选对象 → 对象详情（含推进历史）
异常看板 → 某异常对象 → 对象详情 + 影响的下游对象
异常看板 → 某异常类型汇总 → 该类型全部对象列表
baseline → 某差异对象 → 对象详情
baseline → 刷新触发原因 → 对应批次详情
```

每个页面至少要有进入路径和下钻出口，不允许孤立页面。

---

## 10. Delta 展示硬规范

所有指标卡和关键数字必须同时展示 **当前值 + 本批次新增量 + 相对上一批次的 delta**。

格式：
- `活跃对象 12,847 | 本批 +3 | 较上批 +1 ↑`
- `等待池 1,283 | 本批 +15 | 较上批 -3 ↓`
- `异常对象 47 | 本批 +2 | 较上批 +2 ↑`（红色上箭头 = 恶化）

Delta 配色：
- 正向变化（改善）：绿色
- 负向变化（恶化）：红色
- 中性变化：灰色
- 无 delta（首次初始化）：显示 "—"

注意：某些指标的"增加"意味着恶化（如异常对象数增加），delta 颜色应根据语义而非数值方向决定。
