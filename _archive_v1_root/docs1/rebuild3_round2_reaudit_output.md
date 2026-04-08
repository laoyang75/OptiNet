# rebuild3 第二轮彻底复评输出

审计时间：2026-04-05
产物路径：`docs1/rebuild3_round2_reaudit_output.md`、`docs1/rebuild3_field_baseline.md`

## 第一部分：总评结论

- 当前总评：不通过。文档基线已经足够清晰，但当前实现只在对象主状态层和部分画像页上接近 UI_v2；主流程页、快照页、批次中心、baseline、初始化页以及支撑治理页仍存在“页面能开、主语不对 / 有值返回、口径不对 / 选项存在、底座是伪语义”的系统级偏差。
- 问题计数：P0 = 2，P1 = 5，P2 = 2，P3 = 2。
- 是否允许进入下一阶段实施：不允许直接进入下一轮功能扩展或样式收尾；必须先修完全部 P0 和核心 P1，否则下一轮实现仍会继续在错误基线上叠加。
- 当前基线是否足够稳定：
  - 文档基线：稳定，可作为下一轮唯一真相源。
  - 实现基线：不稳定，尤其是 scenario/timepoint/batch_snapshot/baseline 对齐层面。
- 一句话结论：rebuild3 已经从“UI 没对齐”进展到“UI 壳体大体对齐”，但还没有真正回到“冻结业务语义 + UI_v2 设计语义 + 真实数据链路”三层共同约束下的正确系统语义。

## 第二部分：阶段性交付检查

### Phase 0：资料盘点与真相源分级基线

- 完成状态：完成
- 产物是否齐全：齐全
- 检查点结果：三份 Tier 0 已读完；UI_v2 页面文档已纳入；Tier 2 已按需查阅；数据库里存在两套初始化场景和一套 smoke 场景，均可定位到真实 `run_id`。
- 阶段结论：通过

#### 0.1 文档清单与分级表

| 层级 | 资料 | 状态 | 用途 |
|---|---|---|---|
| Tier 0 | `rebuild3/docs/01_rebuild3_说明_最终冻结版.md` | 已读 | 冻结业务语义、四分流、baseline 原则 |
| Tier 0 | `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md` | 已读 | 页面目标、对象主语、资格边界 |
| Tier 0 | `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md` | 已读 | SQL-first / Postgres-first / Vue3 / FastAPI 边界 |
| Tier 1 | `rebuild3/docs/UI_v2/design_notes.md` | 已读 | IA、读模型、页面表达优先级 |
| Tier 1 | `rebuild3/docs/UI_v2/index.html` | 已读 | 总览说明，含快照视图说明 |
| Tier 1 | `rebuild3/docs/UI_v2/design_system.html` | 已读 | 视觉组件基线 |
| Tier 1 | `rebuild3/docs/UI_v2/pages/*.html` | 已读 | 页面布局与静态表达 |
| Tier 1 | `rebuild3/docs/UI_v2/pages/*_doc.md` | 已读 | 每页主问题、字段层次、交互要求 |
| Tier 2 | `rebuild3/docs/00_审核结论.md` | 按需查阅 | 文档冲突裁决参考 |
| Tier 2 | `rebuild3/docs/ui_final_rectification_report.md` | 按需查阅 | 上轮修复声明对照 |
| Tier 2 | `rebuild3/docs/api_models.md` | 按需查阅 | API 约定参考 |
| Tier 2 | `rebuild3/docs/param_matrix.md` | 按需查阅 | 资格阈值 |
| Tier 2 | `docs1/rebuild3_round2_execution_note.md` | 按需查阅 | 上轮执行说明 |
| Tier 2 | `docs1/rebuild3_snapshot_rerun_plan.md` | 按需查阅 | scenario/timepoint 设计补充 |
| 忽略 | `rebuild3/docs/04*`、`ui_restructure_prompt.md` 等历史 prompt | 明确忽略 | 非真相源，不参与裁决 |

#### 0.2 路由清单

| 路由 | 前端页面 | 备注 |
|---|---|---|
| `/` | 跳转到 `/flow/overview` | 首页入口 |
| `/flow/overview` | `rebuild3/frontend/src/pages/FlowOverviewPage.vue` | 主流程首页 |
| `/flow/snapshot` | `rebuild3/frontend/src/pages/FlowSnapshotPage.vue` | 时间快照版 |
| `/runs` | `rebuild3/frontend/src/pages/RunBatchCenterPage.vue` | 运行/批次中心 |
| `/objects` | `rebuild3/frontend/src/pages/ObjectsPage.vue` | 对象浏览 |
| `/objects/:objectType/:objectId` | `rebuild3/frontend/src/pages/ObjectDetailPage.vue` | 对象详情 |
| `/observation` | `rebuild3/frontend/src/pages/ObservationWorkspacePage.vue` | 等待/观察工作台 |
| `/anomalies` | `rebuild3/frontend/src/pages/AnomalyWorkspacePage.vue` | 异常工作台 |
| `/baseline` | `rebuild3/frontend/src/pages/BaselineProfilePage.vue` | 基线/画像 |
| `/compare` | `rebuild3/frontend/src/pages/ValidationComparePage.vue` | 验证/对照 |
| `/profiles/lac` | `rebuild3/frontend/src/pages/LacProfilePage.vue` | LAC 画像 |
| `/profiles/bs` | `rebuild3/frontend/src/pages/BsProfilePage.vue` | BS 画像 |
| `/profiles/cell` | `rebuild3/frontend/src/pages/CellProfilePage.vue` | Cell 画像 |
| `/initialization` | `rebuild3/frontend/src/pages/InitializationPage.vue` | 初始化数据 |
| `/governance` | `rebuild3/frontend/src/pages/GovernancePage.vue` | 基础数据治理 |

#### 0.3 页面 -> 设计稿映射表

