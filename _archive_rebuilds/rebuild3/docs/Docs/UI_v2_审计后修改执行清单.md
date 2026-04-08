# rebuild3 UI v2 — 审计后修改执行清单

> 适用对象：负责 UI v2 修改的设计 agent / 原型 agent
>
> 本文件基于以下结果整理：
> - `docs/rebuild3/UI_v2/audit_deviation_report.md`
> - `docs/rebuild3/UI_v2/audit_decisions_required.md`
> - 本轮补充意见：新增“基础数据治理”栏目，用于承接字段、表、实际使用关系与迁移说明
>
> 目标不是直接写开发文档，而是先把 UI 原型、页面结构、命名口径、栏目组织修正到可进入最终开发修订的状态。

---

## 1. 本轮修改目标

本轮 UI 修改只做三件事：

1. 把 UI v2 与冻结版核心语义重新对齐，消除状态模型、四分流命名、资格表达上的偏差。
2. 把 rebuild2 仍有价值的画像指标保留下来，但降级为“解释信息”，不再让旧分类体系主导页面。
3. 新增“基础数据治理”栏目，补上未来整体迁移所需的字段治理、表治理、实际使用说明与迁移状态。

---

## 2. 本轮必须统一的总规则

以下规则属于 P0，所有页面都必须服从：

### 2.1 对象生命周期统一

所有对象页面统一使用以下 `lifecycle_state` 枚举，不得在不同页面改名或删改语义：

- `waiting`
- `observing`
- `active`
- `dormant`
- `retired`
- `rejected`

说明：
- 页面可以按场景隐藏暂时不用的取值；
- 但字段语义和筛选口径必须一致；
- 画像页不能再各自维护一套“简化版生命周期”。

### 2.2 对象健康状态统一

对象层只允许以下 `health_state` 作为主状态：

- `healthy`
- `insufficient`
- `gps_bias`
- `collision_suspect`
- `collision_confirmed`
- `dynamic`
- `migration_suspect`

说明：
- `classification_v2`、`gps_confidence`、`signal_confidence` 可以保留为解释标签或质量信息；
- 但它们不能再代替 `health_state` 成为主状态字段；
- LAC 页中的“覆盖不足”不能直接作为主健康状态，若需要保留，应降级为派生字段，如 `region_quality_label`。

### 2.3 资格表达统一为三层

所有对象相关页面都必须区分三层资格，不允许混成一个门槛：

- 存在资格
- `anchorable`
- `baseline_eligible`

说明：
- 等待/观察工作台尤其要修正，不能再把 `10 GPS / 2 设备 / 3 天` 直接当成对象晋升门槛；
- 这些阈值最多只能服务某一层资格判断，不得替代整套状态机。

### 2.4 四分流命名必须全称

UI 中只允许出现以下全称：

- `fact_governed`
- `fact_pending_observation`
- `fact_pending_issue`
- `fact_rejected`

说明：
- 禁止继续出现 `pending_obs`、`fact_pending_obs` 这类缩写；
- 页面文案可以显示中文，但技术字段名、mock key、tooltip 里的英文主字段必须使用全称。

### 2.5 旧画像模型降级为解释层

rebuild2 留下来的以下信息可保留，但必须降级为“辅助解释”：

- `classification_v2`
- `gps_confidence`
- `signal_confidence`
- 旧画像聚合出的空间质量标签

推荐处理方式：
- `dynamic`、`collision_*` 可转为对象级 `health_state`；
- `single_large`、`normal_spread` 转为记录级异常标签，不直接写入对象主状态；
- `collision_uncertain` 暂按 `collision_suspect` 的弱提示处理，并保留原值供说明。

### 2.6 版本上下文要成为全局组件

核心页面都要有统一的版本上下文条，至少按页面适用情况展示以下字段：

- `run_id`
- `batch_id`
- `contract_version`
- `rule_set_version`
- `baseline_version`

