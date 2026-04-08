# Prompt：rebuild3 UI v2 最终审计与修复（Impeccable 执行版）

你现在在项目根目录：`/Users/yangcongan/cursor/WangYou_Data`

你的任务**不是只做评审或给建议**，而是要基于：

1. **当前程序与代码实现**
2. **原始 UI_v2 设计稿与页面文档**
3. **当前实际运行中的页面**

对 `rebuild3` 做一次 **最终 UI 审计 + 直接修复落地**。

本轮目标非常明确：

- 让当前 `rebuild3` 主工作台在**信息架构、页面布局、视觉层级、中文化、交互链路、功能完整度**上，尽可能收敛到 `UI_v2`
- 不再停留在“比之前好一点”，而是完成一轮**真正可交付的最终修复**
- 审计必须基于**真实代码 + 真实运行页面 + 原始设计**，不能只靠阅读文档想象

---

## 一、你的角色

你现在扮演：

- 资深产品设计师
- 资深 UX 架构师
- 资深前端设计工程师
- 擅长用 **Impeccable / 前端设计 skill** 做高质量中文工作台 UI 修复的实现型 agent

你的任务不是重做一套“自认为更美观”的新界面，而是：

- **先审计**：找出当前实现与 `UI_v2`、冻结业务文档、真实功能之间的偏差
- **再修复**：直接改代码，把偏差消掉
- **再验收**：确认视觉、中文、功能、跳转、状态表达都成立

---

## 二、强制使用的 design skill 链路

开始前，必须按下面顺序执行并遵守：

1. `teach-impeccable`
   - 先检查当前 instructions 与项目根目录 `.impeccable.md`
   - 如果上下文已经足够，直接继承
   - 如果仍不足，再补全设计上下文
2. `frontend-design`
3. `normalize`
4. `typeset`
5. `arrange`
6. `clarify`
7. `polish`

可按需要追加：

- `colorize`
- `adapt`
- `harden`
- `animate`

### 本项目当前已知设计上下文（必须遵守）

以根目录 `.impeccable.md` 为准，尤其是这些硬约束：

- 使用者是数据运营 / 数据分析 / 技术运维人员
- 场景是**本地桌面工作台**
- 品牌气质：**Precise / Professional / Controllable**
- 整体风格：**浅色、克制、清晰、密度适中但可扫描**
- 设计原则：
  - 状态清晰优先于装饰
  - 层级必须一眼可扫
  - 对象中心，不回退到 Step 导航
  - 密集但不压迫
  - 所有页面都要服务“决策”而不是只展示结果

**不要做成 AI 套壳风格。不要做成紫色渐变 SaaS 模板。不要做成重玻璃态。不要做成深色炫技面板。**

---

## 三、真相优先级（发生冲突时必须这样判断）

### 优先级 1：冻结业务文档（业务规则唯一权威）

必须优先读取并遵守：

- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
- `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
- `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
- `rebuild3/docs/04c_UI目的与改版说明.md`

### 优先级 2：原始 UI_v2 设计资产（正式 UI 基线）

必须完整读取：

- `rebuild3/docs/UI_v2/index.html`
- `rebuild3/docs/UI_v2/design_notes.md`
- `rebuild3/docs/UI_v2/design_system.html`
- `rebuild3/docs/UI_v2/pages/*.html`
- `rebuild3/docs/UI_v2/pages/*_doc.md`

### 优先级 3：当前实现代码与当前运行页面（实现现实）

必须审计：

- `rebuild3/frontend/src/App.vue`
- `rebuild3/frontend/src/router.ts`
- `rebuild3/frontend/src/styles.css`
- `rebuild3/frontend/src/components/*`
- `rebuild3/frontend/src/pages/*`
- `rebuild3/frontend/src/lib/*`
- `rebuild3/backend/app/api/*`
- `rebuild3/backend/app/main.py`

### 优先级 4：历史参考

只用于行为与字段口径参考，不作为视觉标准：

- `rebuild2/frontend/`
- `rebuild2/launcher_web.py`
- `rebuild2` 相关旧逻辑与旧页面

---

## 四、你必须实际查看“当前运行页面”

你不能只看源码，必须结合真实 UI 审计。

### 运行入口