| 路由 | UI_v2 设计稿 | 设计说明文档 |
|---|---|---|
| `/flow/overview` | `rebuild3/docs/UI_v2/pages/01_flow_overview.html` | `rebuild3/docs/UI_v2/pages/01_flow_overview_doc.md` |
| `/flow/snapshot` | `rebuild3/docs/UI_v2/pages/01_flow_overview_timeline.html` | 无独立 `_doc.md`；语义取自 `rebuild3/docs/UI_v2/design_notes.md`、`rebuild3/docs/UI_v2/index.html`、`rebuild3/docs/UI_v2/pages/01_flow_overview_timeline.html` |
| `/runs` | `rebuild3/docs/UI_v2/pages/02_run_batch_center.html` | `rebuild3/docs/UI_v2/pages/02_run_batch_center_doc.md` |
| `/objects` | `rebuild3/docs/UI_v2/pages/03_objects.html` | `rebuild3/docs/UI_v2/pages/03_objects_doc.md` |
| `/objects/:objectType/:objectId` | `rebuild3/docs/UI_v2/pages/04_object_detail.html` | `rebuild3/docs/UI_v2/pages/04_object_detail_doc.md` |
| `/observation` | `rebuild3/docs/UI_v2/pages/05_observation_workspace.html` | `rebuild3/docs/UI_v2/pages/05_observation_workspace_doc.md` |
| `/anomalies` | `rebuild3/docs/UI_v2/pages/06_anomaly_workspace.html` | `rebuild3/docs/UI_v2/pages/06_anomaly_workspace_doc.md` |
| `/baseline` | `rebuild3/docs/UI_v2/pages/07_baseline_profile.html` | `rebuild3/docs/UI_v2/pages/07_baseline_profile_doc.md` |
| `/compare` | `rebuild3/docs/UI_v2/pages/08_validation_compare.html` | `rebuild3/docs/UI_v2/pages/08_validation_compare_doc.md` |
| `/profiles/lac` | `rebuild3/docs/UI_v2/pages/09_lac_profile.html` | `rebuild3/docs/UI_v2/pages/09_lac_profile_doc.md` |
| `/profiles/bs` | `rebuild3/docs/UI_v2/pages/10_bs_profile.html` | `rebuild3/docs/UI_v2/pages/10_bs_profile_doc.md` |
| `/profiles/cell` | `rebuild3/docs/UI_v2/pages/11_cell_profile.html` | `rebuild3/docs/UI_v2/pages/11_cell_profile_doc.md` |
| `/initialization` | `rebuild3/docs/UI_v2/pages/12_initialization.html` | `rebuild3/docs/UI_v2/pages/12_initialization_doc.md` |
| `/governance` | `rebuild3/docs/UI_v2/pages/13_data_governance.html` | `rebuild3/docs/UI_v2/pages/13_data_governance_doc.md` |

#### 0.4 页面 -> API 映射表

| 路由 | 前端 API 调用 | 后端入口 |
|---|---|---|
| `/flow/overview` | `api.getFlowOverview()` | `rebuild3/backend/app/api/run.py:36` |
| `/flow/snapshot` | `api.getFlowSnapshots()` | `rebuild3/backend/app/api/run.py:139` + `rebuild3/backend/app/api/run_snapshot.py:362` |
| `/runs` | `api.getBatches()`、`api.getBatchDetail()` | `rebuild3/backend/app/api/run.py:154`、`rebuild3/backend/app/api/run.py:201` |
| `/objects` | `api.getObjectsSummary()`、`api.getObjectsList()` | `rebuild3/backend/app/api/object.py:20`、`rebuild3/backend/app/api/object.py:68` |
| `/objects/:objectType/:objectId` | `api.getObjectDetail()` | `rebuild3/backend/app/api/object_detail.py:166` |
| `/observation` | `api.getObservationWorkspace()` | `rebuild3/backend/app/api/run_workspaces.py:32` |
| `/anomalies` | `api.getAnomalyWorkspace()` | `rebuild3/backend/app/api/run_workspaces.py:196` |
| `/baseline` | `api.getBaselineProfile()` | `rebuild3/backend/app/api/run_workspaces.py:329` |
| `/compare` | `api.getCompareOverview()`、`api.getCompareDiffs()` | `rebuild3/backend/app/api/compare.py:95`、`rebuild3/backend/app/api/compare.py:105` |
| `/profiles/lac` | `api.getProfileList({ object_type: 'lac' })` | `rebuild3/backend/app/api/object.py:123` |
| `/profiles/bs` | `api.getProfileList({ object_type: 'bs' })` | `rebuild3/backend/app/api/object.py:123` |
| `/profiles/cell` | `api.getProfileList({ object_type: 'cell' })` | `rebuild3/backend/app/api/object.py:123` |
| `/initialization` | `api.getInitialization()` | `rebuild3/backend/app/api/run.py:241` |
| `/governance` | `api.getGovernanceOverview()`、`api.getGovernanceFields()`、`api.getGovernanceTables()`、`api.getGovernanceUsage()`、`api.getGovernanceMigration()` | `rebuild3/backend/app/api/governance.py:77`、`rebuild3/backend/app/api/governance.py:87`、`rebuild3/backend/app/api/governance.py:97`、`rebuild3/backend/app/api/governance.py:107`、`rebuild3/backend/app/api/governance.py:134` |

#### 0.5 API -> 表/视图映射表

| API | 主要表 / 视图 | 结论 |
|---|---|---|
| `/api/v1/runs/flow-overview` | `rebuild3_meta.batch_flow_summary`、`rebuild3_meta.batch_snapshot`、`rebuild3_meta.batch_baseline_refresh_log`、`rebuild3_meta.batch_anomaly_summary` | 当前硬绑 `FULL_BATCH_ID`，并用 sample validation 做 delta |
| `/api/v1/runs/flow-snapshots` | `rebuild3_meta.run`、`rebuild3_meta.batch`、`rebuild3_meta.batch_snapshot` | 结构上有 scenario/timepoint；语义上 scenario snapshot 不是实治理快照 |
| `/api/v1/runs/batches`、`/api/v1/runs/batch/{id}` | `rebuild3_meta.batch*`、`rebuild3_sample_meta.batch*` | 当前只读 full + sample 两个伪批次 |
| `/api/v1/objects/*` | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac`、`rebuild3.stg_*_profile`、`rebuild3_meta.r2_full_*` | 对象层主数据基本真实 |
| `/api/v1/runs/observation-workspace` | `rebuild3.obj_cell`、`rebuild3.stg_cell_profile`、`rebuild3_meta` 决策摘要 | 主列表真实，趋势仍用 sample/full fallback |
| `/api/v1/runs/anomaly-workspace` | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3_meta.batch_anomaly_summary` | 主体真实，但批次统计仍绑 `FULL_BATCH_ID` |
| `/api/v1/runs/baseline-profile` | `rebuild3.baseline_*`、`rebuild3_meta.baseline_version`、`rebuild3.obj_cell`、`rebuild3_meta.r2_full_*` | 不是“上一版 baseline 差异”，而是 rebuild2 对照 |
| `/api/v1/compare/*` | 无 live compare 读模型；纯 fallback 常量 | 非真实对比数据 |
| `/api/v1/governance/*` | 无 live 元数据注册表；纯 fallback catalog | 非真实治理目录 |

#### 0.6 场景 / 运行数据基线

| run_id | run_type | scenario_key | init_days | step_hours | 完成批次数 | 说明 |
|---|---|---|---:|---:|---:|---|
| `RUN-SCN-INIT2D_STEP2H-20260405101143177` | `scenario_replay` | `INIT2D_STEP2H` | 2 | 2 | 61 | 1 个 init + 60 个 rolling_2h |
| `RUN-SCN-INIT1D_STEP2H-20260405100310813` | `scenario_replay` | `INIT1D_STEP2H` | 1 | 2 | 73 | 1 个 init + 72 个 rolling_2h |
| `RUN-SCN-SMOKE_INIT1D_STEP2H-20260405095741106` | `scenario_replay` | `SMOKE_INIT1D_STEP2H` | 1 | 2 | 7 | smoke 链路 |
| `RUN-FULL-20251201-20251207-V1` | `full_initialization` | `null` | `null` | `null` | 1 | 正式全量初始化 |

