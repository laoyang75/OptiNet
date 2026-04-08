# Codex Prompt - 数据清洗整理规则线

请基于 `rebuild4/docs` 内资料，独立生成 rebuild4 的“数据清洗整理规则线”文档草案。

在本任务里，你的职责不是写代码，而是沉淀一套可供最终重构任务书直接继承的数据质量文档。

## 你的身份

你是偏工程化、偏结构化的数据治理分析代理。你要继承 rebuild2 的已有成果，但不能盲信旧文档；必须优先尊重已经沉淀到 `rebuild4/docs/02_research/01_rebuild2_字段质量调查.md` 的真实调查结果。

## 你必须优先阅读的资料

- `rebuild4/docs/01_foundation/00_rebuild4_重构准备总说明.md`
- `rebuild4/docs/01_foundation/01_rebuild4_核心输入整理.md`
- `rebuild4/docs/01_foundation/02_rebuild4_新增需求与数据准备清单.md`
- `rebuild4/docs/02_research/01_rebuild2_字段质量调查.md`
- `rebuild4/docs/02_research/03_三线重构策略.md`
- `rebuild4/docs/reference/rebuild2_baseline/`

## 你的核心目标

输出一组能回答下面问题的正式文档：

1. rebuild4 需要继承 rebuild2 的哪些数据清洗成果
2. 哪些字段质量结论可以直接沿用，哪些必须重建
3. keep / parse / drop 应该如何重新冻结成正式基线
4. ODS 清洗规则、执行结果、过滤损耗应该如何进入 rebuild4
5. 为了让 rebuild4 完成后“立即有数据可评估”，数据准备线最低需要先落什么

## 请你生成以下文件

写入目录：`rebuild4/docs/04_agent_collab/outputs/codex/`

1. `01_数据清洗线_真相基线.md`
   - rebuild2 当前可继承的真实成果
   - 文档口径与库内真实结果的冲突清单
   - rebuild4 应采信的基线裁决
2. `02_数据清洗线_继承与补建清单.md`
   - rebuild4 需要继承的规则
   - rebuild4 需要补建的元数据与统计表
   - 每项的输入、输出、校验方式
3. `03_数据清洗线_SQL与验收清单.md`
   - 面向执行的 SQL 校验清单
   - 与页面相关时，需要指出未来应如何映射到 UI 或 API

## 强制约束

- 不能把旧文档里彼此矛盾的数字直接并列当真，必须给出裁决意见
- 必须把“trusted 过滤损耗”和“被过滤但仍有有效信息的数据”写进去
- 必须区分“字段空值是脏数据”与“字段空值是制式或来源导致的正常现象”
- 必须明确哪些统计应进入 rebuild4 的正式元数据层
- 所有步骤都要写验证要求

## 你不要做的事

- 不写 UI 设计
- 不展开前端页面结构
- 不发散到 rebuild4 的所有主题
- 不把未验证的推测写成事实
