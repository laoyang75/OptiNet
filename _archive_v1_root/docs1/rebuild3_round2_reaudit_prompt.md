# rebuild3 第二轮彻底复评 Prompt

你现在不是来做一次“页面冒烟检查”或“补丁回看”，而是来做一次重新开题的系统级深度评估。

你的任务不是证明当前实现“基本可用”，而是确认：

- 当前系统是否真正遵守了 rebuild3 冻结的原始业务语义
- 当前 UI 是否真正对齐了 UI_v2 的人类最终设计意图
- 当前 API、数据库、字段、边界、fallback、缓存、快照机制是否真的支撑这些语义
- 当前实现中是否仍然存在“能跑但主语错了 / 有值但口径错了 / 看起来像对齐其实已经偏航”的严重问题

如果发现设计语义偏差、业务口径偏差、字段来源漂移或边界未落实，必须直接按问题记录，不能因为页面能渲染、接口返回 200、或者已有 fallback 就判定通过。

---

## 一、你的角色

你是 rebuild3 项目的系统级复评者。你必须同时站在 4 个层面审计：

1. 原始冻结文档层：系统本来应该是什么
2. UI_v2 设计层：页面最后应该怎么向人表达
3. 派生实施文档层：后续 prompt、整改文档、审计文档有没有跑偏
4. 当前实现层：代码、API、SQL、真实数据、真实页面到底做成了什么

你必须先完成“文档与基线对齐”，再评估实现。禁止跳过文档阶段直接看代码。

---

## 二、真相源优先级（必须遵守）

### Tier 0：原始冻结文档，定义系统底层语义
以下三份是最上游真相源，必须最先阅读、最先冻结：

- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
- `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
- `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`

它们定义的是：

- 系统主语
- 生命周期与健康状态
- 三类资格边界
- 初始化与 2 小时增量的统一语义
- 四分流与 baseline 冻结逻辑
- SQL-first / Postgres-first / Vue3+TS+Vite / FastAPI 等技术边界

### Tier 1：UI_v2 设计，定义人类最终对齐的页面表达
以下文档定义的是最终页面要回答的问题、页面布局与设计表达：

- `rebuild3/docs/UI_v2/design_notes.md`
- `rebuild3/docs/UI_v2/index.html`
- `rebuild3/docs/UI_v2/design_system.html`
- `rebuild3/docs/UI_v2/pages/*.html`
- `rebuild3/docs/UI_v2/pages/*_doc.md`

规则：

- 页面主语、用户问题定义、布局、信息层次，以 UI_v2 为准
- 但如果 UI_v2 某个局部表达和 Tier 0 冻结文档冲突，必须显式记录冲突来源，不能自行脑补解决
- 页面显示策略以 UI_v2 为准，底层业务/数据口径以 Tier 0 为准

### Tier 2：派生与整改文档（按需查，遇到问题再读）

以下文档不需要全量预读，遇到具体问题时按需查找，避免一次性读入过多内容导致执行偏差：

**整改结论文档（遇到字段/页面问题时查）：**
- `rebuild3/docs/00_审核结论.md` — 文档冲突裁决，两套文档差异收敛结论
- `rebuild3/docs/ui_final_rectification_report.md` — 上轮 UI 修复报告，含已修/未修问题记录

**接口与参数定义（遇到 API/字段/阈值问题时查）：**
- `rebuild3/docs/api_models.md` — API 字段约定
- `rebuild3/docs/param_matrix.md` — 参数边界定义（资格阈值等）

**启动运行（Phase 5 验证时查）：**
- `rebuild3/docs/runtime_startup_guide.md` — 本地启动说明

**其他补充（仅在前述文档无法解答时查）：**
- `docs1/rebuild3_round2_execution_note.md`
- `docs1/rebuild3_snapshot_rerun_plan.md`

> ⚠️ `rebuild3/docs/` 下所有 `04*` 系列文件（`04_`、`04a_`、`04b_`、`04c_`、`04d_`、`04e_`、`04f_`）均为历史 prompt，属于多次 agent 迭代的指令文件，**不是设计基线**，禁止作为真相源引用。
> `ui_restructure_prompt.md` 和 `ui_restructure_audit_prompt.md` 同属历史 prompt，忽略。

### Tier 3：当前代码、API、数据库与真实数据
当前代码不是设计来源，只能作为被审对象：

- 前端页面、组件、状态管理
- FastAPI 路由与读模型装配
- SQL schema / procedure / runner
- PostgreSQL 真实表、视图、索引、约束
- 实际运行出的 scenario / run / batch / snapshot 数据

如果代码与文档冲突，一律先判定代码为问题；只有在文档之间互相冲突时，才进入“文档冲突记录”流程。

---

## 三、评估原则（必须遵守）

### 1. 先做文档基线，再看实现
不得跳过文档归一化。必须先回答：

- 系统究竟要解决什么问题
- 每个页面究竟要回答什么问题
- 每个状态 / 字段 / 资格 / 分流 / baseline 的正式含义是什么
- 初始化和增量的关系究竟如何定义

### 2. 不接受“近似正确”
以下都不能算通过：

- 用 `sample / full / baseline` 近似时间快照
- 用 fallback 聚合或说明文案冒充真实字段
- 用现成共享组件硬套不同页面的不同语义
- 用“数据暂时不足”掩盖页面主语错误
- 用当前实现反推设计意图
- 用缓存结果掩盖底层字段错误

### 3. 必须重查字段与边界
对所有关键字段，都必须重新确认：

- 页面用途
- API 字段名与类型
- 数据表来源
- 是否为主判断字段
- 空值规则
- fallback 规则
- 是否允许被 UI 升格为主状态
- 是否存在由多个字段拼出来的伪语义

### 4. 必须建立全程基线，避免再次跑偏
本次评估不是一次性结论，而是一个带基线、带阶段产物、带检查点的过程。每个阶段都必须生成可复核的产物，不能只给口头总结。

### 5. 初始化场景核查

本阶段核心目的是跑通流程、确认功能设计被有效执行，而不是深度数据验证。两套初始化场景（如 `1天初始化` 和 `2天初始化`）是为了验证多场景选择功能，**如果数据库中只存在一套场景，不视为阻断问题**，记录为“多场景切换功能待验证”并继续。

需要确认的核心功能点：

- UI 是否提供场景选择入口（能选一套说明功能存在）
- 页面是否区分“场景选择”与“场景内时间点选择”
- 是否存在把不同场景的数据混成同一条时间线的错误
- 如果存在两套场景，确认它们是否都写入 `run / batch / batch_snapshot` 并可独立选择

---

## 四、必须先产出的基线文件与检查点

你在正式给问题列表之前，必须先建立以下基线产物。若其中任一步没有完成，不得进入下一阶段。

### Phase 0：资料盘点与真相源分级基线

目标：确认所有有效文档、页面、路由、API、表、关键脚本都已进入审计范围。

必须输出：

1. 文档清单与分级表
2. 路由清单
3. 页面 -> 设计稿映射表
4. 页面 -> API 映射表
5. API -> 表/视图 映射表
6. 场景/运行数据基线（有哪些 scenario / run / batch / snapshot）

检查点：

- 三份冻结原始文档是否已读完并提炼出正式规则
- UI_v2 页面文档是否已全部纳入
- 派生文档是否已按“有效 / 历史 / 重复”分类
- 当前系统中是否确实存在两套初始化场景，并可定位到真实 `run_id`

### Phase 1：原始文档与设计文档对齐基线

目标：先判断文档本身有没有冲突，再进入实现评估。

必须输出：

1. 冻结文档核心规则清单
2. UI_v2 页面语义清单
3. 文档冲突登记表
4. 页面主语基线表

检查点：

- 对象主语是否统一为 `Cell / BS / LAC`
- 生命周期与健康状态是否严格分离
- 三类资格是否明确定义为独立概念
- 初始化与增量是否被明确规定为同一治理语义下的两种入口
- `/flow/snapshot` 是否在设计文档中明确要求“初始化后 + 时间点 A + 时间点 B”
- `LAC / BS / Cell` 三张画像页的资格表达是否在设计文档中被区分

### Phase 2：数据流程与快照机制基线

目标：确认真实数据链路是否支撑文档语义。

必须输出：

1. `run / batch / batch_snapshot` 数据语义表
2. 初始化与 2 小时增量的流程图对照
3. baseline 冻结语义核查表
4. scenario/timepoint 模型核查表
5. 原始数据 -> 标准化 -> 四分流 -> 对象状态 -> baseline 的链路说明

检查点：

- 当前批次是否只参考上一版冻结 baseline
- batch 是否区分 `init` 与 rolling timepoint
- 是否记录 `scenario_key / scenario_label / init_days / step_hours / batch_seq / timepoint_role / snapshot_at`
- `batch_snapshot` 是否真的记录每个批次完成后的快照，而不是页面临时拼装
- 两套初始化场景是否都能形成完整时间线
- scenario 选择与 timepoint 选择是否在数据层上可区分

### Phase 3：页面语义合约基线

目标：逐页确认“这个页面应该回答什么问题”。

必须覆盖以下路由：

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

1. 页面主问题
2. 页面主对象
3. 页面主状态 / 资格 / 解释字段分层
4. 设计要求的交互与筛选
5. 空状态 / 错误状态 / 数据不足状态
6. 依赖的 API 与表
7. 是否需要 scenario 选择
8. 是否需要时间点选择

检查点：

- 页面是否回答了设计定义的问题，而不是相似问题
- 是否存在把解释字段抬升成主状态的情况
- 是否存在共享组件抹平页面差异的情况
- 是否存在字段名正确但含义错误的情况

### Phase 4：API / 字段 / 边界基线

目标：逐项确认字段定义、来源与边界。

必须输出字段映射表，至少覆盖：

- `lifecycle_state`
- `health_state`
- `existence_eligible`
- `anchorable`
- `baseline_eligible`
- `region_quality_label`
- `classification_v2`
- `gps_confidence`
- `signal_confidence`
- `compare_membership`
- 四分流字段：
  - `fact_governed`
  - `fact_pending_observation`
  - `fact_pending_issue`
  - `fact_rejected`

每个字段都必须回答：

- 字段定义
- 来源文档
- 所属层级（主状态 / 资格 / 解释层 / 参考层）
- 允许出现在哪些页面
- 不允许被用于哪些页面主判断
- API 字段名
- 表/视图来源
- 空值规则
- fallback 规则
- 当前实现是否一致

检查点：

- 是否有旧字段冒充新语义
- 是否有多个字段在 UI 中被拼成未定义状态
- 是否有 fallback 未明确标识
- 是否有边界未写清导致多轮跑偏

### Phase 5：真实运行验证基线

目标：用真实代码、真实 API、真实 DB、真实页面验证，不接受纯静态推断。

**验证工具：使用 Playwright MCP 进行页面访问与截图对比。禁止使用 Chrome DevTools MCP。**

本系统为桌面 Web，无需进行移动端或窄屏适配验证。

必须验证：

1. 场景选择功能是否可用（至少一套场景可选）
2. `/flow/snapshot` 是否支持“先选场景，再选场景内时间点 A/B”
3. 真实页面渲染是否与 UI_v2 设计一致（Playwright 截图 + 核对）
4. 关键 API 是否返回真实字段而非 fallback
5. 数据不足时，页面是否如实提示，而不是静默降级

检查点：

- 至少验证一个 smoke 场景（系统启动、场景可选、页面可渲染）
- 至少验证 `/flow/snapshot`、`/runs`、`/flow/overview`、`/profiles` 之一的场景切换
- 至少用 Playwright 对核心页面截图，与 UI_v2 进行布局核对
- 如发现性能明显异常可记录，但不作为主线评估项

### Phase 6：偏差登记、优先级与实施基线

目标：形成不会再次跑偏的最终结论和实施队列。

必须输出：

1. P0 / P1 / P2 / P3 问题清单
2. 文档冲突清单
3. 字段口径冲突清单
4. 页面主语偏差清单
5. 数据链路缺口清单
6. 性能 / 代码规模问题清单
7. 本轮必须修 / 可后移 / 可优化 的三段式队列
8. 下一轮实施前的“禁止假设清单”

检查点：

- 是否已经明确哪些问题是语义错、哪些是数据错、哪些是实现错、哪些是设计冲突
- 是否已经为每个严重问题给出证据链：文档 -> API -> DB -> 页面
- 是否已经形成新的基线，足以支撑下一轮实施不再偏航

---

## 五、必审范围

### 页面层
逐页检查以下路由：

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

### API 层
逐个确认页面对应 API 的：

- 字段名
- 字段类型
- 字段来源
- 是否主字段或解释字段
- 是否存在 fallback
- 是否存在用旧字段冒充新语义
- 是否需要 scenario 选择与 timepoint 选择

### 数据层
必须复核以下表 / 视图 / 过程 / 脚本的真实含义与使用方式：

- `rebuild3_meta.run`
- `rebuild3_meta.batch`
- `rebuild3_meta.batch_snapshot`
- `rebuild3_meta.batch_flow_summary`
- `rebuild3_meta.batch_anomaly_summary`
- `rebuild3_meta.batch_baseline_refresh_log`
- `rebuild3_meta.baseline_version`
- `rebuild3_meta.v_flow_snapshot_timepoints`
- `rebuild3.obj_cell`
- `rebuild3.obj_bs`
- `rebuild3.obj_lac`
- `rebuild3.fact_governed`
- `rebuild3.fact_pending_observation`
- `rebuild3.fact_pending_issue`
- `rebuild3.fact_rejected`
- `rebuild3.baseline_cell`
- `rebuild3.baseline_bs`
- `rebuild3.baseline_lac`
- `rebuild3/backend/sql/schema/*.sql`
- `rebuild3/backend/sql/govern/*.sql`
- `rebuild3/backend/scripts/run_timepoint_snapshot_scenarios.py`
- `rebuild3/backend/scripts/start_timepoint_snapshot_scenarios.sh`

---

## 六、本轮特别高优先的核查点

### A. `/flow/snapshot` 是否真的回到设计原意
你必须明确回答：

1. 页面现在是否真的是“初始化完成后 + 时间点 A + 时间点 B”
2. 页面是否先选场景，再选该场景下的时间点
3. 场景 A 与场景 B 是否可切换，且不会互相混淆
4. 时间点是否来自同一 `run` 下真实 `batch timepoint`
5. 是否还有任何 `sample / full / baseline` 伪时间语义残留
6. `batch_snapshot` 是否真的是页面底座，而不是临时映射
7. 数据不足时，页面是否如实提示“时间点不足”，而不是切换成别的比较逻辑

若任一项不满足，按 P0。

### B. 画像页资格列是否真正按页面区分
你必须明确回答：

1. LAC 是否只表达 `anchorable`
2. BS / Cell 是否表达 `anchorable + baseline_eligible`（若含 `existence_eligible`，需确认是否在冻结文档中有定义）
3. 是否还有共享组件导致的语义混用
4. 资格是否被错误提升为生命周期或健康状态替代品

> ⚠️ 如果 BS/Cell 各自的资格字段在冻结文档中未明确区分定义，须反查 rebuild2 中的同类字段策略，记录为“字段边界待确认”，不能自行推断。

若任一项不满足，按 P1；若导致主状态误判，按 P0。

### C. 所有字段与边界重新确认
必须重新确认至少以下边界：

- `lifecycle_state`
- `health_state`
- `existence_eligible`
- `anchorable`
- `baseline_eligible`
- `region_quality_label`
- `classification_v2`
- `gps_confidence`
- `signal_confidence`
- `compare_membership`
- 四分流字段

要求回答：

- 哪些是主状态
- 哪些是资格
- 哪些是解释层
- 哪些页面允许展示
- 哪些页面不允许上升为主判断

### D. 重新检查 fallback、缓存与伪对齐
你必须显式检查：

- 哪些 API 仍然返回 fallback 数据
- 哪些页面仍然显示说明型占位而不是真实字段
- 哪些缓存掩盖了底层数据错误或延迟同步问题
- 哪些“差不多”的映射实际上改变了问题定义

任何偷偷 fallback 且未明确标示的情况，至少 P1。

### E. 结构健康（性能非主线）

性能优化与代码规模不是本轮核心需求。如在评估过程中发现明显异常（如页面无响应、接口超时），可作为参考项记录，**不纳入阻断评估，不占用主线时间**。

可选记录项：

- 如发现某接口明显缓慢（>5s），记录接口名与耗时即可
- 如发现单文件异常巨大影响可读性，可备注，不作 P 分级

---

## 七、评估方法要求

### 1. 同时做四层映射
每个关键问题都必须至少建立一次：

文档 -> 页面 -> API -> 表/视图/过程 -> 规则

不能只停留在截图或 JSON。

### 2. 必查边界场景
至少检查：

- 无后续时间点
- 只有 1 个后续时间点
- 有多个后续时间点
- 有两个不同初始化场景
- rerun 批次
- 空结果
- 大分页
- 移动端窄屏
- 表格窄列
- 解释字段为空
- baseline 不刷新
- baseline 刚刷新后的下一批次

### 3. 必须验证真实数据，不只看静态代码
优先通过以下证据确认：

- 实际 API 返回
- 实际数据库行
- 实际页面渲染
- 实际运行出来的 `run / batch / snapshot`

不能只写“我猜这个字段应该没问题”。

### 4. 遇到文档冲突时的处理方式
如果 Tier 0 与 Tier 1 / Tier 2 有冲突，必须：

1. 记录冲突位置
2. 明确冲突影响
3. 给出默认裁决规则：
   - 页面设计语义优先参考 UI_v2
   - 底层业务 / 数据口径优先参考冻结原始文档
4. 不得无记录地自行二次解释

---

## 八、输出格式要求

> **输出路径**：所有基线产物和评估产物统一写入 `docs1/rebuild3_round2_reaudit_output.md`，按部分分节。字段基线表如内容较多可单独输出到 `docs1/rebuild3_field_baseline.md`。

### 第一部分：总评结论
直接给出：

- 当前总评
- P0 / P1 / P2 / P3 数量
- 是否允许进入下一阶段实施
- 当前基线是否已经足够稳定

### 第二部分：阶段性交付检查
按 Phase 0 ~ Phase 6 逐项说明：

- 是否完成
- 产物是否齐全
- 是否通过检查点
- 如未通过，卡点是什么

### 第三部分：严重问题清单
每个问题必须包含：

- 严重级别
- 问题标题
- 页面 / 接口 / 表 / 文档位置
- 证据链
- 影响
- 修复建议
- 是否阻塞下一轮实施

### 第四部分：字段与边界确认表
至少输出一张表，明确：

- 字段名
- 文档定义
- 所属层级（主状态 / 资格 / 解释层 / 参考层）
- 页面用途
- API 来源
- 表来源
- 空值规则
- fallback 规则
- 当前实现是否一致

### 第五部分：页面逐页对齐结论
每页必须给出：

- 页面是否回答了设计定义的问题
- 是否仍有语义漂移
- 是否还有未完成的数据链路
- 是否依赖错误 fallback / 缓存 / 假聚合
- 是否需要继续拆分组件 / API / SQL

### 第六部分：基线产物清单
明确列出本轮产出的基线清单，包括但不限于：

- 文档清单与分级表
- 文档冲突登记表
- 页面主语基线表
- 页面 -> API -> 表映射表
- 字段与边界确认表
- scenario / timepoint 核查表
- 速度与代码规模基线

### 第七部分：剩余工作队列
按以下三组输出：

- 必须立刻修
- 本轮可延后但需登记
- 可以后续优化

并在最后附上“禁止再次默认假设”的清单。

---

## 九、严格禁止

以下是正文原则中逻辑隐含但需要显式强调的禁止项：

- **禁止用当前实现反推设计意图**：如果代码和文档冲突，一律先判代码有问题
- **禁止引用 `04*` 系列 prompt 文件作为设计依据**：它们是历史执行指令，不是真相源
- **禁止使用 Chrome DevTools MCP**：页面验证统一使用 Playwright MCP
- **禁止只给问题清单，不建立阶段基线产物**：每个 Phase 必须有可复核的产物文件
- **禁止把不同场景的数据混成同一条时间线**
- **禁止把性能、代码规模问题上升为阻断评估的 P0 问题**（除非直接导致功能不可用）

---

## 十、最终目标

这次评估不是为了“找几个 bug”，而是为了回答一个更重要的问题：

**rebuild3 当前实现，是否已经在“原始冻结文档 + UI_v2 设计 + 派生修订轨迹”三层共同约束下，真正回到了设计要表达的系统语义上。**

如果没有，请明确指出偏离点，并给出基于证据链的修复优先级，不要给出模糊的通过结论。
