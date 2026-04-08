# Prompt F：rebuild3 开发实施（UI 优先纠偏与归档版）

> 使用场景：上一轮 `04e` 执行后，数据主链路已有一定成果，但正式系统交付出现明显偏差，尤其是 UI 与启动器未按 `UI_v2` 基线落地。新开对话时，使用本 Prompt 重新推进。  
> 本 Prompt 目标：不是继续在现有 spike 上修修补补，而是基于当前目录 **重新审计、重建完整任务、以 UI 为主线完成正式实现，并在完成后归档本轮跑偏文件**。

---

## 你的角色

你现在扮演：

- 首席架构师
- UI-first 正式重构负责人
- 全栈实现负责人
- 验证负责人
- 归档与目录治理负责人

你要做的不是“一轮补丁式修复”，而是：

1. 基于当前目录重新确认哪些成果可保留
2. 找出上一轮为何偏离 `04e`
3. 按 `UI_v2` 重新构建完整任务体系
4. 以页面级可见验收为主线推进正式实现
5. 确保用户可以通过启动器/启动说明独立运行系统
6. 在正式实现完成后，将本轮跑偏 spike 文件归档

---

## 在开始任何代码前，必须先读取的材料

### A. 冻结文档与原始 Prompt

1. `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
2. `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
3. `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
4. `rebuild3/docs/04e_prompt_开发实施_正式重构流程版.md`

### B. UI 设计基线

5. `rebuild3/docs/UI_v2/design_notes.md`
6. `rebuild3/docs/UI_v2/index.html`
7. `rebuild3/docs/UI_v2/launcher/launcher.html`
8. `rebuild3/docs/UI_v2/launcher/launcher_doc.md`
9. `rebuild3/docs/UI_v2/pages/*.html`
10. `rebuild3/docs/UI_v2/pages/*_doc.md`
11. `rebuild3/docs/UI_v2/audit_deviation_report.md`
12. `rebuild3/docs/UI_v2/audit_decisions_required.md`
13. `rebuild3/docs/Docs/UI_v2_审计后修改执行清单.md` — UI v2 最终定稿的修改清单（三层资格、双视角异常、画像状态降级、基础数据治理新增、侧边栏分组）
14. `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md`

**重要**：UI_v2 经过了多轮修改，最终版本包含以下关键变更（在审计后执行清单中完成）：
- 等待/观察工作台改为三层资格推进（存在/锚点/基线），不再是单一阈值
- 异常工作台拆为对象级 + 记录级双视角 Tab
- LAC/BS/Cell 画像页统一 health_state，旧分类（classification_v2 等）降级为解释层
- 新增基础数据治理页面（13_data_governance，4 Tab）
- 所有页面侧边栏统一为三组分组（主流程层/画像视角层/支撑治理层）
- 四分流全部使用全称（fact_governed / fact_pending_observation / fact_pending_issue / fact_rejected）
- 基线原则在相关页面显式可见

### C. 当前目录的纠偏输入

15. `rebuild3/docs/rectification_audit.md`
16. `rebuild3/docs/archive_manifest_20260404_ui_spike.md`
17. `rebuild3/docs/impl_alignment.md`
18. `rebuild3/docs/impl_plan.md`
19. `rebuild3/docs/sample_scope.md`
20. `rebuild3/docs/sample_run_report.md`
21. `rebuild3/docs/sample_compare_report.md`
22. `rebuild3/docs/full_run_report.md`
23. `rebuild3/docs/full_compare_report.md`
24. 当前 `rebuild3/` 目录树

### D. 当前实现产物（必须先审计，不可先入为主）

25. `rebuild3/backend/sql/`
26. `rebuild3/backend/scripts/`
27. `rebuild3/backend/app/api/`
28. `rebuild3/frontend/`
29. `rebuild3/launcher/`
30. `rebuild3/config/`

---

## 核心纠偏原则（硬性原则）

### 1. `UI_v2` 是正式页面基线，不是参考灵感

必须执行：

- 页面结构，以 `UI_v2/pages/*.html` 为准
- 页面边界，以 `*_doc.md` 为准
- 导航关系，以 `UI_v2/index.html` 为准
- 启动器，以 `UI_v2/launcher/launcher.html` 为准

禁止：

- 自行发明另一套页面结构
- 用“理解了语义”代替“对齐页面基线”
- 做一个独立工作台原型来替代正式 UI

### 2. UI 是本轮第一验收对象

因为用户当前唯一稳定可见的判断面是 UI，所以本轮必须把 UI 视为首要验收对象。

这意味着：

- 每一页都必须有明确可见验收标准
- 每一页都必须有对应读模型/API
- 每一页都必须说明当前是否真实接数，还是临时回退
- 不允许只说“数据已经跑通，因此 UI 可以后补”

### 3. 当前数据主链路是候选保留资产，不得轻易推倒

你必须先审计当前数据链路，再决定是否复用。

默认候选保留资产包括：

- schema / 独立 schema 设计
- 样本抽取与双跑 SQL
- rebuild3 样本/全量 pipeline SQL
- compare SQL
- 样本与全量报告
- 配置文件

禁止：

- 在未审计前，直接重写整条数据链路
- 把已验证成果与跑偏 UI 一起一刀切废弃

### 4. 启动器与可运行性必须前置

本轮必须解决“用户无法自行运行系统”的问题。

必须交付：

- 启动器页面入口
- 本地运行说明
- 一键或最简启动方式
- 前后端运行状态可检查

### 5. 跑偏 spike 文件必须在新实现通过后归档

但注意：

- 不能现在就清空
- 归档时机：**Gate F（全页验收完成）通过后** 才执行归档
- 归档后要有报告，防止未来目录混乱

依据：

- `rebuild3/docs/archive_manifest_20260404_ui_spike.md`

---

## 先做的不是编码，而是“重新建 task”

你必须先完成下面三个文档，再开始正式改代码。

### 第 0 步：当前目录审计（Gate A0）

先输出：

- `rebuild3/docs/current_tree_audit.md`

至少包含：

1. 当前目录的主要模块树
2. 哪些成果已经存在
3. 哪些成果符合 `04e`
4. 哪些成果只属于 spike
5. 哪些成果应保留复用
6. 哪些成果应在新实现完成后归档
7. 哪些生成产物应清理而非归档

### 第 1 步：UI 页面映射矩阵（Gate A1）

先输出：

- `rebuild3/docs/ui_mapping_matrix.md`

必须逐页列出：

- UI_v2 页面文件
- 正式路由
- 页面目标
- 必要读模型/API
- 依赖数据表/汇总表
- 当前实现状态
- 验收标准
- 是否属于首批优先实现页面

至少覆盖：

- 启动器
- 01 流转总览
- 02 运行 / 批次中心
- 03 对象浏览
- 04 对象详情
- 05 等待 / 观察工作台
- 06 异常工作台
- 07 基线 / 画像
- 08 验证 / 对照
- 09 LAC 画像
- 10 BS 画像
- 11 Cell 画像
- 12 初始化
- 13 基础数据治理

### 第 2 步：新的 UI-first 正式任务书（Gate B）

先输出：

- `rebuild3/docs/ui_first_impl_plan.md`

每个任务必须包含：

- 输入
- 输出
- 依赖
- 验收标准
- 风险
- 回归影响
- 是否复用当前实现
- 如重写，旧文件最终归档到哪里

---

## 新任务书必须覆盖的任务域

### A. 启动与运行域

必须明确：

- 启动器页面如何落地
- 前端如何启动
- 后端如何启动
- 本地依赖如何检查
- 如何判断系统已可运行
- 用户如何从一个明确入口进入系统

至少交付：

- `rebuild3/docs/runtime_startup_guide.md`
- 启动脚本或统一命令入口
- launcher 的正式实现

### B. 页面实现域（UI-first 主线）

页面实现顺序必须有主次，建议优先级如下：

#### 第一批（必须先做完，覆盖主流程核心链路）

1. 启动器
2. 流转总览
3. 运行 / 批次中心
4. 对象浏览
5. 对象详情
6. 等待 / 观察工作台（日常高频使用，三层资格推进）
7. 异常工作台（对象级 + 记录级双视角）

#### 第二批（画像与基线）

8. Cell 画像
9. BS 画像
10. LAC 画像
11. 基线 / 画像

#### 第三批（支撑与验证）

12. 验证 / 对照
13. 初始化
14. 基础数据治理

### C. 共享组件与状态表达域

必须建立并统一：

- VersionContext
- lifecycle_state 徽标
- health_state 徽标
- `anchorable` / `baseline_eligible` 标签
- WATCH 派生状态表达
- 四分流组件
- delta / compare 差异表达组件

### D. 读模型与 API 域

必须覆盖正式页面所需的读模型/API，而不是只实现 Cell 局部接口。

至少覆盖：

- `/api/v1/runs/*`
- `/api/v1/objects/*`
- `/api/v1/compare/*`
- `/api/v1/governance/*`
- 基线 / profile / observation / anomaly 相关接口

要求：

- 页面不能直接拼底层表
- API 必须服务于页面结构
- 页面与 API 的映射必须在 `ui_mapping_matrix.md` 中可追踪

### E. 数据与验证域

必须重新核对当前数据资产：

- 哪些 SQL 与脚本可以直接复用
- 哪些还只是临时实现
- 哪些页面所需读模型仍未生产

必须额外输出：

- `rebuild3/docs/data_reaudit_report.md`

这个报告至少回答：

1. 当前数据链路哪些部分已经满足正式实现输入要求
2. 哪些部分仍只覆盖样本/全量对比，不足以支撑正式 UI
3. 是否存在除 UI 之外的 P0/P1 缺口
4. 是否需要补充 read model / summary table

---

## 实施门禁（新的纠偏门禁）

### Gate A0：当前目录审计完成

通过条件：

- 已输出 `current_tree_audit.md`
- 明确了保留 / 重做 / 归档 / 清理的对象

### Gate A1：UI 映射完成

通过条件：

- 已输出 `ui_mapping_matrix.md`
- 每个正式页面都有路由/API/数据映射

### Gate B：新的 UI-first 任务书完成

通过条件：

- 已输出 `ui_first_impl_plan.md`
- 覆盖启动器、页面、共享组件、API、验证、归档策略

### Gate C：启动器与运行入口完成

通过条件：

- 用户可以根据文档独立启动系统
- 有明确 launcher 入口

### Gate D：第一批页面通过 UI 验收

至少包括：

- 启动器
- 流转总览
- 运行 / 批次中心
- 对象浏览
- 对象详情
- 等待 / 观察工作台
- 异常工作台

### Gate E：API 与页面联调通过

通过条件：

- 首批页面均已接正式读模型/API
- 不再只是局部 spike

### Gate F：全页验收完成

通过条件：

- 所有正式页面已完成实现或已明确列入后续计划并说明原因
- 已输出正式 UI 验收报告

### Gate G：归档完成

通过条件：

- 本轮跑偏 spike 文件已按清单归档
- 已输出归档执行报告

---

## 页面级验收要求（强制）

对每个页面，你都必须输出如下内容：

- 页面是否已实现
- 对应的 UI_v2 原型文件
- 对应的正式路由
- 对应的 API
- 对应的数据来源
- 当前是否真实接数
- 与 UI_v2 的差异
- 差异是否可接受

这些内容必须汇总到：

- `rebuild3/docs/ui_acceptance_report.md`

如果某页未通过，你必须明确写：

- 为什么未通过
- 阻塞是什么
- 下一步怎么补

---

## 归档要求（开发完成后执行）

归档不是建议项，是正式收尾动作。

### 归档输入

- `rebuild3/docs/archive_manifest_20260404_ui_spike.md`

### 归档目标

在新正式实现通过验收后：

1. 将本轮跑偏 spike 文件移入归档目录
2. 对可再生产物执行清理/重建，而不是混乱保留
3. 输出归档说明，避免以后误把 spike 当正式实现

### 建议输出

- `rebuild3/archive/20260404_ui_spike/README.md`
- `rebuild3/docs/archive_execution_report.md`

---

## 最终输出要求

完成本 Prompt 后，项目至少应达到以下状态：

1. 当前目录已被重新审计并分类
2. UI_v2 页面已有完整映射矩阵
3. 新的 UI-first 正式任务书已经建立
4. 用户可通过明确启动入口自行运行系统
5. 第一批关键页面按 UI_v2 基线完成正式实现
6. 页面-API-数据映射清晰可追踪
7. 已输出页面级验收报告
8. 本轮跑偏 spike 文件在新实现通过后被正式归档

---

## 输出风格要求

1. 先审计，再建 task，再实现，再验收，再归档
2. 不要再把 UI 当成附属项
3. 不要再把“理解了页面语义”当成“实现了 UI_v2”
4. 不要输出泛泛建议，必须产出文件和执行结果
5. 任何不满足设计要求的地方，都必须明确指出，而不是默认忽略

