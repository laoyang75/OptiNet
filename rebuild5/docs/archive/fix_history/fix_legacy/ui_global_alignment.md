# UI 全局语义对齐审计

> 审计目标：先建立 `rebuild5` 的 UI 语义基线，不直接做大规模页面改动。  
> 审计依据：`README`、`docs/00_全局约定.md`、`docs/02-06`、`docs/human_guide/00/02/03/04/05`、`ui/*.md`、`frontend/design/src/views/*`、`frontend/design/src/api/*`、`backend/app/routers/*`、`backend/app/service_query/queries.py`。

## 当前判断基线

1. UI 首先要表达“对象是什么、现在处于什么阶段、能被拿来做什么”，而不是直接暴露实现字段名。
2. 管理 / 治理页面可以保留少量术语精度，但必须以中文业务语义为主，代码名只能做辅注。
3. 服务层页面面向业务用户，应优先表达“位置、覆盖、质量、可用性”，弱化治理链路内部术语。
4. 同一个词在不同页面必须只表达一种意思，尤其要分清：
   - 生命周期状态 vs 资格
   - 分流路径 vs 质量等级
   - 维护分类 vs 服务层可见标签
   - 正式库 / 可信库 vs 冻结快照

## 核心结论

### 当前 UI 最大的问题

当前 UI 最大的问题不是单个词写错，而是**同一业务对象被多套命名同时描述**：既有旧实现词（`active`）、又有接口词（`anchor_eligible` / `baseline_eligible` / `donor`）、又有页面词（流转 / 评估 / 画像 / 维护 / 正式库），导致用户很难稳定回答下面三个问题：

- 这个对象现在处于什么阶段？
- 它能不能被拿去补数或刷新基线？
- 这是治理视角的术语，还是业务查询视角的术语？

### 最需要先统一的 5 个表达

1. `active` 与 `qualified` 的映射，彻底停止在 UI 中出现 `Active`。
2. Step 1“补齐”和 Step 4“补数”的边界，避免两个页面都用“补齐率”。
3. `donor` / `source cell` / “补数来源”的统一命名。
4. 服务层页面对 `锚点资格`、`基线资格`、`qualified+`、`excellent` 等治理术语的暴露方式。
5. 全局版本条里“运行批次 / 引用快照 / 当前快照 / 发布版本 / 页面状态”的统一写法。

### 可后置处理的部分

- 导出 CSV 的字段中文化。
- 各类 tooltip / 辅助说明的细腻打磨。
- 开发层接口字段是否改名；这可以放到后续 API 收敛阶段处理。
- `结果库`、`正式库`、`运营商基站数据库` 在开发文档中的进一步分层命名。

## 术语 / 表达对齐表

