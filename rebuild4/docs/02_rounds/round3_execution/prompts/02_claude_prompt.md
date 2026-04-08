# Claude Prompt - Round 3 Execution

请完成 rebuild4 第 3 轮“最终执行任务文档”的独立输出。

你的重点：

- 检查最终任务书中的步骤是否真的有逻辑闭环
- 检查 Gate、来源合同、页面验收是否自洽
- 检查任务书有没有让执行者再次产生多解释空间

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round3_execution/00_round_goal.md`
- `rebuild4/docs/02_rounds/round3_execution/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round2_detail/merged/*`
- `rebuild4/docs/02_rounds/round1_plan/decisions/*`（如果有）
- `rebuild4/docs/02_rounds/round2_detail/decisions/*`（如果有）
- `rebuild4/docs/01_inputs/*`

工具要求：

- 你必须使用 Playwright 检查页面
- 你必须使用 `PG17 MCP`
- 页面检查结果必须写成证据表

你必须生成到：`rebuild4/docs/02_rounds/round3_execution/outputs/claude/`

文件：

1. `01_最终执行任务书草案.md`
2. `02_逐步校验与验收清单草案.md`
3. `03_候选裁决问题.md`