说明：
- 不要求每页都展示五个字段，但必须使用统一组件；
- 禁止某页写 `rule_version`、另一页写 `rule_set_version`。

### 2.7 baseline 原则必须显式可见

所有涉及判定、基线、对照的页面，都要把这句话可视化：

- 当前批次只读取上一版冻结 baseline
- 本批次结束后如触发刷新，新 baseline 仅供下一批次使用

这不是注释，而是 UI 语义的一部分。

---

## 3. 新增栏目：基础数据治理

这是本轮新增要求，优先级 P0。

### 3.1 为什么必须新增

当前 UI 已经覆盖了对象、批次、异常、基线、验证，但还缺一层“底座治理视角”：

- 字段有哪些，哪些仍在被使用
- 表有哪些，哪些是真正运行依赖
- 哪些只是历史兼容或研究表
- 哪些表/字段未来是直接复用、重组迁移、仅参考、还是可淘汰

如果这层不加，后续整体迁移时：
- 设计稿里看不出真实依赖关系
- 开发文档很难界定“必须做”和“仅参考”
- rebuild2 资产会继续以碎片方式被引用

### 3.2 栏目定位

新增一级栏目：

- `基础数据治理`

定位：
- 它不是主流程页面；
- 它是“治理支撑层”页面；
- 用于承接字段资产、表资产、实际使用关系、迁移说明和口径说明。

建议在侧边栏中把它放在“支撑/治理底座”区域，和 `验证/对照` 同属辅助层，而不是挤进主流程前半段。

### 3.3 建议新增页面

建议新增：

- `docs/rebuild3/UI_v2/pages/13_data_governance.html`
- `docs/rebuild3/UI_v2/pages/13_data_governance_doc.md`

### 3.4 页面结构建议

建议使用一个页面 + 多 Tab，而不是拆成多个一级页面。

推荐 Tab 结构：

1. `字段目录`
2. `表目录`
3. `实际使用`
4. `迁移状态与说明`

### 3.5 页面必须回答的问题

“基础数据治理”页面必须能回答以下问题：

- 这个字段属于源字段、标准字段、派生字段还是废弃字段？
- 这张表是事实表、对象快照表、画像聚合表、研究表、元数据表还是临时产物？
- 这张表现在到底被谁在用？
- 是 UI 页面在用、API 在用、批任务在用，还是仅历史兼容保留？
- 未来迁移是直接复用、重组迁移、仅参考还是可淘汰？
- 这张表/字段的权威口径是什么，有什么注意事项？

### 3.6 页面内容要求

#### A. 顶部概览卡

至少包含以下统计：

- 已登记表数量
- 核心运行依赖表数量
- 历史兼容/研究表数量
- 已登记字段数量
- 实际被使用字段数量
- 待迁移确认资产数量

#### B. 字段目录 Tab

字段目录表至少应包含：

- 字段名
- 中文说明
- 所属层级（源/标准/对象/事实/基线/画像/元数据）
- 数据类型
- 来源表
- 当前使用位置
- 是否核心
- 迁移状态
- 备注

推荐标签：

- `核心依赖`
- `辅助依赖`
- `历史兼容`
- `待淘汰`

#### C. 表目录 Tab

表目录表至少应包含：

- 表名
- 中文说明
- 表类型
- 粒度
- 主键/唯一键
- 更新方式
- 上游来源
- 下游使用方
- 保留策略
- 当前状态
- 迁移状态

推荐表类型标签：

- `事实表`
- `对象快照表`
- `基线表`
- `画像聚合表`
- `研究表`
- `元数据表`
- `临时表`

#### D. 实际使用 Tab

这是本次补充要求的重点，必须做出来。

这一页不只列“表存在”，还要列“表被谁用”。

至少需要覆盖：

