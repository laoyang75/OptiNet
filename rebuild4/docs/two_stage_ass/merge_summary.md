# 流式架构审计 — 三方综合整理

## 1. 四个核心问题的三方观点

### 问题1：流转可视化断裂

| Agent | 核心观点（1-2句） | 严重性判断 |
|-------|----------------|-----------|
| Codex | 首页、流转快照、观察工作台等主路径仍依赖 `batch_*` / `observation_workspace_snapshot` 等 read model，但它们与 `profile.py` 生成的 `etl_dim_*` 世界没有统一版本合同，且前后端字段契约漂移，导致页面失真或不可用。 | P0 |
| Claude | 流转相关表并非空壳，`batch_flow_summary`、`batch_snapshot`、`batch_transition_summary` 仍有真实治理数据；问题更像 ETL 画像体系与治理体系并存后缺少边界说明，造成理解混乱。 | P1 |
| Gemini | 在 `profile.py` 改为全量重建后，流转总览、流转快照、观察/异常工作台仍在消费旧批次遗留数据，展示的是过期或虚假的流转语义。 | P0 |

**观点收敛情况**：部分分歧（Codex 和 Gemini 都认为主路径已严重失真；Claude 认为流转数据仍有现实意义，主要问题是双体系并存未说明清楚。）

### 问题2：数据版本管理缺失

| Agent | 核心观点（1-2句） | 严重性判断 |
|-------|----------------|-----------|
| Codex | `run` / `batch` / `current_pointer` 等治理版本表仍在工作，但 `profile.py` 绕开了这套登记流程；问题是当前画像构建没有被重新绑定到 `run_id`、`batch_id`、`rule_set_version`、`baseline_version` 上。 | P1 |
| Claude | 治理体系的版本基础设施并未缺失，`run`、`batch`、`current_pointer`、`contract_version` 仍然完整；缺口主要在 ETL 画像侧，它缺少独立的构建版本与追溯记录。 | P2 |
| Gemini | 当前管道被简化为直接重写表，最新画像构建没有再向 `rebuild4_meta` 注册批次/版本信息，因此批次中心和版本语义与现行全量画像链路脱节。 | P1 |

**观点收敛情况**：部分分歧（都认同当前画像缺少可追溯版本上下文，但 Codex/Claude 认为治理版本体系仍然存在，Gemini 则认为当前批次语义已基本失效。）

### 问题3：参数与画像耦合

| Agent | 核心观点（1-2句） | 严重性判断 |
|-------|----------------|-----------|
| Codex | `profile.py` 同时硬编码了算法常量和业务阈值；核心几何规则可保留，但 lifecycle、anchorable、分桶等策略阈值应从代码里拆出，并纳入版本化管理。 | P1 |
| Claude | 参数硬编码确实存在，但更紧迫的动作是把业务阈值提炼成 `profile.py` 内的 Python 常量；外部配置表或 UI 不是当前必需。 | P2 |
| Gemini | 当前为验证方案而写死的阈值已经限制业务调整，动态阈值应迁出 SQL 建表语句，改由配置或元数据驱动后再注入执行。 | P2 |

**观点收敛情况**：部分分歧（都认同硬编码耦合存在，但对紧迫性和外部化深度判断不同：Codex 最强调版本治理，Claude 最保守，Gemini 介于两者之间。）

### 问题4：整体架构一致性

| Agent | 核心观点（1-2句） | 严重性判断 |
|-------|----------------|-----------|
| Codex | 系统没有围绕单一 truth source 收敛：ETL/画像、批次/异常、`obj_*` 工作台三块语义并存却缺少桥接，用户进入系统后无法判断哪套世界才是当前权威。 | P0 |
| Claude | 当前更像两套数据域共用一个 UI 外壳，而不是单点架构故障；ETL 画像域和治理监控域各自都有可用部分，关键问题是来源说明与边界标识不足。 | 未明确 |
| Gemini | 只有 ETL 数据处理和 Profile 页面在读取最新画像结果，首页、工作台、对象浏览等入口仍连接到旧结构或旧数据源，整体体验因此断裂。 | 未明确 |

**观点收敛情况**：明显分歧（Codex 要求围绕统一 truth source 收敛；Claude 认为双域并存本身可接受；Gemini 则把旧工作台视为整体体验断裂的根源。）

## 2. 争议点汇总

- **争议点**：流转/批次相关页面的数据到底是“仍可用的治理数据”，还是“已经过期的旧遗留”。
- **Codex 观点**：`batch_*`、`batch_anomaly_*` 仍有部分真实数据，但主路径页已经因为 read model 失配和字段契约漂移而失真。
- **Claude 观点**：这些表仍承载真实治理运行结果，流转总览和批次中心基本可用，主要问题是双体系边界没有讲清楚。
- **Gemini 观点**：这些页面展示的是旧批次遗留物，已不再对应当前全量画像流程，应视为过期数据。

