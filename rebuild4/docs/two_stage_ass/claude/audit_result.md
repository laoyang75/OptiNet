# 流式架构审计 — Claude 独立评估结果

> 审计时间: 2026-04-08  
> 审计员: Claude (独立评审)  
> 代码基线: main 分支 commit dfede02  

---

## 一、现状诊断报告

### 数据库实际状态概览

审计发现数据库远比预期丰富。系统已执行了完整的初始化 + 3 批滚动治理：

| 数据层 | 关键表 | 行数 | 状态 |
|--------|--------|------|------|
| ETL 管道 | `rebuild4.etl_filled` | 687,788 | ✅ 完整 |
| Cell 画像 | `rebuild4.etl_dim_cell` | 20,394 | ✅ 完整 |
| BS 画像 | `rebuild4.etl_dim_bs` | 11,942 | ✅ 完整 |
| LAC 画像 | `rebuild4.etl_dim_lac` | 1,270 | ✅ 完整 |
| 治理对象 | `rebuild4.obj_cell` | 1,286,825 | ✅ 有数据 (来自 G2 初始化) |
| 治理对象 | `rebuild4.obj_bs` / `obj_lac` | 228,536 / 13,480 | ✅ 有数据 |
| 事实路由 | `rebuild4.fact_standardized` | 82,205,035 | ✅ 有数据 |
| 事实路由 | `rebuild4.fact_governed` | 67,963,244 | ✅ 有数据 |
| 事实路由 | `rebuild4.fact_pending_observation` | 9,493,333 | ✅ 有数据 |
| 事实路由 | `rebuild4.fact_rejected` | 4,746,997 | ✅ 有数据 |
| 运行/批次 | `rebuild4_meta.run` / `batch` | 2 / 4 | ✅ 有数据 |
| 流转摘要 | `rebuild4_meta.batch_flow_summary` | 4 | ✅ 有数据 |
| 快照 | `rebuild4_meta.batch_snapshot` | 44 | ✅ 有数据 |
| 观察工作台 | `rebuild4_meta.observation_workspace_snapshot` | 50,000 | ✅ 有数据 |
| 异常摘要 | `rebuild4_meta.batch_anomaly_object_summary` | 1,600 | ✅ 有数据 |
| 基线 | `rebuild4.baseline_cell` / `baseline_bs` / `baseline_lac` | 550,219 / 228,536 / 13,480 | ✅ 有数据 |
| 基线版本 | `rebuild4_meta.baseline_version` | 1 (v1) | ✅ 有数据 |
| 基线差异 | `rebuild4_meta.baseline_diff_summary` / `diff_object` | 3 / 0 | ⚠️ 仅首版，无对象级差异 |
| 对象状态历史 | `rebuild4_meta.obj_state_history` | 0 | ❌ 空表 |
| 对比 | `rebuild4_meta.compare_job` | 0 | ❌ 空表 |
| 治理元数据 | `rebuild4_meta.asset_field_catalog` 等 | 各表有数据 | ✅ 已种子 |

运行记录：
- `RUN-INIT-001` (full_initialization, completed, 2026-04-06 12:14)
- `RUN-ROLL-001` (rolling, completed, 2026-04-06 13:29) — 含 3 个批次 (BATCH-ROLL-001/002/003)
- `current_pointer` 指向 `RUN-ROLL-001 / BATCH-ROLL-003`

---

### 各页面逐项诊断

#### 1. FlowOverviewPage (`/flow-overview`) — 流转总览

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`batch_flow_summary` 4行，`batch_snapshot` 44行，`batch_transition_summary` 16行 |
| **功能状态** | ⚠️ **部分可用**。四路事实路由数据完整（standardized 8200万 → governed 6796万 + pending_obs 949万 + pending_issue 1461 + rejected 475万）。Delta 对比可工作（有前后批次）。但 `batch_anomaly_object_summary` 的 column 名可能与前端期望字段不完全对齐 |
| **与原设计偏差** | 原设计期望高频滚动（24批/天），当前仅 4 批次。流程图 13 步指标仅部分有快照数据覆盖。初始化步骤日志完整（11步），但流程图中某些阶段可能缺少对应 `stage_name` 的快照 |

