# 流式架构修改方案

生成时间：2026-04-08T14:50:54+0800  
基于决策：Q1=A，Q2=A，Q3=B，Q4=B，Q5=C  
主线参考：Claude 审计报告  
补充参考：Codex / Gemini 审计中的高置信度发现  
核心交付：流式画像模块（从实验到可观察模块）

---

## 人类决策汇总

| 问题 | 人类选择 | 对方案的约束含义 |
|------|---------|----------------|
| Q1 | A | 以后端权威语义看，`etl_dim_*` 与其 streaming snapshot 才是前台主数据源；`obj_*` 不再作为主路径页面的数据权威。 |
| Q2 | A | `profile.py` 必须新增 streaming 模式；流转总览 / 流转快照 / 观察工作台继续保留，但数据源改为 streaming snapshot 与 snapshot diff。 |
| Q3 | B | 参数外化到 YAML 文件即可；先不做数据库配置表和在线编辑 UI。 |
| Q4 | B | 版本追溯走独立轻量日志：`etl_profile_run_log`；不复用旧 `run` / `batch` 作为当前画像主版本体系。 |
| Q5 | C | `compare_*`、`obj_state_history`、`obj_relation_history` 等历史对比能力本轮冻结，待 streaming 模块稳定后再评估是否恢复或由 snapshot diff 替代。 |

---

## 修改方案

### 阶段一：必须做（流式模块 + 页面对接）

> 目标：
> 1. `profile.py` 支持 streaming 模式，产出 snapshot 序列和 diff  
> 2. 流转页面改接 snapshot 数据，可观察流转过程  
> 3. 所有保留页面都有真实数据

#### 任务 1.1：把流式评估逻辑固化成 `profile.py` 的新增运行模式

- **问题**：当前 `rebuild4/backend/app/etl/profile.py` 只有一次性全量计算，无法保留 Day 1→Day N 的累积过程，也就无法产出可观察 snapshot。
- **来源**：人类决策 Q2=A；`rebuild4/docs/02_profile/06_流式评估.md`；Claude 主线“复用已验证画像逻辑，不重写算法”。
- **修改文件**：`rebuild4/backend/app/etl/profile.py`、`rebuild4/backend/app/etl/pipeline.py`、`rebuild4/docs/02_profile/05_pipeline.md`、`rebuild4/docs/02_profile/06_流式评估.md`
- **修改内容**：
  - 保留现有 `run_profile()` 的 full 行为不变；新增 `run_profile_streaming()`，或等价的 `mode="streaming"` 分支。
  - 把 6 步画像 SQL 抽成“可指定输入源表 / 日期窗口 / 输出目标”的共享执行路径，避免复制一套新 SQL。
  - streaming 模式按 `DATE(ts_std)` 做累积窗口，复用实验中“独立观测去重 → 中位数质心 → P50/P90 → 生命周期判定”的同一算法链路。
  - 每个 streaming 窗口都得到一版 Cell snapshot；最后一个窗口的结果回写到现有 `etl_dim_cell` / `etl_dim_bs` / `etl_dim_lac`，保证现有 Profile 页面继续可用。
- **验证方式**：
  - 对同一 7 天样本运行 streaming，确认最后一个 snapshot 与 full 模式结果一致，至少满足 `06_流式评估.md` 中已验证的“Day 7 ≈ 全量批量”结论。
  - 抽查 `active / observing / waiting` 数量、质心偏差、P90 差异，确保没有引入第二套算法。
- **后续可扩展**：窗口粒度先做“按天累积”；后续再扩展到“按批次”或“滑动窗口”，不在本轮一起做。

---

#### 任务 1.2：落盘 streaming snapshot 与 diff，形成 flow / workspace 的新 read model

