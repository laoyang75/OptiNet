# Claude Prompt - 流转处理流程线

请基于 `rebuild4/docs` 内资料，独立生成 rebuild4 的“流转处理流程线”文档草案。

## 你的身份

你是偏语义梳理、系统建模、门禁设计的流程分析代理。你要承接 rebuild3 的核心目标：构建动态数据库，并让使用者研究不同阶段的流转参数与状态变化。

## 你必须优先阅读的资料

- `rebuild4/docs/01_foundation/00_rebuild4_重构准备总说明.md`
- `rebuild4/docs/01_foundation/01_rebuild4_核心输入整理.md`
- `rebuild4/docs/01_foundation/02_rebuild4_新增需求与数据准备清单.md`
- `rebuild4/docs/02_research/02_rebuild3_04系列偏航复盘.md`
- `rebuild4/docs/02_research/03_三线重构策略.md`
- `rebuild4/docs/reference/rebuild3_core/`
- `rebuild4/docs/reference/rebuild3_review/`

## 你的核心目标

输出一组能回答下面问题的正式文档：

1. rebuild4 的 run / batch / baseline / snapshot / issue / observation 等实体如何定义
2. 初始化、增量、重跑、比较、治理、画像之间的关系如何组织
3. real / synthetic / fallback 在 rebuild4 里如何正式定义并使用
4. rebuild4 要怎样提前准备数据，才能在系统完成后立即有数据可评估
5. 如何把 Gate 变成真正的停机线，而不是说明性文字

## 请你生成以下文件

写入目录：`rebuild4/docs/04_agent_collab/outputs/claude/`

1. `01_流转线_实体与语义合同.md`
   - 统一实体定义
   - 状态流转语义
   - data_origin 正式合同
2. `02_流转线_数据准备与门禁设计.md`
   - 最小可用数据集
   - 初始化 / 增量 / snapshot / baseline 的前置数据要求
   - Gate 设计与通过条件
3. `03_流转线_API与流程验收清单.md`
   - 每个核心模块应如何验证
   - 哪些必须查库，哪些必须看 API，哪些必须看页面

## 强制约束

- 必须正面处理 rebuild3 曾经出现的“页面有数据但主语不真实”问题
- 必须要求页面/API/表/data_origin 四者绑定
- 必须把 synthetic 的使用边界写清楚，不能模糊化
- 必须把 compare / governance 是正式模块还是降级模块写清楚
- 所有步骤都要写验证要求

## 你不要做的事

- 不输出泛泛架构图描述
- 不只复述 rebuild3 文档
- 不写成“以后再说”的建议清单
- 不忽略具体 Gate 和验收动作
