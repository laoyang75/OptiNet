# rebuild4 架构审计结论（Codex 独立评估）

## 一、结论摘要

当前系统不是“完全没数据”，而是出现了**两套并行但未收敛的数据语义**：

1. **主流程/工作台语义**仍然建立在 `rebuild4_meta.run`、`rebuild4_meta.batch`、`rebuild4_meta.batch_snapshot`、`rebuild4.obj_*`、`rebuild4.fact_*`、`rebuild4.baseline_*` 这套“按批次/按对象治理”的模型上。
2. **画像语义**已经切换到 `rebuild4/backend/app/etl/profile.py` 直接从 `rebuild4.etl_filled` 全量重建 `rebuild4.etl_dim_cell` / `rebuild4.etl_dim_bs` / `rebuild4.etl_dim_lac`。

因此系统表面上是一个工作台，实际上已经分裂成：

- 一套“流转/对象/异常/baseline”世界；
- 一套“etl_dim_* 画像”世界。

这两套世界没有被一个统一的版本、批次、参数、快照合同重新绑定起来。结果是：

- ETL 页面基本可用；
- Cell/BS/LAC 画像页基本可用；
- 但首页、流转快照、观察工作台、基线页、验证页等“工作流主路径页面”明显失真或直接不可用；
- 同时多个前端页面与后端 API 已经出现字段名/参数名契约漂移，即使底表有数据，页面也无法正确消费。

**我的总体判断**：

- 当前最优先的问题不是继续加新功能，
- 而是先决定“系统以哪套数据模型为准”，并把前端页面收敛到这套准绳上。

如果以研究项目的投入产出比来看，短期不建议把 `profile.py` 强行改造成真正的逐事件流式增量；更合理的路线是：

- **第一阶段先把页面语义和已有数据对齐**；
- **第二阶段补最小版本管理和参数版本**；
- **第三阶段再决定是否真的补齐批次级差分/观察推进 read model。**

---

## 二、已核实的数据库事实

### 1. 当前指针与运行状态

- `rebuild4_meta.current_pointer` 当前指向：`RUN-ROLL-001` / `BATCH-ROLL-003`
- `rebuild4_meta.run`：2 行（`RUN-INIT-001`、`RUN-ROLL-001`）
- `rebuild4_meta.batch`：4 行（初始化 1 批 + rolling 3 批）
- `rebuild4_meta.batch_flow_summary`：4 行
- `rebuild4_meta.batch_snapshot`：44 行（每批 11 个 metric）
- `rebuild4_meta.batch_transition_summary`：16 行，但全部是 `from_state IS NULL -> governed/pending_observation/pending_issue/rejected`，**不是对象生命周期转移**

### 2. 画像与对象数据

- `rebuild4.etl_dim_cell`：20,394 行（active 5,920 / observing 607 / waiting 13,867）
- `rebuild4.etl_dim_bs`：11,942 行（active 2,954 / observing 208 / waiting 8,780）
- `rebuild4.etl_dim_lac`：1,270 行（active 262 / observing 24 / waiting 984）
- `rebuild4.obj_cell`：1,286,825 行
- `rebuild4.obj_bs`：228,536 行
- `rebuild4.obj_lac`：13,480 行

这说明 `etl_dim_*` 与 `obj_*` **不是同一套口径**，且数量级完全不同。

### 3. 工作台相关 read model

- `rebuild4_meta.observation_workspace_snapshot`：50,000 行，但**全部属于 `BATCH-INIT-001`**
- 对当前批次 `BATCH-ROLL-003`，观察工作台底表**等价于空表**
- `current_stage` 只有：`existence_eligible`、`anchorable`
- 缺少 `baseline_eligible`、`promoted_this_batch`、`converted_to_issue_this_batch` 等结果桶

### 4. 异常与 baseline

- `rebuild4_meta.batch_anomaly_object_summary`：1,600 行
  - 其中 `BATCH-ROLL-003`：1,500 行
- `rebuild4_meta.batch_anomaly_record_summary`：14 行
  - 其中 `BATCH-ROLL-003`：6 个记录级异常类型
- `rebuild4_meta.batch_anomaly_impact_summary`：2,000 行
  - 全部属于 `BATCH-ROLL-003`
- `rebuild4_meta.baseline_version`：1 行（仅 `v1`）
- `rebuild4_meta.baseline_diff_summary`：3 行（`v1` 对空前版的 added_count）
- `rebuild4_meta.baseline_diff_object`：0 行

### 5. 明显空壳/未启用元数据

