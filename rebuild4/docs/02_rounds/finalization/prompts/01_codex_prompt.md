# Codex Prompt - Finalization

请完成 finalization 阶段的独立输出。

你的重点：

- 检查前三轮 merged 是否已经足够可执行
- 检查所有裁决是否真正回写
- 把结果压成“可执行、可校验、可回退”的最终冻结基线
- 明确技术栈、启动器、数据生成策略在最终任务书中的落点

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/finalization/00_round_goal.md`
- `rebuild4/docs/02_rounds/finalization/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round2_detail/merged/*`
- `rebuild4/docs/02_rounds/round3_execution/merged/*`
- `rebuild4/docs/02_rounds/*/decisions/*`
- `rebuild4/docs/01_inputs/*`

工具要求：

- 不重新访问页面
- 可以引用 round3 codex 输出中的截图与页面证据
- 必须使用 `PG17 MCP`

你必须生成到：`rebuild4/docs/02_rounds/finalization/outputs/codex/`

文件：

1. `01_最终冻结基线草案.md`
2. `02_最终范围技术栈与数据策略草案.md`
3. `03_候选裁决问题.md`
