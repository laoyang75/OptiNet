# Merge Prompt - round1_plan

任务：读取 3 个 agent 的同题输出并统一合并。

输入目录：

- `rebuild4/docs/02_rounds/round1_plan/outputs/codex/`
- `rebuild4/docs/02_rounds/round1_plan/outputs/claude/`
- `rebuild4/docs/02_rounds/round1_plan/outputs/gemini/`

你必须重点读取：

- `01_总体评估与计划.md`
- `02_主要风险与缺口.md`
- `03_候选裁决问题.md`

输出到：`rebuild4/docs/02_rounds/round1_plan/merged/`

目标文件：

1. `01_统一计划.md`
2. `02_统一风险与缺口.md`

合并原则：

- 先对齐事实，再对齐结构，再对齐表述
- 数据库事实如涉及计数，必须回到 `PG17 MCP`
- 不要为了“平均三家意见”而模糊化结论
- 能根据已冻结原则裁决的，不要上抛给人类
- 只有真正卡住方向的问题，留给裁决文件