- `rebuild4_meta.compare_job`：0 行
- `rebuild4_meta.compare_result`：0 行
- `rebuild4_meta.obj_state_history`：0 行
- `rebuild4_meta.obj_relation_history`：0 行

---

## 三、页面级现状诊断

> 说明：
> - “数据源状态”按当前代码真正访问的表来判断；
> - “功能状态”从用户打开页面后的实际效果判断；
> - “与原设计偏差”重点写与 `rebuild4/docs/01_inputs/03_ui_v2/pages/` 规格的差距。

| 页面 | 主要数据源 | 数据源状态 | 功能状态 | 与原设计的偏差 |
|---|---|---|---|---|
| `rebuild4/frontend/src/pages/FlowOverviewPage.vue` | `rebuild4_meta.batch_flow_summary` / `batch_snapshot` / `batch_transition_summary` / `batch_anomaly_object_summary` / `initialization_step_log` | 有数据 | 有数据但展示不完整 | 设计要求可切换批次、展示四分流和 delta、问题入口可下钻；当前页面固定看 `current_pointer`，运行选择器禁用，且把 `obj_cell` 映射成“活跃对象”、把 `obj_bs` 映射成“锚点可用”，语义已经错位。 |
| `rebuild4/frontend/src/pages/FlowSnapshotPage.vue` | `rebuild4_meta.batch` + `batch_snapshot` | 有数据 | 完全不可用 | 页面把 `snapshots` 数组当成对象取第 1 行（`[0]`），并使用 `raw_count` / `governed` / `cell_count` / `baseline_version` 这组并不存在的 metric 名；实际数据库存的是 `fact_standardized` / `fact_governed` / `obj_cell` / `baseline_cell` 等。结果是表格几乎全空。 |
| `rebuild4/frontend/src/pages/RunBatchCenterPage.vue` | `rebuild4_meta.run` / `batch` / `batch_flow_summary` / `batch_snapshot` / `batch_transition_summary` / `baseline_refresh_log` | 有数据 | 有数据但展示不完整 | 设计要求批次列表、趋势、批次详情、晋升/降级。当前前端读 `b.governed` / `b.pending_observation` 等字段，但后端返回的是 `governed_count` / `pending_observation_count` 等；四路分布条会失真，详情页也把 `metric_name`/`metric_value`、`from_state`/`to_state` 错当成 `metric`/`value`、`from`/`to`。 |
| `rebuild4/frontend/src/pages/ObjectsPage.vue` | `rebuild4.obj_cell` / `obj_bs` / `obj_lac` | 有数据 | 有数据但展示不完整 | 页面确实能列出对象，但筛选/分页契约漂移：前端发 `page_size/search/lifecycle_state/health_state`，后端收 `size/q/lifecycle/health`；`total` 也从 `context.total` 漂成了 `res.total`。因此搜索、过滤、翻页基本失效。 |
| `rebuild4/frontend/src/pages/ObjectDetailPage.vue` | `rebuild4.obj_*` + `rebuild4_meta.obj_state_history` + `obj_relation_history` + `batch_anomaly_object_summary` | 主对象表有数据；`obj_state_history`、`obj_relation_history` 空表 | 有数据但展示不完整 | 页面只能看到基础对象字段和部分异常；设计要求的“状态时间线/事实分布/资格原因/下游影响”没有闭环。即使后端返回了 `lifecycle_state`/`health_state`/`changed_at`，前端仍按 `state`/`timestamp`/`reason` 读取，时间线字段对不上。 |
| `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue` | `rebuild4_meta.observation_workspace_snapshot` | 表有数据，但当前批次视角等价空表 | 完全不可用 | 当前表只有 `BATCH-INIT-001` 快照，`workspaces.py` 却按 `current_pointer.current_batch_id = BATCH-ROLL-003` 过滤，结果当前页面为空。同时前端还在发 `status/progression/page_size`，后端只认 `lifecycle/missing_qual/size`；前端字段 `l1_exist/l2_anchor/l3_baseline` 也和正式 read model 的 `existence_progress/anchorable_progress/baseline_progress` 不一致。 |
| `rebuild4/frontend/src/pages/AnomalyWorkspacePage.vue` | `rebuild4_meta.batch_anomaly_object_summary` / `batch_anomaly_record_summary` / `batch_anomaly_impact_summary` / `rebuild4.fact_rejected` | 有数据 | 有数据但展示不完整 | 对象级异常主表可出结果，但类型过滤参数错了（前端发 `anomaly_type`，后端收 `type`）；展开行把 `affected_object_key`/`impact_type` 错读成 `impact_key`/`effect`。记录级视图更严重：后端已经按类型聚合了 `affected_rows/new_rows_current_batch/fact_destination`，前端却再次按“行数”重聚合，完全丢失真实统计。 |
| `rebuild4/frontend/src/pages/BaselineProfilePage.vue` | `rebuild4_meta.baseline_version` / `baseline_refresh_log` / `baseline_diff_summary` / `baseline_diff_object` / `rebuild4.obj_cell` | `baseline_version`/`baseline_refresh_log`/`baseline_diff_summary` 有数据；`baseline_diff_object` 空表 | 完全不可用 | 后端 `baseline/current` 返回的是 `{version, stability, coverage}` 结构，前端却直接读取 `current.run_id/current.batch_id/current.trigger_type` 等扁平字段；稳定性分数应该读 `current.stability.stability_score`，前端却读 `current.stability_score`。因此页面会出现大量空值，甚至 `current.version` 会变成对象。 |
| `rebuild4/frontend/src/pages/LacProfilePage.vue` | `rebuild4.etl_dim_lac` | 有数据 | 正常可用 | 作为“画像聚合页”基本能看，但它已经偏离原 `obj_lac` 设计：没有 `health_state`、`anchorable`、`baseline_eligible`、`fact_*` 去向构成，也没有基线参照。 |
| `rebuild4/frontend/src/pages/BsProfilePage.vue` | `rebuild4.etl_dim_bs` + `rebuild4.etl_dim_bs_centroid` | 有数据 | 正常可用 | 画像展示基本成立，但它不是设计稿中的对象工作台 BS 页：缺 `health_state`、`baseline_eligible`、事实分流和 baseline 关联；展示的是 `classification`/`position_grade` 这套画像口径。 |
| `rebuild4/frontend/src/pages/CellProfilePage.vue` | `rebuild4.etl_dim_cell` | 有数据 | 正常可用 | 这是当前最完整的一页，但仍与设计稿不同：没有 `health_state`、`baseline_eligible`、baseline 对照、四路事实去向。另一个小问题是前端还保留了 `low_collision` 过滤项，而 `profile.py` 已不再产出该分类。 |
| `rebuild4/frontend/src/pages/GovernancePage.vue` | `rebuild4_meta.asset_*` / `field_audit_snapshot` / `target_field_snapshot` / `ods_*` / `parse_rule` / `compliance_rule` / `trusted_loss_*` | 有数据 | 有数据但展示不完整 | 大部分 tab 能出通用表格，但概览卡字段有漂移：后端给 `usage_registrations` / `migration_decisions`，前端却读 `usage_count` / `migration_pending`。`trusted_loss` tab 还把 `breakdown_type` 写成了不存在的 `breakdown`，并把 `trusted_rows/filtered_pct/filtered_with_rsrp` 错读成 `trusted/pct/with_signal`。 |
| `rebuild4/frontend/src/pages/EtlRegisterPage.vue` | `rebuild4.sample_raw_gps` / `sample_raw_lac` + 静态 `RAW_FIELDS` | 有数据 | 正常可用 | 和设计基本一致。 |
| `rebuild4/frontend/src/pages/EtlAuditPage.vue` | `rebuild2_meta.target_field` | 有数据 | 正常可用 | 和设计基本一致。 |
| `rebuild4/frontend/src/pages/EtlParsePage.vue` | `rebuild4_meta.etl_run_stats` + `rebuild4.etl_parsed` | 有数据 | 正常可用 | 和设计基本一致。 |
| `rebuild4/frontend/src/pages/EtlCleanPage.vue` | `rebuild4_meta.etl_run_stats.clean_rules` | 有数据 | 正常可用 | 和设计基本一致。 |
| `rebuild4/frontend/src/pages/EtlFillPage.vue` | `rebuild4.etl_cleaned` / `rebuild4.etl_filled` + `etl_run_stats` | 有数据 | 正常可用 | 和设计基本一致。 |
| `rebuild4/frontend/src/pages/ValidationComparePage.vue` | `rebuild4_meta.compare_job` / `compare_result` | 空表 | 完全不可用 | 当前数据库没有 compare job，页面天然无结果；即使将来有结果，前端也仍然按 `total_compared/route_diffs/object_diffs` 聚合结构读取，而后端实际返回的是逐条 `results` 列表。 |