- 被哪些 UI 页面使用
- 被哪些 API 使用
- 被哪些批处理/脚本/任务使用
- 是主读模型、辅助读模型，还是仅用于研究/对账
- 使用强度：核心依赖 / 辅助依赖 / 历史兼容

建议展示方式：

- 左侧为表/字段列表
- 右侧为“使用说明抽屉”或“依赖详情面板”
- 详情中展示“上游 → 当前资产 → 下游”的关系链

#### E. 迁移状态与说明 Tab

每张表、每类字段至少要有一个迁移结论：

- `直接复用`
- `重组迁移`
- `仅参考`
- `可淘汰`

并补充说明：

- 为什么这样判定
- 对 rebuild3 的作用是什么
- 是否存在替代方案
- 是否需要继续保留兼容查询

---

## 4. 现有页面的修改要求

以下内容按页面分配，优先级从高到低执行。

### 4.1 `01_flow_overview.html` / `01_flow_overview_doc.md`

必须修改：

- 四分流全部改为全称；
- 在节点 tooltip 或说明文案中写清楚四条精确路由条件；
- 增加统一版本上下文条；
- 显式写出“当前批次只看上一版冻结 baseline”；
- 把基线刷新解释成“批末统一更新，供下一批使用”；
- 首页不退回通用 Dashboard 叙事，仍保持“流转总览”主语。

### 4.2 `01_flow_overview_timeline.html`

必须修改：

- 明确保留 `batch_snapshot` 语义；
- 在页面中补充“用于回放和局部重跑对照，不是主流程首页”的说明；
- 与流程图版共用统一版本上下文；
- 所有统计口径沿用四分流全称；
- 避免把时间快照做成纯 delta 对比页。

### 4.3 `02_run_batch_center.html` / `02_run_batch_center_doc.md`

必须修改：

- 页面中显式显示 `run_id`、`batch_id`；
- 补齐 `contract_version`、`rule_set_version`、`baseline_version` 上下文；
- 所有 `pending_obs` 改为 `fact_pending_observation`；
- 批次详情里增加“本批决策依赖上一版 baseline”的提示；
- 初始化运行如果在这里出现，应标注为“特殊 run 类型”，不要伪装成普通增量批次。

### 4.4 `03_objects.html` / `03_objects_doc.md`

必须修改：

- 对象表格统一展示生命周期、健康状态、资格状态；
- 资格至少能区分“存在资格 / anchorable / baseline_eligible”；
- 禁止以旧 `classification_v2` 或 `gps_confidence` 作为主列；
- 保留 `watch` 作为派生提示态，不做持久化主状态；
- 保持对象页是治理视角，不与画像页混成一页报表。

### 4.5 `04_object_detail.html` / `04_object_detail_doc.md`

必须修改：

- 详情页沿用对象页统一状态模型；
- 显式展示三层资格及其原因；
- 展示对象在最近批次中的事实去向分布；
- 展示异常影响与关系变化，但不把旧分类直接当成主状态；
- 增加跳转到 LAC/BS/Cell 画像页的清晰入口。

### 4.6 `05_observation_workspace.html` / `05_observation_workspace_doc.md`

这是本轮重点修改页面之一。

必须修改：

- 把“等待/观察推进”改成三段式资格进度，而不是单一阈值进度；
- `10 GPS / 2 设备 / 3 天` 不得再直接作为对象晋升门槛；
- 每个对象要能回答：当前缺的是存在资格、anchorable 还是 baseline_eligible；
- `suggested_action` 必须对应缺失资格层，而不是泛泛建议；
- 保留 `stall_batches`、`trend_direction`、`progress_percent`，但它们服务于三层资格推进，而不是单一门槛。

### 4.7 `06_anomaly_workspace.html` / `06_anomaly_workspace_doc.md`

这是本轮重点修改页面之一。

必须修改：

- 页面不再只覆盖对象级异常；
- 至少拆成以下两个视角：
  - 对象级异常
  - 记录级异常 / 结构不合规
