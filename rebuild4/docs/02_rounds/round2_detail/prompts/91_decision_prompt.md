# Decision Prompt - round2_detail

任务：从 3 个 agent 输出和合并稿中，只提取真正需要人类决策的问题。

输入：

- `rebuild4/docs/02_rounds/round2_detail/outputs/*`
- `rebuild4/docs/02_rounds/round2_detail/merged/*`

输出：

- `rebuild4/docs/02_rounds/round2_detail/decisions/01_待裁决问题清单.md`

硬约束：

- 只收录真正影响方向、结构、合同、Gate 或最终执行成本的问题
- 不要把文字风格差异上抛
- 每个问题都必须提供 A / B / C 三个选项
- 每个选项都必须写影响
- 必须给出推荐项
- 问题数量宁少勿滥