| 当前表达 | 问题 | 建议表达 | 适用页面 | 状态 |
|----------|------|----------|----------|------|
| `数据集选择`（导航 / 文档） vs `当前数据集`（页头） | 同一页面前后不一致；而且当前实现并不支持真正“选择”，容易让用户误以为可在线切换 | 见 `ui_alignment_questions.md` Q1；在拍板前至少统一加上“单活 / 只读”提示 | 全局管理：`ui/02_数据集与运行管理.md`、`frontend/design/src/views/global/DatasetSelect.vue` | 待决策 |
| `批次`、`运行`、`发布`、`快照`、`当前 / 引用` 在不同页面随意切换 | 用户无法稳定分辨“这页看的到底是运行批次、引用快照，还是发布版本” | 全局统一成：`数据集` / `运行批次` / `引用快照` / `当前快照`；服务层再单独标 `当前发布版本` / `发布批次` | 顶栏、Step 2-6 页头、服务层页头：`AppLayout.vue`、`BatchSelector.vue`、各页面 `PageHeader` | 已确认（建议直接执行） |
| `完整运行`、`参数重跑` 等页面词与文档里的 `日常运行 / 初始化 / 局部重算 / 完整回归 / 对比验证` 不一致 | 运行历史页承载控制侧链，但当前类型体系仍带实现色彩，追溯与文档对不上 | 见 `ui_alignment_questions.md` Q2；建议 UI 主表达使用文档口径，代码值做辅注 | 全局管理：`frontend/design/src/views/global/RunHistory.vue`、`docs/07_数据集选择与运行管理.md`、`docs/09_控制操作_初始化重算与回归.md` | 待决策 |
| Step 1 页面叫“补齐”，Step 4 页面统计也写“补齐率” | Step 1 是同报文结构性字段补齐，Step 4 是历史可信知识补数；两者不能混叫 | Step 1 固定为`字段补齐（同报文）`；Step 4 固定为`知识补数`；只在 Step 1 使用`补齐率`，Step 4 改为`补数率` | ETL `Fill.vue`、Step 4 `KnowledgeFill.vue`、相关 UI 文档 | 已确认（建议直接执行） |
| `路由` 与 `分流` 混用 | Step 2 页面是业务分流，不是技术路由表；同一导航里出现“基础画像与路由 / 基础画像与分流”会造成漂移 | UI 主表达统一为`基础画像与分流`；`routing` 仅保留在接口 / 代码路径中 | Step 2：`AppLayout.vue`、`router/index.ts`、`Routing.vue`、`ui/04_基础画像与分流页面.md` | 已确认（建议直接执行） |
| `Path A/B/C` 直接作为卡片主表达 | 对熟悉系统的人可读，对首次进入治理页的用户不够自解释 | 首次出现统一写成`路径 A（命中可信库）`、`路径 B（进入评估）`、`路径 C（丢弃）`；次级位置可缩写为 A/B/C | Step 2：`Routing.vue`、`docs/02_基础画像.md`、`human_guide/02_Step2_基础画像与分流.md` | 已确认（建议直接执行） |
| `碰撞 cell_id`、`碰撞候选`、`碰撞` 不区分 ID 冲突与空间碰撞 | Step 2 的 ID 碰撞防护与 Step 5 的空间碰撞是两类问题；现在都被叫“碰撞”，会误导原因判断 | Step 2 固定叫`ID 碰撞防护`；Step 5 Cell 维护里的 `collision` 固定叫`空间碰撞`或`碰撞小区` | Step 2 `Routing.vue`，Step 5 `CellMaintain.vue`、`GovernanceOverview.vue`，相关文档 | 已确认（建议直接执行） |
| `流转总览`声称看三层对象，但“变动对象”表只展示 Cell 变动 | 页面标题范围比表格范围大，容易让用户以为 BS/LAC 也在下面同表展示 | 若短期只保留 Cell diff，表头改成`Cell 变动样本`；若后续补齐三层，再改成`对象变动样本` | Step 3：`FlowOverview.vue`、`ui/05_流转评估页面.md` | 已确认（建议直接执行） |
| 生命周期状态在筛选器、图例、规则卡中直接显示 `excellent / qualified / observing / waiting` | 管理页也应先给中文含义，否则用户在同页同时看到中文状态标签和英文 code，认知负担高 | 管理 / 治理页统一“中文主标签 + 英文 code 辅注”；例如`合格（qualified）` | Step 3、配置页：`CellEval.vue`、`BSEval.vue`、`LACEval.vue`、`PromotionRules.vue` | 已确认（建议直接执行） |
| Step 5 维护页出现 `Active` / `Observing` / `Waiting`，并用 `active` 统计摘要 | `active` 是旧实现术语，`docs/00_全局约定.md` 已明确映射为 `qualified`；继续显示 `Active` 会直接误导状态体系 | 生命周期摘要统一使用`合格` / `观察` / `等待`；若统计的是窗口内活跃对象，写`窗口内活跃`，不要简写成 `Active` | `BSMaintain.vue`、`LACMaintain.vue`、可能受影响的维护统计区 | 已确认（最高优先级） |
| `锚点资格 (anchor_eligible)`、`基线资格 (baseline_eligible)` 直接作为主标题 | 资格概念是核心语义，但当前页面经常把中文和代码名混在一层；用户难以知道代码名只是字段名 | 治理 / 配置页统一写`锚点资格`、`基线资格`，代码名放括号或 tooltip，不放主卡片大标题 | `PromotionRules.vue`、`CellEval.vue`、`BSMaintain.vue`、`LACMaintain.vue`、`CellMaintain.vue` | 已确认（建议直接执行） |
| 服务层页面直接暴露`可信锚点`、`基线资格`、碰撞 / 多质心等治理字段 | Step 6 面向业务用户，当前表达把治理链路内部字段直接推到业务侧，违反“弱化治理术语”的设计原则 | 见 `ui_alignment_questions.md` Q3；建议默认隐藏或改写成业务可理解的“可用性 / 风险提示”表达 | `StationQuery.vue`、`CoverageAnalysis.vue`、`StatsReport.vue`、`ui/08_服务层页面.md` | 待决策 |
| `donor`、`source cell`、`补数来源` 同时存在 | Step 4 的“补数来源对象”在 UI、human guide、开发文档里叫法不一，且英文 donor 泄漏到 UI | UI 与 human guide 统一叫`补数来源小区`；接口 / SQL 内部继续保留 `donor_*` 仅作实现字段 | `KnowledgeFill.vue`、`frontend/design/src/api/enrichment.ts`、`docs/04_知识补数.md`、`human_guide/04_Step4_知识补数.md` | 已确认（建议直接执行） |
| Step 4 卡片写 `donor 命中`、`excellent donor`、`qualified donor` | 中英混杂，且页面是给治理分析师看的，不需要直接显示英文 donor | 改成`补数来源命中`、`高置信来源小区`、`中置信来源小区`；需要保留质量等级时用`优秀 / 合格` | `KnowledgeFill.vue` | 已确认（建议直接执行） |
| Step 5 页面写`Cell 画像维护`、`Cell 画像列表`、`BS 画像列表`、`LAC 画像列表` | `画像`强调对象特征，`维护`强调正式库治理；现在二者混成一层，会让页面看起来像静态画像浏览页 | Step 5 页面标题统一为`Cell 维护` / `BS 维护` / `LAC 维护`；列表统一写`维护对象列表`或`正式库对象列表` | `CellMaintain.vue`、`BSMaintain.vue`、`LACMaintain.vue`、`ui/06_知识补数与治理页面.md` | 已确认（建议直接执行） |
| `normal_spread`、`collision_bs`、`dynamic_bs`、`large_spread`、`multi_centroid` 直接映到 UI 分类，且在服务搜索里被塞进 `position_grade` / `drift_pattern` | BS 分类、LAC 趋势、Cell 漂移模式是三套不同维度，当前 API 过载字段名会把“质量 / 分类 / 趋势”混成一类 | API 与 UI 分开表达：Cell 用`漂移模式`，BS 用`维护分类`，LAC 用`区域趋势`；搜索结果不要复用 `position_grade` / `drift_pattern` 承载所有层级 | `backend/app/service_query/queries.py`、`frontend/design/src/api/service.ts`、`StationQuery.vue` | 已确认（建议直接执行） |
| 服务页标题叫`基站查询`，但实际支持 Cell / BS / LAC 三层搜索 | 页面名字比实际范围窄，业务用户会误判只能查基站 | 见 `ui_alignment_questions.md` Q3；建议与服务层定位一起拍板，优先考虑`站点查询`或`位置查询（Cell/BS/LAC）` | `StationQuery.vue`、`ui/08_服务层页面.md`、`docs/06_服务层_运营商数据库与分析服务.md` | 待决策 |
| 服务层仍大量使用 `可信 Cell`、`qualified+`、`excellent` | 这些词对治理分析师清楚，但对业务用户过于内部化；尤其 `qualified+` 不是自然语言 | 服务层 UI 改成`可用小区数`、`达标小区占比`、`高精度小区占比`；必要时在帮助文案说明其与内部状态的映射 | `CoverageAnalysis.vue`、`StatsReport.vue` | 已确认（建议直接执行） |
| 配置页说明里仍直接写 `waiting / dormant / retired / collision / baseline_eligible` | 即使是规则页，也应先用中文讲清楚，再补代码名；否则页面像参数文件镜像 | 改成`等待 / 休眠 / 退出 / 碰撞 / 基线资格`，代码名作为次级标注 | `PromotionRules.vue`、`AntitoxinRules.vue`、`RetentionPolicy.vue`、`ui/07_系统配置页面.md` | 已确认（建议直接执行） |
| `结果库`、`正式库`、`可信 Cell`、`运营商数据库` 多套资产名并存 | Step 4/5 与 Step 6 都在谈“库”，但角色不同；当前用户很难知道何时在说治理资产、何时在说对外交付资产 | 管理 / 治理页统一强调`正式库`或`可信正式库`；服务层统一强调`运营商基站数据库`；`结果库`仅保留在开发文档语境 | `docs/06_服务层_运营商数据库与分析服务.md`、服务层页面、Step 4/5 页面 | 已确认（建议直接执行） |
| 业务页和报表页直接显示 `cell_id` / `bs_id` / `qualified BS` 等技术字段名 | 技术字段暴露过重，影响非技术用户阅读；尤其导出报表会把接口字段名误当业务口径 | UI 主列名统一改成`小区 ID` / `基站 ID` / `达标 BS 数`；导出若需保留原字段，可增加“技术版导出” | `StationQuery.vue`、`StatsReport.vue` | 已确认（建议直接执行） |

