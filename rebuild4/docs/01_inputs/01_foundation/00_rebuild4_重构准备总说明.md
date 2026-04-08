# rebuild4 重构准备总说明

状态：准备阶段 / 非实施任务书  
更新时间：2026-04-05

---

## 0. 本文档的作用

这份文档不是 rebuild4 的最终实施任务书，而是为正式任务书做前置整理。

当前阶段只做三件事：

1. 冻结 rebuild4 必须继承的核心真相源
2. 记录 rebuild3 这一轮反复偏离后已经确认的关键问题
3. 把 rebuild4 在任务书中必须新增的内容先整理出来，避免再次边做边改

在正式任务书冻结前：

- 不应直接进入 rebuild4 编码
- 不应先做 UI 再倒推数据
- 不应默认用 synthetic / fallback 顶替 real 数据
- 不应把 rebuild2 里已完成的数据清理细节继续遗漏

---

## 1. rebuild4 的真相源顺序

### Tier 0：核心冻结文档

1. `rebuild4/docs/01_inputs/04_reference/rebuild3_core/01_rebuild3_说明_最终冻结版.md`
2. `rebuild4/docs/01_inputs/04_reference/rebuild3_core/02_rebuild3_预实施任务书_最终冻结版.md`
3. `rebuild4/docs/01_inputs/04_reference/rebuild3_core/03_rebuild3_技术栈要求_最终冻结版.md`

### Tier 1：核心 UI 设计文档

1. `rebuild4/docs/01_inputs/03_ui_v2/design_notes.md`
2. `rebuild4/docs/01_inputs/03_ui_v2/index.html`
3. `rebuild4/docs/01_inputs/03_ui_v2/pages/*_doc.md`
4. `rebuild4/docs/01_inputs/03_ui_v2/audit_decisions_required.md`

### Tier 2：rebuild2 已完成资产

1. `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/00_项目定义.md`
2. `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/04_phase1_总结.md`
3. `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/phase2_trusted_library.md`
4. `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/phase4_data_audit.md`
5. `rebuild2_meta.field_audit`
6. `rebuild2_meta.ods_clean_rule`
7. `rebuild2_meta.ods_clean_result`
8. `rebuild2.dim_lac_trusted`
9. `rebuild2.l0_gps`
10. `rebuild2.l0_lac`
11. `rebuild2.dwd_fact_enriched`

### Tier 3：rebuild3 本轮复盘证据

1. `rebuild4/docs/01_inputs/04_reference/rebuild3_review/rebuild3_round2_repair_task_doc.md`
2. `rebuild4/docs/01_inputs/04_reference/rebuild3_review/rebuild3_round2_repair_execution_note.md`
3. `rebuild4/docs/01_inputs/04_reference/rebuild3_review/Claude_field_baseline.md`
4. 当前数据库实时查询结果（`rebuild3_meta.*`、`rebuild3.*`、`rebuild2*`）

裁决规则：

- 业务语义、主语、状态、资格，以 Tier 0 为准
- 页面用途、导航、主工作流、视觉表达，以 Tier 1 为准
- rebuild2 的字段清洗、过滤漏斗、可信库构建事实，以 Tier 2 的数据库与文档共同为准
- 如果代码或当前实现与以上文档冲突，先判当前实现有偏移，不允许反向用代码改写文档

补充说明：

- 以上 Tier 0 / Tier 1 / Tier 2 文档都已在 `rebuild4/docs` 下保留本地副本，后续整理和任务书编写优先引用 rebuild4 内部路径
- 上游原件仍然保留在 `rebuild3` / `rebuild2` 中，但 rebuild4 阶段应尽量避免跨目录来回取材

---

## 2. rebuild4 必须重新对齐的核心定位

rebuild4 不能再被理解成“把 rebuild3 页面补齐一轮”。

它的正式定位必须回到下面这句：

**rebuild4 = 继承 rebuild2 已验证的数据解析/清洗/可信库研究成果，重新构建一个可持续运行、可研究流转参数、且系统完成后立即有数据可用的本地动态治理系统。**

这里至少有四个关键词不能丢：

1. **继承 rebuild2 已验证成果**
   - 包括字段解析、ODS 清洗、trusted 过滤、GPS 修正、信号补齐、画像与异常研究
2. **动态数据库**
   - 不是一次性静态跑完，而是初始化 + 增量 + baseline 版本承接
3. **可研究不同流转参数**
   - 使用者需要观察不同 run / batch / 场景 / 时间点的流转变化，而不是只看最终结果
4. **完成后必须立即有可用数据**
   - 不能只有页面和 schema，没有可评估数据链

---