- 必须能看到以下内容的入口：
  - `single_large`
  - `normal_spread`
  - 结构不合规
  - GPS 缺失回填 / donor 补齐类风险
- 每个异常都要显式回答：
  - 去向是什么
  - 是否禁锚
  - 是否禁入 baseline
  - 下游影响是什么

### 4.8 `07_baseline_profile.html` / `07_baseline_profile_doc.md`

必须修改：

- 页面中显式加入 baseline 生效时序说明；
- 文案要明确“批次结束后刷新，下一批次使用”；
- 版本卡里补齐 `baseline_version` 和来源批次；
- 触发原因、影响范围、差异对象三块逻辑要更连贯；
- 不把基线页做成静态画像页，它仍是治理语义页面。

### 4.9 `08_validation_compare.html` / `08_validation_compare_doc.md`

必须修改：

- 增加“热层稳定性”维度；
- 保持其为辅助验证模块，不抢首页叙事；
- 页面结果需能解释“为什么 3+4 和 7 天接近/不接近”；
- 结果卡和差异列表要保留可解释性字段。

### 4.10 `09_lac_profile.html` / `09_lac_profile_doc.md`

必须修改：

- LAC 页也必须回到统一 `health_state`；
- `覆盖不足` 不再作为主健康状态，而改为区域质量派生标签；
- 表格与详情区要同时展示：
  - `lifecycle_state`
  - `health_state`
  - 资格状态
  - 区域质量诊断
- 保留区域统计和异常分布，但不要重新发明独立状态体系。

### 4.11 `10_bs_profile.html` / `10_bs_profile_doc.md`

必须修改：

- BS 页主状态改为 `health_state + anchorable + baseline_eligible`；
- `classification_v2`、`gps_confidence`、`signal_confidence` 改成解释层字段；
- 质量指标仍可保留：
  - P50 / P90
  - 覆盖面积
  - 原始 GPS/信号来源占比
  - 设备数 / 记录数 / 活跃天数
- 页面整体语义从“旧异常分类画像”调整为“治理状态 + 质量画像”。

### 4.12 `11_cell_profile.html` / `11_cell_profile_doc.md`

必须修改：

- Cell 页主状态改为统一生命周期、健康状态和资格状态；
- 事实去向统计必须使用四分流全称；
- 最近批次分布、基线差异、对象状态变化可以保留为重点信息；
- rebuild2 的旧分类只做辅助说明，不做主标签；
- 页面要清楚地区分：
  - 对象状态
  - 画像质量
  - 最近事实去向

### 4.13 `12_initialization.html` / `12_initialization_doc.md`

必须修改：

- 保留初始化独立页面，但语义上标注为“特殊 run / 冷启动视图”；
- 页面中增加“初始化完成后如何进入增量链路”的说明；
- 版本上下文要规范到 `rule_set_version`；
- 不必把初始化改成日常工作台，但它要能看出与 run/batch 体系的关系。

---

## 5. 导航与分组建议

本轮不强制重做整套 IA，但建议设计 agent 至少按以下思路整理：

### 5.1 主流程层

- 流转总览
- 流转快照
- 运行/批次中心
- 对象浏览
- 等待/观察工作台
- 异常工作台
- 基线/画像

### 5.2 画像视角层

- LAC 画像
- BS 画像
- Cell 画像

### 5.3 支撑治理层

- 基础数据治理
- 验证/对照
- 初始化数据
- 启动器

说明：
- 如果当前原型不方便大改，可先只增加“基础数据治理”并在视觉上体现分组；
- 但不要让新栏目挤进主流程首页附近，避免破坏“流转 → 原因 → 验证”的主叙事。

---

## 6. 需要同步修改的文件

设计 agent 完成修改时，至少应同步这些文件：