补充核查：

- `rebuild3_meta.batch` 共 142 行；`rebuild3_meta.batch_snapshot` 共 1562 行；`rebuild3_meta.v_flow_snapshot_timepoints` 已能列出 `scenario_key / batch_seq / timepoint_role / snapshot_at / baseline_version`。
- 场景切换功能“存在且可用”：2026-04-05 live page 已通过 Playwright 在 `/flow/snapshot` 把 `RUN-SCN-INIT2D_STEP2H-20260405101143177` 切到 `RUN-SCN-INIT1D_STEP2H-20260405100310813`，页面 header 与时间点选项同步切换。

### Phase 1：原始文档与设计文档对齐基线

- 完成状态：完成
- 产物是否齐全：齐全
- 检查点结果：对象主语、生命周期/健康状态分离、三层资格独立、初始化与增量同语义、快照页“初始化后 + A + B”要求均已明确；发现 1 个文档冲突。
- 阶段结论：通过，但需带着冲突登记进入实现审计

#### 1.1 冻结文档核心规则清单

1. 主语固定为 `Cell / BS / LAC`；其中 Cell 是最小治理主语，BS 是空间锚点主语，LAC 是区域边界与区域健康主语。
2. `lifecycle_state` 与 `health_state` 必须严格分离，任何页面都不能用单一大状态把两者混写。
3. `existence_eligible`、`anchorable`、`baseline_eligible` 是三层资格，不等于主状态。
4. `watch` 只能是 UI 派生提示，不是底层状态字段。
5. 初始化和 2 小时增量必须遵守同一套治理语义，只是入口和窗口不同。
6. 事实去向只能进入四分流：`fact_governed`、`fact_pending_observation`、`fact_pending_issue`、`fact_rejected`。
7. 当前批次只能读取上一版冻结 baseline；本批新生成 baseline 只能供下一批使用。
8. 技术边界固定为 SQL-first / Postgres-first / Vue3 + TS + Vite / FastAPI。

#### 1.2 UI_v2 页面语义清单 / 页面主语基线表

| 路由 | 页面要回答的问题 | 页面主对象 | 主状态 / 资格 / 解释层分层 | 是否需要 scenario 选择 | 是否需要时间点选择 |
|---|---|---|---|---|---|
| `/flow/overview` | 当前批次发生了什么、四分流去哪了、哪里变化最大 | 当前批次 / 当前 run | 主：四分流 + delta；辅：问题入口 | 否（但至少要支持批次切换） | 否 |
| `/flow/snapshot` | 初始化后和两个后续时间点的流水线快照差异 | 同一场景内的 3 个时间点 | 主：时间点快照；辅：批次上下文 | 是 | 是 |
| `/runs` | 哪个批次异常、趋势如何、是否重跑 | run / batch | 主：批次状态、四分流、趋势、重跑 | 可选 | 否 |
| `/objects` | 当前有哪些对象、健康/等待/异常分布如何 | Cell / BS / LAC | 主：生命周期、健康；辅：资格 | 否 | 否 |
| `/observation` | 候选对象卡在哪一层资格、接下来怎么推进 | waiting / observing 对象 | 主：三层资格进度；辅：建议动作 | 否 | 否 |
| `/anomalies` | 异常对象和记录级异常分别影响了什么 | 异常对象 / 异常记录 | 主：health_state / 路由影响；辅：解释 | 否 | 否 |
| `/baseline` | 当前 baseline 为什么刷新/没刷新、和上一版差在哪里 | baseline 版本 | 主：当前版本、触发原因、diff vs previous、稳定性风险 | 否 | 否 |
| `/compare` | 修复前后 / run A vs run B 的差异是否可解释 | 对比 run / diff 对象 | 主：差异收敛；辅：解释比例 | 否 | 否 |
| `/profiles/lac` | LAC 区域健康、区域质量、锚点资格如何 | LAC | 主：生命周期 + 健康；资格：`anchorable`；解释：`region_quality_label` | 否 | 否 |
| `/profiles/bs` | BS 空间精度、健康、锚点/基线资格如何 | BS | 主：生命周期 + 健康；资格：`anchorable` + `baseline_eligible`；参考：`classification_v2` / 旧可信度 | 否 | 否 |
| `/profiles/cell` | Cell 空间精度、健康、事实分流和资格如何 | Cell | 主：生命周期 + 健康；资格：`anchorable` + `baseline_eligible`；参考：所属 BS 的旧分类/旧可信度 | 否 | 否 |
| `/initialization` | 冷启动做了什么、起始状态是什么 | 初始化 run | 主：初始化步骤 + 初始对象规模 + 四分流 | 否（可默认 latest） | 否 |
| `/governance` | 系统里有哪些表/字段、被谁用、迁移状态如何 | 元数据资产目录 | 主：元数据登记与使用情况 | 否 | 否 |

#### 1.3 文档冲突登记表

| 冲突点 | 冲突来源 | 默认裁决 |
|---|---|---|
| 画像页文档把“资格”列标成 `主状态` | `rebuild3/docs/UI_v2/pages/09_lac_profile_doc.md`、`rebuild3/docs/UI_v2/pages/10_bs_profile_doc.md`、`rebuild3/docs/UI_v2/pages/11_cell_profile_doc.md` 与 Tier 0、`rebuild3/docs/UI_v2/design_notes.md` 冲突 | 页面展示可保留资格列，但业务口径仍按 Tier 0：资格不是主状态；实现不得把资格抬升为生命周期/健康替代品 |

### Phase 2：数据流程与快照机制基线

- 完成状态：完成
- 产物是否齐全：齐全
- 检查点结果：`run/batch/batch_snapshot` 元数据结构存在，scenario/timepoint 选择在数据层上可区分；但 `batch_snapshot` 并不满足“真实每批次治理快照”的语义要求。
- 阶段结论：不通过

#### 2.1 `run / batch / batch_snapshot` 数据语义表

| 实体 | 设计语义 | live 实现 | 结论 |
|---|---|---|---|
| `rebuild3_meta.run` | 一次完整运行；可为初始化或 scenario replay | live 有 4 条 run，包含 2 套初始化场景、1 套 smoke、1 套 full init | 结构存在 |
| `rebuild3_meta.batch` | run 内的 init / rolling_2h 批次，带 `scenario_key / timepoint_role / batch_seq / snapshot_at` | live 场景批次字段完整，可区分 init 与 rolling | 结构存在 |
| `rebuild3_meta.batch_snapshot` | 每批次完成后的真实治理快照，支持页面按时间点回放 | live scenario replay 仅写入 11 个合成指标，并非真实治理流水线快照 | 语义失败 |
| `rebuild3_meta.v_flow_snapshot_timepoints` | 供场景和时间点选择的只读视图 | live 可正确列出 run 内 timepoint 序列 | 结构存在 |