### 补充：设计稿中已退场的页面

- `rebuild4/docs/01_inputs/03_ui_v2/pages/12_initialization_doc.md` 仍保留“初始化数据页”设计，
- 但 `rebuild4/frontend/src/router.ts` 已没有对应路由，`frontend/src/pages/` 里也没有 `InitializationPage.vue`。

这不是 bug，而是 `rebuild4/docs/02_profile/06_流式评估.md` 决策后的**有意删除**；但它也意味着现在首页仍在消费 `initialization_step_log`，属于“页面已退、遗留视图还在”的过渡态。

---

## 四、四个核心问题的具体分析

## 问题 1：流转可视化断裂

### 现状判断

#### `flow.py` / `FlowOverviewPage.vue` / `FlowSnapshotPage.vue`

- `rebuild4/backend/app/routers/flow.py` 的数据源并不为空：
  - `rebuild4_meta.batch_flow_summary`
  - `rebuild4_meta.batch_snapshot`
  - `rebuild4_meta.batch_transition_summary`
  - `rebuild4_meta.batch_anomaly_object_summary`
  - `rebuild4_meta.initialization_step_log`
- 但这里的 `batch_snapshot` 是**fact/object/baseline 的批次快照**，不是 `etl_dim_*` 画像的版本快照。
- `batch_transition_summary` 当前只记录 `NULL -> governed/pending_observation/pending_issue/rejected` 的路由计数，**不记录 waiting→observing→active 的对象状态变化**。
- `FlowSnapshotPage.vue` 前端还把 `snapshots` 数组当成对象读取，因此即使数据库有 44 行快照，页面仍无法正确显示。

