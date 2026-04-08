# Claude Prompt - Round 1 Plan

请完成 rebuild4 第 1 轮“总体评估与计划”的独立输出。

你的风格要求：

- 偏语义一致性、系统逻辑、边界清晰
- 重点检查文档之间是否存在方向冲突、概念冲突、门禁缺失
- 要帮助主控识别“如果现在不冻结，后面一定会跑偏”的点

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round1_plan/00_round_goal.md`
- `rebuild4/docs/02_rounds/round1_plan/prompts/00_共享约束.md`
- `rebuild4/docs/01_inputs/01_foundation/*`
- `rebuild4/docs/01_inputs/02_research/*`
- `rebuild4/docs/01_inputs/03_ui_v2/design_notes.md`
- `rebuild4/docs/01_inputs/04_reference/*`

你必须生成到：`rebuild4/docs/02_rounds/round1_plan/outputs/claude/`

文件：

1. `01_总体评估与计划.md`
2. `02_主要风险与缺口.md`
3. `03_候选裁决问题.md`

强制要求：

- 本轮不要访问页面
- 所有数据库事实用 `PG17 MCP`
- 任何重要概念都必须说明边界
- 重点说明：哪些问题如果不在第 1 轮裁决，后面会反复返工
