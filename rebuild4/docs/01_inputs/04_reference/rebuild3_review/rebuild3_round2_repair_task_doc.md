# rebuild3 第二轮修复任务文档（审阅版）

状态：待你审阅确认，未开始实施
编写时间：2026-04-05
关联审计：`docs1/Claude_reaudit_output.md`
关联字段基线：`docs1/Claude_field_baseline.md`

## 0. 本文档的用途

这不是“实现思路草稿”，而是本轮修复的正式任务边界文档。

在你确认之前：
- 不开始代码修复
- 不运行新的 scenario 回放脚本
- 不做会改变当前数据库内容的治理重跑

本文档的目标是先把“修什么、按什么真相源修、哪些本轮修、哪些明确不在本轮修、修完如何验收”冻结下来，避免下一轮实施再次偏航。

---

## 1. 真相源与裁决规则

### 1.1 必须遵守的真相源顺序

1. Tier 0：
   - `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
   - `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
   - `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
2. Tier 1：
   - `rebuild3/docs/UI_v2/design_notes.md`
   - `rebuild3/docs/UI_v2/index.html`
   - `rebuild3/docs/UI_v2/pages/*_doc.md`
3. 本轮复评结论：
   - `docs1/Claude_reaudit_output.md`
   - `docs1/Claude_field_baseline.md`

### 1.2 实施裁决规则

- 业务语义以 Tier 0 为准。
- 页面主问题、布局表达、空状态表达以 UI_v2 为准。
- 如果当前实现和文档冲突，先判当前实现有问题，不得反向用代码解释设计。
- 如果 UI_v2 页面文档和 Tier 0 冲突：
  - 页面展示形式参考 UI_v2
  - 状态/资格/四分流/baseline 口径参考 Tier 0

---

## 2. 本轮修复策略：先恢复“语义真实”，不在本轮重建完整 scenario 治理回放

### 2.1 核心判断

根据复评结果，当前最大的风险不是“样式没齐”，而是：
- synthetic scenario 被当成真实时间快照
- sample/full/fallback 被当成正式主语
- 页面在“能渲染”的前提下仍然说错了话

因此，本轮采用 **保守且可靠的修复路线**：

### 本轮目标

把系统恢复到“页面主语真实、数据来源真实、没有偷偷 fallback、没有伪时间语义”的状态。

### 本轮不做

**不在本轮尝试重建完整的真实 scenario replay 治理流水线。**

原因：
- 这属于更大规模的数据链路重构；
- 如果在没有再次冻结任务边界的情况下直接做，极容易再次跑偏；
- 当前更可靠的做法是：**先把 synthetic / fallback / sample validation 从主语位置撤掉或显式降级**，让系统先“说真话”。

### 本轮完成后系统应达到的状态

- 所有主流程页面只基于“真实 subject”说话。
- 如果没有足够的真实时间点/真实上一版/真实对照数据，页面必须进入诚实空状态，而不是拿别的数据替代。
- 所有 fallback / synthetic 数据必须显式标识，不再伪装成正式结果。

---

## 3. 本轮修复范围（确认后实施）

本轮只做以下 6 个任务包。

### 任务包 A：建立统一的数据来源与主语契约

#### A1. 新增统一来源标识

对以下后端读模型增加统一来源字段：
- `/api/v1/runs/flow-overview`
- `/api/v1/runs/flow-snapshots`
- `/api/v1/runs/batches`
- `/api/v1/runs/baseline-profile`
- `/api/v1/runs/initialization`
- `/api/v1/compare/overview`
- `/api/v1/compare/diffs`
- `/api/v1/governance/*`

建议字段：
- `data_origin`: `real` / `synthetic` / `fallback`
- `origin_detail`: 可选；保留更细粒度来源，例如 `report_fallback`、`fallback_catalog`、`scenario_ratio_estimated`
- `subject_scope`: 例如 `current_batch` / `initialization_run` / `baseline_version` / `validation_reference`
- `subject_note`: 面向 UI 的短说明

#### A2. 统一“真实 subject”的定义

本轮定义如下：
- `real`：直接来自当前正式对象/事实/meta 表的正式结果，且不是 hardcode/fallback，也不是 synthetic scenario procedure 拼装值。`real` 的 `batch_snapshot` 必须是"批次完成后真实写入的逐批治理快照"，而不是经比例估算拼装的摘要。如果某个 run 的 `batch_snapshot` 是比例估算值（包括 full init run），同样标记为 `synthetic`。
- `synthetic`：由 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql` 生成的 scenario replay 元数据，以及任何基于比例估算而非真实治理流水线写入的快照记录。
- `fallback`：来自 hardcode、报告常量、catalog 常量。

实施要求：
- 对外 API 合同层统一只暴露三类 `data_origin`：`real` / `synthetic` / `fallback`；
- 如果实现内部仍区分 `report_fallback`、`fallback_catalog` 等细类，可放入 `origin_detail`，但前端显示逻辑必须先按三类合同执行。

#### A3. 实施目标

后续所有页面分流逻辑都只能基于这个契约：
- `real` 才能占据页面主语位置；
- `synthetic` 不能再被当成正式主语；
- `fallback` 必须显式提示。

前端必须读取 `data_origin`，并按以下规则做视觉区分：
- `real`：正常展示，无额外标记；
- `synthetic`：在数据区域旁显示调试标记（如 `[合成数据]` 小角标），不阻断展示但必须可见；
- `fallback`：在页面顶部显示阻断级 banner，明确说明"当前为 fallback 数据，不代表实时结果"。

#### A4. `run_shared.py` 统一来源契约模块

`rebuild3/backend/app/api/run_shared.py` 是本轮新增的统一模块，负责定义和输出 `data_origin / origin_detail / subject_scope / subject_note` 四个字段。

规则：
- 所有 run / snapshot 类 API（`run.py`、`run_snapshot.py`、`run_workspaces.py`）**必须从 `run_shared.py` 引用**来源契约，禁止各自重复定义 origin logic；
- `compare.py` 和 `governance.py` 的 fallback 标识也应保持与 `run_shared.py` 的定义一致；
- `FULL_BATCH_ID` / `SAMPLE_BATCH_ID` 只能作为兼容期局部兜底，不得继续作为主流程页的全局默认主语。

#### A5. 实施顺序约束

任务包 A（尤其 A4 `run_shared.py` 的建立）必须先于任务包 B、C、D、E 完成，后续任务包的 origin 标识均依赖本模块。


---

### 任务包 B：修复 `/flow/snapshot`，恢复“诚实快照页”

#### B1. 本轮处理原则

本轮 **不让 synthetic scenario 继续冒充真实 timepoint snapshot**。

#### B2. 明确改法

1. 后端 `run_snapshot` 目录中，默认只收录 `run_type = scenario_replay` 的 run，**不收录 `full_initialization` 类型**（full init 不是 scenario 时间线，不应出现在快照视图的场景下拉里）。
2. 如果当前没有任何真实的 scenario/timepoint run：
   - `/flow/snapshot` 页面进入诚实空状态；
   - 提示"当前尚无真实时间点快照；scenario replay 仍为 synthetic，暂不作为正式快照展示"。
3. 不再把 synthetic run 放入用户可选主列表。
4. 如果保留 synthetic 调试能力，只能作为显式诊断模式，不进入正式主视图。
5. 修正百分比计算：
   - 要么全部基于累计值 / 累计输入；
   - 要么全部基于单批值 / 单批输入；
   - 本轮建议：**页面若无真实 timepoint 数据，则直接不展示对照表**，从而彻底避免继续使用 synthetic 指标。
6. 场景下拉 label 必须区分 smoke 与正式场景，禁止显示相同名称：
   - label 必须包含 `scenario_key`（如 `INIT1D_STEP2H`）或可区分前缀；
   - smoke 场景（`scenario_key` 含 `SMOKE`）在下拉里须标注 `[SMOKE]`，不能与正式场景同名呈现。

#### B3. 本轮验收标准

- `/flow/snapshot` 不再展示 `2437.4%`、`5025.1%`、`10896.5%` 等错误百分比。
- `/flow/snapshot` 不再把 synthetic scenario 当正式快照。
- 如果没有真实时间点，页面出现明确空状态，不切换成其他伪逻辑。

#### B4. 涉及文件

后端：
- `rebuild3/backend/app/api/run_snapshot.py`
- `rebuild3/backend/app/api/run.py`
- 可能新增一个共用 origin/helper 文件，或放入 `rebuild3/backend/app/api/run_shared.py`

前端：
- `rebuild3/frontend/src/pages/FlowSnapshotPage.vue`

#### B5. 本轮不做

- 不改写 `004_timepoint_snapshot_scenarios.sql` 去实现真实治理回放。
- 不在本轮重跑 scenario 数据。

---

### 任务包 C：修复 `/flow/overview` 与 `/runs`，恢复真实主语

#### C1. `/flow/overview` 改法

1. 页面主语改为“最新真实 batch”或“用户指定真实 batch”。
2. 取消 sample validation 作为 delta 基线。
3. 如果没有上一真实 batch：
   - delta 区块显示“暂无上一真实批次”；
   - 不再拿 sample 代替。
4. 页面上下文条必须与当前真实 batch 对齐。
5. `compare_callout` 不能继续使用历史硬编码数字：
   - 如果当前可由真实 batch 动态计算，则改成实时计算；
   - 如果当前无法动态算出，则改成明确的“历史参考说明”，并通过 `data_origin` / `subject_note` 显式降级，不能继续伪装成当前批次结论。

#### C2. `/runs` 改法

1. 数据源改为 `rebuild3_meta.batch` 中的真实 batch 列表。
   - **主列表以 `run` 为一级条目**（如 `INIT2D_STEP2H` 场景为一行），每个 run 可展开或跳转查看该 run 下的批次子列表；**不得把 142 条批次行全部平铺为主列表**（否则用户无法使用）。
   - 批次子列表按 `batch_seq` 排序，展示 `timepoint_role / batch_seq / snapshot_at / 四分流摘要`。
2. 当前若某 run 下只有 1 个 rolling 批次（即仅 init 批，无后续时间点）：
   - 子列表只显示该 init 批；
   - 趋势区明确提示"真实批次不足，无法形成趋势"。
3. sample/full 对照不再占据主列表主语。
4. rerun/趋势位允许为空，但不能伪造。

#### C3. 本轮验收标准

- `/flow/overview` 的 `run_id` / `batch_id` 不再是 sample/full 对照逻辑下的伪当前态。
- `/flow/overview` 的 `compare_callout` 不再静默使用历史硬编码数字冒充当前批次结论。
- `/runs` 的主列表不再只有“sample + full 两条伪批次对照”。
- 如果真实批次不足，页面诚实显示“趋势不足”，而不是构造假趋势。

#### C4. 涉及文件

后端：
- `rebuild3/backend/app/api/run.py`
- `rebuild3/backend/app/api/run_shared.py`

前端：
- `rebuild3/frontend/src/pages/FlowOverviewPage.vue`
- `rebuild3/frontend/src/pages/RunBatchCenterPage.vue`

---

### 任务包 D：修复 `/baseline` 与 `/initialization` 的页面主语

#### D1. `/baseline` 改法

1. 页面只回答“当前真实 baseline 版本”的问题。
2. 当前如果只有 1 个 baseline version：
   - 显示当前版本、触发原因、覆盖量、稳定性指标；
   - 差异区明确显示“暂无上一版 baseline，无法比较版本差异”。
3. 不再用 rebuild2 对照结果替代“上一版差异”。
4. 不再把 `compare_membership` 硬编码成 baseline diff。

#### D2. `/initialization` 改法

1. 页面上下文切换为真实 full initialization run/batch。
2. 卡片和步骤说明都以真实 initialization subject 为主。
3. sample validation 不再作为初始化页主体。
4. 若某些步骤详情当前缺真实明细，可以保留“步骤已完成 + 暂无细粒度 step detail”的诚实表达，但不能继续说 sample 是 initialization。

#### D3. 本轮验收标准

- `/baseline` 页面不再出现“仅 rebuild3”这种伪版本差异表达作为主内容。
- `/initialization` 的 `run_id` 不再是 `RUN-SAMPLE-...`。
- 页面空状态 / 无上一版状态表达清晰。

#### D4. 涉及文件

后端：
- `rebuild3/backend/app/api/run_workspaces.py`
- `rebuild3/backend/app/api/run.py`

前端：
- `rebuild3/frontend/src/pages/BaselineProfilePage.vue`
- `rebuild3/frontend/src/pages/InitializationPage.vue`

---

### 任务包 E：修复 `/compare` 与 `/governance` 的 fallback 透明性

#### E1. 处理原则

本轮不强行接真实 compare / governance registry；先确保页面不误导。

#### E2. 明确改法

1. 保留当前 fallback 数据，但必须在 UI 顶部显示明显 banner：
   - Compare：`当前为 fallback 对照结果，仅供参考，不代表实时比对结果`
   - Governance：`当前为 fallback 资产目录，仅供梳理，不代表已接入实时元数据注册表`
2. 后端继续返回 `data_origin=fallback`。
3. 前端必须消费并展示 `data_origin`。
4. 页面上的按钮/文案避免暗示“实时对比”“实时治理目录”。

#### E3. 本轮验收标准

- 用户进入 `/compare`、`/governance`，能在首屏明确看到 fallback 提示。
- 页面不再在视觉上伪装成正式实时数据。

#### E4. 涉及文件

后端：
- `rebuild3/backend/app/api/compare.py`
- `rebuild3/backend/app/api/governance.py`

前端：
- `rebuild3/frontend/src/pages/ValidationComparePage.vue`
- `rebuild3/frontend/src/pages/GovernancePage.vue`

---

### 任务包 F：修复字段表达漂移（本轮仅做“说真话”的最小修正）

#### F1. LAC `region_quality_label`

改法：
- 对 `coverage_insufficient`、`issue_present` 做稳定中文映射。
- 仍保持它是解释层标签，不能抬升为 `health_state`。

#### F2. BS / Cell 参考列

本轮建议采用“真实来源优先”策略：
- 若当前只有 `gps_quality`，则前端列名改为 `GPS质量(参考)` 或 `GPS质量标签(参考)`；
- `signal_confidence` 当前无真实来源，本轮从 BS 页主表中移除或改成明确空状态说明，不再保留一个看似应该有值、但实际永远是 `—` 的伪列。
- Cell 页的坐标来源必须冻结为单一合同，不再静默混用：
  - 若页面主语定义为对象快照，则优先使用 `obj_cell.centroid_lon/centroid_lat`，并统一经 API 映射为页面字段；
  - 若确实需要保留 `stg_cell_profile.center_lon/center_lat` 作为参考坐标，则必须拆成显式参考字段或在字段标签中说明来源，不能继续用同名 `center_lon/center_lat` 掩盖来源差异。
- Cell 页当前 `gps_quality` 实际来自 `stg_cell_profile.bs_gps_quality`，本轮至少要把来源层级说清楚：
  - 要么改名为 `BS侧GPS质量(参考)` / 同等明确命名；
  - 要么从 Cell 主表中移除该列，避免把父 BS 参考值误读为 Cell 自身质量。

> 这里我建议优先“改列名 + 删空列”，而不是伪造 `gps_confidence` / `signal_confidence` 映射。
> 原因：这样最可靠，也最符合“先说真话”。

#### F3. 本轮验收标准

- LAC 页面不再直接显示 `issue_present` / `coverage_insufficient` 技术码。
- BS / Cell 页面不再把 `gps_quality` 冒充成 `gps_confidence`。
- BS 页不再保留一个无真实来源的“信号可信度(参考)”假列。
- Cell 页面不再静默混用 `obj_cell.centroid_*` 与 profile `center_*` 为同一来源。
- Cell 页面不再把父 BS 的 `bs_gps_quality` 伪装成 Cell 自身 `gps_quality`。

#### F4. 涉及文件

后端：
- `rebuild3/backend/app/api/object_common.py`
- 如需详情页同步，则包括 `rebuild3/backend/app/api/object_detail.py`

前端：
- `rebuild3/frontend/src/pages/LacProfilePage.vue`
- `rebuild3/frontend/src/pages/BsProfilePage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

---

## 4. 本轮明确不做的事项

以下内容不纳入本轮实施，避免任务失控：

1. 不重建完整真实 scenario replay 治理流水线。
2. 不重跑全量或 scenario 数据。
3. 不新增复杂的 compare 实时计算系统。
4. 不新增完整 governance 元数据注册中心。
5. 不做大规模 UI 重构或视觉风格调整。
6. 不动 Tier 0 / UI_v2 真相源文档内容。

---

## 5. 交付物要求

本轮实施完成后，必须同步更新文档：

1. 修复说明：
   - `docs1/rebuild3_round2_repair_execution_note.md`
2. 如有字段表达变化：
   - 更新 `docs1/Claude_field_baseline.md` 的实现一致性结论
3. 如有 fallback 显示策略变化：
   - 在执行说明里明确列出哪些页面现在显示 fallback banner

---

## 6. 验收清单（你确认文档后，我将按此逐项自验）

### 6.1 API 验收

- `/api/v1/runs/flow-snapshots`：
  - 不再默认返回 synthetic scenario 作为正式快照源
  - 不再出现错误百分比
  - 有 `data_origin` / `subject_note`
- `/api/v1/runs/flow-overview`：
  - 不再用 sample validation 做 delta
  - 指向真实当前 batch
- `/api/v1/runs/batches`：
  - 主列表来自真实 batch
- `/api/v1/runs/baseline-profile`：
  - 不再把 rebuild2 对照当“版本差异”
- `/api/v1/runs/initialization`：
  - 不再指向 sample run
- `/api/v1/compare/*`、`/api/v1/governance/*`：
  - `data_origin=fallback` 明确保留

### 6.2 页面验收

- `/flow/snapshot`：
  - 首屏要么是“真实快照”，要么是诚实空状态
  - 不再出现 >100% 的离谱百分比
- `/flow/overview`：
  - context bar 指向真实当前 batch
- `/runs`：
  - 不再显示“sample/full 两条伪批次中心”
- `/baseline`：
  - 若无上一版，明确显示“暂无上一版可比”
- `/initialization`：
  - 页面主体来自真实 initialization run
- `/compare`、`/governance`：
  - 首屏可见 fallback banner
- `/profiles/lac`：
  - 区域质量标签中文化
- `/profiles/bs`、`/profiles/cell`：
  - 不再用错误列名冒充旧参考字段

### 6.3 Playwright 验收

本轮实施后至少重验：
- `/flow/snapshot`
- `/flow/overview`
- `/runs`
- `/baseline`
- `/initialization`
- `/compare`
- `/governance`
- `/profiles/lac`
- `/profiles/bs`
- `/profiles/cell`

验收脚本路径：`rebuild3/tests/`（或与实施同步新建）；验收执行结果同步写入 `docs1/rebuild3_round2_repair_execution_note.md`。

---

## 7. 预计改动文件清单

### 后端

- `rebuild3/backend/app/api/run_shared.py`
- `rebuild3/backend/app/api/run.py`
- `rebuild3/backend/app/api/run_snapshot.py`
- `rebuild3/backend/app/api/run_workspaces.py`
- `rebuild3/backend/app/api/object_common.py`
- `rebuild3/backend/app/api/object_detail.py`（如需同步标签映射）
- `rebuild3/backend/app/api/compare.py`
- `rebuild3/backend/app/api/governance.py`

### 前端

- `rebuild3/frontend/src/pages/FlowSnapshotPage.vue`
- `rebuild3/frontend/src/pages/FlowOverviewPage.vue`
- `rebuild3/frontend/src/pages/RunBatchCenterPage.vue`
- `rebuild3/frontend/src/pages/BaselineProfilePage.vue`
- `rebuild3/frontend/src/pages/InitializationPage.vue`
- `rebuild3/frontend/src/pages/ValidationComparePage.vue`
- `rebuild3/frontend/src/pages/GovernancePage.vue`
- `rebuild3/frontend/src/pages/LacProfilePage.vue`
- `rebuild3/frontend/src/pages/BsProfilePage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

### 本轮预期不改动的文件

- `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql`
- `rebuild3/backend/scripts/run_timepoint_snapshot_scenarios.py`
- 任何会触发真实数据重跑的 SQL / shell 启动脚本

---

## 8. 下一轮单独立项的后续任务（不并入本轮）

以下任务需要单独出新的任务文档，不并入这次修复：

1. 真实 scenario replay 治理链重建
   - 目标：让 scenario/timepoint 真正复用正式治理语义，落真实 `batch_snapshot`
2. compare 实时结果表 / 读模型建设
3. governance 实时资产注册表建设
4. observation / anomalies 真实多批趋势建设
5. `rebuild3_sample_meta` 的归属治理
   - 目标：明确 sample validation schema 是否继续保留；
   - 二选一：迁回 `rebuild3_meta` 并用 `run_type = sample_validation` 表达，或在 Tier 0 / 技术文档中正式登记其用途与边界。

---

## 9. 禁止再次默认假设清单

- 禁止继续把 synthetic scenario 当正式快照。
- 禁止继续用 sample/full 代替“当前批次”或“历史趋势”。
- 禁止继续用 rebuild2 对照代替“上一版 baseline”。
- 禁止把 fallback 数据静默包装成实时结果。
- 禁止继续用历史硬编码 `compare_callout` 数字冒充当前批次结论。
- 禁止把 `gps_quality` 继续命名成 `gps_confidence`。
- 禁止继续把 `obj_cell.centroid_*` 与 profile `center_*` 默认为同一真相源。
- 禁止保留无真实来源、但看起来像正式字段的空列。
- 禁止因为“页面能展示”就认为语义正确。

---

## 10. 需要你确认的关键实施取向

我建议你确认以下取向后，我再开始修复：

### 建议方案（推荐）

- 本轮先做“语义回正”和“说真话”修复；
- 不在本轮重建真实 scenario replay；
- `/flow/snapshot` 若无真实 timepoint，则进入诚实空状态；
- BS / Cell 参考列改成真实字段命名，不伪造旧可信度。

### 不建议本轮直接做的方案

- 直接把 `004_timepoint_snapshot_scenarios.sql` 改造成完整真实治理回放；
- 直接在本轮同时做 compare/governance 实时系统；
- 为了“看起来完整”继续保留 synthetic/fallback/sample 伪主语。

如果你认可，我下一步就按这份文档开始实施，并在实施前后严格对照本文件验收。