#### `ObservationWorkspacePage.vue`

- 正式数据源是 `rebuild4_meta.observation_workspace_snapshot`；这点与 `rebuild4/docs/03_final/02_数据生成与回灌策略.md:287` 的合同一致。
- 但数据库里只有 `BATCH-INIT-001` 这一版快照，当前 rolling 批次没有刷新。
- 因此这不是“表不存在”，而是**read model 已经与 current batch 脱节**。

### 根因分析

1. `rebuild4/backend/app/etl/profile.py` 只负责从 `rebuild4.etl_filled` DROP + CREATE `etl_dim_*`，不产出任何“差分事件”或“状态迁移历史”。
2. 主流程页面仍按旧设计假设：
   - 每个 completed batch 都会生成对象状态推进、观察工作台推进、baseline 刷新决策、异常影响链。
3. 当前数据库里，`run/batch/batch_snapshot/batch_flow_summary/batch_anomaly_*` 这套数据仍由另一条 rolling 合同维护；但 `observation_workspace_snapshot` 没跟上，`batch_transition_summary` 也只剩路由分流，不再是真正状态转移。
4. 前端页面又发生了第二层断裂：即使底表有数据，也因为字段名漂移而无法正确展示。

### 影响范围

- 首页 `rebuild4/frontend/src/pages/FlowOverviewPage.vue`
- 流转快照 `rebuild4/frontend/src/pages/FlowSnapshotPage.vue`
- 运行/批次中心 `rebuild4/frontend/src/pages/RunBatchCenterPage.vue`
- 等待/观察工作台 `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue`
- 对象详情中的状态历史 `rebuild4/frontend/src/pages/ObjectDetailPage.vue`

### 建议方案

#### 方案 A（我建议先做）：先重定义页面定位，不先强行补增量

- **首页/批次中心/异常页保留**，继续消费 `rebuild4_meta.batch_*`、`batch_anomaly_*` 这套已存在的批次视图；
- **观察工作台、流转快照先降级或隐藏**，直到 read model 恢复可持续刷新；
- **Cell/BS/LAC 画像页明确声明它们展示的是“全量当前画像快照”**，不再暗示它们具备批次级时序回放能力。

落地文件：

- `rebuild4/frontend/src/router.ts`
- `rebuild4/frontend/src/App.vue`
- `rebuild4/frontend/src/pages/FlowSnapshotPage.vue`
- `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue`
- `rebuild4/frontend/src/pages/BaselineProfilePage.vue`

#### 方案 B（第三阶段再做）：在 `profile.py` 外围补一个“差分 read model 层”

不改 `rebuild4/backend/app/etl/profile.py` 的 6 步 SQL，只在它前后加一层物化：

- 新增 `rebuild4_meta.profile_build_log`
- 新增 `rebuild4_meta.profile_cell_snapshot`（可选）
- 新增 `rebuild4_meta.profile_cell_diff`（可选）
- 每次重建后对比上一版 `etl_dim_cell` / `etl_dim_bs` / `etl_dim_lac`，再生成：
  - `rebuild4_meta.observation_workspace_snapshot`
  - `rebuild4_meta.batch_transition_summary`
  - `rebuild4_meta.obj_state_history`