- **问题**：即使 `profile.py` 能逐窗计算，如果不落盘 snapshot 和 diff，流转页面仍然没有稳定数据源。
- **来源**：人类决策 Q2=A；Claude 主线“流转页面概念保留”；Codex / Gemini 补充“旧 `batch_*` / `observation_workspace_snapshot` 不再是当前画像权威数据源”。
- **修改文件**：`rebuild4/backend/app/etl/profile.py`
- **修改内容**：
  - 在 `profile.py` 内新增 `_ensure_stream_tables()`，最小新增三张表：
    - `rebuild4_meta.etl_profile_snapshot`
    - `rebuild4_meta.etl_profile_snapshot_cell`
    - `rebuild4_meta.etl_profile_snapshot_diff`
  - `etl_profile_snapshot` 保存每个窗口的总体指标：`profile_run_id`、`snapshot_seq`、`snapshot_label`、`window_end_date`、`stream_cell_count`、`active_count`、`observing_count`、`waiting_count`、`anchorable_count`，以及复用实验口径的 `cell_coverage_pct`、`cell_centroid_median_m`、`active_recall_pct` 等收敛指标。
  - `etl_profile_snapshot_cell` 保存每个窗口的 Cell 级状态快照，至少落 `cell_id`、`bs_id`、`lac`、`lifecycle_state`、`anchorable`、`center_lon`、`center_lat`、`p90_radius_m`、`position_grade`、`drift_pattern` 等字段。
  - `etl_profile_snapshot_diff` 保存相邻 snapshot 的 Cell 级 diff，至少落 `diff_kind`、`from_lifecycle_state`、`to_lifecycle_state`、`centroid_shift_m`、`p90_delta_m`、`anchorable_changed`；flow 页面摘要先在 API 查询时按 diff 聚合，不额外再建 summary 表。
- **验证方式**：
  - 每次 streaming run 应产出完整序列：窗口数 = snapshot 数，snapshot 数 - 1 = diff 组数。
  - 抽查某一 `cell_id` 在相邻 snapshot 的 `lifecycle_state` 和 `centroid_shift_m`，确认 diff 是由真实 snapshot 计算出来，而不是另写一套判定。
- **后续可扩展**：本轮只做 Cell 级 snapshot / diff；BS / LAC 级 snapshot 如果后续确实需要，再从当前表结构扩展。

---

#### 任务 1.3：用 streaming snapshot 重写 flow / observation API，保留页面概念但更换数据源

- **问题**：当前 `rebuild4/backend/app/routers/flow.py`、`rebuild4/backend/app/routers/workspaces.py` 仍面向旧 `batch_flow_summary`、`batch_snapshot`、`observation_workspace_snapshot`。
- **来源**：人类决策 Q2=A；Claude 主线“页面概念保留”；Codex 补充“Observation 当前批次等价空表、FlowSnapshot 契约错误”。
- **修改文件**：`rebuild4/backend/app/routers/flow.py`、`rebuild4/backend/app/routers/workspaces.py`、`rebuild4/backend/app/core/context.py`
- **修改内容**：
  - 保留 `/flow-overview`、`/flow-snapshot/timepoints`、`/flow-snapshot`、`/observation-workspace` 这些 URL，后端实现切到 `etl_profile_snapshot*`。
  - `/flow-overview` 返回“当前 snapshot 绝对值 + 相邻 diff 变化值”，核心指标改成 streaming 语义：当前 `waiting / observing / active / anchorable`，以及“新增 active”“新增 anchorable”“大位移 Cell 数”等。
  - `/flow-snapshot/timepoints` 返回本次 streaming run 的窗口序列；`/flow-snapshot` 返回单个 snapshot 指标和与前一 snapshot 的 diff 摘要，支持前端继续做首帧 / A / B 对比。
  - `/observation-workspace` 以当前 snapshot 的 `waiting / observing` Cell 为主列表，以 `etl_profile_snapshot_diff` 推导“本窗口刚进入 observing / active”“质心大幅移动”“资格项补齐进度”等观察信号。
  - `base_context()` 增加当前 `profile_run_id`、当前 `snapshot_seq` / `snapshot_label`，让前端 banner 能明确“你看到的是哪次 streaming run 的哪一帧”。
- **验证方式**：
  - API 响应不再读取 `batch_flow_summary`、`batch_snapshot`、`observation_workspace_snapshot`。
  - 当前 snapshot 与前一 snapshot 同时存在时，`flow-overview` 和 `observation-workspace` 都能返回非空 delta / diff 数据。
