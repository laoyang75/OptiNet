# UI v2 审计偏差报告

## 审计概要

| 类别 | 审计项数 | 一致 | 有偏差 | 缺失 | 需决策 |
|------|---------|------|-------|------|-------|
| A. 对象与状态模型 | 7 | 1 | 4 | 0 | 2 |
| B. 事实分层与四分流 | 4 | 0 | 4 | 0 | 0 |
| C. 初始化流程 | 4 | 1 | 2 | 1 | 0 |
| D. 增量流程 | 4 | 2 | 1 | 1 | 0 |
| E. 版本与批次体系 | 3 | 0 | 1 | 2 | 0 |
| F. UI 隐含的表结构需求 | 13 | 0 | 6 | 7 | 0 |
| G. 页面内容匹配 | 8 | 2 | 5 | 0 | 1 |
| **合计** | **43** | **6** | **23** | **11** | **3** |

## 逐项审计结果

### A. 对象与状态模型

- **A1｜有偏差**：UI 并未在所有页面保持 `waiting / observing / active / dormant / retired / rejected` 全枚举；LAC 画像只展示活跃/休眠/退役，Cell 画像只展示活跃/等待中/观察中/休眠。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:60`，`docs/rebuild3/UI_v2/pages/09_lac_profile_doc.md:40`，`docs/rebuild3/UI_v2/pages/11_cell_profile_doc.md:97`。 影响说明：对象状态读模型和枚举约束会在画像页分叉。
- **A2｜有偏差**：UI 健康表达混入 `覆盖不足`、`异常分类`、`GPS 可信度` 等旧口径，没有统一到 `healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect`。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:61`，`docs/rebuild3/UI_v2/pages/09_lac_profile.html:189`，`docs/rebuild3/UI_v2/pages/10_bs_profile.html:245`，`docs/rebuild3/UI_v2/pages/11_cell_profile.html:351`。 影响说明：健康状态枚举、筛选器和异常路由无法共用。
- **A3｜一致**：`watch` 被作为派生 UI 态而非持久化状态使用，表达方式与冻结文档一致。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:65`，`docs/rebuild3/UI_v2/design_notes.md:165`，`docs/rebuild3/UI_v2/pages/03_objects_doc.md:61`。 影响说明：可以直接沿用为前端派生展示逻辑。
- **A4｜有偏差**：对象浏览/详情页显式展示了锚点与基线资格，但等待工作台只展示样本阈值进度，未把“存在资格 / anchorable / baseline_eligible”分层展示出来。证据：`docs/rebuild3/02_rebuild3_预实施任务书_最终冻结版.md:223`，`docs/rebuild3/UI_v2/pages/03_objects.html:545`，`docs/rebuild3/UI_v2/pages/05_observation_workspace.html:718`。 影响说明：等待对象的推进逻辑会被误解为单一门槛。
- **A5｜需决策**：rebuild2 的 `classification_v2` 只能部分映射到 rebuild3 `health_state`：`dynamic_bs -> dynamic`、`collision_confirmed -> collision_confirmed`、`collision_suspected -> collision_suspect` 可直接转换；`single_large`、`normal_spread` 在冻结文档中被定义为记录级异常，不应直接落对象 `health_state`；数据库里还存在额外的 `collision_uncertain`。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:320`，`rebuild2/frontend/js/pages/profile_bs.js:57`，PG17 表 `rebuild2._research_bs_classification_v2`。 影响说明：对象健康状态、异常标签和事实路由都依赖这张映射表。
- **A6｜需决策**：rebuild2 的 `gps_confidence / signal_confidence` 是四级质量分档，冻结文档要求的是 `anchorable / baseline_eligible` 两个布尔资格，二者不是一一对应。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:313`，`docs/rebuild3/03_rebuild3_技术栈要求_最终冻结版.md:124`，`rebuild2/frontend/js/pages/profile_cell.js:38`，PG17 表 `rebuild2._sample_bs_profile_summary`、`rebuild2._sample_cell_profile_summary`。 影响说明：如果不先定规则矩阵，资格字段无法稳定落库。
- **A7｜有偏差**：09/10/11 三个画像页需要的字段在 rebuild2 里呈现“部分可复用 + 大量需新增状态/聚合”的混合状态；尤其 `lifecycle_state`、`health_state`、`anchorable`、`baseline_eligible` 在 rebuild2 现有画像表中都不存在。证据：`docs/rebuild3/UI_v2/pages/09_lac_profile_doc.md:36`，`docs/rebuild3/UI_v2/pages/10_bs_profile_doc.md:37`，`docs/rebuild3/UI_v2/pages/11_cell_profile_doc.md:38`，PG17 表 `rebuild2._sample_lac_profile_v1`、`rebuild2._sample_bs_profile_summary`、`rebuild2._sample_cell_profile_summary`。 影响说明：画像页不能直接照搬 rebuild2 表结构。

### B. 事实分层与四分流

- **B1｜有偏差**：UI 在多个地方使用 `pending_obs` / `fact_pending_obs` 缩写，违反冻结文档“名称必须完全一致”。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:202`，`docs/rebuild3/UI_v2/design_notes.md:321`，`docs/rebuild3/UI_v2/pages/02_run_batch_center.html:840`，`docs/rebuild3/UI_v2/pages/11_cell_profile.html:325`。 影响说明：后端字段名、快照表字段名和前端标签会漂移。
- **B2｜有偏差**：UI 显示了四分流结果，但没有把冻结文档中的四条精确路由条件完整写到界面或页面说明里。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:220`，`docs/rebuild3/UI_v2/pages/01_flow_overview.html:253`。 影响说明：用户无法直接从 UI 判断“为什么这条事实走到这一层”。
- **B3｜有偏差**：rebuild2 的 `trusted + dwd_fact_enriched` 大体对应 `fact_governed`，异常研究表对应 `fact_pending_issue`，合规过滤/淘汰对应 `fact_rejected`，但没有 `fact_pending_observation` 的等价事实层。证据：`rebuild2/frontend/js/pages/trusted.js:36`，`rebuild2/backend/app/api/anomaly.py:145`，PG17 表 `rebuild2.dwd_fact_enriched`。 影响说明：rebuild3 的等待/观察链路无法复用 rebuild2 事实层。
- **B4｜有偏差**：UI 已覆盖 waiting / collision / dynamic / migration / rejected 等情况，但 `single_large`、`normal_spread`、结构不合规等资格矩阵场景没有在异常工作台和对象详情中完整出现。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:355`，`docs/rebuild3/UI_v2/pages/06_anomaly_workspace.html:646`，`docs/rebuild3/UI_v2/pages/11_cell_profile.html:683`。 影响说明：资格矩阵在前端不可验证，开发时容易遗漏分支。