#### 2.2 初始化与 2 小时增量流程对照

| 项目 | 初始化批次 | rolling_2h 批次 | 设计要求 |
|---|---|---|---|
| `timepoint_role` | `init` | `rolling_2h` | 必须明确区分 |
| `batch_seq` | 0 | 1..N | 必须形成时间线 |
| `input_rows` | 初始化窗口累计输入 | 当前 2 小时窗口输入 | 粒度必须稳定 |
| baseline 读取 | 读上一版冻结 baseline | 读上一版冻结 baseline | 语义必须一致 |
| baseline 产出 | 只为下一批提供新冻结版 | 只为下一批提供新冻结版 | 不可同批自消费 |
| `batch_snapshot` | 应记录 init 完成后的真实状态 | 应记录每个 rolling 批次结束后的真实状态 | 当前未达成 |

#### 2.3 baseline 冻结语义核查表

| 要求 | live 结果 | 结论 |
|---|---|---|
| 当前批次只读取上一版冻结 baseline | 文档如此规定，但 scenario replay SQL 直接按当前全量表比例估算 baseline 数量，未体现“上一版冻结”读法 | 失败 |
| 新版 baseline 仅供下一批使用 | scenario replay 在 init 批次直接写 `baseline_version` 元数据，但没有真实对象级冻结链路 | 失败 |
| baseline 页展示当前版本与上一版差异 | 当前 `/baseline` 读的是 rebuild2 对照和 sample/full 历史 | 失败 |

#### 2.4 scenario / timepoint 模型核查表

| 核查项 | 结果 | 证据 |
|---|---|---|
| 是否有场景选择入口 | 是 | `/flow/snapshot` live 页面可切换 `INIT2D_STEP2H` 与 `INIT1D_STEP2H` |
| 是否区分场景选择与场景内时间点选择 | 是 | `playwright-flow-snapshot-scenario-switch.md` 已显示“运行场景”下拉与 A/B 时间点下拉分离 |
| 时间点是否来自同一 `run` | 是 | `rebuild3_meta.v_flow_snapshot_timepoints` 和 `run_snapshot.py` 同 run 查询 |
| `batch_snapshot` 是否为真实每批次治理快照 | 否 scenario replay SQL 只写合成指标 |
| 是否仍混入伪时间语义 | 是 | run catalog 仍包含 full init；主流程页/批次页仍以 full/sample 替代真实 timepoint |
| 数据不足时是否诚实提示 | 部分是 | `/flow/snapshot` 会提示“仅 1 个时间点”；但不会提示“当前快照是合成 replay 口径” |

#### 2.5 原始数据 -> 标准化 -> 四分流 -> 对象状态 -> baseline 链路说明

- 正式全量链路的对象/事实表是真实存在的：`rebuild3.obj_*`、`rebuild3.fact_*`、`rebuild3.baseline_*` 均有大量 live 数据。
- 但 scenario replay 并没有重新跑这条治理链，而是通过 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:305` 先读当前全量 baseline 比例，再在 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:347` 和 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:419` 写累计/估算值。
- 因此 `/flow/snapshot` 当前展示的是“可切换的时间点 UI”，不是“可相信的每批治理快照底座”。

### Phase 3：页面语义合约基线

- 完成状态：完成
- 产物是否齐全：齐全（详见第五部分页面逐页对齐结论）
- 检查点结果：13 个必审页面均完成主问题 / 主对象 / 字段分层 / 交互需求 / API / scenario-timepoint 依赖核查；发现 5 页存在主语错误，4 页存在明显 fallback 或字段漂移。
- 阶段结论：不通过

### Phase 4：API / 字段 / 边界基线

- 完成状态：完成
- 产物是否齐全：齐全；详表见 `docs1/rebuild3_field_baseline.md`
- 检查点结果：关键字段边界已重新冻结；确认 `gps_confidence` / `signal_confidence` 在 live rebuild3 业务表中不存在，`gps_quality` 被错误拿来代替旧可信度语义。
- 阶段结论：通过基线建立，但实现不通过

### Phase 5：真实运行验证基线

- 完成状态：完成
- 产物是否齐全：齐全
- 检查点结果：已用 live API、live DB、live 页面和 Playwright 完成核查；场景选择确实存在，但核心流程页仍存在数据口径和主语错误。
- 阶段结论：验证完成，系统行为不通过

#### 5.1 live 验证摘要

| 验证项 | 结果 | 证据 |
|---|---|---|
| 后端健康接口 | 通过 | `GET http://127.0.0.1:47121/api/v1/health` 返回正常 |
| 前端可访问 | 通过 | `http://127.0.0.1:47122/` 可访问 |
| `/flow/snapshot` 场景选择 | 通过 | 已从 2 天初始化切到 1 天初始化，header 与 A/B 时间点同步更新 |
| `/flow/snapshot` 时间点选择语义 | 部分通过 | 先选场景，再选场景内 A/B；但快照数据口径错误 |
| `/runs` live 渲染 | 不通过 | 页面只显示 full + sample 两行 |
| `/flow/overview` live 渲染 | 不通过 | 页面上下文为 `RUN-FULL-20251201-20251207-V1` |
| `/profiles/bs` live 渲染 | 部分通过 | 主状态/资格正常，但参考列是 `gps_quality` / `—` |
| `/profiles/lac` live 渲染 | 部分通过 | 区域质量标签直接显示 `issue_present` |
| `/compare` / `/governance` live 渲染 | 不通过 | 页面未提示 fallback，视觉上像正式数据 |

#### 5.2 Playwright 产物清单

- `/flow/snapshot`：`docs1/reaudit-flow-snapshot.png`、`playwright-flow-snapshot-deep3.md`
- `/flow/snapshot` 场景切换：`docs1/reaudit-flow-snapshot-scenario-switch.png`、`playwright-flow-snapshot-scenario-switch.md`
- `/runs`：`docs1/reaudit-runs.png`、`playwright-runs.md`
- `/flow/overview`：`docs1/reaudit-flow-overview.png`、`playwright-flow-overview.md`
- `/profiles/bs`：`docs1/reaudit-bs-profile.png`、`playwright-bs-profile.md`
- `/profiles/lac`：`docs1/reaudit-lac-profile.png`、`playwright-lac-profile.md`
- `/compare`：`docs1/reaudit-compare.png`、`playwright-compare.md`
- `/governance`：`docs1/reaudit-governance.png`、`playwright-governance.md`

### Phase 6：偏差登记、优先级与实施基线

- 完成状态：完成
- 产物是否齐全：齐全
- 检查点结果：问题、文档冲突、字段冲突、页面主语偏差、数据链路缺口和后续队列均已建立。
- 阶段结论：通过；本轮复评已经形成下一轮实施所需的稳定审计基线。

## 第三部分：严重问题清单

### P0-01：scenario replay 不是“真实每批次治理快照”，`batch_snapshot` 语义失真