- **争议点**：数据版本管理问题的范围，是“画像链路缺少补充登记”，还是“当前批次/版本体系已整体失去意义”。
- **Codex 观点**：治理版本体系仍在运行，核心问题是 `profile.py` 没有接回现有的 `run` / `batch` / `rule_set` / `baseline` 上下文。
- **Claude 观点**：治理体系的版本管理并未缺失，只有 ETL 画像需要补一层独立的构建版本记录。
- **Gemini 观点**：由于最新管道不再注册 `run_id` / `batch_id`，批次中心和版本闭环已与现行数据生产方式脱节。

- **争议点**：`obj_*` 与 `etl_dim_*` 的关系应该被解释为“双域并存”，还是应该尽快做数据源切换。
- **Codex 观点**：必须先做架构决策，明确对象页是继续保留 `obj_*` 工作台语义，还是切到 `etl_dim_*` 加新 read model。
- **Claude 观点**：`obj_*` 治理对象与 `etl_dim_*` 画像对象是两套有效但不同的数据域，应通过 UI 标识解释差异。
- **Gemini 观点**：`objects.py` 继续读取 `obj_*` 已是错误数据源，应该立刻切换到 `etl_dim_*`。

- **争议点**：参数外化应做到什么程度。
- **Codex 观点**：业务阈值应纳入 `rule_set_version` 或类似版本化配置，并在治理/版本上下文中展示。
- **Claude 观点**：先把阈值提炼为 `profile.py` 内常量即可，暂不需要外部配置表或 UI。
- **Gemini 观点**：动态阈值应迁到配置或元数据层，后续可在治理模块提供参数表单入口。

## 3. 三方一致的发现

- 当前系统同时存在 `etl_dim_*` 画像链路与 `run` / `batch` / `obj_*` 治理链路，两套语义没有自然收敛到同一个页面心智模型中。（来源：`rebuild4/docs/two_stage_ass/codex/audit_result.md` 问题1/问题4；`rebuild4/docs/two_stage_ass/claude/audit_result.md` 问题1/问题4；`rebuild4/docs/two_stage_ass/gemini/audit_result.md` 问题1/问题4）
- `profile.py` 当前以全量重建方式生成 `etl_dim_cell` / `etl_dim_bs` / `etl_dim_lac`，而 Cell/BS/LAC Profile 页面是最贴近这条最新画像产物的一组页面。（来源：`rebuild4/docs/two_stage_ass/codex/audit_result.md` 页面级诊断/问题1；`rebuild4/docs/two_stage_ass/claude/audit_result.md` 页面级诊断/问题4；`rebuild4/docs/two_stage_ass/gemini/audit_result.md` 现状诊断/问题4）
- 当前画像产出缺少与版本上下文的直接绑定，无法从现有结果中清晰回答“这版画像是哪次构建、绑定了什么规则或批次”。（来源：`rebuild4/docs/two_stage_ass/codex/audit_result.md` 问题2；`rebuild4/docs/two_stage_ass/claude/audit_result.md` 问题2；`rebuild4/docs/two_stage_ass/gemini/audit_result.md` 问题2）
- `profile.py` 中存在硬编码阈值或规则，参数变更目前都依赖代码层调整，而不是清晰的外部版本配置。（来源：`rebuild4/docs/two_stage_ass/codex/audit_result.md` 问题3；`rebuild4/docs/two_stage_ass/claude/audit_result.md` 问题3；`rebuild4/docs/two_stage_ass/gemini/audit_result.md` 问题3）

## 4. 信息缺口

- 系统长期应该以哪套对象模型作为单一权威语义：继续保留 `obj_*` 工作台世界、切换到 `etl_dim_*`，还是长期维持双域并存，三份报告都没有给出可由现有证据唯一确定的结论。
- `etl_dim_*` 与 `obj_*` / `baseline_*` / `observation_workspace_snapshot` 之间是否存在稳定的桥接关系或映射合同，三份报告都指出了割裂，但都没有给出已验证的桥接机制。
- `batch_*`、`observation_workspace_snapshot`、`baseline_*` 等治理 read model 当前是否仍有受支持的持续刷新链路，三份报告都只描述了现状，没有给出权威维护边界。
- `compare_*`、`obj_state_history`、`obj_relation_history` 等能力为什么没有被持续产出，是外部流程停用、尚未接入，还是故意弃用，三份报告都没有给出明确结论。