#### 2. FlowSnapshotPage (`/flow-snapshot`) — 流转快照

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。44 条快照记录，4 个时间点可选 |
| **功能状态** | ⚠️ **部分可用**。初始化快照存在 (`BATCH-INIT-001`)，可与滚动批次对比。但三列对比设计（init + A + B）需要至少 3 个时间点，当前有 4 个，刚好满足 |
| **与原设计偏差** | 设计期望大量时间点形成趋势，当前仅 4 个点。A/B 对比功能可用但选择范围有限 |

#### 3. RunBatchCenterPage (`/runs`) — 运行/批次中心

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。2 个 run，4 个 batch，均为 completed |
| **功能状态** | ✅ **基本可用**。Run 列表、Batch 子列表、四路分布迷你条形图所需数据完整。批次详情面板有快照和转换摘要 |
| **与原设计偏差** | `contract_version` 和 `rule_set_version` 的 JOIN 正常（各 1 条记录）。缺少 `baseline_refresh_log` 的展示（有 4 条记录但可能未关联到具体批次详情面板） |

#### 4. ObjectsPage (`/objects`) — 对象浏览

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`obj_cell` 128万行，`obj_bs` 22.8万，`obj_lac` 1.3万 |
| **功能状态** | ⚠️ **需验证**。后端 `objects.py` 查询 `rebuild4.obj_cell/obj_bs/obj_lac`，这些表有完整数据（lifecycle/health 分布正常：active+healthy 53.4万，observing+insufficient 55.7万等）。但前端期望的字段（如 `qualification_flags`, `watch_state`）需要确认表结构是否包含这些列 |
| **与原设计偏差** | 原设计的 `health` 筛选、`qualification` 标签、`watch` 状态——需确认 `obj_*` 表是否有这些列。`obj_state_history` 为空（0行），所以对象详情页的"状态时间线"不可用 |

#### 5. ObjectDetailPage (`/objects/:type/:id`) — 对象详情

| 维度 | 评估 |
|------|------|
| **数据源状态** | ⚠️ 部分有数据。对象基本信息有数据，但 `obj_state_history`=0行，`obj_relation_history` 未检查 |
| **功能状态** | ⚠️ **部分可用**。基本信息卡可展示，但状态时间线为空，下游关系可能为空 |
| **与原设计偏差** | 设计期望完整的状态历史和关系图，当前仅有基本属性 |

#### 6. ObservationWorkspacePage (`/observation-workspace`) — 观察工作台

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`observation_workspace_snapshot` 50,000行，全部 `lifecycle_state=observing` |
| **功能状态** | ⚠️ **需验证**。后端 `workspaces.py` 查询此表，前端期望 `existence_progress/anchorable_progress/baseline_progress` 等字段，表结构确认包含这些列。但前端的 `status` 筛选器对应后端的 `lifecycle_state` 列——可能存在字段名映射问题 |
| **与原设计偏差** | 三层资格进度数据结构完整。但 `trend_direction`、`stall_batches` 等实际值需验证是否有有意义的非零分布。50K 行全为 observing，缺少 waiting 状态的对象 |

#### 7. AnomalyWorkspacePage (`/anomaly-workspace`) — 异常工作台

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`batch_anomaly_object_summary` 1,600行（4类异常），`batch_anomaly_record_summary` 14行 |
| **功能状态** | ⚠️ **需验证**。对象级异常有分布（gps_bias 600, migration_suspect 500, collision_suspect 500, gps_bias/medium 100）。记录级异常较少。Impact 钻取依赖 `batch_anomaly_impact_summary`——未确认此表数据量 |
| **与原设计偏差** | 基本对齐设计意图。severity 分布存在，anomaly_type 分类与设计匹配 |

#### 8. BaselineProfilePage (`/baseline`) — 基线/画像

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`baseline_version` 1行 (v1)，`baseline_diff_summary` 3行，`baseline_refresh_log` 4行 |
| **功能状态** | ⚠️ **部分可用**。当前版本信息可展示，触发原因可展示。但稳定性评分查询 `obj_cell` 的 stability 字段——需确认。Diff 部分：仅首版（previous=null），所以"对比上一版"不可用。版本历史仅 1 行 |
| **与原设计偏差** | 设计期望多版本基线形成趋势和差异对比，当前仅 v1 单版本 |

#### 9. CellProfilePage (`/profiles/cell`) — Cell 画像

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`etl_dim_cell` 20,394行。lifecycle 分布：active 5,920, observing 607, waiting 13,867 |
| **功能状态** | ✅ **正常可用**。8 种筛选器、7 张摘要卡、可展开详情——数据完整。drift 分析、position_grade、cell_scale 等字段均由 profile.py 生成 |
| **与原设计偏差** | 与 ETL 画像设计完全对齐。这是系统中功能最完整的页面之一 |