- 页面 / 接口 / 表 / 文档位置：`/flow/snapshot`、`/api/v1/runs/flow-snapshots`、`rebuild3_meta.batch_snapshot`、`rebuild3/docs/UI_v2/design_notes.md`、`rebuild3/docs/UI_v2/pages/01_flow_overview_timeline.html`
- 证据链：
  - 文档：UI_v2 明确要求快照页以 `batch_snapshot` 作为“每批次完成后的历史快照底座”，用于“初始化完成后 + 时间点 A + 时间点 B”真实回放。
  - SQL：`rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:305` 直接用当前全量 `baseline_* / obj_*` 比例估算 scenario baseline；`rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:376` 用比例乘累计对象数得到 baseline 数；`rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:419` 只写 11 个快照指标；`rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql:447` 写入 `gps_outlier`、`gps_missing`、`active` 这类合成异常摘要。
  - 数据：最新 `INIT2D_STEP2H` 场景末批快照里 `obj_cell = 1,257,982`、`obj_bs = 609,364`，而正式对象表 live 只有 `rebuild3.obj_cell = 573,561`、`rebuild3.obj_bs = 193,036`；`baseline_cell` 也从 scenario 快照的 `427,585` 漂移到 live baseline 表的 `194,952`。
  - API：`rebuild3/backend/app/api/run_snapshot.py:362` 直接把这些 batch snapshot 行当成页面底座。
  - 页面：`playwright-flow-snapshot-deep3.md` 与 `docs1/reaudit-flow-snapshot-scenario-switch.png` 均证明页面展示的就是这套 replay 结果。
- 影响：
  - `/flow/snapshot` 的核心主语已经偏离“真实每批治理快照”。
  - scenario/timepoint 功能表面存在，但其底座不支撑冻结文档要求的统一治理语义。
  - 后续任何基于 scenario 快照的修复验证都会继续建立在伪数据上。
- 修复建议：
  1. 让 scenario replay 真正复用 rebuild3 正式治理链路，逐批落真实 `batch_snapshot`、`batch_flow_summary`、`batch_anomaly_summary`、baseline refresh 信息。
  2. 禁止再用“当前全量对象比例”估算 baseline 覆盖。
  3. 如果短期做不到，必须把当前 scenario replay 从主流程快照里下线或明确标为 mock / synthetic，不能继续装作真实快照。
- 是否阻塞下一轮实施：是

### P0-02：`/flow/snapshot` 百分比计算混用“累计值 vs 单批输入”，页面出现 2437% ~ 10896%

- 页面 / 接口 / 表 / 文档位置：`/flow/snapshot`、`/api/v1/runs/flow-snapshots`、`rebuild3_meta.batch_snapshot`、`rebuild3/docs/UI_v2/index.html`
- 证据链：
  - 文档：快照页是 3 列对照视图，数值必须能被人解释。
  - 代码：`rebuild3/backend/app/api/run_snapshot.py:23` 把 `batch_input_rows` 设为输入基数；`rebuild3/backend/app/api/run_snapshot.py:24` 把 `fact_standardized` 的百分比基数指向 `batch_input_rows`；`rebuild3/backend/app/api/run_snapshot.py:263` 却从 `context.input_rows` 注入单批窗口输入；`rebuild3/backend/app/api/run_snapshot.py:278` 用累计 `fact_standardized / 单批 input_rows` 计算百分比。
  - API：live `/api/v1/runs/flow-snapshots` 返回 `fact_standardized` 在 `INIT2D_STEP2H` 下为 `13,743,183 / 273,489 = 5025.1%`，在 `INIT1D_STEP2H` 场景切换后为 `6,958,341 / 285,485 = 2437.4%`，时间点 B 甚至达到 `10896.5%`。
  - 页面：`playwright-flow-snapshot-deep3.md` 和 `playwright-flow-snapshot-scenario-switch.md` 均已抓到这些百分比。
- 影响：
  - 即便暂时不讨论 scenario replay 是否真实，当前页面的核心对比数字本身也是错的。
  - 用户会把“标准化事件 10896.5%”误读为系统异常或通过率，快照页失去解释价值。
- 修复建议：
  1. 统一快照粒度：要么全部展示累计值并以累计输入为基数，要么全部展示单批值并同步改写 snapshot 指标来源。
  2. 在 API 层增加“粒度标识”，避免页面无意识混用累计值和窗口值。
  3. 对大于 100% 的百分比先做异常断言和告警，防止静默上线。
- 是否阻塞下一轮实施：是

### P1-01：`/runs` 仍停留在 sample/full 伪批次中心，未接入真实 `run / batch`

- 页面 / 接口 / 表 / 文档位置：`/runs`、`/api/v1/runs/batches`、`rebuild3_meta.batch`、`rebuild3/docs/UI_v2/pages/02_run_batch_center_doc.md`
- 证据链：
  - 文档：运行/批次中心要回答“哪个批次异常？四分流比例怎么变了？趋势是好转还是恶化？”。
  - 代码：`rebuild3/backend/app/api/run.py:156` 只循环 `FULL_BATCH_ID` 和 `SAMPLE_BATCH_ID`；`rebuild3/backend/app/api/run.py:180` 明确把趋势文案写成“当前仅有 sample + full 两个结构化批次”。
  - 数据：live `rebuild3_meta.batch` 实际有 142 行，场景 run 内已形成多批时间线。
  - API：live `/api/v1/runs/batches` 只返回 2 行：`BATCH-FULL-20251201-20251207-V1` 和 `BATCH-SAMPLE-20251201-20251207-V1`。
  - 页面：`docs1/reaudit-runs.png`、`playwright-runs.md` 均显示只有两条批次记录。
- 影响：运行中心没有回答设计定义的问题，只是在展示一组 sample/full 对照卡片。
- 修复建议：
  1. 以 `rebuild3_meta.batch` 为唯一批次底座，接入 scenario / batch / rerun / trend。
  2. 将 sample validation 移出批次中心，改归 `/compare` 辅助模块。
- 是否阻塞下一轮实施：是

### P1-02：`/flow/overview` 主语错误，当前展示的是 full init + sample delta，而不是“当前批次”

- 页面 / 接口 / 表 / 文档位置：`/flow/overview`、`/api/v1/runs/flow-overview`、`rebuild3_meta.batch_flow_summary`、`rebuild3/docs/UI_v2/pages/01_flow_overview_doc.md`
- 证据链：
  - 文档：流转总览必须回答“当前批次的数据流到了哪里”，并支持批次切换。
  - 代码：`rebuild3/backend/app/api/run.py:38` 到 `rebuild3/backend/app/api/run.py:45` 全部固定读取 `FULL_BATCH_ID`；`rebuild3/backend/app/api/run.py:130` 明确写了“delta 采用 sample validation 作为参考基线”。
  - API：live `/api/v1/runs/flow-overview` 返回 `context.run_id = RUN-FULL-20251201-20251207-V1`、`context.batch_id = BATCH-FULL-20251201-20251207-V1`。
  - 页面：`docs1/reaudit-flow-overview.png`、`playwright-flow-overview.md` 都显示 full init 版本上下文。