优先检查以下地址：

- 启动器：`http://127.0.0.1:47120`
- 主工作台：`http://127.0.0.1:47122`
- 后端：`http://127.0.0.1:47121`

如果服务未启动，使用项目现有启动方式把它们拉起，然后进行真实页面检查。

### 你必须完成的页面级检查

按路由逐页检查：

- `/flow/overview`
- `/runs`
- `/objects`
- `/objects/:objectType/:objectId`
- `/observation`
- `/anomalies`
- `/baseline`
- `/compare`
- `/profiles/lac`
- `/profiles/bs`
- `/profiles/cell`
- `/initialization`
- `/governance`

对于每一页，你都必须同时回答：

1. 当前页面和 `UI_v2` 原稿差多少
2. 当前页面和页面文档承诺差多少
3. 当前页面有哪些中文化问题
4. 当前页面有哪些功能缺失 / 假按钮 / 假入口 / 弱下钻
5. 当前页面哪些问题应该前端修，哪些需要后端接口或字段补齐

---

## 五、本轮修复的核心目标

### 目标 A：UI 设计收敛到 UI_v2，而不是继续漂移

你的修复不能只停留在“统一了一点样式”。

必须重点修正：

- 页面整体布局与区块结构
- 视觉层级与阅读顺序
- 顶部上下文条 / 页面头部 / 侧边导航的组织方式
- 关键卡片、表格、趋势区、下钻区的版式
- 颜色语义、状态徽标、资格表达
- 页面之间的一致性与组件复用方式

### 目标 B：全面中文化

当前实现里仍然残留明显英文 UI 文案，这一轮必须系统清理。

以下只是**已知线索，不是完整清单**，你必须继续全文审计：

- `rebuild3/frontend/src/App.vue`
  - `Main Flow`
  - `Profiles`
  - `Support`
- `rebuild3/frontend/src/pages/FlowOverviewPage.vue`
  - `Homepage`
  - `Flow Routes`
  - `Context`
  - `Priority Issues`
  - `Compare Callout`
- `rebuild3/frontend/src/pages/ObservationWorkspacePage.vue`
  - `Observation Workspace`
  - `Backlog`
  - `Tabs`
  - `Candidate Cards`

### 中文化要求

- 所有**可见文案**优先中文
- 包括但不限于：导航、按钮、页头、副标题、section kicker、空状态、错误状态、表头、提示语、badge、筛选器、说明文案
- 只有在以下场景才允许保留英文：
  - 真正的数据字段值 / 枚举值 / API 字段名
  - `run_id` / `batch_id` / `baseline_version` 等技术主键
  - 用户必须识别的标准术语，且中文会歧义
- 即使保留英文技术名，也要尽量加中文解释

### 目标 C：功能不能只剩展示壳

当前系统的问题不只是视觉偏差，还包括功能承诺不足。

你必须核查并补齐：

- 页面之间的下钻链路是否真的能走通
- 筛选 / Tab / 切换 / 快速跳转是否真的服务任务
- 列表页到详情页是否一致
- 当前上下文（run / batch / baseline / rule_set_version）是否统一且稳定可见
- “问题入口”是否能真正落到对象 / 异常 / 批次页面
- 各页中明显承诺给用户的按钮与链接，是否真的可用
- fallback 页面是否明确标识、是否还能继续向前推进

如果当前 API 不足以支撑 `UI_v2` 的必要交互：

- 允许补后端读模型 / API
- 或者做**清晰、诚实、中文化**的降级表达
- 但**不允许**继续保留误导性的假交互

### 目标 D：让页面更像“工作台”，而不是“泛化卡片集合”

当前很多页面虽然已经比早期版本完整，但仍有明显的“共用卡片堆砌感”。

你必须重点修：

- 不同页面之间缺少结构辨识度
- 过度依赖同一套 metric card / panel 排法
- 页面主次不够鲜明
- 缺乏真正服务任务的第一屏
- 与 `UI_v2` 原稿中更明确的版式差距过大

要求：

- 每个页面都要有清晰的“第一页屏任务中心”
- 重要页要有更强的布局辨识度
- 组件复用可以做，但不能把所有页做成同一个壳

---

## 六、必须读取的补充文档（帮助你判断当前偏差）