## 分页面组补充说明

### 全局管理

- 最需要先收敛的是版本条语义；否则后续所有页面都难以对齐。
- `运行历史`页应承担控制侧链语义统一责任，不能继续用临时 run type 名称替代文档口径。

### ETL 页面

- ETL 语义整体较稳，主要问题在于 Step 1 `补齐` 与 Step 4 `补数` 的边界必须全局强调。
- ETL 页允许保留更多结构性术语，但不应提前混入 donor / 正式库 / 可信锚点等 Step 4-5 词汇。

### Step 2 基础画像与分流

- Step 2 最大语义问题是“路由 / 分流 / Path A/B/C / 碰撞”并列出现但层级未分清。
- 一旦把 `路径名称 + 中文含义` 固定住，后续 Step 3、Step 4 的跳转文案就容易统一。

### Step 3 流式评估

- Step 3 当前需要统一的是“状态 / 资格 / diff”的三套表达，不是算法细节。
- `流转总览`要清楚区分“状态分布”“本批变动”“Cell 变动样本”三类内容。

### Step 4-5 治理页面

- 这里是术语漂移最严重的区域：`donor`、`active`、`画像`、`维护分类`、`锚点资格`、`基线资格` 同时存在。
- 这组页面建议先做一轮“中文主表达 + 内部 code 辅助说明”的统一，再进入页面级交互修订。

### Step 6 服务层

- 服务层当前最大的问题不是信息少，而是**内部治理信息太多**。
- 如果后续要保留专家模式，可以通过“高级字段开关”保留锚点 / 基线 / 漂移等信息，但默认视图应转成业务友好语言。