这样可以保留 `profile.py` 的正确实现，又让工作台恢复“批次推进”语义。

### 优先级

**P0**

原因：当前默认首页和工作台主路径已经失真，用户进入系统后无法顺畅完成“看当前状态 → 找异常 → 看观察候选 → 回到版本上下文”这条核心路径。

---

## 问题 2：数据版本管理缺失

### 哪些 `rebuild4_meta` 表仍在使用

### 实际在用且有数据的表

- `run`
- `batch`
- `current_pointer`
- `contract_version`
- `rule_set_version`
- `batch_flow_summary`
- `batch_snapshot`
- `batch_transition_summary`（但语义已弱化）
- `batch_anomaly_object_summary`
- `batch_anomaly_record_summary`
- `batch_anomaly_impact_summary`
- `baseline_version`
- `baseline_refresh_log`
- `observation_workspace_snapshot`（但只有 init 批次）
- `etl_run_stats`
- `asset_field_catalog` / `asset_table_catalog` / `asset_usage_map` / `asset_migration_decision`
- `field_audit_snapshot` / `target_field_snapshot` / `ods_rule_snapshot` / `ods_execution_snapshot`
- `parse_rule` / `compliance_rule`
- `trusted_loss_summary` / `trusted_loss_breakdown`
- `gate_run_result`
- `initialization_step_log`

### 已成空壳或接近空壳的表

- `compare_job`：空表
- `compare_result`：空表
- `obj_state_history`：空表
- `obj_relation_history`：空表
- `baseline_diff_object`：空表
- `baseline_diff_summary`：只有 `v1` 对空前版的 added_count，**不能支撑真正 diff 页面**
- `observation_workspace_snapshot`：只有初始化批次，**不能支撑 current batch 工作台**
- `batch_transition_summary`：只有四路路由计数，**不能支撑“状态转移中心”语义**

### `RunBatchCenterPage.vue` 当前是否能正常显示

不能正常显示，只能算“底层数据有，前台消费坏了”。

原因有两层：

1. **后端数据本身是有的**：`run` 2 行、`batch` 4 行、`batch_flow_summary` 4 行、`batch_snapshot` 44 行。
2. **前端字段契约错误**：
   - 后端给 `governed_count/pending_observation_count/pending_issue_count/rejected_count`
   - 前端读 `governed/pending_observation/pending_issue/rejected`
   - 后端给 `metric_name/metric_value`、`from_state/to_state/transition_count`
   - 前端读 `metric/value`、`from/to/count`

所以页面看起来像“数据不完整”，本质是**接口已变、前端没同步**。

### 根因分析

1. `rebuild4/backend/app/etl/profile.py` 完全绕开 `run_id` / `batch_id` / `rule_set_version` / `baseline_version` 的注册流程。
2. `rebuild4/backend/app/etl/pipeline.py` 只把结果写进 `rebuild4_meta.etl_run_stats`，没有给 `etl_dim_*` 建立任何版本登记。
3. 前端主流程页继续假设“所有关键结果都能被 `run/batch` 体系解释”，而 `etl_dim_*` 这条新链路没有接入这个体系。

### 是否需要让 `profile.py` 每次运行时注册 run + batch

**结论：需要有版本登记，但不建议把 run/batch 注册逻辑直接塞进 `profile.py` 本体。**

更合理的做法是：

- 保持 `rebuild4/backend/app/etl/profile.py` 只做“纯画像构建”；
- 在触发层（例如 `rebuild4/backend/app/etl/pipeline.py` 或一个新的 orchestrator）做版本登记；
- 如果画像构建是跟随 ETL 运行，就**复用 ETL 所属的 `run_id` / `batch_id`**；
- 如果画像构建是单独手动运行，再单独登记一条 `profile_rebuild` 类型的运行记录。

这样能保留 `profile.py` 的简洁性，同时让系统知道：

- 这次 `etl_dim_*` 来自哪次 `etl_filled`
- 绑定了哪个 `contract_version`
- 绑定了哪个 `rule_set_version`
- 绑定了哪个 `baseline_version`

### 数据版本管理的最小可行方案（MVP）

我建议的最小方案如下：

#### MVP-1：不版本化整张 `etl_dim_*` 历史表，只先记录 build manifest

新增一张轻量表，例如：

- `rebuild4_meta.profile_build_log`

最少字段：