- 影响：主页看起来像在汇报“当前态势”，实际上展示的是一条静态 full init 对照结果。
- 修复建议：
  1. Flow overview 以“当前选中批次 / 最新正式批次”为主语。
  2. delta 必须是同一语义下的上一批或上一时间点，不得再用 sample validation 代替。
- 是否阻塞下一轮实施：是

### P1-03：`/baseline` 没有做“当前版 vs 上一版”的版本差异，而是在做 rebuild2 对照

- 页面 / 接口 / 表 / 文档位置：`/baseline`、`/api/v1/runs/baseline-profile`、`rebuild3_meta.baseline_version`、`rebuild3.baseline_*`、`rebuild3/docs/UI_v2/pages/07_baseline_profile_doc.md`
- 证据链：
  - 文档：baseline 页要回答“当前 baseline 版本和触发原因”“与上一版差异来自哪里”。
  - 代码：`rebuild3/backend/app/api/run_workspaces.py:337` 把 version history 拼成 sample + full；`rebuild3/backend/app/api/run_workspaces.py:364` 到 `rebuild3/backend/app/api/run_workspaces.py:367` 比的是 r2 baseline eligible 数量；`rebuild3/backend/app/api/run_workspaces.py:379` 到 `rebuild3/backend/app/api/run_workspaces.py:390` 取的是“rebuild3 baseline 里但 r2 baseline_eligible = false”的对象；`rebuild3/backend/app/api/run_workspaces.py:441` 把 membership 直接硬编码成 `compare_membership(True, False)`。
  - API：live `/api/v1/runs/baseline-profile` 的 `diff_samples` membership 只有 `仅 rebuild3`，不存在“上一版新增 / 移除 / 变更”。
- 影响：baseline 页正在回答“rebuild2 vs rebuild3 差异”，不是“上一版 baseline vs 当前版差异”。
- 修复建议：
  1. 以 `rebuild3_meta.baseline_version` 的相邻两个版本为 diff 对象。
  2. 生成 `added / removed / changed` 三类版本差异。
  3. 如果没有上一版，应明确显示“只有首版 baseline，无上一版可比较”。
- 是否阻塞下一轮实施：是

### P1-04：`/initialization` 使用 sample validation 结果冒充冷启动页主语

- 页面 / 接口 / 表 / 文档位置：`/initialization`、`/api/v1/runs/initialization`、`rebuild3_sample_meta.*`、`rebuild3/docs/UI_v2/pages/12_initialization_doc.md`
- 证据链：
  - 文档：初始化页要展示冷启动 run 的 11 步流程、初始化结果汇总和起始状态。
  - 代码：`rebuild3/backend/app/api/run.py:243` 到 `rebuild3/backend/app/api/run.py:276` 全部读取 `rebuild3_sample_meta` / `SAMPLE_BATCH_ID`；`rebuild3/backend/app/api/run.py:278` 明写“初始化页当前接的是 sample validation 结果”。
  - API：live `/api/v1/runs/initialization` 返回 `context.run_id = RUN-SAMPLE-20251201-20251207-V1`。
- 影响：页面确实能展示“初始化长什么样”，但主语不是初始化 run，而是样本验证。
- 修复建议：
  1. 默认读取最新一次真实初始化 run。
  2. 多场景存在时，允许切换初始化 run，但不能再把 sample validation 当主体。
- 是否阻塞下一轮实施：是

### P1-05：`/compare` 与 `/governance` 仍是 fallback 数据，而且页面没有显式暴露 fallback 状态

- 页面 / 接口 / 表 / 文档位置：`/compare`、`/governance`、`/api/v1/compare/*`、`/api/v1/governance/*`、`rebuild3/docs/UI_v2/pages/08_validation_compare_doc.md`、`rebuild3/docs/UI_v2/pages/13_data_governance_doc.md`
- 证据链：
  - 代码：`rebuild3/backend/app/api/compare.py:100`、`rebuild3/backend/app/api/compare.py:110` 返回 `data_origin = report_fallback`；`rebuild3/backend/app/api/governance.py:82`、`rebuild3/backend/app/api/governance.py:92`、`rebuild3/backend/app/api/governance.py:102`、`rebuild3/backend/app/api/governance.py:128`、`rebuild3/backend/app/api/governance.py:139` 全部返回 `data_origin = fallback_catalog`。
  - 前端：`rebuild3/frontend/src/pages/ValidationComparePage.vue:165` 仅取 `o.scopes` / `d`；`rebuild3/frontend/src/pages/GovernancePage.vue:185` 到 `rebuild3/frontend/src/pages/GovernancePage.vue:186` 仅取 `overview / rows / groups`，不展示 `data_origin`。
  - 页面：`docs1/reaudit-compare.png` 和 `docs1/reaudit-governance.png` 看起来像正式数据，没有 fallback 告警。
- 影响：页面视觉上像“已经接好真实系统”，实际还是报告常量和目录常量，极易误导下一轮开发。
- 修复建议：
  1. 要么接 live compare 结果 / live 元数据注册表；
  2. 要么在页面头部加阻断级 banner：`当前为 fallback 数据，不可作为真实治理判断`。
- 是否阻塞下一轮实施：是

### P2-01：BS/Cell 参考字段口径漂移，`gps_confidence` 被 `gps_quality` 替代，`signal_confidence` 缺失

- 页面 / 接口 / 表 / 文档位置：`/profiles/bs`、`/profiles/cell`、`/api/v1/objects/profile-list`、`rebuild3/docs/UI_v2/pages/10_bs_profile_doc.md`、`rebuild3/docs/UI_v2/pages/11_cell_profile_doc.md`
- 证据链：
  - 文档：UI_v2 仍把 `classification_v2 / gps_confidence / signal_confidence` 定义为灰色参考列。
  - 代码：`rebuild3/backend/app/api/object_common.py:157` 和 `rebuild3/backend/app/api/object_common.py:159` 实际取的是 `gps_quality`；`rebuild3/backend/app/api/object_common.py:217` 到 `rebuild3/backend/app/api/object_common.py:218` 只序列化 `classification_v2` 和 `gps_quality`；`rebuild3/frontend/src/pages/BsProfilePage.vue:74`、`rebuild3/frontend/src/pages/BsProfilePage.vue:75` 仍展示“GPS可信度(参考)”和“信号可信度(参考)”列；`rebuild3/frontend/src/pages/CellProfilePage.vue:72` 展示的也是 `gps_quality`。
  - live schema：当前 rebuild3 业务表中没有 `gps_confidence` / `signal_confidence`。
  - 页面：`playwright-bs-profile.md` 显示行值为 `Usable` / `Risk` / `—`，不是旧可信度体系。
- 影响：页面参考列标题和实际字段来源不一致，后续很容易继续把“画像质量标签”误读成“旧可信度参考”。
- 修复建议：
  1. 若继续保留旧可信度语义，显式引入 `gps_confidence_ref` / `signal_confidence_ref` 映射来源；
  2. 若决定不保留，应改 UI 文案为 `GPS质量(参考)` 并删除空白的 `signal_confidence` 列。