#### 10. BsProfilePage (`/profiles/bs`) — BS 画像

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`etl_dim_bs` 11,942行，`etl_dim_bs_centroid` 有多质心数据 |
| **功能状态** | ✅ **正常可用**。筛选、摘要卡、多质心展开详情均有数据支撑 |
| **与原设计偏差** | 完全对齐 |

#### 11. LacProfilePage (`/profiles/lac`) — LAC 画像

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`etl_dim_lac` 1,270行 |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

#### 12. GovernancePage (`/governance`) — 基础数据治理

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。11 个子标签的数据表全部有种子数据：field_catalog 1,214行, table_catalog 98行, field_audit 27行, target_field 55行, ods_rule 26行, ods_execution 24行, parse_rule 25行, compliance_rule 14行, trusted_loss_summary 1行, trusted_loss_breakdown 7行 |
| **功能状态** | ✅ **正常可用**。所有标签页均有数据可展示 |
| **与原设计偏差** | `asset_usage_map` 仅 6 行，`asset_migration_decision` 仅 10 行——覆盖不完整但可用 |

#### 13. ValidationComparePage (`/validation/compare`) — 验证对比

| 维度 | 评估 |
|------|------|
| **数据源状态** | ❌ 空表。`compare_job` = 0, `compare_result` = 0 |
| **功能状态** | ❌ **不可用**。页面会显示"不足两次可比运行，暂无对比结果" |
| **与原设计偏差** | 设计为高级验证功能，需要两次运行 + 手动触发对比。当前虽有 2 个 run，但未执行 compare job |

#### 14. EtlRegisterPage (`/etl/register`) — 数据登记

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。后端硬编码 27 个 RAW_FIELDS 决策 + 查询 sample_raw 表行数 |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

#### 15. EtlAuditPage (`/etl/audit`) — L0 审计

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。查询 `rebuild2_meta.target_field` (55行) |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

#### 16. EtlParsePage (`/etl/parse`) — ETL 解析

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据。`etl_run_stats` 6行，`etl_parsed` 有数据 |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

#### 17. EtlCleanPage (`/etl/clean`) — ETL 清洗

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据 |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

#### 18. EtlFillPage (`/etl/fill`) — ETL 填充

| 维度 | 评估 |
|------|------|
| **数据源状态** | ✅ 有数据 |
| **功能状态** | ✅ **正常可用** |
| **与原设计偏差** | 完全对齐 |

---

### 页面功能状态汇总

| 状态 | 页面 |
|------|------|
| ✅ 正常可用 (8) | CellProfile, BsProfile, LacProfile, Governance, EtlRegister, EtlAudit, EtlParse, EtlClean, EtlFill |
| ⚠️ 部分可用 (7) | FlowOverview, FlowSnapshot, RunBatchCenter, Objects, ObjectDetail, ObservationWorkspace, AnomalyWorkspace, Baseline |
| ❌ 不可用 (1) | ValidationCompare |

---

## 二、四个核心问题分析

### 问题 1: 流转可视化断裂

#### 根因分析

**原始假设错误——流转数据并非空壳。** 数据库中 `batch_flow_summary`(4行)、`batch_snapshot`(44行)、`batch_transition_summary`(16行) 均有真实数据，来自 G2 全量初始化 (RUN-INIT-001) 和 G3 滚动治理 (RUN-ROLL-001 含 3 批次)。

真正的问题不是"没有数据"，而是 **两套画像体系并存但不互通**：

1. **ETL 画像** (`etl_dim_cell/bs/lac`)：由 `profile.py` 从 `etl_filled` 构建，20,394 Cell，基于样本数据（~688K行）
2. **治理对象** (`obj_cell/bs/lac`)：由 G2 初始化从 `rebuild2.l0_gps/l0_lac` 构建，1,286,825 Cell，基于全量历史数据（82M 标准化事实）

这两套体系的对象数量级差异巨大（20K vs 128万），因为它们使用不同的数据源和不同的处理逻辑。flow/snapshot/workspace 页面读的是治理对象体系的数据，profiles 页面读的是 ETL 画像体系的数据。

#### 影响范围

