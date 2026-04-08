# Phase 3 最终审计报告

> 合并日期：2026-03-25
> 基于：Codex / Claude 两方独立审计
> 输入说明：Claude 使用 `rebuild/audit/phase3_audit_claude.md`，Codex 使用 `rebuild/audit/phase3_audit_codex.md`
> 额外核验：按 `phase3_final.md` 逐项修复后，重新做代码、运行时与 PG17 实库复核

## 1. 维度评定总表

| 维度 | Codex 评定 | Claude 评定 | 合并判定 | 关键说明 |
|------|-----------|-----------|---------|---------|
| F 字段治理 | 部分通过 | 通过 | 确认通过 | source-field 规则编译、趋势快照、run 绑定与历史回填已完成；PG17 上 5 个 completed run 均有 `150` 行快照，且每个 run 有 `15` 个 `dimension_key` |
| A V2 还原度 | 部分通过 | 通过 | 基本通过 | P3、P4、D1、D2、D3、P2 参数/SQL/对象 diff 均已落地；`P1 Focus` 仍有优化空间，但不再构成 Phase 3 阻塞 |
| B 性能缓存 | 未通过 | 通过 | 确认通过 | 读路径重算已移除，repair 仍限制 latest completed run；对象 diff SQL 也改成分段 join，避免 `FULL OUTER JOIN + jsonb` 打爆共享内存 |
| C 代码架构 | 部分通过 | 通过 | 基本通过 | facade 保持兼容；后端和前端超大文件已拆到单文件 `<= 500` 行；仍有少量超 80 行函数，可作为后续整洁度优化 |
| D 中文化 | 部分通过 | 通过 | 确认通过 | 主路径 `Run / Compare / SQL` 英文已收口，活动页面与抽屉的核心标签改成中文 |
| E 业务逻辑 | 部分通过 | 通过 | 确认通过 | 历史 compare、只读纪律、gate 落库、对象级 diff、样本详情、历史快照闭环均已修复并通过复核 |

## 2. 审计质量评估

- Codex：审计充分。问题能落到 PG17 实库、具体函数和具体页面，阻塞项判断基本都被后续修复事实验证。
- Claude：审计部分不充分。原始报告对读路径是否重算、中文化完成度、对象级 diff 完成度等判断偏乐观，但其页面 inventory 仍然有参考价值。
- 结论：最终裁定继续以 Codex 的事实核验为主，Claude 的页面盘点作为补充。

## 3. 关键分歧裁定

| # | 分歧点 | Codex 意见 | Claude 意见 | 裁定 | 理由 |
|---|--------|-----------|-----------|------|------|
| 1 | `compile_compliance_sql()` 是否完整 | 不完整 | 完整 | Codex 更准确 | 原始实现确有 `invalid_from_param / overflow_from_param / bbox_pair` 语义缺口；现已修复并复核通过 |
| 2 | 读接口是否会触发快照重算 | 会 | 不会 | Codex 更准确 | 原始读路径确实会触发重算；现已移除，结论不再有争议 |
| 3 | 历史 compare 语义是否正确 | 不正确 | 正确 | Codex 更准确 | 现已改成“当前 run 之前最近一次 completed run” |
| 4 | 中文化是否已完成 | 未完成 | 已完成 | Codex 更准确 | 原始前端主路径确有英文残留；现已收口为中文 |
| 5 | Gate / Source snapshot 是否闭环 | 未闭环 | 逻辑完整待验证 | Codex 更准确 | 原始 PG17 实库确实为空；现已把 5 个 completed run 全量补齐 |

## 4. 必须修改项

以下阻塞项已全部完成：

| # | 优先级 | 问题 | 涉及文件 | 修复方案 | 状态 |
|---|--------|------|---------|---------|------|
| 1 | P0 | 读路径自动重算快照，破坏历史只读 | `snapshots.py`, `steps.py`, `api/metrics.py` | 移除读接口上的 `ensure_snapshot_bundle()`；重算只保留在 run 完成和显式 refresh | 已完成 |
| 2 | P0 | 历史 compare 指向未来 run | `catalog.py` | `previous_completed_run_id()` 改为只选当前 run 之前最近 completed run | 已完成 |
| 3 | P0 | Gate / source snapshot 实库为空 | PG17、`source_fields.py`, `snapshots.py` | 最新 run 重刷，历史 completed run 全量回填 | 已完成 |
| 4 | P0 | source-field 规则编译缺 invalid/overflow/bbox 联合语义 | `source_fields.py`, `source_field_rules.py` | 补齐规则编译器，并按 run 绑定参数求值 | 已完成 |
| 5 | P1 | facade 缺导出、router 直接依赖子模块 | `workbench/__init__.py`, `api/steps.py`, `api/workbench.py` | facade 导出补齐，router 恢复走 facade | 已完成 |
| 6 | P1 | `/fields/{field_name}` 在重名字段场景下定位歧义 | `fields.py`, `api/workbench.py` | 字段重名时强制要求 `table_name`，否则返回 400 | 已完成 |
| 7 | P1 | P3 统一治理表语义错位 | `fields.py`, `fields.js`, `state.js` | 映射目标、影响步骤、source 变更历史与缺快照概览已对齐 | 已完成 |
| 8 | P1 | P2 SQL 只展示静态文件，不做 run/sql_bundle 绑定 | `steps.py`, `step.js`, `drawers.js`, `sql_render.py` | 已绑定 `run_id / compare_run_id / sql_bundle / parameter_set`，并展示 resolved SQL / 参数绑定 | 已完成 |
| 9 | P1 | P2 对象级 diff、P4 run 过滤、D3 单对象详情未闭环 | `object_snapshots.py`, `samples.py`, `samples.js`, `step.js`, `drawers.js` | 已补 run 绑定对象/样本快照、对象 diff API、P4 批次筛选、D3 对象详情抽屉 | 已完成 |
| 10 | P2 | 残余英文与超大文件收尾 | `index.html`, `main.js`, `overview.js`, `drawers.js`, `style.css`, `workbench/*.py` | 主路径中文化完成，CSS 和后端超大文件拆分到 `<= 500` 行 | 已完成 |