- `docs/rebuild3/UI_v2/design_notes.md`
- `docs/rebuild3/UI_v2/pages/01_flow_overview.html`
- `docs/rebuild3/UI_v2/pages/01_flow_overview_doc.md`
- `docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html`
- `docs/rebuild3/UI_v2/pages/02_run_batch_center.html`
- `docs/rebuild3/UI_v2/pages/02_run_batch_center_doc.md`
- `docs/rebuild3/UI_v2/pages/03_objects.html`
- `docs/rebuild3/UI_v2/pages/03_objects_doc.md`
- `docs/rebuild3/UI_v2/pages/04_object_detail.html`
- `docs/rebuild3/UI_v2/pages/04_object_detail_doc.md`
- `docs/rebuild3/UI_v2/pages/05_observation_workspace.html`
- `docs/rebuild3/UI_v2/pages/05_observation_workspace_doc.md`
- `docs/rebuild3/UI_v2/pages/06_anomaly_workspace.html`
- `docs/rebuild3/UI_v2/pages/06_anomaly_workspace_doc.md`
- `docs/rebuild3/UI_v2/pages/07_baseline_profile.html`
- `docs/rebuild3/UI_v2/pages/07_baseline_profile_doc.md`
- `docs/rebuild3/UI_v2/pages/08_validation_compare.html`
- `docs/rebuild3/UI_v2/pages/08_validation_compare_doc.md`
- `docs/rebuild3/UI_v2/pages/09_lac_profile.html`
- `docs/rebuild3/UI_v2/pages/09_lac_profile_doc.md`
- `docs/rebuild3/UI_v2/pages/10_bs_profile.html`
- `docs/rebuild3/UI_v2/pages/10_bs_profile_doc.md`
- `docs/rebuild3/UI_v2/pages/11_cell_profile.html`
- `docs/rebuild3/UI_v2/pages/11_cell_profile_doc.md`
- `docs/rebuild3/UI_v2/pages/12_initialization.html`
- `docs/rebuild3/UI_v2/pages/12_initialization_doc.md`
- `docs/rebuild3/UI_v2/pages/13_data_governance.html`（新增）
- `docs/rebuild3/UI_v2/pages/13_data_governance_doc.md`（新增）

如设计 agent 还需要保留待确认问题清单，也应同步回看：

- `docs/rebuild3/Docs/questions_for_review.md`

---

## 7. 本轮不处理的内容

以下内容暂不在这份 UI 修改清单里定死：

- 最终数据库 DDL
- 最终 API 字段级定义
- run/batch/baseline 元数据表的最终建模
- compare 任务调度实现
- 初始化与增量编排的具体后端落地方式

这些内容等 UI 修正后，再进入开发文档最终修订。

---

## 8. 设计完成后的验收标准

设计 agent 修改完成后，我会按以下标准复核：

### P0 必过项

- 所有页面不再使用 `pending_obs` / `fact_pending_obs`
- 生命周期与健康状态口径统一
- 等待/观察页改成三层资格推进
- 异常页补入记录级异常/结构不合规视角
- baseline 页写清楚“上一版冻结 / 下一批生效”
- LAC 页不再把“覆盖不足”当主健康状态
- 新增“基础数据治理”栏目
- “基础数据治理”中必须有“实际使用”说明

### P1 应满足项

- 版本上下文条在核心页面统一出现
- 画像页把旧分类体系降级为解释层
- 验证页补齐“热层稳定性”
- 初始化页与 run/batch 关系更清楚

### P2 加分项

- 侧边栏完成分组
- 基础数据治理页有表/字段/使用关系的联动详情
- 页面之间的跳转关系比当前更清晰

---

## 9. 给设计 agent 的一句话执行指令

请不要把这轮修改理解为“多加一个页面”。

这轮真正要做的是：

- 把 UI v2 从“原型已丰富但口径仍混杂”修正为“语义一致、可交付开发”的版本；
- 同时补上一层“基础数据治理”视角，让未来迁移有明确的数据资产说明和实际使用说明。