- **后续可扩展**：如果后续要保留“按批次”视图，可以在这一层把日窗口与批次窗口抽象成统一 timepoint，不需要再改页面路由。

---

#### 任务 1.4：前端 flow / snapshot / observation 页面改接新 schema，并把“baseline 资格”改成 streaming 观察语义

- **问题**：前端页面当前既有字段契约漂移，也仍然假设旧治理批次语义，例如 `FlowSnapshotPage.vue` 读取不存在的 metric 名，`ObservationWorkspacePage.vue` 还在用 `baseline_progress`。
- **来源**：Codex 高置信度补充；人类决策 Q2=A；Claude 主线“页面保留，但要讲清楚来源并对齐真实数据”。
- **修改文件**：`rebuild4/frontend/src/lib/api.ts`、`rebuild4/frontend/src/pages/FlowOverviewPage.vue`、`rebuild4/frontend/src/pages/FlowSnapshotPage.vue`、`rebuild4/frontend/src/pages/ObservationWorkspacePage.vue`、`rebuild4/frontend/src/components/DataOriginBanner.vue`（**新建**）、`rebuild4/frontend/src/components/GlobalStatusBar.vue`
- **修改内容**：
  - `FlowOverviewPage.vue` 改读 streaming 指标，不再展示旧四路治理分流；卡片和趋势统一改为 snapshot / diff 语义。
  - `FlowSnapshotPage.vue` 不再把 `snapshots` 数组当单对象读取，改为按 timepoint 选择首帧 / A / B 三列对比；指标名切到 snapshot 表真实字段。
  - `ObservationWorkspacePage.vue` 的三层进度从“存在 / 锚点 / 基线”改为“存在 / 锚点 / 激活”，第三层不再依赖旧 baseline 体系。
  - 在数据来源 banner 中展示 `profile_run_id`、窗口粒度、当前 timepoint、参数版本摘要，避免再次出现“看的是哪套数据”不清楚的问题。
- **验证方式**：
  - 页面首屏不出现空表或 `-` 占满整页的情况。
  - 选择不同 timepoint 时，三页都能切出真实数值变化，而不是只显示一组静态汇总。
- **后续可扩展**：参数版本稳定后，再把参数 hash / 配置文件名放进 banner；本轮先把 run 与 timepoint 显示出来。

---

#### 任务 1.5：把对象浏览 / 对象详情切到 `etl_dim_*`，结束 `obj_*` 与画像主路径的双轨并存

- **问题**：Q1 已明确选 A，但 `rebuild4/backend/app/routers/objects.py` 和对象页仍面向 `obj_*`，导致用户在“画像 2 万 Cell”与“对象 128 万 Cell”之间切换时完全割裂。
- **来源**：人类决策 Q1=A；Codex / Gemini 高置信度补充“Objects 仍查 `obj_*` 是主路径割裂点”；Claude 的现状诊断可作为现有差异说明，但不再采纳其“双域长期并存”建议。
- **修改文件**：`rebuild4/backend/app/routers/objects.py`、`rebuild4/frontend/src/lib/api.ts`、`rebuild4/frontend/src/pages/ObjectsPage.vue`、`rebuild4/frontend/src/pages/ObjectDetailPage.vue`
- **修改内容**：
  - `objects.py` 的 Cell / BS / LAC 查询改到 `etl_dim_cell` / `etl_dim_bs` / `etl_dim_lac`，或在需要同一 run 语境时改查当前 final snapshot 的 companion 数据。
  - `ObjectsPage.vue` 的筛选项改成画像语义：`lifecycle_state`、`anchorable`、`position_grade`、`drift_pattern`、`cell_scale` 等；不再以前台主路径暴露旧 `health_state` / `watch_state` 体系。
  - `ObjectDetailPage.vue` 只保留当前画像详情和“最近一次 snapshot diff”信息；`obj_state_history` / `obj_relation_history` 相关区域改为冻结提示，不再假装有数据。
- **验证方式**：
  - 对象列表总量与 Profile 页面同口径对齐：Cell 应接近 `etl_dim_cell` 当前行数，而不是旧 `obj_cell` 的百万级。
  - 搜索、筛选、分页与后端参数名一致，不再出现前后端 query key 漂移。