- **FlowOverviewPage**: 展示的四路分布是治理体系的 82M 事实路由，与 ETL 画像的 688K 行无关
- **FlowSnapshotPage**: 快照对比的是治理批次指标，与画像构建无关
- **ObservationWorkspacePage**: 50K 条 observing 对象来自治理体系
- 用户如果从流转总览看到"128万 Cell"然后切到 Cell 画像看到"20,394 Cell"会产生困惑

#### 建议方案

这不是需要"修复"的 bug，而是需要 **明确两套体系的关系并在 UI 上清晰标注**：

1. **在侧边栏或页面标题中区分两个数据域**：
   - "ETL 画像"域：ETL 管道 + Cell/BS/LAC Profile → 基于样本数据的精细画像
   - "治理监控"域：Flow/Snapshot/Run/Object/Workspace/Baseline → 基于全量数据的治理运行状态
2. **在 FlowOverviewPage 添加数据源说明**：标注数据来源为 G2/G3 治理运行，非 ETL 画像
3. **不要试图让 `profile.py` 产出增量记录来喂给 flow 页面** —— 这会混淆两套体系的边界

#### 优先级: P1

两套体系各自可用，但用户可能困惑于数量级差异。需要 UI 层的说明性文案，不需要架构改动。

---

### 问题 2: 数据版本管理缺失

#### 根因分析

**版本管理并非完全缺失。** 数据库实际状态：

| 表 | 行数 | 说明 |
|---|---|---|
| `rebuild4_meta.contract_version` | 1 | `rebuild4-final-freeze-2026-04-06-v6` |
| `rebuild4_meta.rule_set_version` | 1 | 有绑定 |
| `rebuild4_meta.current_pointer` | 1 | 指向 `RUN-ROLL-001 / BATCH-ROLL-003` |
| `rebuild4_meta.run` | 2 | 初始化 + 滚动，均完成 |
| `rebuild4_meta.batch` | 4 | 1 初始化 + 3 滚动 |
| `rebuild4_meta.baseline_version` | 1 | v1 |

治理体系的版本管理基础设施完整运行。`context.py` 中 `get_current_pointer()` 正确读取 `current_pointer` 并关联 `contract_version` 和 `rule_set_version`。

**真正的问题是 `profile.py` 每次运行时 DROP + CREATE，不记录任何版本信息**。ETL 画像没有 run_id、batch_id、时间戳——无法追溯"这版画像是什么时候、基于什么数据生成的"。

#### 影响范围

- `RunBatchCenterPage` 展示的是治理运行，正常工作
- ETL 画像（Cell/BS/LAC Profile 页面）无法回溯生成时间或对比历史版本
- 如果 `profile.py` 重跑，旧数据直接丢失，无法对比

#### 建议方案

**最小可行方案（不改变 profile.py 核心逻辑）**：

1. 在 `profile.py` 的 `run_profile()` 开始时，向 `rebuild4_meta.etl_run_stats` 写入一条记录（已有 6 行，可复用此表），记录 `profile_run_id`, `started_at`, `input_table='etl_filled'`, `input_rows`
2. 在 `etl_dim_cell/bs/lac` 表中添加 `profile_run_id` 列（或在一个独立的 `rebuild4_meta.profile_version` 表中记录）
3. 完成后更新该记录的 `finished_at` 和 `output_rows`

不需要对接治理体系的 `run/batch` 概念——ETL 画像是独立体系，用独立的版本记录即可。

#### 优先级: P2

当前不阻塞任何功能。画像数据可用，只是缺少可追溯性。在需要对比多次画像构建结果时才会成为问题。

---

### 问题 3: 参数与画像耦合

#### 根因分析

`profile.py` (rebuild4/backend/app/etl/profile.py) 的所有阈值硬编码在 SQL 字符串中。经审计，参数分为三类：

**A. 物理常量 / 算法内核（不应外部化）**：
- GPS 中国边界：lon 73-135, lat 3-54
- 信号范围：RSRP -156..0, RSRQ -50..0, SINR -30..50
- 经度转米系数 85,300（北京纬度）
- 纬度转米系数 111,000

**B. 分类阈值（核心算法参数，谨慎外部化）**：
- collision 判定：spread ≥ 2,200m, net/spread < 0.3
- stable 判定：spread < 500m
- migration 判定：spread ≥ 2,200m, net/spread ≥ 0.7
- large_coverage 判定：500m ≤ spread < 2,200m
- BS 异常距离阈值：2,500m