- 是否阻塞下一轮实施：否，但必须登记

### P2-02：LAC `region_quality_label` 直接展示技术值，未对齐“覆盖不足等”人类标签

- 页面 / 接口 / 表 / 文档位置：`/profiles/lac`、`/api/v1/objects/profile-list?object_type=lac`、`rebuild3.obj_lac`、`rebuild3/docs/UI_v2/pages/09_lac_profile_doc.md`
- 证据链：
  - 文档：LAC 页要求把 `region_quality_label` 作为独立灰色标签，表达“覆盖不足”等人类语义。
  - 代码：`rebuild3/backend/app/api/object_common.py:229` 直接返回原值；`rebuild3/frontend/src/pages/LacProfilePage.vue:60` 直接渲染 `row.region_quality_label`。
  - 数据：live `rebuild3.obj_lac.region_quality_label` 只有 `coverage_insufficient`、`issue_present`、`null`。
  - 页面：`docs1/reaudit-lac-profile.png` 清楚展示了 `issue_present`。
- 影响：页面虽然保住了“质量标签独立于 health_state”的边界，但表达层未完成，用户看到的是技术代码。
- 修复建议：在 API 或前端增加稳定映射表，例如 `coverage_insufficient -> 覆盖不足`、`issue_present -> 存在区域问题`。
- 是否阻塞下一轮实施：否，但必须登记

### P3-01：观察工作台的趋势仍是 sample/full 派生，不是真实多批推进趋势

- 页面 / 接口 / 表 / 文档位置：`/observation`、`/api/v1/runs/observation-workspace`、`rebuild3/docs/UI_v2/pages/05_observation_workspace_doc.md`
- 证据链：
  - 代码：`rebuild3/backend/app/api/run_workspaces.py:77` 到 `rebuild3/backend/app/api/run_workspaces.py:78` 仍读取 sample/full decision summary；`rebuild3/backend/app/api/run_workspaces.py:188` 到 `rebuild3/backend/app/api/run_workspaces.py:192` 生成的 backlog trend 只有“样本 / 正式”；`rebuild3/backend/app/api/run_workspaces.py:192` 还写明“不是实时多批增量斜率”。
- 影响：页面主体卡片和推进建议是有价值的，但趋势区仍不是设计期所说的真实批次推进趋势。
- 修复建议：在真实多批元数据打通后，把 observation trend 改成同一 run 内批次序列。
- 是否阻塞下一轮实施：否

### P3-02：`/flow/snapshot` 运行场景下拉仍混入 full init 且存在重复标签，场景表达不够稳

- 页面 / 接口 / 表 / 文档位置：`/flow/snapshot`、`/api/v1/runs/flow-snapshots`、`rebuild3_meta.run`
- 证据链：
  - API：live run options 同时包含 `RUN-FULL-20251201-20251207-V1` 和两个都显示为“1 天初始化 / 每 2 小时快照”的 run（正式 1 天场景 + smoke 场景）。
  - 页面：`playwright-flow-snapshot-deep3.md` 显示 3 个用户可选 label，其中有两个同名“1 天初始化 / 每 2 小时快照”。
- 影响：虽然不改变底层数据对错，但会让用户难以区分 smoke 和正式 1 天场景，也会让 full init 出现在时间快照视图里。
- 修复建议：
  1. snapshot run catalog 默认只收录 `scenario_replay`；
  2. label 强制带 `scenario_key` 或 `run_type`，避免同名。
- 是否阻塞下一轮实施：否

### 3.11 文档冲突清单

| 类型 | 内容 | 默认裁决 |
|---|---|---|
| 设计文档冲突 | LAC/BS/Cell 画像文档把资格列标成 `主状态` | 底层业务口径仍按 Tier 0：资格不是主状态；UI 只可作为资格标签展示 |

### 3.12 字段口径冲突清单

| 字段 | 文档口径 | 当前实现 | 结论 |
|---|---|---|---|
| `gps_confidence` | rebuild2 参考可信度 | 被 `gps_quality` 替代 | 漂移 |
| `signal_confidence` | rebuild2 参考可信度 | 列保留但无数据来源 | 缺口 |
| `region_quality_label` | “覆盖不足等”人类标签 | 直接返回技术码 | 表达不完整 |
| `compare_membership` | 参考性对比成员关系 | baseline 页误当版本差异使用 | 语义错位 |

### 3.13 页面主语偏差清单

| 页面 | 设计主语 | 当前主语 | 结论 |
|---|---|---|---|
| `/flow/overview` | 当前批次 | full init + sample delta | 偏差 |
| `/flow/snapshot` | 同一场景内的真实三时间点 | 场景 UI 正确，但底座是 synthetic replay | 偏差 |
| `/runs` | 真实 run / batch center | sample/full 对照中心 | 偏差 |
| `/baseline` | 当前 baseline vs 上一版 | rebuild2 对照 | 偏差 |
| `/initialization` | 冷启动 run | sample validation | 偏差 |
| `/compare` | run A vs run B 实差 | fallback report | 偏差 |
| `/governance` | 元数据注册表 | fallback catalog | 偏差 |

### 3.14 数据链路缺口清单

| 链路缺口 | 影响 |
|---|---|
| scenario replay 未复用真实治理流程 | 快照页时间点数据不可作为治理真相 |
| batch center 未接真实 `rebuild3_meta.batch` 全量时间线 | 运行中心无法回答批次趋势问题 |
| baseline page 缺“上一版版本差异”读模型 | 无法解释 baseline 版本演进 |
| compare page 缺 live compare 结果表/视图 | 验证页只能展示常量 |
| governance page 缺 live 资产注册表 | 治理页只能展示 fallback 目录 |

### 3.15 性能 / 代码规模问题清单

- 未发现需要上升为阻断级的性能问题。
- 代码规模不是本轮主线问题；真正的阻断点是主语、口径和数据链路。

## 第四部分：字段与边界确认表

详细版本见 `docs1/rebuild3_field_baseline.md`。这里保留摘要表，方便和严重问题对读。

| 字段 | 层级 | live 来源 | 当前实现结论 |
|---|---|---|---|
| `lifecycle_state` | 主状态 | `rebuild3.obj_*` | 一致 |
| `health_state` | 主状态 | `rebuild3.obj_*` | 一致 |
| `existence_eligible` | 资格 | `rebuild3.obj_*` | 基本一致 |
| `anchorable` | 资格 | `rebuild3.obj_*` | 基本一致 |
| `baseline_eligible` | 资格 | `rebuild3.obj_*` | 字段一致，页面使用有偏差 |
| `region_quality_label` | 解释层 | `rebuild3.obj_lac` | 原始码直出，不一致 |
| `classification_v2` | 参考层 | `rebuild3_meta.r2_full_profile_bs` / `rebuild3.stg_bs_classification_ref` | 部分一致 |
| `gps_confidence` | 参考层 | live schema 不存在 | 不一致 |
| `signal_confidence` | 参考层 | live schema 不存在 | 不一致 |
| `compare_membership` | 派生参考字段 | 对象 API 派生 + baseline 页硬编码 | 部分一致 |
| 四分流字段 | 事实主字段 | `rebuild3.fact_*` + `rebuild3_meta.batch_*` | 正式链路基本存在，但 scenario replay 为 synthetic |