请继续读取并综合：

- `rebuild3/docs/UI_v2/audit_deviation_report.md`
- `rebuild3/docs/UI_v2/audit_decisions_required.md`
- `rebuild3/docs/ui_mapping_matrix.md`
- `rebuild3/docs/impl_alignment.md`
- `rebuild3/docs/ui_acceptance_report.md`
- `rebuild3/docs/issues.md`
- `rebuild3/docs/current_tree_audit.md`

注意：

- `ui_acceptance_report.md` 只能当作历史记录，**不能当作“现在已经没问题”的结论**
- 你必须以当前实际页面体验和代码实现为准，再重新给出结论

---

## 七、你要如何执行这次修复

### 阶段 1：建立偏差清单（必须先做）

请输出一份你自己的偏差判断，并按严重度分级：

- `P0`：功能阻塞 / 关键页面无法使用 / 明显错误状态 / 链路断裂
- `P1`：信息架构、页面结构、关键视觉层级明显偏离 UI_v2
- `P2`：中文化不完整、组件一致性差、状态表达不统一
- `P3`：细节 polish、空状态、边界态、间距与排版问题

### 阶段 2：直接修代码，不要停在提建议

你必须直接修改：

- `rebuild3/frontend/src/**`
- 必要时可修改 `rebuild3/backend/app/**`
- 必要时可修改 `rebuild3/launcher/launcher_ui/index.html`（仅在你确认主工作台与启动器在语言/风格/入口上明显割裂时）

优先顺序：

1. 先修主框架与壳层：导航、页头、上下文条、全局布局、中文残留
2. 再修主流程页：流转总览、运行/批次中心、对象浏览、对象详情
3. 再修工作台页：观察、异常、基线
4. 再修支撑页：验证/对照、初始化、基础数据治理、画像页
5. 最后做排版、状态、边界态 polish

### 阶段 3：不能只“表面像”，还要“行为对”

你在修页面时，必须逐页确认：

- 当前 API 返回的数据字段能否支撑 `UI_v2` 的核心模块
- 不能支撑时，是该补接口，还是该做诚实降级
- 当前 route / query / 页面内部状态是否满足用户连续操作
- 页面之间的路径是否比现在更顺手，更像真实工作台

---

## 八、硬约束

### 1. 业务语义绝对不能漂移

下列业务词必须保持一致，不允许自行改名：

- `lifecycle_state`
- `health_state`
- `anchorable`
- `baseline_eligible`
- `fact_governed`
- `fact_pending_observation`
- `fact_pending_issue`
- `fact_rejected`
- `run_id`
- `batch_id`
- `contract_version`
- `rule_set_version`
- `baseline_version`

### 2. 不允许拿“更现代”当理由偏离原设计目标

禁止以下倾向：

- 把页面做成通用 SaaS 后台模板
- 把 UI_v2 的工作台结构改回 KPI Dashboard
- 把验证/对照再次抬到主入口
- 为了“统一组件”削平页面个性与任务结构
- 继续留下英文 section 名称和英文提示文案
- 用假数据 / 假按钮 / 假跳转冒充功能完整

### 3. 桌面优先，但不能在窄屏直接坏掉

- 主目标仍然是本地桌面工作台
- 但基础响应式不能坏
- 至少保证常见笔记本宽度可用
- 不能把关键功能在较窄窗口直接裁没

### 4. 设计风格限制

- 浅色模式优先
- 蓝/靛蓝为主品牌色
- 绿色 / 黄色 / 橙色 / 红色承载状态语义
- 不要紫色主导
- 不要重度毛玻璃
- 不要过度圆角 + 厚阴影的“AI 卡片堆”
- 不要仅靠大面积卡片复制来组织所有内容

---

## 九、建议你重点关注的页面问题

以下不是替你下结论，而是提醒你必须重点审：

### 1. 全局壳层

检查：

- 侧边导航是否足够接近 `UI_v2` 的导航层次与优先级
- 顶部标题、分组名、描述语是否中文化且语义准确
- 版本上下文条是否稳定、可读、足够靠前
- 全局视觉是否仍偏“统一卡片壳”，缺少工作台感

### 2. 流转总览

检查：