这些阈值有 `04_cell_research.md` 中的实验依据（2,200m 来自数据中的自然间隙），不应轻易调整。但研究项目可能需要尝试不同参数。

**C. 业务阈值（应该外部化）**：
- lifecycle 门槛：obs ≥ 3, devices ≥ 2, P90 < 1,500m, span ≥ 24h
- position_grade 分级：excellent (obs≥8, devs≥3, P90<500m), good (obs≥3, devs≥2), qualified (obs≥1)
- GPS confidence 分级：high (gps≥20, devs≥3), medium (gps≥10, devs≥2)
- Signal confidence 分级：high (signal≥20), medium (≥5)
- cell_scale 分级：major (obs≥50, devs≥10), large (20/5), medium (10/3), small (3)
- anchorable 条件：gps≥10, devs≥2, P90<1500, span≥24h

#### 影响范围

- 任何阈值变更都需要编辑 `profile.py` 中的 SQL 字符串
- 变更后必须全量重算（`run_profile()` 全部 6 步），无法局部重算
- 阈值分散在 Step 4 (build_cell) 的一个大 SQL 中，修改容易引入错误

#### 建议方案

1. **提取 B 类和 C 类参数到 `profile.py` 文件顶部的 Python 常量字典**：
   ```python
   PROFILE_PARAMS = {
       "lifecycle_min_obs": 3,
       "lifecycle_min_devices": 2,
       "lifecycle_max_p90": 1500,
       "lifecycle_min_span_hours": 24,
       "collision_spread_m": 2200,
       "collision_ratio_max": 0.3,
       ...
   }
   ```
   SQL 中使用 `%(lifecycle_min_obs)s` 参数化替换。

2. **不需要外部配置文件或 UI**。这是研究项目，Python 常量足够。未来如需 UI，可在 `GovernancePage` 添加"画像参数"标签读取这些常量。

3. **全量重算是正确行为**。画像各步骤有依赖关系（cell → bs → lac），局部重算的正确性难以保证。当前 6 步执行时间在可接受范围内。

#### 优先级: P2

当前不阻塞功能。阈值已在研究文档中验证。提取为常量是良好实践但非紧急。

---

### 问题 4: 整体架构一致性

#### 根因分析

系统实际上是 **两套数据体系在同一个 UI 壳中运行**：

```
                    ETL 体系                              治理体系
                    ────────                              ────────
数据源        sample_raw_gps/lac (249K原始)         rebuild2.l0_gps/l0_lac (82M标准化)
处理管道      pipeline.py → profile.py               G2初始化 + G3滚动 (外部脚本)
对象表        etl_dim_cell (20K)                     obj_cell (128万)
页面          EtlParse/Clean/Fill + Profile×3        Flow + Snapshot + Run + Object + Workspace
                + EtlRegister + EtlAudit               + Anomaly + Baseline + Governance
```

这不是设计缺陷——这是两个不同阶段的产物共存。ETL 画像是 rebuild4 自有管道从样本数据构建的精细画像；治理对象是从 rebuild2 历史全量数据回灌的治理快照。

#### 各 `???` 数据源的实际状态

| 页面 | 数据源 | 实际状态 |
|------|--------|----------|
| 等待/观察工作台 | `rebuild4_meta.observation_workspace_snapshot` | ✅ 50,000行 (全部 observing) |
| 异常工作台 | `rebuild4_meta.batch_anomaly_object_summary` + `batch_anomaly_record_summary` | ✅ 1,600 + 14 行 |
| 对象浏览 | `rebuild4.obj_cell/bs/lac` | ✅ 128万/22.8万/1.3万行 |
| 基线/画像 | `rebuild4_meta.baseline_version` + `rebuild4.baseline_cell/bs/lac` | ✅ 1版, 55万/22.8万/1.3万行 |
| 基础数据治理 | `rebuild4_meta.*` 各元数据表 | ✅ 全部有种子数据 |
| ETL 数据处理 | `rebuild4_meta.etl_run_stats` + `rebuild4.etl_*` | ✅ 完整 |

#### 用户视角的可操作流程分析

