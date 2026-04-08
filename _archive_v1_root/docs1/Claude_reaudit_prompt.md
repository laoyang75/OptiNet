# rebuild3 系统级独立复评 Prompt（Claude 专版）

你正在执行一次**从零开始的独立系统级复评**。

这不是补丁回顾、不是页面冒烟，也不是对任何已有审计结论的确认。你的任务是**独立**建立基线、独立发现问题、独立给出优先级结论。

> ⚠️ **重要约束**：本次评估中，**不得阅读任何已有审计输出文件**（包括同目录下任何 `reaudit_output`、`execution_note`、`repair_task_doc` 等已有结论性文档）。这些文件的存在是为了后续对比，不是你的参考。你必须凭借对源文档和代码的直接阅读，独立形成判断。

---

## 一、你的角色

你是 rebuild3 项目的系统级独立复评者，同时站在 4 个层面进行审计：

1. **原始冻结文档层**：系统本来应该是什么——从 Tier 0 文档读出来
2. **UI_v2 设计层**：页面最终应该向人表达什么——从 Tier 1 文档读出来
3. **派生实施文档层**：后续执行文档有没有跑偏——按需核查 Tier 2
4. **当前实现层**：代码、API、SQL、数据库里实际做成了什么

**你必须先完成"文档基线建立"，再评估实现。禁止跳过文档阶段直接看代码。**

---

## 二、真相源优先级（必须遵守）

### Tier 0：原始冻结文档（最上游真相源，必须最先读）

以下三份文档是最高权威，必须全量读取，提炼出正式规则后再进入后续阶段：

- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
- `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
- `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`

这三份文档定义：
- 系统主语（Cell / BS / LAC 的地位与关系）
- 生命周期（`lifecycle_state`）与健康状态（`health_state`）的严格分离
- 三类资格边界（`existence_eligible`、`anchorable`、`baseline_eligible`）
- 初始化与 2 小时增量的统一治理语义
- 四分流逻辑（`fact_governed`、`fact_pending_observation`、`fact_pending_issue`、`fact_rejected`）
- baseline 冻结机制：当前批次只读上一版，新版只供下一批消费
- 技术边界：SQL-first / Postgres-first / Vue3+TS+Vite / FastAPI

### Tier 1：UI_v2 设计文档（定义人类最终对齐的页面表达）

以下文档定义每个页面要回答的问题、布局、信息层次与交互：

- `rebuild3/docs/UI_v2/design_notes.md`
- `rebuild3/docs/UI_v2/index.html`
- `rebuild3/docs/UI_v2/design_system.html`
- `rebuild3/docs/UI_v2/pages/*.html`（每页静态稿）
- `rebuild3/docs/UI_v2/pages/*_doc.md`（每页主问题、字段层次、交互要求）

**裁决规则：**
- 页面主语、用户问题、布局、信息层次：以 UI_v2 为准
- 底层业务/数据口径、状态语义：以 Tier 0 为准
- 如果两者有冲突：**必须显式记录冲突，不能自行裁决**

### Tier 2：派生整改文档（遇到具体问题时按需查，不预读）

- `rebuild3/docs/00_审核结论.md` — 文档冲突裁决参考
- `rebuild3/docs/ui_final_rectification_report.md` — 上轮 UI 修复记录
- `rebuild3/docs/api_models.md` — API 字段约定
- `rebuild3/docs/param_matrix.md` — 资格阈值定义
- `rebuild3/docs/runtime_startup_guide.md` — 本地启动说明
- `docs1/rebuild3_snapshot_rerun_plan.md` — scenario/timepoint 设计补充

> ⚠️ **禁止引用**：`rebuild3/docs/04*` 系列所有文件（`04_`、`04a_`、`04b_`、`04c_`、`04d_`、`04e_`、`04f_`）均为历史执行 prompt，**不是设计基线**，禁止作为真相源。同样禁止引用 `ui_restructure_prompt.md`、`ui_restructure_audit_prompt.md`。

### Tier 3：当前实现（被审对象，不是真相来源）

- 前端：`rebuild3/frontend/src/pages/*.vue`、组件、状态管理
- 后端：`rebuild3/backend/app/api/*.py`（FastAPI 路由与读模型）
- SQL：`rebuild3/backend/sql/schema/*.sql`、`rebuild3/backend/sql/govern/*.sql`
- 脚本：`rebuild3/backend/scripts/*.py`、`*.sh`
- 数据库实际状态：`rebuild3_meta.*`、`rebuild3.*` 各表行数与内容

**原则：代码与文档冲突时，一律先判代码有问题。只有文档之间互相冲突时，才进入冲突记录流程。**

---

## 三、评估原则（必须遵守）

### 1. 先建文档基线，再看实现

必须先回答：
- 系统要解决什么问题
- 每个页面要回答什么问题
- 每个状态 / 字段 / 资格 / 分流 / baseline 的正式含义
- 初始化与增量的关系如何定义

### 2. 不接受"近似正确"

以下情况不能判通过：
- 用 `sample / full / baseline` 近似时间快照
- 用 fallback 数据冒充真实字段，且未显式标识
- 用共享组件硬套不同页面的不同语义
- 用"数据暂时不足"掩盖页面主语错误
- 用当前实现反推设计意图
- 用缓存结果掩盖底层字段错误
- 页面"能渲染"不等于"语义正确"

### 3. 必须重查字段与边界

对所有关键字段，必须独立确认：
- 字段定义与层级（主状态 / 资格 / 解释层 / 参考层）
- 数据表真实来源（查 schema 和 API 实现，不只看字段名）
- 是否存在旧字段冒充新语义
- 空值规则 / fallback 规则
- 是否允许被 UI 抬升为主状态

### 4. 必须建立全程基线产物

每个阶段必须生成可复核的产物，不能只给结论性文字。

### 5. 文档冲突处理

遇到 Tier 0 与 Tier 1 冲突时：
1. 记录冲突位置
2. 说明冲突影响
3. 默认裁决：页面设计语义参考 UI_v2；底层业务口径参考 Tier 0
4. **不得无记录地自行二次解释**

---

## 四、必须先产出的基线文件与检查点

每个 Phase 必须在进入下一个 Phase 之前完成。

### Phase 0：资料盘点与真相源分级基线

**目标**：确认评估范围完整。

必须输出：
1. 文档清单与分级表（Tier 0 / 1 / 2 / 忽略）
2. 路由清单（路由 → 前端页面文件 → 备注）
3. 页面 → 设计稿映射表
4. 页面 → API 映射表
5. API → 表/视图 映射表（通过阅读后端代码建立）
6. 场景 / 运行数据基线：数据库里实际存在哪些 run / batch / snapshot，通过读代码中的 SQL 查询或数据库 schema 推断

**如何查数据库**：通过阅读后端代码（`rebuild3/backend/app/api/*.py`、`rebuild3/backend/sql/`）找到访问数据库的方式，或直接读 `rebuild3_meta` schema 下各表的 DDL 和行数统计。如果工具允许执行 SQL，可查询 `rebuild3_meta.run`、`rebuild3_meta.batch`、`rebuild3_meta.batch_snapshot` 行数与关键字段。

**检查点**：
- 三份 Tier 0 文档是否已全量读取并提炼出正式规则
- UI_v2 所有页面文档是否已纳入
- 数据库中实际有哪些 run，各自 `run_type` 是什么
- 是否存在 scenario_replay 类型的 run，各自有多少批次

---

### Phase 1：原始文档与设计文档对齐基线

**目标**：先判断文档本身是否有冲突，再进入实现评估。

必须输出：
1. 冻结文档核心规则清单
2. UI_v2 页面语义清单与页面主语基线表
3. 文档冲突登记表

**检查点**：
- 对象主语是否统一为 `Cell / BS / LAC`
- 生命周期与健康状态是否严格分离
- 三类资格是否定义为独立概念（不等同于主状态）
- 初始化与增量是否被规定为同一治理语义下的两种入口
- `/flow/snapshot` 在设计文档中要求的是"初始化后 + 时间点 A + 时间点 B"，还是其他结构
- LAC / BS / Cell 三张画像页的资格表达是否在设计文档中被区分

---

### Phase 2：数据流程与快照机制基线

**目标**：确认真实数据链路是否支撑文档语义。

必须输出：
1. `run / batch / batch_snapshot` 数据语义表（设计要求 vs 实际数据）
2. 初始化与 2 小时增量流程图对照
3. baseline 冻结语义核查表
4. scenario / timepoint 模型核查表
5. 原始数据 → 标准化 → 四分流 → 对象状态 → baseline 链路说明

**需要通过代码阅读确认**：
- 查阅 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql`：batch_snapshot 是真实治理结果还是合成估算
- 查阅 `rebuild3_meta.batch` 实际字段与行数
- 查阅 `rebuild3_meta.batch_snapshot` 是如何写入的
- `rebuild3_meta.v_flow_snapshot_timepoints` 视图的定义

**检查点**：
- 当前批次是否只参考上一版冻结 baseline
- `batch_snapshot` 是否真的记录每个批次完成后的真实状态，还是临时拼装
- scenario replay 数据是否来自真实治理链路执行，还是用全量对象比例估算
- 是否存在不同 run 类型的数据被混用的情况

---

### Phase 3：页面语义合约基线

**目标**：逐页确认"这个页面应该回答什么问题"，以及当前实现是否回答了。

必须覆盖以下所有路由：
- `/flow/overview`
- `/flow/snapshot`
- `/runs`
- `/objects`
- `/observation`
- `/anomalies`
- `/baseline`
- `/compare`
- `/profiles/lac`
- `/profiles/bs`
- `/profiles/cell`
- `/initialization`
- `/governance`

每页必须输出：
1. 页面主问题（来自 UI_v2）
2. 页面主对象
3. 主状态 / 资格 / 解释字段分层
4. 设计要求的交互与筛选
5. 空状态 / 数据不足状态要求
6. 依赖的 API 与表
7. 是否需要 scenario 选择
8. 是否需要时间点选择

**核心检查点**（逐页必查）：
- **页面主语是否正确**：API 实际返回的 `run_id` / `batch_id` 是什么 run 类型（通过阅读后端代码确认）
- **delta / 趋势的基线是否与设计要求一致**
- **是否存在 fallback 数据冒充真实数据**（查代码里是否有 `FULL_BATCH_ID`、`SAMPLE_BATCH_ID`、`fallback` 等硬编码）
- **空状态是否诚实**（数据不足时页面是进入空状态，还是切换到其他伪逻辑）

---

### Phase 4：API / 字段 / 边界基线

**目标**：逐项确认字段定义、来源与边界。

必须输出字段映射表，至少覆盖以下字段：

| 字段 | 你需要确认的内容 |
|---|---|
| `lifecycle_state` | 来源表、主状态层级、页面用途 |
| `health_state` | 来源表、与 lifecycle_state 的严格分离方式 |
| `existence_eligible` | 是否被错误用于替代主状态 |
| `anchorable` | LAC/BS/Cell 各页的表达方式是否区分 |
| `baseline_eligible` | 哪些页面展示、是否被错误抬升 |
| `region_quality_label` | 是否直接返回技术码，是否有人类标签映射 |
| `classification_v2` | 来源表是否确实为 r2_full_profile_bs，还是其他 |
| `gps_confidence` | live schema 中是否真实存在，还是被其他字段替代 |
| `signal_confidence` | live schema 中是否真实存在，还是空列 |
| `compare_membership` | 是否被错误用于 baseline diff，而不是对比参考 |
| 四分流字段 | 是否来自真实 rebuild3.fact_* 表，还是 synthetic 估算 |
| `data_origin` | 是否存在，各 API 是否正确标识 real/synthetic/fallback |

每个字段必须回答：
- 文档定义（来自哪个 Tier 文档）
- 所属层级（主状态 / 资格 / 解释层 / 参考层）
- 允许出现在哪些页面
- 不允许被哪些页面用作主判断
- API 字段名（通过阅读后端代码确认）
- 表/视图来源（通过阅读 SQL 查询确认）
- 空值规则
- fallback 规则
- **当前实现是否与文档一致**

**检查点**：
- 是否有旧字段冒充新语义（如 gps_quality 被命名为 gps_confidence）
- 是否有字段在 live schema 中根本不存在
- 是否有 fallback 未明确标识
- 是否有边界模糊导致多轮跑偏的字段

---

### Phase 5：真实运行验证基线

**目标**：用真实页面访问 + 截图验证关键链路，不只停留在代码推断。

**验证工具：使用 Antigravity 浏览器插件访问页面并截图。**
本系统为桌面 Web，前端地址从 `rebuild3/docs/runtime_startup_guide.md` 确认（通常为 `http://127.0.0.1:47122`）。

**截图保存目录**：所有截图统一保存到 `docs1/claude_reaudit/`（如目录不存在请先创建），文件名格式为 `<路由名称>.png`，例如 `flow-snapshot.png`、`runs.png`。

**验证步骤**：

1. **每个关键 API 的实现核查**（代码阅读）：
   - 阅读对应 `rebuild3/backend/app/api/*.py` 文件
   - 确认读取的是哪个表、哪个 ID（是否有 `FULL_BATCH_ID`、`SAMPLE_BATCH_ID` 等硬编码）
   - 确认返回字段是否与文档口径一致

2. **SQL / 存储过程核查**（代码阅读）：
   - 阅读 `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql`
   - 确认 batch_snapshot 写入逻辑：是真实治理结果还是估算拼装
   - 确认百分比计算逻辑：是否存在累计值与单批输入的混用

3. **数据库状态核查**（如工具允许执行 SQL）：
   - 查询 `rebuild3_meta.run` 确认实际 run_type 分布
   - 查询 `rebuild3_meta.batch` 行数与 scenario_key 分布
   - 查询 `rebuild3_meta.batch_snapshot` 行数，验证是否是真实逐批写入

4. **页面真实渲染验证**（使用 Antigravity 浏览器插件）：
   - 打开 `/flow/snapshot`，截图保存到 `docs1/claude_reaudit/flow-snapshot.png`，核查：
     - 场景下拉是否混入 full init；label 是否有重名
     - 百分比数字是否在合理范围（超过 100% 即异常）
   - 打开 `/flow/overview`，截图，核查页面 context bar 显示的是哪个 run_id
   - 打开 `/runs`，截图，核查批次列表主语（是 run 级条目还是 sample/full 两行）
   - 打开 `/baseline`，截图，核查 diff 来源（版本差异还是 rebuild2 对照）
   - 打开 `/initialization`，截图，核查 run_id 主语（是否为 SAMPLE 类型）
   - 打开 `/compare`，截图，核查首屏是否有 fallback banner
   - 打开 `/governance`，截图，核查首屏是否有 fallback banner
   - 打开 `/profiles/lac`，截图，核查区域质量标签是否直接显示技术码
   - 打开 `/profiles/bs`，截图，核查参考列是否有 gps_confidence 等错误命名

5. **前端消费逻辑核查**（代码阅读）：
   - 阅读各 `.vue` 文件，确认是否消费了 `data_origin` 字段
   - 确认 fallback banner 是否已实现
   - 确认是否存在把 `gps_quality` 展示为 `gps_confidence` 列的情况

**检查点**：
- 至少对 `/flow/snapshot`、`/flow/overview`、`/runs`、`/baseline`、`/initialization`、`/compare`、`/governance`、`/profiles/lac`、`/profiles/bs` 进行截图
- 所有截图保存至 `docs1/claude_reaudit/` 目录
- 检查 `/compare`、`/governance` 首屏是否有可见 fallback 提示
- 检查 BS / Cell / LAC 画像页的字段名与实际来源

---

### Phase 6：偏差登记、优先级与实施基线

**目标**：形成不会再次跑偏的最终结论和实施队列。

必须输出：
1. P0 / P1 / P2 / P3 问题清单（每条需含完整证据链：文档 → API → 代码 → 数据）
2. 文档冲突清单
3. 字段口径冲突清单
4. 页面主语偏差清单
5. 数据链路缺口清单
6. 本轮必须修 / 可后移 / 可优化的三段式队列
7. 禁止再次默认假设清单

**优先级定义**：
- **P0**：页面展示的信息与真实业务语义完全相反，或阻断用户理解系统状态的问题
- **P1**：页面主语错误，或关键 API 返回的数据口径与文档定义不一致
- **P2**：字段名或表达层存在误导，但主语基本正确
- **P3**：细节问题，用户体验影响小，不影响主语和核心语义

---

## 五、必审范围

### 页面层（13 个路由全量覆盖）

- `/flow/overview`：当前批次概览
- `/flow/snapshot`：时间点快照对比
- `/runs`：运行 / 批次中心
- `/objects`：对象浏览
- `/observation`：观察工作台
- `/anomalies`：异常工作台
- `/baseline`：基线画像
- `/compare`：验证对照
- `/profiles/lac`：LAC 画像
- `/profiles/bs`：BS 画像
- `/profiles/cell`：Cell 画像
- `/initialization`：初始化数据
- `/governance`：数据治理目录

### API 层（逐个核查）

- 字段名与类型（通过后端代码）
- 字段来源（读哪张表）
- 是否主字段或解释字段
- 是否存在 fallback 且未标识
- 是否用旧字段冒充新语义

### 数据层（通过代码和 schema 推断）

重点核查以下表 / 视图 / 过程：
- `rebuild3_meta.run`
- `rebuild3_meta.batch`
- `rebuild3_meta.batch_snapshot`
- `rebuild3_meta.batch_flow_summary`
- `rebuild3_meta.batch_anomaly_summary`
- `rebuild3_meta.batch_baseline_refresh_log`
- `rebuild3_meta.baseline_version`
- `rebuild3_meta.v_flow_snapshot_timepoints`
- `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac`
- `rebuild3.fact_governed`、`rebuild3.fact_pending_observation`、`rebuild3.fact_pending_issue`、`rebuild3.fact_rejected`
- `rebuild3.baseline_cell`、`rebuild3.baseline_bs`、`rebuild3.baseline_lac`
- `rebuild3/backend/sql/govern/004_timepoint_snapshot_scenarios.sql`（重点核查 batch_snapshot 写入逻辑）

---

## 六、本次特别高优先的核查点

### A. `/flow/snapshot` 快照机制

必须明确回答（通过代码阅读）：

1. 后端 `run_snapshot.py` 在读取 batch_snapshot 时，这些快照数据是如何写入的（真实治理流水线还是比例估算）
2. 场景下拉里是否混入了 `full_initialization` 类型的 run
3. 场景下拉 label 是否有重名情况（如 smoke 与正式场景显示相同名称）
4. 百分比计算：是否存在分子是累计值、分母是单批输入的混用
5. 数据不足时，页面是否如实提示，还是切换成其他比较逻辑

若任一项不满足，按 P0。

### B. 画像页字段分层

必须明确回答：

1. LAC 页是否只表达 `anchorable`（资格层），未混入 BS/Cell 特有资格
2. BS / Cell 页是否区分 `anchorable` 和 `baseline_eligible`
3. `gps_confidence` / `signal_confidence` 在 live rebuild3 schema 中是否真实存在（通过查 DDL 确认）
4. `gps_quality` 是否被错误命名为 `gps_confidence` 列标题
5. `region_quality_label` 是否直接返回技术码（`coverage_insufficient`、`issue_present`），未做人类标签映射

若字段在 schema 中不存在却被页面展示，按 P1。

### C. 主流程页主语正确性

必须查阅后端代码回答：

1. `/flow/overview` 的 API 实现里，`batch_id` 是读哪个常量/变量（是否是 `FULL_BATCH_ID`）
2. `/runs` 的批次列表，是从 `rebuild3_meta.batch` 的全量数据读取，还是只读 sample/full 两个固定 ID
3. `/initialization` 的 API 实现里，`run_id` 是指向哪个 run（是否是 `SAMPLE` 类型）
4. `/baseline` 的 diff 计算，是"当前版 vs 上一版 baseline_version"，还是"rebuild3 vs rebuild2 对照"

### D. Fallback 透明性

必须检查：

1. `/compare` 和 `/governance` 后端是否明确返回 `data_origin=fallback` 或等价字段
2. `/compare` 和 `/governance` 前端是否消费并展示了 fallback 提示（banner 或标记）
3. 其他页面是否有未明确标识的 fallback 数据静默展示

---

## 七、输出格式要求

> **输出路径**：
> - 主评估报告：`docs1/Claude_reaudit_output.md`
> - 字段基线（内容较多时单独输出）：`docs1/Claude_field_baseline.md`
> - 页面截图：统一保存到 `docs1/claude_reaudit/` 子目录（如不存在请先创建），文件命名格式为 `<路由名>.png`
> - 不得将截图保存到 `docs1/` 根目录（会与原有审计截图混淆）

### 第一部分：总评结论
- 当前总评（通过 / 不通过 + 一句话说明）
- P0 / P1 / P2 / P3 数量
- 是否允许进入下一阶段实施
- 当前基线是否足够稳定

### 第二部分：阶段性交付检查
按 Phase 0 ~ Phase 6 逐项说明：
- 是否完成
- 产物是否齐全
- 是否通过检查点
- 如未通过，卡点是什么

### 第三部分：严重问题清单
每个问题必须包含：
- 严重级别（P0 / P1 / P2 / P3）
- 问题标题
- 页面 / 接口 / 表 / 文档位置
- 证据链（代码文件 + 行号 + SQL + 字段）
- 影响
- 修复建议
- 是否阻塞下一轮实施

### 第四部分：字段与边界确认表

对每个关键字段输出：

| 字段 | 文档定义 | 所属层级 | 页面用途 | API 来源 | 表来源 | 空值规则 | fallback 规则 | 当前实现一致性 |
|---|---|---|---|---|---|---|---|---|

### 第五部分：页面逐页对齐结论

对每个路由输出：
- 页面主语是否正确
- 是否回答了设计定义的问题
- 是否存在语义漂移（主语偏差 / 字段口径偏差）
- 数据链路状态
- fallback / 缓存问题
- 建议动作

### 第六部分：基线产物清单

列出本次评估产出的所有基线：
- 文档清单与分级表
- 路由清单
- 页面 → API → 表映射表
- 字段与边界确认表
- scenario / timepoint 核查表
- 页面主语偏差清单

### 第七部分：剩余工作队列

按三组输出：
- **必须立刻修**（P0 + P1）
- **本轮可延后但需登记**（P2 + 登记类 P3）
- **可以后续优化**（P3 / 长期改进）

最后附：**禁止再次默认假设清单**

---

## 八、严格禁止

- **禁止用当前实现反推设计意图**：代码与文档冲突，一律先判代码有问题
- **禁止引用 `04*` 系列 prompt 文件**：它们是历史执行指令，不是真相源
- **禁止阅读已有审计结论文档**：`reaudit_output`、`repair_task_doc` 等现有结论文件在本次评估期间不得参考
- **禁止只给结论性文字，不建立阶段基线产物**：每个 Phase 必须有可复核产物
- **禁止把性能 / 代码规模问题上升为 P0**（除非直接导致功能不可用）
- **禁止把 fallback 数据的存在当作合理状态**：fallback 必须显式标识，且不能占据页面主语位置
- **禁止因为"页面能渲染 / 接口返回 200"就判定通过**

---

## 九、最终目标

这次评估要回答的核心问题是：

**rebuild3 当前实现，是否已经在"原始冻结文档 + UI_v2 设计 + 派生修订轨迹"三层共同约束下，真正回到了设计要表达的系统语义？**

具体体现为：
1. 所有主流程页面（`/flow/overview`、`/flow/snapshot`、`/runs`）的主语是否指向真实对象
2. `batch_snapshot` 是否是真实治理快照，而不是合成估算
3. fallback 数据是否全部已显式标识，且不再占据主语位置
4. 字段名与实际数据来源是否一致（不存在以名盖实）
5. 空状态是否诚实展示（数据不足时提示，不切换成伪逻辑）

如果没有，请明确指出偏离点，并给出基于代码证据链的修复优先级，不要给出模糊的通过结论。
