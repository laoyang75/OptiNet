# rebuild4 docs

从现在开始，`rebuild4/docs` 按“输入资料 -> 多轮同题多 agent 评估 -> 人类裁决 -> finalization 冻结 -> 最终任务书”的方式组织。

如果你是人类使用者，阅读顺序只需要遵循：

1. `rebuild4/docs/00_runbook/00_Runbook.md`
2. 当前轮次的 `merged/` 文档
3. 当前轮次的 `decisions/01_待裁决问题清单.md`（如果存在）
4. `rebuild4/docs/03_final/` 中的最终冻结文档

## 目录结构

### `00_runbook/`

给人类使用的操作说明：

- 怎么读文档
- 3 轮 + finalization 怎么运行
- 什么时候需要你裁决
- 裁决文件怎么回复

### `01_inputs/`

全部输入资料，只作为事实来源与参考，不直接作为执行任务书。

### `02_rounds/`

多轮同题多 agent 协作区：

- `round1_plan/`
- `round2_detail/`
- `round3_execution/`
- `finalization/`

### `03_final/`

最终冻结的正式文件：

- 冻结基线
- 技术栈与基础框架约束
- 数据生成与回灌策略
- 最终执行任务书
- 最终校验清单
- 本轮范围与降级说明

### `99_archive/`

旧版本整理结果归档，不再作为当前主流程输入。

## 当前流程原则

- 3 个 agent 做相同任务，不再按数据/流程/UI 分工出稿
- 前两轮不强制看页面，主要依赖文档与 `PG17 MCP`
- 第三轮必须看页面
- finalization 不重新浏览网页，只复用 round3 的页面证据
- 只有真正需要你决策的问题，才进入裁决文件
- 最终执行前，只认 `03_final/` 中冻结的文档