**能完成的操作**：
1. ✅ 查看 ETL 管道全过程（登记 → 审计 → 解析 → 清洗 → 填充）— 完整可用
2. ✅ 浏览 Cell/BS/LAC 画像，筛选、展开详情 — 完整可用
3. ✅ 查看治理元数据（字段目录、表目录、规则、合规等）— 完整可用
4. ✅ 查看流转总览的四路分布和批次指标 — 基本可用
5. ✅ 查看运行/批次中心 — 基本可用
6. ⚠️ 浏览对象列表 — 有数据但需验证字段映射
7. ⚠️ 查看观察工作台 — 有数据但仅 observing 状态
8. ⚠️ 查看异常工作台 — 有数据
9. ⚠️ 查看基线信息 — 仅 v1，无历史对比

**不能完成的操作**：
1. ❌ 运行验证对比 — compare_job 为空，且无 UI 触发入口
2. ❌ 查看对象状态变更历史 — `obj_state_history` 为空
3. ❌ 查看基线版本差异对比 — 仅 1 版，无 previous
4. ❌ 在两套体系间交叉查询（如"ETL 画像中的 collision cell 在治理体系中是什么状态"）

#### 建议方案

不需要架构重构。关键是 **UI 层面讲清楚数据来源**。

---

## 三、整体重构建议

### 第一阶段（必须做）：让系统从用户视角一致可用

**目标**：用户打开系统后不会因为困惑而误判数据。

1. **添加数据域标识** — 在 `App.vue` 侧边栏中，将导航分为两组：
   - "📊 ETL 与画像"：ETL 管道 5 页 + Profile 3 页
   - "🔍 治理监控"：FlowOverview + FlowSnapshot + RunBatchCenter + Objects + Workspaces + Anomaly + Baseline
   - "📋 系统治理"：Governance + ValidationCompare
   - 文件: `rebuild4/frontend/src/App.vue`, `rebuild4/frontend/src/router.ts`

2. **验证 Objects 页面字段映射** — 确认 `obj_cell/bs/lac` 表的列名与 `objects.py` 查询的 SELECT 列和前端期望的字段名完全对齐。重点检查:
   - `lifecycle_state`, `health_state`, `watch_state`, `qualification_flags`
   - 文件: `rebuild4/backend/app/routers/objects.py`

3. **验证 Workspace 页面字段映射** — 确认 `observation_workspace_snapshot` 的列名与 `workspaces.py` 查询对齐:
   - `lifecycle_state` vs 前端期望的 `status`
   - `existence_progress`, `anchorable_progress`, `baseline_progress`
   - 文件: `rebuild4/backend/app/routers/workspaces.py`

4. **Profile 页面空表提示** — `CellProfilePage.vue`, `BsProfilePage.vue`, `LacProfilePage.vue` 的表格在无数据时无"暂无数据"提示（`<tbody>` 为空），应添加空状态行。
   - 文件: `rebuild4/frontend/src/pages/CellProfilePage.vue`, `BsProfilePage.vue`, `LacProfilePage.vue`

### 第二阶段（应该做）：补充版本管理与参数可追溯性

**目标**：画像构建可追溯，参数变更可控。

5. **画像版本记录** — `profile.py` 每次运行时写入版本记录到 `rebuild4_meta.etl_run_stats` 或新建 `profile_version` 表。
   - 文件: `rebuild4/backend/app/etl/profile.py`
   - 新表: `rebuild4_meta.profile_version` (profile_run_id, started_at, finished_at, input_table, input_rows, output_cell_rows, output_bs_rows, output_lac_rows, params_snapshot JSONB)

6. **参数提取** — 将 `profile.py` 中的 B/C 类阈值提取为文件顶部的 `PROFILE_PARAMS` 字典，SQL 中参数化引用。
   - 文件: `rebuild4/backend/app/etl/profile.py`

7. **参数快照** — 每次画像构建时，将 `PROFILE_PARAMS` 序列化为 JSON 存入 `profile_version.params_snapshot`，实现参数可追溯。

### 第三阶段（可以做）：完善治理体系与 ETL 画像的衔接

**目标**：让两套体系的数据可以交叉验证。

8. **ETL 画像 vs 治理对象交叉对比页** — 新建一个对比视图，展示 `etl_dim_cell` 中的 Cell 在 `obj_cell` 中的对应状态，用于验证两套体系的一致性。
   - 这可以作为 `ValidationComparePage` 的扩展功能
   - 文件: `rebuild4/backend/app/routers/compare.py`, `rebuild4/frontend/src/pages/ValidationComparePage.vue`