### C. 初始化流程

- **C1｜一致**：初始化页面 11 个步骤与冻结版 6.1 流程图逐节点一致。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:155`，`docs/rebuild3/UI_v2/pages/12_initialization.html:159`。 影响说明：初始化页可直接作为冻结流程的 UI 对应物。
- **C2｜有偏差**：rebuild2 有标准化、合规、LAC 过滤、Cell/BS 聚合和异常研究，但缺少“Cell 候选累计与晋升状态机”“由 active BS 派生 LAC”“完整回归一次”“baseline v1”这些 rebuild3 初始化关键步骤。证据：`rebuild2/sql/exec_l0_lac.sql:5`，`rebuild2/backend/app/api/trusted.py:204`，`rebuild2/prompts/step5_8.sql:96`，`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:163`。 影响说明：初始化实现不能按 rebuild2 直接迁移。
- **C3｜有偏差**：UI mock 规模（Cell 12,782 / BS 3,382 / LAC 152）与当前 rebuild2 已知结果集都不匹配：全量 `dim_cell_stats / dim_bs_stats / dim_lac_trusted` 为 573,561 / 193,036 / 1,057，样本画像表为 3,751 / 1,096 / 6。证据：`docs/rebuild3/UI_v2/pages/12_initialization.html:195`，PG17 表计数 `rebuild2.dim_cell_stats`、`rebuild2.dim_bs_stats`、`rebuild2.dim_lac_trusted`、`rebuild2._sample_*`。 影响说明：当前 mock 容量会误导容量评估和分页/缓存策略。
- **C4｜缺失**：冻结文档要求“首轮对象库形成后再做一次完整回归”，rebuild2 脚本链没有对应步骤。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:176`，`rebuild2/prompts/step9_10.sql:6`。 影响说明：rebuild3 初始化中的语义纠偏步骤需要新建。

### D. 增量流程

