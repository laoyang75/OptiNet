# rebuild4 核心输入整理

状态：任务书输入整理  
更新时间：2026-04-05

---

## 0. 这份整理解决什么问题

本文件把 rebuild4 必须继承的核心业务、结构、技术、UI 约束集中整理，作为后续正式任务书的输入。

它回答的是：

- rebuild4 到底要继承 rebuild3 的什么
- 哪些内容已经冻结，不应再在实施阶段反复讨论
- UI_v2 对 rebuild4 的强制约束是什么
- 当前数据库已经具备什么、还缺什么

---

## 1. 从 rebuild3 Tier 0 文档继承的核心共识

### 1.1 系统定位

来自 `rebuild4/docs/01_inputs/04_reference/rebuild3_core/01_rebuild3_说明_最终冻结版.md` 的核心定位：

- rebuild4 仍然是**本地动态治理系统**，不是一次性静态重跑系统
- 初始化与增量必须**共用同一套治理语义**
- Cell 是最小治理主语，BS 是空间锚点，LAC 是区域边界与区域健康主语
- 页面和 API 都必须围绕对象 / 决策 / 事实 / baseline / 状态流转组织

### 1.2 状态与资格

以下表达已冻结，rebuild4 不应重新发明一套：

- `lifecycle_state = waiting / observing / active / dormant / retired / rejected`
- `health_state = healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect`
- 三层资格：
  - `existence_eligible`
  - `anchorable`
  - `baseline_eligible`
- `watch` 只能是 UI 派生态，不能成为持久化主状态

### 1.3 baseline 原则

以下原则必须保留：

- 当前批次只读上一版冻结 baseline
- 当前批次不能一边判定一边改写本批 baseline
- baseline 刷新是批末行为，服务下一批次，而不是回头污染当前批次

### 1.4 事实分流

四分流和标准事件层必须保留：

1. `fact_standardized`
2. `fact_governed`
3. `fact_pending_observation`
4. `fact_pending_issue`
5. `fact_rejected`

对 rebuild4 来说，这不只是表名，而是页面与 API 的主语基础。

---

## 2. 从 rebuild3 Tier 0 文档继承的结构与技术边界

### 2.1 schema 边界

rebuild4 仍应遵守“新 schema 增量新增，不覆盖旧库”的原则。

参考 rebuild3 的组织方式：

- `rebuild4`：对象、事实、画像、异常、读模型依赖的核心数据
- `rebuild4_meta`：run、batch、version、source_adapter、baseline、快照等控制元数据
- `rebuild2 / rebuild2_meta / legacy / rebuild3*`：只读参考源

### 2.2 技术边界

来自 `rebuild4/docs/01_inputs/04_reference/rebuild3_core/03_rebuild3_技术栈要求_最终冻结版.md`：

- PostgreSQL 17 作为主计算与主存储
- Python 3.11+ + FastAPI 负责编排与读模型 API
- Vue 3 + TypeScript + Vite 负责前端工作台
- 实现坚持 SQL-first，不以 ORM 领域模型为主
- 不提前引入 Kafka / Redis / ClickHouse / Spark / 云端调度系统

### 2.3 版本追溯

所有对象、事实、决策、画像都必须能追溯：

- `run_id`
- `contract_version`
- `rule_set_version`
- `baseline_version`

这项要求在 rebuild4 不能被弱化，否则后续又会出现“页面有结果但不知道在看什么”的问题。

---

## 3. UI_v2 对 rebuild4 的强制约束

### 3.1 主工作流

来自 `rebuild4/docs/01_inputs/03_ui_v2/design_notes.md`：

- 日常使用主链路不是“先对照、再看结果”
- 正确链路是：
  - 流转总览
  - 发现变化或异常节点
  - 下钻对象与证据
  - 决定观察/复核/修复
  - 回来看变化是否符合预期

因此 rebuild4 的导航与数据准备都应服务这个主链路。

### 3.2 页面层级

UI_v2 已经把页面层分成三组：

1. **主流程层**
   - 流转总览
   - 流转快照
   - 运行/批次中心
   - 对象浏览
   - 对象详情
   - 等待/观察工作台
   - 异常工作台
   - 基线/画像
2. **画像视角层**
   - LAC 画像
   - BS 画像
   - Cell 画像
3. **支撑治理层**
   - 基础数据治理
   - 验证/对照
   - 初始化数据
   - 启动器

rebuild4 任务书必须延续这套 IA，不应重新退回 step 导航。

### 3.3 审计已确认的关键 UI 决策

来自 `rebuild4/docs/01_inputs/03_ui_v2/audit_decisions_required.md` 已有选择：