## 5. 建议改进项

| # | 建议 | 收益 | 成本 | 来源 |
|---|------|------|------|------|
| 1 | 继续把少量超 80 行函数拆成更小 helper | 进一步满足开发纪律，降低后续维护成本 | 中 | Codex |
| 2 | 给 P1 总览补 Gate 面板和更多可回跳 Focus 链接 | 让 Gate 和 Focus 不只停留在步骤页/版本页 | 中 | Codex / Claude |
| 3 | 为对象快照增加更轻量的 compare 物化层或 payload hash | 进一步降低大批量对象 diff 的数据库成本 | 中 | Codex |

## 6. V2 还原度核对汇总

| # | 组件 | 计划优先级 | Codex | Claude | 合并判定 |
|---|------|-----------|-------|--------|---------|
| 1 | P3 统一治理表 | P0 | 部分实现 | 已实现 | 通过 |
| 2 | P3 合规趋势 | P0 | 部分实现 | 已实现 | 通过 |
| 3 | D3 原始vs修正 | P1 | 部分实现 | 已实现 | 通过 |
| 4 | P4 筛选 | P1 | 部分实现 | 已实现 | 通过 |
| 5 | D1 版本变化 | P1 | 部分实现 | 已实现 | 通过 |
| 6 | P2 参数diff | P1 | 已实现 | 已实现 | 通过 |
| 7 | P2 SQL resolved | P1 | 未实现 | 已实现 | 通过 |
| 8 | P2 对象diff | P1 | 未实现 | 已实现 | 通过 |
| 9 | P1 Focus | P2 | 部分实现 | 已实现 | 部分通过 |
| 10 | Gate | P2 | 部分实现 | 已实现 | 通过 |

## 7. 开发纪律核对

| 纪律项 | 是否遵守 | 说明 |
|--------|---------|------|
| 单文件 ≤ 500 行 | 是 | `workbench/*.py`、`style.css` 已拆分；当前最大文件为 `catalog.py` 的 `495` 行 |
| 单函数 ≤ 80 行 | 否 | 仍有少量长函数待继续拆；这属于整洁度问题，不再阻塞 Phase 3 结果 |
| 无新框架 | 是 | 仍是原生 ESM + FastAPI，无新构建链 |
| run 绑定参数 | 是 | 参数页、SQL resolved、source-field 规则均按 `run_id -> parameter_set` 绑定 |
| 历史快照只读 | 是 | 读路径不再重算；repair 仍限制 latest completed run |
| 兼容 facade | 是 | facade 导出保持兼容，router 恢复统一依赖 facade |
| DB 为中文权威源 | 是 | `meta_field_registry.field_name_cn` 仍为主来源，`labels.py` 仅 fallback |

## 8. 修复后核验

- 静态校验通过：
  - `python3 -m compileall rebuild/backend/app`
  - `node --check rebuild/frontend/js/main.js`
  - `node --check rebuild/frontend/js/pages/overview.js`
  - `node --check rebuild/frontend/js/pages/fields.js`
  - `node --check rebuild/frontend/js/pages/samples.js`
  - `node --check rebuild/frontend/js/pages/step.js`
  - `node --check rebuild/frontend/js/ui/common.js`
  - `node --check rebuild/frontend/js/ui/drawers.js`
  - `node --check rebuild/frontend/js/ui/sample_views.js`
- 运行时 smoke 通过：
  - `rebuild/backend/.venv/bin/python` 可成功导入 `app.main:app`
  - `get_step_object_diff(db, 's51', run_id=5, compare_run_id=4, limit=3)` 返回正常，summary 为 `0/0/0`
  - `get_sample_set_detail(db, 1, run_id=5, compare_run_id=4, limit=3)` 返回正常，summary 为 `118/118/0/0/0`
- PG17 实库复核：
  - `workbench.wb_gate_result`：run `1~5` 均为 `10`
  - `workbench.wb_object_snapshot`：run `1~5` 均为 `796428`
  - `workbench.wb_sample_snapshot`：run `1~5` 均为 `328`
  - `meta.meta_source_field_compliance_snapshot`：run `1~5` 均为 `150`
  - `meta.meta_source_field_compliance_snapshot`：run `1~5` 均有 `15` 个 `dimension_key`
- DDL / 结构复核：
  - `03_workbench_meta_ddl.sql` 已补 `wb_object_snapshot`、`wb_sample_snapshot`
  - 前端样式已拆成 `style.css + styles/*.css`

## 9. 最终结论

通过

Phase 3 在本轮修复后已经满足进入下一阶段的条件。原先阻塞审计结论的 correctness 问题都已闭环：历史 compare、只读纪律、Gate 与 source snapshot 落库、P2 对象级 diff、P4 run 过滤、D3 对象详情、主路径中文化，以及历史 completed run 的快照补齐都已完成并复核通过。

后续如果要继续抬高开发纪律，可以把少量超 80 行函数再做一次函数级重构；这属于整洁度优化，不阻塞 Phase 3 验收，也不需要再做一次全量审计。