- **D1｜一致**：流转总览流程图版与冻结文档 7.1 的节点顺序基本一致。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:198`，`docs/rebuild3/UI_v2/pages/01_flow_overview.html:208`。 影响说明：增量处理主链路可以直接作为前端原型基线。
- **D2｜一致**：UI 明确把晋升、级联更新、异常检测、基线刷新都放在批末节点，符合“批末统一更新”原则。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:227`，`docs/rebuild3/UI_v2/pages/01_flow_overview.html:334`。 影响说明：不会把实时更新错画成逐条更新。
- **D3｜有偏差**：UI 只在流程图里提到“上一版基线”，没有把“当前批次只看上一版冻结 baseline”作为跨页面上下文原则反复强调。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:192`，`docs/rebuild3/UI_v2/pages/01_flow_overview.html:238`，`docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html:271`。 影响说明：对象详情、批次中心、基线页容易被误读为可读写同批基线。
- **D4｜缺失**：rebuild2 没有结构化的 2 小时增量能力：数据库中不存在 run/batch 表，也没有 `batch_id`、`baseline_version` 等增量语义。证据：PG17 schema 检索 `%run%` / `%batch%` 结果为空；`rg` 检索 `rebuild2` 无 `batch_id` / `run_id` 业务代码。 影响说明：增量链路、批次管理、重跑机制都要从零实现。

### E. 版本与批次体系

- **E1｜有偏差**：只有流转总览页完整出现 `run_id / batch_id / contract_version / rule_set_version / baseline_version` 五类标识；其余页面大量缺失，初始化 API 还把 `rule_set_version` 写成 `rule_version`。证据：`docs/rebuild3/UI_v2/pages/01_flow_overview.html:169`，`docs/rebuild3/UI_v2/pages/02_run_batch_center.html:520`，`docs/rebuild3/UI_v2/pages/07_baseline_profile.html:455`，`docs/rebuild3/UI_v2/pages/12_initialization_doc.md:129`。 影响说明：版本绑定无法形成统一上下文条。
- **E2｜缺失**：rebuild2 没有 run / batch 元数据表；meta 里只有 `run_label` 文本字段。证据：PG17 schema `rebuild2` / `rebuild2_meta` 下 `%run%`、`%batch%` 表检索为空；`rebuild2_meta.enrich_result`、`rebuild2_meta.trusted_build_result` 仅有 `run_label`。 影响说明：rebuild3 的批次回放、版本追溯和 UI 上下文必须新建元数据层。
- **E3｜缺失**：`batch_snapshot` 只在 UI v2 中被提出，冻结文档和 rebuild2 实际库中都没有。证据：`docs/rebuild3/UI_v2/design_notes.md:92`，`docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html:411`，`docs/rebuild3/Docs/questions_for_review.md:108`。 影响说明：这是合理新增需求，但必须补入实施计划与 DDL。

### F. UI 隐含的表结构需求

- **F1｜缺失**：流转总览所需的批次元数据、四分流计数、批末决策汇总、异常汇总、基线刷新记录，在 rebuild2 中都没有 batch 级等价表。现有 `enrich_result / trusted_build_result / l0_stats_cache` 只有 step 级缓存。 影响说明：首页无法直接从现有表读取。
- **F2｜缺失**：`batch_snapshot` 需要新的快照表设计；rebuild2 没有任何等价物。证据：`docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html:411`。 影响说明：时间对照版首页无法落地。
- **F3｜缺失**：运行/批次中心需要 `run`、`batch` 两张核心表；rebuild2 仅有 `run_label` 文本，没有结构化运行实体。 影响说明：批次列表、重跑标记、窗口信息都无法复用旧表。
- **F4｜有偏差**：`obj_cell / obj_bs / obj_lac` 可以分别吸收 `dim_cell_stats/refined`、`dim_bs_stats/refined`、`dim_lac_trusted` 的部分字段，但旧表缺少 `lifecycle_state`、`health_state`、`anchorable`、`baseline_eligible`、关系历史和版本字段。证据：`docs/rebuild3/02_rebuild3_预实施任务书_最终冻结版.md:223`，PG17 表 `rebuild2.dim_cell_stats`、`rebuild2.dim_bs_stats`、`rebuild2.dim_lac_trusted`。 影响说明：对象层必须做结构重组，而不是直接 rename。
- **F5｜缺失**：等待/观察工作台需要 `progress_percent`、`trend_direction`、`suggested_action`、`stall_batches` 等批次衍生字段，rebuild2 无等待池、观察池和批次进度数据源。证据：`docs/rebuild3/UI_v2/design_notes.md:365`。 影响说明：观察工作台需要全新读模型和计算逻辑。
- **F6｜有偏差**：异常工作台可部分复用 `_research_bs_classification_v2`、`_research_collision_detail`、`dim_cell_refined.gps_anomaly`，但缺少 `discovered_batch`、`severity`、`anchorable`、`baseline_eligible`、`downstream_impact` 等工作台级字段。证据：`docs/rebuild3/UI_v2/design_notes.md:383`，`rebuild2/backend/app/api/anomaly.py:145`。 影响说明：异常页不能直接挂在旧研究表上。
- **F7｜缺失**：基线/画像页需要 baseline 版本表、差异表、稳定性评分；rebuild2 schema 和 meta 都没有 baseline 表。证据：PG17 schema `%baseline%` 检索为空。 影响说明：基线模块必须从零设计。
- **F8｜缺失**：验证/对照页需要对比结果表或异步任务表；rebuild2 没有等价表。 影响说明：对照页无法沉淀可复用结果。
- **F9｜有偏差**：LAC 画像字段中只有 `operator/tech/lac/record_count` 可直接映射；`location_name`、`lifecycle_state`、`health_state`、`bs_count`、`cell_count`、`area_km2`、`gps/signal 原始率`、`rsrp_avg` 等都需要新聚合或新字段。证据：`docs/rebuild3/UI_v2/pages/09_lac_profile_doc.md:36`，PG17 表 `rebuild2.dim_lac_trusted`、`rebuild2._sample_lac_profile_v1`。 影响说明：LAC 画像不能仅依赖一张旧 LAC 表。
- **F10｜有偏差**：BS 画像的主键、Cell/记录/设备数、P50/P90 可复用；`area_km2`、GPS/信号原始率、`rsrp_avg` 只在样本画像表里有，`classification_v2`、`gps_confidence` 需要改造成 rebuild3 状态/资格模型。证据：`docs/rebuild3/UI_v2/pages/10_bs_profile_doc.md:37`，PG17 表 `rebuild2._sample_bs_profile_summary`、`rebuild2.dim_bs_refined`。 影响说明：BS 画像需要“旧质量指标 + 新治理状态”双层读模型。
- **F11｜有偏差**：Cell 画像的记录/设备/GPS 原始点/P50/P90/原始率/RSRP 可部分复用样本表，但 `lifecycle_state`、`health_state`、最近批次四分流、基线质心差异并不在 rebuild2 现有表里。证据：`docs/rebuild3/UI_v2/pages/11_cell_profile_doc.md:38`，PG17 表 `rebuild2._sample_cell_profile_summary`。 影响说明：Cell 画像必须联接对象层、事实层、基线层。
- **F12｜缺失**：初始化页需要统一的初始化结果记录表；rebuild2 只有 `trusted_build_result`、`enrich_result` 等零散 step 结果，没有完整 init run 结果。 影响说明：初始化页无法直接落到现有 meta 表。
- **F13｜有偏差**：综合来看，rebuild2 只能复用“L0 标准化、可信 LAC/Cell/BS 统计、异常研究、画像样本聚合”这些局部资产；UI v2 对对象状态、批次、基线、观察工作台、验证结果提出了一整套新表需求。 影响说明：实施计划必须先做表需求清单，而不是边做边补。

### G. 页面内容匹配

- **G1｜有偏差**：首页“流转总览”只覆盖了增量链路，初始化步骤被拆到独立页面，因此单页上并未同时覆盖 6.1 和 7.1 的全部步骤。证据：`docs/rebuild3/UI_v2/pages/01_flow_overview.html:208`，`docs/rebuild3/UI_v2/pages/12_initialization.html:152`。 影响说明：首页语义与“全流程总览”仍有缝隙。
- **G2｜一致**：时间快照页的“初始化后 + 自定义1 + 自定义2”三列设计，配合重跑标记，能够承接局部重跑和修复前后对照。证据：`docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html:170`，`docs/rebuild3/UI_v2/pages/01_flow_overview_timeline.html:199`。 影响说明：符合 04c 提出的非全量重跑心智。
- **G3｜有偏差**：等待/观察工作台直接用 `10 GPS / 2 设备 / 3 天` 作为推进门槛，混淆了存在资格、锚点资格和基线资格。冻结文档只把 10/2/1 天作为 anchorable 的 v1 建议，而 Cell 晋升门槛应保持参数化。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:280`，`docs/rebuild3/UI_v2/pages/05_observation_workspace.html:718`。 影响说明：工作台建议动作会错误引导对象晋升。
- **G4｜有偏差**：异常工作台只覆盖对象级异常，未覆盖 10.1 的记录级异常（GPS 偏离、GPS 缺失回填、信号 donor 补齐、`normal_spread`、`single_large`）和结构不合规。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:313`，`docs/rebuild3/UI_v2/pages/06_anomaly_workspace.html:646`。 影响说明：异常视角无法覆盖完整资格矩阵。
- **G5｜有偏差**：基线页解释了“为什么触发”，但没有把“批次结束后才刷新、只供下一批次复用”的冻结原则显式写入触发说明。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:386`，`docs/rebuild3/UI_v2/pages/07_baseline_profile.html:557`。 影响说明：用户可能误以为 baseline 在批内可即时参与判定。
- **G6｜有偏差**：验证/对照页只展示 5 个收敛维度，缺少冻结文档要求的“热层稳定性”。证据：`docs/rebuild3/01_rebuild3_说明_最终冻结版.md:470`，`docs/rebuild3/UI_v2/pages/08_validation_compare.html:507`。 影响说明：验收面板不能完整反映 3+4 vs 7 天的收敛要求。
- **G7｜需决策**：对象浏览页与 LAC/BS/Cell 画像页的职责边界在设计说明里被定义为“治理视角 vs 数据质量视角”，但 `questions_for_review.md` 明确表明导航关系尚未拍板。证据：`docs/rebuild3/UI_v2/design_notes.md:92`，`docs/rebuild3/Docs/questions_for_review.md:5`。 影响说明：IA、导航层级和 API 复用边界都依赖这个决策。
- **G8｜一致**：04c 指出的四个偏差已基本修正：首页改为流转总览，回放对比降级为验证模块，时间快照支持重跑语义，页面优先级也改成“流动 → 原因 → 验证”。证据：`docs/rebuild3/04c_UI目的与改版说明.md:174`，`docs/rebuild3/UI_v2/design_notes.md:68`。 影响说明：UI v2 的总体叙事方向已对齐冻结目标。