- **后续可扩展**：如果后续确实要看对象全生命周期，再从 snapshot diff 反推时间线，不回头依赖 `obj_state_history` 空表。

---

#### 任务 1.6：修复保留页面的已知前端 bug

- **问题**：GovernancePage 和 CellProfilePage 保留在主导航中，但存在字段漂移和失效筛选项，用户会看到空数据或无效选项
- **来源**：Codex 补充（Claude 遗漏）
- **修改文件**：
  - `rebuild4/frontend/src/pages/GovernancePage.vue`
  - `rebuild4/frontend/src/pages/CellProfilePage.vue`
- **修改内容**：
  - GovernancePage 概览卡：`usage_count` → `usage_registrations`，`migration_pending` → `migration_decisions`
  - GovernancePage trusted_loss tab：`breakdown` → `breakdown_type`，`trusted` → `trusted_rows`，`pct` → `filtered_pct`，`with_signal` → `filtered_with_rsrp`
  - CellProfilePage：从 drift/classification 筛选器中移除 `low_collision` 选项（`profile.py` 不再产出此分类，已合并到 `large_coverage`）
- **验证方式**：打开治理页面确认概览卡和 trusted_loss 标签页有数据；打开 Cell 画像页确认筛选选项与 `profile.py` 实际产出一致

---

#### 任务 1.7：清理主导航，只保留已经接上 streaming / profile 权威数据的页面

- **问题**：本轮最重要的是“主路径不误导”；还没改接 streaming 的旧页面如果继续放在主导航，会把用户重新带回旧 read model。
- **来源**：人类决策 Q1=A、Q5=C；Codex / Gemini 对 `RunBatchCenterPage`、`BaselineProfilePage`、`ValidationComparePage`、旧异常工作台的高置信度风险提示。
- **修改文件**：`rebuild4/frontend/src/App.vue`、`rebuild4/frontend/src/router.ts`、`rebuild4/frontend/src/pages/RunBatchCenterPage.vue`、`rebuild4/frontend/src/pages/BaselineProfilePage.vue`、`rebuild4/frontend/src/pages/ValidationComparePage.vue`、`rebuild4/frontend/src/pages/AnomalyWorkspacePage.vue`
- **修改内容**：
  - 主导航只保留 ETL、Profile、FlowOverview、FlowSnapshot、ObservationWorkspace、Objects、Governance 这些已改接真实数据的页面。
  - `RunBatchCenterPage`、`BaselineProfilePage` 暂时从主导航移出，等阶段二改造成“画像运行历史 / 参数版本对比”后再回归。
  - `ValidationComparePage`、`AnomalyWorkspacePage` 若保留直达路由，则页面正文改为“当前冻结 / 待 streaming 模块稳定后重接”的明确提示，不再继续展示旧批次残留数据。
- **验证方式**：
  - 用户从首页进入后，不会再点击到空表、错口径或过期 read model。
  - 主路径的每个页面都能解释“当前数据来自哪次 streaming run / 当前画像表”。
- **后续可扩展**：阶段二完成后，可把 `RunBatchCenterPage` 和 `BaselineProfilePage` 作为“实验运维页”重新加入导航。

---

### 阶段二：应该做（参数外化 + 版本追溯）

> 目标：参数可配置，构建可追溯，改参数重跑可对比

#### 任务 2.1：把业务阈值外化到 YAML，保留算法常量在代码中

- **问题**：当前 `profile.py` 中业务阈值都写死在 SQL 里，改参数必须改代码。
- **来源**：人类决策 Q3=B；Claude 主线“区分算法常量与业务阈值”；三方一致发现“参数硬编码存在”。
- **修改文件**：`rebuild4/backend/app/etl/profile.py`、`rebuild4/backend/app/etl/pipeline.py`、`rebuild4/backend/app/etl/profile_params.yaml`
- **修改内容**：
  - 新建 `profile_params.yaml`，只外化业务阈值：`lifecycle`、`anchorable`、`position_grade`、`gps_confidence`、`signal_confidence`、`cell_scale` 等。
  - 中国边界、经纬度转米系数、漂移算法框架等“算法常量”继续留在代码内，不做运营化开关。
  - `pipeline.py` / `profile.py` 支持传入参数文件路径；streaming run 读取 YAML 后再执行，不再直接改 SQL 字符串常量。
