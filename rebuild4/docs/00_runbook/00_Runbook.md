# Runbook

这是 rebuild4 文档系统的使用说明。

## 1. 你现在只需要做什么

作为人类决策者，你不需要跟着每个细节推进，只需要在 4 个时点介入：

1. 看每一轮的合并稿
2. 如果存在冲突，看裁决问题文件并回复 A / B / C
3. 看 finalization 的冻结稿
4. 最后审阅 `03_final/` 中的正式任务书

## 2. 整个协作流程

### 第 1 轮：总体评估与计划

目标：统一 rebuild4 的范围、原则、先后顺序、关键风险。

你需要看：

- `rebuild4/docs/02_rounds/round1_plan/merged/01_统一计划.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/02_统一风险与缺口.md`
- `rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md`（如果有）

### 第 2 轮：细化设计

目标：把第 1 轮计划细化成实体、表、字段、API、Gate、校验方式。

你需要看：

- `rebuild4/docs/02_rounds/round2_detail/merged/01_统一细化设计.md`
- `rebuild4/docs/02_rounds/round2_detail/merged/02_统一细化校验基线.md`
- `rebuild4/docs/02_rounds/round2_detail/decisions/01_待裁决问题清单.md`（如果有）

### 第 3 轮：最终执行任务草案

目标：基于前两轮结果，生成最终执行任务文档草案。

你需要看：

- `rebuild4/docs/02_rounds/round3_execution/merged/01_统一最终执行任务书.md`
- `rebuild4/docs/02_rounds/round3_execution/merged/02_统一最终校验清单.md`
- `rebuild4/docs/02_rounds/round3_execution/decisions/01_待裁决问题清单.md`（如果有）

### Finalization：最终冻结与任务书生成输入

目标：把前三轮 merged 与全部裁决真正冻结，并为 `03_final/` 生成正式输入。

你需要看：

- `rebuild4/docs/02_rounds/finalization/merged/01_最终冻结基线.md`
- `rebuild4/docs/02_rounds/finalization/merged/02_最终技术栈与基础框架约束.md`
- `rebuild4/docs/02_rounds/finalization/merged/03_数据生成与回灌策略.md`
- `rebuild4/docs/02_rounds/finalization/merged/04_本轮范围与降级说明.md`
- `rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md`（如果有）

### 最终冻结

当 finalization 完成并且你审阅通过后，冻结到：

- `rebuild4/docs/03_final/00_最终冻结基线.md`
- `rebuild4/docs/03_final/01_最终技术栈与基础框架约束.md`
- `rebuild4/docs/03_final/02_数据生成与回灌策略.md`
- `rebuild4/docs/03_final/03_最终执行任务书.md`
- `rebuild4/docs/03_final/04_最终校验清单.md`
- `rebuild4/docs/03_final/05_本轮范围与降级说明.md`

## 3. 三个 agent 的角色

3 个 agent 做的是“同题独立评估 / 编制”，不是“各写一块”。

区别只在侧重点：

- Codex：偏精确、动作、结构、可执行性
- Claude：偏语义一致性、边界、系统逻辑
- Gemini：偏覆盖完整性、交付完整性，但 prompt 会被写得最严格，防止偷懒

## 4. 页面检查规则

### 第 1 轮

- 不要求看页面
- 只看文档和 `PG17 MCP`

### 第 2 轮

- 不要求看页面
- 只看文档和 `PG17 MCP`

### 第 3 轮

- 必须看页面
- Codex：必须使用 Playwright
- Claude / Gemini：必须使用 Antigravity 浏览器
- 三者都必须查询 `PG17 MCP`

### Finalization

- 不重新看页面
- 如需页面证据，只能复用 round3 的截图与页面结论
- 三者仍可使用 `PG17 MCP`

## 5. 你如何回复裁决

当你看到 `01_待裁决问题清单.md` 时，只需要按下面格式回复：

- `D-001: A`
- `F-001: C`

不需要重新解释背景；我会按你的裁决继续整合。

## 6. 如果你要亲自发起一轮

请看：

- `rebuild4/docs/00_runbook/04_如何实际发起一轮.md`
- `rebuild4/docs/00_runbook/05_prompt与输出目录清单.md`
