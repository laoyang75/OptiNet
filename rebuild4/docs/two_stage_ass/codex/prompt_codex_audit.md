# 流式架构审计 — Codex 独立评估

> 你是独立评审员之一。另外还有两个 agent（Claude、Gemini）在独立执行同样的审计，你不知道他们的结论。  
> 请完整阅读所有指定材料，独立给出你的判断。

---

## 背景

rebuild4 是基站信号数据的流式治理系统。近期完成了两个关键变更：

1. **ETL 管道完成**：Parse → Clean → Fill，产出 `etl_filled`（~688K 行，55列）
2. **去掉初始化**：流式评估实验证明逐天累积与批量计算数学等价（Day7 质心偏差 0.00m，生命周期一致率 98.9%），因此删除了11步初始化流程，改为 `profile.py` 直接从 `etl_filled` 全量构建画像

**项目当前阶段**：基本模块已开发完毕，需要评估如何调整。不是开发新功能，而是审计现状、找出结构性问题、提出调整建议。

---

## 待审计的核心问题

### 问题 1: 流转可视化断裂

侧边栏有"流转总览"、"流转快照"、"等待/观察工作台"等页面，但它们的数据源设计依赖**逐批次的状态变化**（哪些 Cell 从 waiting → observing → active），而当前画像构建是一次性全量计算，没有批次、没有增量、没有状态转换记录。

需要评估：
- `flow.py`、`FlowOverviewPage.vue`、`FlowSnapshotPage.vue` 的数据源是什么？是否有实际数据？
- `ObservationWorkspacePage.vue` 的数据源是什么？
- 这些页面原本设计要展示什么信息？当前能正常工作吗？
- 修复方向：应该让画像构建产出增量变化记录，还是重新设计这些页面的定位？

### 问题 2: 数据版本管理缺失

`rebuild4_meta` schema 中有 `run`、`batch`、`contract_version`、`rule_set_version` 等元数据表，设计用于管理"在同一研究语境下的数据版本"。但当前画像构建跳过了这些概念——直接 DROP + CREATE 画像表，不记录 run_id、batch_id。

需要评估：
- `rebuild4_meta` 中哪些表仍在使用？哪些已成空壳？
- `RunBatchCenterPage.vue` 当前能正常显示数据吗？
- 是否需要让 `profile.py` 每次运行时注册 run + batch？
- 数据版本管理的最小可行方案是什么？

### 问题 3: 参数与画像耦合

生命周期阈值（obs >= 3, devices >= 2, P90 < 1500m, span >= 24h）和所有分类规则（collision 2.2km, stable 500m 等）都硬编码在 `profile.py` 的 SQL 中。

需要评估：
- 哪些参数应该外部化为可配置项？（区分"核心算法不应变" vs "业务阈值应可调"）
- 参数变更后是否需要全量重算？能否局部重算？
- 参数配置的 UI 应该放在哪里？

### 问题 4: 整体架构一致性

当前系统：

```
前端页面               后端 API                数据层
────────────────────────────────────────────────────────
流转总览          ← flow.py            ← rebuild4_meta.batch_flow_summary (可能为空)
流转快照          ← flow.py            ← rebuild4_meta.batch_snapshot (可能为空)
运行/批次中心     ← runs.py            ← rebuild4_meta.run/batch (可能为空)
Cell/BS/LAC 画像  ← profiles.py        ← rebuild4.etl_dim_cell/bs/lac (有数据)
等待/观察工作台   ← workspaces.py      ← ???
异常工作台        ← workspaces.py      ← ???
对象浏览          ← objects.py         ← ???
基线/画像         ← baseline.py        ← ???
基础数据治理      ← governance.py      ← rebuild4_meta.* (部分有数据)
ETL 数据处理      ← governance_foundation.py ← rebuild4_meta.etl_run_stats (有数据)
```

需要评估：
- 标记 `???` 的数据源当前是什么状态？
- 哪些页面能正常工作？哪些是空壳？
- 从用户视角，打开这个系统后，能完成什么操作流程？不能完成什么？

---

## 必须阅读的代码文件