- **验证方式**：
  - 修改 YAML 中某个 lifecycle / anchorable 阈值，重新运行 streaming，能看到 snapshot 与 diff 结果变化。
  - 不改代码即可完成一次参数试验。
- **后续可扩展**：后续如需只读展示参数摘要，可加到 `GovernancePage.vue`；本轮不做在线编辑。

---

#### 任务 2.2：建立独立的 `etl_profile_run_log`，形成 streaming 版本追溯主线

- **问题**：有了 snapshot 还不够，仍需回答“这次 streaming 是何时、用什么参数、跑了多少帧、当前哪次为主版本”。
- **来源**：人类决策 Q4=B；三方一致发现“当前画像缺少版本上下文”。
- **修改文件**：`rebuild4/backend/app/etl/profile.py`、`rebuild4/backend/app/core/context.py`
- **修改内容**：
  - 新建 `rebuild4_meta.etl_profile_run_log`，最少记录：`profile_run_id`、`mode`、`window_granularity`、`source_table`、`source_date_from`、`source_date_to`、`params_path`、`params_hash`、`started_at`、`finished_at`、`status`、`snapshot_count`、`final_cell_count`、`final_bs_count`、`final_lac_count`、`is_current`。
  - `etl_profile_snapshot*` 全部挂 `profile_run_id` 外键语义；当前运行完成后切换 `is_current`，前端统一从这里找当前版本。
  - `base_context()` 改为同时返回当前 `profile_run_id` 与参数版本摘要，形成新的全局状态条。
- **验证方式**：
  - 连续跑两次不同参数的 streaming 后，能在日志中区分两次 run，并能明确哪次是 current。
  - 切换 current run 后，flow / objects / profile 页都切到相同版本上下文。
- **后续可扩展**：如果以后要支持“草稿 run / 正式 run”，只需在此表加 `run_role` 或 `published_at`，不必复用旧 `run` / `batch`。

---

#### 任务 2.3：把旧 Run / Baseline 页面改造成“画像运行历史 / 版本对比”页

- **问题**：阶段一把旧治理批次页移出主导航后，仍需要一个地方查看 streaming 运行历史和 run-to-run 差异。
- **来源**：人类决策 Q4=B；Codex 高置信度补充“旧 run/batch 与当前画像链路脱节”；Claude 主线“画像需要独立版本记录”。
- **修改文件**：`rebuild4/backend/app/routers/runs.py`、`rebuild4/backend/app/routers/baseline.py`、`rebuild4/frontend/src/pages/RunBatchCenterPage.vue`、`rebuild4/frontend/src/pages/BaselineProfilePage.vue`、`rebuild4/frontend/src/lib/api.ts`
- **修改内容**：
  - `runs.py` 改读 `etl_profile_run_log` + `etl_profile_snapshot`，把旧“批次中心”改造成“画像运行中心”，展示每次 run 的参数、窗口数、最终对象规模、主要 diff 摘要。
  - `baseline.py` 不再以前台主路径依赖旧 `baseline_version`；改成“当前 run vs 上一 run 的 final snapshot diff”摘要页，页面名称可保留但文案改为“画像版本基线”。
  - `BaselineProfilePage.vue` 以 `profile_run_id` 为主键，展示参数差异、最终 snapshot 差异、重点样本变更。
- **验证方式**：
  - 至少有两次 streaming run 时，页面能正确比较当前 run 与上一 run。
  - 页面不再直接消费旧 `baseline_version` / `baseline_diff_summary` 作为前台主语义。
- **后续可扩展**：如果后续确实需要“命名基线版本”，可以把某次 `profile_run_id` 标记成 baseline，而不是回到旧治理基线模型。

---

### 阶段三：可以做 / 搁置

