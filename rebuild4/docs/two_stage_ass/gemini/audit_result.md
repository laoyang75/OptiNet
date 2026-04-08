# 流式架构审计 — Gemini 独立评估

## 1. 现状诊断报告

针对当前系统的前端页面，结合后端 API 和数据库实际状态，诊断如下：

| 前端页面 | 依赖的 API / 后端逻辑 | 数据源状态 | 功能状态 | 与原设计的偏差 |
| :--- | :--- | :--- | :--- | :--- |
| **FlowOverviewPage.vue**<br>(流转总览) | `flow.py` | `rebuild4_meta.batch_flow_summary`<br>有 4 条旧的模拟记录。 | **展示过期数据** | 原设计用于展示增量批次的四分流及 Delta 变化。目前画像通过 `profile.py` 全量重建，无流转数据产出，该页面形同虚设。 |
| **FlowSnapshotPage.vue**<br>(流转快照) | `flow.py` | `rebuild4_meta.batch_snapshot`<br>有 44 条旧记录。 | **展示过期数据** | 同上，失去真实数据流支撑。 |
| **RunBatchCenterPage.vue**<br>(批次中心) | `runs.py` | `rebuild4_meta.run` / `batch`<br>分别有 2 / 4 条旧记录。 | **展示过期数据** | 原设计作为数据版本的核心控制台。现在的 ETL 脚本直接重写表，未向此类注册批次信息。 |
| **ObservationWorkspacePage.vue**<br>(观察工作台) | `workspaces.py` | `rebuild4_meta.observation_workspace_snapshot`<br>有旧数据 (5w条)。 | **展示过期数据** | 原设计基于批次状态转化（如 `waiting` → `observing`）。现在由于没有批次流转的概念，此工作台无法追踪状态变化。 |
| **AnomalyWorkspacePage.vue**<br>(异常工作台) | `workspaces.py` | `rebuild4_meta.batch_anomaly_*`<br>有旧数据。 | **展示过期数据** | 同上，依赖于按批次产出的异常断言，现已断档。 |
| **ObjectsPage.vue**<br>(对象浏览) | `objects.py` | `rebuild4.obj_cell/bs/lac`<br>存量数据。 | **查错表 / 严重割裂** | 这是最大的问题。画像管道生成的是 `etl_dim_cell` (2w条)，但 API 仍在查被遗弃的 `obj_cell` (128w条)，导致底层事实与对象列表完全脱节。 |
| **BaselineProfilePage.vue**<br>(基线/画像) | `baseline.py` | `rebuild4_meta.baseline_version` | **空壳** | 原设计用于固化高置信度的数据版本。目前全量计算无版本管理，基线失去意义。 |
| **Cell/Bs/Lac ProfilePage**<br>(各级画像) | `profiles.py` | `rebuild4.etl_dim_cell/bs/lac` | **正常可用** | 准确对齐了最新的 `profile.py` 全量计算产物。 |
| **EtlParse/Clean/FillPage**<br>(ETL 大盘) | `governance_foundation.py` | `rebuild4_meta.etl_run_stats` | **正常可用** | 直接读取了 ETL 和画像过程的统计结果表。 |

---

## 2. 四个核心问题的具体分析

### 问题 1: 流转可视化断裂
* **根因分析**：流式画像实验证明了“逐天累积与批量计算等价”，因此开发移除了复杂的逐批次流转和状态机设计（11 步初始化），改为由 `profile.py` 执行轻量级的全量计算。前端 UI 与后端 `flow.py` 等却没有同步重构，仍旧期望读取增量批次的状态流转事件。
* **影响范围**：流转总览、流转快照、等待/观察工作台、异常工作台等核心首页和看板，导致系统呈现“虚假”的旧数据或空台状态。
* **建议方案**：抛弃虚假的流转概念，承认当前“全量画像”的现状。将“流转总览”重构为“全局资产大盘”，直接从 `etl_dim_cell` 统计各生命周期状态的全局分布；将“观察工作台”简化为实时过滤 `etl_dim_cell` 中 `lifecycle_state='observing'` 记录的列表页，取消其追踪生命周期的历史意图。
* **优先级**：P0（阻塞核心功能，对用户造成极大误导）。