- 是否真正体现 `01_flow_overview.html` 与时间快照视图的核心信息结构
- 是否把四分流、delta、问题入口、上下文放在首屏主位
- 是否还残留过多英文与 generic panel 结构

### 3. 运行 / 批次中心

检查：

- 是否像真正的批次诊断工作台
- 是否支持从批次变化进入对象/异常/基线
- 是否只是“列表 + 明细”而没有诊断链路

### 4. 对象浏览 / 对象详情

检查：

- 对象列表和详情页是否真正有治理语义，不只是普通数据表
- 是否正确表达 lifecycle / health / 资格 / 事实落点 / 历史变化 / 下游影响
- 对象详情页是否足够像 `UI_v2` 原稿，而不是简化信息面板

### 5. 等待 / 观察工作台

检查：

- 三层资格推进是否清晰
- 停滞 / 接近晋升 / 建议转问题是否明确
- 是否仍然只是候选卡片堆，而不是可操作工作台

### 6. 异常工作台

检查：

- 对象级异常与记录级异常是否真正双视角
- 严重度、影响范围、建议动作是否足够清楚
- 与对象页 / 批次页的联动是否成立

### 7. 基线 / 画像 + 三个 profile 页面

检查：

- 是否把基线判断、差异、风险、画像解释讲清楚
- `classification_v2` / `gps_confidence` / `signal_confidence` 是否只是解释层
- 三个画像页是否既统一，又各自保留对象特性

### 8. 验证 / 对照、初始化、基础数据治理

检查：

- 是否明确是支撑页，而不是主流程页
- fallback 是否足够诚实、足够中文化
- 页面是否仍有明显占位感

---

## 十、你必须产出的内容

### A. 直接代码改动

你必须完成真实代码修改，而不是只输出文档。

### B. 修复报告

请新增并写入：

- `rebuild3/docs/ui_final_rectification_report.md`

报告至少包含：

1. 本轮审计范围
2. 逐页问题清单（按 P0 / P1 / P2 / P3）
3. 你实际修了什么
4. 哪些问题是前端修复，哪些需要后端配合
5. 哪些残余问题暂未修完，以及原因
6. 验证方式与结果

### C. 如有必要，更新相关说明文档

如果你做了明显的 IA、组件边界或运行方式修正，可同步更新这些文档中真正过时的部分：

- `rebuild3/docs/ui_acceptance_report.md`
- `rebuild3/docs/runtime_startup_guide.md`
- `rebuild3/README.md`

但前提是：**只更新你真正改变且已经验证的内容。**

---

## 十一、验证要求（必须执行）

至少执行并记录：

### 前端

```bash
cd rebuild3/frontend && npm run build
```

### 后端（如果你改了 Python / API）

```bash
python3 -m py_compile rebuild3/backend/app/api/*.py rebuild3/backend/app/core/*.py rebuild3/backend/app/main.py
```

### 页面实际检查

你必须重新打开并检查：

- 主工作台首页
- 至少 5 个关键页面
- 至少 1 条“列表 -> 详情”下钻链路
- 至少 1 条“问题入口 -> 目标页面”跳转链路

如果你修改了 launcher 入口或启动方式，也要检查：

- `http://127.0.0.1:47120`

---

## 十二、完成标准

只有同时满足下面条件，才算完成：

1. 当前实现和 `UI_v2` 的偏差被系统梳理并修复，而不是局部装饰
2. 页面级英文残留被基本清理，主界面完成中文化
3. 主流程页、对象页、工作台页的结构更接近原设计，不再只是通用卡片拼装
4. 关键交互和下钻链路可用，不再出现明显“看起来能点但没意义”的入口
5. fallback 页面明确、诚实、中文化
6. 构建通过，必要的后端校验通过
7. 有一份新的修复报告可以交付给项目负责人审阅

---

## 十三、最后提醒

- **这不是重新做视觉探索**，而是一次面向交付的最终修复
- **这不是只写审计报告**，而是要边审计边改代码
- **不要自作主张推翻 UI_v2**，除非它与冻结业务文档直接冲突，并且你在报告里明确说明
- **不要把“能运行”当作“已经完成”**；这次要解决的是“设计、中文、功能仍然差很多”的真实问题

请开始执行。