- **冻结 `compare_*`**：`rebuild4_meta.compare_job` / `compare_result` 继续冻结；若后续恢复，直接比较两个 `profile_run_id` 的 final snapshot，不再沿用旧 compare 语义。
- **冻结 `obj_state_history` / `obj_relation_history`**：本轮不回填空表；对象时间线如有需要，后续由 `etl_profile_snapshot_diff` 反推。
- **冻结 anomaly 工作台重构**：`AnomalyWorkspacePage.vue` 暂不强行接回旧 `batch_anomaly_*`；等 streaming 稳定后，再评估是否基于 `drift_pattern`、大位移 diff、异常迁移规则重建。
- **不做旧 `batch_*` 历史回填**：旧 `batch_flow_summary` / `batch_snapshot` 只留作历史参考，不尝试回填成 streaming 口径。

---

## 从 Codex / Gemini 吸收的补充发现

| 发现 | 来源 | 采纳原因 | 对应任务 |
|------|------|---------|---------|
| `observation_workspace_snapshot` 只有初始化批次，当前批次视角等价空表 | Codex | 这是已核实的事实，直接说明旧观察工作台不能继续作为当前画像主数据源 | 任务 1.3 / 1.4 |
| `FlowSnapshotPage.vue`、`RunBatchCenterPage.vue`、`BaselineProfilePage.vue`、`ObjectsPage.vue` 存在明显前后端字段契约漂移 | Codex | 这是具体实现层问题，不涉及架构争议，必须修 | 任务 1.4 / 1.5 / 2.3 |
| `compare_job`、`compare_result`、`obj_state_history`、`obj_relation_history`、`baseline_diff_object` 为空或近空壳 | Codex / Claude / Gemini | 三方都提到无有效产出，且 Q5 已决定暂时冻结 | 阶段三 / 不处理问题 |
| `ObjectsPage` 继续读取 `obj_*` 会把前台重新拉回旧治理对象世界 | Codex / Gemini | 与 Q1=A 直接冲突，必须切到 `etl_dim_*` | 任务 1.5 |

---

## 不处理的问题

| 问题 | 不处理原因 |
|------|-----------|
| 旧治理体系下的 `obj_*` 与 `etl_dim_*` 一一历史映射回填 | 本轮核心是让 streaming 画像可观察并成为前台权威，不做大规模历史桥接。 |
| 基于旧 `batch_anomaly_*` 的异常工作台继续演进 | 这会把主路径重新绑回旧批次语义；等 streaming snapshot 稳定后，再定义新的异常口径。 |
| `compare_*` 页面恢复为旧批次对比中心 | Q5 已明确冻结；后续若恢复，比较对象应改为 `profile_run_id` 而不是旧 `run/batch`。 |
| `obj_state_history` / `obj_relation_history` 空表补数 | 本轮没有必要为了旧表强造历史，snapshot diff 已能覆盖当前阶段最关心的观察变化。 |

---

## 方案边界说明

本方案完成后：

- **能做什么**：
  - 用同一套已验证画像算法，按天或按窗口累积运行 streaming，得到 snapshot 序列。
  - 在流转总览 / 流转快照 / 观察工作台中看到真实的 Cell 状态推进、资格补齐与质心变化。
  - 让对象浏览回到 `etl_dim_*` 权威世界，主路径不再在“2 万画像 Cell”和“128 万治理对象”之间跳语义。
  - 改 YAML 参数后重跑 streaming，并通过 run log / snapshot diff 观察参数效果。

- **不能做什么**：
  - 不能把旧 `batch_*` 历史自动翻译成新的 streaming snapshot 历史。
  - 不能恢复旧 `compare_*`、`obj_state_history`、`obj_relation_history` 那套完整治理时间线。
  - 不能在本轮内同时完成 anomaly 重构、基线重构和所有 legacy read model 回填。

- **后续重构方向**：
  - 若 streaming 模块稳定，再把 `RunBatchCenterPage`、`BaselineProfilePage` 做成标准的“参数试验 / 版本对比”中心。
  - 若确实需要对象历史与异常工作台，再统一建立“基于 snapshot diff 的派生 read model”，而不是回头修补旧治理批次体系。
  - 若参数试验频率升高，再考虑在 `GovernancePage.vue` 加只读参数展示或审批式参数管理，但不改变 Q3=B 的轻量路线。
