# Decision Prompt - finalization

任务：从 3 个 agent 的 finalization 输出和合并稿中，只提取真正影响 final 文档冻结的人类裁决问题。

输入：

- `rebuild4/docs/02_rounds/finalization/outputs/*`
- `rebuild4/docs/02_rounds/finalization/merged/*`

输出：

- `rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md`

硬约束：

- 只收录真正影响 final 冻结口径、技术栈、基础框架、数据生成策略或最终执行范围的问题
- 不要把结构风格问题上抛
- 每个问题都必须提供 A / B / C 选项与影响，并给出推荐项
