# rebuild3 docs 索引

## 当前主入口

按下面顺序阅读即可覆盖当前项目的业务、实现边界、设计基线与本轮审计结果：

1. `01_rebuild3_说明_最终冻结版.md` — 业务冻结说明，重点是状态模型、事实分流、Section 7 流式治理过程。
2. `02_rebuild3_预实施任务书_最终冻结版.md` — 实施边界、交付范围与页面读模型。
3. `03_rebuild3_技术栈要求_最终冻结版.md` — 技术栈、Schema、实现约束与验证要求。
4. `UI_v2/` — 当前唯一有效的 UI 基线，包含 `design_notes.md`、`design_system.html`、13 个页面设计稿 HTML 与对应 `*_doc.md`。
5. `api_models.md` — 前后端接口模型与字段说明。
6. `runtime_startup_guide.md` — 本地运行与服务启动说明。
7. `ui_restructure_audit_prompt.md` — 本轮完整审计/修复任务说明。
8. `ui_final_rectification_report.md` — 本轮执行结果、修复清单、验证记录与 docs 整理结论。

## 目录状态

### 保留为当前基线

- `01_rebuild3_说明_最终冻结版.md`
- `02_rebuild3_预实施任务书_最终冻结版.md`
- `03_rebuild3_技术栈要求_最终冻结版.md`
- `UI_v2/`
- `api_models.md`
- `runtime_startup_guide.md`
- `ui_restructure_prompt.md`
- `ui_restructure_audit_prompt.md`
- `ui_final_rectification_report.md`

### 保留为过程参考（未归档）

这些目录仍保留，原因是它们互相存在交叉引用，且对追溯决策背景仍有价值：

- `Docs/` — UI_v2 审计后问题清单、确认问题与开发补丁。
- `Prompt/` — 多轮任务说明与评审 Prompt。
- `UI/` — UI_v1 / 旧版设计参考，已不再作为实现基线。
- `claude/`
- `codex/`
- `04_agent_prompts_UI与开发.md`
- `04a_prompt_UI设计.md`
- `04b_prompt_开发实施.md`
- `04c_UI目的与改版说明.md`
- `04d_prompt_UI设计_重写版.md`
- `04e_prompt_开发实施_正式重构流程版.md`
- `04f_prompt_开发实施_UI优先纠偏与归档版.md`
- `00_审核结论.md`
- `param_matrix.md`

### 已归档

2026-04-05 审计后，以下中间产物已移入：

- `archive/20260405_ui_reaudit/`

该归档批次包含：

- 旧审计输出：`ui_audit/`、`gemini_ui_audit/`、`ui_acceptance_report.md`
- 旧实施计划与映射：`impl_plan.md`、`impl_alignment.md`、`ui_first_impl_plan.md`、`ui_mapping_matrix.md`
- 旧运行/对照/回放报告：`sample_*`、`full_*`、`replay_log.md`
- 旧复核与中间报告：`current_tree_audit.md`、`data_reaudit_report.md`、`rectification_audit.md`
- 旧归档报告：`archive_execution_report.md`、`archive_manifest_20260404_ui_spike.md`
- 旧问题清单：`issues.md`

## 当前推荐目录结构

```text
rebuild3/docs/
├── 01_rebuild3_说明_最终冻结版.md
├── 02_rebuild3_预实施任务书_最终冻结版.md
├── 03_rebuild3_技术栈要求_最终冻结版.md
├── UI_v2/
├── Docs/
├── Prompt/
├── api_models.md
├── runtime_startup_guide.md
├── ui_restructure_prompt.md
├── ui_restructure_audit_prompt.md
├── ui_final_rectification_report.md
└── archive/
    └── 20260405_ui_reaudit/
```

## 使用建议

- 做产品/流程对齐时，优先看冻结文档 + `UI_v2/`。
- 做实现或联调时，补充看 `api_models.md`、`runtime_startup_guide.md`、`Docs/`。
- 做历史追溯时，去 `archive/` 查旧审计和旧实施文档，不要把它们当当前基线。