**后端 API（每个 router 都要读）**：
- `rebuild4/backend/app/routers/flow.py`
- `rebuild4/backend/app/routers/runs.py`
- `rebuild4/backend/app/routers/objects.py`
- `rebuild4/backend/app/routers/workspaces.py`
- `rebuild4/backend/app/routers/baseline.py`
- `rebuild4/backend/app/routers/profiles.py`
- `rebuild4/backend/app/routers/governance.py`
- `rebuild4/backend/app/routers/governance_foundation.py`
- `rebuild4/backend/app/routers/compare.py`
- `rebuild4/backend/app/main.py`
- `rebuild4/backend/app/core/context.py`

**画像构建**：
- `rebuild4/backend/app/etl/profile.py`
- `rebuild4/backend/app/etl/pipeline.py`

**前端（每个页面都要读）**：
- `rebuild4/frontend/src/App.vue`
- `rebuild4/frontend/src/router.ts`
- `rebuild4/frontend/src/lib/api.ts`
- `rebuild4/frontend/src/pages/` 下所有 `.vue` 文件

**文档（理解原始设计意图）**：
- `rebuild4/docs/01_etl/00_总览.md`
- `rebuild4/docs/02_profile/00_总览.md`
- `rebuild4/docs/02_profile/01_cell.md`
- `rebuild4/docs/02_profile/04_cell_research.md`
- `rebuild4/docs/02_profile/05_pipeline.md`
- `rebuild4/docs/02_profile/06_流式评估.md`
- `rebuild4/docs/03_final/02_数据生成与回灌策略.md`
- `rebuild4/docs/01_inputs/03_ui_v2/pages/` 下所有文档
- `rebuild4/docs/01_inputs/04_reference/rebuild3_core/01_rebuild3_说明_最终冻结版.md`（§6-§9）

---

## 必须检查的数据库状态

使用 `mcp__PG17__execute_sql` 执行：

```sql
-- 1. rebuild4_meta 中各表的数据量
SELECT table_name FROM information_schema.tables WHERE table_schema = 'rebuild4_meta' ORDER BY table_name;

SELECT COUNT(*) FROM rebuild4_meta.run;
SELECT COUNT(*) FROM rebuild4_meta.batch;
SELECT COUNT(*) FROM rebuild4_meta.batch_flow_summary;
SELECT COUNT(*) FROM rebuild4_meta.batch_snapshot;

-- 2. 画像表的数据量和 lifecycle 分布
SELECT lifecycle_state, COUNT(*) FROM rebuild4.etl_dim_cell GROUP BY 1;
SELECT lifecycle_state, COUNT(*) FROM rebuild4.etl_dim_bs GROUP BY 1;
SELECT lifecycle_state, COUNT(*) FROM rebuild4.etl_dim_lac GROUP BY 1;

-- 3. workspaces/objects/baseline 依赖的表（逐表探查）
```

---

## 输出要求

将你的结论保存到 `rebuild4/docs/two_stage_ass/codex/audit_result.md`。

### 1. 现状诊断报告

对每个前端页面，给出：
- **数据源状态**：有数据 / 空表 / 表不存在
- **功能状态**：正常可用 / 有数据但展示不完整 / 完全不可用
- **与原设计的偏差**：简述当前实现与 UI 文档规格的差距

### 2. 四个核心问题的具体分析

对每个问题，给出：
- **根因分析**：为什么会出现这个问题
- **影响范围**：影响哪些页面、哪些用户操作
- **建议方案**：具体的修复/重构方向（不需要详细代码，但需要指出关键的数据流变化）
- **优先级**：P0（阻塞核心功能）/ P1（影响用户体验）/ P2（架构优化）

### 3. 整体重构建议

基于以上分析，给出分阶段修复计划：
- **第一阶段（必须做）**：让系统从用户视角可用
- **第二阶段（应该做）**：补充数据版本和参数管理
- **第三阶段（可以做）**：完善流转可视化和增量观察能力

---

## 约束

- 不修改任何代码，仅做分析
- 保持 ETL + 画像管道（profile.py）不变——这是已验证的正确实现
- 所有建议必须具体到文件路径和数据表名
- 评估必须基于实际代码和数据库状态，不能基于假设
- 这是研究项目，不要以生产系统标准过度工程化