## 第五部分：页面逐页对齐结论

| 路由 | 是否回答设计定义的问题 | 语义漂移 | 数据链路状态 | fallback / 缓存问题 | 是否需要继续拆分组件 / API / SQL |
|---|---|---|---|---|---|
| `/flow/overview` | 否 把 full init 当当前批次 | 读模型未接真实当前批次 | sample validation 伪 delta | 需要重做 API 选批与 delta 逻辑 |
| `/flow/snapshot` | 否 UI 交互基本对，数据底座和百分比错 | `batch_snapshot` synthetic | 未显式提示 synthetic | 需要重做 scenario runner 和快照口径 |
| `/runs` | 否 批次中心退化成 sample/full 对照页 | 未接 `rebuild3_meta.batch` 全量时间线 | sample/full 固化趋势 | 需要重做 API 与趋势图数据源 |
| `/objects` | 基本是 | 主状态与资格分层基本正确 | 对象主表真实 | compare 仍依赖 r2 参考层 | 暂不需大拆，只需清理参考字段文案 |
| `/observation` | 基本是 | 主体卡片对；趋势口径偏弱 | 主体来自 `obj_cell`，趋势非多批 | note 已显式说明派生趋势 | 后续补真实多批 trend 即可 |
| `/anomalies` | 基本是 | 双视图存在；批次统计仍固定 full batch | 对象表真实，统计层未批次化 | 无显式 fallback，但统计受 full batch 限制 | 后续补选批能力 |
| `/baseline` | 否 把 rebuild2 对照当版本差异 | 缺 baseline version diff 读模型 | history 也混 sample/full | 需要新增 baseline diff API / SQL |
| `/compare` | 否 页面视觉像真实对照，实际是 fallback report | 无 live compare 读模型 | `report_fallback` 未向用户暴露 | 需要真实 compare 表或强提醒 |
| `/profiles/lac` | 部分是 | 主状态/资格分层对，但解释标签未人类化 | 对象主表真实 | 无 fallback，表达层未完成 | 只需小修映射 |
| `/profiles/bs` | 部分是 | 主状态/资格分层对，参考列口径漂移 | 对象+画像主链真实 | 旧可信度被 `gps_quality` 替代 | 需要清理字段命名与来源 |
| `/profiles/cell` | 部分是 | 与 BS 类似，旧参考列漂移 | 对象+画像主链真实 | 旧可信度被 `gps_quality` 替代 | 需要清理字段命名与来源 |
| `/initialization` | 否 sample validation 冒充 init run | 读模型接错 schema | 明文说明是 sample validation | 需要切回真实 init run |
| `/governance` | 否 页面看起来像 live catalog，实际是 fallback 目录 | 无 live 元数据注册表 | `fallback_catalog` 未向用户暴露 | 需要真实注册表或强提醒 |

补充说明：

- `/objects/:objectType/:objectId` 不在本轮强制页面清单里，但抽查结果显示对象详情页对 route distribution 和状态展示基本可用；后续主要受 `compare_membership` 语义边界影响。

## 第六部分：基线产物清单

- 文档清单与分级表：见第二部分 Phase 0 / 0.1。
- 路由清单：见第二部分 Phase 0 / 0.2。
- 页面 -> 设计稿映射表：见第二部分 Phase 0 / 0.3。
- 页面 -> API 映射表：见第二部分 Phase 0 / 0.4。
- API -> 表/视图映射表：见第二部分 Phase 0 / 0.5。
- scenario / run / batch / snapshot 基线：见第二部分 Phase 0 / 0.6、Phase 2 / 2.4。
- 冻结文档核心规则清单：见第二部分 Phase 1 / 1.1。
- 页面主语基线表：见第二部分 Phase 1 / 1.2。
- 文档冲突登记表：见第二部分 Phase 1 / 1.3。
- `run / batch / batch_snapshot` 语义表：见第二部分 Phase 2 / 2.1。
- baseline 冻结语义核查表：见第二部分 Phase 2 / 2.3。
- 字段与边界确认表：见 `docs1/rebuild3_field_baseline.md` 和第四部分摘要表。
- 页面逐页对齐结论：见第五部分。
- Playwright 验证与截图清单：见第二部分 Phase 5 / 5.2。
- 速度与代码规模基线：本轮未发现阻断级性能问题，见第三部分 / 3.15。

## 第七部分：剩余工作队列

### 必须立刻修

1. 用真实治理链路重做 scenario replay，保证 `batch_snapshot` 真正代表每批次结果。
2. 修正 `/flow/snapshot` 的累计值 / 单批值粒度混用，彻底消除 2437% ~ 10896% 这类错误百分比。
3. 把 `/flow/overview` 改为真实当前批次 / 可选批次读模型，不再引用 sample validation delta。
4. 把 `/runs` 改为真实 `run / batch` 中心，接入 scenario、timepoint、rerun、趋势。
5. 把 `/baseline` 改成“当前版 vs 上一版”的 baseline version diff。
6. 把 `/initialization` 切回真实初始化 run。
7. 在 `/compare` 和 `/governance` 中二选一：接真实数据，或在 UI 中显式暴露 fallback 并降级定位。

### 本轮可延后但需登记

1. 统一 BS/Cell 画像参考列口径，决定是恢复 `gps_confidence / signal_confidence`，还是正式改文案为 `gps_quality`。
2. 为 LAC `region_quality_label` 建立稳定的人类标签映射。
3. 为 `/observation`、`/anomalies` 补真实批次趋势 / 选批能力。
4. 让 `/flow/snapshot` 的场景标签区分 smoke / 正式 / full init，避免重复名字。

### 可以后续优化

1. 进一步清理 `api_models.md` 与当前实现之间的过时字段说明。
2. 为 governance 元数据注册表增加自动扫描和人工登记结合机制。
3. 为 compare 增加 run A / run B 参数化，而不是固定 sample/full 两挡。

### 禁止再次默认假设清单

- 禁止再把 sample/full/baseline 近似成“时间快照”。
- 禁止把 fallback 数据静默包装成正式治理数据。
- 禁止把资格字段抬升成生命周期 / 健康状态。
- 禁止把 `gps_quality` 继续冒充 `gps_confidence`。
- 禁止把 `compare_membership` 当成 baseline 版本差异。
- 禁止用当前实现反推设计意图；一旦和 Tier 0 / UI_v2 冲突，先判实现有问题。
- 禁止继续在没有真实多批数据读模型的情况下，用 sample/full 对照代替“趋势”。