- 对象浏览与画像页：并列导航
- 旧 `classification/confidence`：保留为解释层，不再做主状态
- 搜索：以对象主键 + run_id + batch_id 为主，但特定页面仍需支持 LAC / BS / Cell 快速定位
- 初始化页：并入运行语义，不应脱离 run / batch 体系理解
- 侧边栏：分组 + 对象画像二级结构
- delta：关键页面展示，次级页面可折叠
- `batch_snapshot`：作为时间快照页底座，属于正式需求
- 资格进度：必须拆成存在 / 锚点 / baseline 三段
- 异常工作台：需要覆盖对象级异常 + 记录级异常/结构不合规子视图

### 3.4 UI_v2 对数据的直接要求

UI_v2 不是纯视觉稿，它已经暗含了数据结构要求：

- 首页必须有当前批次的四分流
- 快照页必须有时间点历史
- run/batch 中心必须能看批次变化与趋势
- 对象页和画像页必须能区分治理态与质量态
- baseline 页必须能说明为什么刷新/没刷新
- compare 页必须能解释修复前后差异
- governance 页必须能回答字段/表/使用状态

因此 rebuild4 的任务书不能只写页面，还必须写清这些页面的数据底座。

---

## 4. rebuild2 必须被显式继承的内容

### 4.1 解析与清洗

rebuild4 必须直接继承或显式复用 rebuild2 已验证的内容：

- 原始字段审计
- `cell_infos` 解析规则
- `ss1` 解析规则
- ODS 清洗规则
- 合规规则
- 主键与派生规则（如 `bs_id` / `sector_id`）

### 4.2 trusted 过滤与对象构建

rebuild2 已完成的研究成果不能在 rebuild4 中“只拿最终结果，不解释来源”：

- trusted LAC 筛选
- trusted Cell 筛选
- trusted BS / refined BS 计算
- GPS 修正
- 信号补齐
- 异常分类
- 画像基线

### 4.3 rebuild2 的文档与元数据将成为 rebuild4 的解释层来源

对于 rebuild4，rebuild2 不只是历史参考，更是“为什么会过滤成这样”的解释层来源。

这意味着 rebuild4 任务书中至少要明确：

- 哪些解释直接读取 `rebuild2_meta` 与 `rebuild2` 结果
- 哪些解释迁移到 `rebuild4_meta` 做统一承接
- 哪些 rebuild2 文档中的数字以数据库实时查询结果为准

---

## 5. 当前数据库状态对 rebuild4 的现实约束

### 5.1 rebuild3 当前已经有的正式数据

2026-04-05 实时查询结果：

- `rebuild3.fact_standardized`：43,771,306 行
- `rebuild3.fact_governed`：24,855,605 行
- `rebuild3.fact_pending_observation`：10,590,738 行
- `rebuild3.fact_pending_issue`：3,825,562 行
- `rebuild3.fact_rejected`：4,499,401 行
- `rebuild3.obj_cell`：573,561 行
- `rebuild3.obj_bs`：193,036 行
- `rebuild3.obj_lac`：50,153 行

### 5.2 rebuild3 当前的运行元数据现实

2026-04-05 实时查询结果：

- `rebuild3_meta.run`：4 个 run
  - 1 个 `full_initialization`
  - 3 个 `scenario_replay`
- `rebuild3_meta.batch_snapshot`：1,562 行
  - 覆盖 142 个 batch
  - 4 个 stage（`input` / `routing` / `objects` / `baseline`）
  - 11 个 metric
- `rebuild3_meta.baseline_version`：4 条
  - 1 条正式 full baseline
  - 3 条 scenario baseline

### 5.3 当前缺口

虽然 rebuild3 已经有大量数据，但对 rebuild4 任务书来说，必须清楚承认以下事实：

- 真正的 real 动态主链仍不足
- `scenario_replay` 目前仍是 synthetic 语义
- `/compare`、`/governance` 仍有 fallback 历史包袱
- “有数据可评估”这件事不能再靠后期补 synthetic 评估模式兜底

---

## 6. rebuild4 正式任务书必须回答的关键问题

### 6.1 数据侧

- rebuild4 的正式初始化数据从哪里来
- rebuild4 的正式增量批次从哪里来
- 哪些表是直接复用 rebuild2 / rebuild3 的只读源
- 哪些结果必须由 rebuild4 自己重新产出

### 6.2 页面侧

- 哪些页面必须以 real 数据为主语
- 哪些页面允许临时 synthetic 评估模式
- 哪些页面若只有 fallback，则不算正式完成

### 6.3 验收侧

- “页面能打开”是否算完成：不算
- “有 synthetic 数据能评估 UI”是否算完成：只算阶段性完成
- “有 real run / batch / baseline / snapshot 能支撑主链路评估”才算正式进入验收

---

## 7. 结论

rebuild4 的核心输入已经足够明确：

- 业务语义用 rebuild3 的 Tier 0 文档
- 页面与工作流用 UI_v2
- 数据清洗解释层必须把 rebuild2 正式纳入
- 数据准备必须成为任务书中的一等模块

下一步不应直接开始实现，而应继续把“新增需求与数据准备清单”写实、写细、写成可验收条目。