- `profile_build_id`
- `run_id`
- `batch_id`
- `contract_version_id`
- `rule_set_version_id`
- `baseline_version`
- `source_table`（固定 `rebuild4.etl_filled`）
- `source_row_count`
- `cell_count`
- `bs_count`
- `lac_count`
- `built_at`

#### MVP-2：当前快照只保留一份实体表，但要能回指版本

在 `etl_dim_cell` / `etl_dim_bs` / `etl_dim_lac` 增加统一元字段（或维护 companion pointer 表）：

- `profile_build_id`
- `built_at`

这样前端至少能解释“你现在看到的画像是哪个 build”。

#### MVP-3：前端版本上下文统一从一个地方取

- `rebuild4/backend/app/core/context.py`
- `rebuild4_meta.current_pointer`
- `rebuild4_meta.profile_build_log`

统一生成“当前运行/当前批次/当前基线/当前画像 build/当前规则版本”上下文条。

### 优先级

**P1**

原因：它不会像首页损坏那样立刻阻断浏览，但它直接影响可解释性、可追溯性和后续所有参数管理。

---

## 问题 3：参数与画像耦合

### 代码中当前硬编码的主要参数

`rebuild4/backend/app/etl/profile.py` 当前至少硬编码了以下几类阈值：

1. **漂移/碰撞阈值**
   - `stable < 500m`
   - `collision >= 2200m`
   - `migration >= 2200m 且 net/max >= 0.7`
   - `large_coverage = 500m~2200m`
2. **生命周期阈值**
   - `independent_obs >= 3`
   - `distinct_dev_id >= 2`
   - `p90_radius_m < 1500`
   - `observed_span_hours >= 24`
3. **anchorable 阈值**
   - `gps_valid_count >= 10`
   - `distinct_dev_id >= 2`
   - `p90_radius_m < 1500`
   - `observed_span_hours >= 24`
4. **质量/规模分桶**
   - `position_grade`
   - `gps_confidence`
   - `signal_confidence`
   - `cell_scale`
5. **BS/LAC 分类阈值**
   - `dist_to_bs_m > 2500 -> large_spread`
   - `drift_max_spread_m > 1500 -> is_dynamic`

### 哪些参数应该外部化

### 应保留为“核心算法常量”的部分

这些参数直接对应研究结论，短期不建议做成操作型 UI 可调项：

- 1 分钟独立观测去重策略
- 中位数质心 (`PERCENTILE_CONT(0.5)`) 而不是 AVG
- 日质心漂移分析框架
- `stable=500m` / `collision=2200m` 这一组“几何分段”

原因：这些不是业务策略，而是算法定义；一旦改动，等于换了画像算法版本。

### 应外部化为“策略阈值”的部分

这些更像业务判定门槛，适合独立版本化：

- lifecycle 的 `obs/dev/P90/span` 门槛
- `anchorable` 的 `gps_valid/dev/P90/span` 门槛
- `position_grade` 分桶
- `gps_confidence` / `signal_confidence` 分桶
- `cell_scale` 分桶
- `BS large_spread` 的 2500m 门槛

### 参数变更后是否需要全量重算

### 必须全量重算的情况

如果改的是这些参数，必须从 `rebuild4.etl_filled` 重新跑画像：

- 独立观测定义
- 质心算法
- 原始 GPS/信号有效性边界
- 漂移分析基本方法

### 可以局部重算/重物化的情况

如果改的是这些“判定阈值”，理论上可以只重算标签层：

- lifecycle_state
- anchorable
- position_grade
- gps_confidence
- signal_confidence
- cell_scale
- BS/LAC 的聚合标签与统计

因为 `etl_dim_cell` 已经保留了：

- `independent_obs`
- `distinct_dev_id`
- `observed_span_hours`
- `gps_valid_count`
- `p90_radius_m`
- `drift_max_spread_m`
- `drift_net_m`
- `drift_days`

也就是说，**很多策略变更不必回到 `etl_filled`，只需基于现有画像做一次轻量 rematerialize。**

但当前实现没有单独的“标签重算层”，所以实际操作上仍只能整跑 `profile.py`。这是架构上应该补的一层。

### 参数配置 UI 应该放在哪里

我建议放在**治理/版本上下文**里，而不是放在 Cell/BS/LAC 画像页里：

#### 第一选择

- `rebuild4/frontend/src/pages/GovernancePage.vue`
- 新增一个 `画像规则` / `Profile Rules` tab

理由：

- 参数本质是规则版本的一部分；
- 修改后影响全局，而不是某个页面本地筛选；
- 最适合和 `rebuild4_meta.rule_set_version` 绑定。

#### 第二选择（只读镜像）

