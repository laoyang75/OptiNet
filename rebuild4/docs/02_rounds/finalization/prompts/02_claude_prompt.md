# Claude Prompt - Finalization

请完成 finalization 阶段的独立输出。

你的重点：

- 检查前三轮与所有 decisions 是否还有逻辑冲突
- 检查最终口径是否真的只有一个解释空间
- 检查技术栈、启动器、数据生成策略是否已经进入正式执行约束

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
- 如需要页面证据，只能引用 round3 的既有截图与结论
- 必须使用 `PG17 MCP`

你必须生成到：`rebuild4/docs/02_rounds/finalization/outputs/claude/`

文件：

1. `01_最终冻结基线草案.md`
2. `02_最终范围技术栈与数据策略草案.md`
3. `03_候选裁决问题.md`