## 偏差详情

### DEV-A1 生命周期枚举未在所有页面保持完整

- **审计项**：A1
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：冻结版要求所有对象统一使用 `waiting / observing / active / dormant / retired / rejected`。
  - UI v2 怎么设计的：对象浏览页完整使用了 6 个状态，但 LAC 画像仅展示活跃/休眠/退役，Cell 画像仅展示活跃/等待中/观察中/休眠。
  - rebuild2 怎么实现的：rebuild2 没有 `lifecycle_state` 概念，只有统计/画像表。
- **差异描述**：UI 在不同页面把生命周期裁成了不同子集，且没有稳定字段名。
- **影响范围**：影响对象列表、画像页筛选、详情页状态时间线和对象快照表的统一枚举。
- **建议修正方案**：所有页面统一落到 `lifecycle_state`；允许按页面隐藏不用的值，但不得改名、删枚举。

### DEV-A2 健康状态表达回退到旧质量分类

- **审计项**：A2
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：冻结版要求 `health_state` 只使用 7 个持久化取值。
  - UI v2 怎么设计的：LAC 画像引入 `覆盖不足`，BS/Cell 画像重新使用“异常分类 + GPS 可信度”，Cell 画像主表还使用 `健康 / 异常 / 空`。
  - rebuild2 怎么实现的：rebuild2 主要使用 `classification_v2`、`gps_confidence`、`signal_confidence`。
- **差异描述**：UI 把新旧两套模型混写，导致对象状态与画像质量没有统一主语。
- **影响范围**：健康筛选、异常工作台、事实路由和对象详情的解释口径都会漂移。
- **建议修正方案**：对象层只保留 `health_state`；画像页若需要质量标签，应改为派生字段或异常标签，不再替代 `health_state`。

### DEV-A4 三类资格在等待/异常页面表达不完整

- **审计项**：A4
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：冻结版要求对象必须同时回答存在资格、锚点资格、基线资格。
  - UI v2 怎么设计的：对象浏览/详情展示了锚点与基线标签，但等待工作台只展示样本门槛，异常页只展示“禁锚/禁基线”。
  - rebuild2 怎么实现的：rebuild2 没有三层资格模型。
- **差异描述**：等待/观察链路没有把“是否已被系统承认存在”与“能否当锚点/进基线”拆开。
- **影响范围**：工作台会把对象推进误读成单一晋升门槛，难以对齐事实分层。
- **建议修正方案**：等待工作台增加“存在资格 / 锚点资格 / 基线资格”三段式文案和进度；异常页补充资格失效原因。

### DEV-A7 画像页字段对现有表的复用度被高估

- **审计项**：A7
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：预实施任务书要求对象页和画像页围绕读模型，而不是直接依赖旧表。
  - UI v2 怎么设计的：09/10/11 页面同时要求状态、资格、空间指标、来源构成和最近事实分布。
  - rebuild2 怎么实现的：旧画像表只提供样本级空间/信号指标，不提供 rebuild3 状态和资格。
- **差异描述**：UI 所需字段横跨对象层、事实层、基线层和异常层，不能由单一旧表直接满足。
- **影响范围**：如果按“前端直接读旧画像表”实施，会导致字段缺口和 API 拼装混乱。
- **建议修正方案**：分别定义 `profile_lac`、`profile_bs`、`profile_cell` 读模型，并显式列出来自对象/事实/基线/异常的字段来源。

### DEV-B1 四分流命名出现缩写体

- **审计项**：B1
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：冻结版只接受 `fact_governed / fact_pending_observation / fact_pending_issue / fact_rejected`。
  - UI v2 怎么设计的：设计说明、批次中心、Cell 画像中出现了 `pending_obs`、`fact_pending_obs`。
  - rebuild2 怎么实现的：旧实现没有四分流体系。
- **差异描述**：UI 关键页面已经把缩写写进 mock 字段和标签。
- **影响范围**：后续表名、接口字段名、ECharts series 名称都会被带偏。
- **建议修正方案**：统一改为全称；文案层可显示“观察事实”，但技术字段与 mock key 不再出现缩写。

### DEV-B2 四分流路由条件没有在 UI 中被精确表达

- **审计项**：B2
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：7.2 明确规定四条路由分别对应“已知且健康/仅记录级异常”“已知但对象级异常”“未知但合规”“结构不合规”。
  - UI v2 怎么设计的：流转总览展示了四个结果节点，但没有把进入条件写在页面说明或节点文案里。
  - rebuild2 怎么实现的：旧实现以 trusted / anomaly / reject 为主，不具备同语义四分流。
- **差异描述**：UI 更像“结果仪表”，而不是“决策说明板”。
- **影响范围**：审计和开发阶段都无法从原型直接校验路由逻辑。
- **建议修正方案**：在流转节点 tooltip、批次详情和事实列表页统一展示四条冻结版路由说明。

### DEV-B3 rebuild2 缺少 observation 等价事实层

- **审计项**：B3
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：rebuild3 把等待/观察定义为独立事实层 `fact_pending_observation`。
  - UI v2 怎么设计的：等待工作台和 Cell 画像都依赖 observation 事实。
  - rebuild2 怎么实现的：只有 trusted/enriched、异常研究和合规淘汰，缺少 observation 事实表。
- **差异描述**：rebuild3 新增了真正的“候选事实层”。
- **影响范围**：等待池、观察池和晋升链路都不能复用 rebuild2 数据路径。
- **建议修正方案**：把 `fact_pending_observation` 作为 rebuild3 独立长期事实层设计进 schema。

### DEV-B4 资格矩阵在异常与详情页中未完整落地