- `rebuild4/frontend/src/pages/RunBatchCenterPage.vue`

在运行上下文区展示“当前生效阈值摘要”，但不在这里编辑。

### 建议方案

- 新增轻量配置实体，例如：
  - `rebuild4_meta.profile_rule_set`
  - 或直接给 `rebuild4_meta.rule_set_version` 挂一个 JSON 配置
- 让 `profile.py` 在运行时读取“当前 profile rule set”，而不是把所有阈值写死在 SQL 里
- 前端先做**只读展示**，不要一步做到在线编辑
- 真要编辑时，必须创建新 `rule_set_version`，并触发新一次 profile build，而不是直接热修改当前值

### 优先级

**P1**

原因：它不阻断页面打开，但它是后续版本管理、解释能力和实验复现的前提。

---

## 问题 4：整体架构一致性

### 现状判断

当前系统分成三块：

#### A. ETL 基础链路（最完整）

- `rebuild4/backend/app/etl/pipeline.py`
- `rebuild4/backend/app/routers/governance_foundation.py`
- `rebuild4/frontend/src/pages/Etl*.vue`

这一层最完整，数据库也有真实数据支撑。

#### B. 画像链路（次完整）

- `rebuild4/backend/app/etl/profile.py`
- `rebuild4/backend/app/routers/profiles.py`
- `rebuild4/frontend/src/pages/CellProfilePage.vue`
- `rebuild4/frontend/src/pages/BsProfilePage.vue`
- `rebuild4/frontend/src/pages/LacProfilePage.vue`

这一层能工作，但它是“全量当前画像”，不是“批次治理工作台”。

#### C. 主流程工作台（最不一致）

- `rebuild4/backend/app/routers/flow.py`
- `rebuild4/backend/app/routers/runs.py`
- `rebuild4/backend/app/routers/objects.py`
- `rebuild4/backend/app/routers/workspaces.py`
- `rebuild4/backend/app/routers/baseline.py`
- `rebuild4/backend/app/routers/compare.py`
- 对应多个 `.vue` 页面

这一层的问题不是“没建表”，而是：

- 有些 read model 还在（`batch_*`、`anomaly_*`）
- 有些 read model 停在初始化（`observation_workspace_snapshot`）
- 有些 read model 空表（`compare_*`、`obj_state_history`）
- 多个前端页面又和后端契约漂移

### 从用户视角，当前系统能完成什么 / 不能完成什么

### 用户现在能完成的流程

1. 打开 ETL 页面，了解原始数据、字段审计、解析/清洗/补齐统计
2. 打开 Cell/BS/LAC 页面，浏览当前画像聚合结果
3. 打开异常页对象 tab，查看当前批次对象异常的大致列表
4. 打开对象浏览页，粗略浏览 `obj_*` 表里的对象（但筛选/翻页体验有问题）

### 用户现在不能可靠完成的流程

1. **首页进入后看清“当前批次发生了什么”**
   - 首页指标标签已经错位
2. **比较不同批次快照**
   - `FlowSnapshotPage.vue` 基本不可用
3. **查看当前 waiting/observing 候选推进**
   - `ObservationWorkspacePage.vue` 当前批次为空
4. **查看 baseline 版本与差异**
   - baseline 页前后端结构不匹配，且只有 1 个版本
5. **查看对象状态演进历史**
   - `obj_state_history` / `obj_relation_history` 空表
6. **做验证/对照**
   - compare 表为空，前端结构也不匹配

### 根因分析

根因不是单点 bug，而是**主路径页面没有围绕一个统一的“当前 truth source”收敛**。

### 建议方案

#### 统一“当前权威语义”

我建议明确分层：

- **ETL 与当前画像**：以 `etl_*` / `etl_dim_*` 为准
- **批次工作台与异常**：以 `run/batch/batch_*` / `batch_anomaly_*` 为准
- **对象页是否保留 `obj_*`**：必须明确。如果保留，就要继续物化并修完页面；如果不保留，就应逐步让对象浏览/详情页切到 `etl_dim_*` + 新 read model

当前最危险的是既保留 `obj_*`，又让画像页走 `etl_dim_*`，但中间没有桥。

### 优先级

**P0**

因为这已经不是“可优化的一致性”，而是“用户打开系统后看到的是哪套世界”的问题。

---

## 五、整体重构建议（分阶段）

## 第一阶段（必须做）：先让系统从用户视角可用

### 目标

让用户至少能完成一条闭环：

**首页看当前状态 → 批次中心看批次 → 对象/异常页看明细 → 画像页看当前画像。**

