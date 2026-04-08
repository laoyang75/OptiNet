# Gemini Prompt - Round 1 Plan

请完成 rebuild4 第 1 轮“总体评估与计划”的独立输出。

你必须比平时更严格地执行任务；禁止偷工减料，禁止只写总结，禁止跳过章节。

## 你的强制工作方式

1. 先列出你实际阅读过的输入文件路径
2. 再进入正式输出
3. 每一章都必须包含：
   - 结论
   - 依据（带文件路径）
   - 风险
   - 校验方式
4. 所有数据库事实必须通过 `PG17 MCP execute_sql`
5. 如果你认为“无问题”，也必须解释为什么无问题
6. 不允许省略表格、风险段、自检段
7. 最后一节必须写“我可能遗漏的点”
8. 你必须按固定章节输出，不允许自行删减章节

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round1_plan/00_round_goal.md`
- `rebuild4/docs/02_rounds/round1_plan/prompts/00_共享约束.md`
- `rebuild4/docs/01_inputs/01_foundation/*`
- `rebuild4/docs/01_inputs/02_research/*`
- `rebuild4/docs/01_inputs/03_ui_v2/design_notes.md`
- `rebuild4/docs/01_inputs/04_reference/*`

你必须生成到：`rebuild4/docs/02_rounds/round1_plan/outputs/gemini/`

文件：

1. `01_总体评估与计划.md`
2. `02_主要风险与缺口.md`
3. `03_候选裁决问题.md`

额外硬约束：

- 本轮禁止访问页面
- 禁止只输出概念总结
- `03_候选裁决问题.md` 必须只列真正值得人类决策的问题
- `01_总体评估与计划.md` 至少必须包含：
  - 输入审计表
  - rebuild4 总体目标判断
  - 三阶段推进建议
  - 必须前置冻结项
- `02_主要风险与缺口.md` 至少必须包含：
  - 风险清单表
  - 每项风险的触发条件
  - 每项风险的预防方式
- 输出末尾必须附“自检清单”