## 3. rebuild3 暴露出来的主要偏移

rebuild4 的正式任务书必须正面吸收这些教训：

### 3.1 先实现后冻结，导致多轮补丁

已发生的问题：

- 文档其实已经足够清晰，但执行中多次偏离主语和边界
- 后续不得不通过多轮 repair 回正
- 结果是时间被消耗在“修偏差”，而不是“推进主系统”

rebuild4 约束：

- 必须先冻结任务文档，再开始实施
- 实施中新增需求必须先写入文档，再进入代码

### 3.2 页面曾经能渲染，但主语不真实

已发生的问题：

- synthetic scenario 曾被当成正式时间点快照
- sample/full/fallback 曾占据主流程页面的主语位置
- compare / governance 曾长期依赖 fallback

rebuild4 约束：

- 每个页面/API 都必须声明 `data_origin`
- `real / synthetic / fallback` 必须是合同级字段，而不是实现内部约定
- 不允许 fallback 冒充 real

### 3.3 数据准备没有被当成一等任务

已发生的问题：

- UI 能打开，但很多页面早期没有足够数据可评估
- 后续又不得不补 synthetic 评估模式，才能给功能评估提供数据

rebuild4 约束：

- 数据准备必须写进主任务书，而不是当成上线前顺手补
- 每个核心页面都要明确其最小可用数据前提
- 任务书必须包含“数据准备完成”的验收标准

### 3.4 rebuild2 的清洗细节没有完整进入新系统叙事

已发生的问题：

- rebuild3 继承了 rebuild2 的很多治理值和对象结果
- 但使用者仍看不到：多少数据因为哪些规则被过滤掉、这些数据来自哪里、过滤前后损耗如何

rebuild4 约束：

- rebuild2 数据清洗细节必须纳入 rebuild4 的正式可见范围
- 不能只保留最终治理结果，不保留过滤与损耗解释

---

## 4. rebuild4 任务书必须新增的三项硬要求

### 4.1 新增 rebuild2 数据清理细节链路

必须能回答：

1. 原始字段中哪些被 keep / parse / drop
2. ODS 清洗规则有哪些
3. 每条规则影响了多少行
4. 哪些是删除、哪些是置空、哪些是转换
5. trusted 过滤前后损耗多少
6. 被过滤数据主要来自什么来源、什么解析通道、什么制式
7. 当前页面看到的治理结果，向前可追溯到哪些清洗与过滤动作

### 4.2 把“有数据可评估”列为正式交付条件

必须明确：

- 系统完成后，用户能立刻评估真实流转，而不是只看空页面
- 如果某页暂时只能用 synthetic 评估数据，也必须在任务书中提前声明
- 数据准备不是附属工作，而是主交付件之一

### 4.3 全面服从 UI_v2

必须服从的不是“某几页长得像”，而是 UI_v2 的完整设计意图：

- 主工作流是流转总览 -> 下钻 -> 观察/异常 -> 基线/对照
- 页面围绕对象 / 决策 / 事实 / baseline 组织，而不是旧 step
- 所有页面支持按对象快速定位
- baseline 原则、状态表达、四分流、资格表达需要一致

---

## 5. rebuild4 正式任务书建议结构

建议在本目录下继续生成以下正式文档：

1. `01_rebuild4_核心输入整理.md`
   - 汇总 rebuild3 01/02/03 + UI_v2 的必须继承项
2. `02_rebuild4_新增需求与数据准备清单.md`
   - 汇总本轮新增需求、数据准备要求、当前已知证据
3. `03_rebuild4_正式任务书.md`
   - 冻结实施边界、分期、验收标准
4. `04_rebuild4_数据准备计划.md`
   - 定义初始化数据、增量数据、快照、baseline、对照的生成与验收
5. `05_rebuild4_UI与API映射表.md`
   - 页面 -> API -> 表/视图 -> 数据来源 -> 验收项

---

## 6. rebuild4 的实施前检查清单

正式任务书发布前，以下项目必须全部回答清楚：

- 是否已经明确 Tier 0 / UI_v2 / rebuild2 的真相源优先级
- 是否已经把 rebuild2 清洗与过滤细节列入正式范围
- 是否已经定义各页面所需的最小可用数据前提
- 是否已经定义 `real / synthetic / fallback` 的页面与 API 表达规则
- 是否已经明确哪些模块本轮必须真实接数，哪些允许暂缓
- 是否已经明确 compare / governance / snapshot / overview 的数据来源要求
- 是否已经定义“空状态可接受”与“必须有数据”的边界

如果以上任一项仍未冻结，就不应进入 rebuild4 编码阶段。