### 问题 2: 数据版本管理缺失
* **根因分析**：当前的 `pipeline.py` 被简化为纯粹的批处理任务，只负责执行 SQL（DROP + CREATE），完全去除了对 `rebuild4_meta` schema 中复杂元数据的依赖和写入。
* **影响范围**：运行/批次中心失效；基线版本管理、对照比较功能无法基于版本进行 diff；无法追溯数据的历史快照。
* **建议方案**：引入“轻量级版本化”。在 `pipeline.py` 开始执行时，往 `rebuild4_meta.run` 和 `batch` 注册一条记录以获取全局的 `batch_id`。即便当前是全量重建表，也能用这个 `batch_id` 作为“当前可用语境”的标识，让批次中心重新发挥作用。
* **优先级**：P1（影响功能闭环与数据可追溯性）。

### 问题 3: 参数与画像耦合
* **根因分析**：为快速证明流式方案的等效性，算法阈值（如 `obs>=3`、稳定基站半径 `<500m`）和规则判断被简单粗暴地硬编码在 `profile.py` 的建表 SQL 中。
* **影响范围**：业务人员无法在线调整阈值参数。一旦参数发生变更，需要研发修改后端 SQL 并全量重跑管道。
* **建议方案**：区分“不可变的几何算法”（如计算质心中位数）与“业务动态阈值”。在 `rebuild4_meta.rule_set_version` 或配置表中定义参数 JSON。`profile.py` 在执行 SQL 前，通过 Python 将配置项作为占位符注入 SQL 模板。配置项外化后，前端可以在“数据治理”增加参数配置表单。不建议做局部重算，既然全量速度可接受，修改参数后统一重跑保持状态一致即可。
* **优先级**：P2（架构优化与业务灵活性）。

### 问题 4: 整体架构一致性
* **标记 `???` 的数据源当前状态**：
  * 等待/观察工作台、异常工作台、基线/画像依赖的表是残留的过时数据（空壳）。
  * 对象浏览（`objects.py`）依赖的是 `rebuild4.obj_cell`，而真实的活跃数据产出是 `rebuild4.etl_dim_cell`，产生了灾难性的脱节。
* **页面工作状态**：只有“ETL 数据处理”大盘和“画像模块（Profile）”在正常读取最新数据。
* **用户视角盲区**：用户进入系统后，首页（流转总览）是不可信的数据，工作台是无效的历史遗留。用户能够查看画像列表，但在点击“对象浏览”进行深入探索时，看到的是老旧的错误数据源，系统整体体验完全断裂。

---

## 3. 整体重构建议 (分阶段计划)

### 第一阶段（必须做 - 阻断修复）：让系统从用户视角可用
1. **API 数据源切换**：立刻修改 `rebuild4/backend/app/routers/objects.py`，将 `obj_cell`、`obj_bs`、`obj_lac` 查询全部替换为指向 `etl_dim_cell`、`etl_dim_bs`、`etl_dim_lac`，修复对象详情查不到实际数据的 P0 缺陷。
2. **首页降级与替换**：下线（或隐藏）“流转总览”和“流转快照”，将系统默认首页切换至 “Cell 画像” 或 “ETL 数据处理”，停止展示失效的批次流转图。
3. **重写工作台入口**：修改 `workspaces.py`，放弃查 `observation_workspace_snapshot` 表，直接执行 `SELECT * FROM rebuild4.etl_dim_cell WHERE lifecycle_state = 'observing'`，让工作台恢复真实可用。

### 第二阶段（应该做 - 架构弥合）：补充轻量级数据版本管理
1. **构建管道注册**：在 `pipeline.py` 中增加生命周期钩子，在 ETL 开始前生成新的 `run_id` 和 `batch_id`，并记录开始和结束时间。
2. **恢复批次中心**：让 `RunBatchCenterPage.vue` 重新工作，仅作为“全量画像执行历史记录”的展示。
3. **轻量级 Baseline**：不再做复杂的增量 Diff Baseline，而是直接将当次 `batch_id` 对应的 `etl_dim_cell` 打上基线 Tag。

### 第三阶段（可以做 - 体验升级）：完善流转可视化和参数外化
1. **重构全局大盘**：基于最新的 `etl_dim_cell` 统计生命周期、信号置信度等指标，重新设计一个“静态数据分布总览”取代旧的动态流转图。
2. **外化算法参数**：在 Governance 模块中提供表单接口，允许业务修改生命周期阈值（如 `obs>=3` 改为 `obs>=5`），通过 Python `string.format` 动态渲染到 `profile.py` 中。
