# Merge Prompt - round3_execution

任务：读取 3 个 agent 的同题输出并统一合并。

输入目录：

- `rebuild4/docs/02_rounds/round3_execution/outputs/codex/`
- `rebuild4/docs/02_rounds/round3_execution/outputs/claude/`
- `rebuild4/docs/02_rounds/round3_execution/outputs/gemini/`

你必须重点读取：

- `01_最终执行任务书草案.md`
- `02_逐步校验与验收清单草案.md`
- `03_候选裁决问题.md`

输出到：`rebuild4/docs/02_rounds/round3_execution/merged/`

目标文件：

1. `01_统一最终执行任务书.md`
2. `02_统一最终校验清单.md`

合并原则：

- 先对齐事实，再对齐结构，再对齐表述
- 数据库事实如涉及计数，必须回到 `PG17 MCP`
- 不要为了“平均三家意见”而模糊化结论
- 能根据已冻结原则裁决的，不要上抛给人类
- 只有真正卡住方向的问题，留给裁决文件