9. **补充 `obj_state_history`** — 如果未来执行更多滚动批次，确保治理引擎写入状态变更历史，使 `ObjectDetailPage` 的时间线可用。
   - 依赖: 外部治理引擎代码（非 rebuild4 范围）

10. **基线迭代** — 执行更多滚动批次后触发 baseline v2 生成，使 `BaselineProfilePage` 的版本对比和 diff 展示功能生效。
    - 依赖: 更多数据输入 + baseline 触发逻辑

---

## 附录：完整数据库表清单与行数

### rebuild4 schema (35 表)

| 表名 | 行数 | 所属体系 |
|------|------|---------|
| etl_filled | 687,788 | ETL |
| etl_parsed | ~689K | ETL |
| etl_cleaned | ~688K | ETL |
| etl_dim_cell | 20,394 | ETL 画像 |
| etl_dim_bs | 11,942 | ETL 画像 |
| etl_dim_lac | 1,270 | ETL 画像 |
| etl_dim_bs_centroid | 有数据 | ETL 画像 |
| etl_ci_gps / etl_ci_lac / etl_ss1_gps / etl_ss1_lac | 中间表 | ETL |
| fact_standardized | 82,205,035 | 治理 |
| fact_governed | 67,963,244 | 治理 |
| fact_pending_observation | 9,493,333 | 治理 |
| fact_pending_issue | 1,461 | 治理 |
| fact_rejected | 4,746,997 | 治理 |
| obj_cell | 1,286,825 | 治理 |
| obj_bs | 228,536 | 治理 |
| obj_lac | 13,480 | 治理 |
| baseline_cell | 550,219 | 治理 |
| baseline_bs | 228,536 | 治理 |
| baseline_lac | 13,480 | 治理 |
| sample_raw_gps / sample_raw_lac | 原始数据 | 输入 |
| sample_l0_gps / sample_l0_lac / sample_l0_raw_gps / sample_l0_raw_lac | 参考数据 | 输入 |
| sample_cell_profile / sample_bs_profile / sample_dim_cell / sample_dim_bs / sample_enriched | 参考数据 | 输入 |
| eval_stream_convergence | 实验数据 | 研究 |
| tmp_cell_obs_v2 | 临时表 | - |

### rebuild4_meta schema (40 表)

| 表名 | 行数 | 说明 |
|------|------|------|
| run | 2 | INIT-001 + ROLL-001 |
| batch | 4 | 1 初始化 + 3 滚动 |
| batch_flow_summary | 4 | 每批次四路分布 |
| batch_snapshot | 44 | 各阶段指标快照 |
| batch_transition_summary | 16 | 状态转换摘要 |
| batch_anomaly_object_summary | 1,600 | 对象级异常 |
| batch_anomaly_record_summary | 14 | 记录级异常 |
| observation_workspace_snapshot | 50,000 | 观察对象快照 |
| baseline_version | 1 | v1 |
| baseline_diff_summary | 3 | 首版差异（无 previous） |
| baseline_diff_object | 0 | 空 |
| baseline_refresh_log | 4 | 刷新日志 |
| obj_state_history | 0 | 空 |
| compare_job / compare_result | 0 / 0 | 空 |
| current_pointer | 1 | main → ROLL-001/BATCH-ROLL-003 |
| contract_version | 1 | v6 |
| rule_set_version | 1 | 1 版 |
| initialization_step_log | 11 | 11步全部完成 |
| etl_run_stats | 6 | ETL 运行统计 |
| asset_field_catalog | 1,214 | 字段目录 |
| asset_table_catalog | 98 | 表目录 |
| asset_usage_map | 6 | 使用关系 |
| asset_migration_decision | 10 | 迁移决策 |
| field_audit_snapshot | 27 | 字段审计 |
| target_field_snapshot | 55 | 目标字段 |
| ods_rule_snapshot | 26 | ODS 规则 |
| ods_execution_snapshot | 24 | ODS 执行 |
| parse_rule | 25 | 解析规则 |
| compliance_rule | 14 | 合规规则 |
| trusted_loss_summary | 1 | 可信损失汇总 |
| trusted_loss_breakdown | 7 | 可信损失明细 |
| gate_definition | 9 | 门控定义 |
| gate_run_result | 9 | 门控结果 |
| seed_artifact_manifest | 未查 | 种子管理 |
| source_adapter | 未查 | 源适配器 |
| lac_location_snapshot | 未查 | LAC 位置 |
