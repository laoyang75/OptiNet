# Merge Prompt - finalization

任务：读取 3 个 agent 的 finalization 输出并统一合并。

输入目录：

- `rebuild4/docs/02_rounds/finalization/outputs/codex/`
- `rebuild4/docs/02_rounds/finalization/outputs/claude/`
- `rebuild4/docs/02_rounds/finalization/outputs/gemini/`

你必须重点读取：

- `01_最终冻结基线草案.md`
- `02_最终范围技术栈与数据策略草案.md`
- `03_候选裁决问题.md`

输出到：`rebuild4/docs/02_rounds/finalization/merged/`

目标文件：

1. `01_最终冻结基线.md`
2. `02_最终技术栈与基础框架约束.md`
3. `03_数据生成与回灌策略.md`
4. `04_本轮范围与降级说明.md`

合并原则：

- 先检查前三轮与 decisions 是否完全回写
- 再冻结技术栈、启动器、数据策略
- 不再重新讨论已裁决方向
- 只有真正影响 final 文档冻结的问题，才留给裁决文件