### 必做项

1. **修正前后端契约漂移**
   - `rebuild4/frontend/src/pages/FlowSnapshotPage.vue`
   - `rebuild4/frontend/src/pages/RunBatchCenterPage.vue`
   - `rebuild4/frontend/src/pages/ObjectsPage.vue`
   - `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue`
   - `rebuild4/frontend/src/pages/AnomalyWorkspacePage.vue`
   - `rebuild4/frontend/src/pages/BaselineProfilePage.vue`
   - `rebuild4/frontend/src/pages/GovernancePage.vue`
   - `rebuild4/frontend/src/pages/ValidationComparePage.vue`
   - `rebuild4/frontend/src/lib/api.ts`

2. **短期下线或隐藏当前必然空/必然错的页面功能**
   - `FlowSnapshotPage.vue`
   - `ObservationWorkspacePage.vue`
   - `ValidationComparePage.vue`
   - `BaselineProfilePage.vue` 的 diff 区块

3. **首页收敛到真实可解释的数据**
   - `rebuild4/backend/app/routers/flow.py`
   - `rebuild4/frontend/src/pages/FlowOverviewPage.vue`
   - 不再把 `obj_cell` 直接称为“活跃对象”，不再把 `obj_bs` 直接称为“锚点可用”

4. **批次中心收敛到真实字段**
   - `rebuild4/backend/app/routers/runs.py`
   - `rebuild4/frontend/src/pages/RunBatchCenterPage.vue`

5. **把对象页和画像页的定位写清楚**
   - 对象页 = `obj_*` 工作台对象
   - 画像页 = `etl_dim_*` 当前全量画像

### 完成标准

- 首页不再语义错位
- 运行/批次中心能正确显示四路分布和详情
- 对象浏览能正确筛选和翻页
- 异常页对象 tab 能正确过滤和展开影响
- 明确标识哪些页面是“暂不可用/待后续恢复”

---

## 第二阶段（应该做）：补最小数据版本与参数管理

### 目标

把“当前看到的画像”与“哪个 run/batch/rule_set/baseline 产出的”重新绑定。

### 建议项

1. 新增 `rebuild4_meta.profile_build_log`
2. 给 `etl_dim_*` 增加 `profile_build_id` 或 companion pointer
3. 给 `rule_set_version` 绑定一份 profile 参数快照（JSON 即可）
4. 在 `rebuild4/frontend/src/pages/GovernancePage.vue` 增加“画像规则/参数版本”tab
5. 在 `rebuild4/frontend/src/pages/RunBatchCenterPage.vue` 展示当前 rule set / profile build 摘要

### 完成标准

- 能回答“当前画像来自哪一次构建”
- 能回答“当前阈值是什么”
- 参数变更后能留下版本痕迹

---

## 第三阶段（可以做）：完善流转可视化与增量观察能力

### 目标

如果项目后续仍然需要真正的“流转/观察/批次推进”体验，再补 read model，而不是改坏 `profile.py` 本体。

### 建议项

1. 在 `profile.py` 外围增加差分物化层
2. 让每次画像构建都能生成：
   - `rebuild4_meta.observation_workspace_snapshot`
   - `rebuild4_meta.batch_transition_summary`（真正状态转移版）
   - `rebuild4_meta.obj_state_history`
3. 如果确有需要，再新增：
   - `rebuild4_meta.profile_cell_diff`
   - `rebuild4_meta.profile_bs_diff`
   - `rebuild4_meta.profile_lac_diff`
4. 恢复：
   - `rebuild4/frontend/src/pages/FlowSnapshotPage.vue`
   - `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue`
   - `rebuild4/frontend/src/pages/ObjectDetailPage.vue` 的状态历史区块

### 完成标准

- 观察工作台能看当前批次推进
- 流转快照能比较批次差异
- 对象详情能解释状态什么时候变化

---

## 六、我给出的最终判断

### 最重要的判断 1

**当前系统最大的结构性问题，不是 `profile.py` 算错了，而是 `profile.py` 正确地做成了“全量当前画像”，但工作台其余部分还停留在“按批次推进的治理界面”思维。**

### 最重要的判断 2

**短期最优策略不是把 `profile.py` 改回增量流式，而是先把页面和已有数据契约对齐，明确哪些页面展示“当前画像”、哪些页面展示“批次治理”。**

### 最重要的判断 3

**如果后续确实需要观察工作台/流转快照这类页面，就应该在 `profile.py` 外面补“差分 read model 层”，而不是把已经验证正确的画像主算法重新搅乱。**
