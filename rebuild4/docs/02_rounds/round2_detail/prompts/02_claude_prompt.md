# Claude Prompt - Round 2 Detail

请完成 rebuild4 第 2 轮“细化设计”的独立输出。

你的重点：

- 实体语义是否一致
- `data_origin` 边界是否稳定
- Gate 是否真能阻断跑偏
- 页面/API/表主语是否真的统一

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round2_detail/00_round_goal.md`
- `rebuild4/docs/02_rounds/round2_detail/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round1_plan/decisions/*`（如果有）
- `rebuild4/docs/01_inputs/*`

你必须生成到：`rebuild4/docs/02_rounds/round2_detail/outputs/claude/`

文件：

1. `01_细化设计总稿.md`
2. `02_实体字段接口与Gate细化.md`
3. `03_候选裁决问题.md`

强制要求：

- 本轮不要访问页面
- 所有数据库事实用 `PG17 MCP`
- 必须指出哪些细节若不冻结，后续执行会出现多解释空间