- **审计项**：B4
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：10.3 要求每种情况同时回答“去向 / 锚点 / baseline”。
  - UI v2 怎么设计的：动态、碰撞、waiting 等场景已有表达，但 `single_large`、`normal_spread`、结构不合规未被放进异常工作台和详情页。
  - rebuild2 怎么实现的：旧异常页聚焦 BS 级研究分类，不覆盖 rebuild3 资格矩阵。
- **差异描述**：矩阵只落了一部分 happy-path / obvious-path 场景。
- **影响范围**：开发时会遗漏边界异常的去向与资格。
- **建议修正方案**：在异常工作台增加记录级异常视图，并在对象详情补“事实去向 + 资格原因 + baseline 资格”说明。

### DEV-C2 rebuild2 初始化链路与 rebuild3 初始化语义不等价

- **审计项**：C2
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：初始化要求 run/version 绑定、Cell 晋升、BS/LAC 派生、完整回归、baseline v1。
  - UI v2 怎么设计的：初始化页完全按照 rebuild3 新语义绘制。
  - rebuild2 怎么实现的：存在标准化、可信 LAC、Cell/BS 聚合与异常研究，但没有等待/观察/晋升状态机、LAC 派生、baseline。
- **差异描述**：rebuild2 更像静态构建链，rebuild3 是对象治理冷启动链。
- **影响范围**：后端实施不能简单按旧 SQL 顺序搬运。
- **建议修正方案**：把 rebuild2 可复用步骤拆成“标准化输入层”“样本聚合层”“异常研究层”，在其上重建 rebuild3 初始化编排。

### DEV-C3 初始化 mock 规模与现有结果集不匹配

- **审计项**：C3
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：冻结文档没有给出具体对象量级，但要求 UI 与验证路径保持可追溯。
  - UI v2 怎么设计的：初始化 mock 写死 12,782 Cell / 3,382 BS / 152 LAC。
  - rebuild2 怎么实现的：当前已知全量表与样本表都不是这一组数量。
- **差异描述**：mock 既不像全量，也不像 6 个样本 LAC 的聚合结果。
- **影响范围**：分页、性能预估、空状态阈值和趋势图比例都可能被误导。
- **建议修正方案**：用一次真实样本跑数替换初始化 mock，至少让 Cell/BS/LAC 三个量级来自同一套结果集。

### DEV-C4 完整回归一次在 rebuild2 中没有对应实现

- **审计项**：C4
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：6.2 第 7 点要求首轮对象库形成后再做一次完整回归。
  - UI v2 怎么设计的：初始化页把它画成了独立第 10 步。
  - rebuild2 怎么实现的：现有 SQL 链以表构建和汇总为主，没有二次全链路回归。
- **差异描述**：这是 rebuild3 新增的冷启动纠偏步骤。
- **影响范围**：如果忽略，会把研究期“先粗后细”语义直接带入 baseline。
- **建议修正方案**：在实施计划中单列“初始化首轮完成后的完整回归”任务和验收。

### DEV-D3 上一版冻结 baseline 原则没有成为全局上下文

- **审计项**：D3
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：冻结版明确要求“当前批次只看上一版冻结 baseline”。
  - UI v2 怎么设计的：仅流程图和时间快照页面点到为止，其他核心页面缺少同一提示。
  - rebuild2 怎么实现的：旧实现没有 baseline 版本体系。
- **差异描述**：关键原则被埋在单页流程里，而不是作为跨页面上下文。
- **影响范围**：会误导用户把本批结果和当前判定混在一起。
- **建议修正方案**：在全局上下文条加入“当前判定参考 baseline_version=xxx（上一版冻结）”固定提示。

### DEV-D4 rebuild2 不具备 2 小时增量能力

- **审计项**：D4
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：rebuild3 核心变化就是初始化 + 2 小时增量共用骨架。
  - UI v2 怎么设计的：批次中心、流转总览、时间快照都以 batch 为主语。
  - rebuild2 怎么实现的：没有 run/batch 表，也没有 batch_id、重跑、baseline 版本等控制语义。
- **差异描述**：增量链路是 rebuild3 几乎全新的后端能力。
- **影响范围**：批次控制、重跑、状态承接、快照记录都要新建。
- **建议修正方案**：把元数据层（run/batch/baseline/version）列为开发优先级 M0。

### DEV-E1 五类版本标识没有在全页面完整出现

- **审计项**：E1
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：所有对象、事实、异常、画像、读模型都必须可追溯到 run / batch / contract / rule_set / baseline。
  - UI v2 怎么设计的：只有首页完整；批次中心无 batch_id，基线页无 run/batch/contract，初始化 API 文档写成 `rule_version`。
  - rebuild2 怎么实现的：旧实现本身也没有这套版本体系。
- **差异描述**：页面上下文条没有统一模板。
- **影响范围**：用户难以确认“当前正在看哪一版结果”。
- **建议修正方案**：抽象统一 `VersionContext` 组件，强制所有主页面至少展示五类版本中的适用项。

### DEV-E2 rebuild2 无结构化 run/batch 元数据

- **审计项**：E2
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：要求 `run_id` 与 `batch_id` 分离，并能重复回放和比对。
  - UI v2 怎么设计的：运行/批次中心高度依赖这两张表。
  - rebuild2 怎么实现的：meta 只保存 `run_label` 字符串，没有 run、batch 实体。
- **差异描述**：旧库缺的是模型，不是字段 rename。
- **影响范围**：运行中心、时间快照、验证对照全部无法直接复用旧元数据。
- **建议修正方案**：在 `rebuild3_meta` 新建 `run`, `batch`, `batch_source`, `batch_rerun_link` 等表。

### DEV-E3 batch_snapshot 仅存在于 UI 方案中

- **审计项**：E3
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：冻结文档未定义 `batch_snapshot`。
  - UI v2 怎么设计的：时间快照版把它作为核心数据底座。
  - rebuild2 怎么实现的：数据库中无此表。
- **差异描述**：这是 UI 的合理新增需求，而非现有实现映射项。
- **影响范围**：如果不入计划，时间快照页会在开发时失去数据来源。
- **建议修正方案**：将其标记为“新增读模型支撑表”，在最终实施任务书中补充 DDL、更新机制和保留策略。

### DEV-F1 流转总览依赖的批次汇总表在 rebuild2 中缺席

