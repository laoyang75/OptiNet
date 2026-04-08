# Gemini Prompt - Finalization

请完成 finalization 阶段的独立输出。

这是高约束冻结编制任务。禁止偷懒，禁止把前三轮内容简单拼接，禁止忽略已裁决结果，禁止重新访问页面。

## 强制工作方式

1. 先列出你实际阅读的文档清单
2. 列出你引用的 round3 页面证据来源（如截图路径或 merged 页面结论）
3. 列出你实际执行的 PG17 查询主题
4. 再进入正式输出
5. 如果任何一项未完成，必须明确写 blocked，不允许补写推测内容

## 强制工具要求

- 本轮禁止重新访问页面
- 只能引用 round3 codex 输出目录下现有截图和 round3 merged 中的页面结论
- 必须使用 `PG17 MCP`
- 不允许假装已经做了新的页面检查

## 每个输出文件必须具备的结构

每一章都必须写：

- 结论
- 依据（文件路径 / 截图路径 / PG17）
- 风险
- 校验
- 若失败如何处理

## 你必须覆盖的最终冻结主题

至少必须明确写出：

- 前三轮哪些结论已正式冻结
- 所有 decisions 是否已回写
- 技术栈是否单独冻结
- 启动器是否归入基础框架能力
- 数据生成与回灌策略如何进入最终任务书
- 是否仍存在必须延期的议题

## 你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/finalization/00_round_goal.md`
- `rebuild4/docs/02_rounds/finalization/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round2_detail/merged/*`
- `rebuild4/docs/02_rounds/round3_execution/merged/*`
- `rebuild4/docs/02_rounds/*/decisions/*`
- `rebuild4/docs/01_inputs/*`

你必须生成到：`rebuild4/docs/02_rounds/finalization/outputs/gemini/`

文件：

1. `01_最终冻结基线草案.md`
2. `02_最终范围技术栈与数据策略草案.md`
3. `03_候选裁决问题.md`

额外硬约束：

- `01_最终冻结基线草案.md` 至少必须包含：
  - 已冻结结论清单
  - 已回写裁决清单
  - 仍残留冲突检查
- `02_最终范围技术栈与数据策略草案.md` 至少必须包含：
  - 技术栈冻结
  - 启动器/基础框架约束
  - 数据生成与回灌策略
  - 本轮范围与降级说明
- `03_候选裁决问题.md` 只能放真正卡住 final 文档冻结的问题
- 输出末尾必须附“自检清单”和“我最可能遗漏的部分”
