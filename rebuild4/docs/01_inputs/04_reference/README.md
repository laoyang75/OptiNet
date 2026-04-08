# rebuild4 reference

这里存放 rebuild4 编写阶段需要直接引用的本地副本，目标是尽量把任务书准备工作收拢在 `rebuild4/docs` 内完成。

目录说明：

- `rebuild3_core/`
  - rebuild3 的 Tier 0 核心冻结文档副本
- `rebuild2_baseline/`
  - rebuild2 的数据清理、trusted 构建、数据审计相关文档副本
- `rebuild3_review/`
  - rebuild3 本轮 repair、复盘、字段基线相关文档副本

同步说明：

- 本地副本同步时间：2026-04-05
- 上游原件仍分别位于 `rebuild3/docs/`、`rebuild2/docs/`、`rebuild2/prompts/`
- rebuild4 阶段优先引用本目录副本；如后续发现上游更新，再做一次受控同步