- **审计项**：F1
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：首页必须展示批次流向、四分流、晋升/降级、异常、baseline 刷新。
  - UI v2 怎么设计的：首页和批次中心都按 batch 粒度展示这些统计。
  - rebuild2 怎么实现的：只有 step 级缓存和构建结果，没有 batch 级汇总表。
- **差异描述**：首页读模型没有可直接对齐的旧表。
- **影响范围**：只能靠实时大查询拼首页，性能与一致性都不可控。
- **建议修正方案**：新增 `batch_flow_summary`、`batch_decision_summary`、`batch_anomaly_summary`、`batch_baseline_refresh_log`。

### DEV-F2 时间快照页需要全新的 batch_snapshot 设计

- **审计项**：F2
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：冻结版没有现成表定义。
  - UI v2 怎么设计的：时间快照页明确要求保留各阶段历史快照并支持任意两点对照。
  - rebuild2 怎么实现的：没有快照存储。
- **差异描述**：不是字段补充，而是新的读模型底座。
- **影响范围**：快照页、局部重跑对照、问题复盘都无从落地。
- **建议修正方案**：建议至少包含 `snapshot_id`, `run_id`, `batch_id`, `snapshot_time`, `stage_code`, `metrics_json`, `is_rerun`, `source_batch_id`, `baseline_version_before`, `baseline_version_after`。

### DEV-F3 运行/批次中心缺少 run/batch 实体表

- **审计项**：F3
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：运行中心是 UI 一级页面。
  - UI v2 怎么设计的：页面要展示 run 类型、状态、窗口、重跑、关联批次。
  - rebuild2 怎么实现的：不存在 run/batch 表。
- **差异描述**：旧实现没有同级实体可映射。
- **影响范围**：运行/批次中心、时间快照和验证页都无主键主语。
- **建议修正方案**：新建 `run`、`batch` 两张主表，以及必要的重跑关系表。

### DEV-F4 对象快照表需要在旧统计表之上重组

- **审计项**：F4
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：对象快照表至少要支持状态、资格、关系、版本和摘要统计。
  - UI v2 怎么设计的：对象浏览、详情、画像、异常、等待页都共享对象快照。
  - rebuild2 怎么实现的：现有 `dim_cell_stats/refined`、`dim_bs_stats/refined`、`dim_lac_trusted` 只覆盖统计与空间属性。
- **差异描述**：缺少生命周期、健康状态、资格、关系历史、版本绑定。
- **影响范围**：若不重组，所有对象相关页面都要各自拼 SQL。
- **建议修正方案**：将旧表作为初始化输入，重新沉淀 `obj_cell / obj_bs / obj_lac` 与历史表。

### DEV-F5 等待/观察工作台没有旧数据源可复用

- **审计项**：F5
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：等待池必须回答“还差什么、最近有没有推进、建议做什么”。
  - UI v2 怎么设计的：工作台使用 `progress_percent`、`trend_direction`、`stall_batches`、`suggested_action`。
  - rebuild2 怎么实现的：没有 waiting / observing 对象和批次进度。
- **差异描述**：工作台属于 rebuild3 新增能力。
- **影响范围**：等待/观察工作台必须从事实层和 batch 维度重新计算。
- **建议修正方案**：新增 observation 事实、候选对象进度表和批次推进汇总表。

### DEV-F6 异常工作台字段超出 rebuild2 研究表边界

- **审计项**：F6
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：异常页要表达类型、严重度、资格、证据趋势和下游影响。
  - UI v2 怎么设计的：异常工作台明确展示 `severity`、`discovered_batch`、`downstream_objects`、`suggested_action`。
  - rebuild2 怎么实现的：研究表只提供分类结果和部分碰撞细节。
- **差异描述**：缺少批次语义、资格语义和下游影响路径。
- **影响范围**：异常页无法靠旧表直接落地，且无法服务工作流动作。
- **建议修正方案**：新增 `anomaly_issue`、`anomaly_evidence`、`anomaly_impact_path` 三类表。

### DEV-F7 基线版本体系完全缺失

- **审计项**：F7
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：baseline_version 是 rebuild3 五大主语之一。
  - UI v2 怎么设计的：基线页要求版本历史、触发原因、差异和稳定性评分。
  - rebuild2 怎么实现的：schema 与 meta 中都无 baseline 表。
- **差异描述**：需要从零建立版本、对象快照和差异结构。
- **影响范围**：基线页、对象详情基线引用、下一批参照逻辑均无落点。
- **建议修正方案**：新增 `baseline_version`, `baseline_cell`, `baseline_bs`, `baseline_lac`, `baseline_diff`。

### DEV-F8 验证对照结果没有持久化载体

- **审计项**：F8
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：验证路径是本期验收主线。
  - UI v2 怎么设计的：验证页需要异步对比、分页差异列表和可解释性摘要。
  - rebuild2 怎么实现的：没有 compare result 表或 compare task 表。
- **差异描述**：当前只能临时计算，无法复查或复用。
- **影响范围**：收敛验证结果难以沉淀、难以回放。
- **建议修正方案**：新增 `validation_compare_task` 与 `validation_compare_result` 两张表或等价缓存层。

### DEV-F9 LAC 画像主表字段需要大规模补算

- **审计项**：F9
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：LAC 画像既是对象视图，也是区域质量视图。
  - UI v2 怎么设计的：主表需要位置、生命周期、健康、Cell/BS/记录/设备、面积、异常占比、GPS/信号原始率、RSRP。
  - rebuild2 怎么实现的：只有 `dim_lac_trusted` 和样本 LAC 画像能提供其中一部分。
- **差异描述**：生命周期、健康、区域质量和大部分聚合字段都不能直接从 `dim_lac_trusted` 读取。
- **影响范围**：LAC 画像页会成为字段最碎、聚合最重的一页。
- **建议修正方案**：单独设计 `profile_lac` 读模型，按对象层 + 事实层 + 异常层进行预聚合。

### DEV-F10 BS 画像仍然强依赖旧 classification/confidence

- **审计项**：F10
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：rebuild3 对象层应以 `health_state` + 资格为主。
  - UI v2 怎么设计的：BS 画像主表和详情仍以“异常分类 + GPS 可信度”为核心。
  - rebuild2 怎么实现的：这正是旧样本画像的主要字段。
- **差异描述**：UI 画像页保留了旧模型，但冻结版没有对应持久化字段。
- **影响范围**：BS 画像将与对象浏览页出现两套状态主语。
- **建议修正方案**：BS 画像保留空间精度指标，但把主状态改为 `health_state`、`anchorable`、`baseline_eligible`；旧分类仅作为解释标签。

### DEV-F11 Cell 画像需要同时联接对象/事实/基线三层

- **审计项**：F11
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：Cell 是最小治理主语，画像页必须能看到状态、空间、事实去向。
  - UI v2 怎么设计的：Cell 画像既要展示 lifecycle/health，又要展示基线质心偏差和最近批次四分流。
  - rebuild2 怎么实现的：旧样本表只有空间/信号和部分 BS 分类字段。
- **差异描述**：Cell 画像已不是单纯 profile summary，而是治理+画像融合页。
- **影响范围**：如果没有新的预聚合表，页面查询复杂度会非常高。
- **建议修正方案**：新增 `profile_cell` 读模型，至少联接 `obj_cell`、`baseline_cell`、`fact_*` 批次汇总。

### DEV-F12 初始化页缺少统一结果记录表

- **审计项**：F12
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：初始化是单独入口，但应有完整结果留痕。
  - UI v2 怎么设计的：页面要同时展示流程步骤、结果汇总、事实分布和特殊策略。
  - rebuild2 怎么实现的：只有零散构建结果，不存在 init run 结果对象。
- **差异描述**：初始化结果没有单一主表承接。
- **影响范围**：初始化页、初始化重跑和冷启动审计都无法标准化。
- **建议修正方案**：新增 `initialization_run_result` 与 `initialization_step_result`。

### DEV-F13 UI v2 已隐含一整套新增表需求

- **审计项**：F13
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：预实施任务书要求在 UI 确认后再输出最终建模任务书。
  - UI v2 怎么设计的：页面已经隐含出对象层、事实层、基线层、批次层、验证层多个新表。
  - rebuild2 怎么实现的：旧库只能提供初始化输入和参考聚合逻辑。
- **差异描述**：如果不先出完整表清单，开发阶段会持续返工。
- **影响范围**：DDL、API、缓存策略和前端 mock 都会同时失焦。
- **建议修正方案**：先把本报告末尾的“UI 隐含表需求汇总”转成最终实施任务书的 M0/M5/M6/M7 输入。

### DEV-G1 流转总览与初始化总览仍然分裂为两页

- **审计项**：G1
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：审计项要求核查 6.1 与 7.1 是否被完整覆盖。
  - UI v2 怎么设计的：增量链路放在首页，初始化链路放在独立页面。
  - rebuild2 怎么实现的：旧 UI 更偏 step 页面，不构成直接约束。
- **差异描述**：全流程总览被拆开，首页看不到冷启动与增量的整体衔接。
- **影响范围**：用户理解“初始化后如何进入增量”时需要跨页跳转。
- **建议修正方案**：至少在首页增加“初始化入口卡”和“初始化→增量切换说明”，避免语义断裂。

### DEV-G3 等待/观察页把 anchorable 建议阈值当成晋升阈值

- **审计项**：G3
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：存在资格、锚点资格、基线资格是三层门槛；10/2/1 天只属于 anchorable v1 建议。
  - UI v2 怎么设计的：工作台用 10 GPS / 2 设备 / 3 天去驱动 waiting/observing 的推进和建议动作。
  - rebuild2 怎么实现的：旧画像里的 GPS 可信度高/中/低并不是 waiting/observing 状态机。
- **差异描述**：UI 混淆了“对象被承认存在”和“对象可做锚点”。
- **影响范围**：晋升建议、观察池排序、对象状态转移都会偏离冻结版。
- **建议修正方案**：把工作台拆成三段进度：存在资格进度、锚点资格进度、基线成熟进度。

### DEV-G4 异常工作台只覆盖对象级异常

- **审计项**：G4
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：10.1 与 10.2 要同时覆盖记录级和对象级异常。
  - UI v2 怎么设计的：异常工作台只列 collision、dynamic、migration、gps_bias。
  - rebuild2 怎么实现的：旧异常页也主要围绕 BS 级分类研究。
- **差异描述**：记录级异常、结构不合规和补齐来源风险没有入口。
- **影响范围**：事实分层和资格矩阵无法在 UI 层完整审阅。
- **建议修正方案**：在异常工作台增加“记录级异常 / 结构不合规”二级视图，或在批次详情中补齐。

### DEV-G5 基线页未把冻结刷新原则显式可视化

- **审计项**：G5
- **严重度**：重要
- **三方现状**：
  - 冻结文档怎么定义的：Section 12 关注的不是某个阈值，而是“先判定、后刷新、供下一批复用”的时序原则。
  - UI v2 怎么设计的：基线页展示了触发条件和贡献来源，但没有明确提示时序原则。
  - rebuild2 怎么实现的：旧实现没有 baseline 页面。
- **差异描述**：UI 解释了“为什么刷新”，没解释“什么时候才能刷新、刷新给谁用”。
- **影响范围**：用户和开发都容易忽略批次级冻结语义。
- **建议修正方案**：在基线页概况区新增“生效时序”说明：本版 baseline 仅供下一批次使用。

### DEV-G6 验证页缺少热层稳定性维度

- **审计项**：G6
- **严重度**：阻塞
- **三方现状**：
  - 冻结文档怎么定义的：15.1 明确列出 6 个对比维度，其中包含热层稳定性。
  - UI v2 怎么设计的：页面只展示对象、空间、信号、异常、决策 5 个指标。
  - rebuild2 怎么实现的：旧系统也没有热层稳定性展示。
- **差异描述**：验收面板缺了一项冻结版定义的硬指标。
- **影响范围**：3+4 vs 7 天验证的通过条件不完整。
- **建议修正方案**：补一张“热层稳定性”指标卡和对应差异对象/Cell 波动列表。

## UI 隐含的表需求汇总

| 表名 | 用途 | 服务哪些页面 | rebuild2 是否有等价表 | 可复用程度 | 需要新增的字段 | 需要新建 |
|------|------|------------|-------------------|----------|-------------|---------|
| run | 记录一次初始化或增量运行的主上下文 | 流转总览、运行/批次中心、验证/对照 | 无 | 0% | `run_type`, `status`, `window_start`, `window_end`, `contract_version`, `rule_set_version`, `baseline_version_before/after` | 是 |
| batch | 记录 2 小时批次及重跑关系 | 流转总览、流转快照、运行/批次中心 | 无 | 0% | `batch_id`, `run_id`, `source_batch_id`, `is_rerun`, `window_start/end`, `status` | 是 |
| batch_flow_summary | 批次四分流与输入/输出汇总 | 流转总览、运行/批次中心 | 无 | 0% | `governed_count`, `pending_observation_count`, `pending_issue_count`, `rejected_count`, `delta_vs_previous` | 是 |
| batch_decision_summary | 批末晋升/降级/级联更新结果 | 流转总览、运行/批次中心、对象详情 | 无 | 0% | `promoted_count`, `demoted_count`, `cascade_bs_count`, `cascade_lac_count` | 是 |
| batch_anomaly_summary | 批次级异常汇总与变化 | 流转总览、异常工作台 | 无 | 0% | `by_health_state`, `disabled_anchorable_count`, `disabled_baseline_count`, `trend` | 是 |
| batch_baseline_refresh_log | 批次是否触发 baseline 刷新及原因 | 流转总览、运行/批次中心、基线/画像 | 无 | 0% | `triggered`, `reason`, `source_batch_id`, `baseline_version_before/after` | 是 |
| batch_snapshot | 时间快照版首页的阶段快照 | 流转快照、验证/回放解释 | 无 | 0% | `stage_code`, `snapshot_time`, `metrics_json`, `is_rerun`, `source_batch_id` | 是 |
| obj_cell | Cell 当前快照 | 对象浏览、对象详情、等待工作台、Cell 画像 | `dim_cell_stats` / `dim_cell_refined` | 40% | `lifecycle_state`, `health_state`, `anchorable`, `baseline_eligible`, `baseline_version`, `last_batch_id` | 是（重组） |
| obj_bs | BS 当前快照 | 对象浏览、对象详情、异常工作台、BS 画像 | `dim_bs_stats` / `dim_bs_refined` | 45% | `lifecycle_state`, `health_state`, `anchorable`, `baseline_eligible`, `active_child_cell_count` | 是（重组） |
| obj_lac | LAC 当前快照 | 对象浏览、对象详情、LAC 画像 | `dim_lac_trusted` | 25% | `lifecycle_state`, `health_state`, `anchorable`, `baseline_eligible`, `location_name`, `area_km2` | 是（重组） |
| obj_state_history | 对象状态变更留痕 | 对象详情、异常复核 | 无 | 0% | `from_lifecycle_state`, `to_lifecycle_state`, `from_health_state`, `to_health_state`, `reason`, `batch_id` | 是 |
| obj_relation_history | Cell-BS-LAC 关系变化与迁移留痕 | 对象详情、异常工作台 | 无 | 0% | `change_type`, `old_parent_key`, `new_parent_key`, `batch_id` | 是 |
| fact_standardized | 不可变标准事件层 | 流转快照、验证/审计 | `l0_gps` / `l0_lac` / 标准化脚本结果 | 30% | `event_id`, `event_time`, `batch_id`, `run_id`, `contract_version`, `idempotency_key` | 是（新标准层） |
| fact_governed | 已治理事实 | 流转总览、对象详情、画像页 | `dwd_fact_enriched` | 55% | `baseline_eligible`, `anomaly_tags`, `batch_id`, `baseline_version`, `obj_keys` | 是（改造） |
| fact_pending_observation | 等待/观察事实 | 等待工作台、Cell 画像、对象详情 | 无 | 0% | `progress_inputs`, `candidate_key`, `batch_id`, `observation_reason` | 是 |
| fact_pending_issue | 问题事实 | 异常工作台、对象详情、Cell 画像 | 无直接等价（仅异常研究表） | 15% | `issue_key`, `health_state`, `severity`, `batch_id`, `downstream_impact` | 是 |
| fact_rejected | 拒收事实 | 流转总览、批次中心、初始化页 | ODS/可信链路中的淘汰结果 | 20% | `reject_reason`, `batch_id`, `contract_version`, `source_record_id` | 是 |
| observation_candidate_rm | 候选对象推进读模型 | 等待/观察工作台 | 无 | 0% | `progress_percent`, `trend_direction`, `stall_batches`, `suggested_action` | 是 |
| anomaly_issue | 异常对象主表 | 异常工作台、对象详情 | `_research_bs_classification_v2` / `dim_cell_refined` | 25% | `discovered_batch`, `severity`, `anchorable`, `baseline_eligible`, `suggested_action` | 是（重组） |
| anomaly_impact_path | 异常影响链路 | 异常工作台、对象详情、基线页 | 无 | 0% | `downstream_object_key`, `impact_type`, `impact_count`, `batch_id` | 是 |
| baseline_version | baseline 版本头表 | 基线/画像、流转总览、验证/对照 | 无 | 0% | `baseline_version`, `rule_set_version`, `source_batch_id`, `created_at`, `refresh_reason` | 是 |
| baseline_cell / baseline_bs / baseline_lac | 各对象基线快照 | 基线/画像、对象详情、Cell/BS/LAC 画像 | 无 | 0% | `baseline_version`, `object_key`, `centroid`, `coverage_metrics`, `quality_grade` | 是 |
| baseline_diff | 与上一版 baseline 的差异摘要 | 基线/画像、对象详情 | 无 | 0% | `change_type`, `object_key`, `detail_json`, `source_batch_id` | 是 |
| profile_lac / profile_bs / profile_cell | 画像页预聚合读模型 | 09/10/11 画像页 | `_sample_lac_profile_v1` / `_sample_bs_profile_summary` / `_sample_cell_profile_summary` | 35%-60% | `lifecycle_state`, `health_state`, `qualification`, `recent_fact_distribution`, `baseline_diff` | 是（重组） |
| initialization_run_result | 初始化结果头表 | 初始化数据页、验证/对照 | 无 | 0% | `run_id`, `window`, `status`, `summary_json`, `distribution_json`, `baseline_version` | 是 |
| initialization_step_result | 初始化步骤明细 | 初始化数据页 | `trusted_build_result` / `enrich_result` | 15% | `step_seq`, `step_name`, `input_count`, `output_count`, `detail_json` | 是（重组） |
| validation_compare_task / validation_compare_result | 对比任务与结果 | 验证/对照 | 无 | 0% | `run_a`, `run_b`, `status`, `object_convergence`, `spatial_convergence`, `heat_layer_stability` | 是 |
